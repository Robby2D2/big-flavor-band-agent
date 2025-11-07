"""
Quick Test - Index and Search a Small Subset
Tests the RAG system on just a few songs for quick validation.
"""

import asyncio
import logging
from pathlib import Path
from typing import List

from database import DatabaseManager
from rag_system import SongRAGSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("quick-test")


async def quick_test(num_songs: int = 5):
    """
    Quick test of RAG system with a small subset of songs.
    
    Args:
        num_songs: Number of songs to test with
    """
    print("="*70)
    print("  Quick RAG System Test")
    print("="*70)
    print(f"\nTesting with {num_songs} songs...\n")
    
    audio_library = Path("audio_library")
    
    if not audio_library.exists():
        print(f"ERROR: Audio library not found at {audio_library}")
        return
    
    # Initialize database
    db = DatabaseManager()
    await db.connect()
    
    # Initialize RAG (use CLAP if available, but don't require it)
    try:
        rag = SongRAGSystem(db, use_clap=True)
        print("✓ Using CLAP model for embeddings")
    except Exception as e:
        logger.warning(f"CLAP not available, using librosa only: {e}")
        rag = SongRAGSystem(db, use_clap=False)
        print("✓ Using librosa-only embeddings")
    
    # Get a few songs to test
    audio_files = sorted(list(audio_library.glob("*.mp3")))[:num_songs*2]
    
    if len(audio_files) < num_songs:
        print(f"WARNING: Only found {len(audio_files)} audio files")
        num_songs = len(audio_files)
    
    print(f"\nFound {len(audio_files)} audio files in library")
    
    # Try to find songs in database that match these files
    test_songs = []
    
    for audio_file in audio_files[:num_songs*2]:  # Get more than needed in case some aren't in DB
        # Try to find matching song in database
        song_title = audio_file.stem
        
        query = """
            SELECT id, title FROM songs 
            WHERE title ILIKE $1 
            LIMIT 1
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, f"%{song_title}%")
        
        if row:
            test_songs.append({
                'song_id': row['id'],
                'title': row['title'],
                'audio_path': str(audio_file)
            })
            
            if len(test_songs) >= num_songs:
                break
    
    if not test_songs:
        print("\nERROR: Could not find any matching songs in database")
        print("Make sure songs are scraped and loaded into the database first")
        await db.close()
        return
    
    print(f"\nMatched {len(test_songs)} songs with database entries:")
    for i, song in enumerate(test_songs, 1):
        print(f"  {i}. {song['title']}")
    
    # Index these songs
    print("\n" + "-"*70)
    print("Step 1: Indexing audio files...")
    print("-"*70)
    
    to_index = [(song['audio_path'], song['song_id']) for song in test_songs]
    
    results = await rag.index_audio_batch(to_index)
    
    print(f"\n✓ Indexed {results['success']}/{results['total']} songs")
    
    if results['failed'] > 0:
        print(f"✗ Failed to index {results['failed']} songs:")
        for audio_path, song_id in results['failed_files']:
            print(f"  - {Path(audio_path).name}")
    
    if results['success'] == 0:
        print("\nERROR: No songs were indexed successfully")
        await db.close()
        return
    
    # Test similarity search
    print("\n" + "-"*70)
    print("Step 2: Testing similarity search...")
    print("-"*70)
    
    # Use the first song as reference
    reference_song = test_songs[0]
    print(f"\nReference song: {reference_song['title']}")
    
    similar_songs = await rag.search_by_audio_similarity(
        query_audio_path=reference_song['audio_path'],
        limit=5,
        similarity_threshold=0.0  # Get all results for testing
    )
    
    if similar_songs:
        print(f"\n✓ Found {len(similar_songs)} similar songs:")
        for i, result in enumerate(similar_songs, 1):
            print(f"  {i}. {result['title']}")
            print(f"     Similarity: {result['similarity']:.3f}")
            if result.get('tempo_bpm'):
                print(f"     Tempo: {result['tempo_bpm']:.1f} BPM")
    else:
        print("✗ No similar songs found")
    
    # Test tempo search
    print("\n" + "-"*70)
    print("Step 3: Testing tempo search...")
    print("-"*70)
    
    # Get tempo from first song
    embedding = await rag.get_song_embedding(reference_song['song_id'])
    
    if embedding and embedding.get('librosa_features'):
        import json
        # librosa_features is stored as JSON string
        features = json.loads(embedding['librosa_features']) if isinstance(embedding['librosa_features'], str) else embedding['librosa_features']
        if 'tempo' in features:
            tempo = features['tempo']
            print(f"\nSearching for songs around {tempo:.1f} BPM...")
            
            tempo_results = await rag.search_by_tempo_and_audio(
                target_tempo=tempo,
                tempo_tolerance=20.0,
                limit=5
            )
            
            if tempo_results:
                print(f"\n✓ Found {len(tempo_results)} songs:")
                for i, result in enumerate(tempo_results, 1):
                    print(f"  {i}. {result['title']}")
                    if result.get('tempo_bpm'):
                        print(f"     Tempo: {result['tempo_bpm']:.1f} BPM")
                    if result.get('tempo_diff') is not None:
                        print(f"     Difference: ±{result['tempo_diff']:.1f} BPM")
    
    # Get stats
    print("\n" + "-"*70)
    print("Step 4: System statistics")
    print("-"*70)
    
    stats = await rag.get_embedding_stats()
    
    print(f"\nTotal songs in database: {stats['total_songs']}")
    print(f"Songs with audio embeddings: {stats['songs_with_audio_embeddings']}")
    
    coverage = (stats['songs_with_audio_embeddings'] / stats['total_songs'] * 100 
                if stats['total_songs'] > 0 else 0)
    print(f"Coverage: {coverage:.1f}%")
    
    # Summary
    print("\n" + "="*70)
    print("  Test Complete!")
    print("="*70)
    
    if results['success'] == len(test_songs) and similar_songs:
        print("\n✓ All systems operational!")
        print("\nNext steps:")
        print("  1. Index full library: python index_audio_library.py")
        print("  2. Run demos: python demo_rag_search.py")
        print("  3. Try interactive mode: python demo_rag_search.py interactive")
    else:
        print("\n⚠ Some tests had issues. Check logs above.")
    
    await db.close()


async def test_single_file(audio_path: str):
    """
    Test feature extraction on a single file without database.
    
    Args:
        audio_path: Path to audio file
    """
    from audio_embedding_extractor import AudioEmbeddingExtractor
    
    print("="*70)
    print("  Single File Feature Extraction Test")
    print("="*70)
    
    path = Path(audio_path)
    
    if not path.exists():
        print(f"\nERROR: File not found: {audio_path}")
        return
    
    print(f"\nAnalyzing: {path.name}\n")
    
    # Test librosa-only first
    print("-"*70)
    print("Testing librosa features (fast, CPU-only)...")
    print("-"*70)
    
    extractor = AudioEmbeddingExtractor(use_clap=False)
    
    try:
        features = extractor.extract_all_features(audio_path)
        
        print("\n✓ Librosa features extracted successfully")
        
        librosa_features = features['librosa_features']
        print(f"\nAudio Properties:")
        print(f"  Tempo: {librosa_features.get('tempo', 'N/A'):.1f} BPM")
        print(f"  Key: {librosa_features.get('estimated_key', 'N/A')}")
        print(f"  Duration: {librosa_features.get('duration', 'N/A'):.1f} seconds")
        
        print(f"\nSpectral Features:")
        print(f"  Brightness: {librosa_features.get('spectral_centroid_mean', 0):.0f} Hz")
        print(f"  Bandwidth: {librosa_features.get('spectral_bandwidth_mean', 0):.0f} Hz")
        
        print(f"\nEnergy:")
        print(f"  RMS: {librosa_features.get('rms_mean', 0):.4f}")
        
        print(f"\nEmbedding:")
        print(f"  Dimension: {features['embedding_dimension']}")
        print(f"  Type: Librosa-only (37 features + zero-padded)")
        
    except Exception as e:
        print(f"\n✗ Librosa extraction failed: {e}")
        return
    
    # Test with CLAP
    print("\n" + "-"*70)
    print("Testing with CLAP model (slower, requires transformers)...")
    print("-"*70)
    
    try:
        extractor_clap = AudioEmbeddingExtractor(use_clap=True)
        
        features_clap = extractor_clap.extract_all_features(audio_path)
        
        print("\n✓ CLAP embedding extracted successfully")
        
        print(f"\nEmbedding:")
        print(f"  Dimension: {features_clap['embedding_dimension']}")
        print(f"  Type: Combined (37 librosa + 512 CLAP)")
        print(f"  CLAP available: {features_clap['clap_embedding'] is not None}")
        
    except ImportError:
        print("\n⚠ CLAP model not available")
        print("  Install: pip install transformers torch")
    except Exception as e:
        print(f"\n⚠ CLAP extraction failed: {e}")
    
    print("\n" + "="*70)
    print("  Test Complete!")
    print("="*70)


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'file':
            if len(sys.argv) > 2:
                asyncio.run(test_single_file(sys.argv[2]))
            else:
                print("Usage: python quick_test_rag.py file <path_to_audio_file>")
        else:
            # Treat as number of songs
            try:
                num = int(sys.argv[1])
                asyncio.run(quick_test(num))
            except ValueError:
                print("Usage:")
                print("  python quick_test_rag.py [num_songs]  # Default: 5")
                print("  python quick_test_rag.py file <audio_file>  # Test single file")
    else:
        # Default: test with 5 songs
        asyncio.run(quick_test(5))
