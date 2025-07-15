#!/usr/bin/env python3
"""
Master Plan IA 2025 - Dashboard Server
Serveur web pour l'interface de monitoring
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import asyncio
import json
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import sys
import os
from pathlib import Path

# Ajouter le chemin core au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))

try:
    from advanced_metrics import metrics_system, get_metrics_dashboard
    from intelligent_coordinator import IntelligentCoordinator
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to import core modules: {e}")
    # Fallback pour éviter les crashes
    metrics_system = None
    get_metrics_dashboard = lambda: {"error": "Metrics system not available"}

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Master Plan IA 2025 - Dashboard",
    description="Interface de monitoring avancée",
    version="1.0.0"
)

# Configuration des templates et fichiers statiques
templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

# Gestionnaire de connexions WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected: {len(self.active_connections)} active connections")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected: {len(self.active_connections)} active connections")
    
    async def send_to_all(self, message: dict):
        """Envoie un message à toutes les connexions actives"""
        if not self.active_connections:
            return
        
        message_json = json.dumps(message)
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error(f"Error sending WebSocket message: {e}")
                disconnected.append(connection)
        
        # Nettoyer les connexions fermées
        for connection in disconnected:
            self.active_connections.remove(connection)

manager = ConnectionManager()

# Tâche de diffusion des métriques
async def broadcast_metrics():
    """Diffuse les métriques en temps réel"""
    while True:
        try:
            if manager.active_connections:
                dashboard_data = get_metrics_dashboard()
                await manager.send_to_all({
                    "type": "metrics_update",
                    "data": dashboard_data,
                    "timestamp": time.time()
                })
            
            await asyncio.sleep(5)  # Mise à jour toutes les 5 secondes
        except Exception as e:
            logger.error(f"Error in metrics broadcast: {e}")
            await asyncio.sleep(5)

# Démarrer la diffusion au démarrage
@app.on_event("startup")
async def startup_event():
    if metrics_system:
        metrics_system.start_auto_collection()
    asyncio.create_task(broadcast_metrics())

@app.on_event("shutdown")
async def shutdown_event():
    if metrics_system:
        metrics_system.stop_auto_collection()

# Routes principales
@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Page d'accueil du dashboard"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/health")
async def health_check():
    """Vérification de santé du dashboard"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "metrics_system": metrics_system is not None,
        "active_connections": len(manager.active_connections)
    }

@app.get("/api/metrics")
async def get_metrics():
    """Récupère les métriques actuelles"""
    return get_metrics_dashboard()

@app.get("/api/metrics/{metric_name}")
async def get_specific_metric(metric_name: str, since: Optional[float] = None):
    """Récupère une métrique spécifique"""
    if not metrics_system:
        raise HTTPException(status_code=503, detail="Metrics system not available")
    
    return metrics_system.get_metric_data(metric_name, since=since)

@app.get("/api/metrics/{metric_name}/timeseries")
async def get_metric_timeseries(
    metric_name: str,
    interval: int = 60,
    since: Optional[float] = None
):
    """Récupère une série temporelle"""
    if not metrics_system:
        raise HTTPException(status_code=503, detail="Metrics system not available")
    
    from advanced_metrics import MetricAggregation
    return metrics_system.get_time_series(
        metric_name,
        interval_seconds=interval,
        since=since,
        aggregation=MetricAggregation.AVG
    )

@app.get("/api/system/status")
async def get_system_status():
    """Récupère le statut du système"""
    try:
        # Importer les modules nécessaires
        sys.path.insert(0, str(Path(__file__).parent.parent / 'api'))
        from unified_api import orchestration_hub, agent_coordinator
        
        if orchestration_hub:
            hub_status = await orchestration_hub.get_system_status()
        else:
            hub_status = {"error": "Orchestration hub not available"}
        
        if agent_coordinator:
            coord_metrics = await agent_coordinator.get_coordination_metrics()
        else:
            coord_metrics = {"error": "Agent coordinator not available"}
        
        return {
            "timestamp": time.time(),
            "orchestration": hub_status,
            "coordination": coord_metrics,
            "dashboard": {
                "active_connections": len(manager.active_connections),
                "metrics_system": metrics_system is not None
            }
        }
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return {"error": str(e)}

@app.get("/api/agents")
async def get_agents():
    """Récupère la liste des agents"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / 'api'))
        from unified_api import orchestration_hub
        
        if orchestration_hub and hasattr(orchestration_hub, 'agents'):
            agents = []
            for agent_id, agent in orchestration_hub.agents.items():
                agents.append({
                    "id": agent.id,
                    "name": agent.name,
                    "type": agent.type.value if hasattr(agent.type, 'value') else str(agent.type),
                    "capabilities": agent.capabilities,
                    "is_healthy": agent.is_healthy,
                    "current_tasks": agent.current_tasks,
                    "max_concurrent_tasks": agent.max_concurrent_tasks,
                    "load_percentage": (agent.current_tasks / agent.max_concurrent_tasks) * 100
                })
            return {"agents": agents, "total": len(agents)}
        else:
            return {"agents": [], "total": 0, "error": "Orchestration hub not available"}
    except Exception as e:
        logger.error(f"Error getting agents: {e}")
        return {"error": str(e)}

@app.get("/api/workflows")
async def get_workflows():
    """Récupère la liste des workflows"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / 'api'))
        from unified_api import agent_coordinator
        
        if agent_coordinator and hasattr(agent_coordinator, 'workflows'):
            workflows = []
            for workflow_id, workflow in agent_coordinator.workflows.items():
                workflows.append({
                    "id": workflow.id,
                    "name": workflow.name,
                    "pattern": workflow.pattern.value if hasattr(workflow.pattern, 'value') else str(workflow.pattern),
                    "status": workflow.status,
                    "agents": workflow.agents,
                    "current_step": workflow.current_step,
                    "total_steps": len(workflow.steps),
                    "progress": (workflow.current_step / max(1, len(workflow.steps))) * 100,
                    "created_at": workflow.created_at
                })
            return {"workflows": workflows, "total": len(workflows)}
        else:
            return {"workflows": [], "total": 0, "error": "Agent coordinator not available"}
    except Exception as e:
        logger.error(f"Error getting workflows: {e}")
        return {"error": str(e)}

@app.get("/api/intelligence/metrics")
async def get_intelligence_metrics():
    """Récupère les métriques d'intelligence"""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / 'api'))
        from unified_api import agent_coordinator
        
        if hasattr(agent_coordinator, 'intelligent_coordinator'):
            coordinator = agent_coordinator.intelligent_coordinator
            return await coordinator.get_intelligence_metrics()
        else:
            return {"error": "Intelligent coordinator not available"}
    except Exception as e:
        logger.error(f"Error getting intelligence metrics: {e}")
        return {"error": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Endpoint WebSocket pour les mises à jour en temps réel"""
    await manager.connect(websocket)
    try:
        while True:
            # Maintenir la connexion active
            data = await websocket.receive_text()
            # Echo pour tester la connexion
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# API pour les actions
@app.post("/api/actions/scale_agent")
async def scale_agent(request: dict):
    """Scale un agent (augmente/diminue les instances)"""
    agent_id = request.get("agent_id")
    action = request.get("action")  # "scale_up" ou "scale_down"
    
    if not agent_id or not action:
        raise HTTPException(status_code=400, detail="agent_id and action required")
    
    # Simuler l'action de scaling
    await asyncio.sleep(0.5)
    
    result = {
        "success": True,
        "agent_id": agent_id,
        "action": action,
        "timestamp": time.time(),
        "message": f"Agent {agent_id} {action} completed"
    }
    
    # Notifier via WebSocket
    await manager.send_to_all({
        "type": "action_completed",
        "data": result
    })
    
    return result

@app.post("/api/actions/restart_agent")
async def restart_agent(request: dict):
    """Redémarre un agent"""
    agent_id = request.get("agent_id")
    
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id required")
    
    # Simuler le redémarrage
    await asyncio.sleep(1)
    
    result = {
        "success": True,
        "agent_id": agent_id,
        "action": "restart",
        "timestamp": time.time(),
        "message": f"Agent {agent_id} restarted successfully"
    }
    
    # Notifier via WebSocket
    await manager.send_to_all({
        "type": "action_completed",
        "data": result
    })
    
    return result

@app.post("/api/actions/update_strategy")
async def update_coordination_strategy(request: dict):
    """Met à jour la stratégie de coordination"""
    strategy = request.get("strategy")
    
    if not strategy:
        raise HTTPException(status_code=400, detail="strategy required")
    
    # Simuler la mise à jour
    await asyncio.sleep(0.2)
    
    result = {
        "success": True,
        "strategy": strategy,
        "timestamp": time.time(),
        "message": f"Coordination strategy updated to {strategy}"
    }
    
    # Notifier via WebSocket
    await manager.send_to_all({
        "type": "strategy_updated",
        "data": result
    })
    
    return result

# API pour les alertes
@app.get("/api/alerts")
async def get_alerts():
    """Récupère les alertes actives"""
    # Simuler des alertes
    alerts = [
        {
            "id": "alert-1",
            "type": "warning",
            "metric": "agent_load",
            "message": "Agent load above 80%",
            "value": 0.85,
            "threshold": 0.8,
            "timestamp": time.time() - 300,
            "agent_id": "agent-1"
        },
        {
            "id": "alert-2",
            "type": "info",
            "metric": "task_success_rate",
            "message": "Task success rate improved",
            "value": 0.92,
            "threshold": 0.9,
            "timestamp": time.time() - 600,
            "agent_id": "agent-2"
        }
    ]
    
    return {"alerts": alerts, "total": len(alerts)}

@app.get("/api/performance/report")
async def get_performance_report():
    """Génère un rapport de performance"""
    try:
        dashboard_data = get_metrics_dashboard()
        
        # Analyser les données pour le rapport
        report = {
            "timestamp": time.time(),
            "period": "last_24_hours",
            "summary": dashboard_data.get("summary", {}),
            "performance_score": dashboard_data.get("summary", {}).get("performance_score", 0.8),
            "key_metrics": {},
            "recommendations": [],
            "trends": {}
        }
        
        # Extraire les métriques clés
        metrics = dashboard_data.get("metrics", {})
        for metric_name, metric_data in metrics.items():
            if metric_data.get("latest_value") is not None:
                report["key_metrics"][metric_name] = {
                    "current": metric_data["latest_value"],
                    "trend": "stable",  # Placeholder
                    "status": "normal"
                }
        
        # Recommandations basées sur les métriques
        summary = dashboard_data.get("summary", {})
        if summary.get("overall_health") == "warning":
            report["recommendations"].append("Monitor system load and consider scaling")
        
        if summary.get("quality_score", 0) < 0.8:
            report["recommendations"].append("Review quality control processes")
        
        return report
        
    except Exception as e:
        logger.error(f"Error generating performance report: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "dashboard_server:app",
        host="0.0.0.0",
        port=5173,
        reload=True,
        log_level="info"
    )