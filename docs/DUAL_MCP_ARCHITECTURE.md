# Dual MCP Architecture

## Overview

The Big Flavor Band Agent now uses a **dual MCP server architecture** that cleanly separates concerns:

- **RAG Server** (`rag_mcp_server.py`): Handles all READ/SEARCH/RETRIEVAL operations
- **Production Server** (`mcp_server_new.py`): Handles all WRITE/PRODUCTION/MODIFICATION operations

This architecture follows MCP best practices where the RAG system handles retrieval and the MCP server handles production operations.

## Architecture Components

### 1. RAG MCP Server (`rag_mcp_server.py`)

**Purpose**: Search and retrieval using semantic embeddings

**Tools**:
- `search_by_audio_file` - Find songs similar to an uploaded audio file
- `search_by_text_description` - Find songs matching text descriptions
- `search_by_tempo_range` - Find songs within a specific BPM range
- `search_hybrid` - Combine multiple search criteria

**Technology Stack**:
- PostgreSQL with pgvector for vector similarity search
- CLAP embeddings for audio similarity
- Librosa features for tempo/key detection
- Text embeddings for metadata search

### 2. Production MCP Server (`mcp_server_new.py`)

**Purpose**: Audio production and modification operations

**Tools**:
- `analyze_audio` - Extract tempo, key, beats from audio files
- `match_tempo` - Time-stretch audio to target BPM (pitch-preserving)
- `create_transition` - Create beat-matched DJ transitions
- `apply_mastering` - Apply professional mastering (compression, limiting)

**Technology Stack**:
- Librosa for audio analysis and manipulation
- SoundFile for audio I/O
- NumPy/SciPy for DSP operations

### 3. Claude Dual MCP Agent (`claude_dual_mcp_agent.py`)

**Purpose**: Orchestrate both servers through Claude AI

**Features**:
- Routes tool calls to appropriate server
- Maintains conversation context
- Tracks token usage and costs
- Provides natural language interface

## Tool Organization

```json
{
  "tools": [
    {
      "name": "search_by_audio_file",
      "server": "rag",
      "description": "Find songs similar to an uploaded audio file"
    },
    {
      "name": "search_by_text_description", 
      "server": "rag",
      "description": "Find songs matching text descriptions"
    },
    {
      "name": "search_by_tempo_range",
      "server": "rag",
      "description": "Find songs within a specific tempo range"
    },
    {
      "name": "search_hybrid",
      "server": "rag",
      "description": "Search with multiple criteria"
    },
    {
      "name": "analyze_audio",
      "server": "mcp",
      "description": "Extract tempo, key, beats from audio"
    },
    {
      "name": "match_tempo",
      "server": "mcp",
      "description": "Time-stretch audio to specific BPM"
    },
    {
      "name": "create_transition",
      "server": "mcp",
      "description": "Create beat-matched DJ transition"
    },
    {
      "name": "apply_mastering",
      "server": "mcp",
      "description": "Apply professional mastering"
    }
  ]
}
```

## Usage Examples

### Search Operations (RAG Server)

```python
# Find songs by audio similarity
await agent.chat("Find songs that sound like my-song.mp3")

# Natural language search
await agent.chat("Find calm ambient sleep music")

# Tempo-based search
await agent.chat("Find songs between 120-130 BPM")

# Hybrid search
await agent.chat("Find upbeat rock songs around 140 BPM")
```

### Production Operations (MCP Server)

```python
# Analyze audio characteristics
await agent.chat("Analyze the tempo and key of song.mp3")

# Time-stretch to target BPM
await agent.chat("Change song.mp3 to 128 BPM and save as song-128.mp3")

# Create DJ transition
await agent.chat("Create a smooth transition from song1.mp3 to song2.mp3")

# Apply mastering
await agent.chat("Master song.mp3 to -14 LUFS and save as song-mastered.mp3")
```

## Setup Instructions

### 1. Start RAG Server

```bash
python rag_mcp_server.py
```

### 2. Start Production Server

```bash
python mcp_server_new.py
```

### 3. Run Agent

```bash
python claude_dual_mcp_agent.py
```

## File Structure

```
big-flavor-band-agent/
├── rag_mcp_server.py          # RAG/search MCP server
├── mcp_server_new.py           # Production MCP server
├── claude_dual_mcp_agent.py    # Orchestrating agent
├── rag_system.py               # RAG implementation
├── database.py                 # Database manager
├── audio_analysis_cache.py     # Audio analysis caching
├── audio_embedding_extractor.py # Audio embeddings
└── docs/
    └── DUAL_MCP_ARCHITECTURE.md # This file
```

## Benefits of This Architecture

1. **Separation of Concerns**: Read operations are separate from write operations
2. **Scalability**: Each server can be scaled independently
3. **Maintainability**: Clear boundaries between search and production
4. **MCP Best Practices**: Follows recommended patterns for MCP servers
5. **Flexibility**: Can add new tools to either server without affecting the other

## Migration from Old Architecture

The old `mcp_server.py` combined both search and production operations. To migrate:

1. **Search tools** → Moved to `rag_mcp_server.py`
2. **Production tools** → Moved to `mcp_server_new.py`
3. **Agent** → Updated to `claude_dual_mcp_agent.py` with routing logic

## Database Schema

The architecture uses these key tables:

- `songs` - Song metadata
- `audio_embeddings` - Vector embeddings for audio similarity
- `text_embeddings` - Text embeddings for metadata search

See `sql/init/` for complete schema.

## Performance Considerations

- **RAG Server**: Uses pgvector for efficient similarity search
- **Production Server**: Audio processing operations are CPU-intensive
- **Caching**: Audio analysis results are cached to avoid recomputation
- **Connection Pooling**: Database connections are pooled for efficiency

## Future Enhancements

- [ ] Add real-time audio streaming support
- [ ] Implement batch processing for production operations
- [ ] Add support for more audio formats
- [ ] Implement advanced mastering chains
- [ ] Add collaborative filtering recommendations
- [ ] Support for multi-user scenarios

## Troubleshooting

### RAG Server Issues

- Ensure PostgreSQL with pgvector is running
- Verify audio embeddings are indexed
- Check database connection settings

### Production Server Issues

- Verify librosa and soundfile are installed
- Ensure sufficient disk space for output files
- Check audio file format compatibility

### Agent Issues

- Verify Anthropic API key is set
- Check both servers are running
- Review conversation history for errors

## API Reference

See individual server files for complete API documentation:
- `rag_mcp_server.py` - RAG server tools
- `mcp_server_new.py` - Production server tools
- `claude_dual_mcp_agent.py` - Agent orchestration
