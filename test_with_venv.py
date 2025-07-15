#!/usr/bin/env python3
"""
Master Plan IA 2025 - Test avec environnement virtuel
Test complet du système avec environnement virtuel
"""

import os
import sys
import subprocess
import time
import logging
from pathlib import Path

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_with_venv():
    """Exécute le test avec l'environnement virtuel"""
    project_root = Path(__file__).parent
    venv_path = project_root / "venv"
    
    if not venv_path.exists():
        logger.error("❌ Environnement virtuel non trouvé. Exécutez d'abord: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt")
        return 1
    
    # Chemins vers l'environnement virtuel
    venv_python = venv_path / "bin" / "python"
    
    if not venv_python.exists():
        logger.error("❌ Python de l'environnement virtuel non trouvé")
        return 1
    
    # Exécuter le test avec l'environnement virtuel
    logger.info("🚀 Exécution du test avec l'environnement virtuel")
    
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv_path)
    env["PATH"] = f"{venv_path}/bin:{env.get('PATH', '')}"
    
    try:
        result = subprocess.run([
            str(venv_python), 
            str(project_root / "test_system.py")
        ], env=env, cwd=str(project_root))
        
        return result.returncode
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'exécution: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(run_with_venv())