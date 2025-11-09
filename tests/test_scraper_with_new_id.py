"""
Test scraping with new song ID system and verify database storage
This test will:
1. Scrape 30 songs starting from "Going to California - raga" (paging test)
2. Verify song IDs are numeric from MP3 URLs
3. Verify file naming uses ID + title format
4. Load songs into database
5. Extract lyrics for test songs
6. Query database to verify stored data
"""

import asyncio
import logging
import json
import sys
from pathlib import Path
from datetime import datetime

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


async def main():
    """Main test function"""
    
    print("\n" + "="*70)
    print("Song Scraper Test - Paging & Database Verification")
    print("="*70)
    print()
    print("This test will:")
    print("  1. Scrape 5 songs starting from 'Going to California - raga'")
    print("  2. Verify numeric song IDs from MP3 URLs")
    print("  3. Verify file naming (ID_title.mp3)")
    print("  4. Load into database")
    print("  5. Extract lyrics for first 3 songs")
    print("  6. Verify database storage")
    print()
    
    response = input("Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Cancelled.")
        return
    
    scraper = None
    db_manager = None
    
    try:
        # Initialize database
        print("\n[1/6] Connecting to database...")
        db_manager = DatabaseManager()
        await db_manager.connect()
        data_manager = ScrapedDataManager(db_manager)
        print("✓ Database connected")
        
        # Initialize RAG system
        print("\n[2/6] Initializing RAG system...")
        rag_system = SongRAGSystem(db_manager, use_clap=True)
        print("✓ RAG system initialized")
        
        # Initialize scraper
        print("\n[3/6] Initializing web scraper...")
        scraper = BigFlavorScraper(
            headless=False,  # Visible browser
            download_audio=True  # Download MP3 files
        )
        scraper.navigate_to_songs()
        print("✓ Scraper initialized")
        
        # Scrape songs with paging test
        print("\n[4/6] Scraping 5 songs starting from 'Going to California - raga'...")
        print("(This tests the paging functionality)")
        print()
        
        start_from_song = "Going to California - raga"
        songs = scraper.get_all_songs_with_details(
            max_scrolls=20,
            limit=5,
            start_from_song=start_from_song
        )
        
        print(f"\n✓ Scraped {len(songs)} songs")
        
        # Verify song IDs and file naming
        print("\n[5/6] Verifying song IDs and file names...")
        valid_ids = 0
        invalid_ids = 0
        valid_files = 0
        
        for song in songs:
            song_id = song.get('id')
            title = song.get('title', 'Unknown')
            local_path = song.get('local_audio_path', '')
            
            # Check if ID is numeric
            if isinstance(song_id, int) or (isinstance(song_id, str) and song_id.isdigit()):
                valid_ids += 1
            else:
                invalid_ids += 1
                logger.warning(f"Non-numeric ID for '{title}': {song_id}")
            
            # Check file naming format (should be ID_title.mp3)
            if local_path and str(song_id) in local_path:
                valid_files += 1
            elif local_path:
                logger.warning(f"File name doesn't contain ID for '{title}': {local_path}")
        
        print(f"  Valid numeric IDs:     {valid_ids}/{len(songs)}")
        print(f"  Valid file names:      {valid_files}/{len(songs)}")
        
        if invalid_ids > 0:
            print(f"  ⚠ Found {invalid_ids} songs with non-numeric IDs")
        
        # Show first 3 songs as examples
        print("\nFirst 3 songs:")
        for i, song in enumerate(songs[:3], 1):
            print(f"  {i}. ID={song.get('id')}, Title={song.get('title')}")
            print(f"     File={song.get('local_audio_path', 'N/A')}")
            print(f"     URL={song.get('audio_url', 'N/A')[:80]}...")
        
        # Load into database
        print(f"\n[6/6] Loading songs into database...")
        
        inserted_count = 0
        for i, song_data in enumerate(songs, 1):
            try:
                if 'id' not in song_data or not song_data['id']:
                    logger.warning(f"Skipping song without ID: {song_data.get('title')}")
                    continue
                
                song_id = await data_manager.insert_song_with_details(song_data)
                inserted_count += 1
                
                if i % 5 == 0:
                    print(f"  Loaded {i}/{len(songs)} songs...")
                    
            except Exception as e:
                logger.error(f"Failed to insert song {song_data.get('title')}: {e}")
        
        print(f"\n✓ Loaded {inserted_count} songs into database")
        
        # Perform audio analysis and indexing for all songs with audio files
        print("\n" + "="*70)
        print("AUDIO ANALYSIS & INDEXING")
        print("="*70)
        print("Analyzing audio features and creating embeddings...")
        
        analysis_count = 0
        indexed_count = 0
        
        for i, song in enumerate(songs, 1):
            if not song.get('local_audio_path'):
                continue
            
            try:
                song_id = song['id'] if isinstance(song['id'], int) else int(song['id'])
                print(f"\n  [{i}/{len(songs)}] {song.get('title')[:50]}...")
                
                # 1. Extract audio features using librosa
                features = rag_system.embedding_extractor.extract_librosa_features(song['local_audio_path'])
                
                if features:
                    # 2. Update songs table with key audio features
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
                    
                    # 3. Save to audio_analysis table
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
                        song.get('audio_url', ''),
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
                    
                    analysis_count += 1
                    
                    # 4. Create audio embeddings (like index_audio_library.py does)
                    # Ensure song_id is integer for index_audio_file
                    if await rag_system.index_audio_file(song['local_audio_path'], song_id):
                        indexed_count += 1
                        print(f"      ✓ BPM: {features.get('tempo', 0):.1f}, Key: {features.get('estimated_key', 'Unknown')}, Duration: {features.get('duration', 0):.1f}s, Indexed: Yes")
                    else:
                        print(f"      ⚠ BPM: {features.get('tempo', 0):.1f}, Key: {features.get('estimated_key', 'Unknown')}, Duration: {features.get('duration', 0):.1f}s, Indexed: Failed")
                else:
                    print(f"      ⚠ Analysis failed")
                    
            except Exception as e:
                logger.error(f"Failed to analyze/index audio: {e}")
        
        print(f"\n✓ Analyzed: {analysis_count}/{len([s for s in songs if s.get('local_audio_path')])} songs")
        print(f"✓ Indexed: {indexed_count}/{len([s for s in songs if s.get('local_audio_path')])} songs (audio_embeddings created)")
        
        # Extract lyrics for first 3 songs
        print("\n" + "="*70)
        print("LYRICS EXTRACTION")
        print("="*70)
        print("Extracting lyrics for first 3 songs (Whisper large-v3, no VAD, no demucs)...")
        
        lyrics_extracted = 0
        for i, song in enumerate(songs[:3], 1):
            if not song.get('local_audio_path'):
                continue
            
            try:
                print(f"\n  [{i}/3] {song.get('title')[:50]}...")
                result = await rag_system.extract_and_index_lyrics(
                    audio_path=song['local_audio_path'],
                    song_id=song['id'],
                    separate_vocals=False,
                    vad_filter=False,
                    whisper_model_size='large-v3'
                )
                
                if result.get('lyrics'):
                    lyrics_extracted += 1
                    lyrics_preview = result['lyrics'][:200].replace('\n', ' ')
                    print(f"      ✓ Extracted {len(result['lyrics'])} characters")
                    print(f"      Preview: {lyrics_preview}...")
                else:
                    print(f"      ⚠ No lyrics found")
                    
            except Exception as e:
                logger.error(f"Failed to extract lyrics: {e}")
        
        print(f"\n✓ Extracted lyrics for {lyrics_extracted}/3 songs")
        
        # Verify database storage
        print("\n" + "="*70)
        print("DATABASE VERIFICATION")
        print("="*70)
        
        for i, song in enumerate(songs[:3], 1):
            song_id = song.get('id')
            if not song_id:
                continue
            
            print(f"\nSong {i}: {song.get('title')}")
            print(f"  ID: {song_id}")
            
            # Get song from database
            db_song = await db_manager.get_song(int(song_id) if isinstance(song_id, str) else song_id)
            if db_song:
                print(f"  ✓ Found in database")
                print(f"    Title: {db_song.get('title')}")
                print(f"    Session: {db_song.get('session')}")
                print(f"    Audio URL: {db_song.get('audio_url', '')[:60]}...")
            else:
                print(f"  ✗ NOT found in database")
            
            # Get comments
            comments = await data_manager.get_song_comments(int(song_id) if isinstance(song_id, str) else song_id)
            print(f"  Comments: {len(comments)}")
            if comments:
                for comment in comments[:2]:
                    print(f"    - {comment.get('comment_text')[:60]}...")
            
            # Get instruments
            instruments = await data_manager.get_song_instruments(int(song_id) if isinstance(song_id, str) else song_id)
            print(f"  Instruments: {len(instruments)}")
            if instruments:
                for inst in instruments[:3]:
                    print(f"    - {inst.get('musician')}: {inst.get('instrument')}")
            
            # Get audio analysis
            audio_url = song.get('audio_url', '')
            if audio_url:
                async with db_manager.pool.acquire() as conn:
                    analysis = await conn.fetchrow(
                        "SELECT bpm, key, energy FROM audio_analysis WHERE audio_url = $1",
                        audio_url
                    )
                    if analysis:
                        print(f"  Audio Analysis: BPM={analysis['bpm']:.1f}, Key={analysis['key']}, Energy={analysis['energy']:.3f}")
                    else:
                        print(f"  Audio Analysis: Not found")
            
            # Check for lyrics in database
            query = "SELECT content FROM text_embeddings WHERE song_id = $1 AND content_type = 'lyrics'"
            async with db_manager.pool.acquire() as conn:
                lyrics_row = await conn.fetchrow(query, int(song_id) if isinstance(song_id, str) else song_id)
            
            if lyrics_row:
                lyrics_text = lyrics_row['content']
                print(f"  Lyrics: {len(lyrics_text)} characters")
                print(f"    Preview: {lyrics_text[:100].replace(chr(10), ' ')}...")
            else:
                print(f"  Lyrics: Not extracted yet")
        
        # Summary
        print("\n" + "="*70)
        print("TEST COMPLETE!")
        print("="*70)
        print(f"Songs scraped:      {len(songs)}")
        print(f"Valid numeric IDs:  {valid_ids}")
        print(f"Songs in database:  {inserted_count}")
        print(f"Lyrics extracted:   {lyrics_extracted}")
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
