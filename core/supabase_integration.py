#!/usr/bin/env python3
"""
Master Plan IA 2025 - Intégration Supabase
Intégration avec Supabase suivant les meilleures pratiques MCP
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import os
import yaml
from pathlib import Path

# Import du client Supabase officiel
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("⚠️ Supabase client not installed. Run: pip install supabase")

logger = logging.getLogger(__name__)

class SupabaseIntegration:
    """Intégration Supabase pour Master Plan IA 2025"""
    
    def __init__(self, config_path: str = "config/supabase.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.client: Optional[Client] = None
        self.is_connected = False
        
        # Statistiques
        self.stats = {
            'queries_executed': 0,
            'queries_failed': 0,
            'tables_accessed': set(),
            'last_query': None,
            'connection_time': None
        }
        
        if SUPABASE_AVAILABLE:
            self._initialize_client()
        else:
            logger.warning("Supabase client not available, using mock mode")
    
    def _load_config(self) -> Dict[str, Any]:
        """Charge la configuration Supabase"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    return yaml.safe_load(f)
            else:
                logger.warning(f"Config file not found: {self.config_path}")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading Supabase config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Configuration sécurisée - utilise les variables d'environnement"""
        
        # Essayer d'utiliser le système de configuration sécurisé
        try:
            from .secure_config import secure_config
            return {
                'project_url': secure_config.credentials.supabase_url,
                'anon_key': secure_config.credentials.supabase_anon_key,
                'read_only': True,
                'timeout': 30,
                'tables': {
                    'agents': 'agents',
                    'tasks': 'tasks',
                    'workflows': 'workflows',
                    'metrics': 'metrics',
                    'plugins': 'plugins',
                    'webhooks': 'webhooks',
                    'webhook_deliveries': 'webhook_deliveries',
                    'users': 'users',
                    'user_sessions': 'user_sessions'
                }
            }
        except Exception as e:
            logger.error(f"Could not load secure config: {e}")
        
        # Fallback vers les variables d'environnement
        project_url = os.getenv('SUPABASE_URL')
        anon_key = os.getenv('SUPABASE_ANON_KEY')
        
        if not project_url or not anon_key:
            logger.error("CRITICAL: Supabase credentials not found in environment variables")
            logger.error("Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables")
            raise ValueError("Missing required Supabase credentials")
        
        return {
            'project_url': project_url,
            'anon_key': anon_key,
            'read_only': True,
            'timeout': 30,
            'tables': {
                'agents': 'agents',
                'tasks': 'tasks',
                'workflows': 'workflows',
                'metrics': 'metrics',
                'plugins': 'plugins',
                'webhooks': 'webhooks',
                'webhook_deliveries': 'webhook_deliveries',
                'users': 'users',
                'user_sessions': 'user_sessions'
            }
        }
    
    def _initialize_client(self):
        """Initialise le client Supabase"""
        try:
            self.client = create_client(
                self.config['project_url'],
                self.config['anon_key']
            )
            self.is_connected = True
            self.stats['connection_time'] = datetime.now().isoformat()
            logger.info("✅ Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase client: {e}")
            self.is_connected = False
    
    async def health_check(self) -> Dict[str, Any]:
        """Vérifie la santé de la connexion Supabase"""
        if not self.is_connected or not self.client:
            return {
                'status': 'disconnected',
                'error': 'Client not initialized',
                'timestamp': datetime.now().isoformat()
            }
        
        try:
            # Test simple avec une requête vers une table
            table_name = list(self.config['tables'].values())[0]
            result = self.client.table(table_name).select('*').limit(1).execute()
            
            return {
                'status': 'healthy',
                'tables_accessible': len(self.config['tables']),
                'last_test': datetime.now().isoformat(),
                'stats': {
                    **self.stats,
                    'tables_accessed': list(self.stats['tables_accessed'])
                }
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    # Opérations CRUD
    
    async def insert_agent(self, agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insère un nouvel agent"""
        if not self.is_connected:
            return self._mock_result('insert', agent_data)
        
        try:
            result = self.client.table('agents').insert(agent_data).execute()
            self.stats['queries_executed'] += 1
            self.stats['tables_accessed'].add('agents')
            self.stats['last_query'] = datetime.now().isoformat()
            
            return {
                'success': True,
                'data': result.data,
                'operation': 'insert_agent'
            }
        except Exception as e:
            self.stats['queries_failed'] += 1
            logger.error(f"Error inserting agent: {e}")
            return {
                'success': False,
                'error': str(e),
                'operation': 'insert_agent'
            }
    
    async def get_agents(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Récupère les agents"""
        if not self.is_connected:
            return self._mock_agents()
        
        try:
            query = self.client.table('agents').select('*')
            
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)
            
            result = query.execute()
            self.stats['queries_executed'] += 1
            self.stats['tables_accessed'].add('agents')
            
            return result.data
        except Exception as e:
            self.stats['queries_failed'] += 1
            logger.error(f"Error getting agents: {e}")
            return []
    
    async def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Met à jour un agent"""
        if not self.is_connected:
            return self._mock_result('update', {'id': agent_id, **updates})
        
        try:
            result = self.client.table('agents').update(updates).eq('id', agent_id).execute()
            self.stats['queries_executed'] += 1
            self.stats['tables_accessed'].add('agents')
            
            return {
                'success': True,
                'data': result.data,
                'operation': 'update_agent'
            }
        except Exception as e:
            self.stats['queries_failed'] += 1
            logger.error(f"Error updating agent: {e}")
            return {
                'success': False,
                'error': str(e),
                'operation': 'update_agent'
            }
    
    async def insert_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insère une nouvelle tâche"""
        if not self.is_connected:
            return self._mock_result('insert', task_data)
        
        try:
            result = self.client.table('tasks').insert(task_data).execute()
            self.stats['queries_executed'] += 1
            self.stats['tables_accessed'].add('tasks')
            
            return {
                'success': True,
                'data': result.data,
                'operation': 'insert_task'
            }
        except Exception as e:
            self.stats['queries_failed'] += 1
            logger.error(f"Error inserting task: {e}")
            return {
                'success': False,
                'error': str(e),
                'operation': 'insert_task'
            }
    
    async def get_tasks(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Récupère les tâches"""
        if not self.is_connected:
            return self._mock_tasks()
        
        try:
            query = self.client.table('tasks').select('*')
            
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)
            
            result = query.order('created_at', desc=True).execute()
            self.stats['queries_executed'] += 1
            self.stats['tables_accessed'].add('tasks')
            
            return result.data
        except Exception as e:
            self.stats['queries_failed'] += 1
            logger.error(f"Error getting tasks: {e}")
            return []
    
    async def insert_metric(self, metric_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insère une métrique"""
        if not self.is_connected:
            return self._mock_result('insert', metric_data)
        
        try:
            result = self.client.table('metrics').insert(metric_data).execute()
            self.stats['queries_executed'] += 1
            self.stats['tables_accessed'].add('metrics')
            
            return {
                'success': True,
                'data': result.data,
                'operation': 'insert_metric'
            }
        except Exception as e:
            self.stats['queries_failed'] += 1
            logger.error(f"Error inserting metric: {e}")
            return {
                'success': False,
                'error': str(e),
                'operation': 'insert_metric'
            }
    
    async def get_metrics(self, 
                         metric_name: Optional[str] = None,
                         since: Optional[datetime] = None,
                         limit: int = 100) -> List[Dict[str, Any]]:
        """Récupère les métriques"""
        if not self.is_connected:
            return self._mock_metrics()
        
        try:
            query = self.client.table('metrics').select('*')
            
            if metric_name:
                query = query.eq('name', metric_name)
            
            if since:
                query = query.gte('timestamp', since.isoformat())
            
            result = query.order('timestamp', desc=True).limit(limit).execute()
            self.stats['queries_executed'] += 1
            self.stats['tables_accessed'].add('metrics')
            
            return result.data
        except Exception as e:
            self.stats['queries_failed'] += 1
            logger.error(f"Error getting metrics: {e}")
            return []
    
    async def insert_plugin_status(self, plugin_data: Dict[str, Any]) -> Dict[str, Any]:
        """Insère le statut d'un plugin"""
        if not self.is_connected:
            return self._mock_result('insert', plugin_data)
        
        try:
            # Upsert pour éviter les doublons
            result = self.client.table('plugins').upsert(plugin_data, on_conflict='name').execute()
            self.stats['queries_executed'] += 1
            self.stats['tables_accessed'].add('plugins')
            
            return {
                'success': True,
                'data': result.data,
                'operation': 'insert_plugin_status'
            }
        except Exception as e:
            self.stats['queries_failed'] += 1
            logger.error(f"Error inserting plugin status: {e}")
            return {
                'success': False,
                'error': str(e),
                'operation': 'insert_plugin_status'
            }
    
    async def get_plugins(self) -> List[Dict[str, Any]]:
        """Récupère les plugins"""
        if not self.is_connected:
            return self._mock_plugins()
        
        try:
            result = self.client.table('plugins').select('*').execute()
            self.stats['queries_executed'] += 1
            self.stats['tables_accessed'].add('plugins')
            
            return result.data
        except Exception as e:
            self.stats['queries_failed'] += 1
            logger.error(f"Error getting plugins: {e}")
            return []
    
    # Fonctions Mock pour les tests
    
    def _mock_result(self, operation: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Résultat simulé"""
        return {
            'success': True,
            'data': [{'id': 'mock-id', **data, 'created_at': datetime.now().isoformat()}],
            'operation': operation,
            'mock': True
        }
    
    def _mock_agents(self) -> List[Dict[str, Any]]:
        """Agents simulés"""
        return [
            {
                'id': 'agent-1',
                'name': 'LLM Agent',
                'type': 'llm',
                'status': 'active',
                'capabilities': ['text_generation', 'analysis'],
                'created_at': datetime.now().isoformat()
            },
            {
                'id': 'agent-2',
                'name': 'Claude Agent',
                'type': 'claude',
                'status': 'active',
                'capabilities': ['code_generation', 'debugging'],
                'created_at': datetime.now().isoformat()
            }
        ]
    
    def _mock_tasks(self) -> List[Dict[str, Any]]:
        """Tâches simulées"""
        return [
            {
                'id': 'task-1',
                'agent_id': 'agent-1',
                'type': 'analysis',
                'status': 'completed',
                'payload': {'text': 'Sample text'},
                'result': {'analysis': 'completed'},
                'created_at': datetime.now().isoformat()
            }
        ]
    
    def _mock_metrics(self) -> List[Dict[str, Any]]:
        """Métriques simulées"""
        return [
            {
                'id': 'metric-1',
                'name': 'task_execution_time',
                'value': 1.5,
                'tags': {'agent': 'agent-1'},
                'timestamp': datetime.now().isoformat()
            }
        ]
    
    def _mock_plugins(self) -> List[Dict[str, Any]]:
        """Plugins simulés"""
        return [
            {
                'id': 'plugin-1',
                'name': 'weather-agent',
                'version': '1.0.0',
                'type': 'agent',
                'status': 'active',
                'created_at': datetime.now().isoformat()
            }
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques"""
        return {
            **self.stats,
            'tables_accessed': list(self.stats['tables_accessed']),
            'is_connected': self.is_connected,
            'supabase_available': SUPABASE_AVAILABLE
        }

# Instance globale
supabase = SupabaseIntegration()

# Exemple d'utilisation
async def main():
    """Test de l'intégration Supabase"""
    
    print("🔗 Test de l'intégration Supabase")
    print("=" * 40)
    
    # Health check
    health = await supabase.health_check()
    print(f"Health check: {json.dumps(health, indent=2)}")
    
    # Test des agents
    print("\n📊 Test des agents...")
    agents = await supabase.get_agents()
    print(f"Agents: {len(agents)} trouvés")
    
    # Test d'insertion d'agent
    agent_data = {
        'name': 'Test Agent',
        'type': 'test',
        'status': 'active',
        'capabilities': ['test'],
        'config': {'test': True},
        'created_at': datetime.now().isoformat()
    }
    
    result = await supabase.insert_agent(agent_data)
    print(f"Insert result: {result}")
    
    # Test des métriques
    print("\n📈 Test des métriques...")
    metrics = await supabase.get_metrics(limit=5)
    print(f"Métriques: {len(metrics)} trouvées")
    
    # Statistiques
    stats = supabase.get_stats()
    print(f"\nStatistiques: {json.dumps(stats, indent=2)}")

if __name__ == "__main__":
    asyncio.run(main())