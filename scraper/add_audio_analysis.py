"""
Add audio analysis (BPM, key, duration) for all songs missing it.
Uses local audio_library files.
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
from src.rag.audio_embedding_extractor import AudioEmbeddingExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Add audio analysis for songs that don't have it"""
    
    print("\n" + "="*70)
    print("Add Audio Analysis - CPU-based librosa")
    print("="*70)
    print("\nThis will analyze audio files to extract:")
    print("  - Tempo (BPM)")
    print("  - Key")
    print("  - Duration (seconds)")
    print()
    
    db_manager = None
    
    try:
        # Initialize database
        print("[1/2] Connecting to database...")
        db_manager = DatabaseManager()
        await db_manager.connect()
        print("✓ Database connected")
        
        # Initialize audio extractor directly
        print("\n[2/2] Initializing audio analyzer...")
        audio_extractor = AudioEmbeddingExtractor(use_clap=False)  # Don't need CLAP for basic analysis
        print("✓ Audio analyzer initialized")
        
        # Get songs missing audio analysis
        print("\n" + "="*70)
        print("FINDING SONGS MISSING AUDIO ANALYSIS")
        print("="*70)
        
        songs_missing_analysis = await db_manager.pool.fetch("""
            SELECT id, title, audio_url
            FROM songs
            WHERE tempo_bpm IS NULL
            ORDER BY id
        """)
        
        if not songs_missing_analysis:
            print("\n✓ All songs already have audio analysis!")
            return
        
        print(f"Found {len(songs_missing_analysis)} songs missing audio analysis\n")
        
        # Process each song
        print("="*70)
        print("ANALYZING AUDIO FILES")
        print("="*70)
        print()
        
        audio_library = Path(project_root) / "audio_library"
        
        success_count = 0
        error_count = 0
        not_found_count = 0
        
        for i, row in enumerate(songs_missing_analysis, 1):
            song_id = row['id']
            title = row['title']
            
            print(f"\n[{i}/{len(songs_missing_analysis)}] {title}")
            print(f"  ID: {song_id}")
            
            # Construct local audio file path - match web_scraper.py sanitization
            import re
            safe_title = re.sub(r'[^\w\s-]', '', title).strip()  # Remove all non-word chars except spaces and hyphens
            safe_title = re.sub(r'[-\s]+', '_', safe_title)  # Replace hyphens and spaces with underscore
            
            local_audio_file = audio_library / f"{song_id}_{safe_title}.mp3"
            
            if not local_audio_file.exists():
                print(f"  ✗ Audio file not found: {local_audio_file}")
                not_found_count += 1
                continue
            
            try:
                # Extract audio features
                analysis = audio_extractor.extract_librosa_features(str(local_audio_file))
                
                # Update songs table with basic fields only
                await db_manager.pool.execute("""
                    UPDATE songs 
                    SET tempo_bpm = $1, key = $2, duration_seconds = $3
                    WHERE id = $4
                """, analysis.get('tempo'), analysis.get('estimated_key'), 
                    analysis.get('duration'), song_id)
                
                success_count += 1
                # Format output safely handling None values
                tempo_str = f"{analysis.get('tempo'):.1f}" if analysis.get('tempo') else 'N/A'
                duration_str = f"{analysis.get('duration'):.1f}" if analysis.get('duration') else 'N/A'
                energy_str = f"{analysis.get('energy'):.2f}" if analysis.get('energy') else 'N/A'
                print(f"  ✓ BPM: {tempo_str}, Key: {analysis.get('estimated_key', 'N/A')}, Duration: {duration_str}s, Energy: {energy_str}")
                
                # Progress update every 50 songs
                if i % 50 == 0:
                    print(f"\n  Progress: {i}/{len(songs_missing_analysis)} - {success_count} analyzed, {error_count} errors, {not_found_count} not found")
                
            except Exception as e:
                error_count += 1
                logger.error(f"Failed to analyze song {song_id} ({title}): {e}")
                print(f"  ✗ Error: {e}")
        
        # Final summary
        print("\n" + "="*70)
        print("FINAL SUMMARY")
        print("="*70)
        print(f"\nProcessed {len(songs_missing_analysis)} songs:")
        print(f"  Successfully analyzed:  {success_count}")
        print(f"  Audio files not found:  {not_found_count}")
        print(f"  Errors:                 {error_count}")
        
        if success_count == len(songs_missing_analysis):
            print("\n✓ All songs now have audio analysis!")
        elif success_count > 0:
            print(f"\n✓ Added audio analysis for {success_count} songs")
            if not_found_count > 0:
                print(f"⚠ {not_found_count} songs are missing audio files")
            if error_count > 0:
                print(f"⚠ {error_count} songs had errors during analysis")
        else:
            print("\n✗ No songs were analyzed")
        
        print()
        
    except Exception as e:
        logger.error(f"Process failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        
    finally:
        if db_manager:
            print("Closing database connection...")
            await db_manager.close()
        
        print("\nAnalysis complete!")


if __name__ == "__main__":
    asyncio.run(main())
