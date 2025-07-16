"""
Advanced Backup and Disaster Recovery System
Prevents data loss and enables quick recovery from failures
"""

import asyncio
import gzip
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Callable, Set, Tuple
import aiofiles
import aiohttp
import boto3
from botocore.exceptions import ClientError
import redis.asyncio as redis
from dataclasses import asdict

from .observability_system import observability, MetricType, AlertSeverity
from .config_system import config_system


class BackupType(Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    DIFFERENTIAL = "differential"
    CONFIGURATION = "configuration"
    METRICS = "metrics"
    LOGS = "logs"
    SECRETS = "secrets"
    STATE = "state"


class BackupStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StorageType(Enum):
    LOCAL = "local"
    S3 = "s3"
    REDIS = "redis"
    NETWORK = "network"


class CompressionType(Enum):
    NONE = "none"
    GZIP = "gzip"
    BZIP2 = "bzip2"
    LZ4 = "lz4"


@dataclass
class BackupMetadata:
    backup_id: str
    backup_type: BackupType
    status: BackupStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    size_bytes: int = 0
    file_path: Optional[str] = None
    checksum: Optional[str] = None
    compression: CompressionType = CompressionType.GZIP
    storage_type: StorageType = StorageType.LOCAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_backup_id: Optional[str] = None  # For incremental backups
    retention_days: int = 30
    encrypted: bool = False


@dataclass
class RestorePoint:
    point_id: str
    timestamp: datetime
    backups: List[str]  # List of backup IDs needed for restore
    description: str
    system_state: Dict[str, Any] = field(default_factory=dict)
    verified: bool = False


@dataclass
class BackupSchedule:
    schedule_id: str
    backup_type: BackupType
    cron_expression: str
    enabled: bool = True
    retention_days: int = 30
    storage_type: StorageType = StorageType.LOCAL
    compression: CompressionType = CompressionType.GZIP
    metadata: Dict[str, Any] = field(default_factory=dict)


class BackupStorage:
    """Abstract base class for backup storage"""
    
    async def store(self, backup_id: str, data: bytes, metadata: BackupMetadata) -> bool:
        raise NotImplementedError
    
    async def retrieve(self, backup_id: str) -> Optional[bytes]:
        raise NotImplementedError
    
    async def delete(self, backup_id: str) -> bool:
        raise NotImplementedError
    
    async def list_backups(self) -> List[str]:
        raise NotImplementedError


class LocalStorage(BackupStorage):
    """Local filesystem storage"""
    
    def __init__(self, backup_dir: str = "backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
    
    async def store(self, backup_id: str, data: bytes, metadata: BackupMetadata) -> bool:
        try:
            file_path = self.backup_dir / f"{backup_id}.backup"
            
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(data)
            
            # Store metadata
            metadata_path = self.backup_dir / f"{backup_id}.metadata"
            async with aiofiles.open(metadata_path, 'w') as f:
                await f.write(json.dumps(asdict(metadata), default=str))
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to store backup {backup_id}: {e}")
            return False
    
    async def retrieve(self, backup_id: str) -> Optional[bytes]:
        try:
            file_path = self.backup_dir / f"{backup_id}.backup"
            
            if not file_path.exists():
                return None
            
            async with aiofiles.open(file_path, 'rb') as f:
                return await f.read()
        except Exception as e:
            self.logger.error(f"Failed to retrieve backup {backup_id}: {e}")
            return None
    
    async def delete(self, backup_id: str) -> bool:
        try:
            file_path = self.backup_dir / f"{backup_id}.backup"
            metadata_path = self.backup_dir / f"{backup_id}.metadata"
            
            if file_path.exists():
                file_path.unlink()
            if metadata_path.exists():
                metadata_path.unlink()
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete backup {backup_id}: {e}")
            return False
    
    async def list_backups(self) -> List[str]:
        try:
            return [f.stem for f in self.backup_dir.glob("*.backup")]
        except Exception as e:
            self.logger.error(f"Failed to list backups: {e}")
            return []


class S3Storage(BackupStorage):
    """Amazon S3 storage"""
    
    def __init__(self, bucket_name: str, aws_access_key: str = None, 
                 aws_secret_key: str = None, region: str = "us-east-1"):
        self.bucket_name = bucket_name
        self.region = region
        
        # Initialize S3 client
        session = boto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region
        )
        self.s3_client = session.client('s3')
        
        self.logger = logging.getLogger(__name__)
    
    async def store(self, backup_id: str, data: bytes, metadata: BackupMetadata) -> bool:
        try:
            # Upload backup data
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"backups/{backup_id}.backup",
                Body=data,
                Metadata={
                    'backup-type': metadata.backup_type.value,
                    'created-at': metadata.created_at.isoformat(),
                    'checksum': metadata.checksum or ''
                }
            )
            
            # Upload metadata
            metadata_json = json.dumps(asdict(metadata), default=str)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"metadata/{backup_id}.metadata",
                Body=metadata_json.encode(),
                ContentType='application/json'
            )
            
            return True
        except ClientError as e:
            self.logger.error(f"Failed to store backup {backup_id} to S3: {e}")
            return False
    
    async def retrieve(self, backup_id: str) -> Optional[bytes]:
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=f"backups/{backup_id}.backup"
            )
            return response['Body'].read()
        except ClientError as e:
            self.logger.error(f"Failed to retrieve backup {backup_id} from S3: {e}")
            return None
    
    async def delete(self, backup_id: str) -> bool:
        try:
            # Delete backup data
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=f"backups/{backup_id}.backup"
            )
            
            # Delete metadata
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=f"metadata/{backup_id}.metadata"
            )
            
            return True
        except ClientError as e:
            self.logger.error(f"Failed to delete backup {backup_id} from S3: {e}")
            return False
    
    async def list_backups(self) -> List[str]:
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix="backups/"
            )
            
            backups = []
            for obj in response.get('Contents', []):
                key = obj['Key']
                if key.endswith('.backup'):
                    backup_id = Path(key).stem
                    backups.append(backup_id)
            
            return backups
        except ClientError as e:
            self.logger.error(f"Failed to list backups from S3: {e}")
            return []


class BackupSystem:
    """
    Advanced backup and disaster recovery system
    """
    
    def __init__(self, storage_configs: Dict[StorageType, Dict[str, Any]] = None):
        self.storage_configs = storage_configs or {}
        self.storages: Dict[StorageType, BackupStorage] = {}
        
        # Backup tracking
        self.backup_metadata: Dict[str, BackupMetadata] = {}
        self.restore_points: Dict[str, RestorePoint] = {}
        self.backup_schedules: Dict[str, BackupSchedule] = {}
        
        # State tracking
        self.running_backups: Set[str] = set()
        self.last_backup_times: Dict[BackupType, datetime] = {}
        
        # Background tasks
        self.backup_tasks: Set[asyncio.Task] = set()
        self.is_running = False
        
        # Compression handlers
        self.compression_handlers = {
            CompressionType.GZIP: self._compress_gzip,
            CompressionType.NONE: self._compress_none
        }
        
        self.decompression_handlers = {
            CompressionType.GZIP: self._decompress_gzip,
            CompressionType.NONE: self._decompress_none
        }
        
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize the backup system"""
        
        # Initialize storage backends
        await self._initialize_storages()
        
        # Load existing backup metadata
        await self._load_backup_metadata()
        
        # Start background tasks
        self.is_running = True
        self.backup_tasks.add(asyncio.create_task(self._backup_scheduler()))
        self.backup_tasks.add(asyncio.create_task(self._backup_monitor()))
        self.backup_tasks.add(asyncio.create_task(self._cleanup_old_backups()))
        
        self.logger.info("✅ Backup system initialized")
    
    async def _initialize_storages(self):
        """Initialize storage backends"""
        
        # Always initialize local storage
        self.storages[StorageType.LOCAL] = LocalStorage()
        
        # Initialize S3 storage if configured
        if StorageType.S3 in self.storage_configs:
            s3_config = self.storage_configs[StorageType.S3]
            self.storages[StorageType.S3] = S3Storage(**s3_config)
        
        # Initialize Redis storage if configured
        if StorageType.REDIS in self.storage_configs:
            redis_config = self.storage_configs[StorageType.REDIS]
            # Redis storage implementation would go here
            pass
    
    async def _load_backup_metadata(self):
        """Load existing backup metadata"""
        try:
            # Try to load from local storage first
            local_storage = self.storages[StorageType.LOCAL]
            backup_ids = await local_storage.list_backups()
            
            for backup_id in backup_ids:
                metadata_path = Path("backups") / f"{backup_id}.metadata"
                if metadata_path.exists():
                    async with aiofiles.open(metadata_path, 'r') as f:
                        metadata_json = await f.read()
                        metadata_dict = json.loads(metadata_json)
                        
                        # Convert back to BackupMetadata
                        metadata = BackupMetadata(**metadata_dict)
                        self.backup_metadata[backup_id] = metadata
            
            self.logger.info(f"Loaded {len(self.backup_metadata)} backup metadata entries")
        
        except Exception as e:
            self.logger.error(f"Failed to load backup metadata: {e}")
    
    # Core Backup Operations
    
    async def create_backup(self, backup_type: BackupType, 
                          storage_type: StorageType = StorageType.LOCAL,
                          compression: CompressionType = CompressionType.GZIP,
                          description: str = None) -> Optional[str]:
        """Create a new backup"""
        
        backup_id = f"{backup_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create backup metadata
        metadata = BackupMetadata(
            backup_id=backup_id,
            backup_type=backup_type,
            status=BackupStatus.PENDING,
            created_at=datetime.now(),
            storage_type=storage_type,
            compression=compression,
            metadata={"description": description} if description else {}
        )
        
        self.backup_metadata[backup_id] = metadata
        self.running_backups.add(backup_id)
        
        try:
            # Update status
            metadata.status = BackupStatus.RUNNING
            
            # Collect data based on backup type
            data = await self._collect_backup_data(backup_type, backup_id)
            
            if data is None:
                raise Exception("Failed to collect backup data")
            
            # Compress data
            compressed_data = await self._compress_data(data, compression)
            
            # Calculate checksum
            metadata.checksum = hashlib.sha256(compressed_data).hexdigest()
            metadata.size_bytes = len(compressed_data)
            
            # Store backup
            storage = self.storages[storage_type]
            success = await storage.store(backup_id, compressed_data, metadata)
            
            if not success:
                raise Exception("Failed to store backup")
            
            # Update metadata
            metadata.status = BackupStatus.SUCCESS
            metadata.completed_at = datetime.now()
            
            # Update tracking
            self.last_backup_times[backup_type] = datetime.now()
            
            # Record metrics
            observability.increment_counter(
                "backup_created_total",
                labels={
                    "backup_type": backup_type.value,
                    "storage_type": storage_type.value,
                    "status": "success"
                }
            )
            
            observability.record_histogram(
                "backup_size_bytes",
                metadata.size_bytes,
                labels={"backup_type": backup_type.value}
            )
            
            self.logger.info(f"Backup {backup_id} created successfully")
            return backup_id
        
        except Exception as e:
            metadata.status = BackupStatus.FAILED
            metadata.metadata["error"] = str(e)
            
            # Record failure metric
            observability.increment_counter(
                "backup_created_total",
                labels={
                    "backup_type": backup_type.value,
                    "storage_type": storage_type.value,
                    "status": "failed"
                }
            )
            
            # Create alert
            await observability.create_alert(
                AlertSeverity.HIGH,
                f"Backup failed: {backup_id} - {str(e)}",
                "backup",
                "backup_failure",
                1,
                0,
                {"backup_id": backup_id, "backup_type": backup_type.value}
            )
            
            self.logger.error(f"Backup {backup_id} failed: {e}")
            return None
        
        finally:
            self.running_backups.discard(backup_id)
    
    async def _collect_backup_data(self, backup_type: BackupType, backup_id: str) -> Optional[bytes]:
        """Collect data for backup based on type"""
        
        try:
            if backup_type == BackupType.CONFIGURATION:
                # Backup configuration data
                config_data = config_system.export_config()
                return json.dumps(config_data, default=str).encode()
            
            elif backup_type == BackupType.METRICS:
                # Backup metrics data
                metrics_data = observability.get_metrics()
                return json.dumps(metrics_data, default=str).encode()
            
            elif backup_type == BackupType.STATE:
                # Backup system state
                state_data = await self._collect_system_state()
                return json.dumps(state_data, default=str).encode()
            
            elif backup_type == BackupType.LOGS:
                # Backup recent logs
                logs_data = await self._collect_logs()
                return logs_data.encode()
            
            elif backup_type == BackupType.FULL:
                # Full system backup
                full_data = {
                    "configuration": config_system.export_config(),
                    "metrics": observability.get_metrics(),
                    "system_state": await self._collect_system_state(),
                    "backup_metadata": {k: asdict(v) for k, v in self.backup_metadata.items()}
                }
                return json.dumps(full_data, default=str).encode()
            
            else:
                self.logger.warning(f"Unknown backup type: {backup_type}")
                return None
        
        except Exception as e:
            self.logger.error(f"Failed to collect backup data for {backup_type}: {e}")
            return None
    
    async def _collect_system_state(self) -> Dict[str, Any]:
        """Collect current system state"""
        return {
            "timestamp": datetime.now().isoformat(),
            "backup_system": {
                "running_backups": len(self.running_backups),
                "total_backups": len(self.backup_metadata),
                "last_backup_times": {k.value: v.isoformat() for k, v in self.last_backup_times.items()}
            },
            "system_info": {
                "cpu_count": os.cpu_count(),
                "working_directory": str(Path.cwd()),
                "python_version": os.sys.version
            }
        }
    
    async def _collect_logs(self) -> str:
        """Collect recent logs"""
        # This would collect logs from logging system
        # For now, return placeholder
        return f"Log collection timestamp: {datetime.now().isoformat()}"
    
    # Compression Methods
    
    async def _compress_data(self, data: bytes, compression: CompressionType) -> bytes:
        """Compress data using specified compression type"""
        handler = self.compression_handlers.get(compression)
        if handler:
            return await handler(data)
        return data
    
    async def _decompress_data(self, data: bytes, compression: CompressionType) -> bytes:
        """Decompress data using specified compression type"""
        handler = self.decompression_handlers.get(compression)
        if handler:
            return await handler(data)
        return data
    
    async def _compress_gzip(self, data: bytes) -> bytes:
        """Compress data using gzip"""
        return gzip.compress(data)
    
    async def _decompress_gzip(self, data: bytes) -> bytes:
        """Decompress data using gzip"""
        return gzip.decompress(data)
    
    async def _compress_none(self, data: bytes) -> bytes:
        """No compression"""
        return data
    
    async def _decompress_none(self, data: bytes) -> bytes:
        """No decompression"""
        return data
    
    # Restore Operations
    
    async def restore_backup(self, backup_id: str, target_path: str = None) -> bool:
        """Restore a backup"""
        
        if backup_id not in self.backup_metadata:
            self.logger.error(f"Backup {backup_id} not found")
            return False
        
        metadata = self.backup_metadata[backup_id]
        
        try:
            # Retrieve backup data
            storage = self.storages[metadata.storage_type]
            compressed_data = await storage.retrieve(backup_id)
            
            if compressed_data is None:
                raise Exception("Failed to retrieve backup data")
            
            # Verify checksum
            if metadata.checksum:
                actual_checksum = hashlib.sha256(compressed_data).hexdigest()
                if actual_checksum != metadata.checksum:
                    raise Exception("Backup data corruption detected")
            
            # Decompress data
            data = await self._decompress_data(compressed_data, metadata.compression)
            
            # Restore based on backup type
            success = await self._restore_backup_data(metadata.backup_type, data, target_path)
            
            if success:
                # Record success metric
                observability.increment_counter(
                    "backup_restored_total",
                    labels={
                        "backup_type": metadata.backup_type.value,
                        "status": "success"
                    }
                )
                
                self.logger.info(f"Backup {backup_id} restored successfully")
                return True
            else:
                raise Exception("Failed to restore backup data")
        
        except Exception as e:
            # Record failure metric
            observability.increment_counter(
                "backup_restored_total",
                labels={
                    "backup_type": metadata.backup_type.value,
                    "status": "failed"
                }
            )
            
            self.logger.error(f"Failed to restore backup {backup_id}: {e}")
            return False
    
    async def _restore_backup_data(self, backup_type: BackupType, data: bytes, target_path: str = None) -> bool:
        """Restore backup data based on type"""
        
        try:
            if backup_type == BackupType.CONFIGURATION:
                # Restore configuration
                config_data = json.loads(data.decode())
                errors = await config_system.import_config(config_data)
                return len(errors) == 0
            
            elif backup_type == BackupType.FULL:
                # Restore full system
                full_data = json.loads(data.decode())
                
                # Restore configuration
                if "configuration" in full_data:
                    await config_system.import_config(full_data["configuration"])
                
                # Other restore operations would go here
                return True
            
            elif backup_type in [BackupType.METRICS, BackupType.LOGS, BackupType.STATE]:
                # For these types, write to file if target_path provided
                if target_path:
                    async with aiofiles.open(target_path, 'wb') as f:
                        await f.write(data)
                    return True
                else:
                    self.logger.warning(f"No target path provided for {backup_type} restore")
                    return False
            
            else:
                self.logger.warning(f"Unknown backup type for restore: {backup_type}")
                return False
        
        except Exception as e:
            self.logger.error(f"Failed to restore backup data for {backup_type}: {e}")
            return False
    
    # Scheduling and Automation
    
    def schedule_backup(self, backup_type: BackupType, cron_expression: str,
                       storage_type: StorageType = StorageType.LOCAL,
                       retention_days: int = 30) -> str:
        """Schedule automatic backups"""
        
        schedule_id = f"schedule_{backup_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        schedule = BackupSchedule(
            schedule_id=schedule_id,
            backup_type=backup_type,
            cron_expression=cron_expression,
            storage_type=storage_type,
            retention_days=retention_days
        )
        
        self.backup_schedules[schedule_id] = schedule
        
        self.logger.info(f"Backup scheduled: {schedule_id}")
        return schedule_id
    
    async def _backup_scheduler(self):
        """Background task for scheduled backups"""
        while self.is_running:
            try:
                current_time = datetime.now()
                
                for schedule_id, schedule in self.backup_schedules.items():
                    if not schedule.enabled:
                        continue
                    
                    # Check if it's time to run this backup
                    if self._should_run_scheduled_backup(schedule, current_time):
                        await self.create_backup(
                            schedule.backup_type,
                            schedule.storage_type,
                            retention_days=schedule.retention_days
                        )
                
                await asyncio.sleep(60)  # Check every minute
            
            except Exception as e:
                self.logger.error(f"Backup scheduler error: {e}")
                await asyncio.sleep(60)
    
    def _should_run_scheduled_backup(self, schedule: BackupSchedule, current_time: datetime) -> bool:
        """Check if scheduled backup should run"""
        # Simple implementation - in production, use a proper cron parser
        # For now, just check if it's been more than an hour since last backup
        last_backup = self.last_backup_times.get(schedule.backup_type)
        if last_backup is None:
            return True
        
        return (current_time - last_backup).total_seconds() > 3600
    
    async def _backup_monitor(self):
        """Monitor backup system health"""
        while self.is_running:
            try:
                # Check for failed backups
                failed_backups = [
                    backup_id for backup_id, metadata in self.backup_metadata.items()
                    if metadata.status == BackupStatus.FAILED
                ]
                
                if failed_backups:
                    # Create alert for failed backups
                    await observability.create_alert(
                        AlertSeverity.MEDIUM,
                        f"Failed backups detected: {len(failed_backups)}",
                        "backup",
                        "failed_backups",
                        len(failed_backups),
                        0,
                        {"failed_backup_ids": failed_backups[:5]}  # Limit to first 5
                    )
                
                # Check backup freshness
                await self._check_backup_freshness()
                
                # Update metrics
                observability.set_gauge(
                    "backup_total_count",
                    len(self.backup_metadata)
                )
                
                observability.set_gauge(
                    "backup_running_count",
                    len(self.running_backups)
                )
                
                await asyncio.sleep(300)  # Check every 5 minutes
            
            except Exception as e:
                self.logger.error(f"Backup monitor error: {e}")
                await asyncio.sleep(300)
    
    async def _check_backup_freshness(self):
        """Check if backups are fresh enough"""
        current_time = datetime.now()
        
        for backup_type in BackupType:
            last_backup = self.last_backup_times.get(backup_type)
            
            if last_backup is None:
                continue
            
            hours_since_backup = (current_time - last_backup).total_seconds() / 3600
            
            # Alert if backup is older than 24 hours
            if hours_since_backup > 24:
                await observability.create_alert(
                    AlertSeverity.MEDIUM,
                    f"Backup {backup_type.value} is {hours_since_backup:.1f} hours old",
                    "backup",
                    "backup_freshness",
                    hours_since_backup,
                    24,
                    {"backup_type": backup_type.value}
                )
    
    async def _cleanup_old_backups(self):
        """Clean up old backups based on retention policy"""
        while self.is_running:
            try:
                current_time = datetime.now()
                
                for backup_id, metadata in list(self.backup_metadata.items()):
                    # Check if backup is older than retention period
                    backup_age = (current_time - metadata.created_at).days
                    
                    if backup_age > metadata.retention_days:
                        # Delete old backup
                        await self._delete_backup(backup_id)
                
                await asyncio.sleep(3600)  # Check every hour
            
            except Exception as e:
                self.logger.error(f"Backup cleanup error: {e}")
                await asyncio.sleep(3600)
    
    async def _delete_backup(self, backup_id: str) -> bool:
        """Delete a backup"""
        if backup_id not in self.backup_metadata:
            return False
        
        metadata = self.backup_metadata[backup_id]
        
        try:
            # Delete from storage
            storage = self.storages[metadata.storage_type]
            success = await storage.delete(backup_id)
            
            if success:
                # Remove from metadata
                del self.backup_metadata[backup_id]
                
                self.logger.info(f"Backup {backup_id} deleted")
                return True
            else:
                self.logger.error(f"Failed to delete backup {backup_id}")
                return False
        
        except Exception as e:
            self.logger.error(f"Error deleting backup {backup_id}: {e}")
            return False
    
    # API Methods
    
    def get_backup_status(self) -> Dict[str, Any]:
        """Get backup system status"""
        return {
            "total_backups": len(self.backup_metadata),
            "running_backups": len(self.running_backups),
            "backup_types": {
                backup_type.value: len([
                    b for b in self.backup_metadata.values()
                    if b.backup_type == backup_type
                ])
                for backup_type in BackupType
            },
            "last_backup_times": {
                k.value: v.isoformat() for k, v in self.last_backup_times.items()
            },
            "scheduled_backups": len(self.backup_schedules)
        }
    
    def list_backups(self, backup_type: BackupType = None, limit: int = 100) -> List[BackupMetadata]:
        """List backups"""
        backups = list(self.backup_metadata.values())
        
        if backup_type:
            backups = [b for b in backups if b.backup_type == backup_type]
        
        # Sort by creation time (newest first)
        backups.sort(key=lambda b: b.created_at, reverse=True)
        
        return backups[:limit]
    
    def get_backup_metadata(self, backup_id: str) -> Optional[BackupMetadata]:
        """Get backup metadata"""
        return self.backup_metadata.get(backup_id)
    
    async def shutdown(self):
        """Shutdown backup system"""
        self.is_running = False
        
        # Cancel background tasks
        for task in self.backup_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self.backup_tasks, return_exceptions=True)
        
        self.logger.info("Backup system shutdown complete")


# Global instance
backup_system = BackupSystem()


# Usage example
if __name__ == "__main__":
    async def example_usage():
        # Initialize backup system
        await backup_system.initialize()
        
        # Create a configuration backup
        backup_id = await backup_system.create_backup(
            BackupType.CONFIGURATION,
            description="Daily configuration backup"
        )
        
        print(f"Created backup: {backup_id}")
        
        # Schedule daily full backups
        schedule_id = backup_system.schedule_backup(
            BackupType.FULL,
            "0 2 * * *",  # Daily at 2 AM
            retention_days=7
        )
        
        print(f"Scheduled backup: {schedule_id}")
        
        # Get backup status
        status = backup_system.get_backup_status()
        print(f"Backup status: {status}")
        
        # List backups
        backups = backup_system.list_backups()
        print(f"Total backups: {len(backups)}")
        
        # Shutdown
        await backup_system.shutdown()
    
    asyncio.run(example_usage())