# Lyrics Extraction - Quick Reference

## 🎵 What This Does

Automatically extracts lyrics from your audio files and indexes them for semantic search in the RAG system.

**Technology Stack**:
- 🎤 **Demucs**: Separates vocals from instrumentals
- 🗣️ **faster-whisper**: Transcribes vocals to text (4-5x faster than standard Whisper)

## ⚡ Quick Start

### 1. Install Dependencies
```powershell
pip install faster-whisper demucs
```

### 2. Verify Installation
```powershell
python tests/test_lyrics_extractor.py
```

### 3. Test Single Song
```powershell
python src/rag/lyrics_extractor.py audio_library/your_song.mp3
```

### 4. Index Your Library
```powershell
# Start with a few songs
python src/rag/index_lyrics.py --max-songs 5

# Index all songs without lyrics
python src/rag/index_lyrics.py
```

## 📊 Performance

| Configuration | Time per Song | Batch (100 songs) |
|--------------|---------------|-------------------|
| GPU + Base model | 1-2 min | 2-3 hours |
| CPU + Base model | 3-7 min | 5-12 hours |

**Accuracy**: 70-95% depending on audio quality and vocal clarity

## 🎯 Common Commands

```powershell
# Check status
python src/rag/index_lyrics.py --status

# Test single file
python src/rag/index_lyrics.py --test audio_library/song.mp3

# Index with custom settings
python src/rag/index_lyrics.py --max-songs 10 --min-confidence 0.7

# Skip vocal separation (faster, less accurate)
python src/rag/index_lyrics.py --no-vocal-separation

# Reindex all songs
python src/rag/index_lyrics.py --reindex
```

## 📁 Files Created

- `src/rag/lyrics_extractor.py` - Core lyrics extraction module
- `src/rag/index_lyrics.py` - Batch indexing script
- `tests/test_lyrics_extractor.py` - Dependency checker
- `docs/LYRICS_EXTRACTION_GUIDE.md` - Full documentation

## 🔧 Configuration

Edit `src/rag/lyrics_extractor.py` to change models:

```python
# For speed (less accurate)
whisper_model_size='tiny'

# Recommended balance
whisper_model_size='base'

# For accuracy (slower)
whisper_model_size='medium'
```

## 💡 Tips

1. **First run takes longer** - Models download automatically (~3GB)
2. **Use GPU if available** - 3-4x faster than CPU
3. **Start small** - Test with `--max-songs 5` first
4. **Check confidence** - Songs with confidence < 70% may have poor transcriptions
5. **Vocal separation helps** - Especially for songs with heavy instrumentation

## 🔍 Using Lyrics in Search

Once indexed, lyrics are automatically included in text searches:

```python
# The RAG system will search lyrics along with titles and metadata
results = await rag.search_by_text(
    query_embedding=embedding("songs about heartbreak"),
    content_types=['lyrics', 'title', 'description']
)
```

## ❓ Troubleshooting

| Problem | Solution |
|---------|----------|
| Dependencies not found | `pip install faster-whisper demucs` |
| Out of memory | Use `--no-vocal-separation` or set `use_gpu=False` |
| Low accuracy | Enable vocal separation, use larger model |
| Too slow | Use `whisper_model_size='tiny'` or skip vocal separation |

## 📚 Full Documentation

See `docs/LYRICS_EXTRACTION_GUIDE.md` for:
- Detailed installation
- Model selection guide
- Performance tuning
- Advanced configuration
- Troubleshooting guide

## 🚀 Next Steps

1. ✅ Install dependencies
2. ✅ Test on sample songs
3. ✅ Index your library
4. ⏳ Generate text embeddings (requires OpenAI API - TODO)
5. ⏳ Use lyrics in semantic search
