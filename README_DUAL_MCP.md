# Big Flavor Band Agent - Dual MCP Architecture

## 🎵 What's New?

The Big Flavor Band Agent now uses a **dual MCP server architecture** that cleanly separates search/retrieval operations from production/modification operations, following MCP best practices.

## 🏗️ Architecture Overview

```
┌─────────────────────────────────┐
│      Claude AI Agent            │
│  (Natural Language Interface)   │
└──────────┬──────────────────────┘
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌───────┐    ┌────────┐
│ RAG   │    │  MCP   │
│Server │    │ Server │
└───────┘    └────────┘
   READ         WRITE
  SEARCH      PRODUCE
```

### RAG Server 🔍
Handles all **search and retrieval** operations:
- Find songs by audio similarity
- Search by text descriptions
- Filter by tempo/BPM
- Hybrid multi-criteria search

### Production Server 🎛️
Handles all **audio production** operations:
- Analyze audio (BPM, key, beats)
- Match tempo (time-stretching)
- Create transitions (DJ mixing)
- Apply mastering (loudness, compression)

## 🚀 Quick Start

### Option 1: Use the Integrated Agent (Recommended)

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY="your-key-here"

# Run the agent
python claude_dual_mcp_agent.py
```

Then chat naturally:
```
You: Find calm sleep music
Assistant: [searches RAG server and returns results]

You: Make this song 120 BPM
Assistant: [uses production server to time-stretch]
```

### Option 2: Run Servers Independently

```bash
# Terminal 1: Start RAG server
python rag_mcp_server.py

# Terminal 2: Start Production server
python mcp_server_new.py

# Terminal 3: Use your own client
# Connect to both servers via MCP protocol
```

## 📚 Documentation

- **[Dual MCP Architecture](docs/DUAL_MCP_ARCHITECTURE.md)** - Complete architecture guide
- **[Tool Routing Guide](docs/TOOL_ROUTING_GUIDE.md)** - Which server handles what
- **[Refactoring Complete](docs/REFACTORING_COMPLETE.md)** - Summary of changes

## 🛠️ Available Tools

### RAG Server Tools (Search/Read)

| Tool | Description |
|------|-------------|
| `search_by_audio_file` | Find songs similar to an audio file |
| `search_by_text_description` | Natural language music search |
| `search_by_tempo_range` | Find songs by BPM range |
| `search_hybrid` | Multi-criteria search (audio + text + tempo) |

### Production Server Tools (Write/Modify)

| Tool | Description |
|------|-------------|
| `analyze_audio` | Extract tempo, key, beats, energy |
| `match_tempo` | Time-stretch to target BPM (pitch-preserving) |
| `create_transition` | Create beat-matched DJ transitions |
| `apply_mastering` | Professional mastering (compression, limiting) |

## 💡 Usage Examples

### Finding Music

```python
# Natural language search
"Find calm ambient music for sleeping"
→ Uses: search_by_text_description

# Audio similarity
"Find songs that sound like my-track.mp3"
→ Uses: search_by_audio_file

# Tempo-based
"Find songs between 120-130 BPM"
→ Uses: search_by_tempo_range

# Complex search
"Find upbeat rock songs around 140 BPM"
→ Uses: search_hybrid
```

### Audio Production

```python
# Analyze a file
"What's the tempo and key of this song?"
→ Uses: analyze_audio

# Change tempo
"Make this song 128 BPM without changing pitch"
→ Uses: match_tempo

# DJ mixing
"Create a smooth transition from song1 to song2"
→ Uses: create_transition

# Mastering
"Master this track to -14 LUFS"
→ Uses: apply_mastering
```

## 🧪 Testing

Run the test suite to verify everything works:

```bash
python test_dual_mcp.py
```

This will test:
- ✅ RAG server search capabilities
- ✅ Production server audio operations
- ✅ Agent orchestration and routing

## 📦 Installation

### Prerequisites

```bash
# Python 3.8+
python --version

# Install dependencies
pip install -r requirements.txt

# PostgreSQL with pgvector extension
# See DATABASE_SETUP.md for details
```

### Environment Setup

```bash
# Copy example env file
cp .env.example .env

# Edit .env and set:
# - ANTHROPIC_API_KEY
# - Database connection settings
```

## 🔧 Configuration

### RAG Server

Configure in `rag_mcp_server.py`:
- `use_clap`: Enable CLAP audio embeddings (default: True)
- Database connection via `DatabaseManager`

### Production Server

Configure in `mcp_server_new.py`:
- `enable_audio_analysis`: Enable audio analysis cache (default: True)

## 📁 Project Structure

```
big-flavor-band-agent/
├── claude_dual_mcp_agent.py    # Main agent (orchestrator)
├── rag_mcp_server.py           # RAG/search server
├── mcp_server_new.py           # Production server
├── rag_system.py               # RAG implementation
├── database.py                 # Database manager
├── test_dual_mcp.py            # Test suite
├── docs/
│   ├── DUAL_MCP_ARCHITECTURE.md
│   ├── TOOL_ROUTING_GUIDE.md
│   └── REFACTORING_COMPLETE.md
└── [legacy files preserved]
```

## 🎯 Key Benefits

1. **Clean Separation**: Read vs Write operations clearly separated
2. **MCP Best Practices**: Follows recommended architecture patterns
3. **Scalability**: Each server scales independently
4. **Flexibility**: Easy to add new tools
5. **Maintainability**: Clear boundaries between concerns

## 🔄 Migration from Old Architecture

The original `mcp_server.py` and `claude_mcp_agent.py` are preserved for reference.

**Changes:**
- Search tools → Moved to `rag_mcp_server.py`
- Production tools → Moved to `mcp_server_new.py`
- Agent → Updated to `claude_dual_mcp_agent.py` with routing

All functionality is maintained, just better organized!

## 🐛 Troubleshooting

### RAG Server Issues
- Ensure PostgreSQL with pgvector is running
- Check audio embeddings are indexed
- Verify database connection settings

### Production Server Issues
- Install librosa: `pip install librosa soundfile`
- Check disk space for output files
- Verify audio file format compatibility

### Agent Issues
- Set ANTHROPIC_API_KEY environment variable
- Ensure both servers are accessible
- Check conversation history for errors

## 📊 Performance

- **RAG Server**: Uses pgvector for fast similarity search (milliseconds)
- **Production Server**: Audio processing is CPU-intensive (seconds to minutes)
- **Caching**: Audio analysis results cached to avoid recomputation
- **Connection Pooling**: Database connections pooled for efficiency

## 🤝 Contributing

We welcome contributions! Areas for enhancement:
- Additional search algorithms
- More audio production tools
- Performance optimizations
- UI/web interface
- Mobile app integration

## 📄 License

See LICENSE file for details.

## 🔗 Related Projects

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [pgvector](https://github.com/pgvector/pgvector)
- [librosa](https://librosa.org/)
- [Claude AI](https://www.anthropic.com/claude)

## 📞 Support

For issues, questions, or contributions:
- Check the documentation in `docs/`
- Review test suite: `test_dual_mcp.py`
- See troubleshooting guide above

---

**Note**: This is a refactored architecture that separates concerns following MCP best practices. The original files are preserved for reference.
