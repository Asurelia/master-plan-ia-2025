#!/usr/bin/env python3
"""
Master Plan IA 2025 - Auto Scaler
Système d'auto-scaling intelligent pour les agents
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
import math
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ScalingAction(Enum):
    """Actions de scaling"""
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    MAINTAIN = "maintain"
    REDISTRIBUTE = "redistribute"

class ScalingTrigger(Enum):
    """Déclencheurs de scaling"""
    LOAD_THRESHOLD = "load_threshold"
    RESPONSE_TIME = "response_time"
    QUEUE_SIZE = "queue_size"
    ERROR_RATE = "error_rate"
    PREDICTIVE = "predictive"
    MANUAL = "manual"

class ScalingPolicy(Enum):
    """Politiques de scaling"""
    CONSERVATIVE = "conservative"    # Scaling prudent
    AGGRESSIVE = "aggressive"       # Scaling rapide
    PREDICTIVE = "predictive"       # Basé sur les prédictions
    COST_OPTIMIZED = "cost_optimized"  # Optimisé pour les coûts
    PERFORMANCE_FIRST = "performance_first"  # Performance avant tout

@dataclass
class ScalingMetrics:
    """Métriques pour le scaling"""
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    task_queue_size: int = 0
    avg_response_time: float = 0.0
    error_rate: float = 0.0
    throughput: float = 0.0
    success_rate: float = 1.0
    cost_per_hour: float = 0.0
    
    @property
    def load_score(self) -> float:
        """Score de charge combiné"""
        return (self.cpu_usage + self.memory_usage) / 2
    
    @property
    def performance_score(self) -> float:
        """Score de performance"""
        return (self.success_rate * 0.6 + 
                (1 - min(self.error_rate, 1.0)) * 0.3 + 
                min(10 / max(self.avg_response_time, 0.1), 1.0) * 0.1)

@dataclass
class ScalingEvent:
    """Événement de scaling"""
    timestamp: float
    agent_id: str
    action: ScalingAction
    trigger: ScalingTrigger
    reason: str
    metrics_before: ScalingMetrics
    metrics_after: Optional[ScalingMetrics] = None
    success: bool = True
    cost_impact: float = 0.0

@dataclass
class AgentScalingConfig:
    """Configuration de scaling pour un agent"""
    agent_id: str
    min_instances: int = 1
    max_instances: int = 10
    target_cpu: float = 0.7
    target_memory: float = 0.8
    scale_up_threshold: float = 0.8
    scale_down_threshold: float = 0.3
    max_response_time: float = 5.0
    max_error_rate: float = 0.1
    cooldown_period: int = 300  # 5 minutes
    scale_up_increment: int = 1
    scale_down_increment: int = 1
    cost_per_instance: float = 0.1
    
class PredictiveModel:
    """Modèle prédictif simple pour le scaling"""
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.history: deque = deque(maxlen=window_size)
        self.patterns: Dict[str, List[float]] = defaultdict(list)
        
    def add_observation(self, timestamp: float, load: float, metadata: Dict[str, Any] = None):
        """Ajoute une observation"""
        self.history.append({
            'timestamp': timestamp,
            'load': load,
            'metadata': metadata or {}
        })
        
        # Identifier des patterns temporels
        hour = datetime.fromtimestamp(timestamp).hour
        day_of_week = datetime.fromtimestamp(timestamp).weekday()
        
        self.patterns[f"hour_{hour}"].append(load)
        self.patterns[f"day_{day_of_week}"].append(load)
        
    def predict_load(self, future_minutes: int = 30) -> float:
        """Prédit la charge future"""
        if len(self.history) < 10:
            return 0.5  # Valeur par défaut
        
        # Tendance récente
        recent_loads = [obs['load'] for obs in list(self.history)[-10:]]
        if len(recent_loads) >= 2:
            trend = (recent_loads[-1] - recent_loads[0]) / len(recent_loads)
        else:
            trend = 0
        
        # Pattern temporel
        current_time = time.time()
        future_time = current_time + (future_minutes * 60)
        future_hour = datetime.fromtimestamp(future_time).hour
        
        historical_avg = statistics.mean(recent_loads)
        
        # Moyenne historique pour cette heure
        if f"hour_{future_hour}" in self.patterns:
            hour_pattern = statistics.mean(self.patterns[f"hour_{future_hour}"])
            historical_avg = (historical_avg + hour_pattern) / 2
        
        # Appliquer la tendance
        predicted_load = historical_avg + (trend * future_minutes)
        
        return max(0, min(1, predicted_load))
    
    def get_confidence(self) -> float:
        """Retourne la confiance de la prédiction"""
        if len(self.history) < 20:
            return 0.3
        
        # Calculer la variance récente
        recent_loads = [obs['load'] for obs in list(self.history)[-20:]]
        variance = statistics.variance(recent_loads)
        
        # Plus la variance est faible, plus la confiance est élevée
        confidence = max(0.1, min(0.9, 1 - variance))
        
        return confidence

class AutoScaler:
    """Système d'auto-scaling intelligent"""
    
    def __init__(self, orchestration_hub=None):
        self.orchestration_hub = orchestration_hub
        self.scaling_configs: Dict[str, AgentScalingConfig] = {}
        self.scaling_history: deque = deque(maxlen=1000)
        self.predictive_models: Dict[str, PredictiveModel] = {}
        self.current_metrics: Dict[str, ScalingMetrics] = {}
        self.last_scaling_actions: Dict[str, float] = {}
        self.policy = ScalingPolicy.CONSERVATIVE
        self.is_running = False
        self.scaling_tasks = []
        
        # Configuration globale
        self.global_config = {
            'check_interval': 30,  # Vérification toutes les 30 secondes
            'prediction_window': 30,  # Prédiction 30 minutes à l'avance
            'min_confidence': 0.7,  # Confiance minimale pour scaling prédictif
            'max_cost_per_hour': 10.0,  # Coût maximum par heure
            'enable_predictive': True,
            'enable_cost_optimization': True
        }
        
        logger.info("🔄 Auto Scaler initialized")
    
    def register_agent(self, agent_id: str, config: AgentScalingConfig = None):
        """Enregistre un agent pour l'auto-scaling"""
        if not config:
            config = AgentScalingConfig(agent_id=agent_id)
        
        self.scaling_configs[agent_id] = config
        self.predictive_models[agent_id] = PredictiveModel()
        self.current_metrics[agent_id] = ScalingMetrics()
        
        logger.info(f"📋 Agent registered for scaling: {agent_id}")
    
    def update_agent_metrics(self, agent_id: str, metrics: ScalingMetrics):
        """Met à jour les métriques d'un agent"""
        if agent_id not in self.scaling_configs:
            return
        
        self.current_metrics[agent_id] = metrics
        
        # Alimenter le modèle prédictif
        if agent_id in self.predictive_models:
            self.predictive_models[agent_id].add_observation(
                time.time(),
                metrics.load_score,
                {
                    'response_time': metrics.avg_response_time,
                    'error_rate': metrics.error_rate,
                    'throughput': metrics.throughput
                }
            )
    
    async def start_auto_scaling(self):
        """Démarre l'auto-scaling"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # Tâche principale de scaling
        async def scaling_loop():
            while self.is_running:
                try:
                    await self._check_and_scale_all_agents()
                    await asyncio.sleep(self.global_config['check_interval'])
                except Exception as e:
                    logger.error(f"Error in scaling loop: {e}")
                    await asyncio.sleep(self.global_config['check_interval'])
        
        # Tâche de prédiction
        async def prediction_loop():
            while self.is_running:
                try:
                    if self.global_config['enable_predictive']:
                        await self._predictive_scaling()
                    await asyncio.sleep(300)  # Toutes les 5 minutes
                except Exception as e:
                    logger.error(f"Error in prediction loop: {e}")
                    await asyncio.sleep(300)
        
        # Tâche d'optimisation des coûts
        async def cost_optimization_loop():
            while self.is_running:
                try:
                    if self.global_config['enable_cost_optimization']:
                        await self._optimize_costs()
                    await asyncio.sleep(600)  # Toutes les 10 minutes
                except Exception as e:
                    logger.error(f"Error in cost optimization: {e}")
                    await asyncio.sleep(600)
        
        self.scaling_tasks = [
            asyncio.create_task(scaling_loop()),
            asyncio.create_task(prediction_loop()),
            asyncio.create_task(cost_optimization_loop())
        ]
        
        logger.info("🚀 Auto-scaling started")
    
    async def stop_auto_scaling(self):
        """Arrête l'auto-scaling"""
        self.is_running = False
        
        for task in self.scaling_tasks:
            task.cancel()
        
        # Attendre que les tâches se terminent
        await asyncio.gather(*self.scaling_tasks, return_exceptions=True)
        
        self.scaling_tasks.clear()
        logger.info("🛑 Auto-scaling stopped")
    
    async def _check_and_scale_all_agents(self):
        """Vérifie et scale tous les agents"""
        for agent_id in self.scaling_configs:
            await self._check_and_scale_agent(agent_id)
    
    async def _check_and_scale_agent(self, agent_id: str):
        """Vérifie et scale un agent spécifique"""
        if agent_id not in self.scaling_configs:
            return
        
        config = self.scaling_configs[agent_id]
        metrics = self.current_metrics.get(agent_id, ScalingMetrics())
        
        # Vérifier le cooldown
        last_action = self.last_scaling_actions.get(agent_id, 0)
        if time.time() - last_action < config.cooldown_period:
            return
        
        # Déterminer l'action de scaling
        action, trigger, reason = await self._determine_scaling_action(agent_id, config, metrics)
        
        if action != ScalingAction.MAINTAIN:
            await self._execute_scaling_action(agent_id, action, trigger, reason, metrics)
    
    async def _determine_scaling_action(self, 
                                      agent_id: str, 
                                      config: AgentScalingConfig, 
                                      metrics: ScalingMetrics) -> Tuple[ScalingAction, ScalingTrigger, str]:
        """Détermine l'action de scaling nécessaire"""
        
        # Obtenir le nombre d'instances actuelles
        current_instances = await self._get_current_instances(agent_id)
        
        # Vérifications de seuils
        if metrics.load_score > config.scale_up_threshold:
            if current_instances < config.max_instances:
                return ScalingAction.SCALE_UP, ScalingTrigger.LOAD_THRESHOLD, f"Load {metrics.load_score:.2f} > {config.scale_up_threshold}"
        
        elif metrics.load_score < config.scale_down_threshold:
            if current_instances > config.min_instances:
                return ScalingAction.SCALE_DOWN, ScalingTrigger.LOAD_THRESHOLD, f"Load {metrics.load_score:.2f} < {config.scale_down_threshold}"
        
        # Vérifications de performance
        if metrics.avg_response_time > config.max_response_time:
            if current_instances < config.max_instances:
                return ScalingAction.SCALE_UP, ScalingTrigger.RESPONSE_TIME, f"Response time {metrics.avg_response_time:.2f}s > {config.max_response_time}s"
        
        if metrics.error_rate > config.max_error_rate:
            if current_instances < config.max_instances:
                return ScalingAction.SCALE_UP, ScalingTrigger.ERROR_RATE, f"Error rate {metrics.error_rate:.2f} > {config.max_error_rate}"
        
        # Vérifications de queue
        if metrics.task_queue_size > 10:  # Seuil arbitraire
            if current_instances < config.max_instances:
                return ScalingAction.SCALE_UP, ScalingTrigger.QUEUE_SIZE, f"Queue size {metrics.task_queue_size} > 10"
        
        return ScalingAction.MAINTAIN, ScalingTrigger.LOAD_THRESHOLD, "All metrics within acceptable range"
    
    async def _predictive_scaling(self):
        """Scaling prédictif basé sur les patterns"""
        for agent_id, model in self.predictive_models.items():
            if agent_id not in self.scaling_configs:
                continue
            
            config = self.scaling_configs[agent_id]
            confidence = model.get_confidence()
            
            if confidence < self.global_config['min_confidence']:
                continue
            
            # Prédire la charge future
            predicted_load = model.predict_load(self.global_config['prediction_window'])
            current_instances = await self._get_current_instances(agent_id)
            
            # Décider du scaling prédictif
            if predicted_load > config.scale_up_threshold:
                if current_instances < config.max_instances:
                    await self._execute_scaling_action(
                        agent_id, 
                        ScalingAction.SCALE_UP, 
                        ScalingTrigger.PREDICTIVE,
                        f"Predicted load {predicted_load:.2f} (confidence: {confidence:.2f})",
                        ScalingMetrics(cpu_usage=predicted_load, memory_usage=predicted_load)
                    )
            
            elif predicted_load < config.scale_down_threshold:
                if current_instances > config.min_instances:
                    await self._execute_scaling_action(
                        agent_id, 
                        ScalingAction.SCALE_DOWN, 
                        ScalingTrigger.PREDICTIVE,
                        f"Predicted load {predicted_load:.2f} (confidence: {confidence:.2f})",
                        ScalingMetrics(cpu_usage=predicted_load, memory_usage=predicted_load)
                    )
    
    async def _optimize_costs(self):
        """Optimise les coûts en arrêtant les instances sous-utilisées"""
        total_cost = 0
        optimizations = []
        
        for agent_id, config in self.scaling_configs.items():
            current_instances = await self._get_current_instances(agent_id)
            metrics = self.current_metrics.get(agent_id, ScalingMetrics())
            
            instance_cost = config.cost_per_instance * current_instances
            total_cost += instance_cost
            
            # Si l'utilisation est faible depuis longtemps, proposer une optimisation
            if (metrics.load_score < 0.2 and 
                current_instances > config.min_instances and
                metrics.avg_response_time < config.max_response_time * 0.5):
                
                optimizations.append({
                    'agent_id': agent_id,
                    'current_instances': current_instances,
                    'suggested_instances': max(config.min_instances, current_instances - 1),
                    'cost_savings': config.cost_per_instance,
                    'load': metrics.load_score
                })
        
        # Appliquer les optimisations si le coût total est trop élevé
        if total_cost > self.global_config['max_cost_per_hour']:
            for optimization in optimizations:
                await self._execute_scaling_action(
                    optimization['agent_id'],
                    ScalingAction.SCALE_DOWN,
                    ScalingTrigger.LOAD_THRESHOLD,
                    f"Cost optimization: {optimization['cost_savings']:.2f} savings",
                    self.current_metrics.get(optimization['agent_id'], ScalingMetrics())
                )
    
    async def _execute_scaling_action(self, 
                                    agent_id: str, 
                                    action: ScalingAction, 
                                    trigger: ScalingTrigger,
                                    reason: str, 
                                    metrics: ScalingMetrics):
        """Exécute une action de scaling"""
        config = self.scaling_configs[agent_id]
        
        try:
            # Enregistrer l'action
            scaling_event = ScalingEvent(
                timestamp=time.time(),
                agent_id=agent_id,
                action=action,
                trigger=trigger,
                reason=reason,
                metrics_before=metrics
            )
            
            # Exécuter l'action
            if action == ScalingAction.SCALE_UP:
                success = await self._scale_up_agent(agent_id, config.scale_up_increment)
                scaling_event.cost_impact = config.cost_per_instance * config.scale_up_increment
                
            elif action == ScalingAction.SCALE_DOWN:
                success = await self._scale_down_agent(agent_id, config.scale_down_increment)
                scaling_event.cost_impact = -config.cost_per_instance * config.scale_down_increment
                
            else:
                success = True
            
            scaling_event.success = success
            
            if success:
                self.last_scaling_actions[agent_id] = time.time()
                logger.info(f"✅ Scaling action executed: {agent_id} {action.value} - {reason}")
            else:
                logger.error(f"❌ Scaling action failed: {agent_id} {action.value} - {reason}")
            
            # Enregistrer l'événement
            self.scaling_history.append(scaling_event)
            
        except Exception as e:
            logger.error(f"Error executing scaling action: {e}")
            scaling_event.success = False
            self.scaling_history.append(scaling_event)
    
    async def _get_current_instances(self, agent_id: str) -> int:
        """Récupère le nombre d'instances actuelles"""
        if self.orchestration_hub and hasattr(self.orchestration_hub, 'agents'):
            if agent_id in self.orchestration_hub.agents:
                # Simuler le nombre d'instances basé sur la charge
                agent = self.orchestration_hub.agents[agent_id]
                load_factor = agent.current_tasks / agent.max_concurrent_tasks
                return max(1, min(5, int(load_factor * 3) + 1))
        
        return 1  # Fallback
    
    async def _scale_up_agent(self, agent_id: str, increment: int) -> bool:
        """Scale up un agent"""
        try:
            # Simuler le scaling up
            await asyncio.sleep(0.1)
            
            # Dans un vrai système, on créerait de nouvelles instances
            # ici on simule juste
            logger.info(f"🔺 Scaling up {agent_id} by {increment} instances")
            
            return True
        except Exception as e:
            logger.error(f"Failed to scale up {agent_id}: {e}")
            return False
    
    async def _scale_down_agent(self, agent_id: str, increment: int) -> bool:
        """Scale down un agent"""
        try:
            # Simuler le scaling down
            await asyncio.sleep(0.1)
            
            # Dans un vrai système, on arrêterait des instances
            # ici on simule juste
            logger.info(f"🔻 Scaling down {agent_id} by {increment} instances")
            
            return True
        except Exception as e:
            logger.error(f"Failed to scale down {agent_id}: {e}")
            return False
    
    async def manual_scale(self, agent_id: str, action: ScalingAction, instances: int = 1) -> bool:
        """Scaling manuel"""
        if agent_id not in self.scaling_configs:
            return False
        
        metrics = self.current_metrics.get(agent_id, ScalingMetrics())
        
        await self._execute_scaling_action(
            agent_id, 
            action, 
            ScalingTrigger.MANUAL,
            f"Manual scaling: {instances} instances",
            metrics
        )
        
        return True
    
    def get_scaling_status(self) -> Dict[str, Any]:
        """Retourne le statut du scaling"""
        status = {
            'is_running': self.is_running,
            'policy': self.policy.value,
            'config': self.global_config,
            'agents': {},
            'recent_events': [],
            'statistics': {
                'total_scale_ups': 0,
                'total_scale_downs': 0,
                'success_rate': 0,
                'avg_response_time': 0,
                'total_cost_savings': 0
            }
        }
        
        # Statut des agents
        for agent_id, config in self.scaling_configs.items():
            metrics = self.current_metrics.get(agent_id, ScalingMetrics())
            status['agents'][agent_id] = {
                'config': {
                    'min_instances': config.min_instances,
                    'max_instances': config.max_instances,
                    'current_instances': asyncio.create_task(self._get_current_instances(agent_id)),
                    'cost_per_instance': config.cost_per_instance
                },
                'metrics': {
                    'load_score': metrics.load_score,
                    'response_time': metrics.avg_response_time,
                    'error_rate': metrics.error_rate,
                    'throughput': metrics.throughput
                },
                'prediction': {
                    'confidence': self.predictive_models[agent_id].get_confidence(),
                    'predicted_load': self.predictive_models[agent_id].predict_load()
                }
            }
        
        # Événements récents
        recent_events = list(self.scaling_history)[-10:]
        for event in recent_events:
            status['recent_events'].append({
                'timestamp': event.timestamp,
                'agent_id': event.agent_id,
                'action': event.action.value,
                'trigger': event.trigger.value,
                'reason': event.reason,
                'success': event.success,
                'cost_impact': event.cost_impact
            })
        
        # Statistiques
        if self.scaling_history:
            successful_events = [e for e in self.scaling_history if e.success]
            scale_ups = [e for e in self.scaling_history if e.action == ScalingAction.SCALE_UP]
            scale_downs = [e for e in self.scaling_history if e.action == ScalingAction.SCALE_DOWN]
            
            status['statistics'] = {
                'total_scale_ups': len(scale_ups),
                'total_scale_downs': len(scale_downs),
                'success_rate': len(successful_events) / len(self.scaling_history),
                'total_cost_savings': sum(e.cost_impact for e in self.scaling_history if e.cost_impact < 0)
            }
        
        return status
    
    def update_policy(self, new_policy: ScalingPolicy):
        """Met à jour la politique de scaling"""
        self.policy = new_policy
        
        # Ajuster les paramètres selon la politique
        if new_policy == ScalingPolicy.AGGRESSIVE:
            self.global_config['check_interval'] = 15
            for config in self.scaling_configs.values():
                config.scale_up_threshold = 0.6
                config.scale_down_threshold = 0.4
                config.cooldown_period = 120
        
        elif new_policy == ScalingPolicy.CONSERVATIVE:
            self.global_config['check_interval'] = 60
            for config in self.scaling_configs.values():
                config.scale_up_threshold = 0.8
                config.scale_down_threshold = 0.2
                config.cooldown_period = 600
        
        elif new_policy == ScalingPolicy.COST_OPTIMIZED:
            self.global_config['enable_cost_optimization'] = True
            for config in self.scaling_configs.values():
                config.scale_down_threshold = 0.4
        
        logger.info(f"🔄 Scaling policy updated to {new_policy.value}")

# Exemple d'utilisation
async def main():
    """Test de l'auto-scaler"""
    scaler = AutoScaler()
    
    # Enregistrer des agents
    scaler.register_agent("agent-1", AgentScalingConfig(
        agent_id="agent-1",
        min_instances=1,
        max_instances=5,
        cost_per_instance=0.1
    ))
    
    scaler.register_agent("agent-2", AgentScalingConfig(
        agent_id="agent-2",
        min_instances=2,
        max_instances=8,
        cost_per_instance=0.15
    ))
    
    # Démarrer l'auto-scaling
    await scaler.start_auto_scaling()
    
    # Simuler des métriques
    for i in range(10):
        # Simuler une charge croissante
        load = min(1.0, i * 0.1)
        
        scaler.update_agent_metrics("agent-1", ScalingMetrics(
            cpu_usage=load,
            memory_usage=load * 0.8,
            avg_response_time=1.0 + load,
            error_rate=load * 0.05,
            throughput=10 - load * 3
        ))
        
        await asyncio.sleep(2)
    
    # Afficher le statut
    status = scaler.get_scaling_status()
    print(json.dumps(status, indent=2, default=str))
    
    # Arrêter l'auto-scaling
    await scaler.stop_auto_scaling()

if __name__ == "__main__":
    asyncio.run(main())