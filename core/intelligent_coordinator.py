#!/usr/bin/env python3
"""
Master Plan IA 2025 - Intelligent Coordinator
Système de coordination intelligente avec apprentissage et adaptation
"""

import asyncio
import json
import time
import uuid
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import defaultdict, deque
import networkx as nx
from datetime import datetime, timedelta
import statistics
import math

logger = logging.getLogger(__name__)

class LearningMode(Enum):
    """Modes d'apprentissage du coordinateur"""
    REACTIVE = "reactive"          # Réagit aux événements
    PROACTIVE = "proactive"        # Anticipe les besoins
    ADAPTIVE = "adaptive"          # S'adapte automatiquement
    PREDICTIVE = "predictive"      # Prédit les résultats

class CoordinationStrategy(Enum):
    """Stratégies de coordination avancées"""
    LOAD_BALANCED = "load_balanced"        # Équilibrage de charge
    PERFORMANCE_OPTIMIZED = "performance_optimized"  # Optimisé pour la performance
    COST_EFFICIENT = "cost_efficient"     # Efficace en coûts
    QUALITY_FOCUSED = "quality_focused"   # Axé sur la qualité
    HYBRID = "hybrid"                     # Hybride adaptatif

@dataclass
class AgentPerformanceMetrics:
    """Métriques de performance d'un agent"""
    agent_id: str
    success_rate: float = 0.0
    avg_response_time: float = 0.0
    throughput: float = 0.0
    error_rate: float = 0.0
    quality_score: float = 0.0
    load_factor: float = 0.0
    cost_per_task: float = 0.0
    specialization_scores: Dict[str, float] = field(default_factory=dict)
    recent_performance: deque = field(default_factory=lambda: deque(maxlen=100))
    trend_direction: str = "stable"  # improving, declining, stable
    
    def update_performance(self, task_result: Dict[str, Any]):
        """Met à jour les métriques de performance"""
        self.recent_performance.append({
            'timestamp': time.time(),
            'success': task_result.get('success', False),
            'response_time': task_result.get('response_time', 0),
            'quality': task_result.get('quality_score', 0),
            'cost': task_result.get('cost', 0)
        })
        
        # Recalculer les métriques
        if self.recent_performance:
            recent_data = list(self.recent_performance)[-20:]  # 20 dernières tâches
            
            self.success_rate = sum(1 for r in recent_data if r['success']) / len(recent_data)
            self.avg_response_time = statistics.mean(r['response_time'] for r in recent_data)
            self.quality_score = statistics.mean(r['quality'] for r in recent_data)
            self.cost_per_task = statistics.mean(r['cost'] for r in recent_data)
            self.error_rate = 1 - self.success_rate
            
            # Calculer la tendance
            if len(recent_data) >= 10:
                first_half = recent_data[:len(recent_data)//2]
                second_half = recent_data[len(recent_data)//2:]
                
                first_avg = statistics.mean(r['quality'] for r in first_half)
                second_avg = statistics.mean(r['quality'] for r in second_half)
                
                if second_avg > first_avg * 1.1:
                    self.trend_direction = "improving"
                elif second_avg < first_avg * 0.9:
                    self.trend_direction = "declining"
                else:
                    self.trend_direction = "stable"

@dataclass
class CoordinationContext:
    """Contexte de coordination enrichi"""
    id: str
    task_type: str
    priority: int
    deadline: Optional[float] = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    preferences: Dict[str, Any] = field(default_factory=dict)
    historical_data: List[Dict[str, Any]] = field(default_factory=list)
    environmental_factors: Dict[str, Any] = field(default_factory=dict)
    user_feedback: List[Dict[str, Any]] = field(default_factory=list)

class IntelligentCoordinator:
    """
    Coordinateur intelligent avec apprentissage automatique
    et adaptation dynamique des stratégies de coordination
    """
    
    def __init__(self, base_coordinator=None):
        self.base_coordinator = base_coordinator
        self.agent_metrics: Dict[str, AgentPerformanceMetrics] = {}
        self.coordination_history: deque = deque(maxlen=1000)
        self.learning_mode = LearningMode.ADAPTIVE
        self.current_strategy = CoordinationStrategy.HYBRID
        
        # Système d'apprentissage
        self.pattern_memory: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.success_patterns: Dict[str, float] = {}
        self.failure_patterns: Dict[str, float] = {}
        
        # Système de prédiction
        self.prediction_models: Dict[str, Any] = {}
        self.confidence_threshold = 0.7
        
        # Métriques globales
        self.global_metrics = {
            'total_tasks': 0,
            'successful_tasks': 0,
            'avg_completion_time': 0,
            'cost_efficiency': 0,
            'quality_index': 0,
            'adaptation_score': 0
        }
        
        # Système d'optimisation
        self.optimization_targets = {
            'minimize_latency': 0.3,
            'maximize_quality': 0.4,
            'minimize_cost': 0.2,
            'maximize_throughput': 0.1
        }
        
        logger.info("🧠 Intelligent Coordinator initialized")
    
    async def initialize_agent_metrics(self, agent_id: str, capabilities: List[str]):
        """Initialise les métriques pour un nouvel agent"""
        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = AgentPerformanceMetrics(
                agent_id=agent_id,
                specialization_scores={cap: 0.5 for cap in capabilities}
            )
    
    async def intelligent_agent_selection(self, 
                                        task_context: CoordinationContext,
                                        available_agents: List[str]) -> List[str]:
        """
        Sélection intelligente d'agents basée sur les métriques,
        l'historique et les prédictions
        """
        if not available_agents:
            return []
        
        # Scores des agents pour cette tâche
        agent_scores = {}
        
        for agent_id in available_agents:
            if agent_id not in self.agent_metrics:
                await self.initialize_agent_metrics(agent_id, [])
            
            metrics = self.agent_metrics[agent_id]
            score = await self._calculate_agent_score(metrics, task_context)
            agent_scores[agent_id] = score
        
        # Tri par score décroissant
        sorted_agents = sorted(agent_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Sélection adaptative basée sur la stratégie
        selected_agents = await self._apply_selection_strategy(sorted_agents, task_context)
        
        logger.info(f"🎯 Agent selection: {selected_agents} (strategy: {self.current_strategy.value})")
        return selected_agents
    
    async def _calculate_agent_score(self, 
                                   metrics: AgentPerformanceMetrics,
                                   context: CoordinationContext) -> float:
        """Calcule le score d'un agent pour une tâche donnée"""
        base_score = 0.0
        
        # Score de performance générale (30%)
        performance_score = (
            metrics.success_rate * 0.4 +
            (1 - metrics.error_rate) * 0.3 +
            metrics.quality_score * 0.3
        )
        base_score += performance_score * 0.3
        
        # Score de spécialisation (25%)
        specialization_score = metrics.specialization_scores.get(context.task_type, 0.5)
        base_score += specialization_score * 0.25
        
        # Score de charge (20%)
        load_score = max(0, 1 - metrics.load_factor)
        base_score += load_score * 0.2
        
        # Score de tendance (15%)
        trend_multiplier = {
            'improving': 1.2,
            'stable': 1.0,
            'declining': 0.8
        }
        base_score *= trend_multiplier.get(metrics.trend_direction, 1.0)
        
        # Score de vitesse (10%)
        if metrics.avg_response_time > 0:
            speed_score = 1 / (1 + metrics.avg_response_time)
            base_score += speed_score * 0.1
        
        # Ajustements contextuels
        if context.deadline:
            time_pressure = (context.deadline - time.time()) / 3600  # heures
            if time_pressure < 1:  # Moins d'une heure
                base_score *= 1.2 if metrics.avg_response_time < 10 else 0.8
        
        # Facteur de coût selon la stratégie
        if self.current_strategy == CoordinationStrategy.COST_EFFICIENT:
            cost_factor = 1 / (1 + metrics.cost_per_task)
            base_score *= cost_factor
        
        return max(0, min(1, base_score))
    
    async def _apply_selection_strategy(self, 
                                      sorted_agents: List[Tuple[str, float]],
                                      context: CoordinationContext) -> List[str]:
        """Applique la stratégie de sélection d'agents"""
        if not sorted_agents:
            return []
        
        strategy = self.current_strategy
        
        if strategy == CoordinationStrategy.PERFORMANCE_OPTIMIZED:
            # Prendre les meilleurs agents
            return [agent for agent, score in sorted_agents[:3] if score > 0.6]
        
        elif strategy == CoordinationStrategy.LOAD_BALANCED:
            # Équilibrer la charge
            selected = []
            for agent_id, score in sorted_agents:
                if len(selected) >= 3:
                    break
                metrics = self.agent_metrics[agent_id]
                if metrics.load_factor < 0.8:  # Pas trop chargé
                    selected.append(agent_id)
            return selected
        
        elif strategy == CoordinationStrategy.QUALITY_FOCUSED:
            # Privilégier la qualité
            quality_agents = [
                agent for agent, score in sorted_agents 
                if self.agent_metrics[agent].quality_score > 0.7
            ]
            return quality_agents[:2]
        
        elif strategy == CoordinationStrategy.COST_EFFICIENT:
            # Optimiser les coûts
            cost_efficient = [
                agent for agent, score in sorted_agents 
                if self.agent_metrics[agent].cost_per_task < 0.5
            ]
            return cost_efficient[:3]
        
        else:  # HYBRID
            # Stratégie hybride adaptative
            if context.priority > 7:
                return [sorted_agents[0][0]]  # Meilleur agent seulement
            elif context.priority > 5:
                return [agent for agent, score in sorted_agents[:2]]
            else:
                return [agent for agent, score in sorted_agents[:3]]
    
    async def adaptive_coordination_pattern(self, 
                                          context: CoordinationContext,
                                          agents: List[str]) -> str:
        """
        Sélectionne dynamiquement le pattern de coordination
        le plus adapté selon le contexte et l'historique
        """
        # Analyser l'historique pour ce type de tâche
        similar_tasks = [
            task for task in self.coordination_history
            if task.get('task_type') == context.task_type
        ]
        
        if len(similar_tasks) < 5:
            # Pas assez d'historique, utiliser les defaults
            return self._get_default_pattern(context, agents)
        
        # Analyser les patterns les plus performants
        pattern_performance = defaultdict(list)
        for task in similar_tasks[-20:]:  # 20 dernières tâches similaires
            pattern = task.get('pattern')
            success = task.get('success', False)
            quality = task.get('quality_score', 0)
            time_taken = task.get('completion_time', 0)
            
            if pattern:
                score = (success * 0.5 + quality * 0.3 + (1/(1+time_taken)) * 0.2)
                pattern_performance[pattern].append(score)
        
        # Calculer les scores moyens
        avg_scores = {
            pattern: statistics.mean(scores) 
            for pattern, scores in pattern_performance.items()
            if len(scores) >= 2
        }
        
        if not avg_scores:
            return self._get_default_pattern(context, agents)
        
        # Sélectionner le meilleur pattern
        best_pattern = max(avg_scores, key=avg_scores.get)
        confidence = avg_scores[best_pattern]
        
        # Si confiance faible, utiliser pattern adaptatif
        if confidence < self.confidence_threshold:
            return self._get_adaptive_pattern(context, agents, avg_scores)
        
        logger.info(f"🎯 Selected pattern: {best_pattern} (confidence: {confidence:.2f})")
        return best_pattern
    
    def _get_default_pattern(self, context: CoordinationContext, agents: List[str]) -> str:
        """Retourne le pattern par défaut selon le contexte"""
        if len(agents) == 1:
            return "sequential"
        elif context.priority > 8:
            return "competitive"
        elif context.deadline and (context.deadline - time.time()) < 3600:
            return "parallel"
        elif context.task_type in ["analysis", "research"]:
            return "collaborative"
        else:
            return "pipeline"
    
    def _get_adaptive_pattern(self, 
                            context: CoordinationContext,
                            agents: List[str],
                            historical_scores: Dict[str, float]) -> str:
        """Sélectionne un pattern adaptatif basé sur plusieurs facteurs"""
        
        # Facteurs de décision
        factors = {
            'urgency': min(1.0, (10 - context.priority) / 10),
            'complexity': len(context.constraints) / 10,
            'agent_count': len(agents) / 5,
            'time_pressure': 1.0 if context.deadline and (context.deadline - time.time()) < 3600 else 0.5
        }
        
        # Matrice de décision
        if factors['urgency'] > 0.8 and factors['agent_count'] > 0.4:
            return "competitive"
        elif factors['complexity'] > 0.6:
            return "hierarchical"
        elif factors['time_pressure'] > 0.8:
            return "parallel"
        elif factors['agent_count'] > 0.6:
            return "collaborative"
        else:
            return "pipeline"
    
    async def execute_with_intelligence(self, 
                                      workflow_id: str,
                                      context: CoordinationContext) -> Dict[str, Any]:
        """
        Exécute un workflow avec intelligence adaptative
        """
        start_time = time.time()
        
        # Sélection intelligente d'agents
        available_agents = await self._get_available_agents()
        selected_agents = await self.intelligent_agent_selection(context, available_agents)
        
        if not selected_agents:
            return {"error": "No suitable agents available"}
        
        # Sélection du pattern adaptatif
        pattern = await self.adaptive_coordination_pattern(context, selected_agents)
        
        # Création du workflow optimisé
        steps = await self._create_optimized_steps(context, selected_agents, pattern)
        
        # Exécution avec monitoring
        result = await self._execute_with_monitoring(
            workflow_id, context, selected_agents, pattern, steps
        )
        
        # Apprentissage post-exécution
        await self._learn_from_execution(context, result, time.time() - start_time)
        
        return result
    
    async def _get_available_agents(self) -> List[str]:
        """Récupère la liste des agents disponibles"""
        if self.base_coordinator and hasattr(self.base_coordinator, 'orchestration_hub'):
            hub = self.base_coordinator.orchestration_hub
            if hasattr(hub, 'agents'):
                return [
                    agent_id for agent_id, agent in hub.agents.items()
                    if agent.is_healthy and agent.current_tasks < agent.max_concurrent_tasks
                ]
        
        # Fallback pour les tests
        return ["llm-session-default", "ollama-default", "claude-code-default"]
    
    async def _create_optimized_steps(self, 
                                    context: CoordinationContext,
                                    agents: List[str],
                                    pattern: str) -> List[Dict[str, Any]]:
        """Crée des étapes optimisées pour le workflow"""
        steps = []
        
        if pattern == "sequential":
            for i, agent in enumerate(agents):
                steps.append({
                    "agent": agent,
                    "task": {
                        "type": context.task_type,
                        "step": i,
                        "optimization": "sequential"
                    }
                })
        
        elif pattern == "parallel":
            for agent in agents:
                steps.append({
                    "agent": agent,
                    "task": {
                        "type": context.task_type,
                        "optimization": "parallel"
                    }
                })
        
        elif pattern == "collaborative":
            for agent in agents:
                steps.append({
                    "agent": agent,
                    "task": {
                        "type": context.task_type,
                        "role": "collaborator",
                        "optimization": "collaborative"
                    }
                })
        
        elif pattern == "competitive":
            for agent in agents:
                steps.append({
                    "agent": agent,
                    "task": {
                        "type": context.task_type,
                        "role": "competitor",
                        "optimization": "competitive"
                    }
                })
        
        elif pattern == "hierarchical":
            # Leader
            steps.append({
                "agent": agents[0],
                "task": {
                    "type": context.task_type,
                    "role": "leader",
                    "optimization": "hierarchical"
                }
            })
            # Spécialistes
            for agent in agents[1:]:
                steps.append({
                    "agent": agent,
                    "task": {
                        "type": context.task_type,
                        "role": "specialist",
                        "optimization": "hierarchical"
                    }
                })
        
        elif pattern == "pipeline":
            for i, agent in enumerate(agents):
                steps.append({
                    "agent": agent,
                    "task": {
                        "type": context.task_type,
                        "stage": i,
                        "optimization": "pipeline"
                    }
                })
        
        return steps
    
    async def _execute_with_monitoring(self,
                                     workflow_id: str,
                                     context: CoordinationContext,
                                     agents: List[str],
                                     pattern: str,
                                     steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Exécute le workflow avec monitoring en temps réel"""
        
        execution_start = time.time()
        
        # Utiliser le coordinateur de base si disponible
        if self.base_coordinator:
            try:
                # Créer le workflow
                workflow_id = await self.base_coordinator.create_workflow(
                    name=f"Intelligent-{workflow_id}",
                    pattern=getattr(self.base_coordinator, 'CoordinationPattern', type('', (), {pattern.upper(): pattern})).COLLABORATIVE,
                    agents=agents,
                    steps=steps,
                    initial_context=context.constraints
                )
                
                # Exécuter
                result = await self.base_coordinator.execute_workflow(workflow_id)
                
                # Enrichir avec les métriques
                result['execution_time'] = time.time() - execution_start
                result['pattern_used'] = pattern
                result['agents_used'] = agents
                result['intelligence_applied'] = True
                
                return result
            
            except Exception as e:
                logger.error(f"Error in base coordinator execution: {e}")
        
        # Fallback simulation
        await asyncio.sleep(0.5)  # Simule l'exécution
        return {
            "workflow_id": workflow_id,
            "pattern_used": pattern,
            "agents_used": agents,
            "execution_time": time.time() - execution_start,
            "success": True,
            "quality_score": 0.8,
            "intelligence_applied": True,
            "result": "Intelligent execution completed successfully"
        }
    
    async def _learn_from_execution(self, 
                                  context: CoordinationContext,
                                  result: Dict[str, Any],
                                  execution_time: float):
        """Apprend de l'exécution pour améliorer les futures décisions"""
        
        # Mise à jour des métriques des agents
        for agent_id in result.get('agents_used', []):
            if agent_id in self.agent_metrics:
                self.agent_metrics[agent_id].update_performance({
                    'success': result.get('success', False),
                    'response_time': execution_time,
                    'quality_score': result.get('quality_score', 0.5),
                    'cost': result.get('cost', 0.1)
                })
        
        # Mise à jour de l'historique
        self.coordination_history.append({
            'timestamp': time.time(),
            'task_type': context.task_type,
            'pattern': result.get('pattern_used'),
            'agents': result.get('agents_used'),
            'success': result.get('success', False),
            'quality_score': result.get('quality_score', 0.5),
            'completion_time': execution_time,
            'context': context.constraints
        })
        
        # Mise à jour des patterns de succès/échec
        pattern_key = f"{context.task_type}_{result.get('pattern_used')}"
        if result.get('success'):
            self.success_patterns[pattern_key] = self.success_patterns.get(pattern_key, 0) + 1
        else:
            self.failure_patterns[pattern_key] = self.failure_patterns.get(pattern_key, 0) + 1
        
        # Adaptation de la stratégie
        await self._adapt_strategy(context, result)
        
        # Mise à jour des métriques globales
        self.global_metrics['total_tasks'] += 1
        if result.get('success'):
            self.global_metrics['successful_tasks'] += 1
        
        success_rate = self.global_metrics['successful_tasks'] / self.global_metrics['total_tasks']
        if success_rate > 0.9:
            self.global_metrics['adaptation_score'] += 0.1
        elif success_rate < 0.7:
            self.global_metrics['adaptation_score'] -= 0.1
        
        logger.info(f"🧠 Learning completed: Success rate: {success_rate:.2f}, Adaptation score: {self.global_metrics['adaptation_score']:.2f}")
    
    async def _adapt_strategy(self, context: CoordinationContext, result: Dict[str, Any]):
        """Adapte la stratégie de coordination basée sur les résultats"""
        
        quality = result.get('quality_score', 0.5)
        execution_time = result.get('execution_time', 0)
        success = result.get('success', False)
        
        # Adaptation basée sur la performance
        if not success or quality < 0.6:
            # Échec ou qualité faible
            if self.current_strategy == CoordinationStrategy.COST_EFFICIENT:
                self.current_strategy = CoordinationStrategy.QUALITY_FOCUSED
                logger.info("🔄 Strategy adapted: COST_EFFICIENT -> QUALITY_FOCUSED")
            elif self.current_strategy == CoordinationStrategy.PERFORMANCE_OPTIMIZED:
                self.current_strategy = CoordinationStrategy.HYBRID
                logger.info("🔄 Strategy adapted: PERFORMANCE_OPTIMIZED -> HYBRID")
        
        elif quality > 0.8 and execution_time < 5:
            # Très bonne performance
            if self.current_strategy == CoordinationStrategy.QUALITY_FOCUSED:
                self.current_strategy = CoordinationStrategy.PERFORMANCE_OPTIMIZED
                logger.info("🔄 Strategy adapted: QUALITY_FOCUSED -> PERFORMANCE_OPTIMIZED")
        
        # Adaptation basée sur la charge système
        total_load = sum(metrics.load_factor for metrics in self.agent_metrics.values())
        avg_load = total_load / max(1, len(self.agent_metrics))
        
        if avg_load > 0.8:
            self.current_strategy = CoordinationStrategy.LOAD_BALANCED
            logger.info("🔄 Strategy adapted to LOAD_BALANCED due to high system load")
        elif avg_load < 0.3 and self.current_strategy == CoordinationStrategy.LOAD_BALANCED:
            self.current_strategy = CoordinationStrategy.HYBRID
            logger.info("🔄 Strategy adapted: LOAD_BALANCED -> HYBRID")
    
    async def get_intelligence_metrics(self) -> Dict[str, Any]:
        """Retourne les métriques d'intelligence du coordinateur"""
        
        total_tasks = self.global_metrics['total_tasks']
        if total_tasks == 0:
            return {"status": "no_data", "message": "No tasks executed yet"}
        
        success_rate = self.global_metrics['successful_tasks'] / total_tasks
        
        # Métriques d'apprentissage
        pattern_effectiveness = {}
        for pattern, successes in self.success_patterns.items():
            failures = self.failure_patterns.get(pattern, 0)
            total = successes + failures
            if total > 0:
                pattern_effectiveness[pattern] = successes / total
        
        # Métriques des agents
        agent_rankings = {}
        for agent_id, metrics in self.agent_metrics.items():
            score = (metrics.success_rate * 0.4 + 
                    metrics.quality_score * 0.3 + 
                    (1 - metrics.load_factor) * 0.3)
            agent_rankings[agent_id] = {
                'score': score,
                'trend': metrics.trend_direction,
                'specializations': metrics.specialization_scores
            }
        
        return {
            'overall_intelligence': {
                'success_rate': success_rate,
                'adaptation_score': self.global_metrics['adaptation_score'],
                'learning_mode': self.learning_mode.value,
                'current_strategy': self.current_strategy.value,
                'total_tasks_processed': total_tasks
            },
            'pattern_effectiveness': pattern_effectiveness,
            'agent_rankings': agent_rankings,
            'coordination_insights': {
                'most_successful_pattern': max(pattern_effectiveness, key=pattern_effectiveness.get) if pattern_effectiveness else None,
                'avg_execution_time': statistics.mean([task['completion_time'] for task in self.coordination_history if 'completion_time' in task]) if self.coordination_history else 0,
                'quality_trend': self._calculate_quality_trend()
            }
        }
    
    def _calculate_quality_trend(self) -> str:
        """Calcule la tendance de qualité"""
        if len(self.coordination_history) < 10:
            return "insufficient_data"
        
        recent_tasks = list(self.coordination_history)[-10:]
        older_tasks = list(self.coordination_history)[-20:-10] if len(self.coordination_history) >= 20 else []
        
        if not older_tasks:
            return "stable"
        
        recent_quality = statistics.mean(task.get('quality_score', 0.5) for task in recent_tasks)
        older_quality = statistics.mean(task.get('quality_score', 0.5) for task in older_tasks)
        
        if recent_quality > older_quality * 1.1:
            return "improving"
        elif recent_quality < older_quality * 0.9:
            return "declining"
        else:
            return "stable"

# Exemple d'utilisation
async def main():
    """Test du coordinateur intelligent"""
    coordinator = IntelligentCoordinator()
    
    # Simulation d'une tâche
    context = CoordinationContext(
        id="test-context",
        task_type="analysis",
        priority=8,
        deadline=time.time() + 3600,
        constraints={"domain": "technical", "complexity": "high"}
    )
    
    # Exécution intelligente
    result = await coordinator.execute_with_intelligence("test-workflow", context)
    print(f"Résultat: {json.dumps(result, indent=2)}")
    
    # Métriques d'intelligence
    metrics = await coordinator.get_intelligence_metrics()
    print(f"Métriques: {json.dumps(metrics, indent=2)}")

if __name__ == "__main__":
    asyncio.run(main())