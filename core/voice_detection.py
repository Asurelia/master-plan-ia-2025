"""
Voice Detection System using Vosk
Provides real-time speech-to-text capabilities for Master Plan IA
"""

import json
import logging
import asyncio
import threading
import queue
from typing import Optional, Callable, Dict, Any
from datetime import datetime

try:
    import vosk
    import pyaudio
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    logging.warning("Vosk or PyAudio not installed. Voice detection will be disabled.")

logger = logging.getLogger(__name__)


class VoiceDetectionSystem:
    """Real-time voice detection system using Vosk"""
    
    def __init__(self, model_path: str = "models/vosk-model-small-fr-0.22", 
                 language: str = "fr-FR",
                 sample_rate: int = 16000):
        """
        Initialize the voice detection system
        
        Args:
            model_path: Path to the Vosk model directory
            language: Language code (default: French)
            sample_rate: Audio sample rate (default: 16000)
        """
        self.model_path = model_path
        self.language = language
        self.sample_rate = sample_rate
        self.model = None
        self.recognizer = None
        self.stream = None
        self.audio = None
        self.is_listening = False
        self.audio_queue = queue.Queue()
        self.callbacks: Dict[str, Callable] = {}
        
        # Initialize if Vosk is available
        if VOSK_AVAILABLE:
            self._initialize_model()
    
    def _initialize_model(self):
        """Initialize Vosk model and recognizer"""
        try:
            # Load Vosk model
            if not vosk.Model(self.model_path):
                logger.error(f"Could not load Vosk model from {self.model_path}")
                return False
            
            self.model = vosk.Model(self.model_path)
            self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
            
            # Initialize PyAudio
            self.audio = pyaudio.PyAudio()
            
            logger.info(f"Voice detection initialized with model: {self.model_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize voice detection: {e}")
            return False
    
    def start_listening(self, callback: Optional[Callable] = None):
        """
        Start continuous voice detection
        
        Args:
            callback: Function to call with recognized text
        """
        if not VOSK_AVAILABLE:
            logger.error("Vosk not available. Cannot start listening.")
            return False
        
        if self.is_listening:
            logger.warning("Already listening")
            return False
        
        try:
            # Open audio stream
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=8192,
                stream_callback=self._audio_callback
            )
            
            self.is_listening = True
            self.stream.start_stream()
            
            # Start recognition thread
            recognition_thread = threading.Thread(target=self._recognition_loop, args=(callback,))
            recognition_thread.daemon = True
            recognition_thread.start()
            
            logger.info("Started voice detection")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start listening: {e}")
            return False
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback to capture audio data"""
        self.audio_queue.put(in_data)
        return (in_data, pyaudio.paContinue)
    
    def _recognition_loop(self, callback: Optional[Callable] = None):
        """Main recognition loop running in separate thread"""
        logger.info("Recognition loop started")
        
        while self.is_listening:
            try:
                # Get audio data from queue
                data = self.audio_queue.get(timeout=1)
                
                # Process with Vosk
                if self.recognizer.AcceptWaveform(data):
                    # Final result
                    result = json.loads(self.recognizer.Result())
                    text = result.get('text', '')
                    
                    if text:
                        self._process_recognition(text, is_final=True, callback=callback)
                else:
                    # Partial result
                    partial = json.loads(self.recognizer.PartialResult())
                    partial_text = partial.get('partial', '')
                    
                    if partial_text:
                        self._process_recognition(partial_text, is_final=False, callback=callback)
                        
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Recognition error: {e}")
    
    def _process_recognition(self, text: str, is_final: bool, callback: Optional[Callable] = None):
        """Process recognized text"""
        timestamp = datetime.now().isoformat()
        
        result = {
            'text': text,
            'is_final': is_final,
            'timestamp': timestamp,
            'language': self.language
        }
        
        # Log the recognition
        if is_final:
            logger.info(f"Recognized: {text}")
        else:
            logger.debug(f"Partial: {text}")
        
        # Call registered callbacks
        if callback:
            callback(result)
        
        # Call any registered event callbacks
        event_name = 'final_recognition' if is_final else 'partial_recognition'
        if event_name in self.callbacks:
            self.callbacks[event_name](result)
    
    def stop_listening(self):
        """Stop voice detection"""
        if not self.is_listening:
            return
        
        self.is_listening = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        logger.info("Stopped voice detection")
    
    def on(self, event: str, callback: Callable):
        """Register event callback"""
        self.callbacks[event] = callback
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of voice detection"""
        return {
            'is_listening': self.is_listening,
            'model_loaded': self.model is not None,
            'language': self.language,
            'sample_rate': self.sample_rate,
            'vosk_available': VOSK_AVAILABLE
        }
    
    async def async_listen(self, duration: Optional[int] = None) -> str:
        """
        Async method to listen for a specific duration
        
        Args:
            duration: Listening duration in seconds (None for continuous)
            
        Returns:
            Recognized text
        """
        result_text = ""
        result_event = asyncio.Event()
        
        def on_recognition(result):
            nonlocal result_text
            if result['is_final']:
                result_text = result['text']
                result_event.set()
        
        self.start_listening(callback=on_recognition)
        
        try:
            # Wait for recognition or timeout
            await asyncio.wait_for(result_event.wait(), timeout=duration)
        except asyncio.TimeoutError:
            pass
        finally:
            self.stop_listening()
        
        return result_text
    
    def __del__(self):
        """Cleanup on deletion"""
        if self.is_listening:
            self.stop_listening()
        
        if self.audio:
            self.audio.terminate()


# Integration with Master Plan IA
class VoiceCommandProcessor:
    """Process voice commands for Master Plan IA"""
    
    def __init__(self, voice_detector: VoiceDetectionSystem):
        self.voice_detector = voice_detector
        self.command_handlers = {}
        self.wake_words = ["master plan", "plan ia", "assistant"]
        self.is_active = False
        
    def register_command(self, keywords: list, handler: Callable):
        """Register command handler for specific keywords"""
        for keyword in keywords:
            self.command_handlers[keyword.lower()] = handler
    
    def process_command(self, text: str):
        """Process recognized text as command"""
        text_lower = text.lower()
        
        # Check for wake word
        if not self.is_active:
            for wake_word in self.wake_words:
                if wake_word in text_lower:
                    self.is_active = True
                    logger.info(f"Wake word detected: {wake_word}")
                    return {"action": "activated", "message": "À votre écoute"}
            return None
        
        # Process command
        for keyword, handler in self.command_handlers.items():
            if keyword in text_lower:
                try:
                    result = handler(text)
                    return result
                except Exception as e:
                    logger.error(f"Command handler error: {e}")
                    return {"error": str(e)}
        
        # Check for deactivation
        if "merci" in text_lower or "stop" in text_lower:
            self.is_active = False
            return {"action": "deactivated", "message": "À bientôt"}
        
        return {"action": "unknown", "text": text}


# Example usage and integration
if __name__ == "__main__":
    # Initialize voice detection
    detector = VoiceDetectionSystem()
    processor = VoiceCommandProcessor(detector)
    
    # Register some example commands
    processor.register_command(
        ["status", "état"],
        lambda text: {"action": "status", "message": "Système opérationnel"}
    )
    
    processor.register_command(
        ["aide", "help"],
        lambda text: {"action": "help", "message": "Commandes disponibles: status, aide"}
    )
    
    # Start listening
    def on_recognition(result):
        if result['is_final']:
            response = processor.process_command(result['text'])
            if response:
                print(f"Response: {response}")
    
    detector.start_listening(callback=on_recognition)
    
    try:
        # Keep running
        input("Appuyez sur Entrée pour arrêter...\n")
    finally:
        detector.stop_listening()