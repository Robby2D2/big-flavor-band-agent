"""
Lyrics Extractor Module
Extracts lyrics from audio files using vocal separation (Demucs) and transcription (faster-whisper).

This two-step approach provides higher accuracy:
1. Demucs separates vocals from instrumentals
2. faster-whisper transcribes the isolated vocals
"""

import logging
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
import subprocess
import json

logger = logging.getLogger("lyrics-extractor")

# Check for faster-whisper availability
FASTER_WHISPER_AVAILABLE = False
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
    logger.info("faster-whisper loaded successfully")
except ImportError:
    logger.warning("faster-whisper not available. Install with: pip install faster-whisper")

# Check for demucs availability
DEMUCS_AVAILABLE = False
try:
    import torch
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    from demucs.audio import convert_audio
    DEMUCS_AVAILABLE = True
    logger.info("demucs loaded successfully")
except ImportError as e:
    logger.warning(f"demucs not available: {e}. Install with: pip install demucs")


class LyricsExtractor:
    """
    Extract lyrics from audio files using vocal separation and transcription.
    """
    
    def __init__(
        self,
        whisper_model_size: str = "base",
        use_gpu: bool = True,
        demucs_model: str = "htdemucs",
        min_confidence: float = 0.5
    ):
        """
        Initialize the lyrics extractor.
        
        Args:
            whisper_model_size: Model size for faster-whisper 
                               ('tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3')
                               'base' is recommended for balance of speed/accuracy
            use_gpu: Whether to use GPU acceleration (if available)
            demucs_model: Demucs model to use ('htdemucs', 'htdemucs_ft', 'mdx_extra')
                         'htdemucs' is recommended for best quality
            min_confidence: Minimum confidence threshold for including transcribed text
        """
        self.whisper_model_size = whisper_model_size
        self.use_gpu = use_gpu
        self.demucs_model = demucs_model
        self.min_confidence = min_confidence
        
        # Initialize faster-whisper model
        self.whisper_model = None
        if FASTER_WHISPER_AVAILABLE:
            try:
                device = "cuda" if use_gpu and self._cuda_available() else "cpu"
                compute_type = "float16" if device == "cuda" else "int8"
                
                logger.info(f"Loading faster-whisper model '{whisper_model_size}' on {device}")
                self.whisper_model = WhisperModel(
                    whisper_model_size,
                    device=device,
                    compute_type=compute_type
                )
                logger.info(f"faster-whisper model loaded successfully on {device}")
            except Exception as e:
                logger.error(f"Failed to load faster-whisper model: {e}")
                self.whisper_model = None
        
        # Demucs model
        self.demucs = None
        self.device = None
        if DEMUCS_AVAILABLE:
            try:
                logger.info(f"Loading Demucs model '{demucs_model}'")
                self.demucs = get_model(demucs_model)
                self.device = "cuda" if use_gpu and self._cuda_available() else "cpu"
                self.demucs.to(self.device)
                logger.info(f"Demucs model loaded successfully on {self.device}")
            except Exception as e:
                logger.error(f"Failed to load Demucs model: {e}")
                self.demucs = None
        
        logger.info(f"LyricsExtractor initialized (Whisper: {self.whisper_model is not None}, Demucs: {self.demucs is not None})")
    
    def _cuda_available(self) -> bool:
        """Check if CUDA is available for GPU acceleration."""
        try:
            import torch
            return torch.cuda.is_available()
        except:
            return False
    
    def separate_vocals(self, audio_path: str, output_dir: Optional[str] = None) -> Optional[str]:
        """
        Separate vocals from audio using Demucs.
        
        Args:
            audio_path: Path to input audio file
            output_dir: Directory to save separated vocals (temp dir if None)
            
        Returns:
            Path to separated vocals file, or None if separation failed
        """
        if not DEMUCS_AVAILABLE or self.demucs is None:
            logger.warning("Demucs not available, skipping vocal separation")
            return audio_path  # Return original file if separation not available
        
        try:
            logger.info(f"Separating vocals from {audio_path}")
            
            # Create temp directory if not specified
            if output_dir is None:
                output_dir = tempfile.mkdtemp(prefix="demucs_")
            else:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # Load audio file using librosa (more compatible)
            import librosa
            import numpy as np
            
            audio_data, sr = librosa.load(audio_path, sr=None, mono=False)
            
            # Convert to torch tensor
            if audio_data.ndim == 1:
                # Mono - convert to stereo for demucs
                audio_data = np.stack([audio_data, audio_data])
            
            wav = torch.from_numpy(audio_data).float()
            
            # Convert to the model's expected format
            wav = convert_audio(wav, sr, self.demucs.samplerate, self.demucs.audio_channels)
            
            # Apply the model
            ref = wav.mean(0)
            wav = (wav - ref.mean()) / ref.std()
            
            with torch.no_grad():
                sources = apply_model(
                    self.demucs,
                    wav[None].to(self.device),
                    device=self.device,
                    shifts=1,
                    split=True,
                    overlap=0.25,
                    progress=False
                )[0]
            
            sources = sources * ref.std() + ref.mean()
            
            # Extract vocals (index depends on model, usually index 3 for htdemucs)
            # htdemucs order: drums, bass, other, vocals
            vocals = sources[3]  # vocals stem
            
            # Save vocals to file using soundfile to avoid torchcodec issues
            vocals_path = Path(output_dir) / "vocals.wav"
            vocals = vocals.cpu().numpy()
            
            import soundfile as sf
            # Transpose to (samples, channels) format for soundfile
            if vocals.ndim > 1:
                vocals = vocals.T
            
            sf.write(str(vocals_path), vocals, self.demucs.samplerate)
            
            logger.info(f"Vocals separated successfully: {vocals_path}")
            return str(vocals_path)
            
        except Exception as e:
            logger.error(f"Error separating vocals: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return audio_path  # Fallback to original file
    
    def transcribe_audio(
        self,
        audio_path: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Transcribe audio to text using faster-whisper.
        
        Args:
            audio_path: Path to audio file (preferably vocals only)
            language: Language code for transcription ('en' for English)
            
        Returns:
            Dictionary with transcription results
        """
        if not FASTER_WHISPER_AVAILABLE or self.whisper_model is None:
            return {
                'lyrics': '',
                'segments': [],
                'confidence': 0.0,
                'error': 'faster-whisper not available'
            }
        
        try:
            logger.info(f"Transcribing audio: {audio_path}")
            
            # Transcribe with faster-whisper
            segments, info = self.whisper_model.transcribe(
                audio_path,
                language=language,
                beam_size=5,
                vad_filter=True,  # Voice activity detection to filter out silence
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Process segments
            all_text = []
            segment_data = []
            total_confidence = 0.0
            segment_count = 0
            
            for segment in segments:
                # Filter by confidence
                if segment.avg_logprob is not None:
                    # Convert log probability to confidence (0-1)
                    confidence = min(1.0, max(0.0, 1.0 + segment.avg_logprob))
                else:
                    confidence = 0.5  # Default if not available
                
                if confidence >= self.min_confidence:
                    all_text.append(segment.text.strip())
                    segment_data.append({
                        'start': segment.start,
                        'end': segment.end,
                        'text': segment.text.strip(),
                        'confidence': confidence
                    })
                    total_confidence += confidence
                    segment_count += 1
            
            # Calculate overall confidence
            avg_confidence = total_confidence / segment_count if segment_count > 0 else 0.0
            
            lyrics = ' '.join(all_text)
            
            logger.info(f"Transcription complete: {len(lyrics)} characters, confidence: {avg_confidence:.2f}")
            
            return {
                'lyrics': lyrics,
                'segments': segment_data,
                'confidence': avg_confidence,
                'language': info.language,
                'language_probability': info.language_probability
            }
            
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return {
                'lyrics': '',
                'segments': [],
                'confidence': 0.0,
                'error': str(e)
            }
    
    def extract_lyrics(
        self,
        audio_path: str,
        separate_vocals: bool = True,
        language: str = "en",
        cleanup_temp: bool = True
    ) -> Dict[str, Any]:
        """
        Extract lyrics from audio file (full pipeline).
        
        Args:
            audio_path: Path to input audio file
            separate_vocals: Whether to separate vocals first (recommended)
            language: Language code for transcription
            cleanup_temp: Whether to delete temporary files after processing
            
        Returns:
            Dictionary with lyrics and metadata
        """
        temp_dir = None
        vocals_path = audio_path
        
        try:
            # Step 1: Separate vocals if requested
            if separate_vocals and DEMUCS_AVAILABLE and self.demucs is not None:
                temp_dir = tempfile.mkdtemp(prefix="lyrics_extraction_")
                vocals_path = self.separate_vocals(audio_path, temp_dir)
                if vocals_path is None:
                    vocals_path = audio_path
            else:
                logger.info("Skipping vocal separation (using full mix)")
            
            # Step 2: Transcribe
            result = self.transcribe_audio(vocals_path, language)
            
            # Add metadata
            result['audio_path'] = audio_path
            result['vocals_separated'] = separate_vocals and vocals_path != audio_path
            
            return result
            
        except Exception as e:
            logger.error(f"Error extracting lyrics: {e}")
            return {
                'lyrics': '',
                'segments': [],
                'confidence': 0.0,
                'error': str(e),
                'audio_path': audio_path
            }
        
        finally:
            # Cleanup temporary files
            if cleanup_temp and temp_dir and Path(temp_dir).exists():
                try:
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")
    
    def batch_extract(
        self,
        audio_paths: List[str],
        separate_vocals: bool = True,
        language: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        Extract lyrics from multiple audio files.
        
        Args:
            audio_paths: List of paths to audio files
            separate_vocals: Whether to separate vocals
            language: Language code for transcription
            
        Returns:
            List of lyrics extraction results
        """
        results = []
        
        for i, audio_path in enumerate(audio_paths, 1):
            logger.info(f"Processing {i}/{len(audio_paths)}: {audio_path}")
            
            result = self.extract_lyrics(
                audio_path,
                separate_vocals=separate_vocals,
                language=language
            )
            
            results.append(result)
        
        return results
    
    def is_available(self) -> bool:
        """Check if all dependencies are available."""
        return FASTER_WHISPER_AVAILABLE and self.whisper_model is not None
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of the lyrics extractor."""
        return {
            'faster_whisper_available': FASTER_WHISPER_AVAILABLE,
            'whisper_model_loaded': self.whisper_model is not None,
            'whisper_model_size': self.whisper_model_size,
            'demucs_available': DEMUCS_AVAILABLE,
            'demucs_model': self.demucs_model,
            'demucs_initialized': self.demucs is not None,
            'gpu_available': self._cuda_available(),
            'min_confidence': self.min_confidence
        }


def main():
    """Test the lyrics extractor."""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) < 2:
        print("Usage: python lyrics_extractor.py <audio_file>")
        print("\nExample:")
        print("  python lyrics_extractor.py audio_library/song.mp3")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    
    if not Path(audio_file).exists():
        print(f"Error: File not found: {audio_file}")
        sys.exit(1)
    
    print("\n" + "="*70)
    print("Lyrics Extractor Test")
    print("="*70)
    
    # Initialize extractor
    extractor = LyricsExtractor(
        whisper_model_size='base',  # Good balance of speed/accuracy
        use_gpu=True,
        demucs_model='htdemucs'
    )
    
    # Check status
    status = extractor.get_status()
    print("\nExtractor Status:")
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    if not extractor.is_available():
        print("\n❌ Lyrics extractor is not fully available")
        print("Install dependencies:")
        print("  pip install faster-whisper demucs")
        sys.exit(1)
    
    print("\n" + "-"*70)
    print(f"Processing: {audio_file}")
    print("-"*70 + "\n")
    
    # Extract lyrics
    result = extractor.extract_lyrics(audio_file, separate_vocals=True)
    
    # Display results
    print("\n" + "="*70)
    print("Results")
    print("="*70)
    
    if 'error' in result and result['error']:
        print(f"\n❌ Error: {result['error']}")
    else:
        print(f"\n✓ Lyrics extracted successfully!")
        print(f"\nConfidence: {result['confidence']:.2%}")
        print(f"Language: {result.get('language', 'N/A')} (probability: {result.get('language_probability', 0):.2%})")
        print(f"Vocals separated: {result.get('vocals_separated', False)}")
        print(f"Segments: {len(result['segments'])}")
        
        print(f"\n{'='*70}")
        print("LYRICS")
        print(f"{'='*70}\n")
        print(result['lyrics'])
        
        if result['segments']:
            print(f"\n{'='*70}")
            print("TIMESTAMPED SEGMENTS")
            print(f"{'='*70}\n")
            for seg in result['segments'][:5]:  # Show first 5 segments
                print(f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']} (confidence: {seg['confidence']:.2%})")
            if len(result['segments']) > 5:
                print(f"... and {len(result['segments']) - 5} more segments")


if __name__ == '__main__':
    main()
