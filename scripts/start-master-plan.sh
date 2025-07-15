#!/bin/bash

# Master Plan IA 2025 - Startup Script
# Lance l'écosystème complet d'IA unifiée

echo "🚀 Master Plan IA 2025 - Démarrage"
echo "=================================="

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
OBSERVABILITY_PATH="$(cd "$PROJECT_ROOT/../observability" 2>/dev/null && pwd)"

# Fonction de vérification
check_service() {
    local service_name=$1
    local check_command=$2
    
    if eval $check_command >/dev/null 2>&1; then
        echo -e "${GREEN}✅ $service_name${NC}"
        return 0
    else
        echo -e "${RED}❌ $service_name${NC}"
        return 1
    fi
}

# Fonction principale
main() {
    case "${1:-start}" in
        "start")
            echo -e "${BLUE}🔧 Vérification des prérequis...${NC}"
            
            # Vérifier Python
            if ! command -v python3 >/dev/null 2>&1; then
                echo -e "${RED}❌ Python 3 requis${NC}"
                exit 1
            fi
            
            # Vérifier les dépendances
            echo -e "${BLUE}📦 Installation des dépendances...${NC}"
            pip3 install fastapi uvicorn networkx --break-system-packages 2>/dev/null || pip3 install --user fastapi uvicorn networkx
            
            echo -e "\n${BLUE}🎛️ Démarrage du système d'observabilité...${NC}"
            
            # Démarrer le système d'observabilité
            if [ -d "$OBSERVABILITY_PATH" ]; then
                cd "$OBSERVABILITY_PATH"
                if [ -f "scripts/start-system.sh" ]; then
                    echo -e "${YELLOW}⚡ Démarrage du monitoring multi-IA...${NC}"
                    ./scripts/start-system.sh > /tmp/observability.log 2>&1 &
                    OBSERVABILITY_PID=$!
                    sleep 5
                    
                    # Vérifier que le serveur est démarré
                    if curl -s http://localhost:4000/health >/dev/null 2>&1; then
                        echo -e "${GREEN}✅ Système d'observabilité démarré${NC}"
                    else
                        echo -e "${RED}❌ Échec démarrage observabilité${NC}"
                    fi
                    
                    # Démarrer les adaptateurs multi-IA
                    if [ -f "adapters/start-multi-ai-monitoring.sh" ]; then
                        echo -e "${YELLOW}⚡ Démarrage des adaptateurs multi-IA...${NC}"
                        cd adapters
                        ./start-multi-ai-monitoring.sh start > /tmp/multi-ai-adapters.log 2>&1 &
                        cd ..
                        sleep 3
                        echo -e "${GREEN}✅ Adaptateurs multi-IA démarrés${NC}"
                    fi
                fi
            else
                echo -e "${YELLOW}⚠️  Système d'observabilité non trouvé${NC}"
                echo -e "${YELLOW}   Continuons sans monitoring avancé${NC}"
            fi
            
            echo -e "\n${BLUE}🚀 Démarrage Master Plan IA 2025...${NC}"
            
            # Démarrer l'API unifiée
            cd "$PROJECT_ROOT"
            echo -e "${YELLOW}⚡ Démarrage de l'API unifiée...${NC}"
            python3 api/unified_api.py > /tmp/master-plan-api.log 2>&1 &
            API_PID=$!
            sleep 5
            
            # Vérifier que l'API est démarrée
            if curl -s http://localhost:8000/health >/dev/null 2>&1; then
                echo -e "${GREEN}✅ API Master Plan démarrée${NC}"
            else
                echo -e "${RED}❌ Échec démarrage API Master Plan${NC}"
            fi
            
            echo -e "\n${BLUE}=====================================${NC}"
            echo -e "${GREEN}🎉 Master Plan IA 2025 Opérationnel !${NC}"
            echo -e "${BLUE}=====================================${NC}"
            echo
            echo -e "🌐 API Master Plan:     ${GREEN}http://localhost:8000${NC}"
            echo -e "📊 Dashboard Monitoring: ${GREEN}http://localhost:5173${NC}"
            echo -e "🔧 API Observabilité:   ${GREEN}http://localhost:4000${NC}"
            echo
            echo -e "📋 Endpoints principaux:"
            echo -e "   • Statut système:    ${YELLOW}GET /system/status${NC}"
            echo -e "   • Agents:           ${YELLOW}GET /agents${NC}"
            echo -e "   • Tâches:           ${YELLOW}GET /tasks${NC}"
            echo -e "   • Workflows:        ${YELLOW}GET /workflows${NC}"
            echo -e "   • Coordination:     ${YELLOW}POST /coordination/collaborate${NC}"
            echo -e "   • Monitoring:       ${YELLOW}GET /monitoring/events${NC}"
            echo
            echo -e "📖 Documentation:       ${GREEN}http://localhost:8000/docs${NC}"
            echo -e "💻 Logs:               ${YELLOW}tail -f /tmp/master-plan-*.log${NC}"
            echo
            echo -e "Pour arrêter:           ${YELLOW}$0 stop${NC}"
            ;;
            
        "stop")
            echo -e "${YELLOW}🛑 Arrêt du Master Plan IA 2025...${NC}"
            
            # Arrêter les processus
            pkill -f "python3 api/unified_api.py" 2>/dev/null || true
            pkill -f "start-system.sh" 2>/dev/null || true
            pkill -f "start-multi-ai-monitoring.sh" 2>/dev/null || true
            
            # Arrêter le système d'observabilité
            if [ -d "$OBSERVABILITY_PATH" ]; then
                cd "$OBSERVABILITY_PATH"
                if [ -f "scripts/reset-system.sh" ]; then
                    ./scripts/reset-system.sh >/dev/null 2>&1 || true
                fi
                if [ -f "adapters/start-multi-ai-monitoring.sh" ]; then
                    cd adapters
                    ./start-multi-ai-monitoring.sh stop >/dev/null 2>&1 || true
                fi
            fi
            
            echo -e "${GREEN}✅ Master Plan IA 2025 arrêté${NC}"
            ;;
            
        "status")
            echo -e "${BLUE}📊 Statut Master Plan IA 2025${NC}"
            echo "=========================="
            
            # Vérifier les services
            check_service "API Master Plan (8000)" "curl -s http://localhost:8000/health"
            check_service "Observabilité (4000)" "curl -s http://localhost:4000/health"
            check_service "Dashboard (5173)" "curl -s http://localhost:5173"
            
            echo
            echo -e "${BLUE}🧠 Agents disponibles:${NC}"
            curl -s http://localhost:8000/agents 2>/dev/null | python3 -m json.tool 2>/dev/null | grep '"name"' | head -5 || echo "   API non disponible"
            
            echo
            echo -e "${BLUE}📋 Tâches récentes:${NC}"
            curl -s http://localhost:8000/tasks 2>/dev/null | python3 -m json.tool 2>/dev/null | grep '"status"' | head -5 || echo "   API non disponible"
            ;;
            
        "test")
            echo -e "${BLUE}🧪 Test du Master Plan IA 2025${NC}"
            echo "============================"
            
            # Test de base
            echo -e "${YELLOW}1. Test de santé...${NC}"
            curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "❌ API non disponible"
            
            echo -e "\n${YELLOW}2. Test soumission tâche...${NC}"
            curl -s -X POST http://localhost:8000/tasks \
                -H "Content-Type: application/json" \
                -d '{"type": "test", "payload": {"message": "Hello Master Plan IA 2025"}}' \
                | python3 -m json.tool 2>/dev/null || echo "❌ Échec soumission tâche"
            
            echo -e "\n${YELLOW}3. Test création workflow...${NC}"
            curl -s -X POST http://localhost:8000/workflows \
                -H "Content-Type: application/json" \
                -d '{"name": "Test Workflow", "pattern": "sequential", "agents": ["llm-session-default"], "steps": [{"agent": "llm-session-default", "task": {"type": "test"}}]}' \
                | python3 -m json.tool 2>/dev/null || echo "❌ Échec création workflow"
            
            echo -e "\n${GREEN}✅ Tests terminés${NC}"
            ;;
            
        "logs")
            echo -e "${BLUE}📜 Logs Master Plan IA 2025${NC}"
            echo "=========================="
            
            echo -e "\n${YELLOW}API Master Plan:${NC}"
            [ -f "/tmp/master-plan-api.log" ] && tail -20 /tmp/master-plan-api.log || echo "Pas de logs API"
            
            echo -e "\n${YELLOW}Observabilité:${NC}"
            [ -f "/tmp/observability.log" ] && tail -20 /tmp/observability.log || echo "Pas de logs observabilité"
            
            echo -e "\n${YELLOW}Adaptateurs Multi-IA:${NC}"
            [ -f "/tmp/multi-ai-adapters.log" ] && tail -20 /tmp/multi-ai-adapters.log || echo "Pas de logs adaptateurs"
            ;;
            
        "help"|"-h"|"--help")
            echo "Master Plan IA 2025 - Système d'orchestration IA unifié"
            echo
            echo "Usage: $0 [commande]"
            echo
            echo "Commandes:"
            echo "  start    Démarrer le système complet (défaut)"
            echo "  stop     Arrêter le système"
            echo "  status   Afficher le statut des services"
            echo "  test     Exécuter des tests de base"
            echo "  logs     Afficher les logs"
            echo "  help     Afficher cette aide"
            echo
            echo "Fonctionnalités:"
            echo "  • Orchestration multi-agents (Claude, LLM Session, Ollama)"
            echo "  • Coordination intelligente (6 patterns)"
            echo "  • API unifiée REST + WebSocket"
            echo "  • Monitoring temps réel intégré"
            echo "  • Dashboard d'observabilité"
            echo
            echo "Ports utilisés:"
            echo "  • 8000: API Master Plan"
            echo "  • 4000: Observabilité"
            echo "  • 5173: Dashboard"
            echo "  • 11434: Ollama (optionnel)"
            ;;
            
        *)
            echo -e "${RED}Commande inconnue: $1${NC}"
            echo "Utilisez '$0 help' pour l'aide"
            exit 1
            ;;
    esac
}

# Gestion des signaux
cleanup() {
    echo -e "\n${YELLOW}Signal reçu, arrêt en cours...${NC}"
    $0 stop
    exit 0
}

trap cleanup INT TERM

# Exécuter
main "$@"