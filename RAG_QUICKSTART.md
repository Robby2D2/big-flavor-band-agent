# 🎵 Song RAG System - Quick Start

A complete **Retrieval-Augmented Generation** system for semantic audio search using multimodal embeddings.

## 🚀 Quick Start (5 minutes)

### 1. Setup

```powershell
# Run the setup script
.\setup_rag_system.ps1
```

This will:
- Install PyTorch, transformers, and other dependencies
- Apply database schema for audio embeddings
- Verify installation

### 2. Quick Test (5 songs)

```powershell
# Test on a small subset first
python quick_test_rag.py 5
```

This will:
- Index 5 songs from your library
- Test audio similarity search
- Verify everything works

### 3. Index Full Library

```powershell
# Index all songs (this takes time!)
python index_audio_library.py
```

**Time estimate:**
- With GPU: 1-2 hours for ~1200 songs
- CPU only: 4-10 hours for ~1200 songs

### 4. Try the Demos

```powershell
# Run all demos
python demo_rag_search.py

# Interactive mode - pick songs and find similar ones
python demo_rag_search.py interactive
```

## 📚 What's Included

### Core Files
- `audio_embedding_extractor.py` - Extract audio features (librosa + CLAP)
- `rag_system.py` - Main RAG system with search functions
- `index_audio_library.py` - Batch indexing tool
- `demo_rag_search.py` - Demos and interactive search
- `quick_test_rag.py` - Quick validation tool

### Database
- `sql/init/03-add-audio-embeddings.sql` - Complete schema with vector indexes

### Documentation
- `RAG_SYSTEM_GUIDE.md` - Comprehensive guide
- `RAG_IMPLEMENTATION_SUMMARY.md` - Technical details

## 🎯 What Can You Do?

### 1. Find Similar Sounding Songs

```python
from rag_system import SongRAGSystem
from database import DatabaseManager

db = DatabaseManager()
await db.connect()
rag = SongRAGSystem(db, use_clap=True)

results = await rag.search_by_audio_similarity(
    "audio_library/Helpless.mp3",
    limit=10,
    similarity_threshold=0.5
)
```

### 2. Find Songs by Tempo + Sound

```python
results = await rag.search_by_tempo_and_audio(
    target_tempo=120,
    reference_audio_path="audio_library/Some Song.mp3",
    tempo_tolerance=10.0
)
```

### 3. Hybrid Audio + Text Search

```python
results = await rag.search_hybrid(
    audio_embedding=audio_emb,
    text_embedding=text_emb,
    audio_weight=0.6,
    text_weight=0.4
)
```

## 🔧 Troubleshooting

### Can't Find CLAP Model?

The model downloads automatically on first use (~1GB). If it fails:

```python
from transformers import ClapModel, AutoProcessor
model = ClapModel.from_pretrained("laion/clap-htsat-unfused")
processor = AutoProcessor.from_pretrained("laion/clap-htsat-unfused")
```

### Out of Memory?

If GPU runs out of memory:
1. Process smaller batches in `index_audio_library.py`
2. Use CPU: `SongRAGSystem(db, use_clap=False)`
3. Close other GPU applications

### Songs Not Matching?

If indexing can't find songs:
1. Make sure songs are in database: `python scrape_and_load_all.py`
2. Check filename matching logic in `index_audio_library.py`
3. Use manual matching or fuzzy search

## 📊 Performance

### Indexing Speed
- **GPU + CLAP**: ~2-5 seconds per song
- **CPU + CLAP**: ~10-30 seconds per song  
- **Librosa-only**: ~1-2 seconds per song

### Search Speed
- Vector similarity: <50ms
- Hybrid search: <100ms

### Storage
- ~2.5 KB per song
- ~10 MB for 1200 songs

## 🎓 Learn More

- **Full Guide**: `RAG_SYSTEM_GUIDE.md`
- **Technical Details**: `RAG_IMPLEMENTATION_SUMMARY.md`
- **Code Examples**: Look at `demo_rag_search.py`

## 📈 Next Steps

1. **Add Text Embeddings** - Embed song descriptions using OpenAI
2. **Build Playlist Generator** - Use similarity for cohesive playlists
3. **Create Web UI** - Visual similarity browser
4. **Integrate with MCP** - Expose RAG tools via MCP server
5. **Export Embeddings** - Use in other tools/services

## 🐛 Common Issues

### Issue: "No module named 'transformers'"
**Solution:** `pip install transformers torch`

### Issue: "CUDA out of memory"
**Solution:** Use `use_clap=False` or process smaller batches

### Issue: "Audio file not found"
**Solution:** Ensure files are in `audio_library/` directory

### Issue: "Database connection failed"
**Solution:** Start PostgreSQL: `docker-compose up -d`

## 💡 Tips

1. **Test first** - Use `quick_test_rag.py` before full indexing
2. **GPU recommended** - 5-10x faster with NVIDIA GPU
3. **Monitor progress** - Check console logs during indexing
4. **Start small** - Index 20-50 songs first to verify
5. **Backup database** - Before major operations

## 🎉 Features

- ✅ **549-dimensional audio embeddings** (librosa + CLAP)
- ✅ **Vector similarity search** (<50ms queries)
- ✅ **Multimodal search** (audio + text)
- ✅ **Tempo-aware search**
- ✅ **Batch processing**
- ✅ **Progress tracking**
- ✅ **Error recovery**
- ✅ **Interactive demos**
- ✅ **Comprehensive documentation**

## 📞 Need Help?

1. Check logs for error messages
2. Review `audio_indexing_report.json` after indexing
3. Enable debug logging: `logging.basicConfig(level=logging.DEBUG)`
4. Read `RAG_SYSTEM_GUIDE.md` for details

---

**Ready to start?** Run `.\setup_rag_system.ps1` and then `python quick_test_rag.py`!
