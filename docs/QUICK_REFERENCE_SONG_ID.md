# Quick Reference: Song ID Migration

## Quick Start Commands

### 1. Run Migration (Required First)
```powershell
venv\Scripts\Activate.ps1
.\database\run_migration_song_id.ps1
```

### 2. Test New System (30 songs)
```powershell
python tests/test_scraper_with_new_id.py
```

### 3. Verify Database
```powershell
python tests/verify_database.py
```

### 4. Full Scrape (Optional)
```powershell
cd scraper
python scrape_and_load_all.py
```

## What Changed

| Feature | Before | After |
|---------|--------|-------|
| **Song ID** | String from title<br>`"going_to_california_raga"` | Integer from URL<br>`1864` |
| **File Name** | `Going to California - raga.mp3` | `1864_Going_to_California_raga.mp3` |
| **Database ID Type** | `VARCHAR(50)` | `INTEGER` |
| **Comments** | Not extracted | ✅ Extracted & stored |
| **Lyrics** | Manual process | ✅ Auto-extracted with Whisper v3-large |
| **RAG Search** | Limited | ✅ Full semantic search |

## Key Files Modified

- `scraper/web_scraper.py` - ID extraction, file naming
- `database/database.py` - Integer IDs
- `scraper/scraped_data_manager.py` - Integer IDs
- `scraper/scrape_and_load_all.py` - RAG integration

## Key Files Added

- `database/sql/migrations/04-migrate-song-id-to-integer.sql`
- `database/run_migration_song_id.ps1`
- `tests/test_scraper_with_new_id.py`
- `tests/verify_database.py`
- `docs/SONG_ID_MIGRATION_GUIDE.md`
- `docs/IMPLEMENTATION_SUMMARY_SONG_ID.md`

## Example Queries

### Find Songs by Musician
```python
import asyncio
from database.database import DatabaseManager
from scraper.scraped_data_manager import ScrapedDataManager

async def main():
    db = DatabaseManager()
    await db.connect()
    dm = ScrapedDataManager(db)
    
    # SQL query example
    query = """
        SELECT s.title, i.name as instrument
        FROM songs s
        JOIN song_instruments si ON s.id = si.song_id
        JOIN musicians m ON si.musician_id = m.id
        JOIN instruments i ON si.instrument_id = i.id
        WHERE m.name = 'Rob Danek'
    """
    async with db.pool.acquire() as conn:
        songs = await conn.fetch(query)
    
    for song in songs:
        print(f"{song['title']}: {song['instrument']}")
    
    await db.close()

asyncio.run(main())
```

### Semantic Search in Lyrics
```python
from src.rag.big_flavor_rag import SongRAGSystem

async def search():
    db = DatabaseManager()
    await db.connect()
    rag = SongRAGSystem(db)
    
    results = await rag.search_by_text("love and peace")
    for r in results[:5]:
        print(f"{r['title']}: {r['score']}")
    
    await db.close()

asyncio.run(search())
```

## Troubleshooting

### "Song ID must be numeric"
→ Check audio URL format: `/audio/{id}/filename.mp3`

### Migration fails
→ Manually drop tables first:
```sql
DROP TABLE IF EXISTS song_instruments CASCADE;
DROP TABLE IF EXISTS song_comments CASCADE;
DROP TABLE IF EXISTS songs CASCADE;
```

### Lyrics extraction slow
→ Check GPU: `python check_gpu.py`
→ Or use smaller model: `whisper_model_size='base'`

## Support

See full documentation:
- `docs/SONG_ID_MIGRATION_GUIDE.md` - Complete guide
- `docs/IMPLEMENTATION_SUMMARY_SONG_ID.md` - What was done
- `docs/RAG_SYSTEM_GUIDE.md` - RAG details
- `docs/LYRICS_QUICKSTART.md` - Lyrics extraction
