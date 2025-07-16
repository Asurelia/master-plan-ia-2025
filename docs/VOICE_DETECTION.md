# 🎤 Détection Vocale - Master Plan IA 2025

## Vue d'ensemble

Le système de détection vocale intégré permet d'interagir avec Master Plan IA par la voix. Il utilise **Vosk** comme moteur de reconnaissance vocale offline, garantissant la confidentialité et la rapidité.

## Fonctionnalités

### ✅ Fonctionnalités implémentées

- **Reconnaissance vocale en temps réel** avec Vosk
- **Traitement des commandes vocales** avec mots-clés
- **API REST** pour contrôler la détection vocale
- **Stream temps réel** des résultats de reconnaissance
- **Support multilingue** (français, anglais, etc.)
- **Système de commandes personnalisables**
- **Authentification JWT** pour sécuriser l'accès

### 🔧 Architecture

```
core/
├── voice_detection.py          # Système principal de détection
├── orchestration_hub.py        # Intégration avec le hub
└── ...

api/
├── unified_api.py              # Endpoints API voice
└── ...

scripts/
├── download_vosk_model.py      # Script de téléchargement de modèles
└── ...

models/                         # Modèles Vosk (à télécharger)
├── vosk-model-small-fr-0.22/
└── ...
```

## Installation

### 1. Dépendances

```bash
pip install -r requirements.txt
```

Dépendances principales :
- `vosk==0.3.45` - Moteur de reconnaissance vocale
- `pyaudio==0.2.14` - Capture audio
- `sounddevice==0.5.1` - Alternative à PyAudio
- `librosa==0.10.1` - Traitement audio avancé

### 2. Téléchargement du modèle

```bash
# Modèle français léger (recommandé)
python scripts/download_vosk_model.py fr-small

# Modèle français complet (meilleure précision)
python scripts/download_vosk_model.py fr-large

# Modèle anglais
python scripts/download_vosk_model.py en-small

# Lister tous les modèles disponibles
python scripts/download_vosk_model.py --list
```

### 3. Configuration

Le système se configure automatiquement, mais vous pouvez personnaliser :

```python
from core.voice_detection import VoiceDetectionSystem

detector = VoiceDetectionSystem(
    model_path="models/vosk-model-small-fr-0.22",
    language="fr-FR",
    sample_rate=16000
)
```

## Utilisation

### 1. API REST

#### Démarrer la détection vocale
```bash
curl -X POST "http://localhost:8000/voice/start" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_path": "models/vosk-model-small-fr-0.22",
    "language": "fr-FR",
    "sample_rate": 16000
  }'
```

#### Arrêter la détection vocale
```bash
curl -X POST "http://localhost:8000/voice/stop" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### Vérifier le statut
```bash
curl "http://localhost:8000/voice/status"
```

#### Traiter une commande vocale
```bash
curl -X POST "http://localhost:8000/voice/command" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "master plan status",
    "timestamp": "2025-07-16T23:00:00Z"
  }'
```

#### Stream temps réel
```bash
curl "http://localhost:8000/voice/stream" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 2. Utilisation programmatique

```python
from core.voice_detection import VoiceDetectionSystem, VoiceCommandProcessor

# Initialiser le système
detector = VoiceDetectionSystem()
processor = VoiceCommandProcessor(detector)

# Enregistrer des commandes
processor.register_command(
    ["status", "état"],
    lambda text: {"action": "status", "message": "Système opérationnel"}
)

processor.register_command(
    ["aide", "help"],
    lambda text: {"action": "help", "message": "Commandes disponibles"}
)

# Démarrer l'écoute
def on_recognition(result):
    if result['is_final']:
        response = processor.process_command(result['text'])
        print(f"Commande: {result['text']}")
        print(f"Réponse: {response}")

detector.start_listening(callback=on_recognition)

# Garder le programme actif
input("Appuyez sur Entrée pour arrêter...")
detector.stop_listening()
```

### 3. Commandes vocales par défaut

Le système reconnaît ces **mots de réveil** :
- "master plan"
- "plan ia"
- "assistant"

**Commandes disponibles** :
- `"master plan status"` → Statut du système
- `"plan ia aide"` → Liste des commandes
- `"assistant arrêt"` → Arrêt du système

**Désactivation** :
- `"merci"` ou `"stop"` → Désactive l'écoute

## Modèles Vosk

### Modèles français

| Modèle | Taille | Précision | Usage recommandé |
|--------|--------|-----------|------------------|
| `fr-small` | 41M | Bonne | Utilisation continue |
| `fr-large` | 1.4G | Excellente | Transcription précise |

### Modèles anglais

| Modèle | Taille | Précision | Usage recommandé |
|--------|--------|-----------|------------------|
| `en-small` | 40M | Bonne | Utilisation continue |
| `en-large` | 1.8G | Excellente | Transcription précise |

### Modèles multilingues

| Modèle | Taille | Langues | Usage recommandé |
|--------|--------|---------|------------------|
| `multi-small` | 36M | EN, FR, ES, DE | Multi-langues |

## Configuration avancée

### Personnalisation des commandes

```python
processor = VoiceCommandProcessor(detector)

# Commande simple
processor.register_command(
    ["redémarrer", "restart"],
    lambda text: {"action": "restart", "message": "Redémarrage..."}
)

# Commande avec logique complexe
def handle_agent_command(text):
    if "status" in text:
        return {"action": "agent_status", "data": get_agent_status()}
    elif "créer" in text:
        return {"action": "create_agent", "message": "Création d'agent..."}
    return {"action": "unknown_agent_command"}

processor.register_command(["agent"], handle_agent_command)
```

### Intégration avec le hub d'orchestration

```python
from core.orchestration_hub import OrchestrationHub

hub = OrchestrationHub()
processor = VoiceCommandProcessor(detector)

# Commande pour créer une tâche
def create_task_command(text):
    task = {
        "type": "voice_task",
        "payload": {"command": text},
        "priority": 5
    }
    task_id = await hub.submit_task(task)
    return {"action": "task_created", "task_id": task_id}

processor.register_command(["créer tâche"], create_task_command)
```

## Tests

### Test basique
```bash
python test_voice_detection.py
```

### Test avec modèle
```bash
# Télécharger un modèle d'abord
python scripts/download_vosk_model.py fr-small

# Puis tester
python test_voice_detection.py
```

### Test de l'API
```bash
# Démarrer l'API
python api/unified_api.py

# Dans un autre terminal
curl "http://localhost:8000/voice/status"
```

## Dépannage

### Problèmes courants

#### 1. Vosk non installé
```
ImportError: No module named 'vosk'
```
**Solution** : `pip install vosk`

#### 2. PyAudio non installé
```
ImportError: No module named 'pyaudio'
```
**Solutions** :
- Ubuntu/Debian : `sudo apt-get install portaudio19-dev && pip install pyaudio`
- macOS : `brew install portaudio && pip install pyaudio`
- Windows : `pip install pyaudio`

#### 3. Modèle non trouvé
```
Could not load Vosk model from models/vosk-model-small-fr-0.22
```
**Solution** : `python scripts/download_vosk_model.py fr-small`

#### 4. Erreur de microphone
```
Error opening audio device
```
**Solutions** :
- Vérifier les permissions microphone
- Tester avec `python -c "import pyaudio; pyaudio.PyAudio()"`
- Utiliser `sounddevice` en alternative

### Logs de debug

```python
import logging
logging.basicConfig(level=logging.DEBUG)

detector = VoiceDetectionSystem()
detector.start_listening()
```

## Sécurité

### Authentification

Tous les endpoints vocaux nécessitent une authentification JWT :

```python
# Dans l'API
current_user: Dict[str, Any] = Depends(require_user)
```

### Confidentialité

- **Traitement 100% local** avec Vosk
- **Aucune donnée envoyée** vers des serveurs externes
- **Chiffrement des communications** API avec HTTPS

### Limitations

- **Modèles légers** : Précision moindre que les services cloud
- **Ressources CPU** : Traitement en temps réel
- **Langues supportées** : Limitées aux modèles Vosk disponibles

## Roadmap

### Version actuelle (1.0)
- ✅ Reconnaissance vocale basic avec Vosk
- ✅ Commandes vocales simple
- ✅ API REST intégrée
- ✅ Stream temps réel

### Version future (1.1)
- 🔄 Détection d'activité vocale (VAD)
- 🔄 Amélioration de la précision
- 🔄 Support de plus de langues
- 🔄 Interface web pour la configuration

### Version future (1.2)
- 🔄 Reconnaissance de locuteur
- 🔄 Commandes vocales contextuelles
- 🔄 Intégration avec TTS (text-to-speech)
- 🔄 Mode conversationnel

## Contributions

Pour contribuer au système de détection vocale :

1. **Fork** le projet
2. **Créer une branche** pour votre fonctionnalité
3. **Tester** avec `python test_voice_detection.py`
4. **Commiter** vos changements
5. **Créer une Pull Request**

## Support

- **Documentation** : Ce fichier
- **Tests** : `python test_voice_detection.py`
- **Issues** : GitHub Issues du projet
- **Communauté** : Discussions GitHub

---

*Master Plan IA 2025 - Système de détection vocale*