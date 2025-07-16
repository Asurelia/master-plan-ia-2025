#!/usr/bin/env python3
"""
Master Plan IA 2025 - Redis Cache Manager
Gestionnaire de cache Redis pour optimiser les performances
"""

import asyncio
import json
import time
import pickle
from typing import Any, Optional, Dict, List, Union, Callable
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
from functools import wraps

logger = logging.getLogger(__name__)

class CacheStrategy(Enum):
    """Stratégies de mise en cache"""
    WRITE_THROUGH = "write_through"      # Écrire en cache et en DB
    WRITE_BEHIND = "write_behind"        # Écrire en cache, puis en DB async
    WRITE_AROUND = "write_around"        # Écrire en DB seulement
    CACHE_ASIDE = "cache_aside"          # Application gère le cache
    REFRESH_AHEAD = "refresh_ahead"      # Rafraîchir avant expiration

class SerializationType(Enum):
    """Types de sérialisation"""
    JSON = "json"
    PICKLE = "pickle"
    STRING = "string"

@dataclass
class CacheConfig:
    """Configuration du cache"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 50
    decode_responses: bool = False
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    connection_pool_class: type = ConnectionPool
    health_check_interval: int = 30
    
    # Configuration par défaut des TTL (en secondes)
    default_ttl: int = 3600              # 1 heure
    metrics_ttl: int = 300               # 5 minutes
    agent_status_ttl: int = 60           # 1 minute
    workflow_ttl: int = 1800             # 30 minutes
    ai_response_ttl: int = 86400         # 24 heures
    
    # Limites
    max_key_length: int = 1024
    max_value_size: int = 512 * 1024     # 512 KB
    
    # Stratégies
    default_strategy: CacheStrategy = CacheStrategy.CACHE_ASIDE
    enable_compression: bool = True
    compression_threshold: int = 1024     # Compresser si > 1KB

@dataclass
class CacheStats:
    """Statistiques du cache"""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    errors: int = 0
    avg_get_time: float = 0.0
    avg_set_time: float = 0.0
    memory_usage: int = 0
    keys_count: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

class RedisCache:
    """Gestionnaire de cache Redis avancé"""
    
    def __init__(self, config: CacheConfig = None):
        self.config = config or CacheConfig()
        self.client: Optional[redis.Redis] = None
        self.pool: Optional[ConnectionPool] = None
        self.stats = CacheStats()
        self.is_connected = False
        self._lock = asyncio.Lock()
        self._invalidation_callbacks: Dict[str, List[Callable]] = {}
        
        logger.info("🔄 Redis Cache Manager initialized")
    
    async def connect(self):
        """Connexion à Redis"""
        try:
            self.pool = redis.ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                max_connections=self.config.max_connections,
                decode_responses=self.config.decode_responses,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout
            )
            
            self.client = redis.Redis(connection_pool=self.pool)
            
            # Test de connexion
            await self.client.ping()
            self.is_connected = True
            
            logger.info(f"✅ Connected to Redis at {self.config.host}:{self.config.port}")
            
            # Démarrer le health check
            asyncio.create_task(self._health_check_loop())
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            self.is_connected = False
            raise
    
    async def disconnect(self):
        """Déconnexion de Redis"""
        if self.client:
            await self.client.close()
            await self.pool.disconnect()
            self.is_connected = False
            logger.info("🔌 Disconnected from Redis")
    
    async def _health_check_loop(self):
        """Boucle de vérification de santé"""
        while self.is_connected:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self.client.ping()
            except Exception as e:
                logger.error(f"Redis health check failed: {e}")
                self.is_connected = False
    
    def _generate_key(self, namespace: str, key: str) -> str:
        """Génère une clé avec namespace"""
        full_key = f"masterplan:{namespace}:{key}"
        
        # Vérifier la longueur
        if len(full_key) > self.config.max_key_length:
            # Hasher si trop long
            key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
            full_key = f"masterplan:{namespace}:{key_hash}"
        
        return full_key
    
    def _serialize(self, value: Any, serialization: SerializationType = SerializationType.JSON) -> bytes:
        """Sérialise une valeur"""
        if serialization == SerializationType.STRING:
            return str(value).encode()
        elif serialization == SerializationType.JSON:
            return json.dumps(value, default=str).encode()
        elif serialization == SerializationType.PICKLE:
            return pickle.dumps(value)
        else:
            raise ValueError(f"Unknown serialization type: {serialization}")
    
    def _deserialize(self, data: bytes, serialization: SerializationType = SerializationType.JSON) -> Any:
        """Désérialise une valeur"""
        if data is None:
            return None
        
        if serialization == SerializationType.STRING:
            return data.decode()
        elif serialization == SerializationType.JSON:
            return json.loads(data.decode())
        elif serialization == SerializationType.PICKLE:
            return pickle.loads(data)
        else:
            raise ValueError(f"Unknown serialization type: {serialization}")
    
    async def get(self, 
                  namespace: str, 
                  key: str, 
                  serialization: SerializationType = SerializationType.JSON) -> Optional[Any]:
        """Récupère une valeur du cache"""
        if not self.is_connected:
            self.stats.errors += 1
            return None
        
        start_time = time.time()
        full_key = self._generate_key(namespace, key)
        
        try:
            data = await self.client.get(full_key)
            
            elapsed = time.time() - start_time
            self.stats.avg_get_time = (self.stats.avg_get_time + elapsed) / 2
            
            if data is None:
                self.stats.misses += 1
                return None
            
            self.stats.hits += 1
            return self._deserialize(data, serialization)
            
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self.stats.errors += 1
            return None
    
    async def set(self,
                  namespace: str,
                  key: str,
                  value: Any,
                  ttl: Optional[int] = None,
                  serialization: SerializationType = SerializationType.JSON,
                  strategy: Optional[CacheStrategy] = None) -> bool:
        """Stocke une valeur dans le cache"""
        if not self.is_connected:
            self.stats.errors += 1
            return False
        
        start_time = time.time()
        full_key = self._generate_key(namespace, key)
        
        try:
            # Sérialiser la valeur
            data = self._serialize(value, serialization)
            
            # Vérifier la taille
            if len(data) > self.config.max_value_size:
                logger.warning(f"Value too large for key {full_key}: {len(data)} bytes")
                return False
            
            # Déterminer le TTL
            if ttl is None:
                ttl = self._get_default_ttl(namespace)
            
            # Stocker dans Redis
            if ttl > 0:
                await self.client.setex(full_key, ttl, data)
            else:
                await self.client.set(full_key, data)
            
            elapsed = time.time() - start_time
            self.stats.avg_set_time = (self.stats.avg_set_time + elapsed) / 2
            self.stats.sets += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            self.stats.errors += 1
            return False
    
    async def delete(self, namespace: str, key: str) -> bool:
        """Supprime une valeur du cache"""
        if not self.is_connected:
            return False
        
        full_key = self._generate_key(namespace, key)
        
        try:
            result = await self.client.delete(full_key)
            self.stats.deletes += 1
            
            # Déclencher les callbacks d'invalidation
            await self._trigger_invalidation_callbacks(namespace, key)
            
            return result > 0
            
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            self.stats.errors += 1
            return False
    
    async def delete_pattern(self, namespace: str, pattern: str) -> int:
        """Supprime toutes les clés correspondant à un pattern"""
        if not self.is_connected:
            return 0
        
        full_pattern = self._generate_key(namespace, pattern)
        
        try:
            # Utiliser SCAN pour éviter de bloquer Redis
            deleted = 0
            async for key in self.client.scan_iter(match=full_pattern):
                await self.client.delete(key)
                deleted += 1
                self.stats.deletes += 1
            
            return deleted
            
        except Exception as e:
            logger.error(f"Cache delete pattern error: {e}")
            self.stats.errors += 1
            return 0
    
    async def exists(self, namespace: str, key: str) -> bool:
        """Vérifie si une clé existe"""
        if not self.is_connected:
            return False
        
        full_key = self._generate_key(namespace, key)
        
        try:
            return await self.client.exists(full_key) > 0
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
            return False
    
    async def ttl(self, namespace: str, key: str) -> int:
        """Récupère le TTL restant d'une clé"""
        if not self.is_connected:
            return -1
        
        full_key = self._generate_key(namespace, key)
        
        try:
            return await self.client.ttl(full_key)
        except Exception as e:
            logger.error(f"Cache ttl error: {e}")
            return -1
    
    async def expire(self, namespace: str, key: str, ttl: int) -> bool:
        """Définit/met à jour le TTL d'une clé"""
        if not self.is_connected:
            return False
        
        full_key = self._generate_key(namespace, key)
        
        try:
            return await self.client.expire(full_key, ttl)
        except Exception as e:
            logger.error(f"Cache expire error: {e}")
            return False
    
    # Cache avancé avec patterns
    
    async def get_or_set(self,
                        namespace: str,
                        key: str,
                        factory: Callable,
                        ttl: Optional[int] = None,
                        serialization: SerializationType = SerializationType.JSON) -> Any:
        """Pattern Cache-Aside: récupère ou calcule et stocke"""
        # Essayer de récupérer du cache
        value = await self.get(namespace, key, serialization)
        
        if value is not None:
            return value
        
        # Calculer la valeur
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()
        
        # Stocker en cache
        await self.set(namespace, key, value, ttl, serialization)
        
        return value
    
    async def mget(self,
                   namespace: str,
                   keys: List[str],
                   serialization: SerializationType = SerializationType.JSON) -> Dict[str, Any]:
        """Récupère plusieurs valeurs en une fois"""
        if not self.is_connected or not keys:
            return {}
        
        # Générer les clés complètes
        full_keys = [self._generate_key(namespace, key) for key in keys]
        
        try:
            values = await self.client.mget(full_keys)
            
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = self._deserialize(value, serialization)
                    self.stats.hits += 1
                else:
                    self.stats.misses += 1
            
            return result
            
        except Exception as e:
            logger.error(f"Cache mget error: {e}")
            self.stats.errors += 1
            return {}
    
    async def mset(self,
                   namespace: str,
                   data: Dict[str, Any],
                   ttl: Optional[int] = None,
                   serialization: SerializationType = SerializationType.JSON) -> bool:
        """Stocke plusieurs valeurs en une fois"""
        if not self.is_connected or not data:
            return False
        
        try:
            # Préparer les données
            redis_data = {}
            for key, value in data.items():
                full_key = self._generate_key(namespace, key)
                redis_data[full_key] = self._serialize(value, serialization)
            
            # Stocker dans Redis
            await self.client.mset(redis_data)
            
            # Appliquer le TTL si nécessaire
            if ttl is not None:
                pipeline = self.client.pipeline()
                for full_key in redis_data.keys():
                    pipeline.expire(full_key, ttl)
                await pipeline.execute()
            
            self.stats.sets += len(data)
            return True
            
        except Exception as e:
            logger.error(f"Cache mset error: {e}")
            self.stats.errors += 1
            return False
    
    # Opérations atomiques
    
    async def increment(self, namespace: str, key: str, amount: int = 1) -> Optional[int]:
        """Incrémente une valeur atomiquement"""
        if not self.is_connected:
            return None
        
        full_key = self._generate_key(namespace, key)
        
        try:
            return await self.client.incrby(full_key, amount)
        except Exception as e:
            logger.error(f"Cache increment error: {e}")
            return None
    
    async def decrement(self, namespace: str, key: str, amount: int = 1) -> Optional[int]:
        """Décrémente une valeur atomiquement"""
        if not self.is_connected:
            return None
        
        full_key = self._generate_key(namespace, key)
        
        try:
            return await self.client.decrby(full_key, amount)
        except Exception as e:
            logger.error(f"Cache decrement error: {e}")
            return None
    
    # Listes et ensembles
    
    async def lpush(self, namespace: str, key: str, *values: Any) -> Optional[int]:
        """Ajoute des valeurs au début d'une liste"""
        if not self.is_connected:
            return None
        
        full_key = self._generate_key(namespace, key)
        
        try:
            serialized = [self._serialize(v, SerializationType.JSON) for v in values]
            return await self.client.lpush(full_key, *serialized)
        except Exception as e:
            logger.error(f"Cache lpush error: {e}")
            return None
    
    async def lrange(self, namespace: str, key: str, start: int, stop: int) -> List[Any]:
        """Récupère une portion de liste"""
        if not self.is_connected:
            return []
        
        full_key = self._generate_key(namespace, key)
        
        try:
            values = await self.client.lrange(full_key, start, stop)
            return [self._deserialize(v, SerializationType.JSON) for v in values]
        except Exception as e:
            logger.error(f"Cache lrange error: {e}")
            return []
    
    async def sadd(self, namespace: str, key: str, *values: Any) -> Optional[int]:
        """Ajoute des valeurs à un ensemble"""
        if not self.is_connected:
            return None
        
        full_key = self._generate_key(namespace, key)
        
        try:
            serialized = [self._serialize(v, SerializationType.JSON) for v in values]
            return await self.client.sadd(full_key, *serialized)
        except Exception as e:
            logger.error(f"Cache sadd error: {e}")
            return None
    
    async def smembers(self, namespace: str, key: str) -> set:
        """Récupère tous les membres d'un ensemble"""
        if not self.is_connected:
            return set()
        
        full_key = self._generate_key(namespace, key)
        
        try:
            values = await self.client.smembers(full_key)
            return {self._deserialize(v, SerializationType.JSON) for v in values}
        except Exception as e:
            logger.error(f"Cache smembers error: {e}")
            return set()
    
    # Invalidation et callbacks
    
    def register_invalidation_callback(self, namespace: str, callback: Callable):
        """Enregistre un callback d'invalidation"""
        if namespace not in self._invalidation_callbacks:
            self._invalidation_callbacks[namespace] = []
        self._invalidation_callbacks[namespace].append(callback)
    
    async def _trigger_invalidation_callbacks(self, namespace: str, key: str):
        """Déclenche les callbacks d'invalidation"""
        callbacks = self._invalidation_callbacks.get(namespace, [])
        
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(key)
                else:
                    callback(key)
            except Exception as e:
                logger.error(f"Invalidation callback error: {e}")
    
    # Utilitaires
    
    def _get_default_ttl(self, namespace: str) -> int:
        """Récupère le TTL par défaut pour un namespace"""
        ttl_map = {
            "metrics": self.config.metrics_ttl,
            "agents": self.config.agent_status_ttl,
            "workflows": self.config.workflow_ttl,
            "ai_responses": self.config.ai_response_ttl
        }
        
        return ttl_map.get(namespace, self.config.default_ttl)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques du cache"""
        info = {}
        
        if self.is_connected:
            try:
                # Informations Redis
                redis_info = await self.client.info()
                info.update({
                    "used_memory": redis_info.get("used_memory", 0),
                    "used_memory_human": redis_info.get("used_memory_human", "0B"),
                    "connected_clients": redis_info.get("connected_clients", 0),
                    "total_commands_processed": redis_info.get("total_commands_processed", 0),
                    "instantaneous_ops_per_sec": redis_info.get("instantaneous_ops_per_sec", 0)
                })
                
                # Nombre de clés
                info["total_keys"] = await self.client.dbsize()
                
            except Exception as e:
                logger.error(f"Error getting Redis info: {e}")
        
        # Statistiques locales
        info.update({
            "hits": self.stats.hits,
            "misses": self.stats.misses,
            "hit_rate": self.stats.hit_rate,
            "sets": self.stats.sets,
            "deletes": self.stats.deletes,
            "errors": self.stats.errors,
            "avg_get_time_ms": self.stats.avg_get_time * 1000,
            "avg_set_time_ms": self.stats.avg_set_time * 1000,
            "is_connected": self.is_connected
        })
        
        return info
    
    async def flush_namespace(self, namespace: str) -> int:
        """Vide toutes les clés d'un namespace"""
        if not self.is_connected:
            return 0
        
        pattern = self._generate_key(namespace, "*")
        return await self.delete_pattern(namespace, "*")
    
    async def flush_all(self) -> bool:
        """Vide tout le cache (utiliser avec précaution)"""
        if not self.is_connected:
            return False
        
        try:
            await self.client.flushdb()
            self.stats = CacheStats()  # Réinitialiser les stats
            return True
        except Exception as e:
            logger.error(f"Cache flush error: {e}")
            return False

# Décorateur de cache
def cached(namespace: str, 
          ttl: Optional[int] = None,
          key_builder: Optional[Callable] = None,
          serialization: SerializationType = SerializationType.JSON):
    """Décorateur pour mettre en cache les résultats de fonctions"""
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Construire la clé
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Clé par défaut basée sur les arguments
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Récupérer l'instance de cache (doit être passée comme premier argument ou dans kwargs)
            cache = kwargs.get('cache') or (args[0] if args and hasattr(args[0], 'cache') else None)
            
            if not cache:
                # Pas de cache disponible, exécuter directement
                return await func(*args, **kwargs)
            
            # Essayer de récupérer du cache
            result = await cache.get(namespace, cache_key, serialization)
            
            if result is not None:
                return result
            
            # Exécuter la fonction
            result = await func(*args, **kwargs)
            
            # Stocker en cache
            await cache.set(namespace, cache_key, result, ttl, serialization)
            
            return result
        
        return wrapper
    return decorator

# Instance globale
redis_cache = RedisCache()

# Exemple d'utilisation
async def main():
    """Test du cache Redis"""
    
    # Configuration personnalisée
    config = CacheConfig(
        host="localhost",
        port=6379,
        default_ttl=3600,
        metrics_ttl=300
    )
    
    cache = RedisCache(config)
    await cache.connect()
    
    try:
        # Test de base
        await cache.set("test", "key1", {"value": "Hello Redis!"})
        value = await cache.get("test", "key1")
        print(f"Retrieved: {value}")
        
        # Test avec TTL
        await cache.set("metrics", "cpu_usage", 0.75, ttl=60)
        ttl = await cache.ttl("metrics", "cpu_usage")
        print(f"TTL: {ttl} seconds")
        
        # Test atomique
        counter = await cache.increment("counters", "requests")
        print(f"Counter: {counter}")
        
        # Test de liste
        await cache.lpush("logs", "event1", "Log entry 1")
        await cache.lpush("logs", "event1", "Log entry 2")
        logs = await cache.lrange("logs", "event1", 0, -1)
        print(f"Logs: {logs}")
        
        # Statistiques
        stats = await cache.get_stats()
        print(f"Cache stats: {json.dumps(stats, indent=2)}")
        
    finally:
        await cache.disconnect()

if __name__ == "__main__":
    asyncio.run(main())