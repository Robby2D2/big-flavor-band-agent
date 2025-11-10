"""
Process ALL songs from bigflavorband.com with complete pipeline:
1. Scrape all songs with details
2. For each song (one at a time):
   - Insert into database
   - Analyze audio features
   - Create audio embeddings
   - Extract lyrics (Whisper large-v3)
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scraper.web_scraper import BigFlavorScraper
from database.database import DatabaseManager
from scraper.scraped_data_manager import ScrapedDataManager
from src.rag.big_flavor_rag import SongRAGSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def process_song(song_data: dict, db_manager: DatabaseManager, data_manager: ScrapedDataManager, 
                       rag_system: SongRAGSystem, index: int, total: int, lyrics_extractor=None):
    """
    Process a single song, only filling in missing data.
    Checks database for existing audio analysis, embeddings, and lyrics.
    """
    results = {
        'inserted': False,
        'audio_analyzed': False,
        'audio_indexed': False,
        'lyrics_extracted': False,
        'skipped': {
            'audio_analysis': False,
            'audio_embeddings': False,
            'lyrics': False
        },
        'errors': []
    }
    
    try:
        title = song_data.get('title', 'Unknown')
        song_id = song_data.get('id')
        
        print(f"\n{'='*70}")
        print(f"SONG {index}/{total}: {title}")
        print(f"{'='*70}")
        print(f"ID: {song_id}")
        
        if not song_id:
            print("  ✗ Missing song ID")
            results['errors'].append("Missing song ID")
            return results
        
        # Check what already exists in database
        existing_data = await db_manager.pool.fetchrow("""
            SELECT 
                s.id,
                s.tempo_bpm,
                s.key,
                s.duration_seconds,
                EXISTS(SELECT 1 FROM audio_embeddings WHERE song_id = s.id) as has_audio_embedding,
                EXISTS(SELECT 1 FROM text_embeddings WHERE song_id = s.id AND content_type = 'lyrics') as has_lyrics
            FROM songs s
            WHERE s.id = $1
        """, song_id)
        
        song_exists = existing_data is not None
        has_audio_analysis = existing_data and existing_data['tempo_bpm'] is not None if existing_data else False
        has_audio_embedding = existing_data['has_audio_embedding'] if existing_data else False
        has_lyrics = existing_data['has_lyrics'] if existing_data else False
        
        if song_exists:
            print(f"  → Song exists in database")
            print(f"    Audio analysis: {'✓' if has_audio_analysis else '✗'}")
            print(f"    Audio embedding: {'✓' if has_audio_embedding else '✗'}")
            print(f"    Lyrics: {'✓' if has_lyrics else '✗'}")
        
        # 1. Insert/Update database
        print("\n[1/4] Database insert/update...")
        try:
            inserted_id = await data_manager.insert_song_with_details(song_data)
            results['inserted'] = True
            if song_exists:
                print(f"  ✓ Updated song ID {inserted_id}")
            else:
                print(f"  ✓ Inserted song ID {inserted_id}")
        except Exception as e:
            error = f"Database insert error: {e}"
            logger.error(error)
            print(f"  ✗ {error}")
            results['errors'].append(error)
            return results
        
        # Check if audio file exists
        audio_path = song_data.get('local_audio_path')
        if audio_path and Path(audio_path).exists():
            print(f"Audio file: {audio_path}")
            
            # 2. Analyze audio features (only if missing)
            if has_audio_analysis:
                print("\n[2/4] Audio analysis already exists - skipping")
                results['audio_analyzed'] = True
                results['skipped']['audio_analysis'] = True
            else:
                print("\n[2/4] Analyzing audio features...")
                try:
                    analysis = rag_system.embedding_extractor.analyze_audio(audio_path)
                    results['audio_analyzed'] = True
                    print(f"  ✓ BPM: {analysis.get('tempo_bpm', 'N/A')}, Key: {analysis.get('key', 'N/A')}, Duration: {analysis.get('duration_seconds', 'N/A')}s")
                except Exception as e:
                    error = f"Audio analysis error: {e}"
                    logger.error(error)
                    print(f"  ✗ {error}")
                    results['errors'].append(error)
            
            # 3. Create audio embeddings (only if missing)
            if has_audio_embedding:
                print("\n[3/4] Audio embeddings already exist - skipping")
                results['audio_indexed'] = True
                results['skipped']['audio_embeddings'] = True
            else:
                print("\n[3/4] Creating audio embeddings...")
                try:
                    success = await rag_system.index_audio_file(audio_path, song_id)
                    if success:
                        results['audio_indexed'] = True
                        print(f"  ✓ Audio embeddings created")
                    else:
                        error = "Failed to create audio embeddings"
                        print(f"  ✗ {error}")
                        results['errors'].append(error)
                except Exception as e:
                    error = f"Audio embedding error: {e}"
                    logger.error(error)
                    print(f"  ✗ {error}")
                    results['errors'].append(error)
            
            # 4. Extract lyrics (only if missing)
            if has_lyrics:
                print("\n[4/4] Lyrics already extracted - skipping")
                results['lyrics_extracted'] = True
                results['skipped']['lyrics'] = True
            else:
                print("\n[4/4] Extracting lyrics (Whisper large-v3)...")
                try:
                    result = await rag_system.extract_and_index_lyrics(
                        audio_path=audio_path,
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
        print(f"SUMMARY: {title[:50]}")
        print(f"  Database: {'✓' if results['inserted'] else '✗'}")
        print(f"  Audio Analysis: {'✓ (existing)' if results['skipped']['audio_analysis'] else ('✓' if results['audio_analyzed'] else '✗')}")
        print(f"  Audio Embeddings: {'✓ (existing)' if results['skipped']['audio_embeddings'] else ('✓' if results['audio_indexed'] else '✗')}")
        print(f"  Lyrics: {'✓ (existing)' if results['skipped']['lyrics'] else ('✓' if results['lyrics_extracted'] else '✗')}")
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
    """Main processing function"""
    
    print("\n" + "="*70)
    print("Process ALL Songs - Complete Pipeline")
    print("="*70)
    print("\nThis will:")
    print("  1. Scrape ALL songs from bigflavorband.com")
    print("  2. Process each song completely before moving to next:")
    print("     - Insert into database with all metadata")
    print("     - Analyze audio features (BPM, key, duration, etc.)")
    print("     - Create audio embeddings")
    print("     - Extract and store lyrics (Whisper large-v3)")
    print()
    print("Note: This may take a long time depending on number of songs.")
    print("      Whisper large-v3 takes ~1 minute per song.")
    print()
    
    # response = input("Continue? (yes/no): ").strip().lower()
    # if response not in ['yes', 'y']:
    #     print("Cancelled.")
    #     return
    
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
            headless=True,
            download_audio=True
        )
        scraper.navigate_to_songs()
        print("✓ Scraper initialized")
        
        # Scrape all songs
        print("\n" + "="*70)
        print("COLLECTING ALL SONGS")
        print("="*70)
        print("\nScraping all songs from website...")
        print("(This collects all songs first due to Vaadin grid virtualization)")
        print()
        
        songs = scraper.get_all_songs_with_details(
            max_scrolls=1000,  # High limit to get all songs
            limit=None  # No limit
        )
        
        if not songs:
            print("\n✗ No songs were scraped")
            return
        
        print(f"✓ Collected {len(songs)} songs\n")
        
        # Initialize LyricsExtractor once for reuse
        print("Initializing Whisper large-v3 model (one-time setup)...")
        from src.rag.lyrics_extractor import LyricsExtractor
        lyrics_extractor = LyricsExtractor(
            whisper_model_size='large-v3',
            use_gpu=True,
            min_confidence=0.5,
            load_demucs=False
        )
        print("✓ Whisper model loaded\n")
        
        # Process each song completely
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
        logger.error(f"Process failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        
    finally:
        # Cleanup
        if scraper:
            print("\nClosing browser...")
            scraper.stop()
        
        if db_manager:
            print("Closing database connection...")
            await db_manager.close()
        
        print("\nProcessing complete!")


if __name__ == "__main__":
    asyncio.run(main())
