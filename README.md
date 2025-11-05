# Big Flavor Band AI Agent

An AI-powered agent for managing the Big Flavor band's song library, with capabilities for song recommendations, album curation, and audio engineering assistance.

## 🎸 Features

- **Real Song Library**: Access to **1,452 real songs** from bigflavorband.com via RSS feed
- **Smart Song Recommendations**: Get suggestions for what song to play next based on tempo, key, mood, and energy
- **Album Curation**: Automatically create album suggestions from your song library with optimal track ordering
- **Setlist Generation**: Create performance setlists with customizable energy flow patterns
- **Audio Engineering Assistance**: Get professional audio engineering suggestions to improve recording quality
- **Flow Analysis**: Analyze how well songs transition together in albums or setlists
- **MCP Server Integration**: Built with Model Context Protocol for AI agent connectivity
- **Intelligent Metadata**: Automatically infers genre, mood, and tags from song titles and sessions

## 📁 Project Structure

```
big-flavor-band-agent/
├── agent.py                    # Main AI agent
├── mcp_server.py              # MCP server for song library management
├── recommendation_engine.py   # Song recommendation logic
├── album_curator.py           # Album and setlist curation
├── audio_analyzer.py          # Audio engineering analysis
├── requirements.txt           # Python dependencies
├── config.json               # Configuration file
└── README.md                 # This file
```

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)

### Installation

1. Clone or download this repository

2. Install dependencies:
```powershell
pip install -r requirements.txt
```

3. Configure the agent (optional):
Edit `config.json` to customize settings like the website URL and cache settings.

### Running the Agent

#### Demo Mode (Recommended for Learning)

Run the agent in demo mode to see all features:

```powershell
python agent.py
```

This will demonstrate:
- Song recommendations
- Album creation
- Audio engineering analysis
- Setlist generation

#### MCP Server Mode

To run the MCP server for integration with other AI systems:

```powershell
python mcp_server.py
```

The server exposes tools for:
- `get_song_library` - Fetch complete song library
- `search_songs` - Search by title, genre, or mood
- `get_song_details` - Get detailed song information
- `filter_songs_by_genre` - Filter by genre(s)
- `filter_songs_by_tempo` - Filter by tempo range
- `analyze_song_metadata` - Analyze song characteristics

## 💡 Usage Examples

### Get Next Song Suggestion

```python
from agent import BigFlavorAgent

agent = BigFlavorAgent()
await agent.initialize()

# Suggest next song after current song
suggestion = await agent.suggest_next_song(
    current_song_id="song_001",
    mood="upbeat",
    energy="high"
)
print(suggestion)
```

### Create an Album

```python
# Create a themed album
album = await agent.create_album_suggestion(
    theme="upbeat rock",
    target_duration_minutes=45
)
print(f"Album: {album['album_name']}")
print(f"Tracks: {len(album['tracks'])}")
```

### Get Audio Engineering Suggestions

```python
# Get suggestions for improving a song
suggestions = await agent.get_audio_engineering_suggestions("song_002")
print(suggestions['improvement_suggestions'])
```

### Generate a Setlist

```python
# Create a setlist for a gig
setlist = await agent.suggest_setlist(
    duration_minutes=60,
    energy_flow="building"  # Options: varied, building, consistent
)
print(f"Setlist: {setlist['setlist_name']}")
```

## 🔧 Configuration

Edit `config.json` to customize:

- `website_url`: Your band's website URL
- `cache_duration`: How long to cache song library data (in seconds)
- `default_album_duration`: Default target album duration (minutes)
- `default_setlist_duration`: Default setlist duration (minutes)

## 📊 Song Data Format

Songs in the library should include:

```json
{
  "id": "unique_song_id",
  "title": "Song Title",
  "genre": "Rock",
  "tempo_bpm": 128,
  "key": "C Major",
  "duration_seconds": 245,
  "energy": "high",
  "mood": "upbeat",
  "tags": ["tag1", "tag2"],
  "recording_date": "2024-06-15",
  "audio_quality": "good"
}
```

## 🌐 RSS Feed Integration - LIVE DATA! 🎉

**The MCP Server now uses REAL songs from bigflavorband.com!**

### ✅ What's Included

- **1,452 real songs** fetched from https://bigflavorband.com/rss
- **Automatic metadata parsing** including:
  - Song titles and variants
  - Recording sessions (e.g., "Kevin's Bar+Cart Birthday Bash", "Broken Pitchfork Retreat")
  - Direct MP3 download links
  - Publication dates
  - Inferred genres and moods
  - Auto-generated tags for instruments and styles

### Testing the RSS Integration

Run the test script to see real songs in action:

```powershell
python test_rss_parser.py
```

This will display:
- Total songs fetched from the RSS feed
- Sample songs with full metadata
- Search functionality demo
- Genre filtering demo

### How It Works

The MCP server:
1. Fetches the RSS feed from bigflavorband.com
2. Parses XML to extract song information
3. Infers genres based on keywords (Rock, Blues, Jazz, Acoustic/Folk)
4. Determines moods from song titles (melancholic, upbeat, energetic, romantic, reflective)
5. Generates tags from instruments mentioned (guitar, piano, drums, vocals, etc.)
6. Caches results for performance

### Example Real Songs

- "So Tired" - 45+ variations across different sessions
- "Here Comes a Regular" - Multiple live and studio versions
- "Hallelujah" - Various performer arrangements
- "This Year" - Different interpretations and sessions
- "Rock and Roll" - Live recordings and studio takes

For more details, see [RSS_UPDATE.md](./RSS_UPDATE.md)

## 🎵 Features in Detail

### Recommendation Engine

Uses multiple factors to suggest songs:
- **Tempo compatibility**: Prefers songs within 20 BPM
- **Key compatibility**: Based on circle of fifths
- **Genre matching**: Similar styles flow better
- **Mood alignment**: Matches desired emotional tone
- **Energy levels**: Maintains or shifts energy as desired

### Album Curator

Creates coherent albums by:
- Filtering songs by theme
- Selecting optimal duration
- Ordering tracks for flow
- Balancing energy throughout
- Analyzing transitions between songs

### Audio Analyzer

Provides engineering guidance:
- Genre-specific mixing suggestions
- Mood-based effect recommendations
- Tempo-appropriate processing
- Quality assessment and improvement potential
- Comparison across multiple songs

## 🤝 Contributing to Your Library

To add new songs to your library:

1. Add song metadata to the website/database
2. Include all required fields (id, title, genre, tempo, etc.)
3. The agent will automatically include them in recommendations

## 📝 Todos & Future Enhancements

- [ ] Implement actual web scraping for bigflavorband.com
- [ ] Add Spotify/Apple Music integration for broader recommendations
- [ ] Implement actual audio file analysis (librosa, pydub)
- [ ] Add machine learning for improved recommendations
- [ ] Create web UI for easier interaction
- [ ] Add collaborative filtering based on listener preferences
- [ ] Implement automatic key and tempo detection
- [ ] Add support for multiple band profiles

## 🎓 Learning Resources

This project demonstrates:
- **MCP (Model Context Protocol)**: Building AI agent servers
- **Async Python**: Using asyncio for concurrent operations
- **Music Theory**: Key compatibility, tempo, and flow
- **Audio Engineering**: Mixing and mastering concepts
- **Recommendation Systems**: Scoring and ranking algorithms

## 🐛 Troubleshooting

### Import Errors
Make sure all dependencies are installed:
```powershell
pip install -r requirements.txt
```

### MCP Server Not Connecting
Ensure the server is running and check the logs for errors.

### No Songs Found
If using the demo, mock data should load automatically. Check that `_get_mock_songs()` is working.

## 📄 License

See LICENSE file for details.

## 🎸 About Big Flavor

Big Flavor is a band of dads who love playing music together. We might not be the best musicians, but we have fun, and that's what counts! This AI agent helps us organize our songs and improve our sound quality.

Rock on! 🤘

---

**Built with ❤️ by dad rockers, for dad rockers**
