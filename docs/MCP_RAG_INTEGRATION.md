# 🎸 MCP Server with RAG System Integration

## Overview

Your MCP server now includes **semantic search capabilities** powered by the RAG (Retrieval-Augmented Generation) system! AI agents can now find songs based on audio similarity, not just metadata.

## 🆕 New Tools Available

### 1. `semantic_search_by_audio`
**Find songs that sound similar to a reference audio file**

```json
{
  "name": "semantic_search_by_audio",
  "arguments": {
    "audio_path": "/path/to/reference.mp3",
    "limit": 10,
    "similarity_threshold": 0.5
  }
}
```

**Parameters:**
- `audio_path` (required): Path to reference audio file
- `limit` (optional): Max results (default: 10)
- `similarity_threshold` (optional): Min similarity 0-1 (default: 0.5)

**Returns:**
```json
{
  "query_audio": "/path/to/reference.mp3",
  "total_results": 5,
  "similarity_threshold": 0.5,
  "results": [
    {
      "song_id": "abc123",
      "title": "Similar Song",
      "genre": "Rock",
      "similarity": 0.87,
      "tempo_bpm": 125.0,
      "audio_path": "/path/to/similar.mp3"
    }
  ]
}
```

### 2. `get_similar_songs`
**Find songs similar to a given song using embeddings**

```json
{
  "name": "get_similar_songs",
  "arguments": {
    "song_id": "abc123",
    "limit": 10,
    "similarity_threshold": 0.5
  }
}
```

**Use Case:** "Show me songs that sound like 'Summer Groove'"

### 3. `search_by_tempo_and_similarity`
**Find songs with similar tempo and optionally similar sound**

```json
{
  "name": "search_by_tempo_and_similarity",
  "arguments": {
    "target_tempo": 120.0,
    "reference_audio_path": "/optional/audio/file.mp3",
    "tempo_tolerance": 10.0,
    "limit": 10
  }
}
```

**Use Case:** "Find songs around 120 BPM that sound like this audio file"

### 4. `get_embedding_stats`
**Get statistics about indexed song embeddings**

```json
{
  "name": "get_embedding_stats",
  "arguments": {}
}
```

**Returns:**
```json
{
  "status": "success",
  "statistics": {
    "total_songs": 1452,
    "songs_with_audio_embeddings": 823,
    "songs_with_text_embeddings": 0,
    "avg_tempo": 118.5
  }
}
```

### 5. `find_songs_without_embeddings`
**Find songs that haven't been indexed yet**

```json
{
  "name": "find_songs_without_embeddings",
  "arguments": {}
}
```

**Use Case:** Check which songs still need to be indexed

## 🚀 How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   AI Agent (via MCP)                     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              BigFlavorMCPServer                          │
│  • Original Tools (RSS, search, filter)                 │
│  • NEW: RAG-powered semantic search                     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                 SongRAGSystem                            │
│  • Audio similarity search (549-dim vectors)            │
│  • Text similarity search (1536-dim vectors)            │
│  • Hybrid search (audio + text)                         │
│  • Tempo-based search with audio similarity             │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│         PostgreSQL + pgvector Database                   │
│  • audio_embeddings table                               │
│  • IVFFlat indexes for fast similarity search           │
└─────────────────────────────────────────────────────────┘
```

### Embedding Features

**Audio Embeddings (549 dimensions):**
- **CLAP**: 512-dim deep learning audio embeddings
- **Librosa**: 37 audio features (tempo, key, MFCCs, spectral features)

**What Makes Songs "Similar":**
- Timbral characteristics (instrument sounds)
- Rhythmic patterns
- Harmonic content
- Energy levels
- Spectral features

## 🧪 Testing

### Quick Test
```powershell
python test_mcp_rag.py
```

This will:
1. ✅ Check embedding statistics
2. ✅ Find songs without embeddings
3. ✅ Test semantic audio search (if audio files exist)
4. ✅ Test similar song discovery by ID
5. ✅ Test tempo-based search

### Expected Output
```
================================================================================
Testing MCP Server with RAG System
================================================================================

✅ RAG system initialized successfully!

================================================================================
Test 1: Get Embedding Statistics
================================================================================
{
  "status": "success",
  "statistics": {
    "total_songs": 1452,
    "songs_with_audio_embeddings": 823,
    "songs_with_text_embeddings": 0,
    "avg_tempo": 118.5
  }
}

📊 823/1452 songs have audio embeddings

================================================================================
Test 2: Find Songs Without Embeddings
================================================================================

629 songs need indexing:
  1. Song Title 1 (ID: abc123)
  2. Song Title 2 (ID: def456)
  ...
```

## 🎯 Usage Examples

### Example 1: Find Similar Songs
```python
# AI Agent asks: "Find songs that sound like 'Summer Groove'"

# MCP Server receives:
{
  "name": "get_similar_songs",
  "arguments": {
    "song_id": "song_001",
    "limit": 5,
    "similarity_threshold": 0.5
  }
}

# Returns:
{
  "reference_song_id": "song_001",
  "total_results": 5,
  "results": [
    {
      "title": "Weekend Warrior",
      "genre": "Rock",
      "similarity": 0.82,
      "tempo_bpm": 128.5
    },
    ...
  ]
}
```

### Example 2: Audio-Based Discovery
```python
# AI Agent: "I have this audio file, find similar songs"

{
  "name": "semantic_search_by_audio",
  "arguments": {
    "audio_path": "audio_library/reference.mp3",
    "limit": 10,
    "similarity_threshold": 0.4
  }
}
```

### Example 3: Tempo + Similarity Search
```python
# AI Agent: "Find upbeat songs around 130 BPM that sound energetic"

{
  "name": "search_by_tempo_and_similarity",
  "arguments": {
    "target_tempo": 130.0,
    "tempo_tolerance": 10.0,
    "reference_audio_path": "audio_library/energetic_sample.mp3",
    "limit": 10
  }
}
```

## 📋 Prerequisites

### ✅ Required
- PostgreSQL database running
- pgvector extension installed
- Songs indexed with embeddings (run `index_audio_library.py`)

### ⚠️ Check Status
```powershell
# Test database connection and embeddings
python test_mcp_rag.py

# Check embedding stats
python -c "
import asyncio
from database import DatabaseManager
from rag_system import SongRAGSystem

async def check():
    db = DatabaseManager()
    await db.connect()
    rag = SongRAGSystem(db)
    stats = await rag.get_embedding_stats()
    print(stats)
    await db.close()

asyncio.run(check())
"
```

## 🔧 Configuration

### Enable/Disable RAG
```python
# In mcp_server.py or when initializing
server = BigFlavorMCPServer(
    enable_rag=True,  # Set to False to disable RAG features
    enable_audio_analysis=True
)
```

### Database Connection
The RAG system uses the `DatabaseManager` class which reads from:
- Environment variables (`DB_HOST`, `DB_USER`, etc.)
- Or defaults in `database.py`

## 🐛 Troubleshooting

### Issue: "RAG system not enabled or not initialized"
**Solution:**
1. Check database is running: `docker ps`
2. Verify database config in `database.py`
3. Test connection: `python -c "from database import DatabaseManager; import asyncio; asyncio.run(DatabaseManager().connect())"`

### Issue: "No songs have embeddings yet"
**Solution:**
```powershell
# Index your audio library
python index_audio_library.py
```

### Issue: "No embedding found for song"
**Solution:** The specific song hasn't been indexed yet. Check with:
```powershell
python test_mcp_rag.py
```

## 🎉 What's Next?

Now that RAG is integrated into your MCP server, you can:

1. **🤖 Test with AI Agents**: Connect Claude or other MCP-compatible agents
2. **🎵 Build Playlists**: Use semantic similarity to create cohesive playlists
3. **🔍 Advanced Search**: Combine text search with audio similarity
4. **📊 Analytics**: Analyze your music library by sonic characteristics
5. **🎸 Recommendations**: Build a recommendation engine

## 📚 Related Files

- `mcp_server.py` - MCP server with RAG integration
- `rag_system.py` - RAG system implementation
- `test_mcp_rag.py` - Test script for RAG features
- `index_audio_library.py` - Index songs for RAG search
- `database.py` - Database manager
- `audio_embedding_extractor.py` - Audio feature extraction

## 🎯 Key Benefits

✅ **Semantic Search** - Find songs by how they sound, not just metadata  
✅ **AI-Powered Discovery** - Let AI agents explore your music intelligently  
✅ **Multimodal** - Combines audio features with text metadata  
✅ **Fast** - pgvector IVFFlat indexes for sub-second search  
✅ **Scalable** - Works with thousands of songs  

---

**Ready to test?** Run `python test_mcp_rag.py` to see it in action! 🚀
