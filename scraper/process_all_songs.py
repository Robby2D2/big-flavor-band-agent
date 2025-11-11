"""
Process ALL songs from bigflavorband.com with complete pipeline:
1. Parse RSS feed to get song IDs
2. Scrape only new songs (skip existing ones)
3. For each song (one at a time):
   - Insert into database
   - Analyze audio features
   - Create audio embeddings
   - Extract lyrics (Whisper large-v3)
"""

import asyncio
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, Set
from urllib.parse import unquote

import requests

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


def parse_rss_feed(rss_url: str = "https://bigflavorband.com/rss") -> Dict[str, int]:
    """
    Parse RSS feed to extract song ID mapping from audio URLs.
    
    Returns:
        Dict mapping "session--title" to numeric song ID
        Example: {"Session Name--Song Title": 1234}
    """
    logger.info(f"Fetching RSS feed from {rss_url}")
    
    try:
        response = requests.get(rss_url, timeout=30)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        song_id_map = {}
        
        # Parse each item in RSS feed
        for item in root.findall('.//item'):
            link_elem = item.find('link')
            if link_elem is not None and link_elem.text:
                # URL format: https://bigflavorband.com/audio/<song_id>/<session>--<title>.mp3
                url = unquote(link_elem.text)  # Decode URL encoding
                
                # Extract song ID and filename
                match = re.search(r'/audio/(\d+)/(.+?)\.mp3', url)
                if match:
                    song_id = int(match.group(1))
                    filename = match.group(2)  # "session--title"
                    
                    song_id_map[filename] = song_id
                    logger.debug(f"Mapped: {filename} -> {song_id}")
        
        logger.info(f"Successfully parsed RSS feed: found {len(song_id_map)} song mappings")
        return song_id_map
        
    except Exception as e:
        logger.error(f"Failed to parse RSS feed: {e}")
        logger.warning("Continuing without RSS feed data - will scrape all songs")
        return {}


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
                    analysis = rag_system.embedding_extractor.extract_librosa_features(audio_path)
                    
                    # Update database with audio analysis
                    await db_manager.pool.execute("""
                        UPDATE songs 
                        SET tempo_bpm = $1, key = $2, duration_seconds = $3
                        WHERE id = $4
                    """, analysis.get('tempo_bpm'), analysis.get('key'), 
                        analysis.get('duration_seconds'), song_id)
                    
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
        print("\n[1/4] Connecting to database...")
        db_manager = DatabaseManager()
        await db_manager.connect()
        data_manager = ScrapedDataManager(db_manager)
        print("✓ Database connected")
        
        # Get existing song IDs from database first
        existing_song_ids = await db_manager.pool.fetch("SELECT id FROM songs")
        existing_ids_set = {row['id'] for row in existing_song_ids}
        print(f"Found {len(existing_ids_set)} songs already in database")
        
        # Parse RSS feed to get song ID mappings
        print("\n[2/4] Parsing RSS feed...")
        print("="*70)
        rss_song_map = parse_rss_feed()
        print(f"✓ RSS feed parsed: {len(rss_song_map)} song mappings")
        
        # Create reverse lookup: song_id -> session--title
        id_to_key = {song_id: key for key, song_id in rss_song_map.items()}
        
        # Identify which song IDs we can skip (already in database)
        skip_ids = existing_ids_set & set(rss_song_map.values())
        print(f"Can skip {len(skip_ids)} songs that are already in database")
        
        # Initialize RAG system
        print("\n[3/4] Initializing RAG system...")
        rag_system = SongRAGSystem(db_manager, use_clap=True)
        print("✓ RAG system initialized")
        
        # Initialize scraper with RSS mapping
        print("\n[4/4] Initializing web scraper...")
        scraper = BigFlavorScraper(
            headless=True,
            download_audio=True,
            rss_song_map=rss_song_map  # Pass RSS mapping to scraper
        )
        scraper.navigate_to_songs()
        print("✓ Scraper initialized")
        
        # Scrape songs (will use RSS map to skip existing ones)
        print("\n" + "="*70)
        print("COLLECTING SONGS FROM WEBSITE")
        print("="*70)
        
        print(f"Found {len(existing_ids_set)} songs already in database")
        print(f"These will be skipped during scraping to save time\n")
        
        # Scrape all songs (will skip existing ones)
        print("="*70)
        print("COLLECTING NEW SONGS FROM WEBSITE")
        print("="*70)
        print("\nScraping songs from website...")
        print("(Skipping songs already in database)")
        print()
        
        songs = scraper.get_all_songs_with_details(
            max_scrolls=1000,  # High limit to get all songs
            limit=None,  # No limit
            existing_song_ids=existing_ids_set  # Skip these songs
        )
        
        if not songs:
            print("\n✗ No songs were scraped")
            return
        
        print(f"\n✓ Collected {len(songs)} songs from website\n")
        
        # IMMEDIATELY insert all scraped songs into database before processing
        print("="*70)
        print("INSERTING ALL SONGS INTO DATABASE")
        print("="*70)
        print("(Saving metadata immediately to prevent data loss)\n")
        
        inserted_count = 0
        updated_count = 0
        error_count = 0
        
        for i, song_data in enumerate(songs, 1):
            song_id = song_data.get('id')
            title = song_data.get('title', 'Unknown')
            
            try:
                # Check if song exists
                existing = await db_manager.pool.fetchval(
                    "SELECT id FROM songs WHERE id = $1", song_id
                )
                
                # Insert or update
                result_id = await data_manager.insert_song_with_details(song_data)
                
                if existing:
                    updated_count += 1
                    status = "updated"
                else:
                    inserted_count += 1
                    status = "inserted"
                
                if i % 50 == 0:
                    print(f"  Progress: {i}/{len(songs)} - {inserted_count} inserted, {updated_count} updated")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Failed to insert song {song_id} ({title}): {e}")
                print(f"  ✗ Error inserting song {song_id}: {e}")
        
        print(f"\n✓ Database insertion complete:")
        print(f"    Inserted: {inserted_count}")
        print(f"    Updated: {updated_count}")
        print(f"    Errors: {error_count}")
        print(f"    Total in DB: {inserted_count + updated_count}\n")
        
        if error_count > 0:
            print(f"⚠ {error_count} songs failed to insert - check logs for details\n")
        
        # Save backup JSON file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = Path(__file__).parent / f"scraped_songs_{timestamp}.json"
        
        print(f"Creating backup JSON file: {backup_file.name}")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(songs, f, indent=2, default=str, ensure_ascii=False)
        print(f"✓ Backup saved to {backup_file.name}\n")
        
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
