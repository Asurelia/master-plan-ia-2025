#!/usr/bin/env python3
"""
Master Plan IA 2025 - Test End-to-End
Test complet du système pour valider les corrections
"""

import asyncio
import json
import sys
import os
import time
import requests
from pathlib import Path
import subprocess
import signal
import logging
from typing import Dict, Any, List

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SystemTester:
    """Testeur complet du système Master Plan IA 2025"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.api_url = "http://localhost:8000"
        self.api_process = None
        self.test_results = []
        
    def log_test(self, test_name: str, success: bool, message: str = ""):
        """Log un résultat de test"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} - {test_name}: {message}")
        self.test_results.append({
            'test': test_name,
            'success': success,
            'message': message,
            'timestamp': time.time()
        })
    
    def test_dependencies(self) -> bool:
        """Test des dépendances Python"""
        logger.info("🔍 Testing Python dependencies...")
        
        required_modules = [
            'fastapi', 'uvicorn', 'pydantic', 'sqlalchemy', 
            'requests', 'asyncio', 'pathlib'
        ]
        
        all_success = True
        for module in required_modules:
            try:
                __import__(module)
                self.log_test(f"Import {module}", True)
            except ImportError as e:
                self.log_test(f"Import {module}", False, str(e))
                all_success = False
        
        return all_success
    
    def test_configuration(self) -> bool:
        """Test de la configuration"""
        logger.info("🔍 Testing configuration...")
        
        try:
            # Ajouter le chemin config
            sys.path.insert(0, str(self.project_root / 'config'))
            from settings import get_settings
            
            settings = get_settings()
            
            # Tester la validation
            errors = settings.validate_configuration()
            if errors:
                self.log_test("Configuration validation", False, f"Errors: {errors}")
                return False
            
            self.log_test("Configuration validation", True)
            
            # Tester l'accès aux propriétés
            self.log_test("API configuration", True, f"API: {settings.API_HOST}:{settings.API_PORT}")
            self.log_test("Database configuration", True, f"DB: {settings.DATABASE_URL}")
            
            return True
            
        except Exception as e:
            self.log_test("Configuration system", False, str(e))
            return False
    
    def test_database(self) -> bool:
        """Test de la base de données"""
        logger.info("🔍 Testing database...")
        
        try:
            # Ajouter les chemins nécessaires
            sys.path.insert(0, str(self.project_root / 'persistence'))
            sys.path.insert(0, str(self.project_root / 'config'))
            
            from database import DatabaseManager
            
            db_manager = DatabaseManager()
            db_manager.initialize()
            
            self.log_test("Database initialization", True)
            
            # Test création d'agent
            agent_data = {
                'id': 'test-agent-system',
                'type': 'test',
                'name': 'System Test Agent',
                'capabilities': ['test'],
                'config': {'test': True}
            }
            
            agent = db_manager.create_agent(agent_data)
            self.log_test("Agent creation", True, f"Agent ID: {agent.id}")
            
            # Test récupération
            retrieved_agent = db_manager.get_agent('test-agent-system')
            self.log_test("Agent retrieval", retrieved_agent is not None, 
                         f"Retrieved: {retrieved_agent.name if retrieved_agent else 'None'}")
            
            # Test statistiques
            stats = db_manager.get_system_stats()
            self.log_test("System stats", True, f"Agents: {stats['agents']['total']}")
            
            # Nettoyage
            db_manager.delete_agent('test-agent-system')
            self.log_test("Agent cleanup", True)
            
            return True
            
        except Exception as e:
            self.log_test("Database system", False, str(e))
            return False
    
    def test_core_modules(self) -> bool:
        """Test des modules core"""
        logger.info("🔍 Testing core modules...")
        
        try:
            # Ajouter le chemin core
            sys.path.insert(0, str(self.project_root / 'core'))
            
            # Test OrchestrationHub
            try:
                from orchestration_hub import OrchestrationHub, Agent, Task, AgentType
                hub = OrchestrationHub()
                self.log_test("OrchestrationHub import", True)
                
                # Test création d'agent
                agent = Agent(
                    id='test-agent',
                    type=AgentType.CUSTOM,
                    name='Test Agent',
                    capabilities=['test']
                )
                self.log_test("Agent creation", True, f"Agent: {agent.name}")
                
            except Exception as e:
                self.log_test("OrchestrationHub", False, str(e))
                return False
            
            # Test AgentCoordinator
            try:
                from agent_coordinator import AgentCoordinator, CoordinationPattern
                coordinator = AgentCoordinator(hub)
                self.log_test("AgentCoordinator import", True)
                
                # Test des patterns
                patterns = list(CoordinationPattern)
                self.log_test("Coordination patterns", True, f"Patterns: {len(patterns)}")
                
            except Exception as e:
                self.log_test("AgentCoordinator", False, str(e))
                return False
            
            return True
            
        except Exception as e:
            self.log_test("Core modules", False, str(e))
            return False
    
    def start_api_server(self) -> bool:
        """Démarre le serveur API"""
        logger.info("🚀 Starting API server...")
        
        try:
            # Démarrer le serveur en arrière-plan
            api_script = self.project_root / 'api' / 'unified_api.py'
            
            if not api_script.exists():
                self.log_test("API script exists", False, f"Script not found: {api_script}")
                return False
            
            # Lancer le serveur
            self.api_process = subprocess.Popen([
                sys.executable, str(api_script)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
            cwd=str(self.project_root))
            
            # Attendre que le serveur démarre
            max_wait = 30
            for i in range(max_wait):
                try:
                    response = requests.get(f"{self.api_url}/health", timeout=2)
                    if response.status_code == 200:
                        self.log_test("API server startup", True, f"Started in {i+1}s")
                        return True
                except:
                    pass
                time.sleep(1)
            
            self.log_test("API server startup", False, "Timeout after 30s")
            return False
            
        except Exception as e:
            self.log_test("API server startup", False, str(e))
            return False
    
    def test_api_endpoints(self) -> bool:
        """Test des endpoints API"""
        logger.info("🔍 Testing API endpoints...")
        
        try:
            # Test health check
            response = requests.get(f"{self.api_url}/health")
            self.log_test("Health endpoint", response.status_code == 200, 
                         f"Status: {response.status_code}")
            
            # Test root endpoint
            response = requests.get(f"{self.api_url}/")
            self.log_test("Root endpoint", response.status_code == 200, 
                         f"Status: {response.status_code}")
            
            # Test system status
            response = requests.get(f"{self.api_url}/system/status")
            self.log_test("System status endpoint", response.status_code == 200, 
                         f"Status: {response.status_code}")
            
            # Test agents list
            response = requests.get(f"{self.api_url}/agents")
            self.log_test("Agents list endpoint", response.status_code == 200, 
                         f"Status: {response.status_code}")
            
            # Test tasks list
            response = requests.get(f"{self.api_url}/tasks")
            self.log_test("Tasks list endpoint", response.status_code == 200, 
                         f"Status: {response.status_code}")
            
            # Test workflows list
            response = requests.get(f"{self.api_url}/workflows")
            self.log_test("Workflows list endpoint", response.status_code == 200, 
                         f"Status: {response.status_code}")
            
            # Test coordination patterns
            response = requests.get(f"{self.api_url}/patterns")
            self.log_test("Coordination patterns endpoint", response.status_code == 200, 
                         f"Status: {response.status_code}")
            
            return True
            
        except Exception as e:
            self.log_test("API endpoints", False, str(e))
            return False
    
    def test_api_functionality(self) -> bool:
        """Test de la fonctionnalité API"""
        logger.info("🔍 Testing API functionality...")
        
        try:
            # Test soumission de tâche
            task_data = {
                "type": "test",
                "payload": {"message": "Test task"}
            }
            
            response = requests.post(f"{self.api_url}/tasks", json=task_data)
            self.log_test("Task submission", response.status_code == 200, 
                         f"Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                task_id = result.get('task_id')
                
                # Récupérer la tâche
                if task_id:
                    response = requests.get(f"{self.api_url}/tasks/{task_id}")
                    self.log_test("Task retrieval", response.status_code == 200, 
                                 f"Status: {response.status_code}")
            
            # Test création de workflow
            workflow_data = {
                "name": "Test Workflow",
                "pattern": "sequential",
                "agents": ["test-agent"],
                "steps": [{"agent": "test-agent", "task": {"type": "test"}}]
            }
            
            response = requests.post(f"{self.api_url}/workflows", json=workflow_data)
            self.log_test("Workflow creation", response.status_code == 200, 
                         f"Status: {response.status_code}")
            
            return True
            
        except Exception as e:
            self.log_test("API functionality", False, str(e))
            return False
    
    def stop_api_server(self):
        """Arrête le serveur API"""
        if self.api_process:
            logger.info("🛑 Stopping API server...")
            self.api_process.terminate()
            try:
                self.api_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.api_process.kill()
            self.api_process = None
    
    def run_full_test(self) -> bool:
        """Exécute tous les tests"""
        logger.info("🧪 Starting Master Plan IA 2025 System Test")
        logger.info("=" * 50)
        
        all_success = True
        
        try:
            # Tests individuels
            all_success &= self.test_dependencies()
            all_success &= self.test_configuration()
            all_success &= self.test_database()
            all_success &= self.test_core_modules()
            
            # Tests avec serveur API
            if self.start_api_server():
                all_success &= self.test_api_endpoints()
                all_success &= self.test_api_functionality()
            else:
                all_success = False
            
        except KeyboardInterrupt:
            logger.info("🛑 Test interrupted by user")
            all_success = False
            
        finally:
            self.stop_api_server()
        
        # Résumé des résultats
        self.print_test_summary()
        
        return all_success
    
    def print_test_summary(self):
        """Affiche le résumé des tests"""
        logger.info("\n" + "=" * 50)
        logger.info("📊 TEST SUMMARY")
        logger.info("=" * 50)
        
        passed = sum(1 for result in self.test_results if result['success'])
        failed = len(self.test_results) - passed
        
        logger.info(f"Total tests: {len(self.test_results)}")
        logger.info(f"✅ Passed: {passed}")
        logger.info(f"❌ Failed: {failed}")
        logger.info(f"Success rate: {passed/len(self.test_results)*100:.1f}%")
        
        # Afficher les échecs
        if failed > 0:
            logger.info("\n❌ Failed tests:")
            for result in self.test_results:
                if not result['success']:
                    logger.info(f"  - {result['test']}: {result['message']}")
        
        logger.info("\n" + "=" * 50)
        
        if failed == 0:
            logger.info("🎉 ALL TESTS PASSED! Master Plan IA 2025 is ready!")
        else:
            logger.info("⚠️  Some tests failed. Please check the issues above.")
    
    def cleanup(self):
        """Nettoyage final"""
        self.stop_api_server()

def main():
    """Point d'entrée principal"""
    tester = SystemTester()
    
    # Gestionnaire de signaux pour nettoyage
    def signal_handler(signum, frame):
        logger.info("🛑 Received signal, cleaning up...")
        tester.cleanup()
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        success = tester.run_full_test()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        return 1
    finally:
        tester.cleanup()

if __name__ == "__main__":
    sys.exit(main())