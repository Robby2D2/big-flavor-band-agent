# Getting Started with Your Big Flavor Band AI Agent

Hey there! Welcome to your new AI agent project. Here's everything you need to know to get started.

## 🚀 First Steps (Do This First!)

### 1. Install Dependencies

Open PowerShell in this directory and run:

```powershell
.\setup.ps1
```

Or manually:

```powershell
pip install -r requirements.txt
```

### 2. Test the Installation

```powershell
python test_install.py
```

This will verify everything is working correctly.

### 3. Try the Interactive Demo

```powershell
python example.py
```

This runs through all features with sample data.

## 🎮 Ways to Use the Agent

### Option 1: Interactive CLI (Easiest!)

```powershell
python cli.py
```

This gives you a menu-driven interface to explore all features:
- Get song recommendations
- Create albums
- Generate setlists
- Get audio engineering advice
- And more!

### Option 2: Run the Demo Script

```powershell
python example.py
```

Shows all features in action with explanations.

### Option 3: Python Code

Create your own scripts:

```python
import asyncio
from agent import BigFlavorAgent

async def main():
    agent = BigFlavorAgent()
    await agent.initialize()
    
    # Get a recommendation
    result = await agent.suggest_next_song(mood="upbeat")
    print(result)

asyncio.run(main())
```

### Option 4: MCP Server (Advanced)

```powershell
python mcp_server.py
```

This starts the Model Context Protocol server for AI agent integration.

## 📁 What's What?

### Core Files (The Important Stuff)

- **agent.py** - The main AI agent that orchestrates everything
- **mcp_server.py** - MCP server for song library management
- **recommendation_engine.py** - Smart song recommendations
- **album_curator.py** - Album creation and setlist generation
- **audio_analyzer.py** - Audio quality analysis and suggestions

### Helper Files

- **cli.py** - Interactive menu interface (try this first!)
- **example.py** - Comprehensive demo of all features
- **test_install.py** - Verify your installation works

### Configuration & Docs

- **config.json** - Settings you can customize
- **requirements.txt** - Python packages needed
- **README.md** - Full documentation
- **QUICKSTART.md** - Quick reference guide
- **PROJECT_OVERVIEW.md** - Deep dive into the project
- **GETTING_STARTED.md** - This file!

## 🎵 Understanding the Song Data

Right now, the agent uses 5 sample songs as mock data:

1. **Summer Groove** - Upbeat rock (128 BPM)
2. **Midnight Blues** - Melancholic blues (88 BPM)
3. **Weekend Warrior** - Energetic rock (145 BPM)
4. **Coffee Shop Serenade** - Relaxed acoustic (102 BPM)
5. **Dad Rock Anthem** - Fun rock (132 BPM)

Each song has metadata like:
- Genre (Rock, Blues, Acoustic)
- Tempo (BPM)
- Key (C Major, E Minor, etc.)
- Energy (low, medium, high)
- Mood (upbeat, melancholic, relaxed, etc.)
- Audio quality (excellent, good, fair, poor)

## 🌐 Connecting to Your Real Website

To use actual data from bigflavorband.com:

1. Open `mcp_server.py`
2. Find the `get_song_library()` method (around line 165)
3. Replace the mock data logic with actual web scraping:

```python
async def get_song_library(self):
    async with httpx.AsyncClient() as client:
        response = await client.get(self.base_url)
        # Parse your website here
        # Extract song information
        # Return formatted song data
```

You might want to use BeautifulSoup for HTML parsing:
```powershell
pip install beautifulsoup4
```

## 🎯 Quick Wins

Here are some cool things to try right away:

### 1. Get a Song Recommendation

```powershell
python cli.py
# Choose option 1
```

### 2. Create an Album

```powershell
python cli.py
# Choose option 3
# Try theme: "rock"
```

### 3. Generate a Setlist for Your Next Gig

```powershell
python cli.py
# Choose option 7
# Duration: 60 minutes
# Energy flow: Building
```

### 4. Get Audio Improvement Tips

```powershell
python cli.py
# Choose option 5
# Pick a song
```

## 🛠️ Customizing for Your Band

### Change Default Settings

Edit `config.json`:

```json
{
  "website_url": "https://bigflavorband.com",
  "default_album_duration_minutes": 45,
  "default_setlist_duration_minutes": 60
}
```

### Add Your Real Songs

Update the mock data in `mcp_server.py` (line 297) or implement web scraping.

### Adjust Recommendation Weights

In `config.json`, change the `recommendation_weights` section to emphasize different factors.

## 🐛 Troubleshooting

### "Module not found" Error

```powershell
pip install -r requirements.txt
```

### "mcp module not found" Error

```powershell
pip install mcp
```

### Program Crashes

Run the test script to diagnose:
```powershell
python test_install.py
```

### Want to Start Fresh?

Delete `__pycache__` folders and reinstall:
```powershell
Remove-Item -Recurse -Force __pycache__
pip install -r requirements.txt
```

## 📚 Learning Path

### Beginner Path
1. ✅ Run `setup.ps1`
2. ✅ Try `cli.py` to explore features
3. ✅ Read through `README.md`
4. ✅ Modify `config.json` settings
5. ✅ Add your own song data

### Intermediate Path
1. ✅ Study `recommendation_engine.py` - understand scoring
2. ✅ Modify `album_curator.py` - customize curation
3. ✅ Enhance `audio_analyzer.py` - add new suggestions
4. ✅ Create custom scripts using `agent.py`

### Advanced Path
1. ✅ Implement real web scraping in `mcp_server.py`
2. ✅ Add new MCP tools for additional features
3. ✅ Integrate with external APIs (Spotify, etc.)
4. ✅ Add machine learning for better recommendations
5. ✅ Create a web UI

## 🎸 Next Steps

After you're comfortable with the basics:

1. **Customize the mock songs** to match your actual library
2. **Implement web scraping** for bigflavorband.com
3. **Add more songs** to the library
4. **Create custom playlists** for different occasions
5. **Share with your bandmates** and get feedback
6. **Extend with new features** you want

## 💡 Project Ideas

Here are some cool extensions you could build:

- **Practice Scheduler**: Suggest which songs to practice based on upcoming gigs
- **Gear Recommendations**: Suggest equipment based on song characteristics
- **Lyrics Manager**: Organize and search song lyrics
- **Video Link Organizer**: Manage links to performance videos
- **Fan Interaction**: Let fans vote on setlists
- **Song History**: Track which songs you play most often

## 🤝 Getting Help

If you get stuck:

1. Check the error message carefully
2. Run `python test_install.py` to verify setup
3. Review the relevant `.py` file's comments
4. Check `README.md` for detailed documentation
5. Look at `example.py` for usage patterns

## 🎉 Have Fun!

This project is meant to be:
- **Useful** for managing your band
- **Educational** for learning Python and AI
- **Fun** to customize and extend

Don't be afraid to experiment! You can't break anything - it's just code.

## 🎵 The Big Flavor Attitude

Remember: You're doing this for fun and learning. The goal isn't perfection - it's progress. Just like your band - you might not be the best musicians, but you're having a great time and getting better!

**Rock on and happy coding!** 🎸🤘

---

*Built with ❤️ by a dad who codes*
