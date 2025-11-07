# New Project Structure Guide

## Overview

This document describes the refactored project structure that separates concerns into clean, maintainable modules.

## Directory Layout

```
big-flavor-band-agent/
├── run_agent.py                 # Main entry point
├── src/                         # Source code packages
│   ├── __init__.py
│   ├── agent/                   # Agent orchestration
│   │   ├── __init__.py
│   │   └── big_flavor_agent.py
│   ├── rag/                     # RAG search library
│   │   ├── __init__.py
│   │   └── big_flavor_rag.py
│   └── mcp/                     # Production MCP server
│       ├── __init__.py
│       └── big_flavor_mcp.py
├── database/                    # Database layer
│   ├── __init__.py
│   ├── database.py
│   ├── apply_schema.py
│   ├── load_from_backup.py
│   ├── setup-database.ps1
│   └── sql/                     # SQL schemas
├── setup/                       # Configuration & setup
│   ├── requirements.txt
│   ├── config.json
│   ├── setup.ps1
│   └── setup_*.ps1
├── audio_library/               # Audio files
├── docs/                        # Documentation
└── tests/                       # Test files
```

## Architecture Components

### 1. Agent Layer (`src/agent/`)

**Purpose**: Orchestrates user interactions, routes tool calls to appropriate systems

**Key File**: `big_flavor_agent.py`
- Class: `ClaudeRAGMCPAgent`
- Responsibilities:
  - Accept user queries
  - Parse Claude's tool calls
  - Route to RAG library OR MCP server
  - Format responses
  
**Key Methods**:
- `process_query()` - Main REPL loop
- `_call_tool()` - Routes tool calls to correct system
- `_perform_hybrid_search()` - Combines multiple RAG searches

**Dependencies**:
- Imports RAG system directly (library)
- Communicates with MCP server via stdio

### 2. RAG System (`src/rag/`)

**Purpose**: Semantic search over song catalog using vector embeddings

**Key File**: `big_flavor_rag.py`
- Class: `SongRAGSystem`
- **Important**: This is a LIBRARY, not an MCP server
- Responsibilities:
  - Audio similarity search
  - Text-based semantic search
  - Tempo range filtering
  - Hybrid multi-criteria search

**Key Methods**:
- `search_by_audio_similarity()` - CLAP embeddings
- `search_by_text_description()` - Text embeddings
- `search_by_tempo_range()` - BPM filtering
- `search_hybrid()` - Combined searches

**Dependencies**:
- `database.DatabaseManager` - Database access
- `audio_embedding_extractor.AudioEmbeddingExtractor` - CLAP model
- PostgreSQL with pgvector

**Why Not MCP?**
- No need for process isolation
- Direct import is faster
- Simpler code path
- More reusable

### 3. MCP Server (`src/mcp/`)

**Purpose**: Audio production operations (heavy processing, file I/O)

**Key File**: `big_flavor_mcp.py`
- Class: `BigFlavorMCPServer`
- **Important**: This IS an MCP server (process isolation justified)
- Responsibilities:
  - Audio analysis (librosa)
  - Tempo matching (time-stretching)
  - Transition creation (beat-matching)
  - Mastering effects (compression, EQ)

**Key Methods**:
- `analyze_audio()` - Extract tempo, key, beats
- `match_tempo()` - Time-stretch audio
- `create_transition()` - DJ-style crossfades
- `apply_mastering()` - Audio processing chain

**Dependencies**:
- `audio_analysis_cache.AudioAnalysisCache` - Caching
- librosa, soundfile, scipy - Audio DSP
- File system I/O

**Why MCP?**
- Heavy CPU operations
- File I/O isolation
- Cacheable results
- Separate process lifecycle

### 4. Database Layer (`database/`)

**Purpose**: All database-related code and schemas

**Key Files**:
- `database.py` - `DatabaseManager` class
- `apply_schema.py` - Schema application script
- `load_from_backup.py` - Backup restoration
- `sql/` - SQL schema files

**Database Schema**:
- `songs` - Song metadata (title, artist, album, BPM, key)
- `song_embeddings` - CLAP audio embeddings (pgvector)
- `audio_analysis_cache` - Cached librosa analysis

**Access Pattern**:
```python
from database.database import DatabaseManager

db = DatabaseManager()
results = db.execute_query("SELECT * FROM songs")
```

### 5. Setup & Configuration (`setup/`)

**Purpose**: Installation, configuration, dependency management

**Key Files**:
- `requirements.txt` - Python dependencies
- `config.json` - Application configuration
- `setup.ps1` - Main setup script
- `setup_audio_analysis.ps1` - Audio indexing
- `setup_rag_system.ps1` - RAG initialization

## Import Patterns

### From Root Entry Point (`run_agent.py`)

```python
import sys
from pathlib import Path

# Add paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "database"))

# Import agent
from src.agent.big_flavor_agent import ClaudeRAGMCPAgent
```

### Within Agent (`src/agent/big_flavor_agent.py`)

```python
# RAG system (direct library import)
from src.rag.big_flavor_rag import SongRAGSystem

# Database
from database.database import DatabaseManager

# MCP (subprocess communication)
import mcp
```

### Within RAG System (`src/rag/big_flavor_rag.py`)

```python
from database.database import DatabaseManager
from audio_embedding_extractor import AudioEmbeddingExtractor
```

### Within MCP Server (`src/mcp/big_flavor_mcp.py`)

```python
from audio_analysis_cache import AudioAnalysisCache
import librosa
import soundfile as sf
```

## Tool Routing

### Agent Decision Logic

```python
def _call_tool(self, tool_name: str, arguments: dict) -> dict:
    # RAG tools - call library directly
    if tool_name in ['search_by_audio_file', 
                     'search_by_text_description',
                     'search_by_tempo_range', 
                     'search_hybrid']:
        return self.rag_system.{method}(**arguments)
    
    # MCP tools - send via MCP protocol
    elif tool_name in ['analyze_audio', 
                       'match_tempo',
                       'create_transition', 
                       'apply_mastering']:
        return await self._call_mcp_tool(tool_name, arguments)
```

## Migration from Old Structure

### Old Files → New Files

| Old File | New File | Notes |
|----------|----------|-------|
| `claude_dual_mcp_agent.py` | `src/agent/big_flavor_agent.py` | Renamed, imports updated |
| `rag_system.py` | `src/rag/big_flavor_rag.py` | Moved to package |
| `mcp_server_new.py` | `src/mcp/big_flavor_mcp.py` | Moved to package |
| `database.py` | `database/database.py` | Moved to database/ |
| `apply_schema.py` | `database/apply_schema.py` | Moved to database/ |
| `setup-database.ps1` | `database/setup-database.ps1` | Moved to database/ |

### Removed Files

- `rag_mcp_server.py` - Unnecessary MCP wrapper (RAG is now library)
- `claude_mcp_agent.py` - Old single-MCP version
- `mcp_server.py` - Old combined server

## Testing

### Unit Tests

```powershell
# Test each component
python tests/test_agent.py
python tests/test_rag.py
python tests/test_mcp.py
python tests/test_database.py
```

### Integration Tests

```powershell
# Test full system
python run_agent.py
```

## Development Workflow

### Adding a New RAG Search Method

1. Edit `src/rag/big_flavor_rag.py`
2. Add method to `SongRAGSystem` class
3. Update agent's tool schema in `src/agent/big_flavor_agent.py`
4. Update tool routing in `_call_tool()`

### Adding a New Production Tool

1. Edit `src/mcp/big_flavor_mcp.py`
2. Add method to `BigFlavorMCPServer` class
3. Add MCP tool handler
4. Update agent's tool schema
5. Update tool routing in `_call_tool()`

### Database Schema Changes

1. Edit SQL in `database/sql/`
2. Run `python database/apply_schema.py`
3. Update `DatabaseManager` if needed

## Best Practices

### ✅ Do

- Import RAG system directly (it's a library)
- Use MCP for heavy/isolated operations
- Keep database code in `database/` package
- Add new setup scripts to `setup/`
- Document changes in `docs/`

### ❌ Don't

- Don't wrap RAG in MCP (unnecessary overhead)
- Don't put database code in other packages
- Don't hardcode paths (use Path objects)
- Don't skip tests after changes

## Performance Considerations

### RAG System (Direct Import)
- ✅ Fast: No IPC overhead
- ✅ Simple: Direct function calls
- ✅ Efficient: Shared memory space

### MCP Server (Process Isolation)
- ⚠️ Slower: IPC overhead
- ✅ Isolated: Separate process
- ✅ Justified: Heavy processing, caching

## Next Steps

1. ✅ Update all imports throughout codebase
2. ⬜ Test compilation of all new files
3. ⬜ Update remaining test files
4. ⬜ Run integration tests
5. ⬜ Update all documentation
6. ⬜ Remove old files once confirmed working

## Questions?

See other documentation:
- `SIMPLIFIED_ARCHITECTURE.md` - High-level architecture
- `TOOL_ROUTING_GUIDE.md` - Detailed tool routing
- `RAG_SYSTEM_GUIDE.md` - RAG implementation details

---

**Key Takeaway**: Clean separation of concerns with appropriate technology choices. RAG = library (fast), MCP = production server (isolated), Agent = orchestrator (smart).
