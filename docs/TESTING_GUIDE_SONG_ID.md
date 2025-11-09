# Step-by-Step Testing Guide

This guide walks you through testing the new song ID system and RAG integration.

## Prerequisites

- PostgreSQL database running
- Python virtual environment activated
- Database configured (see `docs/DATABASE_SETUP.md`)

## Step 1: Activate Environment

```powershell
# Navigate to project directory
cd c:\Users\Rob\Documents\Projects\big-flavor-band-agent

# Activate virtual environment
venv\Scripts\Activate.ps1
```

## Step 2: Run Database Migration

**⚠️ WARNING**: This will delete all existing song data!

```powershell
# Run migration script
.\database\run_migration_song_id.ps1
```

**Expected Output**:
```
===================================
Database Migration: Song ID to INTEGER
===================================

WARNING: This will DROP all existing songs and related data!
Continue? (yes/no): yes

Applying migration...
[SQL output...]
✓ Migration applied successfully!
```

**Verify Migration**:
```powershell
psql -h localhost -U bigflavor -d bigflavor -c "\dt"
```

You should see tables: `songs`, `song_comments`, `song_instruments`, `musicians`, `instruments`, etc.

## Step 3: Run Test Scraper

This will scrape 30 songs starting from "Going to California - raga" to test paging.

```powershell
# Run test
python tests/test_scraper_with_new_id.py
```

**What to Expect**:
1. Browser window opens (visible)
2. Navigates to bigflavorband.com
3. Scrolls to find "Going to California - raga"
4. Clicks each song to get details
5. Downloads MP3 files to `audio_library/`
6. Inserts songs into database
7. Extracts lyrics for first 3 songs
8. Shows verification results

**Test Duration**: 15-20 minutes

**Expected Output**:
```
======================================================================
Song Scraper Test - Paging & Database Verification
======================================================================

[1/6] Connecting to database...
✓ Database connected

[2/6] Initializing RAG system...
✓ RAG system initialized

[3/6] Initializing web scraper...
✓ Scraper initialized

[4/6] Scraping 30 songs starting from 'Going to California - raga'...
Processing song: Going to California - raga
  ✓ Got details for: Going to California - raga
[... more songs ...]

✓ Scraped 30 songs

[5/6] Verifying song IDs and file names...
  Valid numeric IDs:     30/30
  Valid file names:      30/30

First 3 songs:
  1. ID=1234, Title=Going to California - raga
     File=audio_library\1234_Going_to_California_raga.mp3
     URL=https://bigflavorband.com/audio/1234/...

[6/6] Loading songs into database...
  Loaded 5/30 songs...
  Loaded 10/30 songs...
[... progress ...]
✓ Loaded 30 songs into database

[Extra] Extracting lyrics for first 3 songs...
  [1/3] Going to California - raga...
      ✓ Extracted 1543 characters
      Preview: Going to California with an aching in my heart...
[... more lyrics ...]

✓ Extracted lyrics for 3/3 songs

======================================================================
DATABASE VERIFICATION
======================================================================

Song 1: Going to California - raga
  ID: 1234
  ✓ Found in database
    Title: Going to California - raga
    Session: Valentomkev
  Comments: 2
    - Great version!...
    - Love this song...
  Instruments: 3
    - Rob Danek: Vocals (Lead)
    - Tom Wadzinski: Guitar (Classical)
    - Kevin Eberman: Mandolin
  Lyrics: 1543 characters
    Preview: Going to California with an aching in my heart...

[... more songs ...]

======================================================================
TEST COMPLETE!
======================================================================
Songs scraped:      30
Valid numeric IDs:  30
Songs in database:  30
Lyrics extracted:   3
```

## Step 4: Verify Database Contents

```powershell
python tests/verify_database.py
```

**Expected Output**:
```
======================================================================
Database Verification Query
======================================================================

✓ Connected to database

[1] All Songs in Database
----------------------------------------------------------------------
Total songs: 30

1. ID=1234, Title=Going to California - raga
   Session=Valentomkev, Recorded=2019-02-15
   URL=https://bigflavorband.com/audio/1234/...

[... more songs ...]

[2] Songs with Lyrics Extracted
----------------------------------------------------------------------
Songs with lyrics: 3

1. ID=1234, Title=Going to California - raga
   Lyrics (1543 chars): Going to California with an aching in my heart...

[... more ...]

[3] RAG System Embeddings
----------------------------------------------------------------------
Text embeddings (lyrics, metadata): 3
Audio embeddings: 0
Song embeddings: 0

[4] Example Query: Find songs by Rob Danek on Lead Vocals
----------------------------------------------------------------------
Found 5 songs with Rob Danek on Lead Vocals:

1. Going to California - raga (Session: Valentomkev)
[... more ...]

[5] All Musicians in Database
----------------------------------------------------------------------
Total musicians: 15

1. Rob Danek: 8 songs
2. Tom Wadzinski: 12 songs
3. Kevin Eberman: 10 songs
[... more ...]

[6] Sample Comments
----------------------------------------------------------------------
Total comments found: 8

1. Going to California - raga
   Author: Unknown
   Comment: Great version!...

======================================================================
SUMMARY
======================================================================
Total songs:        30
Songs with lyrics:  3
Total comments:     8
Instrument entries: 45
Unique musicians:   15
```

## Step 5: Manual Verification

### Check Audio Files
```powershell
dir audio_library\
```

**Expected**: Files named like `1234_Going_to_California_raga.mp3`

### Query Specific Song
```powershell
psql -h localhost -U bigflavor -d bigflavor
```

```sql
-- Get song by ID
SELECT * FROM songs WHERE id = 1234;

-- Get instruments for song
SELECT m.name, i.name
FROM song_instruments si
JOIN musicians m ON si.musician_id = m.id
JOIN instruments i ON si.instrument_id = i.id
WHERE si.song_id = 1234;

-- Get lyrics
SELECT content FROM text_embeddings 
WHERE song_id = 1234 AND content_type = 'lyrics';

-- Count total songs
SELECT COUNT(*) FROM songs;
```

## Step 6: Test Semantic Search (Optional)

Create a test script:

```python
# test_semantic_search.py
import asyncio
from database.database import DatabaseManager
from src.rag.big_flavor_rag import SongRAGSystem

async def test_search():
    db = DatabaseManager()
    await db.connect()
    rag = SongRAGSystem(db)
    
    # Search by text
    print("Searching for 'california'...")
    results = await rag.search_by_text("california", limit=5)
    
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['title']} (score: {result.get('score', 'N/A')})")
    
    await db.close()

asyncio.run(test_search())
```

Run it:
```powershell
python test_semantic_search.py
```

## Troubleshooting

### Issue: Browser doesn't open
**Solution**: Check that Chrome/ChromeDriver is installed
```powershell
# Test WebDriver
python -c "from selenium import webdriver; driver = webdriver.Chrome(); driver.quit()"
```

### Issue: Database connection failed
**Solution**: Check PostgreSQL is running
```powershell
# Check service
Get-Service -Name postgresql*

# Start if needed
Start-Service postgresql-x64-14
```

### Issue: Songs have non-numeric IDs
**Cause**: Audio URL doesn't match expected pattern
**Solution**: Check scraper logs for URL format errors

### Issue: Lyrics extraction fails
**Solution**: Check Whisper installation
```powershell
python -c "import whisper; print(whisper.available_models())"
```

### Issue: No GPU acceleration
**Solution**: Install CUDA-enabled PyTorch
```powershell
python check_gpu.py
```

## Success Criteria

✅ Migration completed without errors
✅ 30 songs scraped successfully
✅ All songs have numeric IDs
✅ Files named with ID prefix
✅ Songs loaded into database
✅ Comments extracted and stored
✅ Instruments/musicians linked
✅ Lyrics extracted for test songs
✅ Database queries return correct data
✅ Paging works (advances from "Going to California - raga")

## Next Steps

After successful testing:

1. **Full Scrape**: Run `python scraper/scrape_and_load_all.py` to load all songs
2. **Extract All Lyrics**: Wait for full lyrics extraction (may take hours)
3. **Test Agent**: Use the Claude agent to query songs by musician/lyrics
4. **Backup**: Create database backup once fully loaded

## Support

If you encounter issues:

1. Check error logs in console output
2. Review `docs/SONG_ID_MIGRATION_GUIDE.md`
3. Check `docs/IMPLEMENTATION_SUMMARY_SONG_ID.md`
4. Verify database schema with `\dt` and `\d songs` in psql
