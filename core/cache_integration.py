#!/usr/bin/env python3
"""
Master Plan IA 2025 - Cache Integration
Intégration du cache Redis avec les composants existants
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Callable
from functools import wraps
import logging

from redis_cache import RedisCache, CacheConfig, SerializationType, cached
from intelligent_coordinator import IntelligentCoordinator
from advanced_metrics import AdvancedMetricsSystem
from auto_scaler import AutoScaler

logger = logging.getLogger(__name__)

class CachedOrchestrationHub:
    """Extension de l'OrchestrationHub avec cache Redis"""
    
    def __init__(self, orchestration_hub, cache: RedisCache):
        self.hub = orchestration_hub
        self.cache = cache
        
        # Enregistrer les callbacks d'invalidation
        cache.register_invalidation_callback("agents", self._on_agent_invalidation)
        cache.register_invalidation_callback("workflows", self._on_workflow_invalidation)
    
    async def _on_agent_invalidation(self, key: str):
        """Callback quand un agent est invalidé dans le cache"""
        logger.info(f"Agent cache invalidated: {key}")
    
    async def _on_workflow_invalidation(self, key: str):
        """Callback quand un workflow est invalidé dans le cache"""
        logger.info(f"Workflow cache invalidated: {key}")
    
    async def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Récupère le statut d'un agent avec cache"""
        # Essayer le cache d'abord
        status = await self.cache.get("agents", f"status:{agent_id}")
        
        if status is not None:
            return status
        
        # Sinon, récupérer depuis le hub
        if hasattr(self.hub, 'get_agent_status'):
            status = await self.hub.get_agent_status(agent_id)
            
            # Stocker en cache
            if status:
                await self.cache.set("agents", f"status:{agent_id}", status, ttl=60)
            
            return status
        
        return None
    
    async def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Récupère le statut d'un workflow avec cache"""
        return await self.cache.get_or_set(
            "workflows",
            f"status:{workflow_id}",
            lambda: self.hub.get_workflow_status(workflow_id) if hasattr(self.hub, 'get_workflow_status') else None,
            ttl=300
        )
    
    async def list_agents(self) -> List[Dict[str, Any]]:
        """Liste tous les agents avec cache"""
        # Cache avec TTL court car la liste peut changer
        return await self.cache.get_or_set(
            "agents",
            "list:all",
            lambda: self._get_agents_list(),
            ttl=30
        )
    
    async def _get_agents_list(self) -> List[Dict[str, Any]]:
        """Récupère la liste des agents depuis le hub"""
        if not hasattr(self.hub, 'agents'):
            return []
        
        agents = []
        for agent_id, agent in self.hub.agents.items():
            agents.append({
                "id": agent.id,
                "name": agent.name,
                "type": str(agent.type),
                "is_healthy": agent.is_healthy,
                "load": agent.current_tasks / agent.max_concurrent_tasks
            })
        
        return agents

class CachedMetricsSystem:
    """Extension du système de métriques avec cache Redis"""
    
    def __init__(self, metrics_system: AdvancedMetricsSystem, cache: RedisCache):
        self.metrics = metrics_system
        self.cache = cache
        
        # Configuration du cache pour les métriques
        self.aggregation_cache_ttl = 300  # 5 minutes pour les agrégations
        self.raw_metrics_cache_ttl = 60   # 1 minute pour les métriques brutes
    
    async def get_metric_aggregation(self, 
                                   metric_name: str, 
                                   aggregation: str,
                                   window: int = 3600) -> Optional[float]:
        """Récupère une agrégation avec cache"""
        cache_key = f"agg:{metric_name}:{aggregation}:{window}"
        
        # Essayer le cache
        value = await self.cache.get("metrics", cache_key, SerializationType.JSON)
        
        if value is not None:
            return value
        
        # Calculer l'agrégation
        if hasattr(self.metrics, 'get_aggregation'):
            value = await self.metrics.get_aggregation(metric_name, aggregation, window)
            
            # Stocker en cache
            if value is not None:
                await self.cache.set(
                    "metrics", 
                    cache_key, 
                    value, 
                    ttl=self.aggregation_cache_ttl
                )
            
            return value
        
        return None
    
    async def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Récupère les métriques du dashboard avec cache"""
        return await self.cache.get_or_set(
            "metrics",
            "dashboard:summary",
            lambda: self.metrics.get_dashboard_data() if hasattr(self.metrics, 'get_dashboard_data') else {},
            ttl=30  # Rafraîchir toutes les 30 secondes
        )
    
    async def record_metric_cached(self, 
                                 metric_name: str, 
                                 value: float,
                                 tags: Dict[str, str] = None):
        """Enregistre une métrique avec mise en cache"""
        # Enregistrer dans le système de métriques
        if hasattr(self.metrics, 'record'):
            self.metrics.record(metric_name, value, tags)
        
        # Mettre à jour le cache
        cache_key = f"latest:{metric_name}"
        await self.cache.set(
            "metrics",
            cache_key,
            {
                "value": value,
                "timestamp": time.time(),
                "tags": tags or {}
            },
            ttl=self.raw_metrics_cache_ttl
        )
        
        # Incrémenter le compteur dans Redis
        await self.cache.increment("metrics", f"count:{metric_name}")
    
    async def get_time_series_cached(self,
                                   metric_name: str,
                                   start_time: float,
                                   end_time: float,
                                   interval: int = 60) -> List[Dict[str, Any]]:
        """Récupère une série temporelle avec cache"""
        cache_key = f"series:{metric_name}:{int(start_time)}:{int(end_time)}:{interval}"
        
        # Vérifier le cache
        series = await self.cache.get("metrics", cache_key, SerializationType.JSON)
        
        if series is not None:
            return series
        
        # Récupérer depuis le système de métriques
        if hasattr(self.metrics, 'get_time_series'):
            series = await self.metrics.get_time_series(
                metric_name, 
                interval, 
                since=start_time
            )
            
            # Calculer le TTL basé sur la fraîcheur des données
            data_age = time.time() - end_time
            if data_age > 3600:  # Données de plus d'1 heure
                ttl = 3600  # Cache pour 1 heure
            elif data_age > 300:  # Données de plus de 5 minutes
                ttl = 300   # Cache pour 5 minutes
            else:
                ttl = 60    # Cache pour 1 minute
            
            # Stocker en cache
            await self.cache.set("metrics", cache_key, series, ttl=ttl)
            
            return series
        
        return []

class CachedIntelligentCoordinator:
    """Extension du coordinateur intelligent avec cache Redis"""
    
    def __init__(self, coordinator: IntelligentCoordinator, cache: RedisCache):
        self.coordinator = coordinator
        self.cache = cache
        
        # TTL pour différents types de décisions
        self.strategy_cache_ttl = 600      # 10 minutes
        self.agent_selection_ttl = 300     # 5 minutes
        self.pattern_cache_ttl = 1800      # 30 minutes
    
    async def get_optimal_strategy(self, context: Dict[str, Any]) -> str:
        """Récupère la stratégie optimale avec cache"""
        # Créer une clé basée sur le contexte
        context_hash = hash(json.dumps(context, sort_keys=True, default=str))
        cache_key = f"strategy:optimal:{context_hash}"
        
        # Vérifier le cache
        strategy = await self.cache.get("intelligence", cache_key)
        
        if strategy is not None:
            return strategy
        
        # Calculer la stratégie
        if hasattr(self.coordinator, 'get_optimal_strategy'):
            strategy = await self.coordinator.get_optimal_strategy(context)
            
            # Stocker en cache
            await self.cache.set(
                "intelligence",
                cache_key,
                strategy,
                ttl=self.strategy_cache_ttl
            )
            
            return strategy
        
        return "hybrid"  # Stratégie par défaut
    
    async def select_agents_cached(self, 
                                 task_type: str, 
                                 required_capabilities: List[str]) -> List[str]:
        """Sélectionne les agents avec cache"""
        cache_key = f"agents:selection:{task_type}:{':'.join(sorted(required_capabilities))}"
        
        # Vérifier le cache
        agents = await self.cache.get("intelligence", cache_key)
        
        if agents is not None:
            return agents
        
        # Sélectionner les agents
        if hasattr(self.coordinator, 'intelligent_agent_selection'):
            agents = await self.coordinator.intelligent_agent_selection(
                {"type": task_type, "required_capabilities": required_capabilities},
                []  # Agents disponibles
            )
            
            # Stocker en cache
            await self.cache.set(
                "intelligence",
                cache_key,
                agents,
                ttl=self.agent_selection_ttl
            )
            
            return agents
        
        return []
    
    async def get_coordination_pattern(self, 
                                     pattern_type: str,
                                     agent_count: int) -> Dict[str, Any]:
        """Récupère un pattern de coordination avec cache"""
        cache_key = f"pattern:{pattern_type}:{agent_count}"
        
        return await self.cache.get_or_set(
            "intelligence",
            cache_key,
            lambda: self._calculate_pattern(pattern_type, agent_count),
            ttl=self.pattern_cache_ttl
        )
    
    async def _calculate_pattern(self, pattern_type: str, agent_count: int) -> Dict[str, Any]:
        """Calcule un pattern de coordination"""
        # Simuler le calcul d'un pattern
        patterns = {
            "pipeline": {
                "type": "pipeline",
                "stages": agent_count,
                "parallel": False,
                "timeout": 300
            },
            "parallel": {
                "type": "parallel",
                "workers": agent_count,
                "parallel": True,
                "timeout": 120
            },
            "hierarchical": {
                "type": "hierarchical",
                "levels": min(3, agent_count),
                "parallel": True,
                "timeout": 600
            }
        }
        
        return patterns.get(pattern_type, patterns["parallel"])

class CacheManager:
    """Gestionnaire central du cache pour tous les composants"""
    
    def __init__(self, config: CacheConfig = None):
        self.cache = RedisCache(config or CacheConfig())
        self.is_connected = False
        
        # Extensions cachées
        self.cached_hub = None
        self.cached_metrics = None
        self.cached_coordinator = None
        
        logger.info("🗄️ Cache Manager initialized")
    
    async def connect(self):
        """Connexion au cache Redis"""
        await self.cache.connect()
        self.is_connected = True
        logger.info("✅ Cache Manager connected")
    
    async def disconnect(self):
        """Déconnexion du cache"""
        await self.cache.disconnect()
        self.is_connected = False
        logger.info("🔌 Cache Manager disconnected")
    
    def wrap_orchestration_hub(self, hub):
        """Enveloppe l'OrchestrationHub avec le cache"""
        self.cached_hub = CachedOrchestrationHub(hub, self.cache)
        return self.cached_hub
    
    def wrap_metrics_system(self, metrics_system):
        """Enveloppe le système de métriques avec le cache"""
        self.cached_metrics = CachedMetricsSystem(metrics_system, self.cache)
        return self.cached_metrics
    
    def wrap_coordinator(self, coordinator):
        """Enveloppe le coordinateur avec le cache"""
        self.cached_coordinator = CachedIntelligentCoordinator(coordinator, self.cache)
        return self.cached_coordinator
    
    async def warm_up_cache(self):
        """Précharge le cache avec les données essentielles"""
        logger.info("🔥 Warming up cache...")
        
        tasks = []
        
        # Précharger la liste des agents
        if self.cached_hub:
            tasks.append(self.cached_hub.list_agents())
        
        # Précharger les métriques du dashboard
        if self.cached_metrics:
            tasks.append(self.cached_metrics.get_dashboard_metrics())
        
        # Précharger les patterns de coordination communs
        if self.cached_coordinator:
            for pattern in ["pipeline", "parallel", "hierarchical"]:
                for agents in [2, 3, 5]:
                    tasks.append(
                        self.cached_coordinator.get_coordination_pattern(pattern, agents)
                    )
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("✅ Cache warmed up")
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques du cache"""
        stats = await self.cache.get_stats()
        
        # Ajouter des métriques spécifiques
        namespace_stats = {}
        
        for namespace in ["agents", "workflows", "metrics", "intelligence"]:
            pattern = f"masterplan:{namespace}:*"
            # Compter les clés par namespace
            count = 0
            async for _ in self.cache.client.scan_iter(match=pattern):
                count += 1
            
            namespace_stats[namespace] = count
        
        stats["namespaces"] = namespace_stats
        
        return stats
    
    async def optimize_cache(self):
        """Optimise le cache en supprimant les données périmées"""
        logger.info("🔧 Optimizing cache...")
        
        # Nettoyer les métriques anciennes
        old_metrics_count = await self.cache.delete_pattern(
            "metrics",
            "series:*"
        )
        
        # Nettoyer les décisions d'intelligence anciennes
        old_intelligence_count = await self.cache.delete_pattern(
            "intelligence",
            "strategy:*"
        )
        
        logger.info(
            f"✅ Cache optimized: removed {old_metrics_count} old metrics, "
            f"{old_intelligence_count} old intelligence decisions"
        )
    
    def get_cache_health(self) -> Dict[str, Any]:
        """Vérifie la santé du cache"""
        return {
            "is_connected": self.cache.is_connected,
            "hit_rate": self.cache.stats.hit_rate,
            "errors": self.cache.stats.errors,
            "avg_get_time_ms": self.cache.stats.avg_get_time * 1000,
            "avg_set_time_ms": self.cache.stats.avg_set_time * 1000
        }

# Instance globale
cache_manager = CacheManager()

# Exemple d'utilisation
async def main():
    """Test de l'intégration du cache"""
    
    # Connexion
    await cache_manager.connect()
    
    try:
        # Simuler des composants
        class MockHub:
            agents = {"agent-1": type('Agent', (), {
                'id': 'agent-1',
                'name': 'Test Agent',
                'type': 'analyzer',
                'is_healthy': True,
                'current_tasks': 2,
                'max_concurrent_tasks': 5
            })}
            
            async def get_agent_status(self, agent_id):
                return {"id": agent_id, "status": "active"}
        
        # Wrapper le hub
        hub = MockHub()
        cached_hub = cache_manager.wrap_orchestration_hub(hub)
        
        # Tester le cache
        print("First call (cache miss):")
        start = time.time()
        agents = await cached_hub.list_agents()
        print(f"Time: {(time.time() - start) * 1000:.2f}ms")
        print(f"Agents: {agents}")
        
        print("\nSecond call (cache hit):")
        start = time.time()
        agents = await cached_hub.list_agents()
        print(f"Time: {(time.time() - start) * 1000:.2f}ms")
        print(f"Agents: {agents}")
        
        # Statistiques
        stats = await cache_manager.get_cache_stats()
        print(f"\nCache stats: {json.dumps(stats, indent=2)}")
        
    finally:
        await cache_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(main())