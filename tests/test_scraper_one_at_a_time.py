"""
Test scraping with complete inline processing - one song at a time
This test will:
1. Scrape one song at a time starting from "Going to California - raga"
2. For each song immediately:
   - Download MP3
   - Insert into database
   - Perform audio analysis
   - Create audio embeddings
   - Extract and store lyrics
3. Verify database storage after each song
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.web_scraper import BigFlavorScraper
from database.database import DatabaseManager
from scraper.scraped_data_manager import ScrapedDataManager
from src.rag.big_flavor_rag import SongRAGSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def process_song(song_data: dict, db_manager: DatabaseManager, data_manager: ScrapedDataManager, rag_system: SongRAGSystem, index: int, total: int, lyrics_extractor=None):
    """
    Process a single song completely: DB insert, audio analysis, embeddings, lyrics
    
    Args:
        song_data: Song data from scraper
        db_manager: Database manager
        data_manager: Scraped data manager
        rag_system: RAG system for embeddings and lyrics
        index: Current song number (1-based)
        total: Total songs to process
        lyrics_extractor: Optional pre-initialized LyricsExtractor (for reuse)
    
    Returns:
        dict: Processing results
    """
    results = {
        'song_id': song_data.get('id'),
        'title': song_data.get('title'),
        'inserted': False,
        'audio_analyzed': False,
        'audio_indexed': False,
        'lyrics_extracted': False,
        'errors': []
    }
    
    print(f"\n{'='*70}")
    print(f"SONG {index}/{total}: {song_data.get('title')}")
    print(f"{'='*70}")
    print(f"ID: {song_data.get('id')}")
    print(f"Audio file: {song_data.get('local_audio_path', 'N/A')}")
    
    try:
        # 1. Insert into database
        print("\n[1/4] Inserting into database...")
        if 'id' not in song_data or not song_data['id']:
            error = "Song has no ID"
            print(f"  ✗ {error}")
            results['errors'].append(error)
            return results
        
        song_id = await data_manager.insert_song_with_details(song_data)
        results['inserted'] = True
        print(f"  ✓ Inserted song ID {song_id}")
        
        # Convert to int if needed
        if isinstance(song_id, str):
            song_id = int(song_id)
        
        # 2. Audio analysis
        if song_data.get('local_audio_path'):
            print("\n[2/4] Analyzing audio features...")
            try:
                features = rag_system.embedding_extractor.extract_librosa_features(song_data['local_audio_path'])
                
                if features:
                    # Update songs table
                    await db_manager.pool.execute("""
                        UPDATE songs SET
                            tempo_bpm = $1,
                            key = $2,
                            duration_seconds = $3
                        WHERE id = $4
                    """, 
                        features.get('tempo', 0.0),
                        features.get('estimated_key', 'Unknown'),
                        int(features.get('duration', 0)),
                        song_id
                    )
                    
                    # Save to audio_analysis table
                    await db_manager.pool.execute("""
                        INSERT INTO audio_analysis (
                            song_id, audio_url, bpm, key, energy, 
                            danceability, valence, acousticness, 
                            instrumentalness, liveness, speechiness
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        ON CONFLICT (audio_url) DO UPDATE SET
                            bpm = EXCLUDED.bpm,
                            key = EXCLUDED.key,
                            energy = EXCLUDED.energy,
                            danceability = EXCLUDED.danceability,
                            valence = EXCLUDED.valence,
                            acousticness = EXCLUDED.acousticness,
                            instrumentalness = EXCLUDED.instrumentalness,
                            liveness = EXCLUDED.liveness,
                            speechiness = EXCLUDED.speechiness,
                            analyzed_at = CURRENT_TIMESTAMP
                    """, 
                        song_id,
                        song_data.get('audio_url', ''),
                        features.get('tempo', 0.0),
                        features.get('estimated_key', 'Unknown'),
                        features.get('rms_mean', 0.0),
                        features.get('spectral_bandwidth_mean', 0.0) / 5000.0,
                        features.get('spectral_centroid_mean', 0.0) / 5000.0,
                        1.0 - features.get('zcr_mean', 0.0),
                        1.0 - features.get('rms_mean', 0.0) * 10,
                        features.get('spectral_rolloff_mean', 0.0) / 10000.0,
                        features.get('zcr_mean', 0.0) * 2
                    )
                    
                    results['audio_analyzed'] = True
                    print(f"  ✓ BPM: {features.get('tempo', 0):.1f}, Key: {features.get('estimated_key', 'Unknown')}, Duration: {features.get('duration', 0):.1f}s")
                    
                    # 3. Create audio embeddings
                    print("\n[3/4] Creating audio embeddings...")
                    if await rag_system.index_audio_file(song_data['local_audio_path'], song_id):
                        results['audio_indexed'] = True
                        print(f"  ✓ Audio embeddings created")
                    else:
                        error = "Failed to create audio embeddings"
                        print(f"  ✗ {error}")
                        results['errors'].append(error)
                else:
                    error = "Failed to extract audio features"
                    print(f"  ✗ {error}")
                    results['errors'].append(error)
                    
            except Exception as e:
                error = f"Audio analysis error: {e}"
                logger.error(error)
                print(f"  ✗ {error}")
                results['errors'].append(error)
            
            # 4. Extract lyrics
            print("\n[4/4] Extracting lyrics (Whisper large-v3, no VAD, no demucs)...")
            try:
                result = await rag_system.extract_and_index_lyrics(
                    audio_path=song_data['local_audio_path'],
                    song_id=song_id,
                    separate_vocals=False,
                    vad_filter=False,
                    whisper_model_size='large-v3',
                    lyrics_extractor=lyrics_extractor
                )
                
                if result.get('success') and result.get('lyrics'):
                    results['lyrics_extracted'] = True
                    lyrics_len = len(result['lyrics'])
                    confidence = result.get('confidence', 0)
                    print(f"  ✓ Extracted {lyrics_len} characters (confidence: {confidence:.1%})")
                    
                    # Verify it was stored
                    stored = await db_manager.pool.fetchval(
                        "SELECT COUNT(*) FROM text_embeddings WHERE song_id = $1 AND content_type = 'lyrics'",
                        song_id
                    )
                    if stored:
                        print(f"  ✓ Lyrics stored in database")
                    else:
                        print(f"  ⚠ Lyrics not found in database")
                else:
                    error = result.get('error', 'No lyrics extracted')
                    print(f"  ✗ {error}")
                    results['errors'].append(error)
                    
            except Exception as e:
                error = f"Lyrics extraction error: {e}"
                logger.error(error)
                print(f"  ✗ {error}")
                results['errors'].append(error)
        else:
            print("\n  ⚠ No audio file available, skipping analysis and lyrics")
        
        # Summary for this song
        print(f"\n{'─'*70}")
        print(f"SUMMARY FOR: {song_data.get('title')[:50]}")
        print(f"  Database: {'✓' if results['inserted'] else '✗'}")
        print(f"  Audio Analysis: {'✓' if results['audio_analyzed'] else '✗'}")
        print(f"  Audio Embeddings: {'✓' if results['audio_indexed'] else '✗'}")
        print(f"  Lyrics: {'✓' if results['lyrics_extracted'] else '✗'}")
        if results['errors']:
            print(f"  Errors: {len(results['errors'])}")
        print(f"{'─'*70}")
        
    except Exception as e:
        error = f"Unexpected error: {e}"
        logger.error(error, exc_info=True)
        results['errors'].append(error)
        print(f"\n✗ ERROR: {error}")
    
    return results


async def main():
    """Main test function"""
    
    print("\n" + "="*70)
    print("Song Scraper Test - Complete Inline Processing")
    print("="*70)
    print()
    print("This test will:")
    print("  1. Scrape all songs starting from 'Going to California - raga'")
    print("  2. Process each scraped song immediately and completely:")
    print("     - Insert into database with all metadata")
    print("     - Analyze audio features (BPM, key, duration, etc.)")
    print("     - Create audio embeddings")
    print("     - Extract and store lyrics (Whisper large-v3)")
    print()
    print("Configuration:")
    print("  - Starting from: 'Going to California - raga'")
    print("  - Number of songs: 5")
    print("  - Lyrics: no VAD, no demucs, large-v3 model")
    print()
    print("Note: Due to the Vaadin virtualized grid, songs are collected")
    print("      first, then each is processed completely before the next.")
    print()
    
    response = input("Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Cancelled.")
        return
    
    scraper = None
    db_manager = None
    
    try:
        # Initialize database
        print("\n[1/3] Connecting to database...")
        db_manager = DatabaseManager()
        await db_manager.connect()
        data_manager = ScrapedDataManager(db_manager)
        print("✓ Database connected")
        
        # Initialize RAG system
        print("\n[2/3] Initializing RAG system...")
        rag_system = SongRAGSystem(db_manager, use_clap=True)
        print("✓ RAG system initialized")
        
        # Initialize scraper
        print("\n[3/3] Initializing web scraper...")
        scraper = BigFlavorScraper(
            headless=False,
            download_audio=True
        )
        scraper.navigate_to_songs()
        print("✓ Scraper initialized")
        
        # Scrape all songs first (required for Vaadin grid reliability)
        print("\n" + "="*70)
        print("COLLECTING SONGS")
        print("="*70)
        
        start_from_song = "Going to California - raga"
        num_songs = 5
        
        print(f"\nScraping {num_songs} songs starting from '{start_from_song}'...")
        print("(Vaadin grid requires collecting songs before processing)")
        print()
        
        # Use the reliable scraper method
        songs = scraper.get_all_songs_with_details(
            max_scrolls=20,
            limit=num_songs,
            start_from_song=start_from_song
        )
        
        if not songs:
            print("\n✗ No songs were scraped")
            return
        
        print(f"✓ Collected {len(songs)} songs\n")
        
        # Initialize LyricsExtractor once to reuse across all songs
        # This avoids loading Whisper large-v3 into GPU memory multiple times
        print("Initializing Whisper large-v3 model (one-time setup)...")
        from src.rag.lyrics_extractor import LyricsExtractor
        lyrics_extractor = LyricsExtractor(
            whisper_model_size='large-v3',
            use_gpu=True,
            min_confidence=0.5,
            load_demucs=False  # Not using vocal separation
        )
        print("✓ Whisper model loaded\n")
        
        # Now process each song completely before moving to next
        print("=" * 70)
        print("PROCESSING SONGS ONE AT A TIME")
        print("="*70)
        print()
        
        all_results = []
        for i, song_data in enumerate(songs, 1):
            result = await process_song(
                song_data, 
                db_manager, 
                data_manager, 
                rag_system, 
                i, 
                len(songs),
                lyrics_extractor=lyrics_extractor
            )
            all_results.append(result)
        
        # Final summary
        print("\n" + "="*70)
        print("FINAL SUMMARY")
        print("="*70)
        
        total_inserted = sum(1 for r in all_results if r['inserted'])
        total_analyzed = sum(1 for r in all_results if r['audio_analyzed'])
        total_indexed = sum(1 for r in all_results if r['audio_indexed'])
        total_lyrics = sum(1 for r in all_results if r['lyrics_extracted'])
        total_errors = sum(len(r['errors']) for r in all_results)
        
        print(f"\nProcessed {len(all_results)} songs:")
        print(f"  Database inserts:     {total_inserted}/{len(all_results)}")
        print(f"  Audio analysis:       {total_analyzed}/{len(all_results)}")
        print(f"  Audio embeddings:     {total_indexed}/{len(all_results)}")
        print(f"  Lyrics extracted:     {total_lyrics}/{len(all_results)}")
        print(f"  Total errors:         {total_errors}")
        
        if total_errors == 0:
            print("\n✓ All songs processed successfully!")
        else:
            print(f"\n⚠ {total_errors} errors occurred during processing")
        
        print()
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        
    finally:
        # Cleanup
        if scraper:
            print("\nClosing browser...")
            scraper.stop()
        
        if db_manager:
            print("Closing database connection...")
            await db_manager.close()
        
        print("\nTest complete!")


if __name__ == "__main__":
    asyncio.run(main())
