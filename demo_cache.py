#!/usr/bin/env python3
"""
Démonstration du système de cache Redis
"""

import asyncio
import time
import json
from datetime import datetime
import sys
import os

# Ajouter le chemin des modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))

from redis_cache import RedisCache, CacheConfig, SerializationType
from cache_integration import CacheManager

async def demo_basic_cache():
    """Démonstration des opérations de base du cache"""
    print("\n" + "="*50)
    print("🗄️  DÉMONSTRATION DU CACHE REDIS")
    print("="*50)
    
    # Configuration du cache
    config = CacheConfig(
        host="localhost",
        port=6379,
        db=0,  # Base par défaut
        default_ttl=300,  # 5 minutes
        metrics_ttl=60    # 1 minute pour les métriques
    )
    
    cache = RedisCache(config)
    
    try:
        print("\n📡 Connexion à Redis...")
        await cache.connect()
        print("✅ Connecté à Redis")
        
        # Test des opérations de base
        print("\n🔧 Test des opérations de base:")
        
        # Set/Get simple
        print("  • Stockage d'une valeur simple...")
        await cache.set("demo", "simple_key", "Hello Redis!")
        value = await cache.get("demo", "simple_key")
        print(f"    Valeur récupérée: {value}")
        
        # Set/Get avec objet complexe
        print("  • Stockage d'un objet complexe...")
        complex_data = {
            "user": "Alice",
            "score": 95.5,
            "tags": ["python", "redis", "cache"],
            "metadata": {
                "created": datetime.now().isoformat(),
                "version": "1.0"
            }
        }
        await cache.set("demo", "complex_data", complex_data, ttl=120)
        retrieved_data = await cache.get("demo", "complex_data")
        print(f"    Objet récupéré: {json.dumps(retrieved_data, indent=2)}")
        
        # Test du TTL
        print("  • Test du TTL...")
        ttl = await cache.ttl("demo", "complex_data")
        print(f"    TTL restant: {ttl} secondes")
        
        # Opérations atomiques
        print("\n🔢 Test des opérations atomiques:")
        counter_value = await cache.increment("counters", "demo_counter", 5)
        print(f"  • Compteur après +5: {counter_value}")
        
        counter_value = await cache.increment("counters", "demo_counter", 3)
        print(f"  • Compteur après +3: {counter_value}")
        
        counter_value = await cache.decrement("counters", "demo_counter", 2)
        print(f"  • Compteur après -2: {counter_value}")
        
        # Collections
        print("\n📋 Test des collections:")
        
        # Liste
        await cache.lpush("lists", "demo_logs", "Event 1", "Event 2", "Event 3")
        logs = await cache.lrange("lists", "demo_logs", 0, -1)
        print(f"  • Liste de logs: {logs}")
        
        # Ensemble
        await cache.sadd("sets", "demo_tags", "redis", "cache", "python", "async")
        tags = await cache.smembers("sets", "demo_tags")
        print(f"  • Ensemble de tags: {sorted(list(tags))}")
        
        # Opérations en lot
        print("\n📦 Test des opérations en lot:")
        batch_data = {
            "user:1": {"name": "Alice", "age": 30},
            "user:2": {"name": "Bob", "age": 25},
            "user:3": {"name": "Charlie", "age": 35}
        }
        
        await cache.mset("users", batch_data, ttl=180)
        retrieved_users = await cache.mget("users", ["user:1", "user:2", "user:3"])
        print(f"  • Utilisateurs récupérés: {len(retrieved_users)} sur 3")
        for user_id, user_data in retrieved_users.items():
            print(f"    {user_id}: {user_data}")
        
        # Pattern get_or_set
        print("\n🎯 Test du pattern get_or_set:")
        
        def expensive_computation():
            """Simulation d'un calcul coûteux"""
            print("    💻 Exécution du calcul coûteux...")
            time.sleep(0.1)  # Simulation
            return {
                "result": 42,
                "computed_at": datetime.now().isoformat(),
                "computation_time": 0.1
            }
        
        # Premier appel (cache miss)
        print("  • Premier appel (cache miss):")
        start_time = time.time()
        result1 = await cache.get_or_set("computations", "expensive_calc", expensive_computation, ttl=60)
        elapsed1 = time.time() - start_time
        print(f"    Résultat: {result1}")
        print(f"    Temps: {elapsed1:.3f}s")
        
        # Deuxième appel (cache hit)
        print("  • Deuxième appel (cache hit):")
        start_time = time.time()
        result2 = await cache.get_or_set("computations", "expensive_calc", expensive_computation, ttl=60)
        elapsed2 = time.time() - start_time
        print(f"    Résultat: {result2}")
        print(f"    Temps: {elapsed2:.3f}s")
        print(f"    Accélération: {elapsed1/elapsed2:.1f}x plus rapide!")
        
    except Exception as e:
        print(f"❌ Erreur de connexion Redis: {e}")
        print("💡 Assurez-vous que Redis est installé et en cours d'exécution:")
        print("   sudo apt install redis-server")
        print("   sudo systemctl start redis")
        return False
    
    finally:
        if cache.is_connected:
            await cache.disconnect()
            print("\n🔌 Déconnecté de Redis")
    
    return True

async def demo_cache_integration():
    """Démonstration du gestionnaire de cache intégré"""
    print("\n" + "="*50)
    print("🔗 DÉMONSTRATION DE L'INTÉGRATION CACHE")
    print("="*50)
    
    cache_manager = CacheManager()
    
    try:
        print("\n📡 Connexion du gestionnaire de cache...")
        await cache_manager.connect()
        print("✅ Cache Manager connecté")
        
        # Simulation d'un hub d'orchestration
        class MockOrchestrationHub:
            def __init__(self):
                self.agents = {
                    "agent-1": type('Agent', (), {
                        'id': 'agent-1',
                        'name': 'Analyzer Agent',
                        'type': 'analyzer',
                        'is_healthy': True,
                        'current_tasks': 2,
                        'max_concurrent_tasks': 5
                    }),
                    "agent-2": type('Agent', (), {
                        'id': 'agent-2',
                        'name': 'Generator Agent',
                        'type': 'generator',
                        'is_healthy': True,
                        'current_tasks': 1,
                        'max_concurrent_tasks': 3
                    })
                }
            
            async def get_agent_status(self, agent_id):
                agent = self.agents.get(agent_id)
                if agent:
                    return {
                        "id": agent.id,
                        "name": agent.name,
                        "status": "active",
                        "load": agent.current_tasks / agent.max_concurrent_tasks
                    }
                return None
        
        # Wrapper le hub avec le cache
        print("\n🎭 Test du wrapper d'orchestration:")
        mock_hub = MockOrchestrationHub()
        cached_hub = cache_manager.wrap_orchestration_hub(mock_hub)
        
        # Test avec cache miss et cache hit
        print("  • Premier appel - liste des agents (cache miss):")
        start_time = time.time()
        agents1 = await cached_hub.list_agents()
        elapsed1 = time.time() - start_time
        print(f"    Agents trouvés: {len(agents1)}")
        print(f"    Temps: {elapsed1:.3f}s")
        
        print("  • Deuxième appel - liste des agents (cache hit):")
        start_time = time.time()
        agents2 = await cached_hub.list_agents()
        elapsed2 = time.time() - start_time
        print(f"    Agents trouvés: {len(agents2)}")
        print(f"    Temps: {elapsed2:.3f}s")
        
        if elapsed1 > 0 and elapsed2 > 0:
            print(f"    Accélération: {elapsed1/elapsed2:.1f}x plus rapide!")
        
        # Test du statut d'un agent spécifique
        print("\n  • Test du statut d'agent:")
        status = await cached_hub.get_agent_status("agent-1")
        print(f"    Statut agent-1: {status}")
        
        # Précharger le cache
        print("\n🔥 Préchargement du cache:")
        await cache_manager.warm_up_cache()
        print("✅ Cache préchauffé")
        
        # Statistiques du cache
        print("\n📊 Statistiques du cache:")
        stats = await cache_manager.get_cache_stats()
        
        print(f"  • Hits: {stats.get('hits', 0)}")
        print(f"  • Misses: {stats.get('misses', 0)}")
        print(f"  • Hit rate: {stats.get('hit_rate', 0):.2%}")
        print(f"  • Connexions actives: {stats.get('connected_clients', 0)}")
        print(f"  • Mémoire utilisée: {stats.get('used_memory_human', 'N/A')}")
        
        if 'namespaces' in stats:
            print(f"  • Clés par namespace:")
            for namespace, count in stats['namespaces'].items():
                print(f"    - {namespace}: {count} clés")
        
        # Test d'optimisation
        print("\n🔧 Optimisation du cache:")
        await cache_manager.optimize_cache()
        print("✅ Cache optimisé")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False
    
    finally:
        if cache_manager.is_connected:
            await cache_manager.disconnect()
            print("\n🔌 Cache Manager déconnecté")
    
    return True

async def demo_performance_comparison():
    """Démonstration des gains de performance avec cache"""
    print("\n" + "="*50)
    print("⚡ COMPARAISON DES PERFORMANCES")
    print("="*50)
    
    # Simulation de données de test
    test_data = []
    for i in range(100):
        test_data.append({
            "id": f"item_{i}",
            "name": f"Item {i}",
            "value": i * 1.5,
            "tags": [f"tag_{j}" for j in range(i % 5)],
            "timestamp": datetime.now().isoformat()
        })
    
    def expensive_search(query):
        """Simulation d'une recherche coûteuse"""
        time.sleep(0.01)  # Simulation de 10ms de latence
        results = [item for item in test_data if query.lower() in item["name"].lower()]
        return results
    
    config = CacheConfig(host="localhost", port=6379, db=0)
    cache = RedisCache(config)
    
    try:
        await cache.connect()
        
        queries = ["Item 1", "Item 2", "Item 5", "Item 10", "Item 1"]  # Répétition intentionnelle
        
        print(f"\n🧪 Test avec {len(queries)} requêtes:")
        
        # Sans cache
        print("\n  📋 Sans cache:")
        start_time = time.time()
        for i, query in enumerate(queries):
            results = expensive_search(query)
            print(f"    Requête {i+1}: '{query}' -> {len(results)} résultats")
        elapsed_no_cache = time.time() - start_time
        print(f"  ⏱️  Temps total: {elapsed_no_cache:.3f}s")
        
        # Avec cache
        print("\n  🗄️  Avec cache:")
        start_time = time.time()
        for i, query in enumerate(queries):
            cache_key = f"search:{query}"
            
            # Essayer le cache d'abord
            results = await cache.get("search", cache_key)
            
            if results is None:
                # Cache miss - calculer et stocker
                results = expensive_search(query)
                await cache.set("search", cache_key, results, ttl=60)
                status = "MISS"
            else:
                status = "HIT"
            
            print(f"    Requête {i+1}: '{query}' -> {len(results)} résultats [{status}]")
        
        elapsed_with_cache = time.time() - start_time
        print(f"  ⏱️  Temps total: {elapsed_with_cache:.3f}s")
        
        # Comparaison
        if elapsed_with_cache > 0:
            improvement = elapsed_no_cache / elapsed_with_cache
            savings = ((elapsed_no_cache - elapsed_with_cache) / elapsed_no_cache) * 100
            print(f"\n🚀 Amélioration des performances:")
            print(f"  • {improvement:.1f}x plus rapide")
            print(f"  • {savings:.1f}% de temps économisé")
        
        # Statistiques finales
        stats = await cache.get_stats()
        print(f"\n📈 Statistiques du cache:")
        print(f"  • Hits: {stats.get('hits', 0)}")
        print(f"  • Misses: {stats.get('misses', 0)}")
        print(f"  • Taux de succès: {stats.get('hit_rate', 0):.2%}")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False
    
    finally:
        if cache.is_connected:
            await cache.disconnect()
    
    return True

async def main():
    """Fonction principale de démonstration"""
    print("🎯 DÉMONSTRATION COMPLÈTE DU SYSTÈME DE CACHE REDIS")
    print("="*60)
    
    success = True
    
    # Test des opérations de base
    if not await demo_basic_cache():
        success = False
    
    # Test de l'intégration
    if not await demo_cache_integration():
        success = False
    
    # Test des performances
    if not await demo_performance_comparison():
        success = False
    
    print("\n" + "="*60)
    if success:
        print("🎉 DÉMONSTRATION TERMINÉE AVEC SUCCÈS!")
        print("\n💡 Le cache Redis est maintenant intégré dans Master Plan IA 2025:")
        print("  • Accélération des requêtes répétées")
        print("  • Réduction de la charge sur les composants")
        print("  • Amélioration de la scalabilité")
        print("  • Persistance des données temporaires")
        print("  • Patterns de cache avancés (write-through, cache-aside, etc.)")
    else:
        print("❌ CERTAINES DÉMONSTRATIONS ONT ÉCHOUÉ")
        print("💡 Vérifiez que Redis est installé et configuré correctement")
    
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())