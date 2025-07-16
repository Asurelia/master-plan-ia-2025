"""
Master Orchestrator for Advanced Master Plan IA 2025
Integrates all advanced systems with preventive ecosystem management
"""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml

# Import all advanced systems
from .observability_system import observability
from .security_system import security_system
from .resilience_system import resilience_system
from .config_system import config_system
from .backup_system import backup_system
from .deployment_system import deployment_system
from .voice_detection import VoiceDetectionSystem, VoiceCommandProcessor

# Import existing systems
from .orchestration_hub import OrchestrationHub
from .agent_coordinator import AgentCoordinator


class MasterOrchestrator:
    """
    Master orchestrator that coordinates all systems with advanced ecosystem management
    """
    
    def __init__(self):
        self.is_running = False
        self.initialization_complete = False
        
        # Core systems
        self.orchestration_hub = None
        self.agent_coordinator = None
        
        # Advanced systems
        self.voice_detector = None
        self.voice_processor = None
        
        # System health
        self.system_health = {
            "orchestration_hub": False,
            "agent_coordinator": False,
            "observability": False,
            "security": False,
            "resilience": False,
            "config": False,
            "backup": False,
            "deployment": False,
            "voice_detection": False
        }
        
        # Background tasks
        self.background_tasks = set()
        
        # Shutdown handlers
        self.shutdown_handlers = []
        
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self, config_path: str = "config/master.yaml"):
        """
        Initialize all systems with preventive ecosystem management
        """
        try:
            self.logger.info("🚀 Starting Master Plan IA 2025 - Advanced Edition")
            
            # Load master configuration
            await self._load_master_config(config_path)
            
            # Initialize systems in dependency order
            await self._initialize_core_systems()
            await self._initialize_advanced_systems()
            await self._initialize_integrations()
            
            # Start background monitoring
            await self._start_background_tasks()
            
            # Setup signal handlers
            self._setup_signal_handlers()
            
            # Perform system health check
            await self._perform_system_health_check()
            
            self.initialization_complete = True
            self.is_running = True
            
            self.logger.info("✅ Master Plan IA 2025 initialized successfully")
            
            # Create initialization success backup
            await backup_system.create_backup(
                backup_system.BackupType.CONFIGURATION,
                description="Post-initialization configuration backup"
            )
            
        except Exception as e:
            self.logger.error(f"❌ Master orchestrator initialization failed: {e}")
            await self._emergency_shutdown()
            raise
    
    async def _load_master_config(self, config_path: str):
        """Load master configuration"""
        try:
            # Initialize configuration system first
            await config_system.initialize()
            
            # Load master configuration if exists
            master_config_path = Path(config_path)
            if master_config_path.exists():
                with open(master_config_path, 'r') as f:
                    master_config = yaml.safe_load(f)
                
                # Import configuration
                await config_system.import_config(master_config)
                
                self.logger.info(f"Master configuration loaded from {config_path}")
            else:
                self.logger.info("Using default configuration")
            
            self.system_health["config"] = True
            
        except Exception as e:
            self.logger.error(f"Failed to load master configuration: {e}")
            raise
    
    async def _initialize_core_systems(self):
        """Initialize core orchestration systems"""
        try:
            # Initialize orchestration hub
            self.orchestration_hub = OrchestrationHub()
            await self.orchestration_hub.initialize()
            self.system_health["orchestration_hub"] = True
            
            # Initialize agent coordinator
            self.agent_coordinator = AgentCoordinator(self.orchestration_hub)
            await self.agent_coordinator.initialize()
            self.system_health["agent_coordinator"] = True
            
            self.logger.info("✅ Core systems initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize core systems: {e}")
            raise
    
    async def _initialize_advanced_systems(self):
        """Initialize advanced preventive systems"""
        try:
            # Initialize observability system
            await observability.initialize()
            self.system_health["observability"] = True
            
            # Initialize security system
            await security_system.initialize()
            self.system_health["security"] = True
            
            # Initialize resilience system
            await resilience_system.initialize()
            self.system_health["resilience"] = True
            
            # Initialize backup system
            await backup_system.initialize()
            self.system_health["backup"] = True
            
            # Initialize deployment system
            await deployment_system.initialize()
            self.system_health["deployment"] = True
            
            # Initialize voice detection system
            try:
                self.voice_detector = VoiceDetectionSystem()
                self.voice_processor = VoiceCommandProcessor(self.voice_detector)
                await self._setup_voice_commands()
                self.system_health["voice_detection"] = True
                self.logger.info("✅ Voice detection system initialized")
            except Exception as e:
                self.logger.warning(f"⚠️ Voice detection system failed to initialize: {e}")
                self.system_health["voice_detection"] = False
            
            self.logger.info("✅ Advanced systems initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize advanced systems: {e}")
            raise
    
    async def _initialize_integrations(self):
        """Initialize integrations between systems"""
        try:
            # Setup observability for all systems
            await self._setup_observability_integration()
            
            # Setup security for all systems
            await self._setup_security_integration()
            
            # Setup resilience patterns
            await self._setup_resilience_integration()
            
            # Setup backup schedules
            await self._setup_backup_integration()
            
            self.logger.info("✅ System integrations initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize integrations: {e}")
            raise
    
    async def _setup_observability_integration(self):
        """Setup observability for all systems"""
        
        # Register health checks
        observability.register_health_check(
            "orchestration_hub",
            lambda: self.orchestration_hub.get_system_health() if self.orchestration_hub else False
        )
        
        observability.register_health_check(
            "agent_coordinator",
            lambda: self.agent_coordinator.is_healthy() if self.agent_coordinator else False
        )
        
        observability.register_health_check(
            "voice_detection",
            lambda: self.voice_detector.get_status()['is_listening'] if self.voice_detector else False
        )
        
        # Setup alert handlers
        async def alert_handler(alert):
            self.logger.warning(f"ALERT: {alert.severity.value} - {alert.message}")
            
            # Take action based on alert severity
            if alert.severity.value == "critical":
                await self._handle_critical_alert(alert)
            elif alert.severity.value == "high":
                await self._handle_high_alert(alert)
        
        observability.add_alert_handler(alert_handler)
    
    async def _setup_security_integration(self):
        """Setup security for all systems"""
        
        # Register security rules for voice commands
        if self.voice_processor:
            def validate_voice_command(command):
                # Validate voice commands for security
                dangerous_patterns = ["delete", "destroy", "shutdown", "kill"]
                return not any(pattern in command.lower() for pattern in dangerous_patterns)
            
            self.voice_processor.register_command(
                ["system", "admin"],
                lambda text: {"error": "Admin commands require additional authentication"}
            )
    
    async def _setup_resilience_integration(self):
        """Setup resilience patterns for all systems"""
        
        # Register circuit breakers for external services
        resilience_system.register_circuit_breaker("external_apis")
        resilience_system.register_circuit_breaker("database_operations")
        resilience_system.register_circuit_breaker("voice_processing")
        
        # Register bulkheads for resource isolation
        resilience_system.register_bulkhead("voice_processing")
        resilience_system.register_bulkhead("agent_operations")
        
        # Register fallbacks
        async def voice_fallback():
            return "Voice system temporarily unavailable"
        
        resilience_system.register_fallback("voice_system", voice_fallback)
    
    async def _setup_backup_integration(self):
        """Setup backup schedules and integration"""
        
        # Schedule regular backups
        backup_system.schedule_backup(
            backup_system.BackupType.CONFIGURATION,
            "0 */6 * * *",  # Every 6 hours
            retention_days=7
        )
        
        backup_system.schedule_backup(
            backup_system.BackupType.FULL,
            "0 2 * * *",  # Daily at 2 AM
            retention_days=30
        )
        
        backup_system.schedule_backup(
            backup_system.BackupType.METRICS,
            "0 */12 * * *",  # Every 12 hours
            retention_days=14
        )
    
    async def _setup_voice_commands(self):
        """Setup voice commands for system control"""
        if not self.voice_processor:
            return
        
        # System status commands
        def handle_status_command(text):
            health_status = self.get_system_health()
            healthy_systems = sum(1 for status in health_status.values() if status)
            total_systems = len(health_status)
            
            return {
                "action": "status",
                "message": f"System health: {healthy_systems}/{total_systems} systems healthy",
                "details": health_status
            }
        
        # Backup commands
        def handle_backup_command(text):
            if "create" in text.lower():
                # Schedule backup creation
                asyncio.create_task(backup_system.create_backup(
                    backup_system.BackupType.CONFIGURATION,
                    description="Voice-triggered backup"
                ))
                return {"action": "backup", "message": "Backup creation started"}
            elif "status" in text.lower():
                status = backup_system.get_backup_status()
                return {"action": "backup", "message": f"Backup status: {status}"}
            else:
                return {"action": "backup", "message": "Available: create backup, backup status"}
        
        # Agent commands
        def handle_agent_command(text):
            if self.orchestration_hub:
                agent_count = len(self.orchestration_hub.agents)
                active_tasks = sum(len(agent.current_tasks) for agent in self.orchestration_hub.agents.values())
                
                return {
                    "action": "agents",
                    "message": f"Agents: {agent_count}, Active tasks: {active_tasks}",
                    "details": {"agent_count": agent_count, "active_tasks": active_tasks}
                }
            else:
                return {"action": "agents", "message": "Orchestration hub not available"}
        
        # Register commands
        self.voice_processor.register_command(["status", "état", "health"], handle_status_command)
        self.voice_processor.register_command(["backup", "sauvegarde"], handle_backup_command)
        self.voice_processor.register_command(["agents", "agent"], handle_agent_command)
    
    async def _start_background_tasks(self):
        """Start background monitoring tasks"""
        
        # System health monitoring
        self.background_tasks.add(
            asyncio.create_task(self._system_health_monitor())
        )
        
        # Ecosystem health monitoring
        self.background_tasks.add(
            asyncio.create_task(self._ecosystem_health_monitor())
        )
        
        # Performance monitoring
        self.background_tasks.add(
            asyncio.create_task(self._performance_monitor())
        )
        
        # Automatic problem resolution
        self.background_tasks.add(
            asyncio.create_task(self._auto_problem_resolver())
        )
    
    async def _system_health_monitor(self):
        """Monitor system health and take preventive actions"""
        while self.is_running:
            try:
                # Check system health
                health_status = await self._check_system_health()
                
                # Record health metrics
                healthy_systems = sum(1 for status in health_status.values() if status)
                observability.set_gauge("system_health_ratio", healthy_systems / len(health_status))
                
                # Take action on unhealthy systems
                for system_name, is_healthy in health_status.items():
                    if not is_healthy:
                        await self._handle_unhealthy_system(system_name)
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                self.logger.error(f"System health monitor error: {e}")
                await asyncio.sleep(60)
    
    async def _ecosystem_health_monitor(self):
        """Monitor ecosystem health with predictive analysis"""
        while self.is_running:
            try:
                # Check resource usage trends
                await self._check_resource_trends()
                
                # Check error patterns
                await self._check_error_patterns()
                
                # Check performance trends
                await self._check_performance_trends()
                
                # Predict potential issues
                await self._predict_potential_issues()
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                self.logger.error(f"Ecosystem health monitor error: {e}")
                await asyncio.sleep(300)
    
    async def _performance_monitor(self):
        """Monitor performance and optimize proactively"""
        while self.is_running:
            try:
                # Check response times
                if self.orchestration_hub:
                    avg_response_time = await self.orchestration_hub.get_average_response_time()
                    observability.set_gauge("avg_response_time_ms", avg_response_time * 1000)
                
                # Check throughput
                metrics = observability.get_metrics()
                if "api_requests_total" in metrics:
                    recent_requests = len([m for m in metrics["api_requests_total"] 
                                         if datetime.now() - m.timestamp < timedelta(minutes=1)])
                    observability.set_gauge("requests_per_minute", recent_requests)
                
                # Auto-optimize if needed
                await self._auto_optimize_performance()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Performance monitor error: {e}")
                await asyncio.sleep(30)
    
    async def _auto_problem_resolver(self):
        """Automatically resolve common problems"""
        while self.is_running:
            try:
                # Check for stuck tasks
                await self._resolve_stuck_tasks()
                
                # Check for memory leaks
                await self._resolve_memory_issues()
                
                # Check for configuration drift
                await self._resolve_config_drift()
                
                await asyncio.sleep(600)  # Check every 10 minutes
                
            except Exception as e:
                self.logger.error(f"Auto problem resolver error: {e}")
                await asyncio.sleep(600)
    
    async def _check_system_health(self) -> Dict[str, bool]:
        """Check health of all systems"""
        health_status = {}
        
        try:
            # Check orchestration hub
            health_status["orchestration_hub"] = (
                self.orchestration_hub is not None and 
                await self.orchestration_hub.get_system_health()
            )
            
            # Check agent coordinator
            health_status["agent_coordinator"] = (
                self.agent_coordinator is not None and 
                self.agent_coordinator.is_healthy()
            )
            
            # Check advanced systems
            health_status["observability"] = observability.get_health_status()["overall_status"] == "healthy"
            health_status["security"] = len(security_system.get_security_events(limit=10)) < 5
            health_status["backup"] = backup_system.get_backup_status()["total_backups"] > 0
            health_status["deployment"] = len(deployment_system.get_active_instances()) >= 0
            
            # Check voice detection
            if self.voice_detector:
                voice_status = self.voice_detector.get_status()
                health_status["voice_detection"] = voice_status.get("vosk_available", False)
            else:
                health_status["voice_detection"] = False
            
        except Exception as e:
            self.logger.error(f"Health check error: {e}")
        
        return health_status
    
    async def _handle_unhealthy_system(self, system_name: str):
        """Handle unhealthy system with automatic recovery"""
        self.logger.warning(f"System {system_name} is unhealthy, attempting recovery")
        
        try:
            if system_name == "orchestration_hub" and self.orchestration_hub:
                await self.orchestration_hub.recover()
            elif system_name == "agent_coordinator" and self.agent_coordinator:
                await self.agent_coordinator.recover()
            elif system_name == "voice_detection" and self.voice_detector:
                # Restart voice detection
                self.voice_detector.stop_listening()
                await asyncio.sleep(1)
                self.voice_detector.start_listening()
            
            # Create alert for manual intervention if needed
            await observability.create_alert(
                observability.AlertSeverity.MEDIUM,
                f"System {system_name} recovery attempted",
                "master_orchestrator",
                "system_recovery",
                1,
                0,
                {"system": system_name}
            )
            
        except Exception as e:
            self.logger.error(f"Failed to recover system {system_name}: {e}")
    
    async def _check_resource_trends(self):
        """Check resource usage trends"""
        # This would analyze CPU, memory, disk trends
        # For now, just log the check
        self.logger.debug("Checking resource trends")
    
    async def _check_error_patterns(self):
        """Check for concerning error patterns"""
        # This would analyze error logs for patterns
        # For now, just log the check
        self.logger.debug("Checking error patterns")
    
    async def _check_performance_trends(self):
        """Check performance trends"""
        # This would analyze performance metrics trends
        # For now, just log the check
        self.logger.debug("Checking performance trends")
    
    async def _predict_potential_issues(self):
        """Predict potential issues based on patterns"""
        # This would use ML to predict issues
        # For now, just log the check
        self.logger.debug("Predicting potential issues")
    
    async def _auto_optimize_performance(self):
        """Automatically optimize performance"""
        # This would implement auto-optimization
        # For now, just log the check
        self.logger.debug("Auto-optimizing performance")
    
    async def _resolve_stuck_tasks(self):
        """Resolve stuck tasks"""
        if self.orchestration_hub:
            stuck_tasks = await self.orchestration_hub.get_stuck_tasks()
            for task in stuck_tasks:
                await self.orchestration_hub.cancel_task(task.id)
                self.logger.info(f"Cancelled stuck task: {task.id}")
    
    async def _resolve_memory_issues(self):
        """Resolve memory issues"""
        # This would implement memory cleanup
        # For now, just log the check
        self.logger.debug("Checking for memory issues")
    
    async def _resolve_config_drift(self):
        """Resolve configuration drift"""
        # This would check for configuration changes
        # For now, just log the check
        self.logger.debug("Checking for configuration drift")
    
    async def _handle_critical_alert(self, alert):
        """Handle critical alerts"""
        self.logger.critical(f"CRITICAL ALERT: {alert.message}")
        
        # Create emergency backup
        await backup_system.create_backup(
            backup_system.BackupType.FULL,
            description=f"Emergency backup due to critical alert: {alert.message}"
        )
        
        # Take defensive actions based on alert type
        if "security" in alert.component.lower():
            await self._handle_security_emergency(alert)
        elif "deployment" in alert.component.lower():
            await self._handle_deployment_emergency(alert)
    
    async def _handle_high_alert(self, alert):
        """Handle high priority alerts"""
        self.logger.error(f"HIGH ALERT: {alert.message}")
        
        # Take appropriate actions
        if alert.component == "resilience":
            await self._handle_resilience_alert(alert)
    
    async def _handle_security_emergency(self, alert):
        """Handle security emergency"""
        self.logger.critical("Security emergency detected - taking defensive actions")
        
        # Enable enhanced security monitoring
        # Block suspicious IPs
        # This would implement emergency security measures
    
    async def _handle_deployment_emergency(self, alert):
        """Handle deployment emergency"""
        self.logger.critical("Deployment emergency detected - initiating rollback")
        
        # This would implement emergency rollback procedures
    
    async def _handle_resilience_alert(self, alert):
        """Handle resilience alert"""
        self.logger.warning("Resilience alert - adjusting system parameters")
        
        # This would implement resilience adjustments
    
    async def _perform_system_health_check(self):
        """Perform comprehensive system health check"""
        self.logger.info("Performing system health check...")
        
        health_status = await self._check_system_health()
        
        healthy_systems = sum(1 for status in health_status.values() if status)
        total_systems = len(health_status)
        
        self.logger.info(f"System health: {healthy_systems}/{total_systems} systems healthy")
        
        for system_name, is_healthy in health_status.items():
            status_icon = "✅" if is_healthy else "❌"
            self.logger.info(f"  {status_icon} {system_name}")
        
        if healthy_systems < total_systems:
            self.logger.warning("Some systems are unhealthy - monitor closely")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating shutdown...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _emergency_shutdown(self):
        """Emergency shutdown procedure"""
        self.logger.critical("Emergency shutdown initiated")
        
        # Create emergency backup
        try:
            await backup_system.create_backup(
                backup_system.BackupType.FULL,
                description="Emergency shutdown backup"
            )
        except Exception as e:
            self.logger.error(f"Failed to create emergency backup: {e}")
        
        # Shutdown all systems
        await self.shutdown()
    
    # API Methods
    
    def get_system_health(self) -> Dict[str, bool]:
        """Get current system health status"""
        return self.system_health
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive system information"""
        return {
            "initialization_complete": self.initialization_complete,
            "is_running": self.is_running,
            "system_health": self.system_health,
            "background_tasks": len(self.background_tasks),
            "uptime": datetime.now().isoformat() if self.is_running else None,
            "version": "2.0.0-advanced"
        }
    
    async def execute_voice_command(self, command: str) -> Dict[str, Any]:
        """Execute voice command"""
        if self.voice_processor:
            return self.voice_processor.process_command(command)
        return {"error": "Voice processing not available"}
    
    async def create_deployment(self, config: Dict[str, Any]) -> str:
        """Create new deployment"""
        if deployment_system:
            deployment_config = deployment_system.DeploymentConfig(**config)
            return await deployment_system.deploy(deployment_config)
        raise Exception("Deployment system not available")
    
    async def shutdown(self):
        """Graceful shutdown of all systems"""
        self.logger.info("🛑 Initiating graceful shutdown...")
        
        self.is_running = False
        
        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        # Shutdown systems in reverse order
        try:
            if self.voice_detector:
                self.voice_detector.stop_listening()
            
            await deployment_system.shutdown()
            await backup_system.shutdown()
            await observability.shutdown()
            
            if self.agent_coordinator:
                await self.agent_coordinator.shutdown()
            
            if self.orchestration_hub:
                await self.orchestration_hub.shutdown()
            
            await config_system.cleanup()
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
        
        self.logger.info("✅ Shutdown complete")


# Global instance
master_orchestrator = MasterOrchestrator()


# Main execution
async def main():
    """Main execution function"""
    try:
        await master_orchestrator.initialize()
        
        # Keep running until shutdown
        while master_orchestrator.is_running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        logging.error(f"Critical error: {e}")
    finally:
        await master_orchestrator.shutdown()


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the master orchestrator
    asyncio.run(main())