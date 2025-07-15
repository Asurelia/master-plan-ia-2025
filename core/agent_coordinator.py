#!/usr/bin/env python3
"""
Master Plan IA 2025 - Agent Coordinator
Système de coordination avancé pour agents multi-IA
"""

import asyncio
import json
import time
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import defaultdict
import networkx as nx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CoordinationPattern(Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"
    COLLABORATIVE = "collaborative"
    COMPETITIVE = "competitive"
    HIERARCHICAL = "hierarchical"

class AgentRole(Enum):
    LEADER = "leader"
    SPECIALIST = "specialist"
    VALIDATOR = "validator"
    AGGREGATOR = "aggregator"
    MONITOR = "monitor"

@dataclass
class Context:
    """Contexte partagé entre agents"""
    id: str
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    version: int = 1

@dataclass
class Workflow:
    """Workflow de coordination d'agents"""
    id: str
    name: str
    pattern: CoordinationPattern
    agents: List[str]
    steps: List[Dict[str, Any]]
    context: Context
    status: str = "pending"
    current_step: int = 0
    results: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

@dataclass
class AgentCapability:
    """Capacité d'un agent"""
    name: str
    confidence: float
    cost_factor: float
    avg_response_time: float
    quality_score: float
    specialization_level: float

class AgentCoordinator:
    """
    Coordinateur d'agents pour Master Plan IA 2025
    Gère la coordination, collaboration et orchestration multi-agents
    """
    
    def __init__(self, orchestration_hub=None):
        self.orchestration_hub = orchestration_hub
        self.workflows: Dict[str, Workflow] = {}
        self.contexts: Dict[str, Context] = {}
        self.agent_graph = nx.DiGraph()
        self.collaboration_history: List[Dict[str, Any]] = []
        
        # Métriques de coordination
        self.coordination_metrics = {
            'active_workflows': 0,
            'completed_workflows': 0,
            'failed_workflows': 0,
            'avg_coordination_time': 0.0,
            'collaboration_efficiency': 0.0
        }
        
        # Patterns de coordination pré-définis
        self.coordination_patterns = {
            CoordinationPattern.SEQUENTIAL: self.execute_sequential,
            CoordinationPattern.PARALLEL: self.execute_parallel,
            CoordinationPattern.PIPELINE: self.execute_pipeline,
            CoordinationPattern.COLLABORATIVE: self.execute_collaborative,
            CoordinationPattern.COMPETITIVE: self.execute_competitive,
            CoordinationPattern.HIERARCHICAL: self.execute_hierarchical
        }
        
        logger.info("🧠 Agent Coordinator initialized")
    
    async def create_workflow(self, name: str, pattern: CoordinationPattern,
                            agents: List[str], steps: List[Dict[str, Any]],
                            initial_context: Dict[str, Any] = None) -> str:
        """Crée un nouveau workflow de coordination"""
        workflow_id = f"workflow-{uuid.uuid4().hex[:8]}"
        
        # Créer le contexte initial
        context = Context(
            id=f"context-{workflow_id}",
            data=initial_context or {},
            metadata={
                'workflow_id': workflow_id,
                'pattern': pattern.value,
                'agents': agents
            }
        )
        
        workflow = Workflow(
            id=workflow_id,
            name=name,
            pattern=pattern,
            agents=agents,
            steps=steps,
            context=context
        )
        
        self.workflows[workflow_id] = workflow
        self.contexts[context.id] = context
        self.coordination_metrics['active_workflows'] += 1
        
        # Construire le graphe d'agents pour ce workflow
        await self.build_agent_graph(workflow)
        
        logger.info(f"📋 Workflow created: {workflow_id} ({pattern.value})")
        return workflow_id
    
    async def build_agent_graph(self, workflow: Workflow):
        """Construit le graphe de relations entre agents"""
        # Ajouter les agents au graphe
        for agent_id in workflow.agents:
            if not self.agent_graph.has_node(agent_id):
                agent_info = await self.get_agent_info(agent_id)
                self.agent_graph.add_node(agent_id, **agent_info)
        
        # Ajouter les relations basées sur les étapes
        for step in workflow.steps:
            if 'dependencies' in step:
                for dep in step['dependencies']:
                    if dep in workflow.agents and step['agent'] in workflow.agents:
                        self.agent_graph.add_edge(dep, step['agent'])
    
    async def get_agent_info(self, agent_id: str) -> Dict[str, Any]:
        """Récupère les informations d'un agent"""
        if self.orchestration_hub and agent_id in self.orchestration_hub.agents:
            agent = self.orchestration_hub.agents[agent_id]
            return {
                'type': agent.type.value,
                'capabilities': agent.capabilities,
                'performance': agent.performance_metrics,
                'current_load': agent.current_tasks / agent.max_concurrent_tasks
            }
        return {}
    
    async def execute_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Exécute un workflow de coordination"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        workflow.status = "running"
        start_time = time.time()
        
        try:
            # Exécuter selon le pattern
            pattern_executor = self.coordination_patterns[workflow.pattern]
            result = await pattern_executor(workflow)
            
            workflow.status = "completed"
            workflow.results = result
            self.coordination_metrics['completed_workflows'] += 1
            
            # Enregistrer l'historique
            await self.record_collaboration(workflow, result, time.time() - start_time)
            
            logger.info(f"✅ Workflow completed: {workflow_id}")
            return result
            
        except Exception as e:
            workflow.status = "failed"
            workflow.results = {"error": str(e)}
            self.coordination_metrics['failed_workflows'] += 1
            logger.error(f"❌ Workflow failed: {workflow_id} - {e}")
            raise
        finally:
            self.coordination_metrics['active_workflows'] -= 1
    
    async def execute_sequential(self, workflow: Workflow) -> Dict[str, Any]:
        """Exécution séquentielle des agents"""
        results = {}
        context = workflow.context
        
        for i, step in enumerate(workflow.steps):
            workflow.current_step = i
            agent_id = step['agent']
            task_config = step.get('task', {})
            
            # Préparer la tâche avec le contexte
            task_payload = {
                **task_config,
                'context': context.data,
                'step_info': {
                    'step_number': i,
                    'total_steps': len(workflow.steps),
                    'workflow_id': workflow.id
                }
            }
            
            # Exécuter la tâche
            result = await self.execute_agent_task(agent_id, task_payload)
            results[f"step_{i}_{agent_id}"] = result
            
            # Mettre à jour le contexte
            await self.update_context(context, result, agent_id)
        
        return results
    
    async def execute_parallel(self, workflow: Workflow) -> Dict[str, Any]:
        """Exécution parallèle des agents"""
        tasks = []
        context = workflow.context
        
        for i, step in enumerate(workflow.steps):
            agent_id = step['agent']
            task_config = step.get('task', {})
            
            task_payload = {
                **task_config,
                'context': context.data.copy(),  # Copie pour éviter les conflits
                'step_info': {
                    'step_number': i,
                    'total_steps': len(workflow.steps),
                    'workflow_id': workflow.id
                }
            }
            
            task = self.execute_agent_task(agent_id, task_payload)
            tasks.append((f"step_{i}_{agent_id}", task))
        
        # Attendre tous les résultats
        results = {}
        for task_name, task in tasks:
            try:
                result = await task
                results[task_name] = result
                
                # Mettre à jour le contexte de manière thread-safe
                await self.update_context(context, result, task_name)
                
            except Exception as e:
                results[task_name] = {"error": str(e)}
        
        return results
    
    async def execute_pipeline(self, workflow: Workflow) -> Dict[str, Any]:
        """Exécution en pipeline (streaming entre agents)"""
        results = {}
        context = workflow.context
        
        # Créer des channels pour le streaming
        channels = {}
        for i in range(len(workflow.steps) - 1):
            channels[i] = asyncio.Queue()
        
        # Démarrer tous les agents en parallèle
        tasks = []
        for i, step in enumerate(workflow.steps):
            agent_id = step['agent']
            input_channel = channels.get(i - 1)
            output_channel = channels.get(i)
            
            task = self.execute_pipeline_agent(
                agent_id, step, context, input_channel, output_channel, i
            )
            tasks.append((f"step_{i}_{agent_id}", task))
        
        # Attendre tous les résultats
        for task_name, task in tasks:
            try:
                result = await task
                results[task_name] = result
            except Exception as e:
                results[task_name] = {"error": str(e)}
        
        return results
    
    async def execute_collaborative(self, workflow: Workflow) -> Dict[str, Any]:
        """Exécution collaborative (agents travaillent ensemble)"""
        results = {}
        context = workflow.context
        
        # Créer un espace de travail partagé
        shared_workspace = {
            'contributions': {},
            'consensus': None,
            'conflicts': [],
            'iterations': 0
        }
        
        max_iterations = 3
        consensus_threshold = 0.8
        
        for iteration in range(max_iterations):
            shared_workspace['iterations'] = iteration
            
            # Tous les agents contribuent en parallèle
            contributions = {}
            tasks = []
            
            for agent_id in workflow.agents:
                task_payload = {
                    'shared_workspace': shared_workspace.copy(),
                    'context': context.data,
                    'collaboration_info': {
                        'iteration': iteration,
                        'max_iterations': max_iterations,
                        'workflow_id': workflow.id
                    }
                }
                
                task = self.execute_agent_task(agent_id, task_payload)
                tasks.append((agent_id, task))
            
            # Collecter les contributions
            for agent_id, task in tasks:
                try:
                    contribution = await task
                    contributions[agent_id] = contribution
                except Exception as e:
                    contributions[agent_id] = {"error": str(e)}
            
            shared_workspace['contributions'] = contributions
            
            # Évaluer le consensus
            consensus_score = await self.evaluate_consensus(contributions)
            
            if consensus_score >= consensus_threshold:
                shared_workspace['consensus'] = await self.build_consensus(contributions)
                break
            
            # Identifier les conflits
            conflicts = await self.identify_conflicts(contributions)
            shared_workspace['conflicts'] = conflicts
            
            # Mettre à jour le contexte pour la prochaine itération
            await self.update_context_from_contributions(context, contributions)
        
        results['collaborative_result'] = shared_workspace
        return results
    
    async def execute_competitive(self, workflow: Workflow) -> Dict[str, Any]:
        """Exécution compétitive (agents en compétition)"""
        results = {}
        context = workflow.context
        
        # Tous les agents travaillent sur la même tâche
        base_task = workflow.steps[0].get('task', {})
        
        tasks = []
        for agent_id in workflow.agents:
            task_payload = {
                **base_task,
                'context': context.data.copy(),
                'competition_info': {
                    'competitors': [aid for aid in workflow.agents if aid != agent_id],
                    'workflow_id': workflow.id
                }
            }
            
            task = self.execute_agent_task(agent_id, task_payload)
            tasks.append((agent_id, task))
        
        # Collecter tous les résultats
        submissions = {}
        for agent_id, task in tasks:
            try:
                result = await task
                submissions[agent_id] = result
            except Exception as e:
                submissions[agent_id] = {"error": str(e)}
        
        # Évaluer et classer les résultats
        rankings = await self.evaluate_competitive_results(submissions)
        
        results['competitive_result'] = {
            'submissions': submissions,
            'rankings': rankings,
            'winner': rankings[0]['agent_id'] if rankings else None
        }
        
        return results
    
    async def execute_hierarchical(self, workflow: Workflow) -> Dict[str, Any]:
        """Exécution hiérarchique (agents avec rôles)"""
        results = {}
        context = workflow.context
        
        # Organiser les agents par rôles
        roles = defaultdict(list)
        for step in workflow.steps:
            role = step.get('role', AgentRole.SPECIALIST.value)
            roles[role].append(step)
        
        # Exécution hiérarchique
        # 1. Leaders définissent la stratégie
        if 'leader' in roles:
            leader_results = {}
            for step in roles['leader']:
                agent_id = step['agent']
                task_payload = {
                    **step.get('task', {}),
                    'context': context.data,
                    'role': 'leader',
                    'subordinates': [s['agent'] for s in roles['specialist']]
                }
                
                result = await self.execute_agent_task(agent_id, task_payload)
                leader_results[agent_id] = result
                await self.update_context(context, result, agent_id)
            
            results['leader_phase'] = leader_results
        
        # 2. Specialists exécutent les tâches
        if 'specialist' in roles:
            specialist_tasks = []
            for step in roles['specialist']:
                agent_id = step['agent']
                task_payload = {
                    **step.get('task', {}),
                    'context': context.data,
                    'role': 'specialist',
                    'leader_instructions': results.get('leader_phase', {})
                }
                
                task = self.execute_agent_task(agent_id, task_payload)
                specialist_tasks.append((agent_id, task))
            
            specialist_results = {}
            for agent_id, task in specialist_tasks:
                try:
                    result = await task
                    specialist_results[agent_id] = result
                    await self.update_context(context, result, agent_id)
                except Exception as e:
                    specialist_results[agent_id] = {"error": str(e)}
            
            results['specialist_phase'] = specialist_results
        
        # 3. Validators vérifient les résultats
        if 'validator' in roles:
            validator_results = {}
            for step in roles['validator']:
                agent_id = step['agent']
                task_payload = {
                    **step.get('task', {}),
                    'context': context.data,
                    'role': 'validator',
                    'results_to_validate': results.get('specialist_phase', {})
                }
                
                result = await self.execute_agent_task(agent_id, task_payload)
                validator_results[agent_id] = result
            
            results['validator_phase'] = validator_results
        
        # 4. Aggregators consolident les résultats
        if 'aggregator' in roles:
            aggregator_results = {}
            for step in roles['aggregator']:
                agent_id = step['agent']
                task_payload = {
                    **step.get('task', {}),
                    'context': context.data,
                    'role': 'aggregator',
                    'all_results': results
                }
                
                result = await self.execute_agent_task(agent_id, task_payload)
                aggregator_results[agent_id] = result
            
            results['aggregator_phase'] = aggregator_results
        
        return results
    
    async def execute_agent_task(self, agent_id: str, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Exécute une tâche sur un agent spécifique"""
        if self.orchestration_hub:
            from orchestration_hub import Task
            
            task = Task(
                type=task_payload.get('type', 'generic'),
                payload=task_payload,
                metadata={'coordination': True}
            )
            
            task_id = await self.orchestration_hub.submit_task(task)
            
            # Attendre la completion
            max_wait = 30  # 30 secondes
            wait_time = 0.1
            total_wait = 0
            
            while total_wait < max_wait:
                await asyncio.sleep(wait_time)
                total_wait += wait_time
                
                if task.status.value in ['completed', 'failed']:
                    break
            
            if task.status.value == 'completed':
                return task.result
            else:
                raise Exception(f"Task failed or timeout: {task.error}")
        
        # Simulation si pas de hub
        await asyncio.sleep(0.5)
        return {
            "agent_id": agent_id,
            "result": f"Simulated result for {agent_id}",
            "timestamp": time.time()
        }
    
    async def execute_pipeline_agent(self, agent_id: str, step: Dict[str, Any],
                                   context: Context, input_channel: Optional[asyncio.Queue],
                                   output_channel: Optional[asyncio.Queue], step_index: int) -> Dict[str, Any]:
        """Exécute un agent dans un pipeline"""
        # Traitement streaming
        if input_channel:
            # Attendre les données du canal d'entrée
            input_data = await input_channel.get()
        else:
            # Premier agent du pipeline
            input_data = context.data
        
        # Traitement
        task_payload = {
            **step.get('task', {}),
            'input_data': input_data,
            'context': context.data,
            'pipeline_info': {
                'step_index': step_index,
                'is_first': input_channel is None,
                'is_last': output_channel is None
            }
        }
        
        result = await self.execute_agent_task(agent_id, task_payload)
        
        # Envoyer au canal de sortie
        if output_channel:
            await output_channel.put(result)
        
        return result
    
    async def update_context(self, context: Context, result: Dict[str, Any], agent_id: str):
        """Met à jour le contexte avec les résultats d'un agent"""
        context.data[f"result_{agent_id}"] = result
        context.updated_at = time.time()
        context.version += 1
        context.access_count += 1
        
        # Mettre à jour les métadonnées
        if 'agent_contributions' not in context.metadata:
            context.metadata['agent_contributions'] = {}
        
        context.metadata['agent_contributions'][agent_id] = {
            'timestamp': time.time(),
            'result_keys': list(result.keys()) if isinstance(result, dict) else []
        }
    
    async def update_context_from_contributions(self, context: Context, contributions: Dict[str, Any]):
        """Met à jour le contexte à partir des contributions collaboratives"""
        for agent_id, contribution in contributions.items():
            if 'error' not in contribution:
                context.data[f"contribution_{agent_id}"] = contribution
        
        context.updated_at = time.time()
        context.version += 1
    
    async def evaluate_consensus(self, contributions: Dict[str, Any]) -> float:
        """Évalue le niveau de consensus entre les contributions"""
        # Implémentation simplifiée - dans la réalité, utiliser des métriques plus sophistiquées
        if len(contributions) < 2:
            return 1.0
        
        # Analyser la similarité des contributions
        similarity_scores = []
        contribution_list = list(contributions.values())
        
        for i in range(len(contribution_list)):
            for j in range(i + 1, len(contribution_list)):
                similarity = await self.calculate_similarity(contribution_list[i], contribution_list[j])
                similarity_scores.append(similarity)
        
        return sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0.0
    
    async def calculate_similarity(self, contrib1: Dict[str, Any], contrib2: Dict[str, Any]) -> float:
        """Calcule la similarité entre deux contributions"""
        # Implémentation simplifiée
        if 'error' in contrib1 or 'error' in contrib2:
            return 0.0
        
        # Comparaison basique - à améliorer avec des métriques sémantiques
        common_keys = set(contrib1.keys()) & set(contrib2.keys())
        total_keys = set(contrib1.keys()) | set(contrib2.keys())
        
        if not total_keys:
            return 1.0
        
        return len(common_keys) / len(total_keys)
    
    async def build_consensus(self, contributions: Dict[str, Any]) -> Dict[str, Any]:
        """Construit un consensus à partir des contributions"""
        consensus = {}
        
        # Agréger les contributions
        for agent_id, contribution in contributions.items():
            if 'error' not in contribution:
                for key, value in contribution.items():
                    if key not in consensus:
                        consensus[key] = []
                    consensus[key].append(value)
        
        # Créer le consensus final
        final_consensus = {}
        for key, values in consensus.items():
            if len(values) == 1:
                final_consensus[key] = values[0]
            else:
                # Logique de consensus (majorité, moyenne, etc.)
                final_consensus[key] = values  # Garder toutes les valeurs pour l'instant
        
        return final_consensus
    
    async def identify_conflicts(self, contributions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identifie les conflits entre contributions"""
        conflicts = []
        
        # Analyser les divergences
        for key in set().union(*(contrib.keys() for contrib in contributions.values() if 'error' not in contrib)):
            values = {}
            for agent_id, contrib in contributions.items():
                if 'error' not in contrib and key in contrib:
                    values[agent_id] = contrib[key]
            
            if len(set(str(v) for v in values.values())) > 1:
                conflicts.append({
                    'key': key,
                    'conflicting_values': values,
                    'agents_involved': list(values.keys())
                })
        
        return conflicts
    
    async def evaluate_competitive_results(self, submissions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Évalue et classe les résultats compétitifs"""
        rankings = []
        
        for agent_id, result in submissions.items():
            if 'error' not in result:
                score = await self.calculate_competitive_score(result)
                rankings.append({
                    'agent_id': agent_id,
                    'score': score,
                    'result': result
                })
        
        # Trier par score décroissant
        rankings.sort(key=lambda x: x['score'], reverse=True)
        
        return rankings
    
    async def calculate_competitive_score(self, result: Dict[str, Any]) -> float:
        """Calcule le score compétitif d'un résultat"""
        # Implémentation simplifiée - critères multiples dans la réalité
        score = 0.0
        
        # Critères possibles
        if 'quality' in result:
            score += result['quality'] * 0.4
        
        if 'speed' in result:
            score += (1.0 / max(result['speed'], 0.001)) * 0.3
        
        if 'completeness' in result:
            score += result['completeness'] * 0.3
        
        return score
    
    async def record_collaboration(self, workflow: Workflow, result: Dict[str, Any], execution_time: float):
        """Enregistre l'historique de collaboration"""
        collaboration_record = {
            'workflow_id': workflow.id,
            'pattern': workflow.pattern.value,
            'agents': workflow.agents,
            'execution_time': execution_time,
            'success': workflow.status == 'completed',
            'result_quality': await self.assess_result_quality(result),
            'timestamp': time.time()
        }
        
        self.collaboration_history.append(collaboration_record)
        
        # Maintenir un historique limité
        if len(self.collaboration_history) > 1000:
            self.collaboration_history = self.collaboration_history[-1000:]
    
    async def assess_result_quality(self, result: Dict[str, Any]) -> float:
        """Évalue la qualité d'un résultat"""
        # Implémentation simplifiée
        if not result:
            return 0.0
        
        # Critères de qualité
        quality_score = 0.0
        
        # Complétude
        if 'error' not in result:
            quality_score += 0.5
        
        # Richesse du contenu
        if isinstance(result, dict):
            quality_score += min(len(result) / 10, 0.3)
        
        # Cohérence
        quality_score += 0.2  # Placeholder
        
        return min(quality_score, 1.0)
    
    async def get_coordination_metrics(self) -> Dict[str, Any]:
        """Retourne les métriques de coordination"""
        # Calculer les métriques avancées
        recent_collaborations = [
            c for c in self.collaboration_history
            if c['timestamp'] > time.time() - 3600  # Dernière heure
        ]
        
        if recent_collaborations:
            avg_time = sum(c['execution_time'] for c in recent_collaborations) / len(recent_collaborations)
            success_rate = sum(1 for c in recent_collaborations if c['success']) / len(recent_collaborations)
            avg_quality = sum(c['result_quality'] for c in recent_collaborations) / len(recent_collaborations)
        else:
            avg_time = 0.0
            success_rate = 0.0
            avg_quality = 0.0
        
        return {
            **self.coordination_metrics,
            'recent_performance': {
                'avg_coordination_time': avg_time,
                'success_rate': success_rate,
                'avg_quality': avg_quality,
                'total_collaborations': len(recent_collaborations)
            },
            'agent_graph_stats': {
                'nodes': self.agent_graph.number_of_nodes(),
                'edges': self.agent_graph.number_of_edges(),
                'density': nx.density(self.agent_graph)
            }
        }

# Exemple d'utilisation
async def main():
    coordinator = AgentCoordinator()
    
    # Créer un workflow collaboratif
    workflow_id = await coordinator.create_workflow(
        name="Document Analysis Pipeline",
        pattern=CoordinationPattern.COLLABORATIVE,
        agents=["llm-agent-1", "ollama-agent-1"],
        steps=[
            {"agent": "llm-agent-1", "task": {"type": "analysis", "domain": "content"}},
            {"agent": "ollama-agent-1", "task": {"type": "analysis", "domain": "structure"}}
        ],
        initial_context={"document": "sample document content"}
    )
    
    # Exécuter le workflow
    result = await coordinator.execute_workflow(workflow_id)
    print(f"Workflow result: {json.dumps(result, indent=2)}")
    
    # Afficher les métriques
    metrics = await coordinator.get_coordination_metrics()
    print(f"Coordination metrics: {json.dumps(metrics, indent=2)}")

if __name__ == "__main__":
    asyncio.run(main())