"""
Test Audio Analysis Integration
Quick test to verify audio analysis cache functionality.
"""

import asyncio
from audio_analysis_cache import AudioAnalysisCache


async def test_cache_basic():
    """Test basic cache functionality."""
    print("="*60)
    print("Testing Audio Analysis Cache")
    print("="*60)
    
    cache = AudioAnalysisCache()
    
    # Test 1: Check cache stats
    print("\n1. Checking cache statistics...")
    stats = cache.get_cache_stats()
    print(f"   Total entries: {stats['total_entries']}")
    print(f"   Cache file: {stats['cache_file']}")
    print(f"   Cache size: {stats['cache_size_bytes']} bytes")
    
    # Test 2: Test cache key generation
    print("\n2. Testing cache key generation...")
    test_url = "https://bigflavorband.com/audio/test.mp3"
    cache_key = cache._get_cache_key(test_url)
    print(f"   URL: {test_url}")
    print(f"   Cache key: {cache_key}")
    
    # Test 3: Test getting non-existent cached analysis
    print("\n3. Testing cache miss...")
    result = cache.get_cached_analysis(test_url)
    print(f"   Result: {result}")
    assert result is None, "Expected None for non-existent cache entry"
    print("   ✓ Correctly returned None")
    
    # Test 4: Test saving and retrieving analysis
    print("\n4. Testing cache save and retrieve...")
    test_analysis = {
        'bpm': 128.5,
        'key': 'C',
        'genre_hints': ['Rock', 'Alternative'],
        'energy': 'high',
        'duration_seconds': 245.3
    }
    cache.save_analysis(test_url, test_analysis)
    print("   ✓ Saved test analysis")
    
    retrieved = cache.get_cached_analysis(test_url)
    print(f"   Retrieved: {retrieved}")
    assert retrieved is not None, "Expected cached analysis"
    assert retrieved['bpm'] == 128.5, "BPM mismatch"
    print("   ✓ Successfully retrieved cached analysis")
    
    # Test 5: Check updated stats
    print("\n5. Checking updated cache statistics...")
    stats = cache.get_cache_stats()
    print(f"   Total entries: {stats['total_entries']}")
    print(f"   ✓ Cache has {stats['total_entries']} entries")
    
    print("\n" + "="*60)
    print("All tests passed! ✓")
    print("="*60)
    
    # Optional: Clear test data
    print("\nCleaning up test data...")
    cache.clear_cache()
    print("✓ Cache cleared")


async def test_librosa_availability():
    """Test if librosa is available and working."""
    print("\n" + "="*60)
    print("Testing Librosa Availability")
    print("="*60)
    
    try:
        import librosa
        import numpy
        print("\n✓ Librosa is installed and available")
        print(f"  Librosa version: {librosa.__version__}")
        print(f"  NumPy version: {numpy.__version__}")
        
        # Test basic functionality
        print("\nTesting basic librosa functionality...")
        # Create a simple sine wave
        import numpy as np
        sr = 22050
        duration = 1.0
        frequency = 440.0  # A4 note
        t = np.linspace(0, duration, int(sr * duration))
        y = np.sin(2 * np.pi * frequency * t)
        
        # Try to analyze it
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        print(f"  ✓ Beat tracking works (detected tempo: {tempo:.1f} BPM)")
        
    except ImportError as e:
        print(f"\n✗ Librosa not available: {e}")
        print("\nTo install librosa, run:")
        print("  pip install librosa soundfile numpy")
        return False
    except Exception as e:
        print(f"\n✗ Error testing librosa: {e}")
        return False
    
    print("\n" + "="*60)
    print("Librosa is ready for audio analysis! ✓")
    print("="*60)
    return True


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Audio Analysis Integration Test")
    print("="*60)
    
    # Test 1: Basic cache functionality
    await test_cache_basic()
    
    # Test 2: Librosa availability
    await test_librosa_availability()
    
    print("\n" + "="*60)
    print("Test Suite Complete")
    print("="*60)
    print("\nNext steps:")
    print("1. If librosa is not installed, run: pip install librosa soundfile numpy")
    print("2. Pre-analyze audio files: python pre_analyze_audio.py --max-files 5")
    print("3. Start the MCP server: python mcp_server.py")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
