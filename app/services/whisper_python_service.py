"""
Python Whisper transcription service
"""
import os
import threading

try:
    import whisper
    import torch
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    whisper = None
    torch = None

from ..config.logging_config import get_logger
from ..config.settings import settings
from ..exceptions.custom_exceptions import TranscriptionError

logger = get_logger(__name__)


class WhisperPythonService:
    """Python Whisper transcription service using OpenAI Whisper"""
    
    def __init__(self):
        self.model = None
        self.model_name = None
        self.device = None
        self.available_models = [
            "tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"
        ]
        self.lock = threading.Lock()
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize Whisper Python service"""
        try:
            if not WHISPER_AVAILABLE:
                logger.warning("Python Whisper not available. Install with: pip install openai-whisper torch")
                return
            
            # Determine optimal device
            self.device = self._get_optimal_device()
            logger.info(f"✓ Python Whisper initialized on device: {self.device}")
            logger.info(f"✓ Available models: {self.available_models}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Python Whisper: {e}")
    
    def _get_optimal_device(self) -> str:
        """Determine the best available device for Whisper"""
        if not torch:
            return "cpu"
        
        # Check device preference from settings
        device_preference = getattr(settings, 'whisper_device', 'auto')
        
        if device_preference != 'auto':
            if device_preference == 'cuda' and torch.cuda.is_available():
                return 'cuda'
            elif device_preference == 'mps' and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return 'mps'
            elif device_preference == 'cpu':
                return 'cpu'
            else:
                logger.warning(f"Requested device '{device_preference}' not available, falling back to auto-detection")
        
        # Auto-detect best device
        if torch.cuda.is_available():
            return 'cuda'
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return 'mps'
        else:
            return 'cpu'
    
    def _load_model(self, model_name: str) -> None:
        """Load Whisper model if not already loaded"""
        with self.lock:
            if self.model is None or self.model_name != model_name:
                logger.info(f"Loading Whisper model: {model_name} on {self.device}")
                
                try:
                    # Set download root if specified
                    download_root = getattr(settings, 'whisper_cache_dir', None)
                    if download_root:
                        os.makedirs(download_root, exist_ok=True)
                    
                    self.model = whisper.load_model(
                        model_name, 
                        device=self.device,
                        download_root=download_root
                    )
                    self.model_name = model_name
                    logger.info(f"✓ Model {model_name} loaded successfully")
                    
                except Exception as e:
                    logger.error(f"Failed to load model {model_name}: {e}")
                    raise TranscriptionError(f"Failed to load Whisper model: {e}")
    
    def is_available(self) -> bool:
        """Check if Python Whisper is available"""
        return WHISPER_AVAILABLE
    
    def get_best_model(self) -> str:
        """Get the best available model based on settings"""
        default_model = getattr(settings, 'whisper_python_model', 'base')
        
        if default_model in self.available_models:
            return default_model
        
        # Fallback to base if configured model is not available
        logger.warning(f"Configured model '{default_model}' not in available models, using 'base'")
        return 'base'
    
    def transcribe_url(self, audio_url: str) -> str:
        """
        Transcribe audio from URL using Python Whisper
        
        Args:
            audio_url: URL to audio file
            
        Returns:
            Transcription text
        """
        try:
            logger.debug(f"Transcribing URL with Python Whisper: {audio_url}")
            
            # Load model if needed
            if not self.model:
                model = self.get_best_model()
                self._load_model(model)
            
            # Transcribe URL directly
            with self.lock:
                result = self.model.transcribe(
                    audio_url,
                    verbose=False,
                    temperature=0,
                    best_of=1,
                    beam_size=1,
                    word_timestamps=True
                )
            
            transcription = result["text"].strip()
            logger.debug(f"URL transcription completed: {len(transcription)} characters")
            
            return transcription
            
        except Exception as e:
            logger.error(f"URL transcription failed for {audio_url}: {e}")
            raise TranscriptionError(f"URL transcription failed: {e}")
    
    def transcribe_url_with_words(self, audio_url: str) -> dict:
        """
        Transcribe audio from URL with word-level timestamps for progressive subtitles
        
        Args:
            audio_url: URL to audio file
            
        Returns:
            Complete Whisper result with segments and word timestamps
        """
        try:
            logger.debug(f"Transcribing URL with word timestamps: {audio_url}")
            
            # Load model if needed
            if not self.model:
                model = self.get_best_model()
                self._load_model(model)
            
            # Transcribe URL directly with word timestamps
            with self.lock:
                result = self.model.transcribe(
                    audio_url,
                    verbose=False,
                    temperature=0,
                    best_of=1,
                    beam_size=1,
                    word_timestamps=True
                )
            
            logger.debug(f"URL transcription with words completed: {len(result['segments'])} segments")
            return result
            
        except Exception as e:
            logger.error(f"URL transcription with words failed for {audio_url}: {e}")
            raise TranscriptionError(f"URL transcription with words failed: {e}")
    
    def get_info(self) -> dict:
        """Get Python Whisper service information"""
        info = {
            "available": self.is_available(),
            "backend": "python",
            "device": self.device,
            "available_models": self.available_models,
            "loaded_model": self.model_name,
            "best_model": self.get_best_model() if self.is_available() else None
        }
        
        if WHISPER_AVAILABLE and torch:
            info.update({
                "torch_version": torch.__version__,
                "cuda_available": torch.cuda.is_available(),
                "mps_available": hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()
            })
        
        return info
    
    def unload_model(self) -> None:
        """Unload the current model to free memory"""
        with self.lock:
            if self.model is not None:
                logger.info(f"Unloading model: {self.model_name}")
                del self.model
                self.model = None
                self.model_name = None
                
                # Force garbage collection
                if torch and torch.cuda.is_available():
                    torch.cuda.empty_cache()
    
    def __del__(self):
        """Cleanup when service is destroyed"""
        try:
            self.unload_model()
        except:
            pass