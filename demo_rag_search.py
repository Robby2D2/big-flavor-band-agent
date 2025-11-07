"""
RAG System Demo
Demonstrates audio similarity search and multimodal queries.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any
import json

from database import DatabaseManager
from rag_system import SongRAGSystem
from audio_embedding_extractor import AudioEmbeddingExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("demo")


def print_results(results: List[Dict[str, Any]], title: str = "Results"):
    """Pretty print search results with ALL available information."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)
    
    if not results:
        print("  No results found.")
        return
    
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result.get('title', 'Unknown Title')}")
        print(f"   Song ID: {result.get('song_id', 'N/A')}")
        
        # Similarity scores
        if 'similarity' in result:
            print(f"   Similarity: {result['similarity']:.3f}")
        
        if 'combined_score' in result:
            print(f"   Combined Score: {result['combined_score']:.3f}")
            if 'audio_similarity' in result:
                print(f"   Audio: {result['audio_similarity']:.3f} | Text: {result['text_similarity']:.3f}")
        
        # Basic song info
        if 'genre' in result and result['genre']:
            print(f"   Genre: {result['genre']}")
        
        if 'rating' in result and result['rating'] is not None:
            print(f"   Rating: {'⭐' * result['rating']} ({result['rating']}/5)")
        
        if 'session' in result and result['session']:
            print(f"   Session: {result['session']}")
        
        if 'is_original' in result and result['is_original'] is not None:
            print(f"   Original: {'Yes' if result['is_original'] else 'No (Cover)'}")
        
        if 'track_number' in result and result['track_number']:
            print(f"   Track #: {result['track_number']}")
        
        # Dates
        if 'recorded_on' in result and result['recorded_on']:
            print(f"   Recorded: {result['recorded_on']}")
        
        if 'uploaded_on' in result and result['uploaded_on']:
            print(f"   Uploaded: {result['uploaded_on']}")
        
        # Audio features
        if 'tempo_bpm' in result and result['tempo_bpm']:
            print(f"   Tempo: {result['tempo_bpm']:.1f} BPM")
        
        if 'tempo_diff' in result:
            print(f"   Tempo difference: ±{result['tempo_diff']:.1f} BPM")
        
        if 'audio_path' in result and result['audio_path']:
            print(f"   File: {Path(result['audio_path']).name}")
        
        # Detailed librosa features if available
        if 'librosa_features' in result and result['librosa_features']:
            # librosa_features might be stored as JSON string
            features = json.loads(result['librosa_features']) if isinstance(result['librosa_features'], str) else result['librosa_features']
            
            print(f"\n   Audio Analysis:")
            if 'estimated_key' in features:
                print(f"     Key: {features['estimated_key']}")
            if 'duration' in features:
                print(f"     Duration: {features['duration']:.1f}s")
            if 'spectral_centroid_mean' in features:
                print(f"     Brightness: {features['spectral_centroid_mean']:.0f} Hz")
            if 'rms_mean' in features:
                print(f"     Energy (RMS): {features['rms_mean']:.4f}")
            if 'zcr_mean' in features:
                print(f"     Zero Crossing Rate: {features['zcr_mean']:.4f}")
            if 'spectral_rolloff_mean' in features:
                print(f"     Spectral Rolloff: {features['spectral_rolloff_mean']:.0f} Hz")
            if 'spectral_bandwidth_mean' in features:
                print(f"     Spectral Bandwidth: {features['spectral_bandwidth_mean']:.0f} Hz")
        
        # Show any additional fields that might be present
        excluded_keys = {
            'title', 'song_id', 'similarity', 'combined_score', 'audio_similarity', 
            'text_similarity', 'genre', 'rating', 'session', 'is_original', 
            'track_number', 'recorded_on', 'uploaded_on', 'tempo_bpm', 'tempo_diff', 
            'audio_path', 'librosa_features'
        }
        
        extra_fields = {k: v for k, v in result.items() if k not in excluded_keys and v is not None}
        if extra_fields:
            print(f"\n   Additional Info:")
            for key, value in extra_fields.items():
                if isinstance(value, (int, float, str, bool)):
                    print(f"     {key}: {value}")


async def demo_audio_similarity_search(rag: SongRAGSystem, audio_library: Path):
    """Demo: Find songs similar to a reference song."""
    print("\n" + "="*70)
    print("  DEMO 1: Audio Similarity Search")
    print("="*70)
    print("\nFinding songs that SOUND similar...")
    
    # Use a popular song as reference
    reference_songs = [
        "Helpless.mp3",
        "Fake Plastic Trees.mp3",
        "Going to California.mp3",
        "This Year.mp3"
    ]
    
    reference = None
    for song in reference_songs:
        ref_path = audio_library / song
        if ref_path.exists():
            reference = ref_path
            break
    
    if not reference:
        print("Could not find reference song in library")
        return
    
    print(f"\nReference song: {reference.name}")
    
    results = await rag.search_by_audio_similarity(
        query_audio_path=str(reference),
        limit=8,
        similarity_threshold=0.3
    )
    
    print_results(results, f"Songs similar to '{reference.stem}'")


async def demo_tempo_search(rag: SongRAGSystem):
    """Demo: Find songs with specific tempo."""
    print("\n" + "="*70)
    print("  DEMO 2: Tempo-Based Search")
    print("="*70)
    
    target_tempo = 120.0
    tolerance = 15.0
    
    print(f"\nFinding songs around {target_tempo} BPM (±{tolerance})")
    
    results = await rag.search_by_tempo_and_audio(
        target_tempo=target_tempo,
        tempo_tolerance=tolerance,
        limit=10
    )
    
    print_results(results, f"Songs near {target_tempo} BPM")


async def demo_tempo_with_audio_similarity(rag: SongRAGSystem, audio_library: Path):
    """Demo: Find songs with similar tempo AND sound."""
    print("\n" + "="*70)
    print("  DEMO 3: Tempo + Audio Similarity Search")
    print("="*70)
    
    # Find a reference song with known tempo
    reference_songs = [
        "Helpless.mp3",
        "This Year.mp3"
    ]
    
    reference = None
    for song in reference_songs:
        ref_path = audio_library / song
        if ref_path.exists():
            reference = ref_path
            break
    
    if not reference:
        print("Could not find reference song")
        return
    
    print(f"\nReference song: {reference.name}")
    print("Finding songs with similar tempo that also sound similar...")
    
    # First get the reference song's tempo
    extractor = AudioEmbeddingExtractor(use_clap=False)  # Just for tempo
    features = extractor.extract_librosa_features(str(reference))
    ref_tempo = features.get('tempo', 120)
    
    print(f"Reference tempo: {ref_tempo:.1f} BPM")
    
    results = await rag.search_by_tempo_and_audio(
        target_tempo=ref_tempo,
        reference_audio_path=str(reference),
        tempo_tolerance=10.0,
        limit=10
    )
    
    print_results(results, f"Songs like '{reference.stem}' (tempo + audio)")


async def demo_feature_analysis(rag: SongRAGSystem, audio_library: Path):
    """Demo: Analyze and compare audio features."""
    print("\n" + "="*70)
    print("  DEMO 4: Audio Feature Analysis")
    print("="*70)
    
    # Pick a few songs to analyze
    songs_to_analyze = [
        "Helpless.mp3",
        "Going to California.mp3",
        "Fake Plastic Trees.mp3"
    ]
    
    extractor = AudioEmbeddingExtractor(use_clap=False)
    
    for song_name in songs_to_analyze:
        song_path = audio_library / song_name
        if not song_path.exists():
            continue
        
        print(f"\n--- {song_name} ---")
        
        features = extractor.extract_librosa_features(str(song_path))
        
        print(f"Tempo: {features.get('tempo', 'N/A'):.1f} BPM")
        print(f"Key: {features.get('estimated_key', 'N/A')}")
        print(f"Duration: {features.get('duration', 0):.1f}s")
        print(f"Spectral Centroid (brightness): {features.get('spectral_centroid_mean', 0):.0f} Hz")
        print(f"RMS Energy: {features.get('rms_mean', 0):.4f}")
        print(f"Zero Crossing Rate: {features.get('zcr_mean', 0):.4f}")
        
        # Show top 3 dominant pitch classes
        if 'chroma_mean' in features:
            chroma = features['chroma_mean']
            keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            chroma_with_keys = list(zip(keys, chroma))
            chroma_with_keys.sort(key=lambda x: x[1], reverse=True)
            print(f"Dominant pitches: {', '.join([k for k, _ in chroma_with_keys[:3]])}")


async def demo_statistics(rag: SongRAGSystem):
    """Demo: Show RAG system statistics."""
    print("\n" + "="*70)
    print("  RAG System Statistics")
    print("="*70)
    
    stats = await rag.get_embedding_stats()
    
    print(f"\nTotal songs in database: {stats['total_songs']}")
    print(f"Songs with audio embeddings: {stats['songs_with_audio_embeddings']}")
    print(f"Songs with text embeddings: {stats['songs_with_text_embeddings']}")
    
    coverage = (stats['songs_with_audio_embeddings'] / stats['total_songs'] * 100 
                if stats['total_songs'] > 0 else 0)
    print(f"Audio embedding coverage: {coverage:.1f}%")
    
    # Find songs without embeddings
    missing = await rag.find_songs_without_embeddings()
    print(f"\nSongs needing indexing: {len(missing)}")
    
    if missing and len(missing) <= 10:
        print("\nMissing embeddings for:")
        for song in missing:
            print(f"  - {song['title']}")


async def demo_batch_similarity(rag: SongRAGSystem, audio_library: Path):
    """Demo: Compare multiple songs to find clusters."""
    print("\n" + "="*70)
    print("  DEMO 5: Song Clustering by Audio Similarity")
    print("="*70)
    
    # Pick a few seed songs
    seed_songs = [
        "Helpless.mp3",
        "This Year.mp3",
        "Going to California.mp3"
    ]
    
    print("\nFinding songs similar to multiple references...")
    
    all_similar = {}
    
    for seed in seed_songs:
        seed_path = audio_library / seed
        if not seed_path.exists():
            continue
        
        results = await rag.search_by_audio_similarity(
            query_audio_path=str(seed_path),
            limit=5,
            similarity_threshold=0.4
        )
        
        all_similar[seed] = results
    
    # Print results
    for seed, results in all_similar.items():
        print(f"\n--- Similar to: {seed} ---")
        for i, result in enumerate(results[:3], 1):
            print(f"{i}. {result['title']} ({result['similarity']:.3f})")


async def interactive_demo():
    """Interactive demo where user can search for songs."""
    print("\n" + "="*70)
    print("  Interactive Audio Search Demo")
    print("="*70)
    
    audio_library = Path("audio_library")
    
    # Initialize
    db = DatabaseManager()
    await db.connect()
    
    rag = SongRAGSystem(db, use_clap=True)
    
    print("\nAvailable audio files:")
    audio_files = sorted(list(audio_library.glob("*.mp3")))[:20]
    
    for i, audio_file in enumerate(audio_files, 1):
        print(f"{i:2}. {audio_file.name}")
    
    if len(list(audio_library.glob("*.mp3"))) > 20:
        print(f"    ... and {len(list(audio_library.glob('*.mp3'))) - 20} more")
    
    print("\nEnter the number of a song to find similar tracks (or 'q' to quit):")
    
    while True:
        try:
            choice = input("\n> ").strip()
            
            if choice.lower() == 'q':
                break
            
            idx = int(choice) - 1
            if 0 <= idx < len(audio_files):
                selected = audio_files[idx]
                print(f"\nSearching for songs similar to: {selected.name}")
                
                results = await rag.search_by_audio_similarity(
                    query_audio_path=str(selected),
                    limit=8,
                    similarity_threshold=0.3
                )
                
                print_results(results, f"Similar to '{selected.stem}'")
            else:
                print("Invalid selection")
                
        except ValueError:
            print("Please enter a number or 'q' to quit")
        except KeyboardInterrupt:
            break
    
    await db.close()
    print("\nGoodbye!")


async def main():
    """Run all demos."""
    audio_library = Path("audio_library")
    
    if not audio_library.exists():
        print(f"Error: Audio library not found at {audio_library}")
        print("Please ensure audio files are in the 'audio_library' directory")
        return
    
    # Initialize
    db = DatabaseManager()
    await db.connect()
    
    rag = SongRAGSystem(db, use_clap=True)
    
    # Check if we have embeddings
    stats = await rag.get_embedding_stats()
    
    if stats['songs_with_audio_embeddings'] == 0:
        print("\n" + "!"*70)
        print("  WARNING: No audio embeddings found!")
        print("  Please run: python index_audio_library.py")
        print("!"*70)
        await db.close()
        return
    
    # Run demos
    await demo_statistics(rag)
    await demo_audio_similarity_search(rag, audio_library)
    await demo_tempo_search(rag)
    await demo_tempo_with_audio_similarity(rag, audio_library)
    await demo_feature_analysis(rag, audio_library)
    await demo_batch_similarity(rag, audio_library)
    
    print("\n" + "="*70)
    print("  Demo Complete!")
    print("="*70)
    print("\nFor interactive mode, run:")
    print("  python demo_rag_search.py interactive")
    
    await db.close()


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'interactive':
        asyncio.run(interactive_demo())
    else:
        asyncio.run(main())
