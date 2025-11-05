# Big Flavor Band AI Agent - Project Overview

## 🎯 Project Goals

This project creates an AI-powered assistant for the Big Flavor band to:

1. **Manage Song Library** - Organize and access songs from bigflavorband.com
2. **Recommend Songs** - Suggest what to play next based on musical compatibility
3. **Curate Albums** - Automatically create cohesive album suggestions
4. **Generate Setlists** - Build performance setlists with optimal energy flow
5. **Improve Audio Quality** - Provide professional audio engineering guidance
6. **Learn MCP** - Demonstrate Model Context Protocol for AI agent development

## 📐 Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│                    AI Agent (agent.py)                   │
│  Main orchestrator for all band management features     │
└────────┬────────────────────────────────────────────────┘
         │
         ├──► Recommendation Engine (recommendation_engine.py)
         │    • Song similarity scoring
         │    • Next song suggestions
         │    • Musical compatibility analysis
         │
         ├──► Album Curator (album_curator.py)
         │    • Album creation and ordering
         │    • Flow analysis
         │    • Setlist generation
         │
         └──► Audio Analyzer (audio_analyzer.py)
              • Quality assessment
              • Engineering suggestions
              • Batch comparisons

┌─────────────────────────────────────────────────────────┐
│              MCP Server (mcp_server.py)                  │
│  Exposes song library tools via Model Context Protocol  │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Song Library** → MCP Server exposes tools to query songs
2. **Agent** → Uses recommendation engine, curator, and analyzer
3. **User/AI** → Interacts with agent or MCP server
4. **Results** → JSON-formatted recommendations and analyses

## 🔑 Key Features

### 1. Song Recommendations

**Algorithm**: Multi-factor scoring system

- **Tempo Compatibility** (20 points): Songs within 20 BPM score higher
- **Key Compatibility** (25 points): Based on circle of fifths
- **Genre Match** (15 points): Same genre flows better
- **Mood Preference** (30 points): Match desired emotional tone
- **Energy Preference** (30 points): Maintain or shift energy
- **Audio Quality** (10 points): Slight preference for better recordings

**Use Cases**:
- "What should we play after this song?"
- "Find songs similar to X"
- "Suggest an upbeat song"

### 2. Album Curation

**Strategy**: Theme-based selection with optimal ordering

- Filter songs by theme keywords
- Select songs to match target duration
- Order tracks for energy flow variation
- Analyze transitions between songs
- Generate curation notes

**Use Cases**:
- "Create a 45-minute rock album"
- "How well do these songs flow together?"
- "Build an album around a theme"

### 3. Setlist Generation

**Strategy**: Energy flow patterns for live performance

- **Building**: Start mellow, build to high energy
- **Consistent**: Maintain steady energy level
- **Varied**: Mix energy levels for dynamic show

**Use Cases**:
- "Create a 60-minute setlist"
- "Build an opening set"
- "Plan encore songs"

### 4. Audio Engineering Analysis

**Features**:
- Quality assessment (excellent/good/fair/poor)
- Genre-specific mixing suggestions
- Mood-based effects recommendations
- Tempo-appropriate processing
- Priority action items
- Batch comparison

**Use Cases**:
- "How can we improve this recording?"
- "Compare quality across our songs"
- "What should we focus on in mixing?"

## 🎼 Music Theory Integration

### Key Compatibility (Circle of Fifths)

The system understands musical key relationships:
- Compatible keys transition smoothly
- Major/minor relationships preserved
- Modulation suggestions based on theory

### Tempo Analysis

- **Slow** (<80 BPM): Ballads, emotional pieces
- **Moderate** (80-120 BPM): Standard rock, blues
- **Upbeat** (120-160 BPM): Energetic rock
- **Fast** (>160 BPM): High-energy performances

### Energy Flow Patterns

- **High → High**: Maintains excitement
- **High → Medium**: Natural wind-down
- **High → Low**: Abrupt shift (flagged in analysis)
- **Low → High**: Building energy

## 🛠️ Technical Details

### Technologies Used

- **Python 3.10+**: Modern async/await patterns
- **MCP (Model Context Protocol)**: AI agent communication standard
- **httpx**: Async HTTP client for web requests
- **asyncio**: Concurrent operation handling

### File Structure

```
big-flavor-band-agent/
├── agent.py                    # Main AI agent orchestrator
├── mcp_server.py              # MCP server implementation
├── recommendation_engine.py   # Song recommendation logic
├── album_curator.py           # Album and setlist creation
├── audio_analyzer.py          # Audio quality analysis
├── config.json                # Configuration settings
├── requirements.txt           # Python dependencies
├── README.md                  # Main documentation
├── QUICKSTART.md              # Quick start guide
├── PROJECT_OVERVIEW.md        # This file
├── example.py                 # Comprehensive demo script
├── test_install.py            # Installation test suite
├── setup.ps1                  # Windows setup script
├── .gitignore                 # Git ignore rules
└── LICENSE                    # Project license
```

### Configuration Options

Edit `config.json` to customize:

```json
{
  "website_url": "https://bigflavorband.com",
  "cache_duration_seconds": 3600,
  "default_album_duration_minutes": 45,
  "recommendation_weights": {
    "tempo_compatibility": 20,
    "key_compatibility": 25,
    // ... more weights
  }
}
```

## 🔄 Extending the System

### Adding New Song Data Sources

1. **Web Scraping**: Parse bigflavorband.com HTML
   ```python
   from bs4 import BeautifulSoup
   # Parse song data from website
   ```

2. **REST API**: Connect to music API
   ```python
   async with httpx.AsyncClient() as client:
       response = await client.get(api_url)
       songs = response.json()
   ```

3. **Database**: Direct database connection
   ```python
   import sqlite3
   # Query song database
   ```

### Adding New MCP Tools

1. Define tool schema in `mcp_server.py`:
   ```python
   Tool(
       name="your_tool_name",
       description="What your tool does",
       inputSchema={...}
   )
   ```

2. Implement handler in `call_tool()` method

3. Add corresponding method to fetch/process data

### Adding New Analysis Features

1. Add method to appropriate module
2. Update agent.py to expose the feature
3. Document in README.md
4. Add example to example.py

## 🎓 Learning Opportunities

This project demonstrates:

### 1. AI Agent Development
- MCP server implementation
- Tool-based architecture
- Async Python patterns

### 2. Music Information Retrieval
- Metadata analysis
- Similarity scoring
- Flow optimization

### 3. Recommendation Systems
- Multi-factor scoring
- Preference weighting
- Similarity algorithms

### 4. Audio Engineering Concepts
- Quality assessment
- Genre-specific processing
- Mixing and mastering basics

### 5. Python Best Practices
- Type hints and documentation
- Async/await patterns
- Module organization
- Error handling

## 🚀 Future Enhancement Ideas

### Short Term
- [ ] Real web scraping for bigflavorband.com
- [ ] Persistent song library caching
- [ ] Export playlists to Spotify/Apple Music
- [ ] Web UI for easier interaction

### Medium Term
- [ ] Actual audio file analysis (librosa)
- [ ] Machine learning for personalized recommendations
- [ ] Collaborative filtering based on listener data
- [ ] Automatic key/tempo detection from audio files

### Long Term
- [ ] Multi-band support
- [ ] Social features (share recommendations)
- [ ] Integration with DAWs (Digital Audio Workstations)
- [ ] AI-powered mixing suggestions with audio processing
- [ ] Mobile app for band members

## 📊 Success Metrics

- ✅ All core features functional (recommendations, albums, setlists, audio analysis)
- ✅ MCP server exposing 6+ tools
- ✅ Comprehensive documentation
- ✅ Working demo script
- ✅ Test suite for verification

## 🎸 Band Context

**Big Flavor** is a band of four dads who:
- Enjoy playing music together
- Are honest about their skill level ("not that great")
- Want to improve their recordings
- Need help organizing their growing song library
- Are interested in learning about AI and software development

This project serves dual purposes:
1. **Practical**: Actually helps manage the band's music
2. **Educational**: Teaches AI agent development and MCP

## 📚 Additional Resources

- [Model Context Protocol Docs](https://modelcontextprotocol.io/)
- [Music Theory Basics](https://www.musictheory.net/)
- [Audio Engineering Fundamentals](https://www.soundonsound.com/)
- [Python Async/Await Guide](https://docs.python.org/3/library/asyncio.html)

## 🤝 Contributing

To contribute to this project:

1. Add new features to appropriate modules
2. Update documentation
3. Add tests to test_install.py
4. Update example.py with demos
5. Keep code well-commented

## 📝 Notes for Development

- Use mock data for testing before implementing web scraping
- Keep the agent stateless for easier testing
- Document all scoring algorithms
- Provide reasoning with all recommendations
- Make the system extensible for future features

---

**Built by dad rockers, for dad rockers** 🎸

*"We may not be the best musicians, but we can write a mean Python script!"*
