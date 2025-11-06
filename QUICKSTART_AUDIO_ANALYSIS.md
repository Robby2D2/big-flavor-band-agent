# Quick Start: Audio Analysis Feature

This guide will help you get started with the audio analysis feature to automatically extract BPM, key, and genre information from your MP3 files.

## What You'll Get

After setting up audio analysis, songs in your library will have:
- ✅ **Accurate BPM** (beats per minute) detected from audio
- ✅ **Musical Key** (e.g., C, D#, F Major)
- ✅ **Genre Hints** based on audio characteristics
- ✅ **Energy Level** (low/medium/high)
- ✅ **Exact Duration** in seconds

## Installation (5 minutes)

### Step 1: Install Audio Analysis Dependencies

**Option A - Use the setup script:**
```powershell
.\setup_audio_analysis.ps1
```

**Option B - Manual installation:**
```powershell
pip install librosa soundfile numpy
```

### Step 2: Verify Installation

```powershell
python test_audio_analysis.py
```

You should see:
```
✓ All tests passed!
✓ Librosa is installed and available
```

## Usage

### Option 1: Automatic (Recommended)

Just start the MCP server. It will automatically use cached analysis for any songs that have been analyzed:

```powershell
python mcp_server.py
```

Songs with cached analysis will have accurate BPM, key, and genre data. Songs without cached analysis will use inferred values from the title.

### Option 2: Pre-Analyze Songs

Pre-analyze songs to populate the cache before using them:

**Test with a few songs first:**
```powershell
python pre_analyze_audio.py --max-files 5
```

This will:
1. Fetch the RSS feed from bigflavorband.com
2. Download the first 5 audio files
3. Analyze each file to extract BPM, key, genre
4. Save results to `.audio_cache/analysis_cache.json`
5. Delete the downloaded files (only cache is kept)

**Analyze all songs (takes a while):**
```powershell
python pre_analyze_audio.py
```

### Option 3: Analyze Local Files

If you have MP3 files locally:

```powershell
python pre_analyze_audio.py --local-dir "C:\Path\To\Audio\Files"
```

## Example Output

```
[1/5] Processing: Tired of Being Helpless - Big Flavor Band
  Downloading https://bigflavorband.com/audio/...
  Downloaded to temp_audio\song_0001.mp3
  Analyzing audio...
  ✓ Analysis complete: BPM=132.4, Key=D, Energy=high

[2/5] Processing: Let It Roll - Big Flavor Band
  Downloading https://bigflavorband.com/audio/...
  Already analyzed (cached)

============================================================
Analysis Summary:
  Total files: 5
  Analyzed: 4
  Skipped (cached): 1
  Errors: 0
============================================================

Cache statistics:
  Total cached entries: 5
  Cache file: .audio_cache\analysis_cache.json
  Cache size: 8192 bytes
```

## Using with MCP Tools

Once you have analyzed songs, the MCP server will automatically use the cached data. You can also use these tools:

### Analyze a local audio file:
```json
{
  "tool": "analyze_local_audio",
  "arguments": {
    "file_path": "C:\\Music\\song.mp3"
  }
}
```

### Check cache statistics:
```json
{
  "tool": "get_audio_cache_stats",
  "arguments": {}
}
```

## Performance Tips

1. **Start Small**: Test with `--max-files 5` first
2. **Batch Analysis**: Run pre-analysis during off-hours
3. **Local Storage**: Cache is stored locally, no re-analysis needed
4. **Incremental**: Add new songs to cache as needed

## Troubleshooting

### "librosa not available" warning
- **Solution**: Run `pip install librosa soundfile numpy`
- System still works, just without audio analysis

### Analysis is slow
- **Normal**: Each song takes 5-30 seconds to analyze
- **Workaround**: Use `--max-files` to limit songs
- **Good news**: You only analyze each song once!

### Cache file not found
- **Normal**: Cache is created on first analysis
- **Location**: `.audio_cache/analysis_cache.json`
- **Auto-created**: Will be created automatically when needed

### Incorrect genre detection
- **Expected**: Genre hints are heuristic, not definitive
- **Solution**: Manual genres still work fine
- **Note**: Genre hints are added to tags, not replacing manual genres

## File Structure

After setup, you'll have:
```
big-flavor-band-agent/
├── .audio_cache/
│   └── analysis_cache.json     # Cached analysis results
├── audio_analysis_cache.py     # Audio analysis module
├── pre_analyze_audio.py        # Pre-analysis utility
└── mcp_server.py              # MCP server (with integration)
```

## Next Steps

1. ✅ Install dependencies: `pip install librosa soundfile numpy`
2. ✅ Test installation: `python test_audio_analysis.py`
3. ✅ Analyze a few songs: `python pre_analyze_audio.py --max-files 5`
4. ✅ Start using: `python mcp_server.py`

## Advanced Usage

### Analyze specific sessions
```powershell
# Download and analyze only specific session files
python pre_analyze_audio.py --max-files 20
```

### Clear cache and re-analyze
```python
from audio_analysis_cache import AudioAnalysisCache
cache = AudioAnalysisCache()
cache.clear_cache()
```

### Check what's in the cache
```python
from audio_analysis_cache import AudioAnalysisCache
cache = AudioAnalysisCache()
stats = cache.get_cache_stats()
print(f"Cached songs: {stats['total_entries']}")
```

## Resources

- **Full Documentation**: See [AUDIO_ANALYSIS.md](AUDIO_ANALYSIS.md)
- **Implementation Details**: See [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- **Main README**: See [README.md](README.md)

## Questions?

- Check the logs for detailed analysis progress
- Run `python test_audio_analysis.py` to verify setup
- See [AUDIO_ANALYSIS.md](AUDIO_ANALYSIS.md) for more details

---

**Note**: Audio analysis is optional. The system works fine without it, using inferred metadata from song titles and album names.
