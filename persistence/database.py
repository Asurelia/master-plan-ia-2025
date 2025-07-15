#!/usr/bin/env python3
"""
Master Plan IA 2025 - Database Layer
Système de persistance avec SQLAlchemy
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
import sys
import os

# Ajouter le répertoire config au path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config'))

try:
    from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, Text, Boolean, Float
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker, Session
    from sqlalchemy.pool import StaticPool
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from settings import get_settings
except ImportError as e:
    logging.error(f"Database dependencies not available: {e}")
    # Fallback simple pour éviter les crashes
    class MockBase:
        pass
    
    declarative_base = lambda: MockBase
    Column = String = DateTime = JSON = Text = Boolean = Float = lambda *args, **kwargs: None
    create_engine = sessionmaker = lambda *args, **kwargs: None

logger = logging.getLogger(__name__)

# Base SQLAlchemy
Base = declarative_base()

class AgentRecord(Base):
    """Modèle de données pour les agents"""
    __tablename__ = 'agents'
    
    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    capabilities = Column(JSON)
    config = Column(JSON)
    max_concurrent_tasks = Column(Integer, default=3)
    current_tasks = Column(Integer, default=0)
    is_healthy = Column(Boolean, default=True)
    performance_metrics = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TaskRecord(Base):
    """Modèle de données pour les tâches"""
    __tablename__ = 'tasks'
    
    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    priority = Column(Integer, default=5)
    payload = Column(JSON)
    result = Column(JSON)
    error = Column(Text)
    assigned_agent = Column(String)
    max_retries = Column(Integer, default=3)
    retry_count = Column(Integer, default=0)
    timeout = Column(Integer, default=300)
    task_metadata = Column(JSON)  # Renommé pour éviter le conflit avec metadata réservé
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

class WorkflowRecord(Base):
    """Modèle de données pour les workflows"""
    __tablename__ = 'workflows'
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    pattern = Column(String, nullable=False)
    status = Column(String, nullable=False)
    agents = Column(JSON)
    steps = Column(JSON)
    results = Column(JSON)
    current_step = Column(Integer, default=0)
    context_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

class ContextRecord(Base):
    """Modèle de données pour les contextes"""
    __tablename__ = 'contexts'
    
    id = Column(String, primary_key=True)
    data = Column(JSON)
    context_metadata = Column(JSON)  # Renommé pour éviter le conflit avec metadata réservé
    version = Column(Integer, default=1)
    access_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class MetricRecord(Base):
    """Modèle de données pour les métriques"""
    __tablename__ = 'metrics'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    tags = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)
    source = Column(String)
    
class EventRecord(Base):
    """Modèle de données pour les événements"""
    __tablename__ = 'events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String, nullable=False)
    source = Column(String, nullable=False)
    data = Column(JSON)
    severity = Column(String, default='INFO')
    timestamp = Column(DateTime, default=datetime.utcnow)

# Configuration SQLite pour améliorer les performances
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Configure SQLite pour de meilleures performances"""
    if 'sqlite' in str(dbapi_connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=1000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()

class DatabaseManager:
    """Gestionnaire de base de données pour Master Plan IA 2025"""
    
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.engine = None
        self.SessionLocal = None
        self._initialized = False
    
    def initialize(self):
        """Initialise la connexion à la base de données"""
        if self._initialized:
            return
        
        try:
            db_config = self.settings.get_database_config()
            
            # Configuration spéciale pour SQLite
            if 'sqlite' in db_config['url']:
                self.engine = create_engine(
                    db_config['url'],
                    poolclass=StaticPool,
                    connect_args={
                        'check_same_thread': False,
                        'timeout': 30
                    },
                    echo=db_config.get('echo', False)
                )
            else:
                self.engine = create_engine(
                    db_config['url'],
                    pool_size=db_config.get('pool_size', 10),
                    max_overflow=db_config.get('max_overflow', 20),
                    echo=db_config.get('echo', False)
                )
            
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            # Créer les tables
            Base.metadata.create_all(bind=self.engine)
            
            self._initialized = True
            logger.info("✅ Database initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
    
    def get_session(self) -> Session:
        """Retourne une session de base de données"""
        if not self._initialized:
            self.initialize()
        
        return self.SessionLocal()
    
    def close(self):
        """Ferme la connexion à la base de données"""
        if self.engine:
            self.engine.dispose()
            self._initialized = False
    
    # Méthodes pour les agents
    def create_agent(self, agent_data: Dict[str, Any]) -> AgentRecord:
        """Crée un nouvel agent"""
        with self.get_session() as session:
            agent = AgentRecord(
                id=agent_data['id'],
                type=agent_data['type'],
                name=agent_data['name'],
                capabilities=agent_data.get('capabilities', []),
                config=agent_data.get('config', {}),
                max_concurrent_tasks=agent_data.get('max_concurrent_tasks', 3),
                performance_metrics=agent_data.get('performance_metrics', {})
            )
            session.add(agent)
            session.commit()
            session.refresh(agent)
            return agent
    
    def get_agent(self, agent_id: str) -> Optional[AgentRecord]:
        """Récupère un agent par son ID"""
        with self.get_session() as session:
            return session.query(AgentRecord).filter(AgentRecord.id == agent_id).first()
    
    def get_all_agents(self) -> List[AgentRecord]:
        """Récupère tous les agents"""
        with self.get_session() as session:
            return session.query(AgentRecord).all()
    
    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> Optional[AgentRecord]:
        """Met à jour un agent"""
        with self.get_session() as session:
            agent = session.query(AgentRecord).filter(AgentRecord.id == agent_id).first()
            if agent:
                for key, value in updates.items():
                    if hasattr(agent, key):
                        setattr(agent, key, value)
                agent.updated_at = datetime.utcnow()
                session.commit()
                session.refresh(agent)
            return agent
    
    def delete_agent(self, agent_id: str) -> bool:
        """Supprime un agent"""
        with self.get_session() as session:
            agent = session.query(AgentRecord).filter(AgentRecord.id == agent_id).first()
            if agent:
                session.delete(agent)
                session.commit()
                return True
            return False
    
    # Méthodes pour les tâches
    def create_task(self, task_data: Dict[str, Any]) -> TaskRecord:
        """Crée une nouvelle tâche"""
        with self.get_session() as session:
            task = TaskRecord(
                id=task_data['id'],
                type=task_data['type'],
                status=task_data['status'],
                priority=task_data.get('priority', 5),
                payload=task_data.get('payload', {}),
                assigned_agent=task_data.get('assigned_agent'),
                max_retries=task_data.get('max_retries', 3),
                timeout=task_data.get('timeout', 300),
                task_metadata=task_data.get('metadata', {})
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            return task
    
    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Récupère une tâche par son ID"""
        with self.get_session() as session:
            return session.query(TaskRecord).filter(TaskRecord.id == task_id).first()
    
    def get_tasks_by_status(self, status: str) -> List[TaskRecord]:
        """Récupère les tâches par statut"""
        with self.get_session() as session:
            return session.query(TaskRecord).filter(TaskRecord.status == status).all()
    
    def get_tasks_by_agent(self, agent_id: str) -> List[TaskRecord]:
        """Récupère les tâches d'un agent"""
        with self.get_session() as session:
            return session.query(TaskRecord).filter(TaskRecord.assigned_agent == agent_id).all()
    
    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Optional[TaskRecord]:
        """Met à jour une tâche"""
        with self.get_session() as session:
            task = session.query(TaskRecord).filter(TaskRecord.id == task_id).first()
            if task:
                for key, value in updates.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
                task.updated_at = datetime.utcnow()
                session.commit()
                session.refresh(task)
            return task
    
    # Méthodes pour les workflows
    def create_workflow(self, workflow_data: Dict[str, Any]) -> WorkflowRecord:
        """Crée un nouveau workflow"""
        with self.get_session() as session:
            workflow = WorkflowRecord(
                id=workflow_data['id'],
                name=workflow_data['name'],
                pattern=workflow_data['pattern'],
                status=workflow_data['status'],
                agents=workflow_data.get('agents', []),
                steps=workflow_data.get('steps', []),
                results=workflow_data.get('results', {}),
                context_id=workflow_data.get('context_id')
            )
            session.add(workflow)
            session.commit()
            session.refresh(workflow)
            return workflow
    
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowRecord]:
        """Récupère un workflow par son ID"""
        with self.get_session() as session:
            return session.query(WorkflowRecord).filter(WorkflowRecord.id == workflow_id).first()
    
    def get_workflows_by_status(self, status: str) -> List[WorkflowRecord]:
        """Récupère les workflows par statut"""
        with self.get_session() as session:
            return session.query(WorkflowRecord).filter(WorkflowRecord.status == status).all()
    
    def update_workflow(self, workflow_id: str, updates: Dict[str, Any]) -> Optional[WorkflowRecord]:
        """Met à jour un workflow"""
        with self.get_session() as session:
            workflow = session.query(WorkflowRecord).filter(WorkflowRecord.id == workflow_id).first()
            if workflow:
                for key, value in updates.items():
                    if hasattr(workflow, key):
                        setattr(workflow, key, value)
                workflow.updated_at = datetime.utcnow()
                session.commit()
                session.refresh(workflow)
            return workflow
    
    # Méthodes pour les contextes
    def create_context(self, context_data: Dict[str, Any]) -> ContextRecord:
        """Crée un nouveau contexte"""
        with self.get_session() as session:
            context = ContextRecord(
                id=context_data['id'],
                data=context_data.get('data', {}),
                context_metadata=context_data.get('metadata', {}),
                version=context_data.get('version', 1)
            )
            session.add(context)
            session.commit()
            session.refresh(context)
            return context
    
    def get_context(self, context_id: str) -> Optional[ContextRecord]:
        """Récupère un contexte par son ID"""
        with self.get_session() as session:
            return session.query(ContextRecord).filter(ContextRecord.id == context_id).first()
    
    def update_context(self, context_id: str, updates: Dict[str, Any]) -> Optional[ContextRecord]:
        """Met à jour un contexte"""
        with self.get_session() as session:
            context = session.query(ContextRecord).filter(ContextRecord.id == context_id).first()
            if context:
                for key, value in updates.items():
                    if hasattr(context, key):
                        setattr(context, key, value)
                context.updated_at = datetime.utcnow()
                context.access_count += 1
                session.commit()
                session.refresh(context)
            return context
    
    # Méthodes pour les métriques
    def create_metric(self, name: str, value: float, tags: Dict[str, str] = None, source: str = None) -> MetricRecord:
        """Crée une nouvelle métrique"""
        with self.get_session() as session:
            metric = MetricRecord(
                name=name,
                value=value,
                tags=tags or {},
                source=source
            )
            session.add(metric)
            session.commit()
            session.refresh(metric)
            return metric
    
    def get_metrics(self, name: str = None, source: str = None, limit: int = 100) -> List[MetricRecord]:
        """Récupère les métriques"""
        with self.get_session() as session:
            query = session.query(MetricRecord)
            
            if name:
                query = query.filter(MetricRecord.name == name)
            if source:
                query = query.filter(MetricRecord.source == source)
            
            return query.order_by(MetricRecord.timestamp.desc()).limit(limit).all()
    
    # Méthodes pour les événements
    def create_event(self, event_data: Dict[str, Any]) -> EventRecord:
        """Crée un nouvel événement"""
        with self.get_session() as session:
            event = EventRecord(
                type=event_data['type'],
                source=event_data['source'],
                data=event_data.get('data', {}),
                severity=event_data.get('severity', 'INFO')
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            return event
    
    def get_events(self, event_type: str = None, source: str = None, limit: int = 100) -> List[EventRecord]:
        """Récupère les événements"""
        with self.get_session() as session:
            query = session.query(EventRecord)
            
            if event_type:
                query = query.filter(EventRecord.type == event_type)
            if source:
                query = query.filter(EventRecord.source == source)
            
            return query.order_by(EventRecord.timestamp.desc()).limit(limit).all()
    
    # Méthodes utilitaires
    def get_system_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques du système"""
        with self.get_session() as session:
            stats = {
                'agents': {
                    'total': session.query(AgentRecord).count(),
                    'healthy': session.query(AgentRecord).filter(AgentRecord.is_healthy == True).count()
                },
                'tasks': {
                    'total': session.query(TaskRecord).count(),
                    'pending': session.query(TaskRecord).filter(TaskRecord.status == 'pending').count(),
                    'running': session.query(TaskRecord).filter(TaskRecord.status == 'running').count(),
                    'completed': session.query(TaskRecord).filter(TaskRecord.status == 'completed').count(),
                    'failed': session.query(TaskRecord).filter(TaskRecord.status == 'failed').count()
                },
                'workflows': {
                    'total': session.query(WorkflowRecord).count(),
                    'active': session.query(WorkflowRecord).filter(WorkflowRecord.status == 'running').count(),
                    'completed': session.query(WorkflowRecord).filter(WorkflowRecord.status == 'completed').count()
                }
            }
            return stats
    
    def cleanup_old_data(self, days: int = 30):
        """Nettoie les anciennes données"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        with self.get_session() as session:
            # Nettoyer les anciens événements
            deleted_events = session.query(EventRecord).filter(
                EventRecord.timestamp < cutoff_date
            ).delete()
            
            # Nettoyer les anciennes métriques
            deleted_metrics = session.query(MetricRecord).filter(
                MetricRecord.timestamp < cutoff_date
            ).delete()
            
            # Nettoyer les tâches terminées anciennes
            deleted_tasks = session.query(TaskRecord).filter(
                TaskRecord.updated_at < cutoff_date,
                TaskRecord.status.in_(['completed', 'failed'])
            ).delete()
            
            session.commit()
            
            logger.info(f"🧹 Cleanup completed: {deleted_events} events, {deleted_metrics} metrics, {deleted_tasks} tasks")

# Instance globale du gestionnaire de base de données
db_manager = DatabaseManager()

# Fonctions utilitaires
def get_database() -> DatabaseManager:
    """Retourne l'instance du gestionnaire de base de données"""
    return db_manager

def init_database():
    """Initialise la base de données"""
    db_manager.initialize()

# Test et initialisation
if __name__ == "__main__":
    init_database()
    
    # Test des fonctionnalités
    print("🧪 Testing database operations...")
    
    # Test création d'agent
    agent_data = {
        'id': 'test-agent',
        'type': 'test',
        'name': 'Test Agent',
        'capabilities': ['test'],
        'config': {'test': True}
    }
    
    agent = db_manager.create_agent(agent_data)
    print(f"✅ Agent created: {agent.id}")
    
    # Test récupération
    retrieved_agent = db_manager.get_agent('test-agent')
    print(f"✅ Agent retrieved: {retrieved_agent.name}")
    
    # Test statistiques
    stats = db_manager.get_system_stats()
    print(f"✅ System stats: {stats}")
    
    # Nettoyage
    db_manager.delete_agent('test-agent')
    print("✅ Test completed successfully")