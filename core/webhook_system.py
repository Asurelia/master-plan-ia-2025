#!/usr/bin/env python3
"""
Master Plan IA 2025 - Système de Webhooks
Système de webhooks pour les événements en temps réel
"""

import asyncio
import json
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Callable, Union
from enum import Enum
from dataclasses import dataclass, asdict
from pathlib import Path
import aiohttp
import hmac
import hashlib
from urllib.parse import urlparse

# Imports pour FastAPI
from fastapi import HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl, Field

# Import de notre intégration Supabase
from core.supabase_integration import supabase

logger = logging.getLogger(__name__)

class WebhookEvent(str, Enum):
    """Types d'événements webhook"""
    AGENT_CREATED = "agent.created"
    AGENT_UPDATED = "agent.updated"
    AGENT_DELETED = "agent.deleted"
    AGENT_HEALTH_CHANGED = "agent.health_changed"
    
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    
    WORKFLOW_CREATED = "workflow.created"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    
    METRIC_THRESHOLD = "metric.threshold"
    PLUGIN_LOADED = "plugin.loaded"
    PLUGIN_UNLOADED = "plugin.unloaded"

class WebhookStatus(str, Enum):
    """Status des webhooks"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"

@dataclass
class WebhookPayload:
    """Payload d'un webhook"""
    event: WebhookEvent
    timestamp: str
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    source: str = "master-plan-ia-2025"
    version: str = "1.0.0"
    id: str = None
    
    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())

class WebhookEndpoint(BaseModel):
    """Modèle pour un endpoint webhook"""
    url: HttpUrl
    events: List[WebhookEvent] = Field(default_factory=list)
    secret: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 5
    is_active: bool = True
    description: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)

class WebhookDelivery(BaseModel):
    """Modèle pour une livraison webhook"""
    id: str
    webhook_id: str
    event: WebhookEvent
    payload: Dict[str, Any]
    url: str
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = 3
    next_retry: Optional[datetime] = None
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    delivered_at: Optional[datetime] = None

class WebhookManager:
    """Gestionnaire de webhooks"""
    
    def __init__(self):
        self.endpoints: Dict[str, WebhookEndpoint] = {}
        self.delivery_queue: asyncio.Queue = asyncio.Queue()
        self.workers: List[asyncio.Task] = []
        self.is_running = False
        
        # Statistiques
        self.stats = {
            'total_webhooks': 0,
            'active_webhooks': 0,
            'total_deliveries': 0,
            'successful_deliveries': 0,
            'failed_deliveries': 0,
            'avg_response_time': 0,
            'last_delivery': None
        }
        
        # Configuration
        self.config = {
            'max_workers': 5,
            'rate_limit_per_minute': 60,
            'max_payload_size': 1024 * 1024,  # 1MB
            'signature_header': 'X-Webhook-Signature',
            'timestamp_header': 'X-Webhook-Timestamp',
            'event_header': 'X-Webhook-Event'
        }
        
        # Rate limiting
        self.rate_limits: Dict[str, List[float]] = {}
        
        logger.info("🔗 Webhook Manager initialized")
    
    async def start(self):
        """Démarre le gestionnaire de webhooks"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # Démarrer les workers
        for i in range(self.config['max_workers']):
            worker = asyncio.create_task(self._delivery_worker(f"worker-{i}"))
            self.workers.append(worker)
        
        # Charger les webhooks depuis la base
        await self._load_webhooks()
        
        logger.info(f"✅ Webhook Manager started with {len(self.workers)} workers")
    
    async def stop(self):
        """Arrête le gestionnaire de webhooks"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # Arrêter les workers
        for worker in self.workers:
            worker.cancel()
        
        # Attendre que tous les workers se terminent
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        
        logger.info("✅ Webhook Manager stopped")
    
    async def _load_webhooks(self):
        """Charge les webhooks depuis la base de données"""
        try:
            # Récupérer les webhooks depuis Supabase
            result = await supabase.client.table('webhooks').select('*').eq('is_active', True).execute()
            
            for webhook_data in result.data:
                endpoint = WebhookEndpoint(
                    url=webhook_data['url'],
                    events=[WebhookEvent(e) for e in webhook_data['events']],
                    secret=webhook_data.get('secret'),
                    headers=webhook_data.get('headers', {}),
                    timeout=webhook_data.get('timeout', 30),
                    max_retries=webhook_data.get('max_retries', 3),
                    retry_delay=webhook_data.get('retry_delay', 5),
                    is_active=webhook_data['is_active'],
                    description=webhook_data.get('description'),
                    filters=webhook_data.get('filters', {})
                )
                
                self.endpoints[webhook_data['id']] = endpoint
                self.stats['total_webhooks'] += 1
                if endpoint.is_active:
                    self.stats['active_webhooks'] += 1
            
            logger.info(f"📥 Loaded {len(self.endpoints)} webhooks from database")
            
        except Exception as e:
            logger.error(f"Error loading webhooks: {e}")
    
    async def register_webhook(self, endpoint: WebhookEndpoint) -> str:
        """Enregistre un nouveau webhook"""
        webhook_id = str(uuid.uuid4())
        
        try:
            # Valider l'URL
            parsed_url = urlparse(str(endpoint.url))
            if not parsed_url.scheme or not parsed_url.netloc:
                raise HTTPException(status_code=400, detail="Invalid webhook URL")
            
            # Sauvegarder dans la base
            webhook_data = {
                'id': webhook_id,
                'url': str(endpoint.url),
                'events': [e.value for e in endpoint.events],
                'secret': endpoint.secret,
                'headers': endpoint.headers,
                'timeout': endpoint.timeout,
                'max_retries': endpoint.max_retries,
                'retry_delay': endpoint.retry_delay,
                'is_active': endpoint.is_active,
                'description': endpoint.description,
                'filters': endpoint.filters,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            await supabase.client.table('webhooks').insert(webhook_data).execute()
            
            # Ajouter à la mémoire
            self.endpoints[webhook_id] = endpoint
            self.stats['total_webhooks'] += 1
            if endpoint.is_active:
                self.stats['active_webhooks'] += 1
            
            logger.info(f"✅ Webhook registered: {webhook_id} -> {endpoint.url}")
            
            return webhook_id
            
        except Exception as e:
            logger.error(f"Error registering webhook: {e}")
            raise HTTPException(status_code=500, detail="Failed to register webhook")
    
    async def unregister_webhook(self, webhook_id: str) -> bool:
        """Supprime un webhook"""
        try:
            if webhook_id not in self.endpoints:
                raise HTTPException(status_code=404, detail="Webhook not found")
            
            # Supprimer de la base
            await supabase.client.table('webhooks').delete().eq('id', webhook_id).execute()
            
            # Supprimer de la mémoire
            endpoint = self.endpoints.pop(webhook_id)
            self.stats['total_webhooks'] -= 1
            if endpoint.is_active:
                self.stats['active_webhooks'] -= 1
            
            logger.info(f"🗑️ Webhook unregistered: {webhook_id}")
            
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error unregistering webhook: {e}")
            return False
    
    async def update_webhook(self, webhook_id: str, updates: Dict[str, Any]) -> bool:
        """Met à jour un webhook"""
        try:
            if webhook_id not in self.endpoints:
                raise HTTPException(status_code=404, detail="Webhook not found")
            
            # Mettre à jour dans la base
            updates['updated_at'] = datetime.now(timezone.utc).isoformat()
            await supabase.client.table('webhooks').update(updates).eq('id', webhook_id).execute()
            
            # Mettre à jour en mémoire
            endpoint = self.endpoints[webhook_id]
            for key, value in updates.items():
                if hasattr(endpoint, key):
                    setattr(endpoint, key, value)
            
            logger.info(f"✅ Webhook updated: {webhook_id}")
            
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating webhook: {e}")
            return False
    
    async def trigger_event(self, event: WebhookEvent, data: Dict[str, Any], metadata: Dict[str, Any] = None):
        """Déclenche un événement webhook"""
        if not self.is_running:
            logger.warning("Webhook manager not running, skipping event")
            return
        
        if metadata is None:
            metadata = {}
        
        # Créer le payload
        payload = WebhookPayload(
            event=event,
            timestamp=datetime.now(timezone.utc).isoformat(),
            data=data,
            metadata=metadata
        )
        
        # Trouver les webhooks intéressés par cet événement
        matching_webhooks = []
        for webhook_id, endpoint in self.endpoints.items():
            if not endpoint.is_active:
                continue
            
            # Vérifier si l'événement correspond
            if not endpoint.events or event in endpoint.events:
                # Vérifier les filtres
                if self._matches_filters(payload, endpoint.filters):
                    matching_webhooks.append((webhook_id, endpoint))
        
        # Ajouter à la queue de livraison
        for webhook_id, endpoint in matching_webhooks:
            delivery = WebhookDelivery(
                id=str(uuid.uuid4()),
                webhook_id=webhook_id,
                event=event,
                payload=asdict(payload),
                url=str(endpoint.url),
                max_attempts=endpoint.max_retries,
                created_at=datetime.now(timezone.utc)
            )
            
            await self.delivery_queue.put((endpoint, delivery))
        
        logger.info(f"📤 Event {event.value} triggered for {len(matching_webhooks)} webhooks")
    
    def _matches_filters(self, payload: WebhookPayload, filters: Dict[str, Any]) -> bool:
        """Vérifie si un payload correspond aux filtres"""
        if not filters:
            return True
        
        # Implémenter la logique de filtrage
        # Par exemple: filtrer par agent_id, task_type, etc.
        for filter_key, filter_value in filters.items():
            if filter_key in payload.data:
                if payload.data[filter_key] != filter_value:
                    return False
        
        return True
    
    async def _delivery_worker(self, worker_name: str):
        """Worker pour livrer les webhooks"""
        logger.info(f"🚀 Delivery worker {worker_name} started")
        
        while self.is_running:
            try:
                # Récupérer une livraison de la queue
                endpoint, delivery = await asyncio.wait_for(
                    self.delivery_queue.get(), 
                    timeout=1.0
                )
                
                # Vérifier le rate limiting
                if not self._check_rate_limit(endpoint.url):
                    logger.warning(f"Rate limit exceeded for {endpoint.url}")
                    continue
                
                # Effectuer la livraison
                await self._deliver_webhook(endpoint, delivery)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in delivery worker {worker_name}: {e}")
                await asyncio.sleep(1)
        
        logger.info(f"🛑 Delivery worker {worker_name} stopped")
    
    def _check_rate_limit(self, url: str) -> bool:
        """Vérifie le rate limiting"""
        now = time.time()
        
        if url not in self.rate_limits:
            self.rate_limits[url] = []
        
        # Nettoyer les anciens timestamps
        cutoff = now - 60  # 1 minute
        self.rate_limits[url] = [t for t in self.rate_limits[url] if t > cutoff]
        
        # Vérifier la limite
        if len(self.rate_limits[url]) >= self.config['rate_limit_per_minute']:
            return False
        
        # Ajouter le timestamp actuel
        self.rate_limits[url].append(now)
        return True
    
    async def _deliver_webhook(self, endpoint: WebhookEndpoint, delivery: WebhookDelivery):
        """Livre un webhook"""
        start_time = time.time()
        
        try:
            # Préparer les headers
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Master-Plan-IA-2025/1.0',
                self.config['event_header']: delivery.event.value,
                self.config['timestamp_header']: delivery.payload['timestamp']
            }
            
            # Ajouter les headers personnalisés
            headers.update(endpoint.headers)
            
            # Créer la signature si un secret est configuré
            if endpoint.secret:
                signature = self._create_signature(
                    json.dumps(delivery.payload, sort_keys=True),
                    endpoint.secret
                )
                headers[self.config['signature_header']] = signature
            
            # Effectuer la requête
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=endpoint.timeout)) as session:
                async with session.post(
                    delivery.url,
                    json=delivery.payload,
                    headers=headers
                ) as response:
                    delivery.response_status = response.status
                    delivery.response_body = await response.text()
                    
                    if response.status < 400:
                        delivery.status = "delivered"
                        delivery.delivered_at = datetime.now(timezone.utc)
                        self.stats['successful_deliveries'] += 1
                        logger.info(f"✅ Webhook delivered: {delivery.id} -> {delivery.url}")
                    else:
                        delivery.status = "failed"
                        delivery.error_message = f"HTTP {response.status}: {delivery.response_body}"
                        self.stats['failed_deliveries'] += 1
                        logger.warning(f"❌ Webhook failed: {delivery.id} -> {delivery.url} (HTTP {response.status})")
        
        except Exception as e:
            delivery.status = "failed"
            delivery.error_message = str(e)
            self.stats['failed_deliveries'] += 1
            logger.error(f"❌ Webhook delivery error: {delivery.id} -> {delivery.url}: {e}")
        
        finally:
            # Mettre à jour les statistiques
            delivery.attempts += 1
            response_time = time.time() - start_time
            self.stats['avg_response_time'] = (self.stats['avg_response_time'] + response_time) / 2
            self.stats['total_deliveries'] += 1
            self.stats['last_delivery'] = datetime.now(timezone.utc).isoformat()
            
            # Sauvegarder la livraison
            await self._save_delivery(delivery)
            
            # Programmer un retry si nécessaire
            if delivery.status == "failed" and delivery.attempts < delivery.max_attempts:
                retry_delay = endpoint.retry_delay * (2 ** (delivery.attempts - 1))  # Exponential backoff
                delivery.next_retry = datetime.now(timezone.utc) + asyncio.timedelta(seconds=retry_delay)
                
                # Reprogrammer la livraison
                await asyncio.sleep(retry_delay)
                await self.delivery_queue.put((endpoint, delivery))
    
    def _create_signature(self, payload: str, secret: str) -> str:
        """Crée une signature HMAC"""
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"
    
    async def _save_delivery(self, delivery: WebhookDelivery):
        """Sauvegarde une livraison"""
        try:
            delivery_data = {
                'id': delivery.id,
                'webhook_id': delivery.webhook_id,
                'event': delivery.event.value,
                'payload': delivery.payload,
                'url': delivery.url,
                'status': delivery.status,
                'attempts': delivery.attempts,
                'max_attempts': delivery.max_attempts,
                'response_status': delivery.response_status,
                'response_body': delivery.response_body,
                'error_message': delivery.error_message,
                'created_at': delivery.created_at.isoformat(),
                'delivered_at': delivery.delivered_at.isoformat() if delivery.delivered_at else None,
                'next_retry': delivery.next_retry.isoformat() if delivery.next_retry else None
            }
            
            await supabase.client.table('webhook_deliveries').upsert(delivery_data, on_conflict='id').execute()
            
        except Exception as e:
            logger.error(f"Error saving delivery: {e}")
    
    async def get_webhooks(self) -> List[Dict[str, Any]]:
        """Récupère tous les webhooks"""
        webhooks = []
        
        for webhook_id, endpoint in self.endpoints.items():
            webhooks.append({
                'id': webhook_id,
                'url': str(endpoint.url),
                'events': [e.value for e in endpoint.events],
                'is_active': endpoint.is_active,
                'description': endpoint.description,
                'timeout': endpoint.timeout,
                'max_retries': endpoint.max_retries
            })
        
        return webhooks
    
    async def get_webhook(self, webhook_id: str) -> Optional[Dict[str, Any]]:
        """Récupère un webhook spécifique"""
        if webhook_id not in self.endpoints:
            return None
        
        endpoint = self.endpoints[webhook_id]
        return {
            'id': webhook_id,
            'url': str(endpoint.url),
            'events': [e.value for e in endpoint.events],
            'is_active': endpoint.is_active,
            'description': endpoint.description,
            'timeout': endpoint.timeout,
            'max_retries': endpoint.max_retries,
            'headers': endpoint.headers,
            'filters': endpoint.filters
        }
    
    async def get_deliveries(self, webhook_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Récupère les livraisons"""
        try:
            query = supabase.client.table('webhook_deliveries').select('*')
            
            if webhook_id:
                query = query.eq('webhook_id', webhook_id)
            
            result = query.order('created_at', desc=True).limit(limit).execute()
            
            return result.data
            
        except Exception as e:
            logger.error(f"Error getting deliveries: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques"""
        return {
            **self.stats,
            'queue_size': self.delivery_queue.qsize(),
            'workers_count': len(self.workers),
            'is_running': self.is_running,
            'endpoints_count': len(self.endpoints),
            'rate_limits': {url: len(timestamps) for url, timestamps in self.rate_limits.items()}
        }
    
    # Méthodes d'événements spécifiques
    
    async def on_agent_created(self, agent_data: Dict[str, Any]):
        """Événement: agent créé"""
        await self.trigger_event(WebhookEvent.AGENT_CREATED, agent_data)
    
    async def on_task_completed(self, task_data: Dict[str, Any]):
        """Événement: tâche complétée"""
        await self.trigger_event(WebhookEvent.TASK_COMPLETED, task_data)
    
    async def on_workflow_failed(self, workflow_data: Dict[str, Any]):
        """Événement: workflow échoué"""
        await self.trigger_event(WebhookEvent.WORKFLOW_FAILED, workflow_data)
    
    async def on_system_error(self, error_data: Dict[str, Any]):
        """Événement: erreur système"""
        await self.trigger_event(WebhookEvent.SYSTEM_ERROR, error_data)
    
    async def on_metric_threshold(self, metric_data: Dict[str, Any]):
        """Événement: seuil métrique dépassé"""
        await self.trigger_event(WebhookEvent.METRIC_THRESHOLD, metric_data)

# Instance globale
webhook_manager = WebhookManager()

# Exemple d'utilisation
async def main():
    """Test du système de webhooks"""
    
    print("🔗 Test du système de webhooks")
    print("=" * 40)
    
    # Démarrer le gestionnaire
    await webhook_manager.start()
    
    # Enregistrer un webhook de test
    test_endpoint = WebhookEndpoint(
        url="https://webhook.site/test",
        events=[WebhookEvent.TASK_COMPLETED, WebhookEvent.AGENT_CREATED],
        description="Test webhook"
    )
    
    webhook_id = await webhook_manager.register_webhook(test_endpoint)
    print(f"✅ Webhook enregistré: {webhook_id}")
    
    # Déclencher quelques événements
    await webhook_manager.on_agent_created({
        "agent_id": "agent-1",
        "agent_type": "llm",
        "name": "Test Agent"
    })
    
    await webhook_manager.on_task_completed({
        "task_id": "task-1",
        "task_type": "analysis",
        "result": "success"
    })
    
    # Attendre un peu pour les livraisons
    await asyncio.sleep(5)
    
    # Afficher les statistiques
    stats = webhook_manager.get_stats()
    print(f"\nStatistiques: {json.dumps(stats, indent=2)}")
    
    # Arrêter le gestionnaire
    await webhook_manager.stop()

if __name__ == "__main__":
    asyncio.run(main())