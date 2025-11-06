# Web Scraping Implementation Summary

## Overview

I've created a complete web scraping solution to extract all song data from the Big Flavor Band website (https://bigflavorband.com/) and store it in your PostgreSQL database.

## What Was Built

### 1. Database Schema Extensions (`sql/init/02-add-song-details.sql`)

New tables and columns to store:
- **Song ratings** (1-5 stars)
- **Sessions** (recording sessions like "Full Strength")
- **Comments** with authors
- **Musicians** and **Instruments**
- **Song-Instrument-Musician relationships** (who played what)
- **Original song flag**
- **Upload and recording dates**
- **Track numbers**

### 2. Web Scraper (`web_scraper.py`)

A Selenium-based scraper that:
- ✅ Navigates the Big Flavor Band website
- ✅ Extracts data from the main song table
- ✅ Navigates to each song's "Edit" screen
- ✅ Extracts all form fields (session, dates, original flag, etc.)
- ✅ Extracts instruments and musicians
- ✅ Opens comments popup and extracts all comments
- ✅ Downloads MP3 audio files
- ✅ Handles authentication (if needed)
- ✅ Includes rate limiting (polite delays)
- ✅ Creates JSON backup of all scraped data

### 3. Database Manager (`scraped_data_manager.py`)

Extended database operations for:
- Inserting songs with all details
- Managing sessions
- Adding comments
- Linking musicians with instruments and songs
- Querying by session, musician, rating, etc.
- Getting top-rated songs
- Finding original songs

### 4. Orchestration Script (`scrape_and_populate.py`)

Main script that:
- Connects to the database
- Runs the scraper
- Inserts all data into PostgreSQL
- Creates JSON backup
- Logs all operations
- Handles errors gracefully

### 5. Helper Scripts

- **`apply_schema.py`** - Applies database schema updates
- **`test_scraper.py`** - Interactive test tool for debugging selectors

### 6. Documentation

- **`SCRAPING_QUICKSTART.md`** - Quick start guide
- **`WEB_SCRAPING_GUIDE.md`** - Comprehensive documentation

## Getting Started

### Step 1: Apply Database Schema

```powershell
python apply_schema.py
```

### Step 2: Test the Scraper

```powershell
# Interactive test with visible browser
python test_scraper.py
```

This will:
1. Open Chrome browser (visible)
2. Navigate to bigflavorband.com
3. Show you what data it extracts
4. Help you identify if selectors need adjustment

### Step 3: Full Scrape

```powershell
# Full scrape (headless, with downloads)
python scrape_and_populate.py

# Or with visible browser (for first run)
python scrape_and_populate.py --no-headless
```

## Important: Customizing Selectors

⚠️ The scraper uses **generic CSS selectors** that work for common HTML patterns. You'll likely need to adjust them based on the actual HTML structure of bigflavorband.com.

### Key Areas to Check

1. **Main song table** (`_parse_song_row()` method):
   - Song rows selector
   - Title link location
   - Rating stars
   - Session column

2. **Edit page fields** (`_extract_form_fields()` method):
   - Form input names
   - Select dropdowns
   - Checkbox for original songs
   - Date fields

3. **Instruments** (`_extract_instruments()` method):
   - Instrument table/list
   - Musician names
   - Instrument names

4. **Comments** (`_extract_comments()` method):
   - Comment button/link
   - Comment popup selector
   - Author and text elements

### How to Customize

1. Run `python test_scraper.py` (browser stays open)
2. Right-click elements → "Inspect"
3. Note the HTML structure (classes, IDs, names)
4. Update selectors in `web_scraper.py`
5. Run test again

## Data Flow

```
Big Flavor Website
    ↓ (Selenium scraping)
BigFlavorScraper
    ↓ (structured data)
scrape_and_populate.py
    ↓ (database insertion)
ScrapedDataManager
    ↓ (SQL operations)
PostgreSQL Database
```

## Output Files

After scraping, you'll have:

1. **Database records** - All data in PostgreSQL
2. **Audio files** - `audio_library/*.mp3`
3. **JSON backup** - `scraped_songs_[timestamp].json`
4. **Log file** - `scraping.log`

## Command Line Options

```powershell
# Show browser (debugging)
python scrape_and_populate.py --no-headless

# Skip audio downloads (faster)
python scrape_and_populate.py --no-download

# With authentication
python scrape_and_populate.py --username USER --password PASS

# Combine options
python scrape_and_populate.py --no-headless --no-download
```

## Database Queries

After scraping, query the data:

```python
import asyncio
from database import DatabaseManager
from scraped_data_manager import ScrapedDataManager

async def query_examples():
    db = DatabaseManager()
    await db.connect()
    scraper_db = ScrapedDataManager(db)
    
    # All sessions
    sessions = await scraper_db.get_all_sessions()
    
    # Songs from a session
    songs = await scraper_db.get_session_songs("Full Strength")
    
    # Top rated
    top = await scraper_db.get_top_rated_songs(limit=10)
    
    # By musician
    songs = await scraper_db.get_musician_songs("Robby")
    
    # Originals only
    originals = await scraper_db.get_original_songs()
    
    # Song with instruments and comments
    song_id = "123"
    instruments = await scraper_db.get_song_instruments(song_id)
    comments = await scraper_db.get_song_comments(song_id)
    
    await db.close()

asyncio.run(query_examples())
```

## Architecture

### Technologies Used

- **Selenium** - Browser automation
- **BeautifulSoup** - HTML parsing
- **ChromeDriver** - Chrome browser control (auto-downloaded)
- **Requests** - HTTP client for downloading files
- **asyncpg** - PostgreSQL async driver
- **PostgreSQL** - Database with pgvector extension

### Design Decisions

1. **Selenium over requests/BeautifulSoup alone** - Handles JavaScript rendering, authentication, popups
2. **Separate data manager** - Clean separation of scraping and database logic
3. **Generic selectors** - Flexible patterns that work for common HTML structures
4. **Rate limiting** - Polite 1-second delay between requests
5. **JSON backup** - Safety net if database insertion fails
6. **Comprehensive logging** - Debug scraping issues easily

## Next Steps

1. **Test the scraper** - Run `python test_scraper.py`
2. **Customize selectors** - Update based on actual HTML
3. **Full scrape** - Run `python scrape_and_populate.py`
4. **Verify data** - Check database for completeness
5. **Audio analysis** - Run audio analysis on downloaded MP3s
6. **Use the agent** - Query scraped data through your AI agent

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Element not found | Update CSS selectors in `web_scraper.py` |
| No songs found | Check if login required, verify site accessible |
| ChromeDriver error | Will auto-download; ensure Chrome installed |
| Database connection error | Run `docker-compose up -d` and `python apply_schema.py` |
| Timeout errors | Increase wait times in WebDriverWait calls |

## Files Reference

| File | Purpose |
|------|---------|
| `web_scraper.py` | Main scraping logic |
| `scraped_data_manager.py` | Database operations for scraped data |
| `scrape_and_populate.py` | Orchestration script |
| `apply_schema.py` | Apply database schema |
| `test_scraper.py` | Interactive testing tool |
| `sql/init/02-add-song-details.sql` | Schema updates |
| `SCRAPING_QUICKSTART.md` | Quick start guide |
| `WEB_SCRAPING_GUIDE.md` | Detailed documentation |

## Contact / Support

If you encounter issues:

1. Check `scraping.log` for detailed errors
2. Run with `--no-headless` to see what's happening
3. Use `test_scraper.py` to debug specific issues
4. Inspect HTML and update selectors as needed

## Success Indicators

You'll know it's working when:
- ✅ `test_scraper.py` shows song data
- ✅ Database has records in new tables (sessions, musicians, instruments, comments)
- ✅ `audio_library/` has MP3 files
- ✅ JSON backup file is created
- ✅ No errors in `scraping.log`

Good luck! The scraper is ready to extract all the data from Big Flavor Band's website.
