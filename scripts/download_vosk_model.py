#!/usr/bin/env python3
"""
Script to download and setup Vosk models for voice detection
"""

import os
import sys
import urllib.request
import zipfile
import argparse
from pathlib import Path

# Available Vosk models
VOSK_MODELS = {
    'fr-small': {
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip',
        'size': '41M',
        'description': 'Small French model (recommended for continuous use)'
    },
    'fr-large': {
        'url': 'https://alphacephei.com/vosk/models/vosk-model-fr-0.22.zip',
        'size': '1.4G',
        'description': 'Large French model (better accuracy)'
    },
    'en-small': {
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip',
        'size': '40M',
        'description': 'Small English model'
    },
    'multi-small': {
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip',
        'size': '36M',
        'description': 'Small multilingual model'
    }
}


def download_model(model_key: str, output_dir: str = 'models'):
    """Download and extract Vosk model"""
    
    if model_key not in VOSK_MODELS:
        print(f"Unknown model: {model_key}")
        print(f"Available models: {', '.join(VOSK_MODELS.keys())}")
        return False
    
    model_info = VOSK_MODELS[model_key]
    url = model_info['url']
    
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Download filename
    filename = url.split('/')[-1]
    filepath = os.path.join(output_dir, filename)
    
    print(f"Downloading {model_key} model ({model_info['size']})...")
    print(f"URL: {url}")
    
    try:
        # Download with progress
        def download_progress(block_num, block_size, total_size):
            downloaded = block_num * block_size
            percent = min(downloaded * 100 / total_size, 100)
            mb_downloaded = downloaded / 1024 / 1024
            mb_total = total_size / 1024 / 1024
            sys.stdout.write(f'\rProgress: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)')
            sys.stdout.flush()
        
        urllib.request.urlretrieve(url, filepath, download_progress)
        print("\nDownload complete!")
        
        # Extract
        print("Extracting model...")
        with zipfile.ZipFile(filepath, 'r') as zip_ref:
            zip_ref.extractall(output_dir)
        
        # Remove zip file
        os.remove(filepath)
        
        # Get extracted folder name
        model_dir = filepath.replace('.zip', '')
        
        print(f"Model extracted to: {model_dir}")
        print(f"Use this path in VoiceDetectionSystem: '{model_dir}'")
        
        return True
        
    except Exception as e:
        print(f"Error downloading model: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Download Vosk models for voice detection')
    parser.add_argument('model', nargs='?', default='fr-small',
                        choices=list(VOSK_MODELS.keys()),
                        help='Model to download (default: fr-small)')
    parser.add_argument('-o', '--output', default='models',
                        help='Output directory (default: models)')
    parser.add_argument('-l', '--list', action='store_true',
                        help='List available models')
    
    args = parser.parse_args()
    
    if args.list:
        print("\nAvailable Vosk models:")
        print("-" * 60)
        for key, info in VOSK_MODELS.items():
            print(f"{key:12} | {info['size']:6} | {info['description']}")
        print("-" * 60)
        return
    
    # Download selected model
    success = download_model(args.model, args.output)
    
    if success:
        print("\n✅ Model ready to use!")
        print("\nNext steps:")
        print("1. Install dependencies: pip install vosk pyaudio")
        print("2. Use the model in your code")
        print("\nExample usage:")
        print("```python")
        print("from core.voice_detection import VoiceDetectionSystem")
        print(f"detector = VoiceDetectionSystem(model_path='models/vosk-model-small-{args.model}-*')")
        print("detector.start_listening()")
        print("```")


if __name__ == "__main__":
    main()