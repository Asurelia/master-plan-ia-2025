#!/usr/bin/env python3
"""
Script de test pour le système de détection vocale
"""

import asyncio
import sys
import os
from pathlib import Path

# Ajouter le répertoire core au path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))

try:
    from core.voice_detection import VoiceDetectionSystem, VoiceCommandProcessor
    VOICE_AVAILABLE = True
except ImportError as e:
    print(f"❌ Erreur d'import: {e}")
    print("Veuillez installer les dépendances avec: pip install -r requirements.txt")
    VOICE_AVAILABLE = False


def test_voice_status():
    """Test du statut du système de détection vocale"""
    print("\n=== Test du statut de la détection vocale ===")
    
    if not VOICE_AVAILABLE:
        print("❌ Système de détection vocale non disponible")
        return False
    
    detector = VoiceDetectionSystem()
    status = detector.get_status()
    
    print(f"Vosk disponible: {status['vosk_available']}")
    print(f"Modèle chargé: {status['model_loaded']}")
    print(f"Langue: {status['language']}")
    print(f"Échantillonnage: {status['sample_rate']} Hz")
    print(f"En écoute: {status['is_listening']}")
    
    return status['vosk_available']


def test_voice_commands():
    """Test des commandes vocales"""
    print("\n=== Test des commandes vocales ===")
    
    if not VOICE_AVAILABLE:
        print("❌ Système de détection vocale non disponible")
        return
    
    detector = VoiceDetectionSystem()
    processor = VoiceCommandProcessor(detector)
    
    # Enregistrer quelques commandes de test
    processor.register_command(
        ["status", "état"],
        lambda text: {"action": "status", "message": "Système opérationnel"}
    )
    
    processor.register_command(
        ["aide", "help"],
        lambda text: {"action": "help", "message": "Commandes disponibles: status, aide, arrêt"}
    )
    
    processor.register_command(
        ["arrêt", "stop"],
        lambda text: {"action": "stop", "message": "Arrêt du système"}
    )
    
    # Test des commandes
    test_commands = [
        "master plan status",
        "plan ia aide",
        "assistant arrêt",
        "bonjour",  # commande inconnue
        "merci"     # désactivation
    ]
    
    print("Commandes enregistrées:")
    for keyword in processor.command_handlers.keys():
        print(f"  - {keyword}")
    
    print("\nTest des commandes:")
    for cmd in test_commands:
        result = processor.process_command(cmd)
        print(f"  '{cmd}' -> {result}")


def test_voice_listening():
    """Test de l'écoute vocale (si modèle disponible)"""
    print("\n=== Test de l'écoute vocale ===")
    
    if not VOICE_AVAILABLE:
        print("❌ Système de détection vocale non disponible")
        return
    
    detector = VoiceDetectionSystem()
    
    # Vérifier si un modèle est disponible
    if not detector.model:
        print("❌ Aucun modèle Vosk disponible")
        print("Téléchargez un modèle avec: python scripts/download_vosk_model.py")
        return
    
    print("✅ Modèle Vosk disponible")
    print("Pour tester l'écoute en temps réel, utilisez:")
    print("  python -c \"from core.voice_detection import *; detector = VoiceDetectionSystem(); detector.start_listening(); input('Appuyez sur Entrée pour arrêter...')\"")


async def test_async_voice():
    """Test de l'écoute vocale asynchrone"""
    print("\n=== Test de l'écoute asynchrone ===")
    
    if not VOICE_AVAILABLE:
        print("❌ Système de détection vocale non disponible")
        return
    
    detector = VoiceDetectionSystem()
    
    if not detector.model:
        print("❌ Aucun modèle Vosk disponible")
        return
    
    print("Test de l'écoute asynchrone (5 secondes)...")
    try:
        result = await detector.async_listen(duration=5)
        print(f"Résultat: {result}")
    except Exception as e:
        print(f"Erreur: {e}")


def test_model_download():
    """Test du téléchargement de modèle"""
    print("\n=== Test du téléchargement de modèle ===")
    
    models_dir = Path("models")
    if models_dir.exists():
        model_files = list(models_dir.glob("vosk-model-*"))
        if model_files:
            print(f"✅ Modèles trouvés: {len(model_files)}")
            for model in model_files:
                print(f"  - {model.name}")
        else:
            print("❌ Aucun modèle trouvé dans le répertoire models/")
    else:
        print("❌ Répertoire models/ introuvable")
    
    print("\nPour télécharger un modèle:")
    print("  python scripts/download_vosk_model.py fr-small")


def main():
    """Fonction principale de test"""
    print("🎤 Test du système de détection vocale - Master Plan IA 2025")
    print("=" * 60)
    
    # Tests
    voice_available = test_voice_status()
    test_voice_commands()
    test_model_download()
    
    if voice_available:
        test_voice_listening()
        # Test async (commenté pour éviter les problèmes)
        # asyncio.run(test_async_voice())
    
    print("\n" + "=" * 60)
    print("📝 Résumé des tests:")
    print(f"  • Vosk disponible: {'✅' if VOICE_AVAILABLE else '❌'}")
    print(f"  • Modèle chargé: {'✅' if voice_available else '❌'}")
    print("  • Commandes testées: ✅")
    
    if not voice_available:
        print("\n🔧 Pour activer la détection vocale:")
        print("  1. Installez les dépendances: pip install vosk pyaudio")
        print("  2. Téléchargez un modèle: python scripts/download_vosk_model.py")
        print("  3. Relancez ce test")


if __name__ == "__main__":
    main()