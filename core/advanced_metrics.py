#!/usr/bin/env python3
"""
Master Plan IA 2025 - Advanced Metrics System
Système de métriques avancées avec collecte temps réel et analytics
"""

import asyncio
import json
import time
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import defaultdict, deque
import statistics
import threading
from datetime import datetime, timedelta
import math
import numpy as np

logger = logging.getLogger(__name__)

class MetricType(Enum):
    """Types de métriques"""
    COUNTER = "counter"           # Compteur incrémental
    GAUGE = "gauge"              # Valeur instantanée
    HISTOGRAM = "histogram"       # Distribution de valeurs
    TIMER = "timer"              # Mesure de temps
    RATE = "rate"                # Taux par seconde
    PERCENTAGE = "percentage"     # Pourcentage

class MetricAggregation(Enum):
    """Types d'agrégation"""
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    PERCENTILE_95 = "p95"
    PERCENTILE_99 = "p99"
    MEDIAN = "median"

@dataclass
class MetricPoint:
    """Point de métrique individuel"""
    timestamp: float
    value: float
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MetricDefinition:
    """Définition d'une métrique"""
    name: str
    type: MetricType
    description: str
    unit: str = ""
    tags: List[str] = field(default_factory=list)
    aggregations: List[MetricAggregation] = field(default_factory=list)
    retention_hours: int = 24
    alert_thresholds: Dict[str, float] = field(default_factory=dict)

class MetricCollector:
    """Collecteur de métriques avec tampon circulaire"""
    
    def __init__(self, definition: MetricDefinition, buffer_size: int = 10000):
        self.definition = definition
        self.buffer = deque(maxlen=buffer_size)
        self.lock = threading.Lock()
        self.aggregated_cache = {}
        self.last_aggregation = 0
        self.cache_ttl = 60  # Cache pendant 1 minute
        
    def add_point(self, value: float, tags: Dict[str, str] = None, metadata: Dict[str, Any] = None):
        """Ajoute un point de métrique"""
        point = MetricPoint(
            timestamp=time.time(),
            value=value,
            tags=tags or {},
            metadata=metadata or {}
        )
        
        with self.lock:
            self.buffer.append(point)
            # Invalider le cache
            self.aggregated_cache.clear()
    
    def get_raw_data(self, since: Optional[float] = None, limit: Optional[int] = None) -> List[MetricPoint]:
        """Récupère les données brutes"""
        with self.lock:
            data = list(self.buffer)
        
        if since:
            data = [p for p in data if p.timestamp >= since]
        
        if limit:
            data = data[-limit:]
        
        return data
    
    def aggregate(self, 
                 aggregation: MetricAggregation,
                 since: Optional[float] = None,
                 group_by: Optional[str] = None) -> Dict[str, float]:
        """Agrège les données selon le type d'agrégation"""
        
        cache_key = f"{aggregation.value}_{since}_{group_by}"
        current_time = time.time()
        
        # Vérifier le cache
        if (cache_key in self.aggregated_cache and 
            current_time - self.last_aggregation < self.cache_ttl):
            return self.aggregated_cache[cache_key]
        
        data = self.get_raw_data(since=since)
        
        if not data:
            return {}
        
        # Grouper par tag si spécifié
        if group_by:
            groups = defaultdict(list)
            for point in data:
                key = point.tags.get(group_by, 'unknown')
                groups[key].append(point.value)
        else:
            groups = {'all': [point.value for point in data]}
        
        # Calculer l'agrégation
        result = {}
        for group_key, values in groups.items():
            if not values:
                continue
                
            if aggregation == MetricAggregation.SUM:
                result[group_key] = sum(values)
            elif aggregation == MetricAggregation.AVG:
                result[group_key] = statistics.mean(values)
            elif aggregation == MetricAggregation.MIN:
                result[group_key] = min(values)
            elif aggregation == MetricAggregation.MAX:
                result[group_key] = max(values)
            elif aggregation == MetricAggregation.COUNT:
                result[group_key] = len(values)
            elif aggregation == MetricAggregation.MEDIAN:
                result[group_key] = statistics.median(values)
            elif aggregation == MetricAggregation.PERCENTILE_95:
                result[group_key] = np.percentile(values, 95)
            elif aggregation == MetricAggregation.PERCENTILE_99:
                result[group_key] = np.percentile(values, 99)
        
        # Mettre en cache
        self.aggregated_cache[cache_key] = result
        self.last_aggregation = current_time
        
        return result
    
    def get_time_series(self, 
                       interval_seconds: int = 60,
                       since: Optional[float] = None,
                       aggregation: MetricAggregation = MetricAggregation.AVG) -> List[Dict[str, Any]]:
        """Génère une série temporelle avec intervalles"""
        
        data = self.get_raw_data(since=since)
        if not data:
            return []
        
        # Déterminer les bornes temporelles
        min_time = min(p.timestamp for p in data)
        max_time = max(p.timestamp for p in data)
        
        # Créer les intervalles
        intervals = []
        current_time = min_time
        
        while current_time <= max_time:
            interval_end = current_time + interval_seconds
            
            # Filtrer les données pour cet intervalle
            interval_data = [
                p for p in data 
                if current_time <= p.timestamp < interval_end
            ]
            
            if interval_data:
                values = [p.value for p in interval_data]
                
                if aggregation == MetricAggregation.AVG:
                    value = statistics.mean(values)
                elif aggregation == MetricAggregation.SUM:
                    value = sum(values)
                elif aggregation == MetricAggregation.MIN:
                    value = min(values)
                elif aggregation == MetricAggregation.MAX:
                    value = max(values)
                elif aggregation == MetricAggregation.COUNT:
                    value = len(values)
                else:
                    value = statistics.mean(values)
                
                intervals.append({
                    'timestamp': current_time,
                    'value': value,
                    'count': len(values)
                })
            
            current_time = interval_end
        
        return intervals

class AdvancedMetricsSystem:
    """Système de métriques avancées pour Master Plan IA 2025"""
    
    def __init__(self):
        self.collectors: Dict[str, MetricCollector] = {}
        self.definitions: Dict[str, MetricDefinition] = {}
        self.alert_callbacks: Dict[str, List[callable]] = defaultdict(list)
        self.auto_collection_tasks = []
        self.running = False
        
        # Métriques système prédéfinies
        self._setup_default_metrics()
        
        logger.info("📊 Advanced Metrics System initialized")
    
    def _setup_default_metrics(self):
        """Configure les métriques par défaut"""
        
        default_metrics = [
            # Métriques de performance
            MetricDefinition(
                name="task_execution_time",
                type=MetricType.TIMER,
                description="Temps d'exécution des tâches",
                unit="seconds",
                tags=["agent_id", "task_type", "pattern"],
                aggregations=[MetricAggregation.AVG, MetricAggregation.PERCENTILE_95],
                alert_thresholds={"high": 30.0, "critical": 60.0}
            ),
            
            MetricDefinition(
                name="task_success_rate",
                type=MetricType.PERCENTAGE,
                description="Taux de succès des tâches",
                unit="percent",
                tags=["agent_id", "task_type"],
                aggregations=[MetricAggregation.AVG],
                alert_thresholds={"low": 0.8, "critical": 0.6}
            ),
            
            MetricDefinition(
                name="agent_load",
                type=MetricType.GAUGE,
                description="Charge des agents",
                unit="percentage",
                tags=["agent_id"],
                aggregations=[MetricAggregation.AVG, MetricAggregation.MAX],
                alert_thresholds={"high": 0.8, "critical": 0.95}
            ),
            
            MetricDefinition(
                name="coordination_efficiency",
                type=MetricType.GAUGE,
                description="Efficacité de la coordination",
                unit="score",
                tags=["pattern", "agent_count"],
                aggregations=[MetricAggregation.AVG],
                alert_thresholds={"low": 0.7, "critical": 0.5}
            ),
            
            # Métriques de qualité
            MetricDefinition(
                name="output_quality",
                type=MetricType.GAUGE,
                description="Qualité des résultats",
                unit="score",
                tags=["agent_id", "task_type"],
                aggregations=[MetricAggregation.AVG, MetricAggregation.MIN],
                alert_thresholds={"low": 0.7, "critical": 0.5}
            ),
            
            # Métriques de coût
            MetricDefinition(
                name="task_cost",
                type=MetricType.GAUGE,
                description="Coût des tâches",
                unit="units",
                tags=["agent_id", "task_type"],
                aggregations=[MetricAggregation.SUM, MetricAggregation.AVG],
                alert_thresholds={"high": 1.0, "critical": 2.0}
            ),
            
            # Métriques de système
            MetricDefinition(
                name="active_workflows",
                type=MetricType.GAUGE,
                description="Nombre de workflows actifs",
                unit="count",
                tags=[],
                aggregations=[MetricAggregation.MAX, MetricAggregation.AVG],
                alert_thresholds={"high": 50, "critical": 100}
            ),
            
            MetricDefinition(
                name="api_requests",
                type=MetricType.COUNTER,
                description="Requêtes API",
                unit="requests",
                tags=["endpoint", "method", "status"],
                aggregations=[MetricAggregation.COUNT, MetricAggregation.SUM],
                alert_thresholds={"high": 1000, "critical": 5000}
            ),
            
            # Métriques d'intelligence
            MetricDefinition(
                name="learning_score",
                type=MetricType.GAUGE,
                description="Score d'apprentissage du système",
                unit="score",
                tags=["strategy", "mode"],
                aggregations=[MetricAggregation.AVG],
                alert_thresholds={"low": 0.6, "critical": 0.4}
            ),
            
            MetricDefinition(
                name="adaptation_events",
                type=MetricType.COUNTER,
                description="Événements d'adaptation",
                unit="events",
                tags=["type", "trigger"],
                aggregations=[MetricAggregation.COUNT],
                alert_thresholds={"high": 10, "critical": 50}
            )
        ]
        
        for metric_def in default_metrics:
            self.register_metric(metric_def)
    
    def register_metric(self, definition: MetricDefinition):
        """Enregistre une nouvelle métrique"""
        self.definitions[definition.name] = definition
        self.collectors[definition.name] = MetricCollector(definition)
        logger.info(f"📋 Metric registered: {definition.name}")
    
    def record(self, metric_name: str, value: float, tags: Dict[str, str] = None, metadata: Dict[str, Any] = None):
        """Enregistre une valeur de métrique"""
        if metric_name not in self.collectors:
            logger.warning(f"⚠️  Unknown metric: {metric_name}")
            return
        
        collector = self.collectors[metric_name]
        collector.add_point(value, tags, metadata)
        
        # Vérifier les alertes
        self._check_alerts(metric_name, value, tags or {})
    
    def _check_alerts(self, metric_name: str, value: float, tags: Dict[str, str]):
        """Vérifie les seuils d'alerte"""
        definition = self.definitions.get(metric_name)
        if not definition or not definition.alert_thresholds:
            return
        
        for threshold_name, threshold_value in definition.alert_thresholds.items():
            triggered = False
            
            if threshold_name in ["high", "critical"]:
                triggered = value > threshold_value
            elif threshold_name in ["low"]:
                triggered = value < threshold_value
            
            if triggered:
                alert_data = {
                    'metric': metric_name,
                    'value': value,
                    'threshold': threshold_value,
                    'threshold_type': threshold_name,
                    'tags': tags,
                    'timestamp': time.time()
                }
                
                # Appeler les callbacks d'alerte
                for callback in self.alert_callbacks.get(metric_name, []):
                    try:
                        callback(alert_data)
                    except Exception as e:
                        logger.error(f"Error in alert callback: {e}")
                
                logger.warning(f"🚨 Alert triggered: {metric_name} = {value} (threshold: {threshold_name} = {threshold_value})")
    
    def get_metric_data(self, 
                       metric_name: str,
                       since: Optional[float] = None,
                       aggregation: Optional[MetricAggregation] = None,
                       group_by: Optional[str] = None) -> Dict[str, Any]:
        """Récupère les données d'une métrique"""
        
        if metric_name not in self.collectors:
            return {"error": f"Unknown metric: {metric_name}"}
        
        collector = self.collectors[metric_name]
        
        result = {
            'metric': metric_name,
            'definition': {
                'type': collector.definition.type.value,
                'description': collector.definition.description,
                'unit': collector.definition.unit
            },
            'timestamp': time.time()
        }
        
        if aggregation:
            result['aggregated'] = collector.aggregate(aggregation, since, group_by)
        else:
            # Retourner toutes les agrégations configurées
            result['aggregated'] = {}
            for agg in collector.definition.aggregations:
                result['aggregated'][agg.value] = collector.aggregate(agg, since, group_by)
        
        # Ajouter les données brutes récentes
        raw_data = collector.get_raw_data(since=since, limit=100)
        result['recent_points'] = len(raw_data)
        result['latest_value'] = raw_data[-1].value if raw_data else None
        
        return result
    
    def get_time_series(self, 
                       metric_name: str,
                       interval_seconds: int = 60,
                       since: Optional[float] = None,
                       aggregation: MetricAggregation = MetricAggregation.AVG) -> List[Dict[str, Any]]:
        """Génère une série temporelle"""
        
        if metric_name not in self.collectors:
            return []
        
        collector = self.collectors[metric_name]
        return collector.get_time_series(interval_seconds, since, aggregation)
    
    def get_dashboard_data(self, since: Optional[float] = None) -> Dict[str, Any]:
        """Génère les données pour le dashboard"""
        
        if not since:
            since = time.time() - 3600  # Dernière heure
        
        dashboard = {
            'timestamp': time.time(),
            'period': 'last_hour',
            'metrics': {},
            'alerts': [],
            'summary': {}
        }
        
        # Métriques clés pour le dashboard
        key_metrics = [
            'task_execution_time',
            'task_success_rate',
            'agent_load',
            'coordination_efficiency',
            'output_quality',
            'active_workflows',
            'api_requests',
            'learning_score'
        ]
        
        for metric_name in key_metrics:
            if metric_name in self.collectors:
                metric_data = self.get_metric_data(metric_name, since=since)
                dashboard['metrics'][metric_name] = metric_data
        
        # Calculer le résumé
        dashboard['summary'] = self._calculate_summary(dashboard['metrics'])
        
        return dashboard
    
    def _calculate_summary(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Calcule un résumé des métriques"""
        summary = {
            'overall_health': 'healthy',
            'performance_score': 0.8,
            'efficiency_score': 0.85,
            'quality_score': 0.9,
            'issues': [],
            'recommendations': []
        }
        
        # Analyser la charge des agents
        if 'agent_load' in metrics:
            load_data = metrics['agent_load'].get('aggregated', {})
            avg_load = load_data.get('avg', {}).get('all', 0)
            
            if avg_load > 0.9:
                summary['overall_health'] = 'critical'
                summary['issues'].append("High system load detected")
                summary['recommendations'].append("Consider scaling up agents")
            elif avg_load > 0.7:
                summary['overall_health'] = 'warning'
                summary['issues'].append("Moderate system load")
        
        # Analyser le taux de succès
        if 'task_success_rate' in metrics:
            success_data = metrics['task_success_rate'].get('aggregated', {})
            avg_success = success_data.get('avg', {}).get('all', 0)
            
            if avg_success < 0.7:
                summary['overall_health'] = 'critical'
                summary['issues'].append("Low task success rate")
                summary['recommendations'].append("Review agent configurations")
            elif avg_success < 0.85:
                summary['overall_health'] = 'warning'
        
        # Analyser la qualité
        if 'output_quality' in metrics:
            quality_data = metrics['output_quality'].get('aggregated', {})
            avg_quality = quality_data.get('avg', {}).get('all', 0)
            summary['quality_score'] = avg_quality
            
            if avg_quality < 0.6:
                summary['overall_health'] = 'critical'
                summary['issues'].append("Low output quality")
                summary['recommendations'].append("Review quality control measures")
        
        return summary
    
    def add_alert_callback(self, metric_name: str, callback: callable):
        """Ajoute un callback d'alerte"""
        self.alert_callbacks[metric_name].append(callback)
    
    def start_auto_collection(self):
        """Démarre la collecte automatique"""
        self.running = True
        
        # Tâche de collecte des métriques système
        async def collect_system_metrics():
            while self.running:
                try:
                    # Collecter les métriques système
                    await self._collect_system_metrics()
                    await asyncio.sleep(30)  # Toutes les 30 secondes
                except Exception as e:
                    logger.error(f"Error in system metrics collection: {e}")
                    await asyncio.sleep(30)
        
        # Tâche de nettoyage
        async def cleanup_old_data():
            while self.running:
                try:
                    await self._cleanup_old_data()
                    await asyncio.sleep(3600)  # Toutes les heures
                except Exception as e:
                    logger.error(f"Error in cleanup: {e}")
                    await asyncio.sleep(3600)
        
        self.auto_collection_tasks = [
            asyncio.create_task(collect_system_metrics()),
            asyncio.create_task(cleanup_old_data())
        ]
        
        logger.info("🚀 Auto-collection started")
    
    async def _collect_system_metrics(self):
        """Collecte les métriques système"""
        import psutil
        import os
        
        # Métriques système
        self.record("system_cpu_usage", psutil.cpu_percent(), {"host": "localhost"})
        self.record("system_memory_usage", psutil.virtual_memory().percent, {"host": "localhost"})
        self.record("system_disk_usage", psutil.disk_usage('/').percent, {"host": "localhost"})
        
        # Métriques de processus
        process = psutil.Process(os.getpid())
        self.record("process_cpu_usage", process.cpu_percent(), {"process": "master-plan"})
        self.record("process_memory_usage", process.memory_percent(), {"process": "master-plan"})
        
        # Métriques des collecteurs
        for metric_name, collector in self.collectors.items():
            buffer_usage = len(collector.buffer) / collector.buffer.maxlen
            self.record("collector_buffer_usage", buffer_usage, {"metric": metric_name})
    
    async def _cleanup_old_data(self):
        """Nettoie les anciennes données"""
        current_time = time.time()
        
        for collector in self.collectors.values():
            retention_seconds = collector.definition.retention_hours * 3600
            cutoff_time = current_time - retention_seconds
            
            # Supprimer les points anciens
            with collector.lock:
                original_size = len(collector.buffer)
                collector.buffer = deque(
                    (p for p in collector.buffer if p.timestamp > cutoff_time),
                    maxlen=collector.buffer.maxlen
                )
                cleaned = original_size - len(collector.buffer)
                
                if cleaned > 0:
                    logger.info(f"🧹 Cleaned {cleaned} old points from {collector.definition.name}")
    
    def stop_auto_collection(self):
        """Arrête la collecte automatique"""
        self.running = False
        
        for task in self.auto_collection_tasks:
            task.cancel()
        
        self.auto_collection_tasks.clear()
        logger.info("🛑 Auto-collection stopped")

# Instance globale
metrics_system = AdvancedMetricsSystem()

# Fonctions utilitaires
def record_metric(name: str, value: float, tags: Dict[str, str] = None, metadata: Dict[str, Any] = None):
    """Enregistre une métrique (fonction utilitaire)"""
    metrics_system.record(name, value, tags, metadata)

def get_metrics_dashboard() -> Dict[str, Any]:
    """Retourne les données du dashboard"""
    return metrics_system.get_dashboard_data()

# Décorateurs pour l'instrumentation automatique
def instrument_function(metric_name: str, tags: Dict[str, str] = None):
    """Décorateur pour instrumenter une fonction"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                success = True
                error = None
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                execution_time = time.time() - start_time
                metric_tags = (tags or {}).copy()
                metric_tags.update({
                    'function': func.__name__,
                    'success': str(success)
                })
                
                record_metric(metric_name, execution_time, metric_tags, {
                    'error': error,
                    'args_count': len(args),
                    'kwargs_count': len(kwargs)
                })
            
            return result
        
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                success = True
                error = None
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                execution_time = time.time() - start_time
                metric_tags = (tags or {}).copy()
                metric_tags.update({
                    'function': func.__name__,
                    'success': str(success)
                })
                
                record_metric(metric_name, execution_time, metric_tags, {
                    'error': error,
                    'args_count': len(args),
                    'kwargs_count': len(kwargs)
                })
            
            return result
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator

# Exemple d'utilisation
if __name__ == "__main__":
    async def test_metrics():
        # Démarrer la collecte automatique
        metrics_system.start_auto_collection()
        
        # Enregistrer quelques métriques
        record_metric("task_execution_time", 2.5, {"agent_id": "agent-1", "task_type": "analysis"})
        record_metric("task_success_rate", 0.95, {"agent_id": "agent-1"})
        record_metric("agent_load", 0.7, {"agent_id": "agent-1"})
        
        # Attendre un peu
        await asyncio.sleep(2)
        
        # Récupérer les données du dashboard
        dashboard = get_metrics_dashboard()
        print(json.dumps(dashboard, indent=2))
        
        # Arrêter la collecte
        metrics_system.stop_auto_collection()
    
    asyncio.run(test_metrics())