# Web Scraping Setup Guide

This guide explains how to scrape song data from the Big Flavor Band website and populate the database.

## Overview

The web scraping solution includes:

1. **Updated Database Schema** - New tables and columns for:
   - Song ratings (1-5 stars)
   - Sessions (recording sessions)
   - Comments (with authors)
   - Instruments and musicians
   - Original song flag
   - Upload and recording dates

2. **Web Scraper** - Selenium-based scraper that:
   - Navigates the Big Flavor Band website
   - Extracts data from song list and edit pages
   - Downloads MP3 files
   - Handles authentication if needed

3. **Data Management** - Database operations for:
   - Inserting songs with all details
   - Managing relationships (songs-instruments-musicians)
   - Querying by session, musician, rating, etc.

## Files Created

- `sql/init/02-add-song-details.sql` - Database schema updates
- `web_scraper.py` - Web scraping logic
- `scraped_data_manager.py` - Database operations for scraped data
- `scrape_and_populate.py` - Main script to run scraping

## Setup Instructions

### 1. Install Dependencies

First, install the required Python packages:

```powershell
# Activate your virtual environment if you have one
# .\venv\Scripts\Activate.ps1

# Install web scraping dependencies
pip install beautifulsoup4 selenium webdriver-manager requests
```

### 2. Update Database Schema

Apply the new schema to your PostgreSQL database:

```powershell
# Option 1: Using psql
psql -h localhost -p 5432 -U bigflavor -d bigflavor -f sql\init\02-add-song-details.sql

# Option 2: Using docker exec (if using Docker)
docker exec -i big-flavor-band-agent-postgres-1 psql -U bigflavor -d bigflavor < sql\init\02-add-song-details.sql
```

### 3. Run the Scraper

Run the scraping script:

```powershell
# Basic usage (headless mode, downloads audio)
python scrape_and_populate.py

# Show browser window (useful for debugging)
python scrape_and_populate.py --no-headless

# Skip audio downloads (faster)
python scrape_and_populate.py --no-download

# With authentication (if required)
python scrape_and_populate.py --username YOUR_USERNAME --password YOUR_PASSWORD
```

## How It Works

### Web Scraping Process

1. **Initialize Browser** - Sets up Chrome WebDriver (automatically downloads driver if needed)

2. **Get Song List** - Navigates to the main page and extracts:
   - Track numbers
   - Song titles
   - Edit page URLs
   - Ratings (star counts)
   - Sessions

3. **Get Song Details** - For each song, navigates to edit page and extracts:
   - Session assignment
   - Original song flag
   - Recorded date
   - Uploaded date
   - Instruments and musicians
   - Audio file URL

4. **Extract Comments** - Clicks comment button/link to open popup and extracts:
   - Comment text
   - Comment authors

5. **Download Audio** - Downloads MP3 files to `audio_library/` folder

### Database Insertion

1. **Songs** - Inserts/updates main song record
2. **Sessions** - Creates session records (if new)
3. **Comments** - Adds all comments linked to song
4. **Musicians & Instruments** - Creates musicians and instruments (if new)
5. **Relationships** - Links songs with musicians and instruments

## Important Notes

### HTML Selectors

The scraper uses generic CSS selectors and regex patterns to find elements. **You may need to adjust these** based on the actual HTML structure of the website. To do this:

1. Run with `--no-headless` to see the browser
2. Inspect the HTML elements using browser dev tools
3. Update selectors in `web_scraper.py`:
   - `_parse_song_row()` - Main table parsing
   - `_extract_form_fields()` - Edit page fields
   - `_extract_instruments()` - Instrument/musician data
   - `_extract_comments()` - Comment popup

### Authentication

If the website requires login:
- The `login()` method is implemented but may need adjustment
- Use `--username` and `--password` flags
- Check the login form HTML and update selectors if needed

### Rate Limiting

The scraper includes a 1-second delay between songs to be polite. Adjust if needed in `scrape_all_songs()`.

## Customization

### Selector Examples

If you need to update selectors, here are the key locations:

```python
# In _parse_song_row() - adjust for your table structure
song_rows = soup.find_all('tr', class_='song-row')
title_link = title_cell.find('a')

# In _extract_form_fields() - adjust for form field names
title_input = soup.find('input', {'name': re.compile(r'title', re.I)})
session_select = soup.find('select', {'name': re.compile(r'session', re.I)})

# In _extract_comments() - adjust for comment popup
comment_button = self.driver.find_element(By.CSS_SELECTOR, "a[href*='comment']")
```

### Audio Storage

Audio files are saved to `audio_library/` with filename format: `{song_id}.mp3`

To change storage location, update `audio_dir` in `BigFlavorScraper.__init__()`.

## Database Queries

### Example Queries

```python
from database import DatabaseManager
from scraped_data_manager import ScrapedDataManager

# Setup
db = await DatabaseManager()
await db.connect()
scraper_db = ScrapedDataManager(db)

# Get all sessions
sessions = await scraper_db.get_all_sessions()

# Get songs from a session
songs = await scraper_db.get_session_songs("Full Strength")

# Get top rated songs
top_songs = await scraper_db.get_top_rated_songs(limit=10)

# Get songs by musician
musician_songs = await scraper_db.get_musician_songs("John Doe")

# Get original songs only
originals = await scraper_db.get_original_songs()

# Get song with instruments
song_id = "123"
song = await db.get_song(song_id)
instruments = await scraper_db.get_song_instruments(song_id)
comments = await scraper_db.get_song_comments(song_id)
```

## Troubleshooting

### Chrome Driver Issues

If ChromeDriver fails to download automatically:
1. Manually download from: https://chromedriver.chromium.org/
2. Place in your PATH or project directory
3. Update `Service()` path in `_setup_driver()`

### Element Not Found

If scraper can't find elements:
1. Run with `--no-headless` to see the page
2. Check if page needs JavaScript to load (add waits)
3. Update CSS selectors to match actual HTML

### Database Connection

If database connection fails:
- Verify PostgreSQL is running
- Check credentials in `scrape_and_populate.py`
- Ensure schema is applied with `02-add-song-details.sql`

## Output

The scraper creates:
1. **Database records** - All data inserted into PostgreSQL
2. **Audio files** - Downloaded to `audio_library/`
3. **JSON backup** - `scraped_songs_YYYYMMDD_HHMMSS.json`
4. **Log file** - `scraping.log` with detailed logging

## Next Steps

After scraping:

1. **Verify Data** - Check database for completeness
2. **Audio Analysis** - Run audio analysis on downloaded files
3. **Generate Embeddings** - Create embeddings for RAG
4. **Test Queries** - Use the agent to query scraped data

## Example Complete Workflow

```powershell
# 1. Install dependencies
pip install beautifulsoup4 selenium webdriver-manager requests

# 2. Update database schema
docker exec -i big-flavor-band-agent-postgres-1 psql -U bigflavor -d bigflavor < sql\init\02-add-song-details.sql

# 3. Run scraper (with browser visible for first run)
python scrape_and_populate.py --no-headless

# 4. Check results
python
>>> import asyncio
>>> from database import DatabaseManager
>>> from scraped_data_manager import ScrapedDataManager
>>> 
>>> async def check():
...     db = DatabaseManager()
...     await db.connect()
...     scraper_db = ScrapedDataManager(db)
...     sessions = await scraper_db.get_all_sessions()
...     print(f"Found {len(sessions)} sessions")
...     for session in sessions:
...         print(f"  - {session['name']}: {session['song_count']} songs")
...     await db.close()
>>> 
>>> asyncio.run(check())
```
