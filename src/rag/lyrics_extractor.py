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
        min_confidence: float = 0.5,
        load_demucs: bool = False
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
            load_demucs: Whether to load demucs model at initialization (only if needed for vocal separation)
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
        
        # Demucs model - only load if explicitly requested
        self.demucs = None
        self.device = None
        if load_demucs and DEMUCS_AVAILABLE:
            self._load_demucs()
        
        logger.info(f"LyricsExtractor initialized (Whisper: {self.whisper_model is not None}, Demucs: {self.demucs is not None})")
    
    def _load_demucs(self):
        """Lazy-load demucs model when needed."""
        if self.demucs is not None:
            return  # Already loaded
        
        if not DEMUCS_AVAILABLE:
            logger.warning("Demucs not available")
            return
        
        try:
            logger.info(f"Loading Demucs model '{self.demucs_model}'")
            self.demucs = get_model(self.demucs_model)
            self.device = "cuda" if self.use_gpu and self._cuda_available() else "cpu"
            self.demucs.to(self.device)
            logger.info(f"Demucs model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load Demucs model: {e}")
            self.demucs = None
    
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
        if not DEMUCS_AVAILABLE:
            logger.warning("Demucs not available, skipping vocal separation")
            return audio_path  # Return original file if separation not available
        
        # Lazy-load demucs if needed
        if self.demucs is None:
            logger.info("Demucs not loaded yet, loading now...")
            self._load_demucs()
            if self.demucs is None:
                logger.error("Failed to load Demucs")
                return audio_path
        
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
            
            logger.info(f"Separating vocals from {audio_path} - loaded audio.")

            # Convert to torch tensor
            if audio_data.ndim == 1:
                # Mono - convert to stereo for demucs
                audio_data = np.stack([audio_data, audio_data])
            
            wav = torch.from_numpy(audio_data).float()
            
            logger.info(f"Separating vocals from {audio_path} - completed from numpy.")

            # Convert to the model's expected format
            wav = convert_audio(wav, sr, self.demucs.samplerate, self.demucs.audio_channels)
                        
            logger.info(f"Separating vocals from {audio_path} - converted audio with {self.demucs.samplerate} and {self.demucs.audio_channels}")

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
            
                        
            logger.info(f"Separating vocals from {audio_path} - completed torch.no_grad.")

            sources = sources * ref.std() + ref.mean()
            
            # Extract vocals (index depends on model, usually index 3 for htdemucs)
            # htdemucs order: drums, bass, other, vocals
            vocals = sources[3]  # vocals stem
            
            # Save vocals to file using soundfile to avoid torchcodec issues
            vocals_path = Path(output_dir) / "vocals.wav"
            vocals = vocals.cpu().numpy()
            
            logger.info(f"Separating vocals from {audio_path} - saved vocals to {vocals_path}")
            
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
    
    def apply_voice_frequency_filter(
        self,
        audio_path: str,
        output_path: Optional[str] = None,
        low_cutoff: float = 80.0,
        high_cutoff: float = 8000.0
    ) -> str:
        """
        Apply bandpass filter to isolate typical voice frequency range.
        Human voice typically ranges from 80 Hz to 8000 Hz (with most energy 300-3400 Hz).
        
        Args:
            audio_path: Path to input audio file
            output_path: Path for filtered audio (temp file if None)
            low_cutoff: Low frequency cutoff in Hz (default 80)
            high_cutoff: High frequency cutoff in Hz (default 8000)
            
        Returns:
            Path to filtered audio file
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            from scipy import signal
            
            logger.info(f"Applying voice frequency filter ({low_cutoff}-{high_cutoff} Hz)")
            
            # Load audio
            y, sr = librosa.load(audio_path, sr=None, mono=True)
            
            # Design bandpass filter
            nyquist = sr / 2
            low = low_cutoff / nyquist
            high = high_cutoff / nyquist
            b, a = signal.butter(4, [low, high], btype='band')
            
            # Apply filter
            y_filtered = signal.filtfilt(b, a, y)
            
            # Save filtered audio
            if output_path is None:
                import tempfile
                fd, output_path = tempfile.mkstemp(suffix='.wav')
                import os
                os.close(fd)
            
            sf.write(output_path, y_filtered, sr)
            logger.info(f"Voice frequency filter applied: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error applying frequency filter: {e}")
            return audio_path  # Fallback to original
    
    def transcribe_audio(
        self,
        audio_path: str,
        language: str = "en",
        vad_filter: bool = False,
        vad_min_silence_ms: int = 2000,
        vad_threshold: float = 0.3
    ) -> Dict[str, Any]:
        """
        Transcribe audio to text using faster-whisper.
        
        Args:
            audio_path: Path to audio file (preferably vocals only)
            language: Language code for transcription ('en' for English)
            vad_filter: Enable voice activity detection (filters silence)
            vad_min_silence_ms: Minimum silence duration in ms before filtering (default 2000 = 2 seconds)
            vad_threshold: VAD sensitivity threshold 0.0-1.0 (lower = more sensitive, default 0.3)
            
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
            logger.info(f"Transcribing audio: {audio_path} (VAD: {vad_filter}, threshold: {vad_threshold}, min_silence: {vad_min_silence_ms}ms)")
            
            # Transcribe with faster-whisper
            transcribe_args = {
                'language': language,
                'beam_size': 5,
                'vad_filter': vad_filter
            }
            
            # Add VAD parameters if enabled
            if vad_filter:
                transcribe_args['vad_parameters'] = dict(
                    min_silence_duration_ms=vad_min_silence_ms,
                    threshold=vad_threshold  # Lower threshold = more sensitive to voice (default is 0.5)
                )
            
            segments, info = self.whisper_model.transcribe(
                audio_path,
                **transcribe_args
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
        separate_vocals: bool = False,
        language: str = "en",
        cleanup_temp: bool = True,
        vad_filter: bool = False,
        vad_min_silence_ms: int = 2000,
        vad_threshold: float = 0.3,
        apply_voice_filter: bool = False
    ) -> Dict[str, Any]:
        """
        Extract lyrics from audio file (full pipeline).
        
        Args:
            audio_path: Path to input audio file
            separate_vocals: Whether to separate vocals first (slower but cleaner)
            language: Language code for transcription
            cleanup_temp: Whether to delete temporary files after processing
            vad_filter: Enable voice activity detection (filters silence)
            vad_min_silence_ms: Minimum silence duration in ms before filtering (default 2000 = 2 seconds)
            vad_threshold: VAD sensitivity 0.0-1.0 (lower = more sensitive, default 0.3)
            apply_voice_filter: Apply bandpass filter for voice frequencies (80-8000 Hz)
            
        Returns:
            Dictionary with lyrics and metadata
        """
        temp_dir = None
        vocals_path = audio_path
        temp_files = []
        
        try:
            # Step 1: Separate vocals if requested
            if separate_vocals and DEMUCS_AVAILABLE and self.demucs is not None:
                temp_dir = tempfile.mkdtemp(prefix="lyrics_extraction_")
                vocals_path = self.separate_vocals(audio_path, temp_dir)
                if vocals_path is None:
                    vocals_path = audio_path
            else:
                logger.info("Skipping vocal separation (using full mix)")
            
            # Step 1.5: Apply voice frequency filter if requested
            if apply_voice_filter:
                filtered_path = self.apply_voice_frequency_filter(vocals_path)
                if filtered_path != vocals_path:
                    temp_files.append(filtered_path)
                    vocals_path = filtered_path
            
            # Step 2: Transcribe
            result = self.transcribe_audio(
                vocals_path, 
                language,
                vad_filter=vad_filter,
                vad_min_silence_ms=vad_min_silence_ms,
                vad_threshold=vad_threshold
            )
            
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
            if cleanup_temp:
                if temp_dir and Path(temp_dir).exists():
                    try:
                        shutil.rmtree(temp_dir)
                        logger.debug(f"Cleaned up temporary directory: {temp_dir}")
                    except Exception as e:
                        logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")
                
                # Clean up individual temp files
                for temp_file in temp_files:
                    try:
                        if Path(temp_file).exists():
                            Path(temp_file).unlink()
                            logger.debug(f"Cleaned up temp file: {temp_file}")
                    except Exception as e:
                        logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")
    
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
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='Extract lyrics from audio files')
    parser.add_argument('audio_file', nargs='?', default='tests/wagonwheel.mp3',
                       help='Audio file to process (default: tests/wagonwheel.mp3)')
    parser.add_argument('--vad', action='store_true',
                       help='Enable VAD filtering')
    parser.add_argument('--vad-threshold', type=float, default=0.3,
                       help='VAD threshold 0.0-1.0, lower=more sensitive (default: 0.3)')
    parser.add_argument('--vad-silence', type=int, default=2000,
                       help='Minimum silence duration in ms (default: 2000)')
    parser.add_argument('--voice-filter', action='store_true',
                       help='Apply voice frequency bandpass filter (80-8000 Hz)')
    parser.add_argument('--separate-vocals', action='store_true',
                       help='Use demucs to separate vocals (slow but cleaner)')
    
    args = parser.parse_args()
    audio_file = args.audio_file
    
    if not Path(audio_file).exists():
        print(f"Error: File not found: {audio_file}")
        sys.exit(1)
    
    print("\n" + "="*70)
    print("Lyrics Extractor Test")
    print("="*70)
    print(f"\nSettings:")
    print(f"  Vocal separation: {args.separate_vocals}")
    print(f"  Voice filter: {args.voice_filter}")
    print(f"  VAD enabled: {args.vad}")
    if args.vad:
        print(f"  VAD threshold: {args.vad_threshold}")
        print(f"  VAD min silence: {args.vad_silence}ms")
    
    # Initialize extractor
    extractor = LyricsExtractor(
        whisper_model_size='base',  # Good balance of speed/accuracy
        use_gpu=False,  # CPU mode for compatibility
        demucs_model='htdemucs',
        load_demucs=args.separate_vocals  # Only load demucs if vocal separation requested
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
    
    # Extract lyrics with specified settings
    result = extractor.extract_lyrics(
        audio_file, 
        separate_vocals=args.separate_vocals,
        vad_filter=args.vad,
        vad_threshold=args.vad_threshold,
        vad_min_silence_ms=args.vad_silence,
        apply_voice_filter=args.voice_filter
    )
    
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
