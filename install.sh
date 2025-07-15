#!/bin/bash

# Master Plan IA 2025 - Installation Script
# Script d'installation et de configuration du système

set -e  # Arrêter en cas d'erreur

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$SCRIPT_DIR"
PYTHON_CMD="python3"
PIP_CMD="pip3"

# Fonctions utilitaires
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_command() {
    if command -v "$1" &> /dev/null; then
        log_success "$1 is installed"
        return 0
    else
        log_error "$1 is not installed"
        return 1
    fi
}

install_dependencies() {
    log_info "Installing Python dependencies..."
    
    # Essayer d'installer avec --break-system-packages pour Ubuntu/Debian récents
    if ! $PIP_CMD install -r requirements.txt --break-system-packages 2>/dev/null; then
        log_warning "Failed with --break-system-packages, trying --user"
        if ! $PIP_CMD install -r requirements.txt --user; then
            log_warning "Failed with --user, trying virtual environment"
            
            # Créer un environnement virtuel
            if ! $PYTHON_CMD -m venv venv; then
                log_error "Failed to create virtual environment"
                return 1
            fi
            
            source venv/bin/activate
            pip install -r requirements.txt
            log_success "Dependencies installed in virtual environment"
        else
            log_success "Dependencies installed for user"
        fi
    else
        log_success "Dependencies installed system-wide"
    fi
}

create_directories() {
    log_info "Creating necessary directories..."
    
    mkdir -p data logs config
    mkdir -p persistence/db
    
    log_success "Directories created"
}

create_config_files() {
    log_info "Creating configuration files..."
    
    # Créer le fichier .env
    cat > .env << 'EOF'
# Master Plan IA 2025 Configuration

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Observability
OBSERVABILITY_SERVER=http://localhost:4000

# Database
DATABASE_URL=sqlite:///./data/master_plan.db
REDIS_URL=redis://localhost:6379

# AI Providers
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OLLAMA_URL=http://localhost:11434

# Logging
LOG_LEVEL=INFO
LOG_DIR=./logs
EOF

    # Créer le fichier de configuration settings.py
    cat > config/settings.py << 'EOF'
import os
from pathlib import Path

# Chemin de base du projet
BASE_DIR = Path(__file__).resolve().parent.parent

# Configuration API
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Configuration Observabilité
OBSERVABILITY_SERVER = os.getenv("OBSERVABILITY_SERVER", "http://localhost:4000")

# Configuration Base de données
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/data/master_plan.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Configuration AI Providers
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Configuration Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = Path(os.getenv("LOG_DIR", str(BASE_DIR / "logs")))

# Créer les répertoires nécessaires
LOG_DIR.mkdir(exist_ok=True)
(BASE_DIR / "data").mkdir(exist_ok=True)
EOF

    log_success "Configuration files created"
}

create_database() {
    log_info "Creating database schema..."
    
    # Créer un script d'initialisation de la base de données
    cat > persistence/init_db.py << 'EOF'
#!/usr/bin/env python3

import sqlite3
import os
from pathlib import Path

def init_database():
    """Initialise la base de données SQLite"""
    db_path = Path(__file__).parent.parent / "data" / "master_plan.db"
    db_path.parent.mkdir(exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Table des agents
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            capabilities TEXT,
            config TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Table des tâches
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT,
            result TEXT,
            error TEXT,
            assigned_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Table des workflows
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            pattern TEXT NOT NULL,
            status TEXT NOT NULL,
            agents TEXT,
            steps TEXT,
            results TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Table des contextes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contexts (
            id TEXT PRIMARY KEY,
            data TEXT,
            metadata TEXT,
            version INTEGER DEFAULT 1,
            access_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    
    print("✅ Database initialized successfully")

if __name__ == "__main__":
    init_database()
EOF

    # Exécuter l'initialisation
    $PYTHON_CMD persistence/init_db.py
    
    log_success "Database schema created"
}

create_startup_script() {
    log_info "Creating startup script..."
    
    # Mise à jour du script start-master-plan.sh pour corriger les chemins
    sed -i 's|OBSERVABILITY_PATH="/home/rafai/observability"|OBSERVABILITY_PATH="$(cd "$PROJECT_ROOT/../observability" 2>/dev/null && pwd)"|' scripts/start-master-plan.sh
    
    log_success "Startup script updated"
}

run_tests() {
    log_info "Running basic tests..."
    
    # Test d'import des modules
    if $PYTHON_CMD -c "
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath('.')), 'core'))
try:
    from orchestration_hub import OrchestrationHub
    print('✅ orchestration_hub import successful')
except Exception as e:
    print(f'❌ orchestration_hub import failed: {e}')

try:
    from agent_coordinator import AgentCoordinator
    print('✅ agent_coordinator import successful')
except Exception as e:
    print(f'❌ agent_coordinator import failed: {e}')
"; then
        log_success "Module imports successful"
    else
        log_warning "Some module imports failed"
    fi
}

main() {
    echo "🚀 Master Plan IA 2025 - Installation"
    echo "===================================="
    
    # Vérifier les prérequis
    log_info "Checking prerequisites..."
    
    if ! check_command "$PYTHON_CMD"; then
        log_error "Python 3 is required but not installed"
        exit 1
    fi
    
    if ! check_command "$PIP_CMD"; then
        log_error "pip3 is required but not installed"
        exit 1
    fi
    
    # Changer vers le répertoire du projet
    cd "$PROJECT_ROOT"
    
    # Étapes d'installation
    install_dependencies
    create_directories
    create_config_files
    create_database
    create_startup_script
    run_tests
    
    echo
    echo "🎉 Installation completed successfully!"
    echo "===================================="
    echo
    echo "Next steps:"
    echo "1. Configure your API keys in .env file"
    echo "2. Start the system: ./scripts/start-master-plan.sh"
    echo "3. Check status: ./scripts/start-master-plan.sh status"
    echo "4. Run tests: ./scripts/start-master-plan.sh test"
    echo
    echo "URLs:"
    echo "• API: http://localhost:8000"
    echo "• Documentation: http://localhost:8000/docs"
    echo "• Health check: http://localhost:8000/health"
    echo
    echo "For help: ./scripts/start-master-plan.sh help"
}

# Exécuter le script
main "$@"