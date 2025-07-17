"""
Secure Configuration Management
Fixes hardcoded credentials and implements defensive configuration practices
Based on Stack Overflow & security best practices 2025
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from cryptography.fernet import Fernet
import secrets
import json

logger = logging.getLogger(__name__)


@dataclass
class SecureCredentials:
    """Secure credential management - NO hardcoded secrets"""
    
    # Database credentials
    database_url: Optional[str] = None
    database_password: Optional[str] = None
    
    # API credentials
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    
    # Internal secrets
    jwt_secret_key: Optional[str] = None
    encryption_key: Optional[str] = None
    
    # External services
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    redis_url: Optional[str] = None
    
    def __post_init__(self):
        """Load credentials from secure sources"""
        self._load_from_environment()
        self._validate_required_credentials()
        self._generate_missing_secrets()
    
    def _load_from_environment(self):
        """Load from environment variables (primary source)"""
        env_mapping = {
            'database_url': 'DATABASE_URL',
            'database_password': 'DATABASE_PASSWORD',
            'anthropic_api_key': 'ANTHROPIC_API_KEY',
            'openai_api_key': 'OPENAI_API_KEY',
            'jwt_secret_key': 'JWT_SECRET_KEY',
            'encryption_key': 'ENCRYPTION_KEY',
            'supabase_url': 'SUPABASE_URL',
            'supabase_anon_key': 'SUPABASE_ANON_KEY',
            'redis_url': 'REDIS_URL',
        }
        
        for attr, env_var in env_mapping.items():
            value = os.getenv(env_var)
            if value:
                setattr(self, attr, value)
    
    def _validate_required_credentials(self):
        """Validate that critical credentials are present"""
        required_in_production = [
            'jwt_secret_key',
            'encryption_key'
        ]
        
        is_production = os.getenv('ENVIRONMENT', 'development') == 'production'
        
        if is_production:
            missing = [attr for attr in required_in_production if not getattr(self, attr)]
            if missing:
                raise ValueError(f"Missing required production credentials: {missing}")
    
    def _generate_missing_secrets(self):
        """Generate secure secrets for missing values"""
        if not self.jwt_secret_key:
            self.jwt_secret_key = self._generate_secure_secret()
            logger.info("Generated new JWT secret key")
            self._save_generated_secret('JWT_SECRET_KEY', self.jwt_secret_key)
        
        if not self.encryption_key:
            self.encryption_key = Fernet.generate_key().decode()
            logger.info("Generated new encryption key")
            self._save_generated_secret('ENCRYPTION_KEY', self.encryption_key)
    
    def _generate_secure_secret(self) -> str:
        """Generate cryptographically secure secret"""
        return secrets.token_urlsafe(32)  # 256 bits of entropy
    
    def _save_generated_secret(self, key: str, value: str):
        """Save generated secret to secure location"""
        try:
            # Save to secure file (dev only)
            secrets_dir = Path('.secrets')
            secrets_dir.mkdir(mode=0o700, exist_ok=True)
            
            secret_file = secrets_dir / f"{key.lower()}.key"
            secret_file.write_text(value)
            secret_file.chmod(0o600)  # Read-only for owner
            
            logger.warning(
                f"Generated {key} saved to {secret_file}. "
                f"In production, set environment variable {key}"
            )
        except Exception as e:
            logger.error(f"Failed to save generated secret {key}: {e}")


@dataclass
class SecureAppConfig:
    """Application configuration with security defaults"""
    
    # Environment
    environment: str = field(default_factory=lambda: os.getenv('ENVIRONMENT', 'development'))
    debug: bool = field(default_factory=lambda: os.getenv('DEBUG', 'false').lower() == 'true')
    
    # Network
    host: str = field(default_factory=lambda: os.getenv('HOST', '127.0.0.1'))
    port: int = field(default_factory=lambda: int(os.getenv('PORT', '8000')))
    
    # CORS - SECURE DEFAULTS
    allowed_origins: list = field(default_factory=lambda: [])
    allowed_methods: list = field(default_factory=lambda: ['GET', 'POST', 'PUT', 'DELETE'])
    allowed_headers: list = field(default_factory=lambda: ['Authorization', 'Content-Type'])
    
    # Rate limiting - DEFENSIVE DEFAULTS
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 60  # Conservative default
    rate_limit_burst_multiplier: float = 1.2
    
    # Security headers
    security_headers_enabled: bool = True
    https_redirect_enabled: bool = field(default_factory=lambda: os.getenv('ENVIRONMENT') == 'production')
    
    # Monitoring
    metrics_enabled: bool = True
    logging_level: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    
    def __post_init__(self):
        """Post-initialization validation and security checks"""
        self._load_cors_config()
        self._validate_security_config()
        self._apply_security_defaults()
    
    def _load_cors_config(self):
        """Load CORS configuration securely"""
        origins_env = os.getenv('ALLOWED_ORIGINS', '')
        if origins_env:
            self.allowed_origins = [origin.strip() for origin in origins_env.split(',')]
        else:
            # Secure defaults based on environment
            if self.environment == 'development':
                self.allowed_origins = ['http://localhost:3000', 'http://localhost:5173']
            else:
                # Production must explicitly set origins
                self.allowed_origins = []
    
    def _validate_security_config(self):
        """Validate security configuration"""
        if self.environment == 'production':
            # Production security checks
            if not self.allowed_origins:
                raise ValueError("ALLOWED_ORIGINS must be set in production")
            
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            
            if '*' in self.allowed_origins:
                raise ValueError("Wildcard CORS origins not allowed in production")
        
        # Rate limiting validation
        if self.rate_limit_requests_per_minute < 1:
            raise ValueError("Rate limit must be at least 1 request per minute")
    
    def _apply_security_defaults(self):
        """Apply defensive security defaults"""
        # Force HTTPS in production
        if self.environment == 'production':
            self.https_redirect_enabled = True
            self.security_headers_enabled = True
        
        # Ensure rate limiting is reasonable
        if self.rate_limit_requests_per_minute > 1000:
            logger.warning(f"High rate limit: {self.rate_limit_requests_per_minute}/min")


class SecureConfigManager:
    """Secure configuration manager with encryption and validation"""
    
    def __init__(self):
        self.credentials = SecureCredentials()
        self.app_config = SecureAppConfig()
        self._cipher = self._init_encryption()
    
    def _init_encryption(self) -> Fernet:
        """Initialize encryption for sensitive config values"""
        if not self.credentials.encryption_key:
            raise ValueError("Encryption key not available")
        
        return Fernet(self.credentials.encryption_key.encode())
    
    def encrypt_value(self, value: str) -> str:
        """Encrypt sensitive configuration value"""
        return self._cipher.encrypt(value.encode()).decode()
    
    def decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt sensitive configuration value"""
        return self._cipher.decrypt(encrypted_value.encode()).decode()
    
    def get_database_url(self) -> Optional[str]:
        """Get database URL with password protection"""
        if self.credentials.database_url:
            return self.credentials.database_url
        
        # Construct from components if available
        if self.credentials.database_password:
            # Example: postgresql://user:password@localhost/db
            return f"postgresql://user:{self.credentials.database_password}@localhost/master_plan_ia"
        
        return None
    
    def get_api_key(self, service: str) -> Optional[str]:
        """Get API key for external service"""
        service_mapping = {
            'anthropic': self.credentials.anthropic_api_key,
            'openai': self.credentials.openai_api_key,
        }
        
        key = service_mapping.get(service)
        if not key:
            logger.warning(f"API key for {service} not configured")
        
        return key
    
    def get_jwt_config(self) -> Dict[str, Any]:
        """Get JWT configuration"""
        if not self.credentials.jwt_secret_key:
            raise ValueError("JWT secret key not configured")
        
        return {
            'secret_key': self.credentials.jwt_secret_key,
            'algorithm': 'HS256',
            'access_token_expire_minutes': 30,
            'refresh_token_expire_days': 7,
        }
    
    def get_cors_config(self) -> Dict[str, Any]:
        """Get secure CORS configuration"""
        return {
            'allow_origins': self.app_config.allowed_origins,
            'allow_credentials': True,
            'allow_methods': self.app_config.allowed_methods,
            'allow_headers': self.app_config.allowed_headers,
        }
    
    def get_rate_limit_config(self) -> Dict[str, Any]:
        """Get rate limiting configuration"""
        return {
            'enabled': self.app_config.rate_limit_enabled,
            'requests_per_minute': self.app_config.rate_limit_requests_per_minute,
            'burst_multiplier': self.app_config.rate_limit_burst_multiplier,
        }
    
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.app_config.environment == 'production'
    
    def is_debug(self) -> bool:
        """Check if debug mode is enabled"""
        return self.app_config.debug and not self.is_production()
    
    def validate_configuration(self) -> Dict[str, bool]:
        """Validate entire configuration"""
        checks = {
            'credentials_loaded': bool(self.credentials.jwt_secret_key),
            'cors_configured': bool(self.app_config.allowed_origins),
            'rate_limiting_enabled': self.app_config.rate_limit_enabled,
            'security_headers_enabled': self.app_config.security_headers_enabled,
            'https_in_production': not self.is_production() or self.app_config.https_redirect_enabled,
        }
        
        all_valid = all(checks.values())
        
        if not all_valid:
            failed_checks = [key for key, value in checks.items() if not value]
            logger.error(f"Configuration validation failed: {failed_checks}")
        
        return checks


# Global secure config instance
secure_config = SecureConfigManager()

# Convenience functions
def get_database_url() -> Optional[str]:
    return secure_config.get_database_url()

def get_api_key(service: str) -> Optional[str]:
    return secure_config.get_api_key(service)

def get_jwt_secret() -> str:
    config = secure_config.get_jwt_config()
    return config['secret_key']

def get_cors_config() -> Dict[str, Any]:
    return secure_config.get_cors_config()

def is_production() -> bool:
    return secure_config.is_production()

def is_debug() -> bool:
    return secure_config.is_debug()