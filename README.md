# Big Flavor Band Agent 🎵

AI-powered music discovery and production assistant for the Big Flavor Band's 1,300+ song catalog.

## Architecture

```
┌─────────────────────────────────┐
│     Big Flavor Agent            │
│  (Claude AI + RAG + MCP)        │
└──────┬──────────────────┬───────┘
       │                  │
       │ (direct)         │ (MCP)
       ▼                  ▼
┌─────────────┐     ┌──────────────┐
│ RAG System  │     │Production MCP│
│  (Search)   │     │   Server     │
└─────────────┘     └──────────────┘
```

### Components

- **Agent** (`src/agent/`) - Claude AI orchestration
- **RAG System** (`src/rag/`) - Semantic search library
- **MCP Server** (`src/mcp/`) - Audio production tools
- **Database** (`database/`) - PostgreSQL with pgvector

## Quick Start

### 1. Setup Environment

```powershell
# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r setup/requirements.txt
```

### 2. Configure Database

```powershell
# Run database setup
.\database\setup-database.ps1

# Apply schema
python database/apply_schema.py
```

### 3. Set API Key

```powershell
# Create .env file
echo "ANTHROPIC_API_KEY=your-key-here" > .env
```

### 4. Run the Agent

```powershell
python run_agent.py
```

## Project Structure

```
big-flavor-band-agent/
├── run_agent.py                 # Main entry point
├── src/
│   ├── agent/
│   │   ├── __init__.py
│   │   └── big_flavor_agent.py  # Claude AI agent
│   ├── rag/
│   │   ├── __init__.py
│   │   └── big_flavor_rag.py    # RAG search system
│   └── mcp/
│       ├── __init__.py
│       └── big_flavor_mcp.py    # Audio production MCP server
├── database/
│   ├── database.py              # Database manager
│   ├── apply_schema.py          # Schema application
│   ├── setup-database.ps1       # Setup script
│   └── sql/                     # SQL schemas
├── setup/
│   ├── requirements.txt         # Python dependencies
│   ├── config.json              # Configuration
│   └── setup*.ps1               # Setup scripts
├── audio_library/               # Audio files (indexed)
├── docs/                        # Documentation
└── tests/                       # Test files
```

## Features

### Search Tools (RAG System)
- 🎵 **Audio Similarity** - Find songs that sound similar
- 📝 **Text Search** - Natural language queries
- 🎼 **Tempo Search** - Find songs by BPM
- 🔀 **Hybrid Search** - Combine multiple criteria

### Production Tools (MCP Server)
- 🔍 **Analyze Audio** - Extract tempo, key, beats
- ⏱️ **Match Tempo** - Time-stretch without pitch change
- 🎚️ **Create Transitions** - Beat-matched DJ mixes
- 🎛️ **Apply Mastering** - Professional audio mastering

## Usage Examples

```python
# Search for similar songs
"Find songs that sound like my-track.mp3"

# Natural language search
"Find calm ambient sleep music"

# Tempo-based search
"Find songs between 120-130 BPM"

# Audio production
"Analyze the tempo of song.mp3"
"Make this song 128 BPM"
"Create a DJ transition from song1.mp3 to song2.mp3"
```

## Development

### Running Tests

```powershell
python tests/test_agent.py
python tests/test_rag.py
python tests/test_mcp.py
```

### Adding New Search Methods

Edit `src/rag/big_flavor_rag.py` and add methods to `SongRAGSystem` class.

### Adding New Production Tools

Edit `src/mcp/big_flavor_mcp.py` and add tools to `BigFlavorMCPServer` class.

## Documentation

See `docs/` directory for detailed documentation:
- `SIMPLIFIED_ARCHITECTURE.md` - Architecture overview
- `TOOL_ROUTING_GUIDE.md` - Tool usage guide
- Setup guides and more

## Requirements

- Python 3.8+
- PostgreSQL with pgvector extension
- Anthropic API key
- ~2GB disk space for audio library

## License

See LICENSE file for details.

## Support

For issues or questions, see documentation in `docs/` directory.

---

**Note**: This is a refactored, clean architecture with proper separation of concerns:
- Search operations use RAG system library directly (fast!)
- Production operations use MCP server (isolated process)
- Agent orchestrates both seamlessly
