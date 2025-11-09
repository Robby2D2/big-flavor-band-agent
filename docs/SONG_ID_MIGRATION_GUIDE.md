# Song ID Migration and RAG Integration - Complete Guide

## Overview

This update implements a new song ID system based on numeric IDs extracted from MP3 URLs, along with full RAG (Retrieval-Augmented Generation) integration including automatic lyrics extraction.

## Key Changes

### 1. Song ID System
- **Old**: Song IDs were generated from titles (e.g., `"going_to_california_raga"`)
- **New**: Song IDs are numeric integers extracted from MP3 URLs (e.g., `1864`)
  - Example URL: `https://bigflavorband.com/audio/1864/Valentomkev--That%20s%20the%20Way.mp3`
  - Song ID: `1864`

### 2. File Naming Convention
- **Old**: `song_title.mp3` (e.g., `Going to California - raga.mp3`)
- **New**: `{id}_{title}.mp3` (e.g., `1864_Going_to_California_raga.mp3`)
- Files are still stored in `audio_library/` directory

### 3. Database Schema
- Song ID field changed from `VARCHAR(50)` to `INTEGER`
- All foreign key references updated to use `INTEGER`
- Migration script provided: `database/sql/migrations/04-migrate-song-id-to-integer.sql`

### 4. Comments Extraction
- Comments are now extracted from the Comments column during scraping
- Comments are stored in `song_comments` table with author attribution
- The scraper uses the `title` attribute on the Comments cell to get full comment text

### 5. RAG Integration
- Songs are automatically indexed in the RAG system after database insertion
- Lyrics are extracted using Whisper v3-large model
- Lyrics are stored in `text_embeddings` table with vector embeddings
- Supports semantic search queries like "Find 10 songs where Rob Danek is on Lead Vocals"

## Migration Steps

### Step 1: Backup Current Data (if needed)
```powershell
# Backup current database
pg_dump -h localhost -U bigflavor bigflavor > backup_before_migration.sql
```

### Step 2: Run Database Migration
```powershell
# Navigate to project directory
cd c:\Users\Rob\Documents\Projects\big-flavor-band-agent

# Activate virtual environment
venv\Scripts\Activate.ps1

# Run migration script
.\database\run_migration_song_id.ps1
```

**WARNING**: This migration will DROP all existing song data and recreate tables with new schema!

### Step 3: Verify Migration
```powershell
# Check that tables were created successfully
psql -h localhost -U bigflavor -d bigflavor -c "\dt"
```

## Testing

### Quick Test (30 songs with paging)
```powershell
# Activate environment
venv\Scripts\Activate.ps1

# Run test that starts from "Going to California - raga"
python -m pytest tests/test_scraper_with_new_id.py -v -s
```

This test will:
1. Scrape 30 songs starting from "Going to California - raga"
2. Verify numeric song IDs
3. Verify file naming format
4. Load songs into database
5. Extract lyrics for first 3 songs
6. Verify database storage

### Full Scrape (All Songs)
```powershell
# Navigate to scraper directory
cd scraper

# Run full scrape with RAG integration
python scrape_and_load_all.py
```

**Note**: Full scrape may take 60+ minutes depending on number of songs.

### Verify Database Contents
```powershell
# Run verification script
python tests/verify_database.py
```

This will show:
- All songs in database
- Songs with extracted lyrics
- RAG embeddings count
- Example queries by musician/instrument
- Comments and other metadata

## Code Changes Summary

### Modified Files

#### `scraper/web_scraper.py`
- Added `_extract_song_id_from_url()` - extracts numeric ID from MP3 URL
- Updated `_download_audio()` - uses new file naming convention (ID_title.mp3)
- Updated `_extract_song_details_from_popup()` - extracts and sets numeric song ID
- Updated `get_song_details()` - handles numeric song IDs
- Comments extraction already implemented in `_parse_song_row()`

#### `database/database.py`
- Changed `insert_song()` return type from `str` to `int`
- Added validation to convert string IDs to integers
- Updated `get_song()` parameter type to `int`

#### `scraper/scraped_data_manager.py`
- Updated all methods to use `int` for song_id parameters
- Added ID validation in `insert_song_with_details()`
- Updated type hints throughout

#### `scraper/scrape_and_load_all.py`
- Added RAG system initialization
- Added automatic lyrics extraction after song insertion
- Uses Whisper v3-large model as requested
- Improved error handling and progress reporting

### New Files

#### `database/sql/migrations/04-migrate-song-id-to-integer.sql`
- Complete migration script
- Drops old tables and recreates with INTEGER song IDs
- Recreates all foreign key relationships
- Recreates indexes and triggers

#### `database/run_migration_song_id.ps1`
- PowerShell script to run the migration
- Includes safety prompts
- Shows clear success/failure messages

#### `tests/test_scraper_with_new_id.py`
- Comprehensive test for new ID system
- Tests paging functionality
- Tests lyrics extraction
- Verifies database storage

#### `tests/verify_database.py`
- Database verification and query tool
- Shows songs, lyrics, musicians, comments
- Example semantic queries
- Useful for debugging and verification

## Usage Examples

### Query Songs by Musician
```python
import asyncio
from database.database import DatabaseManager
from scraper.scraped_data_manager import ScrapedDataManager

async def find_rob_songs():
    db = DatabaseManager()
    await db.connect()
    data_manager = ScrapedDataManager(db)
    
    # Find all songs where Rob Danek is on Lead Vocals
    songs = await data_manager.get_musician_songs("Rob Danek")
    
    for song in songs:
        if "Lead" in song.get('instrument', ''):
            print(f"{song['title']} - {song['session']}")
    
    await db.close()

asyncio.run(find_rob_songs())
```

### Search by Lyrics (RAG System)
```python
import asyncio
from database.database import DatabaseManager
from src.rag.big_flavor_rag import SongRAGSystem

async def search_lyrics():
    db = DatabaseManager()
    await db.connect()
    
    rag = SongRAGSystem(db)
    
    # Semantic search in lyrics
    results = await rag.search_by_text("love and peace")
    
    for result in results[:10]:
        print(f"{result['title']}: {result['relevance_score']}")
    
    await db.close()

asyncio.run(search_lyrics())
```

## Troubleshooting

### Issue: "Song ID must be numeric"
**Cause**: Song doesn't have an audio URL or URL doesn't match expected pattern
**Solution**: Check that the song has a valid MP3 URL in format `/audio/{id}/filename.mp3`

### Issue: Migration fails with "relation already exists"
**Cause**: Tables from old schema still exist
**Solution**: 
```sql
-- Manually drop all tables and run migration again
DROP TABLE IF EXISTS song_instruments CASCADE;
DROP TABLE IF EXISTS song_comments CASCADE;
DROP TABLE IF EXISTS audio_embeddings CASCADE;
DROP TABLE IF EXISTS text_embeddings CASCADE;
DROP TABLE IF EXISTS songs CASCADE;
```

### Issue: Lyrics extraction is slow
**Cause**: Whisper v3-large is a large model and requires GPU for good performance
**Solution**: 
- Check if CUDA is available: `python check_gpu.py`
- Consider using a smaller model for testing: `whisper_model_size='base'`
- Use `vad_filter=True` to skip silence and speed up extraction

### Issue: File not found when extracting lyrics
**Cause**: Audio file path in database doesn't match actual file location
**Solution**: Ensure `local_audio_path` in song data points to correct location in `audio_library/`

## RAG System Details

### Embeddings Stored
1. **Text Embeddings** (`text_embeddings` table)
   - Lyrics (full transcription)
   - Song metadata (title, description, etc.)
   - Dimension: 1536 (OpenAI embeddings)

2. **Audio Embeddings** (`audio_embeddings` table)
   - CLAP embeddings (audio-text joint space)
   - Librosa features (spectral, rhythm, etc.)
   - Dimension: 512

### Supported Queries
- Semantic search: "Find songs about heartbreak"
- Musician search: "Find songs where Rob plays guitar"
- Instrument search: "Find songs with mandolin"
- Session search: "Find songs from 'Valentomkev' session"
- Hybrid: Audio similarity + text meaning

## Performance Notes

- Scraping: ~2-5 seconds per song
- Lyrics extraction: ~10-30 seconds per song (depends on GPU and song length)
- Database insertion: <1 second per song
- Full scrape (500+ songs): 60-90 minutes

## Next Steps

1. **Run Migration**: `.\database\run_migration_song_id.ps1`
2. **Test Scraping**: `python tests/test_scraper_with_new_id.py`
3. **Verify Database**: `python tests/verify_database.py`
4. **Optional Full Scrape**: `python scraper/scrape_and_load_all.py`

## Questions?

Check the documentation:
- `docs/DATABASE_SETUP.md` - Database setup
- `docs/RAG_SYSTEM_GUIDE.md` - RAG system details
- `docs/LYRICS_QUICKSTART.md` - Lyrics extraction guide
- `ScrapingInstructions.txt` - Original scraping notes
