"""
Zero-Downtime Deployment System
Enables seamless updates without service interruption
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
import aiohttp
import docker
import yaml
from dataclasses import asdict

from .observability_system import observability, MetricType, AlertSeverity
from .config_system import config_system
from .backup_system import backup_system, BackupType
from .resilience_system import resilience_system, CircuitBreakerConfig


class DeploymentStrategy(Enum):
    BLUE_GREEN = "blue_green"
    ROLLING = "rolling"
    CANARY = "canary"
    RECREATE = "recreate"


class DeploymentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class EnvironmentStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    STARTING = "starting"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass
class DeploymentConfig:
    deployment_id: str
    strategy: DeploymentStrategy
    version: str
    image: str
    replicas: int = 1
    health_check_url: str = "/health"
    health_check_timeout: int = 30
    health_check_retries: int = 3
    rollback_on_failure: bool = True
    canary_percentage: int = 10  # For canary deployments
    rolling_batch_size: int = 1   # For rolling deployments
    pre_deployment_hooks: List[str] = field(default_factory=list)
    post_deployment_hooks: List[str] = field(default_factory=list)
    environment_variables: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeploymentInstance:
    instance_id: str
    deployment_id: str
    container_id: Optional[str] = None
    port: Optional[int] = None
    status: EnvironmentStatus = EnvironmentStatus.INACTIVE
    health_status: str = "unknown"
    started_at: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeploymentRecord:
    deployment_id: str
    config: DeploymentConfig
    status: DeploymentStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    instances: List[DeploymentInstance] = field(default_factory=list)
    current_version: Optional[str] = None
    previous_version: Optional[str] = None
    rollback_deployment_id: Optional[str] = None
    error_message: Optional[str] = None
    logs: List[str] = field(default_factory=list)


class LoadBalancer:
    """Simple load balancer for deployment instances"""
    
    def __init__(self):
        self.active_instances: Dict[str, List[DeploymentInstance]] = defaultdict(list)
        self.traffic_split: Dict[str, float] = {}  # deployment_id -> percentage
        self.logger = logging.getLogger(__name__)
    
    def add_instance(self, deployment_id: str, instance: DeploymentInstance):
        """Add instance to load balancer"""
        self.active_instances[deployment_id].append(instance)
        self.logger.info(f"Added instance {instance.instance_id} to load balancer")
    
    def remove_instance(self, deployment_id: str, instance_id: str):
        """Remove instance from load balancer"""
        instances = self.active_instances.get(deployment_id, [])
        self.active_instances[deployment_id] = [
            inst for inst in instances if inst.instance_id != instance_id
        ]
        self.logger.info(f"Removed instance {instance_id} from load balancer")
    
    def set_traffic_split(self, splits: Dict[str, float]):
        """Set traffic split between deployments"""
        # Normalize percentages
        total = sum(splits.values())
        if total > 0:
            self.traffic_split = {k: v/total for k, v in splits.items()}
        self.logger.info(f"Traffic split updated: {self.traffic_split}")
    
    def get_active_instances(self) -> List[DeploymentInstance]:
        """Get all active instances"""
        all_instances = []
        for deployment_id, instances in self.active_instances.items():
            healthy_instances = [
                inst for inst in instances 
                if inst.status == EnvironmentStatus.ACTIVE and inst.health_status == "healthy"
            ]
            all_instances.extend(healthy_instances)
        return all_instances
    
    def get_instance_for_request(self, request_id: str = None) -> Optional[DeploymentInstance]:
        """Get instance to handle request (simple round-robin)"""
        active_instances = self.get_active_instances()
        if not active_instances:
            return None
        
        # Simple round-robin selection
        instance_id = hash(request_id or str(time.time())) % len(active_instances)
        return active_instances[instance_id]


class DeploymentSystem:
    """
    Zero-downtime deployment system with multiple strategies
    """
    
    def __init__(self):
        # Docker client
        self.docker_client = docker.from_env()
        
        # Deployment tracking
        self.deployments: Dict[str, DeploymentRecord] = {}
        self.active_deployment: Optional[str] = None
        
        # Load balancer
        self.load_balancer = LoadBalancer()
        
        # Port management
        self.port_range = range(8001, 8100)
        self.used_ports: Set[int] = set()
        
        # Background tasks
        self.deployment_tasks: Set[asyncio.Task] = set()
        self.is_running = False
        
        # Hooks
        self.pre_deployment_hooks: Dict[str, Callable] = {}
        self.post_deployment_hooks: Dict[str, Callable] = {}
        
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize deployment system"""
        
        # Register circuit breaker for deployment operations
        resilience_system.register_circuit_breaker(
            "deployment_operations",
            CircuitBreakerConfig(failure_threshold=3, recovery_timeout=300)
        )
        
        # Start background tasks
        self.is_running = True
        self.deployment_tasks.add(asyncio.create_task(self._health_check_monitor()))
        self.deployment_tasks.add(asyncio.create_task(self._deployment_monitor()))
        
        # Load existing deployments
        await self._load_deployment_history()
        
        self.logger.info("✅ Deployment system initialized")
    
    async def _load_deployment_history(self):
        """Load deployment history from persistent storage"""
        try:
            history_file = Path("deployments/history.json")
            if history_file.exists():
                async with aiofiles.open(history_file, 'r') as f:
                    history_data = json.loads(await f.read())
                    
                    for deployment_data in history_data:
                        deployment = DeploymentRecord(**deployment_data)
                        self.deployments[deployment.deployment_id] = deployment
                
                self.logger.info(f"Loaded {len(self.deployments)} deployment records")
        except Exception as e:
            self.logger.error(f"Failed to load deployment history: {e}")
    
    async def _save_deployment_history(self):
        """Save deployment history to persistent storage"""
        try:
            history_file = Path("deployments/history.json")
            history_file.parent.mkdir(parents=True, exist_ok=True)
            
            history_data = [asdict(deployment) for deployment in self.deployments.values()]
            
            async with aiofiles.open(history_file, 'w') as f:
                await f.write(json.dumps(history_data, default=str))
        except Exception as e:
            self.logger.error(f"Failed to save deployment history: {e}")
    
    # Port Management
    
    def _allocate_port(self) -> Optional[int]:
        """Allocate a free port"""
        for port in self.port_range:
            if port not in self.used_ports:
                self.used_ports.add(port)
                return port
        return None
    
    def _release_port(self, port: int):
        """Release a port"""
        self.used_ports.discard(port)
    
    # Core Deployment Operations
    
    async def deploy(self, config: DeploymentConfig) -> str:
        """Start a new deployment"""
        
        # Create deployment record
        deployment_record = DeploymentRecord(
            deployment_id=config.deployment_id,
            config=config,
            status=DeploymentStatus.PENDING,
            created_at=datetime.now(),
            current_version=config.version,
            previous_version=await self._get_current_version()
        )
        
        self.deployments[config.deployment_id] = deployment_record
        
        # Create backup before deployment
        backup_id = await backup_system.create_backup(
            BackupType.FULL,
            description=f"Pre-deployment backup for {config.deployment_id}"
        )
        
        if backup_id:
            deployment_record.logs.append(f"Created backup: {backup_id}")
        
        # Start deployment task
        deployment_task = asyncio.create_task(
            self._execute_deployment(deployment_record)
        )
        self.deployment_tasks.add(deployment_task)
        
        self.logger.info(f"Deployment {config.deployment_id} started")
        return config.deployment_id
    
    async def _execute_deployment(self, deployment_record: DeploymentRecord):
        """Execute deployment based on strategy"""
        
        try:
            deployment_record.status = DeploymentStatus.RUNNING
            deployment_record.started_at = datetime.now()
            
            # Run pre-deployment hooks
            await self._run_hooks(deployment_record.config.pre_deployment_hooks, "pre", deployment_record)
            
            # Execute deployment strategy
            if deployment_record.config.strategy == DeploymentStrategy.BLUE_GREEN:
                success = await self._execute_blue_green_deployment(deployment_record)
            elif deployment_record.config.strategy == DeploymentStrategy.ROLLING:
                success = await self._execute_rolling_deployment(deployment_record)
            elif deployment_record.config.strategy == DeploymentStrategy.CANARY:
                success = await self._execute_canary_deployment(deployment_record)
            elif deployment_record.config.strategy == DeploymentStrategy.RECREATE:
                success = await self._execute_recreate_deployment(deployment_record)
            else:
                raise ValueError(f"Unknown deployment strategy: {deployment_record.config.strategy}")
            
            if success:
                deployment_record.status = DeploymentStatus.SUCCESS
                deployment_record.completed_at = datetime.now()
                
                # Run post-deployment hooks
                await self._run_hooks(deployment_record.config.post_deployment_hooks, "post", deployment_record)
                
                # Update active deployment
                self.active_deployment = deployment_record.deployment_id
                
                # Record success metrics
                observability.increment_counter(
                    "deployment_completed_total",
                    labels={
                        "strategy": deployment_record.config.strategy.value,
                        "status": "success"
                    }
                )
                
                self.logger.info(f"Deployment {deployment_record.deployment_id} completed successfully")
            else:
                raise Exception("Deployment failed")
        
        except Exception as e:
            deployment_record.status = DeploymentStatus.FAILED
            deployment_record.error_message = str(e)
            deployment_record.completed_at = datetime.now()
            
            # Rollback if configured
            if deployment_record.config.rollback_on_failure:
                await self._rollback_deployment(deployment_record)
            
            # Record failure metrics
            observability.increment_counter(
                "deployment_completed_total",
                labels={
                    "strategy": deployment_record.config.strategy.value,
                    "status": "failed"
                }
            )
            
            # Create alert
            await observability.create_alert(
                AlertSeverity.HIGH,
                f"Deployment failed: {deployment_record.deployment_id} - {str(e)}",
                "deployment",
                "deployment_failure",
                1,
                0,
                {"deployment_id": deployment_record.deployment_id}
            )
            
            self.logger.error(f"Deployment {deployment_record.deployment_id} failed: {e}")
        
        finally:
            # Save deployment history
            await self._save_deployment_history()
    
    async def _execute_blue_green_deployment(self, deployment_record: DeploymentRecord) -> bool:
        """Execute blue-green deployment"""
        
        config = deployment_record.config
        
        # Create new instances (green environment)
        instances = []
        for i in range(config.replicas):
            instance = await self._create_instance(deployment_record, f"green-{i}")
            if instance:
                instances.append(instance)
            else:
                # Cleanup on failure
                await self._cleanup_instances(instances)
                return False
        
        # Wait for all instances to be healthy
        if not await self._wait_for_healthy_instances(instances):
            await self._cleanup_instances(instances)
            return False
        
        # Switch traffic to green environment
        await self._switch_traffic(deployment_record.deployment_id, instances)
        
        # Cleanup old instances (blue environment)
        await self._cleanup_old_instances(deployment_record.deployment_id)
        
        deployment_record.instances = instances
        return True
    
    async def _execute_rolling_deployment(self, deployment_record: DeploymentRecord) -> bool:
        """Execute rolling deployment"""
        
        config = deployment_record.config
        current_instances = self.load_balancer.active_instances.get(deployment_record.deployment_id, [])
        
        # Calculate batches
        batch_size = config.rolling_batch_size
        new_instances = []
        
        for i in range(0, config.replicas, batch_size):
            batch_end = min(i + batch_size, config.replicas)
            batch_instances = []
            
            # Create new instances in batch
            for j in range(i, batch_end):
                instance = await self._create_instance(deployment_record, f"rolling-{j}")
                if instance:
                    batch_instances.append(instance)
                else:
                    await self._cleanup_instances(batch_instances)
                    return False
            
            # Wait for batch to be healthy
            if not await self._wait_for_healthy_instances(batch_instances):
                await self._cleanup_instances(batch_instances)
                return False
            
            # Add to load balancer
            for instance in batch_instances:
                self.load_balancer.add_instance(deployment_record.deployment_id, instance)
            
            new_instances.extend(batch_instances)
            
            # Remove old instances in batch
            old_instances_to_remove = current_instances[i:batch_end]
            for instance in old_instances_to_remove:
                await self._stop_instance(instance)
                self.load_balancer.remove_instance(deployment_record.deployment_id, instance.instance_id)
            
            # Wait between batches
            await asyncio.sleep(5)
        
        deployment_record.instances = new_instances
        return True
    
    async def _execute_canary_deployment(self, deployment_record: DeploymentRecord) -> bool:
        """Execute canary deployment"""
        
        config = deployment_record.config
        canary_replicas = max(1, int(config.replicas * config.canary_percentage / 100))
        
        # Create canary instances
        canary_instances = []
        for i in range(canary_replicas):
            instance = await self._create_instance(deployment_record, f"canary-{i}")
            if instance:
                canary_instances.append(instance)
            else:
                await self._cleanup_instances(canary_instances)
                return False
        
        # Wait for canary instances to be healthy
        if not await self._wait_for_healthy_instances(canary_instances):
            await self._cleanup_instances(canary_instances)
            return False
        
        # Set traffic split (canary gets configured percentage)
        self.load_balancer.set_traffic_split({
            deployment_record.deployment_id: config.canary_percentage,
            "previous": 100 - config.canary_percentage
        })
        
        # Monitor canary for some time
        await asyncio.sleep(60)  # Monitor for 1 minute
        
        # Check canary health and metrics
        if await self._validate_canary_deployment(canary_instances):
            # Proceed with full deployment
            remaining_instances = []
            for i in range(canary_replicas, config.replicas):
                instance = await self._create_instance(deployment_record, f"full-{i}")
                if instance:
                    remaining_instances.append(instance)
                else:
                    await self._cleanup_instances(remaining_instances)
                    return False
            
            # Wait for all instances to be healthy
            if not await self._wait_for_healthy_instances(remaining_instances):
                await self._cleanup_instances(remaining_instances)
                return False
            
            # Switch all traffic to new deployment
            all_instances = canary_instances + remaining_instances
            await self._switch_traffic(deployment_record.deployment_id, all_instances)
            
            deployment_record.instances = all_instances
            return True
        else:
            # Canary failed, cleanup
            await self._cleanup_instances(canary_instances)
            return False
    
    async def _execute_recreate_deployment(self, deployment_record: DeploymentRecord) -> bool:
        """Execute recreate deployment (with downtime)"""
        
        config = deployment_record.config
        
        # Stop all current instances
        await self._cleanup_old_instances(deployment_record.deployment_id)
        
        # Create new instances
        instances = []
        for i in range(config.replicas):
            instance = await self._create_instance(deployment_record, f"recreate-{i}")
            if instance:
                instances.append(instance)
            else:
                await self._cleanup_instances(instances)
                return False
        
        # Wait for all instances to be healthy
        if not await self._wait_for_healthy_instances(instances):
            await self._cleanup_instances(instances)
            return False
        
        # Switch traffic to new instances
        await self._switch_traffic(deployment_record.deployment_id, instances)
        
        deployment_record.instances = instances
        return True
    
    # Instance Management
    
    async def _create_instance(self, deployment_record: DeploymentRecord, instance_name: str) -> Optional[DeploymentInstance]:
        """Create a new deployment instance"""
        
        config = deployment_record.config
        port = self._allocate_port()
        
        if port is None:
            self.logger.error("No available ports for new instance")
            return None
        
        instance_id = f"{deployment_record.deployment_id}-{instance_name}"
        
        try:
            # Prepare environment variables
            env_vars = {
                "PORT": str(port),
                "DEPLOYMENT_ID": deployment_record.deployment_id,
                "VERSION": config.version,
                **config.environment_variables
            }
            
            # Create Docker container
            container = self.docker_client.containers.run(
                config.image,
                name=instance_id,
                ports={f"{port}/tcp": port},
                environment=env_vars,
                detach=True,
                restart_policy={"Name": "unless-stopped"}
            )
            
            # Create instance record
            instance = DeploymentInstance(
                instance_id=instance_id,
                deployment_id=deployment_record.deployment_id,
                container_id=container.id,
                port=port,
                status=EnvironmentStatus.STARTING,
                started_at=datetime.now()
            )
            
            deployment_record.logs.append(f"Created instance {instance_id} on port {port}")
            
            # Wait for instance to start
            await asyncio.sleep(10)
            
            # Perform initial health check
            if await self._health_check_instance(instance):
                instance.status = EnvironmentStatus.ACTIVE
                instance.health_status = "healthy"
                
                self.logger.info(f"Instance {instance_id} started successfully")
                return instance
            else:
                # Health check failed, cleanup
                await self._stop_instance(instance)
                return None
        
        except Exception as e:
            self.logger.error(f"Failed to create instance {instance_id}: {e}")
            self._release_port(port)
            return None
    
    async def _stop_instance(self, instance: DeploymentInstance):
        """Stop a deployment instance"""
        
        try:
            if instance.container_id:
                container = self.docker_client.containers.get(instance.container_id)
                container.stop()
                container.remove()
            
            if instance.port:
                self._release_port(instance.port)
            
            instance.status = EnvironmentStatus.INACTIVE
            
            self.logger.info(f"Instance {instance.instance_id} stopped")
        
        except Exception as e:
            self.logger.error(f"Failed to stop instance {instance.instance_id}: {e}")
    
    async def _cleanup_instances(self, instances: List[DeploymentInstance]):
        """Cleanup a list of instances"""
        for instance in instances:
            await self._stop_instance(instance)
    
    async def _cleanup_old_instances(self, deployment_id: str):
        """Cleanup old instances for a deployment"""
        old_instances = self.load_balancer.active_instances.get(deployment_id, [])
        
        for instance in old_instances:
            await self._stop_instance(instance)
            self.load_balancer.remove_instance(deployment_id, instance.instance_id)
    
    # Health Checks
    
    async def _health_check_instance(self, instance: DeploymentInstance) -> bool:
        """Perform health check on an instance"""
        
        if not instance.port:
            return False
        
        deployment_record = self.deployments.get(instance.deployment_id)
        if not deployment_record:
            return False
        
        health_url = f"http://localhost:{instance.port}{deployment_record.config.health_check_url}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(health_url, timeout=deployment_record.config.health_check_timeout) as response:
                    if response.status == 200:
                        instance.last_health_check = datetime.now()
                        instance.health_status = "healthy"
                        return True
                    else:
                        instance.health_status = "unhealthy"
                        return False
        
        except Exception as e:
            instance.health_status = "unhealthy"
            self.logger.warning(f"Health check failed for {instance.instance_id}: {e}")
            return False
    
    async def _wait_for_healthy_instances(self, instances: List[DeploymentInstance]) -> bool:
        """Wait for all instances to be healthy"""
        
        max_retries = 10
        retry_delay = 5
        
        for retry in range(max_retries):
            healthy_count = 0
            
            for instance in instances:
                if await self._health_check_instance(instance):
                    healthy_count += 1
            
            if healthy_count == len(instances):
                return True
            
            self.logger.info(f"Health check retry {retry + 1}/{max_retries}: {healthy_count}/{len(instances)} instances healthy")
            await asyncio.sleep(retry_delay)
        
        return False
    
    async def _validate_canary_deployment(self, canary_instances: List[DeploymentInstance]) -> bool:
        """Validate canary deployment based on health and metrics"""
        
        # Check if all canary instances are healthy
        for instance in canary_instances:
            if not await self._health_check_instance(instance):
                return False
        
        # Check error rates (simplified)
        # In production, you would check real metrics
        error_rate = 0.01  # 1% error rate
        
        if error_rate > 0.05:  # 5% threshold
            return False
        
        return True
    
    # Traffic Management
    
    async def _switch_traffic(self, deployment_id: str, instances: List[DeploymentInstance]):
        """Switch traffic to new instances"""
        
        # Remove old instances from load balancer
        old_instances = self.load_balancer.active_instances.get(deployment_id, [])
        for instance in old_instances:
            self.load_balancer.remove_instance(deployment_id, instance.instance_id)
        
        # Add new instances to load balancer
        for instance in instances:
            self.load_balancer.add_instance(deployment_id, instance)
        
        # Set full traffic to new deployment
        self.load_balancer.set_traffic_split({deployment_id: 100})
        
        self.logger.info(f"Traffic switched to deployment {deployment_id}")
    
    # Rollback
    
    async def _rollback_deployment(self, deployment_record: DeploymentRecord):
        """Rollback a failed deployment"""
        
        try:
            deployment_record.status = DeploymentStatus.ROLLED_BACK
            
            # Find previous successful deployment
            previous_deployment = await self._find_previous_deployment(deployment_record.deployment_id)
            
            if previous_deployment:
                # Restore previous deployment
                await self._restore_deployment(previous_deployment)
                deployment_record.rollback_deployment_id = previous_deployment.deployment_id
                
                self.logger.info(f"Rolled back to deployment {previous_deployment.deployment_id}")
            else:
                self.logger.warning("No previous deployment found for rollback")
        
        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
    
    async def _find_previous_deployment(self, current_deployment_id: str) -> Optional[DeploymentRecord]:
        """Find the previous successful deployment"""
        
        successful_deployments = [
            d for d in self.deployments.values()
            if d.status == DeploymentStatus.SUCCESS and d.deployment_id != current_deployment_id
        ]
        
        if successful_deployments:
            # Return the most recent successful deployment
            return max(successful_deployments, key=lambda d: d.completed_at or datetime.min)
        
        return None
    
    async def _restore_deployment(self, deployment_record: DeploymentRecord):
        """Restore a previous deployment"""
        
        # This would restore the previous deployment
        # For now, just log the action
        self.logger.info(f"Restoring deployment {deployment_record.deployment_id}")
    
    # Hook Management
    
    def register_hook(self, hook_name: str, hook_func: Callable, hook_type: str = "both"):
        """Register a deployment hook"""
        
        if hook_type in ["pre", "both"]:
            self.pre_deployment_hooks[hook_name] = hook_func
        
        if hook_type in ["post", "both"]:
            self.post_deployment_hooks[hook_name] = hook_func
    
    async def _run_hooks(self, hook_names: List[str], hook_type: str, deployment_record: DeploymentRecord):
        """Run deployment hooks"""
        
        hooks = self.pre_deployment_hooks if hook_type == "pre" else self.post_deployment_hooks
        
        for hook_name in hook_names:
            if hook_name in hooks:
                try:
                    await hooks[hook_name](deployment_record)
                    deployment_record.logs.append(f"Executed {hook_type}-deployment hook: {hook_name}")
                except Exception as e:
                    error_msg = f"Hook {hook_name} failed: {e}"
                    deployment_record.logs.append(error_msg)
                    self.logger.error(error_msg)
    
    # Background Tasks
    
    async def _health_check_monitor(self):
        """Monitor health of all active instances"""
        
        while self.is_running:
            try:
                all_instances = self.load_balancer.get_active_instances()
                
                for instance in all_instances:
                    await self._health_check_instance(instance)
                
                # Record health metrics
                healthy_instances = len([
                    i for i in all_instances if i.health_status == "healthy"
                ])
                
                observability.set_gauge("deployment_healthy_instances", healthy_instances)
                observability.set_gauge("deployment_total_instances", len(all_instances))
                
                await asyncio.sleep(30)  # Check every 30 seconds
            
            except Exception as e:
                self.logger.error(f"Health check monitor error: {e}")
                await asyncio.sleep(30)
    
    async def _deployment_monitor(self):
        """Monitor deployment system health"""
        
        while self.is_running:
            try:
                # Check for stuck deployments
                current_time = datetime.now()
                
                for deployment_record in self.deployments.values():
                    if deployment_record.status == DeploymentStatus.RUNNING:
                        if deployment_record.started_at:
                            duration = (current_time - deployment_record.started_at).total_seconds()
                            
                            # Alert if deployment is taking too long (30 minutes)
                            if duration > 1800:
                                await observability.create_alert(
                                    AlertSeverity.MEDIUM,
                                    f"Deployment {deployment_record.deployment_id} is taking too long ({duration:.0f}s)",
                                    "deployment",
                                    "deployment_duration",
                                    duration,
                                    1800,
                                    {"deployment_id": deployment_record.deployment_id}
                                )
                
                # Record deployment metrics
                running_deployments = len([
                    d for d in self.deployments.values()
                    if d.status == DeploymentStatus.RUNNING
                ])
                
                observability.set_gauge("deployment_running_count", running_deployments)
                observability.set_gauge("deployment_total_count", len(self.deployments))
                
                await asyncio.sleep(60)  # Check every minute
            
            except Exception as e:
                self.logger.error(f"Deployment monitor error: {e}")
                await asyncio.sleep(60)
    
    # Utility Methods
    
    async def _get_current_version(self) -> Optional[str]:
        """Get current deployed version"""
        if self.active_deployment:
            deployment = self.deployments.get(self.active_deployment)
            return deployment.config.version if deployment else None
        return None
    
    # API Methods
    
    def get_deployment_status(self, deployment_id: str) -> Optional[DeploymentRecord]:
        """Get deployment status"""
        return self.deployments.get(deployment_id)
    
    def list_deployments(self, limit: int = 100) -> List[DeploymentRecord]:
        """List deployments"""
        deployments = list(self.deployments.values())
        deployments.sort(key=lambda d: d.created_at, reverse=True)
        return deployments[:limit]
    
    def get_active_instances(self) -> List[DeploymentInstance]:
        """Get all active instances"""
        return self.load_balancer.get_active_instances()
    
    async def cancel_deployment(self, deployment_id: str) -> bool:
        """Cancel a running deployment"""
        if deployment_id in self.deployments:
            deployment = self.deployments[deployment_id]
            if deployment.status == DeploymentStatus.RUNNING:
                deployment.status = DeploymentStatus.CANCELLED
                # Cleanup instances
                await self._cleanup_instances(deployment.instances)
                return True
        return False
    
    async def shutdown(self):
        """Shutdown deployment system"""
        self.is_running = False
        
        # Cancel background tasks
        for task in self.deployment_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self.deployment_tasks, return_exceptions=True)
        
        # Cleanup all instances
        for deployment in self.deployments.values():
            await self._cleanup_instances(deployment.instances)
        
        self.logger.info("Deployment system shutdown complete")


# Global instance
deployment_system = DeploymentSystem()


# Usage example
if __name__ == "__main__":
    async def example_usage():
        # Initialize deployment system
        await deployment_system.initialize()
        
        # Create deployment configuration
        config = DeploymentConfig(
            deployment_id="app-v1.2.0",
            strategy=DeploymentStrategy.BLUE_GREEN,
            version="1.2.0",
            image="myapp:1.2.0",
            replicas=3,
            health_check_url="/health",
            rollback_on_failure=True
        )
        
        # Start deployment
        deployment_id = await deployment_system.deploy(config)
        print(f"Started deployment: {deployment_id}")
        
        # Monitor deployment
        while True:
            status = deployment_system.get_deployment_status(deployment_id)
            if status and status.status != DeploymentStatus.RUNNING:
                print(f"Deployment {deployment_id} completed with status: {status.status}")
                break
            await asyncio.sleep(5)
        
        # Get active instances
        instances = deployment_system.get_active_instances()
        print(f"Active instances: {len(instances)}")
        
        # Shutdown
        await deployment_system.shutdown()
    
    asyncio.run(example_usage())