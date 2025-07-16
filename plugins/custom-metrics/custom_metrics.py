#!/usr/bin/env python3
"""
Plugin Custom Metrics - Collecteur de métriques personnalisées
"""

import asyncio
import json
import time
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from collections import defaultdict, deque
import logging
import psutil
import threading

# Import du système de plugins
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'core'))

from plugin_system import MetricsPlugin, plugin_hook, requires_permission

logger = logging.getLogger(__name__)

class CustomMetricsCollector(MetricsPlugin):
    """Plugin de collecte de métriques personnalisées"""
    
    PLUGIN_NAME = "custom-metrics"
    PLUGIN_VERSION = "1.0.0"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.collection_interval = config.get('collection_interval', 30)
        self.metrics_retention = config.get('metrics_retention', 86400)  # 24h
        self.custom_metrics = config.get('custom_metrics', [])
        self.aggregation_window = config.get('aggregation_window', 300)  # 5 min
        self.alert_thresholds = config.get('alert_thresholds', {})
        
        # Stockage des métriques
        self.metrics_data: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.aggregated_metrics: Dict[str, Dict[str, float]] = defaultdict(dict)
        
        # Collecteurs personnalisés
        self.custom_collectors: Dict[str, Callable] = {}
        
        # Tâches asynchrones
        self.collection_task: Optional[asyncio.Task] = None
        self.aggregation_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        
        # Statistiques
        self.stats = {
            'collections_count': 0,
            'metrics_collected': 0,
            'alerts_triggered': 0,
            'last_collection': None,
            'collection_errors': 0,
            'active_metrics': set()
        }
        
        # Initialiser les collecteurs par défaut
        self._init_default_collectors()
    
    def _init_default_collectors(self):
        """Initialise les collecteurs de métriques par défaut"""
        
        self.custom_collectors.update({
            'system_cpu_percent': self._collect_cpu_percent,
            'system_memory_percent': self._collect_memory_percent,
            'system_disk_usage': self._collect_disk_usage,
            'system_network_io': self._collect_network_io,
            'process_count': self._collect_process_count,
            'load_average': self._collect_load_average,
            'python_memory_usage': self._collect_python_memory,
            'thread_count': self._collect_thread_count
        })
    
    async def initialize(self) -> bool:
        """Initialise le collecteur de métriques"""
        try:
            logger.info(f"📊 Initializing Custom Metrics Collector...")
            
            # Valider la configuration
            if self.collection_interval < 5:
                logger.warning("Collection interval too low, setting to 5 seconds")
                self.collection_interval = 5
            
            # Démarrer les tâches de collecte
            self.collection_task = asyncio.create_task(self._collection_loop())
            self.aggregation_task = asyncio.create_task(self._aggregation_loop())
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            # Première collecte
            await self._collect_all_metrics()
            
            self.is_initialized = True
            logger.info(f"✅ Custom Metrics Collector initialized")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Custom Metrics Collector: {e}")
            return False
    
    async def shutdown(self) -> bool:
        """Arrête le collecteur proprement"""
        logger.info("🛑 Shutting down Custom Metrics Collector...")
        
        # Arrêter les tâches
        if self.collection_task:
            self.collection_task.cancel()
        if self.aggregation_task:
            self.aggregation_task.cancel()
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        # Attendre l'arrêt des tâches
        tasks = [t for t in [self.collection_task, self.aggregation_task, self.cleanup_task] if t]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        return True
    
    async def _collection_loop(self):
        """Boucle principale de collecte des métriques"""
        while True:
            try:
                await self._collect_all_metrics()
                await asyncio.sleep(self.collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in collection loop: {e}")
                self.stats['collection_errors'] += 1
                await asyncio.sleep(self.collection_interval)
    
    async def _aggregation_loop(self):
        """Boucle d'agrégation des métriques"""
        while True:
            try:
                await self._aggregate_metrics()
                await asyncio.sleep(self.aggregation_window)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in aggregation loop: {e}")
                await asyncio.sleep(self.aggregation_window)
    
    async def _cleanup_loop(self):
        """Boucle de nettoyage des anciennes métriques"""
        while True:
            try:
                await self._cleanup_old_metrics()
                await asyncio.sleep(3600)  # Cleanup toutes les heures
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(3600)
    
    @requires_permission('system_monitoring')
    async def collect_metrics(self) -> Dict[str, Any]:
        """Collecte les métriques (interface du plugin)"""
        await self._collect_all_metrics()
        
        # Retourner les métriques récentes
        recent_metrics = {}
        for metric_name, data_points in self.metrics_data.items():
            if data_points:
                recent_metrics[metric_name] = {
                    'latest_value': data_points[-1]['value'],
                    'timestamp': data_points[-1]['timestamp'],
                    'count': len(data_points)
                }
        
        return recent_metrics
    
    async def process_metric(self, metric_name: str, value: Any, tags: Dict[str, str]):
        """Traite une métrique (interface du plugin)"""
        await self._record_metric(metric_name, value, tags)
    
    async def _collect_all_metrics(self):
        """Collecte toutes les métriques configurées"""
        timestamp = time.time()
        collected_count = 0
        
        # Collecter les métriques système par défaut
        for metric_name, collector in self.custom_collectors.items():
            try:
                value = await self._run_collector(collector)
                if value is not None:
                    await self._record_metric(metric_name, value, {'source': 'system'})
                    collected_count += 1
            except Exception as e:
                logger.error(f"Error collecting {metric_name}: {e}")
        
        # Collecter les métriques personnalisées configurées
        for metric_config in self.custom_metrics:
            try:
                await self._collect_custom_metric(metric_config)
                collected_count += 1
            except Exception as e:
                logger.error(f"Error collecting custom metric {metric_config}: {e}")
        
        # Mettre à jour les statistiques
        self.stats['collections_count'] += 1
        self.stats['metrics_collected'] += collected_count
        self.stats['last_collection'] = datetime.now().isoformat()
        
        logger.debug(f"📊 Collected {collected_count} metrics")
    
    async def _run_collector(self, collector: Callable) -> Any:
        """Exécute un collecteur de manière sécurisée"""
        if asyncio.iscoroutinefunction(collector):
            return await collector()
        else:
            # Exécuter dans un thread pour éviter de bloquer
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, collector)
    
    async def _record_metric(self, name: str, value: float, tags: Dict[str, str] = None):
        """Enregistre une métrique"""
        data_point = {
            'timestamp': time.time(),
            'value': float(value),
            'tags': tags or {}
        }
        
        self.metrics_data[name].append(data_point)
        self.stats['active_metrics'].add(name)
        
        # Vérifier les seuils d'alerte
        await self._check_alert_thresholds(name, value)
    
    async def _check_alert_thresholds(self, metric_name: str, value: float):
        """Vérifie les seuils d'alerte pour une métrique"""
        if metric_name in self.alert_thresholds:
            threshold_config = self.alert_thresholds[metric_name]
            
            if isinstance(threshold_config, dict):
                if 'max' in threshold_config and value > threshold_config['max']:
                    await self._trigger_alert(metric_name, value, 'max', threshold_config['max'])
                if 'min' in threshold_config and value < threshold_config['min']:
                    await self._trigger_alert(metric_name, value, 'min', threshold_config['min'])
            elif isinstance(threshold_config, (int, float)) and value > threshold_config:
                await self._trigger_alert(metric_name, value, 'max', threshold_config)
    
    async def _trigger_alert(self, metric_name: str, value: float, threshold_type: str, threshold: float):
        """Déclenche une alerte"""
        self.stats['alerts_triggered'] += 1
        
        alert_data = {
            'metric_name': metric_name,
            'current_value': value,
            'threshold_type': threshold_type,
            'threshold_value': threshold,
            'timestamp': time.time()
        }
        
        logger.warning(f"🚨 Alert: {metric_name} = {value} {threshold_type} threshold {threshold}")
        
        # Déclencher l'événement d'alerte pour les autres plugins
        # TODO: Intégrer avec le système d'événements
    
    async def _aggregate_metrics(self):
        """Agrège les métriques sur la fenêtre de temps"""
        cutoff_time = time.time() - self.aggregation_window
        
        for metric_name, data_points in self.metrics_data.items():
            # Filtrer les points de données dans la fenêtre
            recent_points = [
                dp for dp in data_points 
                if dp['timestamp'] > cutoff_time
            ]
            
            if recent_points:
                values = [dp['value'] for dp in recent_points]
                
                self.aggregated_metrics[metric_name] = {
                    'count': len(values),
                    'avg': statistics.mean(values),
                    'min': min(values),
                    'max': max(values),
                    'latest': values[-1],
                    'window_seconds': self.aggregation_window,
                    'timestamp': time.time()
                }
                
                if len(values) > 1:
                    self.aggregated_metrics[metric_name]['stddev'] = statistics.stdev(values)
                    
                if len(values) >= 3:
                    self.aggregated_metrics[metric_name]['median'] = statistics.median(values)
    
    async def _cleanup_old_metrics(self):
        """Nettoie les métriques anciennes"""
        cutoff_time = time.time() - self.metrics_retention
        cleaned_count = 0
        
        for metric_name in list(self.metrics_data.keys()):
            data_points = self.metrics_data[metric_name]
            original_length = len(data_points)
            
            # Filtrer les points anciens
            while data_points and data_points[0]['timestamp'] < cutoff_time:
                data_points.popleft()
                cleaned_count += 1
            
            # Supprimer la métrique si elle n'a plus de données
            if not data_points:
                del self.metrics_data[metric_name]
                if metric_name in self.stats['active_metrics']:
                    self.stats['active_metrics'].remove(metric_name)
        
        if cleaned_count > 0:
            logger.debug(f"🧹 Cleaned up {cleaned_count} old metric data points")
    
    async def _collect_custom_metric(self, metric_config: Dict[str, Any]):
        """Collecte une métrique personnalisée"""
        # TODO: Implémenter la collecte de métriques personnalisées
        # basée sur la configuration
        pass
    
    # Collecteurs système par défaut
    
    def _collect_cpu_percent(self) -> float:
        """Collecte le pourcentage d'utilisation CPU"""
        return psutil.cpu_percent(interval=0.1)
    
    def _collect_memory_percent(self) -> float:
        """Collecte le pourcentage d'utilisation mémoire"""
        return psutil.virtual_memory().percent
    
    def _collect_disk_usage(self) -> float:
        """Collecte l'utilisation disque"""
        return psutil.disk_usage('/').percent
    
    def _collect_network_io(self) -> Dict[str, float]:
        """Collecte les I/O réseau"""
        net_io = psutil.net_io_counters()
        return {
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv
        }
    
    def _collect_process_count(self) -> int:
        """Collecte le nombre de processus"""
        return len(psutil.pids())
    
    def _collect_load_average(self) -> List[float]:
        """Collecte la charge système (load average)"""
        try:
            return list(psutil.getloadavg())
        except AttributeError:
            # Windows n'a pas getloadavg
            return [0.0, 0.0, 0.0]
    
    def _collect_python_memory(self) -> float:
        """Collecte l'utilisation mémoire du processus Python"""
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024  # MB
    
    def _collect_thread_count(self) -> int:
        """Collecte le nombre de threads"""
        return threading.active_count()
    
    # API publique
    
    def register_custom_collector(self, name: str, collector: Callable):
        """Enregistre un collecteur personnalisé"""
        self.custom_collectors[name] = collector
        logger.info(f"📋 Registered custom collector: {name}")
    
    def unregister_custom_collector(self, name: str):
        """Désenregistre un collecteur personnalisé"""
        if name in self.custom_collectors:
            del self.custom_collectors[name]
            logger.info(f"🗑️ Unregistered custom collector: {name}")
    
    def get_metric_history(self, metric_name: str, since: Optional[float] = None) -> List[Dict[str, Any]]:
        """Récupère l'historique d'une métrique"""
        if metric_name not in self.metrics_data:
            return []
        
        data_points = self.metrics_data[metric_name]
        
        if since is not None:
            return [dp for dp in data_points if dp['timestamp'] >= since]
        else:
            return list(data_points)
    
    def get_aggregated_metric(self, metric_name: str) -> Optional[Dict[str, float]]:
        """Récupère les données agrégées d'une métrique"""
        return self.aggregated_metrics.get(metric_name)
    
    def get_all_metrics_summary(self) -> Dict[str, Any]:
        """Récupère un résumé de toutes les métriques"""
        summary = {}
        
        for metric_name in self.stats['active_metrics']:
            latest_data = None
            if metric_name in self.metrics_data and self.metrics_data[metric_name]:
                latest_data = self.metrics_data[metric_name][-1]
            
            aggregated_data = self.aggregated_metrics.get(metric_name)
            
            summary[metric_name] = {
                'latest': latest_data,
                'aggregated': aggregated_data,
                'data_points_count': len(self.metrics_data.get(metric_name, []))
            }
        
        return summary
    
    # Hooks
    
    @plugin_hook('system_status_check')
    async def on_system_status_check(self):
        """Hook pour les vérifications de statut système"""
        await self._collect_all_metrics()
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Retourne les métriques du plugin"""
        return {
            'plugin_metrics': {
                **self.stats,
                'active_metrics': list(self.stats['active_metrics'])
            },
            'config': {
                'collection_interval': self.collection_interval,
                'metrics_retention': self.metrics_retention,
                'aggregation_window': self.aggregation_window,
                'custom_metrics_count': len(self.custom_metrics),
                'collectors_count': len(self.custom_collectors)
            },
            'current_metrics_summary': self.get_all_metrics_summary()
        }
    
    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """Valide la configuration du plugin"""
        if 'collection_interval' in config and config['collection_interval'] < 1:
            logger.error("collection_interval must be at least 1 second")
            return False
        
        if 'metrics_retention' in config and config['metrics_retention'] < 60:
            logger.error("metrics_retention must be at least 60 seconds")
            return False
        
        if 'aggregation_window' in config and config['aggregation_window'] < 10:
            logger.error("aggregation_window must be at least 10 seconds")
            return False
        
        return True

# Point d'entrée du plugin
def create_plugin(config: Dict[str, Any] = None) -> CustomMetricsCollector:
    """Factory function pour créer une instance du plugin"""
    return CustomMetricsCollector(config)

# Export pour compatibilité
CustomMetricsPlugin = CustomMetricsCollector