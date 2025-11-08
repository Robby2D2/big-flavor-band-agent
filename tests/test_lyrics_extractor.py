"""
Quick test of lyrics extraction capabilities
Tests the lyrics extractor on a sample audio file
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.rag.lyrics_extractor import LyricsExtractor


def main():
    print("\n" + "="*70)
    print("Lyrics Extractor - Quick Test")
    print("="*70)
    
    # Check if dependencies are available
    extractor = LyricsExtractor(
        whisper_model_size='base',
        use_gpu=True,
        demucs_model='htdemucs',
        min_confidence=0.5
    )
    
    status = extractor.get_status()
    
    print("\nDependency Status:")
    print(f"  faster-whisper available: {status['faster_whisper_available']}")
    print(f"  Whisper model loaded: {status['whisper_model_loaded']}")
    print(f"  Demucs available: {status['demucs_available']}")
    print(f"  Demucs initialized: {status['demucs_initialized']}")
    print(f"  GPU available: {status['gpu_available']}")
    
    if not extractor.is_available():
        print("\n" + "="*70)
        print("❌ Lyrics extractor is NOT ready")
        print("="*70)
        print("\nMissing dependencies. Please install:")
        print("\n  pip install faster-whisper demucs")
        print("\nOr run the full setup:")
        print("\n  pip install -r setup/requirements.txt")
        return False
    
    print("\n" + "="*70)
    print("✓ Lyrics extractor is ready!")
    print("="*70)
    
    print("\nTo test on an audio file:")
    print("  python src/rag/lyrics_extractor.py audio_library/song.mp3")
    
    print("\nTo index all songs:")
    print("  python src/rag/index_lyrics.py --max-songs 5")
    
    print("\nTo check status:")
    print("  python src/rag/index_lyrics.py --status")
    
    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
