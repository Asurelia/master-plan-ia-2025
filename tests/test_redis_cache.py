#!/usr/bin/env python3
"""
Tests pour le système de cache Redis
"""

import pytest
import asyncio
import time
import json
from unittest.mock import AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

from redis_cache import RedisCache, CacheConfig, SerializationType
from cache_integration import CacheManager

@pytest.fixture
async def redis_cache():
    """Fixture pour le cache Redis avec configuration de test"""
    config = CacheConfig(
        host="localhost",
        port=6379,
        db=15,  # Base de test
        default_ttl=60
    )
    
    cache = RedisCache(config)
    
    # Mock la connexion Redis pour les tests
    with patch('redis.asyncio.Redis') as mock_redis:
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client
        
        # Configuration des mocks
        mock_client.ping.return_value = True
        mock_client.get.return_value = None
        mock_client.set.return_value = True
        mock_client.setex.return_value = True
        mock_client.delete.return_value = 1
        mock_client.exists.return_value = 1
        mock_client.ttl.return_value = 60
        mock_client.expire.return_value = True
        mock_client.mget.return_value = []
        mock_client.mset.return_value = True
        mock_client.incrby.return_value = 1
        mock_client.decrby.return_value = 0
        mock_client.lpush.return_value = 1
        mock_client.lrange.return_value = []
        mock_client.sadd.return_value = 1
        mock_client.smembers.return_value = set()
        mock_client.scan_iter.return_value = []
        mock_client.dbsize.return_value = 0
        mock_client.info.return_value = {
            "used_memory": 1024,
            "used_memory_human": "1K",
            "connected_clients": 1,
            "total_commands_processed": 100,
            "instantaneous_ops_per_sec": 10
        }
        mock_client.flushdb.return_value = True
        
        cache.client = mock_client
        cache.is_connected = True
        
        yield cache

@pytest.mark.asyncio
async def test_cache_basic_operations(redis_cache):
    """Test des opérations de base du cache"""
    
    # Test set/get
    await redis_cache.set("test", "key1", {"value": "test data"})
    assert redis_cache.stats.sets == 1
    
    # Mock le retour de get
    redis_cache.client.get.return_value = json.dumps({"value": "test data"}).encode()
    
    result = await redis_cache.get("test", "key1")
    assert result == {"value": "test data"}
    assert redis_cache.stats.hits == 1
    
    # Test delete
    deleted = await redis_cache.delete("test", "key1")
    assert deleted == True
    assert redis_cache.stats.deletes == 1

@pytest.mark.asyncio
async def test_cache_serialization(redis_cache):
    """Test des différents types de sérialisation"""
    
    # Test JSON
    await redis_cache.set("test", "json_key", {"data": "json"}, serialization=SerializationType.JSON)
    
    # Test STRING
    await redis_cache.set("test", "string_key", "string data", serialization=SerializationType.STRING)
    
    # Test PICKLE
    await redis_cache.set("test", "pickle_key", {"complex": [1, 2, 3]}, serialization=SerializationType.PICKLE)
    
    assert redis_cache.stats.sets == 3

@pytest.mark.asyncio
async def test_cache_ttl_operations(redis_cache):
    """Test des opérations avec TTL"""
    
    # Test avec TTL personnalisé
    await redis_cache.set("test", "ttl_key", "data", ttl=120)
    
    # Test TTL
    ttl = await redis_cache.ttl("test", "ttl_key")
    assert ttl == 60  # Valeur mockée
    
    # Test expire
    success = await redis_cache.expire("test", "ttl_key", 300)
    assert success == True

@pytest.mark.asyncio
async def test_cache_atomic_operations(redis_cache):
    """Test des opérations atomiques"""
    
    # Test increment
    result = await redis_cache.increment("counters", "test_counter", 5)
    assert result == 1  # Valeur mockée
    
    # Test decrement
    result = await redis_cache.decrement("counters", "test_counter", 2)
    assert result == 0  # Valeur mockée

@pytest.mark.asyncio
async def test_cache_collections(redis_cache):
    """Test des opérations sur les collections"""
    
    # Test liste
    count = await redis_cache.lpush("lists", "test_list", "item1", "item2")
    assert count == 1  # Valeur mockée
    
    items = await redis_cache.lrange("lists", "test_list", 0, -1)
    assert items == []  # Valeur mockée
    
    # Test ensemble
    count = await redis_cache.sadd("sets", "test_set", "member1", "member2")
    assert count == 1  # Valeur mockée
    
    members = await redis_cache.smembers("sets", "test_set")
    assert members == set()  # Valeur mockée

@pytest.mark.asyncio
async def test_cache_bulk_operations(redis_cache):
    """Test des opérations en lot"""
    
    # Test mset
    data = {
        "key1": "value1",
        "key2": {"complex": "data"},
        "key3": [1, 2, 3]
    }
    
    success = await redis_cache.mset("bulk", data, ttl=300)
    assert success == True
    
    # Test mget
    redis_cache.client.mget.return_value = [
        json.dumps("value1").encode(),
        json.dumps({"complex": "data"}).encode(),
        json.dumps([1, 2, 3]).encode()
    ]
    
    results = await redis_cache.mget("bulk", ["key1", "key2", "key3"])
    assert len(results) == 3
    assert redis_cache.stats.hits == 3

@pytest.mark.asyncio
async def test_get_or_set_pattern(redis_cache):
    """Test du pattern get_or_set"""
    
    call_count = 0
    
    def expensive_function():
        nonlocal call_count
        call_count += 1
        return {"result": f"computation_{call_count}"}
    
    # Premier appel - cache miss
    redis_cache.client.get.return_value = None
    result1 = await redis_cache.get_or_set("cache_aside", "expensive_key", expensive_function)
    
    assert call_count == 1
    assert result1 == {"result": "computation_1"}
    
    # Deuxième appel - cache hit
    redis_cache.client.get.return_value = json.dumps({"result": "computation_1"}).encode()
    result2 = await redis_cache.get_or_set("cache_aside", "expensive_key", expensive_function)
    
    assert call_count == 1  # La fonction n'a pas été rappelée
    assert result2 == {"result": "computation_1"}

@pytest.mark.asyncio
async def test_cache_stats(redis_cache):
    """Test des statistiques du cache"""
    
    # Effectuer quelques opérations
    await redis_cache.set("test", "key1", "value1")
    await redis_cache.get("test", "key1")
    await redis_cache.delete("test", "key1")
    
    stats = await redis_cache.get_stats()
    
    assert "hits" in stats
    assert "misses" in stats
    assert "sets" in stats
    assert "deletes" in stats
    assert "hit_rate" in stats
    assert "is_connected" in stats
    assert stats["is_connected"] == True

@pytest.mark.asyncio
async def test_cache_key_generation(redis_cache):
    """Test de la génération de clés"""
    
    # Test clé normale
    key1 = redis_cache._generate_key("test", "simple_key")
    assert key1 == "masterplan:test:simple_key"
    
    # Test clé longue (doit être hashée)
    long_key = "a" * 2000
    key2 = redis_cache._generate_key("test", long_key)
    assert len(key2) <= redis_cache.config.max_key_length
    assert key2.startswith("masterplan:test:")

@pytest.mark.asyncio
async def test_cache_error_handling(redis_cache):
    """Test de la gestion d'erreurs"""
    
    # Simuler une déconnexion
    redis_cache.is_connected = False
    
    # Les opérations doivent échouer gracieusement
    result = await redis_cache.get("test", "key")
    assert result is None
    
    success = await redis_cache.set("test", "key", "value")
    assert success == False
    
    success = await redis_cache.delete("test", "key")
    assert success == False

@pytest.mark.asyncio
async def test_cache_manager():
    """Test du gestionnaire de cache"""
    
    cache_manager = CacheManager()
    
    # Mock la connexion
    with patch.object(cache_manager.cache, 'connect') as mock_connect:
        await cache_manager.connect()
        mock_connect.assert_called_once()
        assert cache_manager.is_connected == True
    
    # Test wrapping
    class MockHub:
        async def get_agent_status(self, agent_id):
            return {"id": agent_id, "status": "active"}
    
    hub = MockHub()
    cached_hub = cache_manager.wrap_orchestration_hub(hub)
    
    assert cached_hub is not None
    assert hasattr(cached_hub, 'get_agent_status')

@pytest.mark.asyncio
async def test_cached_decorator():
    """Test du décorateur de cache"""
    
    from redis_cache import cached
    
    call_count = 0
    
    @cached("functions", ttl=300)
    async def expensive_function(x, y, cache=None):
        nonlocal call_count
        call_count += 1
        return x + y
    
    # Premier appel avec cache mock
    cache_mock = AsyncMock()
    cache_mock.get.return_value = None
    cache_mock.set.return_value = True
    
    result1 = await expensive_function(2, 3, cache=cache_mock)
    assert result1 == 5
    assert call_count == 1
    
    # Deuxième appel avec cache hit
    cache_mock.get.return_value = 5
    result2 = await expensive_function(2, 3, cache=cache_mock)
    assert result2 == 5
    assert call_count == 1  # Pas de nouvel appel

def test_cache_config():
    """Test de la configuration du cache"""
    
    config = CacheConfig(
        host="redis.example.com",
        port=6380,
        db=1,
        default_ttl=7200,
        metrics_ttl=60
    )
    
    assert config.host == "redis.example.com"
    assert config.port == 6380
    assert config.db == 1
    assert config.default_ttl == 7200
    assert config.metrics_ttl == 60

if __name__ == "__main__":
    pytest.main([__file__, "-v"])