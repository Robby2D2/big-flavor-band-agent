# Big Flavor Band Agent - Quick Start Guide

## Installation & Setup

### Step 1: Install Python Dependencies

```powershell
pip install -r requirements.txt
```

If you encounter any issues, try upgrading pip first:
```powershell
python -m pip install --upgrade pip
```

### Step 2: Verify Installation

Run the agent in demo mode:
```powershell
python agent.py
```

You should see output showing:
- Song recommendations
- Album suggestions
- Audio engineering analysis
- Setlist generation

## MCP Server Setup

The MCP (Model Context Protocol) server allows AI agents to access the song library.

### Running the MCP Server

```powershell
python mcp_server.py
```

The server will start and listen for MCP requests via stdio.

### Available MCP Tools

1. **get_song_library** - Fetch all songs
2. **search_songs** - Search by query
3. **get_song_details** - Get specific song info
4. **filter_songs_by_genre** - Filter by genre(s)
5. **filter_songs_by_tempo** - Filter by BPM range
6. **analyze_song_metadata** - Analyze song characteristics

## Common Use Cases

### 1. Get Next Song Recommendation

```python
import asyncio
from agent import BigFlavorAgent

async def main():
    agent = BigFlavorAgent()
    await agent.initialize()
    
    # Get suggestion for next song
    result = await agent.suggest_next_song(
        current_song_id="song_001",
        mood="upbeat"
    )
    print(result)

asyncio.run(main())
```

### 2. Create an Album

```python
async def create_album():
    agent = BigFlavorAgent()
    await agent.initialize()
    
    album = await agent.create_album_suggestion(
        theme="rock",
        target_duration_minutes=40
    )
    
    print(f"Album: {album['album_name']}")
    for track in album['tracks']:
        print(f"{track['track_number']}. {track['title']}")

asyncio.run(create_album())
```

### 3. Get Audio Improvement Suggestions

```python
async def improve_audio():
    agent = BigFlavorAgent()
    await agent.initialize()
    
    suggestions = await agent.get_audio_engineering_suggestions("song_002")
    
    print("Mixing Suggestions:")
    for suggestion in suggestions['improvement_suggestions']['mixing']:
        print(f"  - {suggestion}")

asyncio.run(improve_audio())
```

### 4. Generate a Setlist

```python
async def create_setlist():
    agent = BigFlavorAgent()
    await agent.initialize()
    
    setlist = await agent.suggest_setlist(
        duration_minutes=45,
        energy_flow="building"
    )
    
    print(f"Setlist: {setlist['setlist_name']}")
    for song in setlist['songs']:
        print(f"{song['position']}. {song['title']} - {song['performance_notes']}")

asyncio.run(create_setlist())
```

## Configuration

Edit `config.json` to customize:

- Website URL
- Cache duration
- Recommendation weights
- Default durations

## Integrating Real Data

To use real data from bigflavorband.com instead of mock data:

1. Open `mcp_server.py`
2. Find the `get_song_library()` method
3. Replace the mock data logic with actual web scraping or API calls
4. Use libraries like BeautifulSoup for HTML parsing:

```python
from bs4 import BeautifulSoup

async def get_song_library(self):
    async with httpx.AsyncClient() as client:
        response = await client.get(self.base_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Parse your website's song data here
        songs = []
        # ... parsing logic ...
        
        return {"songs": songs}
```

## Troubleshooting

### "Module not found" errors
```powershell
pip install mcp httpx
```

### Async errors
Make sure you're using `asyncio.run()` or `await` inside async functions.

### No songs found
The demo uses mock data. To add real songs, update the MCP server's data fetching logic.

## Next Steps

1. ✅ Run the demo to see features
2. 📝 Customize `config.json` for your preferences
3. 🌐 Integrate with your actual website data
4. 🎵 Add your real song metadata
5. 🚀 Build custom features for your band's needs

## Support

For issues or questions:
- Check the main README.md for detailed documentation
- Review the code comments in each module
- Experiment with the demo mode to understand functionality

Happy coding and rock on! 🎸
