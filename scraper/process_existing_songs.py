"""
Process songs that are already in the database - skip scraping phase.
Fills in missing audio analysis, embeddings, and lyrics.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from database.database import DatabaseManager
from scraper.scraped_data_manager import ScrapedDataManager
from src.rag.big_flavor_rag import SongRAGSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def process_song(song_data: dict, db_manager: DatabaseManager, rag_system: SongRAGSystem, 
                       index: int, total: int, lyrics_extractor=None):
    """
    Process a single song, only filling in missing data.
    """
    results = {
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
        title = song_data['title']
        song_id = song_data['id']
        
        print(f"\n{'='*70}")
        print(f"SONG {index}/{total}: {title}")
        print(f"{'='*70}")
        print(f"ID: {song_id}")
        
        # Check what already exists
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
        
        has_audio_analysis = existing_data and existing_data['tempo_bpm'] is not None
        has_audio_embedding = existing_data['has_audio_embedding'] if existing_data else False
        has_lyrics = existing_data['has_lyrics'] if existing_data else False
        
        print(f"  Current state:")
        print(f"    Audio analysis: {'✓' if has_audio_analysis else '✗'}")
        print(f"    Audio embedding: {'✓' if has_audio_embedding else '✗'}")
        print(f"    Lyrics: {'✓' if has_lyrics else '✗'}")
        
        audio_file = song_data.get('audio_file')
        if not audio_file or not Path(audio_file).exists():
            print(f"  ✗ Audio file not found: {audio_file}")
            results['errors'].append("Audio file not found")
            return results
        
        # 1. Audio Analysis
        print("\n[1/3] Analyzing audio features...")
        if has_audio_analysis:
            print(f"  ✓ Audio analysis already exists - skipping")
            results['skipped']['audio_analysis'] = True
        else:
            try:
                audio_features = await rag_system.embedding_extractor.analyze_audio(audio_file)
                if audio_features:
                    await db_manager.pool.execute("""
                        UPDATE songs 
                        SET tempo_bpm = $1, key = $2, duration_seconds = $3
                        WHERE id = $4
                    """, audio_features['tempo_bpm'], audio_features['key'], 
                        audio_features['duration_seconds'], song_id)
                    results['audio_analyzed'] = True
                    print(f"  ✓ Analyzed: {audio_features['tempo_bpm']} BPM, {audio_features['key']}, {audio_features['duration_seconds']}s")
            except Exception as e:
                error = f"Audio analysis error: {e}"
                results['errors'].append(error)
                print(f"  ✗ {error}")
        
        # 2. Audio Embeddings
        print("\n[2/3] Creating audio embeddings...")
        if has_audio_embedding:
            print(f"  ✓ Audio embeddings already exist - skipping")
            results['skipped']['audio_embeddings'] = True
        else:
            try:
                success = await rag_system.index_audio_file(song_id, audio_file)
                if success:
                    results['audio_indexed'] = True
                    print(f"  ✓ Created audio embeddings")
            except Exception as e:
                error = f"Audio embedding error: {e}"
                results['errors'].append(error)
                print(f"  ✗ {error}")
        
        # 3. Lyrics Extraction
        print("\n[3/3] Extracting lyrics (Whisper large-v3)...")
        if has_lyrics:
            print(f"  ✓ Lyrics already exist - skipping")
            results['skipped']['lyrics'] = True
        else:
            try:
                await rag_system.extract_and_index_lyrics(
                    song_id, 
                    audio_file,
                    lyrics_extractor=lyrics_extractor
                )
                results['lyrics_extracted'] = True
                lyrics_check = await db_manager.pool.fetchval("""
                    SELECT embedding FROM text_embeddings 
                    WHERE song_id = $1 AND content_type = 'lyrics'
                """, song_id)
                if lyrics_check:
                    print(f"  ✓ Extracted and indexed lyrics")
            except Exception as e:
                error = f"Lyrics extraction error: {e}"
                results['errors'].append(error)
                print(f"  ✗ {error}")
        
        # Summary
        print(f"\n{'─'*70}")
        print(f"SUMMARY: {title[:50]}")
        print(f"  Audio Analysis: {'✓ (existing)' if results['skipped']['audio_analysis'] else ('✓' if results['audio_analyzed'] else '✗')}")
        print(f"  Audio Embeddings: {'✓ (existing)' if results['skipped']['audio_embeddings'] else ('✓' if results['audio_indexed'] else '✗')}")
        print(f"  Lyrics: {'✓ (existing)' if results['skipped']['lyrics'] else ('✓' if results['lyrics_extracted'] else '✗')}")
        if results['errors']:
            print(f"  Errors: {len(results['errors'])}")
        print(f"{'─'*70}")
        
    except Exception as e:
        error = f"Processing error: {e}"
        results['errors'].append(error)
        print(f"\n✗ ERROR: {error}")
    
    return results


async def main():
    """Load songs from database and process them"""
    
    print("\n" + "="*70)
    print("Process Existing Songs - Skip Scraping")
    print("="*70)
    print("\nThis will:")
    print("  1. Load all songs from database")
    print("  2. Process each song (fill in missing data):")
    print("     - Audio analysis (if missing)")
    print("     - Audio embeddings (if missing)")
    print("     - Lyrics extraction (if missing)")
    print()
    
    db_manager = None
    
    try:
        # Initialize database
        print("[1/2] Connecting to database...")
        db_manager = DatabaseManager()
        await db_manager.connect()
        print("✓ Database connected")
        
        # Initialize RAG system
        print("\n[2/2] Initializing RAG system...")
        rag_system = SongRAGSystem(db_manager, use_clap=True)
        print("✓ RAG system initialized")
        
        # Load songs from database
        print("\n" + "="*70)
        print("LOADING SONGS FROM DATABASE")
        print("="*70)
        
        songs_data = await db_manager.pool.fetch("""
            SELECT id, title, audio_url
            FROM songs
            ORDER BY id
        """)
        
        if not songs_data:
            print("\n✗ No songs found in database")
            return
        
        # Convert to dict format and construct local audio paths
        songs = []
        audio_library = Path(project_root) / "audio_library"
        
        for row in songs_data:
            # Construct the local filename: {song_id}_{sanitized_title}.mp3
            # The scraper sanitizes titles by replacing special chars with underscores
            song_id = row['id']
            title = row['title']
            
            # Sanitize title the same way the scraper does
            sanitized_title = title.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_')
            sanitized_title = sanitized_title.replace('?', '_').replace('*', '_').replace('"', '_')
            sanitized_title = sanitized_title.replace('<', '_').replace('>', '_').replace('|', '_')
            
            local_audio_file = audio_library / f"{song_id}_{sanitized_title}.mp3"
            
            songs.append({
                'id': song_id,
                'title': title,
                'audio_file': str(local_audio_file)
            })
        
        print(f"✓ Loaded {len(songs)} songs from database\n")
        
        # Initialize LyricsExtractor once
        print("Initializing Whisper large-v3 model...")
        from src.rag.lyrics_extractor import LyricsExtractor
        lyrics_extractor = LyricsExtractor(
            whisper_model_size='large-v3',
            use_gpu=True,
            min_confidence=0.5,
            load_demucs=False
        )
        print("✓ Whisper model loaded\n")
        
        # Process each song
        print("=" * 70)
        print("PROCESSING SONGS")
        print("="*70)
        print()
        
        all_results = []
        for i, song_data in enumerate(songs, 1):
            result = await process_song(
                song_data, 
                db_manager,
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
        
        total_analyzed = sum(1 for r in all_results if r['audio_analyzed'])
        total_indexed = sum(1 for r in all_results if r['audio_indexed'])
        total_lyrics = sum(1 for r in all_results if r['lyrics_extracted'])
        total_errors = sum(len(r['errors']) for r in all_results)
        
        print(f"\nProcessed {len(all_results)} songs:")
        print(f"  Audio analysis:       {total_analyzed}")
        print(f"  Audio embeddings:     {total_indexed}")
        print(f"  Lyrics extracted:     {total_lyrics}")
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
        if db_manager:
            print("Closing database connection...")
            await db_manager.close()
        
        print("\nProcessing complete!")


if __name__ == "__main__":
    asyncio.run(main())
