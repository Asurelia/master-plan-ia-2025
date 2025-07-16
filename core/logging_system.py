#!/usr/bin/env python3
"""
Master Plan IA 2025 - Système de Logging Centralisé
Système de logging avancé avec rotation, niveaux et persistance
"""

import asyncio
import json
import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Union
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, asdict
import traceback
import psutil
import threading
from queue import Queue, Empty
from contextlib import contextmanager
from datetime import timedelta

# Import de notre intégration Supabase
from core.supabase_integration import supabase

class LogLevel(str, Enum):
    """Niveaux de log"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class LogComponent(str, Enum):
    """Composants du système"""
    SYSTEM = "system"
    API = "api"
    ORCHESTRATION = "orchestration"
    AGENT = "agent"
    TASK = "task"
    WORKFLOW = "workflow"
    CACHE = "cache"
    PLUGIN = "plugin"
    AUTH = "auth"
    WEBHOOK = "webhook"
    DATABASE = "database"
    MONITORING = "monitoring"

@dataclass
class LogEntry:
    """Entrée de log structurée"""
    timestamp: str
    level: LogLevel
    component: LogComponent
    message: str
    details: Dict[str, Any]
    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    workflow_id: Optional[str] = None
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    exception: Optional[str] = None
    stack_trace: Optional[str] = None
    process_id: Optional[int] = None
    thread_id: Optional[int] = None
    
    def __post_init__(self):
        if self.process_id is None:
            self.process_id = os.getpid()
        if self.thread_id is None:
            self.thread_id = threading.get_ident()

class LoggerConfig:
    """Configuration du logger"""
    
    def __init__(self):
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # Configuration des fichiers de log
        self.log_files = {
            LogLevel.DEBUG: self.log_dir / "debug.log",
            LogLevel.INFO: self.log_dir / "info.log",
            LogLevel.WARNING: self.log_dir / "warning.log",
            LogLevel.ERROR: self.log_dir / "error.log",
            LogLevel.CRITICAL: self.log_dir / "critical.log"
        }
        
        # Configuration de la rotation
        self.max_bytes = 10 * 1024 * 1024  # 10MB
        self.backup_count = 5
        
        # Configuration des niveaux
        self.console_level = LogLevel.INFO
        self.file_level = LogLevel.DEBUG
        self.database_level = LogLevel.INFO
        
        # Configuration du format
        self.format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        self.date_format = "%Y-%m-%d %H:%M:%S"
        
        # Configuration des composants
        self.component_levels = {
            LogComponent.SYSTEM: LogLevel.INFO,
            LogComponent.API: LogLevel.INFO,
            LogComponent.ORCHESTRATION: LogLevel.DEBUG,
            LogComponent.AGENT: LogLevel.INFO,
            LogComponent.TASK: LogLevel.INFO,
            LogComponent.WORKFLOW: LogLevel.INFO,
            LogComponent.CACHE: LogLevel.WARNING,
            LogComponent.PLUGIN: LogLevel.INFO,
            LogComponent.AUTH: LogLevel.INFO,
            LogComponent.WEBHOOK: LogLevel.INFO,
            LogComponent.DATABASE: LogLevel.WARNING,
            LogComponent.MONITORING: LogLevel.INFO
        }
        
        # Configuration de la persistance
        self.enable_database_logging = True
        self.enable_file_logging = True
        self.enable_console_logging = True
        
        # Configuration des alertes
        self.alert_thresholds = {
            LogLevel.ERROR: 10,  # 10 erreurs par minute
            LogLevel.CRITICAL: 1  # 1 critique par minute
        }
        
        # Configuration des métriques
        self.enable_metrics = True
        self.metrics_interval = 60  # secondes

class StructuredLogger:
    """Logger structuré avec support multi-destinations"""
    
    def __init__(self, config: LoggerConfig = None):
        self.config = config or LoggerConfig()
        self.loggers = {}
        self.handlers = {}
        self.log_queue = Queue()
        self.is_running = False
        self.worker_thread = None
        
        # Statistiques
        self.stats = {
            'total_logs': 0,
            'logs_by_level': {level.value: 0 for level in LogLevel},
            'logs_by_component': {component.value: 0 for component in LogComponent},
            'errors_per_minute': 0,
            'last_log_time': None,
            'start_time': datetime.now(timezone.utc).isoformat()
        }
        
        # Métriques pour les alertes
        self.recent_logs = {level: [] for level in LogLevel}
        
        # Initialiser les loggers
        self._setup_loggers()
        
        # Démarrer le worker
        self.start()
    
    def _setup_loggers(self):
        """Configure les loggers pour chaque composant"""
        
        # Logger principal
        main_logger = logging.getLogger("master_plan")
        main_logger.setLevel(logging.DEBUG)
        
        # Console handler
        if self.config.enable_console_logging:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(getattr(logging, self.config.console_level.value))
            console_formatter = logging.Formatter(
                self.config.format_string,
                datefmt=self.config.date_format
            )
            console_handler.setFormatter(console_formatter)
            main_logger.addHandler(console_handler)
            self.handlers['console'] = console_handler
        
        # File handlers avec rotation
        if self.config.enable_file_logging:
            for level, log_file in self.config.log_files.items():
                file_handler = logging.handlers.RotatingFileHandler(
                    log_file,
                    maxBytes=self.config.max_bytes,
                    backupCount=self.config.backup_count
                )
                file_handler.setLevel(getattr(logging, level.value))
                file_formatter = logging.Formatter(
                    self.config.format_string,
                    datefmt=self.config.date_format
                )
                file_handler.setFormatter(file_formatter)
                main_logger.addHandler(file_handler)
                self.handlers[f'file_{level.value.lower()}'] = file_handler
        
        # Loggers par composant
        for component in LogComponent:
            component_logger = logging.getLogger(f"master_plan.{component.value}")
            component_logger.setLevel(getattr(logging, self.config.component_levels[component].value))
            self.loggers[component] = component_logger
        
        # Logger racine
        self.logger = main_logger
    
    def start(self):
        """Démarre le worker de logging"""
        if self.is_running:
            return
        
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._log_worker, daemon=True)
        self.worker_thread.start()
        
        self.log(LogLevel.INFO, LogComponent.SYSTEM, "Structured Logger started")
    
    def stop(self):
        """Arrête le worker de logging"""
        if not self.is_running:
            return
        
        self.log(LogLevel.INFO, LogComponent.SYSTEM, "Stopping Structured Logger")
        self.is_running = False
        
        # Attendre que le worker se termine
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
    
    def _log_worker(self):
        """Worker thread pour traiter les logs"""
        while self.is_running:
            try:
                # Récupérer un log de la queue
                try:
                    log_entry = self.log_queue.get(timeout=1)
                except Empty:
                    continue
                
                # Traiter le log
                self._process_log_entry(log_entry)
                
                # Marquer comme terminé
                self.log_queue.task_done()
                
            except Exception as e:
                # Éviter les boucles infinies d'erreur
                try:
                    self.logger.error(f"Error in log worker: {e}")
                except:
                    print(f"Critical error in log worker: {e}")
    
    def _process_log_entry(self, log_entry: LogEntry):
        """Traite une entrée de log"""
        try:
            # Mettre à jour les statistiques
            self._update_stats(log_entry)
            
            # Logging vers les fichiers/console
            self._log_to_files(log_entry)
            
            # Logging vers la base de données
            if self.config.enable_database_logging:
                asyncio.create_task(self._log_to_database(log_entry))
            
            # Vérifier les alertes
            self._check_alerts(log_entry)
            
        except Exception as e:
            # Fallback logging
            try:
                self.logger.error(f"Error processing log entry: {e}")
            except:
                print(f"Critical error processing log entry: {e}")
    
    def _update_stats(self, log_entry: LogEntry):
        """Met à jour les statistiques"""
        self.stats['total_logs'] += 1
        self.stats['logs_by_level'][log_entry.level.value] += 1
        self.stats['logs_by_component'][log_entry.component.value] += 1
        self.stats['last_log_time'] = log_entry.timestamp
        
        # Ajouter aux logs récents pour les alertes
        now = time.time()
        self.recent_logs[log_entry.level].append(now)
        
        # Nettoyer les logs anciens (plus de 1 minute)
        cutoff = now - 60
        for level in LogLevel:
            self.recent_logs[level] = [t for t in self.recent_logs[level] if t > cutoff]
    
    def _log_to_files(self, log_entry: LogEntry):
        """Écrit le log dans les fichiers"""
        try:
            # Sélectionner le logger approprié
            component_logger = self.loggers.get(log_entry.component, self.logger)
            
            # Créer le message formaté
            message = self._format_log_message(log_entry)
            
            # Logger selon le niveau
            level_int = getattr(logging, log_entry.level.value)
            component_logger.log(level_int, message)
            
        except Exception as e:
            print(f"Error logging to files: {e}")
    
    async def _log_to_database(self, log_entry: LogEntry):
        """Écrit le log dans la base de données"""
        try:
            log_data = {
                'level': log_entry.level.value,
                'component': log_entry.component.value,
                'message': log_entry.message,
                'details': log_entry.details,
                'user_id': log_entry.user_id,
                'agent_id': log_entry.agent_id,
                'workflow_id': log_entry.workflow_id,
                'timestamp': log_entry.timestamp,
                'created_at': log_entry.timestamp
            }
            
            await supabase.client.table('system_logs').insert(log_data).execute()
            
        except Exception as e:
            # Éviter les boucles d'erreur
            try:
                self.logger.error(f"Error logging to database: {e}")
            except:
                print(f"Critical error logging to database: {e}")
    
    def _check_alerts(self, log_entry: LogEntry):
        """Vérifie les seuils d'alerte"""
        try:
            threshold = self.config.alert_thresholds.get(log_entry.level)
            if threshold is None:
                return
            
            recent_count = len(self.recent_logs[log_entry.level])
            
            if recent_count >= threshold:
                self._trigger_alert(log_entry.level, recent_count, threshold)
                
        except Exception as e:
            print(f"Error checking alerts: {e}")
    
    def _trigger_alert(self, level: LogLevel, count: int, threshold: int):
        """Déclenche une alerte"""
        try:
            alert_message = f"Alert: {count} {level.value} logs in the last minute (threshold: {threshold})"
            
            # Log l'alerte
            self.logger.critical(alert_message)
            
            # TODO: Envoyer l'alerte via webhook ou email
            
        except Exception as e:
            print(f"Error triggering alert: {e}")
    
    def _format_log_message(self, log_entry: LogEntry) -> str:
        """Formate un message de log"""
        parts = [log_entry.message]
        
        if log_entry.details:
            parts.append(f"Details: {json.dumps(log_entry.details)}")
        
        if log_entry.correlation_id:
            parts.append(f"CorrelationID: {log_entry.correlation_id}")
        
        if log_entry.user_id:
            parts.append(f"UserID: {log_entry.user_id}")
        
        if log_entry.agent_id:
            parts.append(f"AgentID: {log_entry.agent_id}")
        
        if log_entry.workflow_id:
            parts.append(f"WorkflowID: {log_entry.workflow_id}")
        
        if log_entry.task_id:
            parts.append(f"TaskID: {log_entry.task_id}")
        
        if log_entry.exception:
            parts.append(f"Exception: {log_entry.exception}")
        
        return " | ".join(parts)
    
    def log(self, 
            level: LogLevel, 
            component: LogComponent, 
            message: str, 
            details: Dict[str, Any] = None,
            **kwargs):
        """Méthode principale de logging"""
        
        if details is None:
            details = {}
        
        # Créer l'entrée de log
        log_entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level,
            component=component,
            message=message,
            details=details,
            **kwargs
        )
        
        # Ajouter à la queue
        try:
            self.log_queue.put(log_entry, timeout=1)
        except:
            # Si la queue est pleine, logger directement
            self._log_to_files(log_entry)
    
    def debug(self, component: LogComponent, message: str, **kwargs):
        """Log DEBUG"""
        self.log(LogLevel.DEBUG, component, message, **kwargs)
    
    def info(self, component: LogComponent, message: str, **kwargs):
        """Log INFO"""
        self.log(LogLevel.INFO, component, message, **kwargs)
    
    def warning(self, component: LogComponent, message: str, **kwargs):
        """Log WARNING"""
        self.log(LogLevel.WARNING, component, message, **kwargs)
    
    def error(self, component: LogComponent, message: str, exception: Exception = None, **kwargs):
        """Log ERROR"""
        details = kwargs.get('details', {})
        
        if exception:
            details['exception_type'] = type(exception).__name__
            details['exception_message'] = str(exception)
            kwargs['exception'] = str(exception)
            kwargs['stack_trace'] = traceback.format_exc()
        
        kwargs['details'] = details
        self.log(LogLevel.ERROR, component, message, **kwargs)
    
    def critical(self, component: LogComponent, message: str, exception: Exception = None, **kwargs):
        """Log CRITICAL"""
        details = kwargs.get('details', {})
        
        if exception:
            details['exception_type'] = type(exception).__name__
            details['exception_message'] = str(exception)
            kwargs['exception'] = str(exception)
            kwargs['stack_trace'] = traceback.format_exc()
        
        kwargs['details'] = details
        self.log(LogLevel.CRITICAL, component, message, **kwargs)
    
    @contextmanager
    def log_context(self, **context):
        """Context manager pour ajouter du contexte aux logs"""
        # TODO: Implémenter le contexte de logging
        yield
    
    def get_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques de logging"""
        return {
            **self.stats,
            'queue_size': self.log_queue.qsize(),
            'is_running': self.is_running,
            'recent_errors': len(self.recent_logs[LogLevel.ERROR]),
            'recent_criticals': len(self.recent_logs[LogLevel.CRITICAL]),
            'system_info': {
                'cpu_percent': psutil.cpu_percent(),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent
            }
        }
    
    async def get_recent_logs(self, 
                            component: LogComponent = None,
                            level: LogLevel = None,
                            limit: int = 100) -> List[Dict[str, Any]]:
        """Récupère les logs récents depuis la base"""
        try:
            query = supabase.client.table('system_logs').select('*')
            
            if component:
                query = query.eq('component', component.value)
            
            if level:
                query = query.eq('level', level.value)
            
            result = query.order('timestamp', desc=True).limit(limit).execute()
            
            return result.data
            
        except Exception as e:
            self.error(LogComponent.SYSTEM, f"Error getting recent logs: {e}", exception=e)
            return []
    
    def cleanup_old_logs(self, days: int = 30):
        """Nettoie les anciens logs"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            # Nettoyer les fichiers de log
            for log_file in self.config.log_files.values():
                if log_file.exists():
                    # Ici on pourrait implémenter une logique de nettoyage plus sophistiquée
                    pass
            
            # Nettoyer la base de données
            asyncio.create_task(self._cleanup_database_logs(cutoff_date))
            
            self.info(LogComponent.SYSTEM, f"Log cleanup completed for logs older than {days} days")
            
        except Exception as e:
            self.error(LogComponent.SYSTEM, f"Error cleaning up logs: {e}", exception=e)
    
    async def _cleanup_database_logs(self, cutoff_date: datetime):
        """Nettoie les logs de la base de données"""
        try:
            cutoff_str = cutoff_date.isoformat()
            
            result = await supabase.client.table('system_logs').delete().lt('timestamp', cutoff_str).execute()
            
            count = len(result.data) if result.data else 0
            self.info(LogComponent.SYSTEM, f"Cleaned up {count} old database logs")
            
        except Exception as e:
            self.error(LogComponent.SYSTEM, f"Error cleaning database logs: {e}", exception=e)

# Instance globale
logger = StructuredLogger()

# Fonctions utilitaires
def get_logger() -> StructuredLogger:
    """Récupère l'instance globale du logger"""
    return logger

def log_debug(component: LogComponent, message: str, **kwargs):
    """Log DEBUG rapide"""
    logger.debug(component, message, **kwargs)

def log_info(component: LogComponent, message: str, **kwargs):
    """Log INFO rapide"""
    logger.info(component, message, **kwargs)

def log_warning(component: LogComponent, message: str, **kwargs):
    """Log WARNING rapide"""
    logger.warning(component, message, **kwargs)

def log_error(component: LogComponent, message: str, exception: Exception = None, **kwargs):
    """Log ERROR rapide"""
    logger.error(component, message, exception=exception, **kwargs)

def log_critical(component: LogComponent, message: str, exception: Exception = None, **kwargs):
    """Log CRITICAL rapide"""
    logger.critical(component, message, exception=exception, **kwargs)

# Décorateur pour logger les appels de fonction
def log_function_call(component: LogComponent, level: LogLevel = LogLevel.DEBUG):
    """Décorateur pour logger les appels de fonction"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            logger.log(level, component, f"Calling {func.__name__}", details={
                'function': func.__name__,
                'args_count': len(args),
                'kwargs_count': len(kwargs)
            })
            
            try:
                result = func(*args, **kwargs)
                
                execution_time = time.time() - start_time
                logger.log(level, component, f"Function {func.__name__} completed", details={
                    'function': func.__name__,
                    'execution_time': execution_time,
                    'success': True
                })
                
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(component, f"Function {func.__name__} failed", exception=e, details={
                    'function': func.__name__,
                    'execution_time': execution_time,
                    'success': False
                })
                raise
        
        return wrapper
    return decorator

# Exemple d'utilisation
if __name__ == "__main__":
    # Test du système de logging
    print("🔍 Test du système de logging")
    print("=" * 40)
    
    # Logs de test
    logger.info(LogComponent.SYSTEM, "System started", details={"version": "1.0.0"})
    logger.debug(LogComponent.API, "API endpoint called", details={"endpoint": "/test"})
    logger.warning(LogComponent.CACHE, "Cache miss", details={"key": "test_key"})
    
    try:
        # Simuler une erreur
        raise ValueError("Test exception")
    except Exception as e:
        logger.error(LogComponent.TASK, "Task failed", exception=e, details={"task_id": "test-123"})
    
    # Attendre un peu
    time.sleep(2)
    
    # Afficher les stats
    stats = logger.get_stats()
    print(f"\nStatistiques: {json.dumps(stats, indent=2)}")
    
    # Arrêter le logger
    logger.stop()