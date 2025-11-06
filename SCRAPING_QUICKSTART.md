# Web Scraping Quick Start

## What Was Created

I've set up a comprehensive web scraping solution for the Big Flavor Band website that will extract:

✅ **Song ratings** (star column)  
✅ **Sessions** (e.g., "Full Strength")  
✅ **Comments** (from the comments popup, including authors)  
✅ **Uploaded on** date  
✅ **Recorded on** date  
✅ **Instruments** (who played what, from edit screen)  
✅ **Original flag** (whether song is an original)  
✅ **MP3 audio files** (downloads to `audio_library/`)  

### New Files

1. **`web_scraper.py`** - Main scraping logic using Selenium
2. **`scraped_data_manager.py`** - Database operations for scraped data
3. **`scrape_and_populate.py`** - Orchestration script
4. **`apply_schema.py`** - Helper to apply database schema
5. **`sql/init/02-add-song-details.sql`** - Database schema updates
6. **`WEB_SCRAPING_GUIDE.md`** - Detailed documentation

### Updated Files

- **`requirements.txt`** - Added web scraping dependencies

## Quick Start

### Step 1: Apply Database Schema

```powershell
python apply_schema.py
```

This will add the new tables and columns needed for scraped data.

### Step 2: Test the Scraper (Dry Run)

Run with the browser visible first to see what's happening:

```powershell
python scrape_and_populate.py --no-headless --no-download
```

This will:
- Show the Chrome browser window
- Navigate to bigflavorband.com
- Extract song data
- NOT download MP3 files (faster for testing)
- Insert data into the database

### Step 3: Full Scrape

Once you've verified it works, run a full scrape:

```powershell
python scrape_and_populate.py
```

This runs in headless mode and downloads all MP3 files.

## Important: Customize Selectors

⚠️ **The scraper uses generic HTML selectors** that may need adjustment based on the actual structure of bigflavorband.com.

### To Customize:

1. Run with `--no-headless` to see the browser
2. Right-click elements and "Inspect" to see the HTML
3. Update selectors in `web_scraper.py`:

**For the main song table:**
```python
# Line ~145 in web_scraper.py
song_rows = soup.find_all('tr', class_='song-row')  # Update class name
```

**For ratings:**
```python
# Line ~180 in web_scraper.py  
stars = len(rating_cell.find_all('span', class_='star'))  # Update selector
```

**For the edit screen fields:**
```python
# Line ~269 in web_scraper.py
title_input = soup.find('input', {'name': re.compile(r'title', re.I)})
session_select = soup.find('select', {'name': re.compile(r'session', re.I)})
# etc.
```

## Command-Line Options

```powershell
# Show browser window (good for debugging)
python scrape_and_populate.py --no-headless

# Skip downloading MP3 files (faster)
python scrape_and_populate.py --no-download

# Login (if site requires authentication)
python scrape_and_populate.py --username YOUR_USER --password YOUR_PASS

# Combine options
python scrape_and_populate.py --no-headless --no-download --username admin --password pass123
```

## What Gets Stored

### Database Tables

**songs** - Extended with new columns:
- `rating` (1-5 stars)
- `session` (session name)
- `uploaded_on` (timestamp)
- `recorded_on` (date)
- `is_original` (boolean)
- `track_number` (integer)

**sessions** - Recording sessions:
- `name` (e.g., "Full Strength")
- `description`

**song_comments** - All comments:
- `song_id` (foreign key)
- `comment_text`
- `author`
- `created_at`

**musicians** - All musicians:
- `name` (unique)

**instruments** - All instruments:
- `name` (unique)

**song_instruments** - Who played what on which song:
- `song_id`
- `musician_id`
- `instrument_id`

### Files Created

- **`audio_library/*.mp3`** - Downloaded audio files
- **`scraped_songs_YYYYMMDD_HHMMSS.json`** - Backup of all scraped data
- **`scraping.log`** - Detailed log of scraping process

## Query Examples

After scraping, you can query the data:

```python
import asyncio
from database import DatabaseManager
from scraped_data_manager import ScrapedDataManager

async def examples():
    db = DatabaseManager()
    await db.connect()
    scraper_db = ScrapedDataManager(db)
    
    # Get all sessions
    sessions = await scraper_db.get_all_sessions()
    print(f"Sessions: {[s['name'] for s in sessions]}")
    
    # Get top rated songs
    top_songs = await scraper_db.get_top_rated_songs(limit=5)
    for song in top_songs:
        print(f"{song['title']}: {song['rating']} stars")
    
    # Get songs by musician
    songs = await scraper_db.get_musician_songs("Robby")
    print(f"Robby played on {len(songs)} songs")
    
    # Get only originals
    originals = await scraper_db.get_original_songs()
    print(f"Found {len(originals)} original songs")
    
    await db.close()

asyncio.run(examples())
```

## Troubleshooting

### "Element not found" errors
- Run with `--no-headless` to see the page
- Update CSS selectors in `web_scraper.py` to match the actual HTML
- Add more wait time if pages load slowly

### Database connection errors
- Make sure PostgreSQL is running: `docker-compose up -d`
- Check if schema was applied: `python apply_schema.py`

### Chrome driver issues
- The script auto-downloads ChromeDriver
- If it fails, manually download from https://chromedriver.chromium.org/
- Make sure Chrome browser is installed

### No songs found
- Check if authentication is needed (use `--username` and `--password`)
- Verify the website is accessible
- Look at `scraping.log` for detailed errors

## Next Steps

After successful scraping:

1. **Verify data:**
   ```powershell
   python
   >>> import asyncio
   >>> from scraped_data_manager import ScrapedDataManager
   >>> from database import DatabaseManager
   >>> async def check():
   ...     db = DatabaseManager()
   ...     await db.connect()
   ...     songs = await db.get_all_songs()
   ...     print(f"Total songs: {len(songs)}")
   ...     await db.close()
   >>> asyncio.run(check())
   ```

2. **Run audio analysis** on downloaded MP3s:
   ```powershell
   python pre_analyze_audio.py
   ```

3. **Test the agent** with scraped data:
   ```powershell
   python agent.py
   ```

## Need Help?

See **`WEB_SCRAPING_GUIDE.md`** for detailed documentation including:
- How to customize selectors
- Database schema details
- Advanced query examples
- Debugging tips
