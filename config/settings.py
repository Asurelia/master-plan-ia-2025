#!/usr/bin/env python3
"""
Master Plan IA 2025 - Configuration centralisée
Système de configuration avec validation Pydantic
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from enum import Enum
import logging

# Chemin de base du projet
BASE_DIR = Path(__file__).resolve().parent.parent

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class DatabaseType(str, Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"

class Settings(BaseSettings):
    """Configuration principale du système"""
    
    # Configuration API
    API_HOST: str = Field(default="0.0.0.0", description="Host de l'API")
    API_PORT: int = Field(default=8000, description="Port de l'API")
    API_RELOAD: bool = Field(default=False, description="Rechargement automatique de l'API")
    API_DEBUG: bool = Field(default=False, description="Mode debug de l'API")
    
    # Configuration Observabilité
    OBSERVABILITY_SERVER: str = Field(default="http://localhost:4000", description="URL du serveur d'observabilité")
    OBSERVABILITY_ENABLED: bool = Field(default=True, description="Activer l'observabilité")
    MONITORING_INTERVAL: int = Field(default=30, description="Intervalle de monitoring en secondes")
    
    # Configuration Base de données
    DATABASE_TYPE: DatabaseType = Field(default=DatabaseType.SQLITE, description="Type de base de données")
    DATABASE_URL: str = Field(default="", description="URL de la base de données")
    DATABASE_POOL_SIZE: int = Field(default=10, description="Taille du pool de connexions")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, description="Overflow maximum du pool")
    
    # Configuration Redis
    REDIS_URL: str = Field(default="redis://localhost:6379", description="URL Redis")
    REDIS_ENABLED: bool = Field(default=False, description="Activer Redis")
    REDIS_TTL: int = Field(default=3600, description="TTL par défaut Redis")
    
    # Configuration AI Providers
    ANTHROPIC_API_KEY: str = Field(default="", description="Clé API Anthropic")
    OPENAI_API_KEY: str = Field(default="", description="Clé API OpenAI")
    OLLAMA_URL: str = Field(default="http://localhost:11434", description="URL Ollama")
    OLLAMA_ENABLED: bool = Field(default=False, description="Activer Ollama")
    
    # Configuration Logging
    LOG_LEVEL: LogLevel = Field(default=LogLevel.INFO, description="Niveau de logging")
    LOG_DIR: str = Field(default="", description="Répertoire des logs")
    LOG_FILE: str = Field(default="master_plan.log", description="Fichier de log")
    LOG_MAX_SIZE: int = Field(default=10, description="Taille maximum des logs en MB")
    LOG_BACKUP_COUNT: int = Field(default=5, description="Nombre de backups de logs")
    
    # Configuration Sécurité
    SECRET_KEY: str = Field(default="", description="Clé secrète pour JWT")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Durée d'expiration des tokens")
    ALLOWED_HOSTS: List[str] = Field(default=["*"], description="Hosts autorisés")
    
    # Configuration Coordination
    MAX_CONCURRENT_WORKFLOWS: int = Field(default=10, description="Nombre maximum de workflows concurrents")
    MAX_AGENTS_PER_WORKFLOW: int = Field(default=5, description="Nombre maximum d'agents par workflow")
    DEFAULT_TASK_TIMEOUT: int = Field(default=300, description="Timeout par défaut des tâches")
    MAX_RETRIES: int = Field(default=3, description="Nombre maximum de tentatives")
    
    # Configuration Performance
    WORKER_THREADS: int = Field(default=4, description="Nombre de threads workers")
    ASYNC_POOL_SIZE: int = Field(default=100, description="Taille du pool async")
    REQUEST_TIMEOUT: int = Field(default=30, description="Timeout des requêtes")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        
    @field_validator('DATABASE_URL', mode='before')
    @classmethod
    def set_database_url(cls, v, info):
        """Génère l'URL de la base de données si non fournie"""
        if v:
            return v
        
        # Utiliser SQLite par défaut
        db_path = BASE_DIR / "data" / "master_plan.db"
        db_path.parent.mkdir(exist_ok=True)
        return f"sqlite:///{db_path}"
    
    @field_validator('LOG_DIR', mode='before')
    @classmethod
    def set_log_dir(cls, v):
        """Génère le répertoire des logs si non fourni"""
        if v:
            return v
        
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        return str(log_dir)
    
    @field_validator('SECRET_KEY', mode='before')
    @classmethod
    def set_secret_key(cls, v):
        """Génère une clé secrète si non fournie"""
        if v:
            return v
        
        import secrets
        return secrets.token_urlsafe(32)
    
    def get_database_config(self) -> Dict[str, Any]:
        """Retourne la configuration de la base de données"""
        return {
            'url': self.DATABASE_URL,
            'pool_size': self.DATABASE_POOL_SIZE,
            'max_overflow': self.DATABASE_MAX_OVERFLOW,
            'echo': self.API_DEBUG
        }
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Retourne la configuration du logging"""
        return {
            'level': self.LOG_LEVEL.value,
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'handlers': {
                'file': {
                    'filename': Path(self.LOG_DIR) / self.LOG_FILE,
                    'maxBytes': self.LOG_MAX_SIZE * 1024 * 1024,
                    'backupCount': self.LOG_BACKUP_COUNT
                },
                'console': {
                    'level': self.LOG_LEVEL.value
                }
            }
        }
    
    def get_cors_config(self) -> Dict[str, Any]:
        """Retourne la configuration CORS"""
        return {
            'allow_origins': self.ALLOWED_HOSTS,
            'allow_credentials': True,
            'allow_methods': ["*"],
            'allow_headers': ["*"]
        }
    
    def get_ai_providers_config(self) -> Dict[str, Any]:
        """Retourne la configuration des providers AI"""
        return {
            'anthropic': {
                'api_key': self.ANTHROPIC_API_KEY,
                'enabled': bool(self.ANTHROPIC_API_KEY)
            },
            'openai': {
                'api_key': self.OPENAI_API_KEY,
                'enabled': bool(self.OPENAI_API_KEY)
            },
            'ollama': {
                'url': self.OLLAMA_URL,
                'enabled': self.OLLAMA_ENABLED
            }
        }
    
    def validate_configuration(self) -> List[str]:
        """Valide la configuration et retourne les erreurs"""
        errors = []
        
        # Vérifier les clés API si les providers sont activés
        if self.ANTHROPIC_API_KEY and not self.ANTHROPIC_API_KEY.startswith('sk-'):
            errors.append("ANTHROPIC_API_KEY format invalide")
        
        if self.OPENAI_API_KEY and not self.OPENAI_API_KEY.startswith('sk-'):
            errors.append("OPENAI_API_KEY format invalide")
        
        # Vérifier les ports
        if not 1 <= self.API_PORT <= 65535:
            errors.append("API_PORT doit être entre 1 et 65535")
        
        # Vérifier les répertoires
        if not Path(self.LOG_DIR).exists():
            try:
                Path(self.LOG_DIR).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Impossible de créer le répertoire de logs: {e}")
        
        return errors

# Instance globale des settings
settings = Settings()

# Configuration du logging
def setup_logging():
    """Configure le système de logging"""
    log_config = settings.get_logging_config()
    
    logging.basicConfig(
        level=getattr(logging, log_config['level']),
        format=log_config['format'],
        handlers=[
            logging.FileHandler(log_config['handlers']['file']['filename']),
            logging.StreamHandler()
        ]
    )
    
    # Configurer les loggers spécifiques
    logger = logging.getLogger('master_plan')
    logger.setLevel(getattr(logging, log_config['level']))
    
    return logger

# Fonction pour recharger la configuration
def reload_settings():
    """Recharge la configuration depuis les fichiers"""
    global settings
    settings = Settings()
    return settings

# Fonction pour obtenir la configuration
def get_settings() -> Settings:
    """Retourne l'instance des settings"""
    return settings

# Validation au démarrage
if __name__ == "__main__":
    errors = settings.validate_configuration()
    if errors:
        print("❌ Erreurs de configuration:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("✅ Configuration valide")
    
    print(f"\nConfiguration actuelle:")
    print(f"  - API: {settings.API_HOST}:{settings.API_PORT}")
    print(f"  - Database: {settings.DATABASE_URL}")
    print(f"  - Logs: {settings.LOG_DIR}")
    print(f"  - Observability: {settings.OBSERVABILITY_SERVER}")