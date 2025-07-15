#!/usr/bin/env python3
"""
Master Plan IA 2025 - Orchestration Hub
Hub central d'orchestration intégrant le monitoring multi-IA
"""

import asyncio
import json
import time
import uuid
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from pathlib import Path
import sys

# Intégration du monitoring multi-IA existant
sys.path.append('/home/rafai/observability/adapters')
from llm_session_monitor import LLMSessionMonitor
from ollama_monitor import OllamaMonitor

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class AgentType(Enum):
    CLAUDE_CODE = "claude-code"
    LLM_SESSION = "llm-session"
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    CUSTOM = "custom"

@dataclass
class Task:
    id: str
    type: str
    payload: Dict[str, Any]
    priority: int = 5
    max_retries: int = 3
    timeout: int = 300
    created_at: float = None
    assigned_agent: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.metadata is None:
            self.metadata = {}

@dataclass
class Agent:
    id: str
    type: AgentType
    name: str
    capabilities: List[str]
    max_concurrent_tasks: int = 3
    current_tasks: int = 0
    is_healthy: bool = True
    last_heartbeat: float = None
    config: Dict[str, Any] = None
    performance_metrics: Dict[str, float] = None

    def __post_init__(self):
        if self.config is None:
            self.config = {}
        if self.performance_metrics is None:
            self.performance_metrics = {
                'avg_response_time': 0.0,
                'success_rate': 1.0,
                'error_rate': 0.0,
                'cost_per_task': 0.0
            }

class OrchestrationHub:
    """
    Hub central d'orchestration pour Master Plan IA 2025
    Intègre le monitoring multi-IA existant
    """
    
    def __init__(self, observability_server: str = "http://localhost:4000"):
        self.observability_server = observability_server
        self.agents: Dict[str, Agent] = {}
        self.tasks: Dict[str, Task] = {}
        self.task_queue: List[str] = []
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.session_id = f"orchestration-{uuid.uuid4().hex[:8]}"
        
        # Intégration monitoring multi-IA
        self.monitors = {
            'llm_session': LLMSessionMonitor(
                server_url=observability_server,
                session_name="orchestration-llm",
                monitor_interval=1.0
            ),
            'ollama': OllamaMonitor(
                server_url=observability_server,
                session_name="orchestration-ollama",
                monitor_interval=1.0
            )
        }
        
        # Métriques système
        self.metrics = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'avg_processing_time': 0.0,
            'system_load': 0.0,
            'active_agents': 0
        }
        
        # Callbacks pour événements
        self.event_callbacks: Dict[str, List[Callable]] = {
            'task_created': [],
            'task_assigned': [],
            'task_completed': [],
            'task_failed': [],
            'agent_registered': [],
            'agent_unhealthy': []
        }
        
        logger.info(f"🚀 Orchestration Hub initialized - Session: {self.session_id}")
    
    async def register_agent(self, agent: Agent) -> bool:
        """Enregistre un nouvel agent dans le hub"""
        try:
            self.agents[agent.id] = agent
            agent.last_heartbeat = time.time()
            
            # Notification monitoring
            await self.send_monitoring_event("AgentRegistered", {
                "agent_id": agent.id,
                "agent_type": agent.type.value,
                "capabilities": agent.capabilities,
                "max_concurrent_tasks": agent.max_concurrent_tasks
            })
            
            # Déclencher callbacks
            await self.trigger_event('agent_registered', agent)
            
            logger.info(f"✅ Agent registered: {agent.id} ({agent.type.value})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to register agent {agent.id}: {e}")
            return False
    
    async def submit_task(self, task: Task) -> str:
        """Soumet une nouvelle tâche au hub"""
        try:
            task.id = task.id or f"task-{uuid.uuid4().hex[:8]}"
            self.tasks[task.id] = task
            self.task_queue.append(task.id)
            self.metrics['total_tasks'] += 1
            
            # Notification monitoring
            await self.send_monitoring_event("TaskSubmitted", {
                "task_id": task.id,
                "task_type": task.type,
                "priority": task.priority,
                "payload_size": len(json.dumps(task.payload))
            })
            
            # Déclencher callbacks
            await self.trigger_event('task_created', task)
            
            # Essayer d'assigner immédiatement
            await self.process_task_queue()
            
            logger.info(f"📋 Task submitted: {task.id} ({task.type})")
            return task.id
            
        except Exception as e:
            logger.error(f"❌ Failed to submit task: {e}")
            raise
    
    async def process_task_queue(self):
        """Traite la file d'attente des tâches"""
        while self.task_queue:
            task_id = self.task_queue[0]
            task = self.tasks.get(task_id)
            
            if not task or task.status != TaskStatus.PENDING:
                self.task_queue.pop(0)
                continue
            
            # Trouver un agent disponible
            agent = await self.find_best_agent(task)
            if not agent:
                break  # Pas d'agent disponible
            
            # Assigner la tâche
            await self.assign_task(task, agent)
            self.task_queue.pop(0)
    
    async def find_best_agent(self, task: Task) -> Optional[Agent]:
        """Trouve le meilleur agent pour une tâche"""
        candidates = []
        
        for agent in self.agents.values():
            if not agent.is_healthy:
                continue
            
            if agent.current_tasks >= agent.max_concurrent_tasks:
                continue
            
            # Vérifier les capacités
            if task.type not in agent.capabilities:
                continue
            
            # Calculer le score (plus bas = meilleur)
            score = self.calculate_agent_score(agent, task)
            candidates.append((score, agent))
        
        if not candidates:
            return None
        
        # Retourner le meilleur agent
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    
    def calculate_agent_score(self, agent: Agent, task: Task) -> float:
        """Calcule le score d'un agent pour une tâche"""
        # Facteurs de score
        load_factor = agent.current_tasks / agent.max_concurrent_tasks
        performance_factor = 1.0 - agent.performance_metrics['success_rate']
        response_time_factor = agent.performance_metrics['avg_response_time'] / 1000.0
        cost_factor = agent.performance_metrics['cost_per_task']
        
        # Score composite (plus bas = meilleur)
        score = (
            load_factor * 0.3 +
            performance_factor * 0.3 +
            response_time_factor * 0.2 +
            cost_factor * 0.2
        )
        
        return score
    
    async def assign_task(self, task: Task, agent: Agent):
        """Assigne une tâche à un agent"""
        try:
            task.assigned_agent = agent.id
            task.status = TaskStatus.RUNNING
            agent.current_tasks += 1
            
            # Notification monitoring
            await self.send_monitoring_event("TaskAssigned", {
                "task_id": task.id,
                "agent_id": agent.id,
                "agent_type": agent.type.value,
                "assignment_time": time.time()
            })
            
            # Déclencher callbacks
            await self.trigger_event('task_assigned', task, agent)
            
            # Démarrer l'exécution
            execution_task = asyncio.create_task(
                self.execute_task(task, agent)
            )
            self.running_tasks[task.id] = execution_task
            
            logger.info(f"⚡ Task assigned: {task.id} -> {agent.id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to assign task {task.id}: {e}")
            await self.mark_task_failed(task, str(e))
    
    async def execute_task(self, task: Task, agent: Agent):
        """Exécute une tâche sur un agent"""
        start_time = time.time()
        
        try:
            # Simulation de l'exécution de tâche
            # Dans une vraie implémentation, cela appellerait l'agent approprié
            await asyncio.sleep(0.1)  # Simulation
            
            # Exemple d'exécution basée sur le type d'agent
            if agent.type == AgentType.LLM_SESSION:
                result = await self.execute_llm_session_task(task, agent)
            elif agent.type == AgentType.OLLAMA:
                result = await self.execute_ollama_task(task, agent)
            elif agent.type == AgentType.CLAUDE_CODE:
                result = await self.execute_claude_code_task(task, agent)
            else:
                result = await self.execute_generic_task(task, agent)
            
            # Marquer comme terminé
            await self.mark_task_completed(task, result)
            
            # Mettre à jour les métriques de l'agent
            execution_time = time.time() - start_time
            await self.update_agent_metrics(agent, execution_time, True)
            
        except Exception as e:
            logger.error(f"❌ Task execution failed: {task.id} - {e}")
            await self.mark_task_failed(task, str(e))
            await self.update_agent_metrics(agent, time.time() - start_time, False)
        finally:
            agent.current_tasks -= 1
            if task.id in self.running_tasks:
                del self.running_tasks[task.id]
    
    async def execute_llm_session_task(self, task: Task, agent: Agent) -> Dict[str, Any]:
        """Exécute une tâche LLM Session"""
        # Intégration avec le monitoring LLM Session
        monitor = self.monitors['llm_session']
        
        # Simulation d'exécution
        await asyncio.sleep(0.5)
        
        return {
            "provider": "llm-session",
            "model": task.payload.get("model", "gpt-4"),
            "response": f"LLM Session response for: {task.payload.get('prompt', 'No prompt')}",
            "tokens": 150,
            "cost": 0.003
        }
    
    async def execute_ollama_task(self, task: Task, agent: Agent) -> Dict[str, Any]:
        """Exécute une tâche Ollama"""
        # Intégration avec le monitoring Ollama
        monitor = self.monitors['ollama']
        
        # Simulation d'exécution
        await asyncio.sleep(0.8)
        
        return {
            "provider": "ollama",
            "model": task.payload.get("model", "llama2"),
            "response": f"Ollama response for: {task.payload.get('prompt', 'No prompt')}",
            "tokens": 120,
            "cost": 0.0  # Local, gratuit
        }
    
    async def execute_claude_code_task(self, task: Task, agent: Agent) -> Dict[str, Any]:
        """Exécute une tâche Claude Code"""
        # Simulation d'exécution
        await asyncio.sleep(0.6)
        
        return {
            "provider": "claude-code",
            "model": "claude-3-sonnet",
            "response": f"Claude Code response for: {task.payload.get('prompt', 'No prompt')}",
            "tokens": 200,
            "cost": 0.015
        }
    
    async def execute_generic_task(self, task: Task, agent: Agent) -> Dict[str, Any]:
        """Exécute une tâche générique"""
        await asyncio.sleep(0.3)
        
        return {
            "provider": "generic",
            "model": "unknown",
            "response": f"Generic response for: {task.payload.get('prompt', 'No prompt')}",
            "tokens": 100,
            "cost": 0.001
        }
    
    async def mark_task_completed(self, task: Task, result: Dict[str, Any]):
        """Marque une tâche comme terminée"""
        task.status = TaskStatus.COMPLETED
        task.result = result
        self.metrics['completed_tasks'] += 1
        
        # Notification monitoring
        await self.send_monitoring_event("TaskCompleted", {
            "task_id": task.id,
            "execution_time": time.time() - task.created_at,
            "result_size": len(json.dumps(result)),
            "tokens_used": result.get("tokens", 0),
            "cost": result.get("cost", 0.0)
        })
        
        # Déclencher callbacks
        await self.trigger_event('task_completed', task, result)
        
        logger.info(f"✅ Task completed: {task.id}")
    
    async def mark_task_failed(self, task: Task, error: str):
        """Marque une tâche comme échouée"""
        task.status = TaskStatus.FAILED
        task.error = error
        self.metrics['failed_tasks'] += 1
        
        # Notification monitoring
        await self.send_monitoring_event("TaskFailed", {
            "task_id": task.id,
            "error": error,
            "execution_time": time.time() - task.created_at
        })
        
        # Déclencher callbacks
        await self.trigger_event('task_failed', task, error)
        
        logger.error(f"❌ Task failed: {task.id} - {error}")
    
    async def update_agent_metrics(self, agent: Agent, execution_time: float, success: bool):
        """Met à jour les métriques d'un agent"""
        metrics = agent.performance_metrics
        
        # Mise à jour temps de réponse moyen
        alpha = 0.1  # Facteur de lissage
        metrics['avg_response_time'] = (
            alpha * execution_time + 
            (1 - alpha) * metrics['avg_response_time']
        )
        
        # Mise à jour taux de succès
        if success:
            metrics['success_rate'] = (
                alpha * 1.0 + 
                (1 - alpha) * metrics['success_rate']
            )
        else:
            metrics['success_rate'] = (
                alpha * 0.0 + 
                (1 - alpha) * metrics['success_rate']
            )
        
        metrics['error_rate'] = 1.0 - metrics['success_rate']
        
        # Heartbeat
        agent.last_heartbeat = time.time()
    
    async def send_monitoring_event(self, event_type: str, payload: Dict[str, Any]):
        """Envoie un événement au système de monitoring"""
        try:
            # Utiliser le système de monitoring existant
            event = {
                "source_app": "orchestration-hub",
                "session_id": self.session_id,
                "hook_event_type": event_type,
                "payload": payload,
                "ai_provider": "orchestration",
                "timestamp": int(time.time() * 1000)
            }
            
            # Envoyer via le monitor approprié
            if 'llm_session' in self.monitors:
                await asyncio.to_thread(
                    self.monitors['llm_session'].send_event,
                    event_type, payload
                )
            
        except Exception as e:
            logger.error(f"❌ Failed to send monitoring event: {e}")
    
    async def trigger_event(self, event_type: str, *args):
        """Déclenche les callbacks d'événements"""
        if event_type in self.event_callbacks:
            for callback in self.event_callbacks[event_type]:
                try:
                    await callback(*args)
                except Exception as e:
                    logger.error(f"❌ Event callback failed: {e}")
    
    def add_event_callback(self, event_type: str, callback: Callable):
        """Ajoute un callback d'événement"""
        if event_type not in self.event_callbacks:
            self.event_callbacks[event_type] = []
        self.event_callbacks[event_type].append(callback)
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Retourne le statut du système"""
        healthy_agents = sum(1 for agent in self.agents.values() if agent.is_healthy)
        
        return {
            "session_id": self.session_id,
            "uptime": time.time() - (self.metrics.get('start_time', time.time())),
            "agents": {
                "total": len(self.agents),
                "healthy": healthy_agents,
                "unhealthy": len(self.agents) - healthy_agents,
                "active": sum(agent.current_tasks for agent in self.agents.values())
            },
            "tasks": {
                "total": self.metrics['total_tasks'],
                "completed": self.metrics['completed_tasks'],
                "failed": self.metrics['failed_tasks'],
                "running": len(self.running_tasks),
                "queued": len(self.task_queue)
            },
            "performance": {
                "success_rate": (
                    self.metrics['completed_tasks'] / max(1, self.metrics['total_tasks'])
                ),
                "avg_processing_time": self.metrics['avg_processing_time'],
                "system_load": self.metrics['system_load']
            }
        }
    
    async def shutdown(self):
        """Arrêt propre du hub"""
        logger.info("🛑 Shutting down Orchestration Hub...")
        
        # Annuler toutes les tâches en cours
        for task_id, task in self.running_tasks.items():
            task.cancel()
        
        # Attendre la fin des tâches
        if self.running_tasks:
            await asyncio.gather(*self.running_tasks.values(), return_exceptions=True)
        
        # Notification monitoring
        await self.send_monitoring_event("OrchestrationShutdown", {
            "session_id": self.session_id,
            "total_tasks_processed": self.metrics['total_tasks'],
            "uptime": time.time() - (self.metrics.get('start_time', time.time()))
        })
        
        logger.info("✅ Orchestration Hub shutdown complete")

# Exemple d'utilisation
async def main():
    # Créer le hub d'orchestration
    hub = OrchestrationHub()
    
    # Enregistrer des agents
    await hub.register_agent(Agent(
        id="llm-agent-1",
        type=AgentType.LLM_SESSION,
        name="LLM Session Agent",
        capabilities=["text_generation", "code_analysis", "translation"]
    ))
    
    await hub.register_agent(Agent(
        id="ollama-agent-1",
        type=AgentType.OLLAMA,
        name="Ollama Local Agent",
        capabilities=["text_generation", "code_generation", "summarization"]
    ))
    
    # Soumettre des tâches
    task1 = Task(
        type="text_generation",
        payload={"prompt": "Explain quantum computing in simple terms"}
    )
    
    task2 = Task(
        type="code_generation",
        payload={"prompt": "Create a Python function to calculate fibonacci numbers"}
    )
    
    task_id1 = await hub.submit_task(task1)
    task_id2 = await hub.submit_task(task2)
    
    # Attendre quelques secondes
    await asyncio.sleep(3)
    
    # Afficher le statut
    status = await hub.get_system_status()
    print(f"System Status: {json.dumps(status, indent=2)}")
    
    # Arrêt propre
    await hub.shutdown()

if __name__ == "__main__":
    asyncio.run(main())