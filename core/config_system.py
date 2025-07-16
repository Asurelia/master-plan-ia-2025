"""
Advanced Configuration Management System
Handles multi-environment configuration, secrets, and hot-reload
"""

import asyncio
import json
import logging
import os
import hashlib
import yaml
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Callable, Set
import aiofiles
import aiofiles.os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field, validator
import redis.asyncio as redis

from .observability_system import observability, MetricType


class ConfigLevel(Enum):
    DEFAULT = "default"
    ENVIRONMENT = "environment"
    USER = "user"
    RUNTIME = "runtime"
    OVERRIDE = "override"


class SecretType(Enum):
    PASSWORD = "password"
    API_KEY = "api_key"
    TOKEN = "token"
    CERTIFICATE = "certificate"
    PRIVATE_KEY = "private_key"


@dataclass
class ConfigChange:
    key: str
    old_value: Any
    new_value: Any
    level: ConfigLevel
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "unknown"


@dataclass
class SecretConfig:
    name: str
    secret_type: SecretType
    encrypted_value: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    rotation_days: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConfigValidator:
    """Configuration validation system"""
    
    def __init__(self):
        self.rules: Dict[str, List[Callable]] = defaultdict(list)
        self.schemas: Dict[str, BaseModel] = {}
    
    def add_rule(self, key: str, validator_func: Callable):
        """Add a validation rule for a configuration key"""
        self.rules[key].append(validator_func)
    
    def add_schema(self, section: str, schema: BaseModel):
        """Add a schema for a configuration section"""
        self.schemas[section] = schema
    
    def validate(self, key: str, value: Any) -> List[str]:
        """Validate a configuration value"""
        errors = []
        
        for rule in self.rules.get(key, []):
            try:
                if not rule(value):
                    errors.append(f"Validation failed for {key}: {rule.__name__}")
            except Exception as e:
                errors.append(f"Validation error for {key}: {str(e)}")
        
        return errors
    
    def validate_section(self, section: str, data: Dict[str, Any]) -> List[str]:
        """Validate a configuration section against its schema"""
        errors = []
        
        if section in self.schemas:
            try:
                self.schemas[section](**data)
            except Exception as e:
                errors.append(f"Schema validation failed for {section}: {str(e)}")
        
        return errors


class SecretManager:
    """Secure secret management with encryption"""
    
    def __init__(self, key_path: str = "secrets/master.key"):
        self.key_path = Path(key_path)
        self.secrets: Dict[str, SecretConfig] = {}
        self.fernet = None
        self.logger = logging.getLogger(__name__)
        
        # Initialize encryption
        self._initialize_encryption()
    
    def _initialize_encryption(self):
        """Initialize encryption key"""
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        
        if self.key_path.exists():
            with open(self.key_path, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_path, 'wb') as f:
                f.write(key)
            # Set restrictive permissions
            os.chmod(self.key_path, 0o600)
        
        self.fernet = Fernet(key)
    
    def store_secret(self, name: str, value: str, secret_type: SecretType = SecretType.PASSWORD,
                    expires_at: Optional[datetime] = None, rotation_days: Optional[int] = None,
                    metadata: Dict[str, Any] = None):
        """Store a secret securely"""
        encrypted_value = self.fernet.encrypt(value.encode()).decode()
        
        self.secrets[name] = SecretConfig(
            name=name,
            secret_type=secret_type,
            encrypted_value=encrypted_value,
            expires_at=expires_at,
            rotation_days=rotation_days,
            metadata=metadata or {}
        )
        
        self.logger.info(f"Secret {name} stored")
    
    def get_secret(self, name: str) -> Optional[str]:
        """Retrieve a secret"""
        if name not in self.secrets:
            return None
        
        secret = self.secrets[name]
        
        # Check if secret expired
        if secret.expires_at and datetime.now() > secret.expires_at:
            self.logger.warning(f"Secret {name} has expired")
            return None
        
        try:
            return self.fernet.decrypt(secret.encrypted_value.encode()).decode()
        except Exception as e:
            self.logger.error(f"Failed to decrypt secret {name}: {e}")
            return None
    
    def list_secrets(self) -> List[str]:
        """List all secret names"""
        return list(self.secrets.keys())
    
    def delete_secret(self, name: str) -> bool:
        """Delete a secret"""
        if name in self.secrets:
            del self.secrets[name]
            self.logger.info(f"Secret {name} deleted")
            return True
        return False
    
    def rotate_secret(self, name: str, new_value: str) -> bool:
        """Rotate a secret"""
        if name not in self.secrets:
            return False
        
        old_secret = self.secrets[name]
        self.store_secret(
            name, new_value, old_secret.secret_type,
            old_secret.expires_at, old_secret.rotation_days,
            old_secret.metadata
        )
        
        self.logger.info(f"Secret {name} rotated")
        return True
    
    def check_expiring_secrets(self, days: int = 7) -> List[str]:
        """Check for secrets expiring within specified days"""
        expiring = []
        cutoff = datetime.now() + timedelta(days=days)
        
        for name, secret in self.secrets.items():
            if secret.expires_at and secret.expires_at <= cutoff:
                expiring.append(name)
        
        return expiring


class ConfigFileHandler(FileSystemEventHandler):
    """File system event handler for configuration changes"""
    
    def __init__(self, config_system):
        self.config_system = config_system
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        if not event.is_directory:
            self.logger.info(f"Configuration file changed: {event.src_path}")
            asyncio.create_task(self.config_system.reload_file(event.src_path))


class ConfigurationSystem:
    """
    Advanced configuration management system with hot-reload and multi-environment support
    """
    
    def __init__(self, config_dir: str = "config", environment: str = None):
        self.config_dir = Path(config_dir)
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        
        # Configuration hierarchy
        self.config_levels = {
            ConfigLevel.DEFAULT: {},
            ConfigLevel.ENVIRONMENT: {},
            ConfigLevel.USER: {},
            ConfigLevel.RUNTIME: {},
            ConfigLevel.OVERRIDE: {}
        }
        
        # Configuration metadata
        self.config_sources: Dict[str, str] = {}
        self.config_changes: List[ConfigChange] = []
        self.config_watchers: Set[str] = set()
        
        # File watching
        self.observer = Observer()
        self.file_handler = ConfigFileHandler(self)
        
        # Components
        self.validator = ConfigValidator()
        self.secret_manager = SecretManager()
        
        # Callbacks
        self.change_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self.reload_callbacks: List[Callable] = []
        
        # Redis for distributed configuration
        self.redis_client = None
        self.redis_prefix = "config:"
        
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self, redis_url: str = None):
        """Initialize the configuration system"""
        
        # Create config directory
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Connect to Redis for distributed config
        if redis_url:
            try:
                self.redis_client = redis.from_url(redis_url)
                await self.redis_client.ping()
                self.logger.info("✅ Configuration system connected to Redis")
            except Exception as e:
                self.logger.warning(f"⚠️ Redis unavailable for configuration: {e}")
                self.redis_client = None
        
        # Load configuration files
        await self._load_default_config()
        await self._load_environment_config()
        await self._load_user_config()
        
        # Setup validation rules
        self._setup_default_validation()
        
        # Start file watching
        self._start_file_watching()
        
        # Start background tasks
        asyncio.create_task(self._monitor_configuration())
        asyncio.create_task(self._check_secret_expiry())
        
        self.logger.info(f"✅ Configuration system initialized for environment: {self.environment}")
    
    async def _load_default_config(self):
        """Load default configuration"""
        default_config_path = self.config_dir / "default.yaml"
        
        if default_config_path.exists():
            config = await self._load_config_file(default_config_path)
            self.config_levels[ConfigLevel.DEFAULT] = config
            self.config_sources.update({k: str(default_config_path) for k in config.keys()})
    
    async def _load_environment_config(self):
        """Load environment-specific configuration"""
        env_config_path = self.config_dir / f"{self.environment}.yaml"
        
        if env_config_path.exists():
            config = await self._load_config_file(env_config_path)
            self.config_levels[ConfigLevel.ENVIRONMENT] = config
            self.config_sources.update({k: str(env_config_path) for k in config.keys()})
    
    async def _load_user_config(self):
        """Load user-specific configuration"""
        user_config_path = self.config_dir / "user.yaml"
        
        if user_config_path.exists():
            config = await self._load_config_file(user_config_path)
            self.config_levels[ConfigLevel.USER] = config
            self.config_sources.update({k: str(user_config_path) for k in config.keys()})
    
    async def _load_config_file(self, file_path: Path) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            async with aiofiles.open(file_path, 'r') as f:
                content = await f.read()
            
            if file_path.suffix.lower() == '.yaml':
                return yaml.safe_load(content) or {}
            elif file_path.suffix.lower() == '.json':
                return json.loads(content) or {}
            else:
                self.logger.warning(f"Unsupported config file format: {file_path}")
                return {}
        
        except Exception as e:
            self.logger.error(f"Failed to load config file {file_path}: {e}")
            return {}
    
    def _start_file_watching(self):
        """Start watching configuration files for changes"""
        if self.config_dir.exists():
            self.observer.schedule(self.file_handler, str(self.config_dir), recursive=True)
            self.observer.start()
            self.logger.info("Configuration file watching started")
    
    def _setup_default_validation(self):
        """Setup default validation rules"""
        
        # Port validation
        def validate_port(value):
            return isinstance(value, int) and 1 <= value <= 65535
        
        # URL validation
        def validate_url(value):
            return isinstance(value, str) and (value.startswith('http://') or value.startswith('https://'))
        
        # Email validation
        def validate_email(value):
            return isinstance(value, str) and '@' in value
        
        # Add common validation rules
        self.validator.add_rule("port", validate_port)
        self.validator.add_rule("url", validate_url)
        self.validator.add_rule("email", validate_email)
    
    # Configuration Access Methods
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with hierarchy"""
        
        # Check override first
        if key in self.config_levels[ConfigLevel.OVERRIDE]:
            return self.config_levels[ConfigLevel.OVERRIDE][key]
        
        # Check runtime
        if key in self.config_levels[ConfigLevel.RUNTIME]:
            return self.config_levels[ConfigLevel.RUNTIME][key]
        
        # Check user
        if key in self.config_levels[ConfigLevel.USER]:
            return self.config_levels[ConfigLevel.USER][key]
        
        # Check environment
        if key in self.config_levels[ConfigLevel.ENVIRONMENT]:
            return self.config_levels[ConfigLevel.ENVIRONMENT][key]
        
        # Check default
        if key in self.config_levels[ConfigLevel.DEFAULT]:
            return self.config_levels[ConfigLevel.DEFAULT][key]
        
        return default
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get an entire configuration section"""
        result = {}
        
        # Merge from all levels
        for level in [ConfigLevel.DEFAULT, ConfigLevel.ENVIRONMENT, 
                     ConfigLevel.USER, ConfigLevel.RUNTIME, ConfigLevel.OVERRIDE]:
            section_config = self.config_levels[level].get(section, {})
            if isinstance(section_config, dict):
                result.update(section_config)
        
        return result
    
    def get_secret(self, key: str) -> Optional[str]:
        """Get a secret value"""
        return self.secret_manager.get_secret(key)
    
    async def set(self, key: str, value: Any, level: ConfigLevel = ConfigLevel.RUNTIME,
                 validate: bool = True) -> bool:
        """Set configuration value"""
        
        # Validate if requested
        if validate:
            errors = self.validator.validate(key, value)
            if errors:
                self.logger.error(f"Validation failed for {key}: {errors}")
                return False
        
        # Store old value for change tracking
        old_value = self.get(key)
        
        # Set new value
        self.config_levels[level][key] = value
        
        # Track change
        change = ConfigChange(
            key=key,
            old_value=old_value,
            new_value=value,
            level=level,
            source="api"
        )
        self.config_changes.append(change)
        
        # Notify callbacks
        await self._notify_change_callbacks(key, old_value, value)
        
        # Update Redis if available
        if self.redis_client:
            await self._update_redis_config(key, value, level)
        
        # Record metrics
        observability.increment_counter(
            "config_changes_total",
            labels={"key": key, "level": level.value}
        )
        
        self.logger.info(f"Configuration updated: {key} = {value} (level: {level.value})")
        return True
    
    async def set_secret(self, key: str, value: str, secret_type: SecretType = SecretType.PASSWORD):
        """Set a secret value"""
        self.secret_manager.store_secret(key, value, secret_type)
        await self._notify_change_callbacks(f"secret.{key}", None, "[SECRET]")
    
    def delete(self, key: str, level: ConfigLevel = ConfigLevel.RUNTIME) -> bool:
        """Delete configuration value"""
        if key in self.config_levels[level]:
            old_value = self.config_levels[level][key]
            del self.config_levels[level][key]
            
            # Track change
            change = ConfigChange(
                key=key,
                old_value=old_value,
                new_value=None,
                level=level,
                source="api"
            )
            self.config_changes.append(change)
            
            self.logger.info(f"Configuration deleted: {key} (level: {level.value})")
            return True
        
        return False
    
    # File Operations
    
    async def reload_file(self, file_path: str):
        """Reload configuration from file"""
        path = Path(file_path)
        
        if not path.exists():
            return
        
        # Determine configuration level
        if path.name == "default.yaml":
            level = ConfigLevel.DEFAULT
        elif path.name == f"{self.environment}.yaml":
            level = ConfigLevel.ENVIRONMENT
        elif path.name == "user.yaml":
            level = ConfigLevel.USER
        else:
            return
        
        # Load new configuration
        new_config = await self._load_config_file(path)
        old_config = self.config_levels[level].copy()
        
        # Update configuration
        self.config_levels[level] = new_config
        
        # Track changes
        all_keys = set(old_config.keys()) | set(new_config.keys())
        for key in all_keys:
            old_value = old_config.get(key)
            new_value = new_config.get(key)
            
            if old_value != new_value:
                change = ConfigChange(
                    key=key,
                    old_value=old_value,
                    new_value=new_value,
                    level=level,
                    source=str(path)
                )
                self.config_changes.append(change)
                
                # Notify callbacks
                await self._notify_change_callbacks(key, old_value, new_value)
        
        # Notify reload callbacks
        for callback in self.reload_callbacks:
            try:
                await callback(str(path), level)
            except Exception as e:
                self.logger.error(f"Reload callback error: {e}")
        
        self.logger.info(f"Configuration reloaded from {path}")
    
    async def save_to_file(self, file_path: str, section: str = None):
        """Save configuration to file"""
        path = Path(file_path)
        
        # Get configuration data
        if section:
            data = self.get_section(section)
        else:
            data = self._merge_all_configs()
        
        # Write to file
        try:
            async with aiofiles.open(path, 'w') as f:
                if path.suffix.lower() == '.yaml':
                    await f.write(yaml.dump(data, default_flow_style=False))
                elif path.suffix.lower() == '.json':
                    await f.write(json.dumps(data, indent=2))
        
        except Exception as e:
            self.logger.error(f"Failed to save config to {path}: {e}")
            return False
        
        self.logger.info(f"Configuration saved to {path}")
        return True
    
    def _merge_all_configs(self) -> Dict[str, Any]:
        """Merge all configuration levels"""
        result = {}
        
        for level in [ConfigLevel.DEFAULT, ConfigLevel.ENVIRONMENT, 
                     ConfigLevel.USER, ConfigLevel.RUNTIME, ConfigLevel.OVERRIDE]:
            result.update(self.config_levels[level])
        
        return result
    
    # Callbacks and Monitoring
    
    def on_change(self, key: str, callback: Callable):
        """Register callback for configuration changes"""
        self.change_callbacks[key].append(callback)
    
    def on_reload(self, callback: Callable):
        """Register callback for file reloads"""
        self.reload_callbacks.append(callback)
    
    async def _notify_change_callbacks(self, key: str, old_value: Any, new_value: Any):
        """Notify change callbacks"""
        for callback in self.change_callbacks.get(key, []):
            try:
                await callback(key, old_value, new_value)
            except Exception as e:
                self.logger.error(f"Change callback error for {key}: {e}")
    
    async def _update_redis_config(self, key: str, value: Any, level: ConfigLevel):
        """Update configuration in Redis"""
        try:
            redis_key = f"{self.redis_prefix}{level.value}:{key}"
            await self.redis_client.set(redis_key, json.dumps(value))
        except Exception as e:
            self.logger.error(f"Failed to update Redis config for {key}: {e}")
    
    # Background Tasks
    
    async def _monitor_configuration(self):
        """Monitor configuration changes and metrics"""
        while True:
            try:
                # Record configuration metrics
                for level, config in self.config_levels.items():
                    observability.set_gauge(
                        f"config_keys_total",
                        len(config),
                        labels={"level": level.value}
                    )
                
                # Record recent changes
                recent_changes = len([c for c in self.config_changes if 
                                    datetime.now() - c.timestamp < timedelta(hours=1)])
                observability.set_gauge("config_recent_changes", recent_changes)
                
                await asyncio.sleep(60)  # Check every minute
            
            except Exception as e:
                self.logger.error(f"Configuration monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _check_secret_expiry(self):
        """Check for expiring secrets"""
        while True:
            try:
                expiring_secrets = self.secret_manager.check_expiring_secrets()
                
                if expiring_secrets:
                    # Create alert for expiring secrets
                    await observability.create_alert(
                        AlertSeverity.MEDIUM,
                        f"Secrets expiring soon: {', '.join(expiring_secrets)}",
                        "configuration",
                        "secret_expiry",
                        len(expiring_secrets),
                        0,
                        {"expiring_secrets": expiring_secrets}
                    )
                
                await asyncio.sleep(3600)  # Check every hour
            
            except Exception as e:
                self.logger.error(f"Secret expiry check error: {e}")
                await asyncio.sleep(3600)
    
    # API Methods
    
    def get_config_info(self) -> Dict[str, Any]:
        """Get configuration system information"""
        return {
            "environment": self.environment,
            "config_levels": {level.value: len(config) for level, config in self.config_levels.items()},
            "total_keys": sum(len(config) for config in self.config_levels.values()),
            "recent_changes": len([c for c in self.config_changes if 
                                 datetime.now() - c.timestamp < timedelta(hours=1)]),
            "secrets_count": len(self.secret_manager.secrets),
            "watchers": len(self.config_watchers)
        }
    
    def get_recent_changes(self, limit: int = 100) -> List[ConfigChange]:
        """Get recent configuration changes"""
        return sorted(self.config_changes, key=lambda x: x.timestamp, reverse=True)[:limit]
    
    def export_config(self, level: ConfigLevel = None) -> Dict[str, Any]:
        """Export configuration"""
        if level:
            return self.config_levels[level].copy()
        return self._merge_all_configs()
    
    async def import_config(self, config_data: Dict[str, Any], 
                          level: ConfigLevel = ConfigLevel.RUNTIME,
                          validate: bool = True) -> List[str]:
        """Import configuration"""
        errors = []
        
        for key, value in config_data.items():
            success = await self.set(key, value, level, validate)
            if not success:
                errors.append(f"Failed to set {key}")
        
        return errors
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
        
        if self.redis_client:
            await self.redis_client.close()


# Global instance
config_system = ConfigurationSystem()

# Convenience functions
def get_config(key: str, default: Any = None) -> Any:
    """Get configuration value"""
    return config_system.get(key, default)

def get_secret(key: str) -> Optional[str]:
    """Get secret value"""
    return config_system.get_secret(key)

def get_section(section: str) -> Dict[str, Any]:
    """Get configuration section"""
    return config_system.get_section(section)

async def set_config(key: str, value: Any, level: ConfigLevel = ConfigLevel.RUNTIME) -> bool:
    """Set configuration value"""
    return await config_system.set(key, value, level)

async def set_secret(key: str, value: str, secret_type: SecretType = SecretType.PASSWORD):
    """Set secret value"""
    await config_system.set_secret(key, value, secret_type)


# Usage example
if __name__ == "__main__":
    async def example_usage():
        # Initialize configuration system
        await config_system.initialize()
        
        # Set some configuration
        await config_system.set("database.host", "localhost")
        await config_system.set("database.port", 5432)
        await config_system.set_secret("database.password", "secret123")
        
        # Get configuration
        db_host = config_system.get("database.host")
        db_port = config_system.get("database.port")
        db_password = config_system.get_secret("database.password")
        
        print(f"Database: {db_host}:{db_port} (password: {db_password})")
        
        # Get configuration info
        info = config_system.get_config_info()
        print(f"Config info: {info}")
        
        # Cleanup
        await config_system.cleanup()
    
    asyncio.run(example_usage())