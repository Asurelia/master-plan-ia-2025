#!/usr/bin/env python3
"""
Master Plan IA 2025 - Plugin System
Système de plugins extensible pour ajouter des fonctionnalités
"""

import asyncio
import json
import time
import importlib
import inspect
import sys
import os
from typing import Dict, List, Any, Optional, Callable, Type, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import logging
from abc import ABC, abstractmethod
import traceback
from functools import wraps
import yaml

logger = logging.getLogger(__name__)

class PluginType(Enum):
    """Types de plugins"""
    AGENT = "agent"                    # Nouveaux types d'agents
    COORDINATION = "coordination"      # Patterns de coordination
    METRICS = "metrics"               # Collecteurs de métriques
    WORKFLOW = "workflow"             # Types de workflows
    API = "api"                       # Extensions d'API
    CACHE = "cache"                   # Stratégies de cache
    SCHEDULER = "scheduler"           # Planificateurs de tâches
    NOTIFICATION = "notification"     # Systèmes de notification
    TRANSFORMER = "transformer"      # Transformateurs de données
    VALIDATOR = "validator"           # Validateurs personnalisés

class PluginStatus(Enum):
    """Statuts des plugins"""
    INACTIVE = "inactive"
    LOADING = "loading"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"

@dataclass
class PluginManifest:
    """Manifeste d'un plugin"""
    name: str
    version: str
    description: str
    author: str
    plugin_type: PluginType
    entry_point: str
    dependencies: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    api_version: str = "1.0"
    license: str = "MIT"
    homepage: str = ""
    tags: List[str] = field(default_factory=list)
    min_python_version: str = "3.9"
    permissions: List[str] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PluginManifest':
        """Crée un manifeste depuis un dictionnaire"""
        if 'plugin_type' in data:
            data['plugin_type'] = PluginType(data['plugin_type'])
        return cls(**data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        data = {
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'author': self.author,
            'plugin_type': self.plugin_type.value,
            'entry_point': self.entry_point,
            'dependencies': self.dependencies,
            'config_schema': self.config_schema,
            'api_version': self.api_version,
            'license': self.license,
            'homepage': self.homepage,
            'tags': self.tags,
            'min_python_version': self.min_python_version,
            'permissions': self.permissions
        }
        return data

@dataclass
class PluginInfo:
    """Informations d'un plugin chargé"""
    manifest: PluginManifest
    instance: Any
    status: PluginStatus
    load_time: float
    error_message: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour l'API"""
        return {
            'manifest': self.manifest.to_dict(),
            'status': self.status.value,
            'load_time': self.load_time,
            'error_message': self.error_message,
            'config': self.config,
            'metrics': self.metrics
        }

class PluginInterface(ABC):
    """Interface de base pour tous les plugins"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.is_initialized = False
        self.name = getattr(self, 'PLUGIN_NAME', self.__class__.__name__)
        self.version = getattr(self, 'PLUGIN_VERSION', '1.0.0')
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialise le plugin"""
        pass
    
    @abstractmethod
    async def shutdown(self) -> bool:
        """Arrête le plugin proprement"""
        pass
    
    async def get_status(self) -> Dict[str, Any]:
        """Retourne le statut du plugin"""
        return {
            'name': self.name,
            'version': self.version,
            'initialized': self.is_initialized,
            'config': self.config
        }
    
    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """Valide la configuration du plugin"""
        return True
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Retourne les métriques du plugin"""
        return {}

class AgentPlugin(PluginInterface):
    """Plugin pour créer de nouveaux types d'agents"""
    
    @abstractmethod
    async def create_agent(self, agent_config: Dict[str, Any]) -> Any:
        """Crée une instance d'agent"""
        pass
    
    @abstractmethod
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Exécute une tâche"""
        pass

class CoordinationPlugin(PluginInterface):
    """Plugin pour nouveaux patterns de coordination"""
    
    @abstractmethod
    async def coordinate(self, 
                        agents: List[Any], 
                        task: Dict[str, Any],
                        context: Dict[str, Any]) -> Dict[str, Any]:
        """Coordonne l'exécution entre agents"""
        pass

class MetricsPlugin(PluginInterface):
    """Plugin pour collecte de métriques personnalisées"""
    
    @abstractmethod
    async def collect_metrics(self) -> Dict[str, Any]:
        """Collecte les métriques"""
        pass
    
    @abstractmethod
    async def process_metric(self, metric_name: str, value: Any, tags: Dict[str, str]):
        """Traite une métrique"""
        pass

class PluginManager:
    """Gestionnaire central des plugins"""
    
    def __init__(self, 
                 plugins_dir: str = "plugins",
                 config_dir: str = "config/plugins"):
        self.plugins_dir = Path(plugins_dir)
        self.config_dir = Path(config_dir)
        self.plugins: Dict[str, PluginInfo] = {}
        self.hooks: Dict[str, List[Callable]] = {}
        self.plugin_types: Dict[PluginType, List[str]] = {
            plugin_type: [] for plugin_type in PluginType
        }
        self.is_initialized = False
        
        # Créer les dossiers si nécessaires
        self.plugins_dir.mkdir(exist_ok=True)
        self.config_dir.mkdir(exist_ok=True, parents=True)
        
        logger.info("🔌 Plugin Manager initialized")
    
    async def initialize(self):
        """Initialise le gestionnaire de plugins"""
        if self.is_initialized:
            return
        
        logger.info("🚀 Initializing Plugin Manager...")
        
        # Découvrir et charger les plugins
        await self.discover_plugins()
        await self.load_all_plugins()
        
        self.is_initialized = True
        logger.info(f"✅ Plugin Manager initialized with {len(self.plugins)} plugins")
    
    async def shutdown(self):
        """Arrête tous les plugins"""
        logger.info("🛑 Shutting down Plugin Manager...")
        
        for plugin_name, plugin_info in self.plugins.items():
            if plugin_info.status == PluginStatus.ACTIVE:
                try:
                    await plugin_info.instance.shutdown()
                    plugin_info.status = PluginStatus.INACTIVE
                    logger.info(f"🔌 Plugin {plugin_name} shut down")
                except Exception as e:
                    logger.error(f"❌ Error shutting down plugin {plugin_name}: {e}")
        
        self.is_initialized = False
        logger.info("✅ Plugin Manager shut down")
    
    async def discover_plugins(self):
        """Découvre les plugins disponibles"""
        logger.info("🔍 Discovering plugins...")
        
        discovered_count = 0
        
        # Parcourir le dossier des plugins
        if self.plugins_dir.exists():
            for plugin_path in self.plugins_dir.iterdir():
                if plugin_path.is_dir() and not plugin_path.name.startswith('.'):
                    manifest_path = plugin_path / "manifest.yaml"
                    if manifest_path.exists():
                        try:
                            with open(manifest_path, 'r', encoding='utf-8') as f:
                                manifest_data = yaml.safe_load(f)
                                manifest = PluginManifest.from_dict(manifest_data)
                                
                                # Vérifier que le plugin n'est pas déjà chargé
                                if manifest.name not in self.plugins:
                                    plugin_info = PluginInfo(
                                        manifest=manifest,
                                        instance=None,
                                        status=PluginStatus.INACTIVE,
                                        load_time=0
                                    )
                                    self.plugins[manifest.name] = plugin_info
                                    discovered_count += 1
                                    
                                    logger.info(f"📦 Discovered plugin: {manifest.name} v{manifest.version}")
                        
                        except Exception as e:
                            logger.error(f"❌ Error reading manifest for {plugin_path.name}: {e}")
        
        logger.info(f"✅ Discovered {discovered_count} plugins")
    
    async def load_plugin(self, plugin_name: str) -> bool:
        """Charge un plugin spécifique"""
        if plugin_name not in self.plugins:
            logger.error(f"❌ Plugin {plugin_name} not found")
            return False
        
        plugin_info = self.plugins[plugin_name]
        manifest = plugin_info.manifest
        
        if plugin_info.status == PluginStatus.ACTIVE:
            logger.warning(f"⚠️ Plugin {plugin_name} already active")
            return True
        
        logger.info(f"🔄 Loading plugin: {plugin_name}")
        plugin_info.status = PluginStatus.LOADING
        
        try:
            start_time = time.time()
            
            # Construire le chemin vers le module
            plugin_path = self.plugins_dir / plugin_name
            module_path = plugin_path / manifest.entry_point
            
            if not module_path.exists():
                raise FileNotFoundError(f"Entry point not found: {module_path}")
            
            # Ajouter le chemin au sys.path temporairement
            sys.path.insert(0, str(plugin_path))
            
            try:
                # Charger le module
                spec = importlib.util.spec_from_file_location(
                    f"plugin_{plugin_name}", 
                    module_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Trouver la classe principale du plugin
                plugin_class = None
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, PluginInterface) and 
                        obj != PluginInterface):
                        plugin_class = obj
                        break
                
                if plugin_class is None:
                    raise ImportError(f"No plugin class found in {manifest.entry_point}")
                
                # Charger la configuration du plugin
                config = await self.load_plugin_config(plugin_name)
                
                # Instancier le plugin
                plugin_instance = plugin_class(config)
                
                # Initialiser le plugin
                await plugin_instance.initialize()
                
                # Mettre à jour les informations
                plugin_info.instance = plugin_instance
                plugin_info.status = PluginStatus.ACTIVE
                plugin_info.load_time = time.time() - start_time
                plugin_info.config = config
                plugin_info.error_message = None
                
                # Enregistrer par type
                self.plugin_types[manifest.plugin_type].append(plugin_name)
                
                logger.info(f"✅ Plugin {plugin_name} loaded successfully in {plugin_info.load_time:.3f}s")
                
                # Déclencher les hooks
                await self.trigger_hook("plugin_loaded", plugin_name, plugin_instance)
                
                return True
                
            finally:
                # Retirer le chemin du sys.path
                if str(plugin_path) in sys.path:
                    sys.path.remove(str(plugin_path))
        
        except Exception as e:
            error_msg = f"Failed to load plugin {plugin_name}: {e}"
            logger.error(f"❌ {error_msg}")
            logger.debug(traceback.format_exc())
            
            plugin_info.status = PluginStatus.ERROR
            plugin_info.error_message = error_msg
            
            return False
    
    async def unload_plugin(self, plugin_name: str) -> bool:
        """Décharge un plugin"""
        if plugin_name not in self.plugins:
            return False
        
        plugin_info = self.plugins[plugin_name]
        
        if plugin_info.status != PluginStatus.ACTIVE:
            return True
        
        logger.info(f"🔄 Unloading plugin: {plugin_name}")
        
        try:
            # Arrêter le plugin
            if plugin_info.instance:
                await plugin_info.instance.shutdown()
            
            # Mettre à jour le statut
            plugin_info.status = PluginStatus.INACTIVE
            plugin_info.instance = None
            
            # Retirer de la liste par type
            plugin_type = plugin_info.manifest.plugin_type
            if plugin_name in self.plugin_types[plugin_type]:
                self.plugin_types[plugin_type].remove(plugin_name)
            
            logger.info(f"✅ Plugin {plugin_name} unloaded")
            
            # Déclencher les hooks
            await self.trigger_hook("plugin_unloaded", plugin_name)
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Error unloading plugin {plugin_name}: {e}")
            return False
    
    async def reload_plugin(self, plugin_name: str) -> bool:
        """Recharge un plugin"""
        logger.info(f"🔄 Reloading plugin: {plugin_name}")
        
        success = await self.unload_plugin(plugin_name)
        if success:
            success = await self.load_plugin(plugin_name)
        
        return success
    
    async def load_all_plugins(self):
        """Charge tous les plugins découverts"""
        logger.info("🔄 Loading all plugins...")
        
        loaded_count = 0
        for plugin_name in self.plugins.keys():
            if await self.load_plugin(plugin_name):
                loaded_count += 1
        
        logger.info(f"✅ Loaded {loaded_count}/{len(self.plugins)} plugins")
    
    async def load_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """Charge la configuration d'un plugin"""
        config_file = self.config_dir / f"{plugin_name}.yaml"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"⚠️ Error loading config for {plugin_name}: {e}")
        
        return {}
    
    async def save_plugin_config(self, plugin_name: str, config: Dict[str, Any]):
        """Sauvegarde la configuration d'un plugin"""
        config_file = self.config_dir / f"{plugin_name}.yaml"
        
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False)
        except Exception as e:
            logger.error(f"❌ Error saving config for {plugin_name}: {e}")
    
    def get_plugin(self, plugin_name: str) -> Optional[Any]:
        """Récupère l'instance d'un plugin"""
        if plugin_name in self.plugins:
            plugin_info = self.plugins[plugin_name]
            if plugin_info.status == PluginStatus.ACTIVE:
                return plugin_info.instance
        return None
    
    def get_plugins_by_type(self, plugin_type: PluginType) -> List[Any]:
        """Récupère tous les plugins d'un type donné"""
        plugins = []
        for plugin_name in self.plugin_types[plugin_type]:
            plugin = self.get_plugin(plugin_name)
            if plugin:
                plugins.append(plugin)
        return plugins
    
    def list_plugins(self, plugin_type: Optional[PluginType] = None) -> List[PluginInfo]:
        """Liste tous les plugins ou par type"""
        if plugin_type is None:
            return list(self.plugins.values())
        else:
            return [
                self.plugins[name] for name in self.plugin_types[plugin_type]
                if name in self.plugins
            ]
    
    def get_plugin_info(self, plugin_name: str) -> Optional[PluginInfo]:
        """Récupère les informations d'un plugin"""
        return self.plugins.get(plugin_name)
    
    async def install_plugin(self, plugin_path: Union[str, Path]):
        """Installe un plugin depuis un chemin"""
        # TODO: Implémenter l'installation de plugins
        pass
    
    async def uninstall_plugin(self, plugin_name: str):
        """Désinstalle un plugin"""
        # TODO: Implémenter la désinstallation
        pass
    
    # Système de hooks
    
    def register_hook(self, event: str, callback: Callable):
        """Enregistre un hook pour un événement"""
        if event not in self.hooks:
            self.hooks[event] = []
        self.hooks[event].append(callback)
    
    def unregister_hook(self, event: str, callback: Callable):
        """Désenregistre un hook"""
        if event in self.hooks and callback in self.hooks[event]:
            self.hooks[event].remove(callback)
    
    async def trigger_hook(self, event: str, *args, **kwargs):
        """Déclenche tous les hooks pour un événement"""
        if event in self.hooks:
            for callback in self.hooks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(*args, **kwargs)
                    else:
                        callback(*args, **kwargs)
                except Exception as e:
                    logger.error(f"❌ Error in hook {callback.__name__} for event {event}: {e}")
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques du système de plugins"""
        stats = {
            'total_plugins': len(self.plugins),
            'active_plugins': len([p for p in self.plugins.values() if p.status == PluginStatus.ACTIVE]),
            'plugin_types': {},
            'load_times': {},
            'error_count': len([p for p in self.plugins.values() if p.status == PluginStatus.ERROR])
        }
        
        # Statistiques par type
        for plugin_type in PluginType:
            active_count = len([
                name for name in self.plugin_types[plugin_type]
                if self.plugins[name].status == PluginStatus.ACTIVE
            ])
            stats['plugin_types'][plugin_type.value] = {
                'total': len(self.plugin_types[plugin_type]),
                'active': active_count
            }
        
        # Temps de chargement
        for name, info in self.plugins.items():
            if info.status == PluginStatus.ACTIVE:
                stats['load_times'][name] = info.load_time
        
        return stats

# Décorateurs pour les plugins

def plugin_hook(event: str):
    """Décorateur pour enregistrer une méthode comme hook"""
    def decorator(func):
        func._plugin_hook = event
        return func
    return decorator

def requires_permission(permission: str):
    """Décorateur pour vérifier les permissions"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # TODO: Implémenter la vérification des permissions
            return await func(self, *args, **kwargs)
        return wrapper
    return decorator

# Instance globale
plugin_manager = PluginManager()

# Exemple d'utilisation
async def main():
    """Test du système de plugins"""
    
    # Initialiser le gestionnaire
    await plugin_manager.initialize()
    
    try:
        # Lister les plugins
        plugins = plugin_manager.list_plugins()
        print(f"Plugins disponibles: {len(plugins)}")
        
        for plugin_info in plugins:
            print(f"  - {plugin_info.manifest.name} v{plugin_info.manifest.version}")
            print(f"    Type: {plugin_info.manifest.plugin_type.value}")
            print(f"    Statut: {plugin_info.status.value}")
            print(f"    Description: {plugin_info.manifest.description}")
        
        # Statistiques
        stats = await plugin_manager.get_system_stats()
        print(f"\nStatistiques: {json.dumps(stats, indent=2)}")
        
    finally:
        await plugin_manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())