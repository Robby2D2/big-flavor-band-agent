# Lyrics Extraction Setup Guide

## Overview

This system extracts lyrics from audio files using:
- **Demucs**: Separates vocals from instrumentals for cleaner transcription
- **faster-whisper**: Fast, accurate speech-to-text transcription (4-5x faster than standard Whisper)

## Installation

### 1. Install Dependencies

```powershell
# Activate your virtual environment first
.\activate.ps1

# Install lyrics extraction dependencies
pip install faster-whisper demucs

# Or install all requirements
pip install -r setup/requirements.txt
```

**Note**: First run will download models (~3GB for Demucs + ~150MB for Whisper base model)

### 2. Verify Installation

```powershell
python tests/test_lyrics_extractor.py
```

You should see:
```
✓ Lyrics extractor is ready!
  faster-whisper available: True
  Whisper model loaded: True
  Demucs available: True
  Demucs initialized: True
  GPU available: True/False
```

## Quick Start

### Test on a Single Song

```powershell
# Test lyrics extraction on one audio file
python src/rag/lyrics_extractor.py audio_library/song.mp3
```

This will:
1. Separate vocals using Demucs
2. Transcribe vocals with faster-whisper
3. Display lyrics with confidence scores and timestamps

### Index Your Audio Library

```powershell
# Check current status
python src/rag/index_lyrics.py --status

# Index first 5 songs (testing)
python src/rag/index_lyrics.py --max-songs 5

# Index all songs without lyrics
python src/rag/index_lyrics.py

# Reindex all songs (including those with existing lyrics)
python src/rag/index_lyrics.py --reindex
```

### Test a Specific Song from Database

```powershell
# Test extraction and indexing for one song
python src/rag/index_lyrics.py --test audio_library/your_song.mp3
```

## How It Works

### Step 1: Vocal Separation (Demucs)

Demucs uses deep learning to separate audio into:
- Vocals
- Drums
- Bass
- Other instruments

We extract only the vocals for cleaner transcription.

**Time**: ~30-60 seconds per song (GPU) or 2-5 minutes (CPU)

### Step 2: Transcription (faster-whisper)

faster-whisper transcribes the isolated vocals to text:
- Uses Whisper model optimized with CTranslate2
- 4-5x faster than original Whisper
- Voice Activity Detection (VAD) filters out silence
- Confidence scores for each segment

**Time**: ~10-30 seconds per song (GPU) or 1-2 minutes (CPU)

### Total Processing Time

- **With GPU**: ~1-2 minutes per song
- **Without GPU**: ~3-7 minutes per song

For 100 songs:
- **With GPU**: ~2-3 hours
- **Without GPU**: ~5-12 hours

## Command Reference

### Basic Usage

```powershell
# Check status
python src/rag/index_lyrics.py --status

# Index songs without lyrics
python src/rag/index_lyrics.py

# Test single file
python src/rag/lyrics_extractor.py audio_library/song.mp3
```

### Advanced Options

```powershell
# Limit number of songs
python src/rag/index_lyrics.py --max-songs 10

# Skip vocal separation (faster but less accurate)
python src/rag/index_lyrics.py --no-vocal-separation

# Set minimum confidence threshold
python src/rag/index_lyrics.py --min-confidence 0.7

# Specify audio library path
python src/rag/index_lyrics.py --audio-library C:\Music\Library

# Reindex all songs
python src/rag/index_lyrics.py --reindex
```

## Configuration

### Model Selection

**Whisper Models** (in `lyrics_extractor.py`):
- `tiny`: Fastest, least accurate (~40MB)
- `base`: **Recommended** - good balance (~150MB)
- `small`: More accurate, slower (~500MB)
- `medium`: High accuracy, slow (~1.5GB)
- `large-v3`: Best accuracy, very slow (~3GB)

**Demucs Models**:
- `htdemucs`: **Recommended** - best quality
- `htdemucs_ft`: Fine-tuned variant
- `mdx_extra`: Alternative model

### Performance Tuning

**For Speed** (less accurate):
```python
extractor = LyricsExtractor(
    whisper_model_size='tiny',
    use_gpu=True,
    min_confidence=0.3
)

# Skip vocal separation
result = extractor.extract_lyrics(audio_path, separate_vocals=False)
```

**For Accuracy** (slower):
```python
extractor = LyricsExtractor(
    whisper_model_size='medium',
    use_gpu=True,
    min_confidence=0.7
)

# Use vocal separation
result = extractor.extract_lyrics(audio_path, separate_vocals=True)
```

## Output

### Lyrics Data Structure

```python
{
    'lyrics': 'Full lyrics as plain text...',
    'confidence': 0.85,  # Overall confidence (0-1)
    'segments': [
        {
            'start': 0.0,  # Start time in seconds
            'end': 3.5,    # End time in seconds
            'text': 'First line of lyrics',
            'confidence': 0.90
        },
        # ... more segments
    ],
    'language': 'en',
    'language_probability': 0.95,
    'vocals_separated': True
}
```

### Database Storage

Lyrics are stored in the `text_embeddings` table:

```sql
SELECT 
    s.title,
    te.content as lyrics,
    te.created_at
FROM songs s
JOIN text_embeddings te ON s.id = te.song_id
WHERE te.content_type = 'lyrics'
```

## Using Lyrics in RAG Search

Once indexed, lyrics are searchable in your RAG system:

```python
# Search by text (including lyrics)
results = await rag.search_by_text(
    query_embedding=text_embedding("songs about love"),
    content_types=['lyrics', 'title', 'description']
)

# Hybrid search (audio + lyrics)
results = await rag.search_hybrid(
    audio_embedding=audio_embedding,
    text_embedding=text_embedding("upbeat love song"),
    audio_weight=0.6,
    text_weight=0.4
)
```

## Troubleshooting

### Issue: "faster-whisper not available"

**Solution**: 
```powershell
pip install faster-whisper
```

### Issue: "demucs not available"

**Solution**:
```powershell
pip install demucs
```

### Issue: "CUDA out of memory"

**Solution**: Use CPU instead or smaller model
```python
extractor = LyricsExtractor(
    whisper_model_size='tiny',
    use_gpu=False  # Use CPU
)
```

### Issue: Low confidence scores

**Possible causes**:
- Instrumental sections (no vocals)
- Heavy background music
- Poor audio quality
- Multiple overlapping vocals

**Solutions**:
- Ensure vocal separation is enabled
- Lower `min_confidence` threshold
- Use better quality source audio

### Issue: Incorrect transcriptions

**Solutions**:
- Use larger Whisper model (`small` or `medium`)
- Ensure vocal separation is enabled
- Check audio quality
- Verify language is set correctly

## Performance Expectations

### Accuracy

With vocal separation enabled:
- **Good quality recordings**: 85-95% accuracy
- **Live recordings**: 70-85% accuracy
- **Poor quality**: 50-70% accuracy

Without vocal separation:
- Expect 10-20% lower accuracy

### Speed Benchmarks

**Base model + Demucs on RTX 3060**:
- Vocal separation: 45 seconds
- Transcription: 15 seconds
- **Total**: ~60 seconds per 3-minute song

**Base model + Demucs on CPU (i7-9700K)**:
- Vocal separation: 3 minutes
- Transcription: 90 seconds
- **Total**: ~4.5 minutes per 3-minute song

## Next Steps

1. **Test on a few songs** to verify setup
2. **Index your library** in batches
3. **Generate text embeddings** for semantic search (TODO: OpenAI integration)
4. **Use lyrics in searches** via RAG system

## Advanced: Generating Text Embeddings

Currently, lyrics are stored without embeddings. To enable semantic search:

```python
# TODO: Add OpenAI API integration
import openai

async def generate_lyrics_embedding(lyrics: str):
    response = await openai.Embedding.create(
        model="text-embedding-ada-002",
        input=lyrics
    )
    return response['data'][0]['embedding']
```

Then update the indexing to include embeddings:

```python
result = await rag.extract_and_index_lyrics(
    audio_path=audio_path,
    song_id=song_id,
    generate_embedding=True  # Will use OpenAI API
)
```

## Questions?

Check the main documentation:
- `docs/RAG_SYSTEM_GUIDE.md` - RAG system overview
- `docs/RAG_QUICKSTART.md` - RAG quick start

Or run with verbose logging:
```powershell
# Set log level to DEBUG
$env:LOG_LEVEL="DEBUG"
python src/rag/index_lyrics.py
```
