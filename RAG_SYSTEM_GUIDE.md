# RAG System for Song Library - Complete Guide

## 🎯 Overview

This RAG (Retrieval-Augmented Generation) system enables semantic search over your song library using **multimodal embeddings**:

- **Audio embeddings**: CLAP (Contrastive Language-Audio Pretraining) + librosa features
- **Text embeddings**: Song metadata, titles, genres, descriptions
- **Hybrid search**: Combines audio and text similarity for best results

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Audio Files (.mp3)                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│           AudioEmbeddingExtractor                            │
│  • Librosa: MFCCs, spectrograms, tempo, key, chroma         │
│  • CLAP: 512-dim deep learning audio embeddings             │
│  • Combined: 549-dim vector (37 librosa + 512 CLAP)         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              PostgreSQL + pgvector                           │
│  • audio_embeddings table (549-dim vectors)                 │
│  • text_embeddings table (1536-dim vectors)                 │
│  • IVFFlat indexes for fast similarity search               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    SongRAGSystem                             │
│  • Audio similarity search                                   │
│  • Text similarity search                                    │
│  • Hybrid search (audio + text)                              │
│  • Tempo-based search with audio similarity                  │
└─────────────────────────────────────────────────────────────┘
```

## 📊 What's Extracted

### Audio Features (Librosa)

1. **Temporal Features**
   - Tempo (BPM)
   - Beat tracking
   - Duration

2. **Spectral Features** (timbre)
   - Spectral centroid (brightness)
   - Spectral rolloff (frequency content)
   - Spectral bandwidth
   - Zero crossing rate (noisiness)

3. **MFCCs** (Mel-Frequency Cepstral Coefficients)
   - 13 coefficients capturing spectral envelope
   - Compact representation of timbre

4. **Harmonic Features**
   - Chroma (12 pitch classes)
   - Key estimation
   - Tonnetz (tonal centroid features)

5. **Energy Features**
   - RMS energy
   - Dynamic range

6. **Mel Spectrogram**
   - Time-frequency representation
   - Captures overall sonic character

### Deep Learning Embeddings (CLAP)

- **512-dimensional** semantic audio embedding
- Trained on 400k+ hours of audio
- Captures high-level audio concepts
- Enables audio-text cross-modal search

## 🚀 Quick Start

### 1. Install Dependencies

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install new dependencies
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install transformers pgvector
pip install -r requirements.txt
```

### 2. Apply Database Schema

```powershell
# Start PostgreSQL if not running
docker-compose up -d

# Apply the new schema
docker exec -i bigflavor-postgres psql -U bigflavor -d bigflavor < sql/init/03-add-audio-embeddings.sql
```

### 3. Index Your Audio Library

```powershell
# Check current status
python index_audio_library.py status

# Index all songs (this will take time!)
python index_audio_library.py

# Or index in smaller batches for testing
# (modify the script to limit songs)
```

### 4. Test Search

```powershell
# Search for similar songs
python rag_system.py "audio_library/Helpless.mp3"

# Or use the demo
python demo_rag_search.py
```

## 🔍 Search Examples

### Audio Similarity Search

Find songs that **sound** similar:

```python
from rag_system import SongRAGSystem
from database import DatabaseManager

db = DatabaseManager()
await db.connect()
rag = SongRAGSystem(db, use_clap=True)

# Find songs similar to "Helpless"
results = await rag.search_by_audio_similarity(
    query_audio_path="audio_library/Helpless.mp3",
    limit=10,
    similarity_threshold=0.5
)

for result in results:
    print(f"{result['title']}: {result['similarity']:.3f}")
```

### Text Search

Find songs by metadata:

```python
# Assuming you have text embeddings (from OpenAI, etc.)
text_embedding = get_text_embedding("upbeat rock song")

results = await rag.search_by_text(
    query_embedding=text_embedding,
    content_types=['genre', 'description'],
    limit=10
)
```

### Hybrid Search

Combine audio and text:

```python
results = await rag.search_hybrid(
    audio_embedding=audio_emb,
    text_embedding=text_emb,
    audio_weight=0.6,  # 60% audio, 40% text
    text_weight=0.4,
    limit=10
)
```

### Tempo + Audio Search

Find songs with specific tempo that sound similar:

```python
results = await rag.search_by_tempo_and_audio(
    target_tempo=120,
    reference_audio_path="audio_library/Some Song.mp3",
    tempo_tolerance=10.0,  # ±10 BPM
    limit=10
)
```

## 🎛️ Configuration Options

### CLAP vs Librosa-Only

**With CLAP** (recommended):
- Pros: Better semantic understanding, captures high-level features
- Cons: Requires ~2GB GPU VRAM, slower (but better)
- Use: `SongRAGSystem(db, use_clap=True)`

**Librosa-only**:
- Pros: Fast, no GPU needed, lightweight
- Cons: Less semantic understanding, mostly acoustic features
- Use: `SongRAGSystem(db, use_clap=False)`

### Embedding Dimensions

- **With CLAP**: 549 dims (37 librosa + 512 CLAP)
- **Without CLAP**: 549 dims (37 librosa + 512 zeros)

You can modify `audio_embedding_extractor.py` to change this.

## 📈 Performance Considerations

### Indexing Speed

- **With CLAP + GPU**: ~2-5 seconds per song
- **With CLAP + CPU**: ~10-30 seconds per song
- **Librosa-only**: ~1-2 seconds per song

For ~1200 songs:
- GPU: ~1-2 hours
- CPU: ~4-10 hours
- Librosa-only: ~30-60 minutes

### Search Speed

- **Vector search**: <50ms for 1000s of songs (with IVFFlat index)
- **Hybrid search**: <100ms
- Highly optimized with pgvector indexes

### Storage

- Audio embeddings: ~2.5 KB per song
- Text embeddings: ~6 KB per song
- For 1200 songs: ~10 MB total

## 🔧 Troubleshooting

### CLAP Model Download Issues

If CLAP model download fails:

```python
# Manually download and cache
from transformers import AutoProcessor, ClapModel
model = ClapModel.from_pretrained("laion/clap-htsat-unfused")
processor = AutoProcessor.from_pretrained("laion/clap-htsat-unfused")
```

### Out of Memory (GPU)

If you get OOM errors:

1. Process in smaller batches
2. Use CPU instead: `device = "cpu"` in extractor
3. Clear cache between batches: `torch.cuda.empty_cache()`

### Slow Indexing

Speed up indexing:

1. Use GPU if available
2. Reduce audio duration in extractor (currently 30s for librosa, 10s for CLAP)
3. Process in parallel (be careful with GPU memory)

### Audio File Not Found

Ensure audio files are in `audio_library/` directory and filenames match song titles in database.

## 🎨 Advanced Usage

### Custom Weighting

Adjust feature importance:

```python
# In audio_embedding_extractor.py, modify create_combined_embedding():
combined = np.concatenate([
    feature_vector * 0.5,  # 50% librosa
    clap_embedding * 0.5   # 50% CLAP
])
```

### Add More Features

Add your own features to librosa extraction:

```python
# In extract_librosa_features():
harmonic, percussive = librosa.effects.hpss(y)
harmonic_ratio = np.mean(harmonic) / np.mean(percussive)
```

### Query Caching

Enable caching for repeated queries:

```python
rag = SongRAGSystem(db, cache_ttl_hours=24)
# Repeated queries will use cache
```

## 📚 Next Steps

1. **Text Embeddings**: Add OpenAI embeddings for song descriptions
2. **Playlist Generation**: Use RAG to create cohesive playlists
3. **Recommendation Engine**: Integrate with existing recommendation system
4. **Audio Chatbot**: Ask natural language questions about songs
5. **Similar Song Browser**: Build UI to explore similar songs

## 🤝 Integration with Existing Code

### With Recommendation Engine

```python
from recommendation_engine import RecommendationEngine
from rag_system import SongRAGSystem

# Combine traditional rules with RAG
recommendations = recommendation_engine.recommend(current_song)
similar_by_audio = await rag.search_by_audio_similarity(current_song['audio_url'])

# Merge results
combined = merge_recommendations(recommendations, similar_by_audio)
```

### With MCP Server

Add RAG tools to your MCP server:

```python
@server.tool()
async def find_similar_songs_by_audio(audio_path: str) -> dict:
    """Find songs with similar audio characteristics."""
    results = await rag.search_by_audio_similarity(audio_path)
    return {"results": results}
```

## 📝 Schema Reference

### audio_embeddings Table

```sql
CREATE TABLE audio_embeddings (
    id SERIAL PRIMARY KEY,
    song_id VARCHAR(50) REFERENCES songs(id),
    audio_path TEXT NOT NULL UNIQUE,
    combined_embedding vector(549),
    clap_embedding vector(512),
    librosa_features JSONB,
    embedding_model VARCHAR(100),
    extracted_at TIMESTAMP
);
```

### Key Functions

- `search_similar_songs_by_audio(embedding, limit, threshold)`
- `search_similar_songs_by_text(embedding, limit, content_types)`
- `search_songs_hybrid(audio_emb, text_emb, weights, limit)`
- `search_by_tempo_and_audio(tempo, tolerance, embedding, limit)`

## 🐛 Known Issues

1. **Filename Matching**: Some songs may not match between DB and filesystem
   - Solution: Manual mapping or fuzzy matching
   
2. **MP3 Loading**: Some MP3s may have encoding issues
   - Solution: Convert to WAV or use different decoder

3. **CLAP Memory**: Large batch processing can exhaust GPU memory
   - Solution: Process in smaller batches or use CPU

## 💡 Tips

1. **Start small**: Test on 10-20 songs first
2. **GPU recommended**: Massive speedup for CLAP
3. **Monitor progress**: Check logs for failed files
4. **Backup database**: Before large indexing jobs
5. **Test queries**: Verify results make sense

## 📞 Support

For issues or questions:
- Check logs in console output
- Review `audio_indexing_report.json` after indexing
- Enable debug logging: `logging.basicConfig(level=logging.DEBUG)`
