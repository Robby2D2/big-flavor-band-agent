# Audio Analysis Cache

This feature automatically extracts BPM, key, genre hints, energy levels, and other metadata from MP3 files using audio analysis, and caches the results locally to avoid re-analyzing files.

## Features

- **Automatic BPM Detection**: Extracts tempo in beats per minute
- **Key Detection**: Identifies the musical key of the song
- **Genre Hints**: Provides genre suggestions based on audio characteristics
- **Energy Analysis**: Calculates energy levels (low/medium/high)
- **Duration Extraction**: Gets accurate song duration
- **Local Caching**: Stores analysis results to avoid re-analyzing unchanged files
- **Change Detection**: Re-analyzes files only when they change (based on file size and modification time)

## Installation

Install the required dependencies:

```powershell
pip install librosa numpy soundfile
```

Or install all dependencies from the requirements file:

```powershell
pip install -r requirements.txt
```

## Usage

### 1. Automatic Integration with MCP Server

The audio analysis is automatically integrated into the MCP server. When songs are fetched from the RSS feed, the server checks if cached analysis exists and enriches the song metadata automatically.

Start the server normally:

```powershell
python mcp_server.py
```

### 2. Pre-Analyze Audio Files

To pre-populate the cache by analyzing all songs from the RSS feed:

```powershell
# Analyze songs and keep MP3 files (default)
python pre_analyze_audio.py --max-files 10

# Analyze all songs from the RSS feed
python pre_analyze_audio.py

# Analyze and delete MP3s after (saves disk space)
python pre_analyze_audio.py --max-files 10 --no-keep-files

# Analyze local audio files
python pre_analyze_audio.py --local-dir "path/to/audio/files"
```

**Note**: By default, MP3 files are now kept in the `audio_library/` directory. This allows re-analysis without re-downloading. Files are organized by song ID (e.g., `song_0001.mp3`). You can safely delete this folder if you need disk space - the cache will remain.

### 3. MCP Tools for Audio Analysis

The MCP server provides tools for analyzing audio:

#### `analyze_local_audio`
Analyze a local audio file to extract BPM, key, genre hints, and energy.

```json
{
  "tool": "analyze_local_audio",
  "arguments": {
    "file_path": "path/to/song.mp3"
  }
}
```

#### `get_audio_cache_stats`
Get statistics about the audio analysis cache.

```json
{
  "tool": "get_audio_cache_stats",
  "arguments": {}
}
```

## How It Works

### Analysis Process

1. **Check Cache**: First checks if the audio file has already been analyzed
2. **Change Detection**: Verifies if the file has changed since last analysis
3. **Audio Analysis**: Uses librosa to analyze the audio:
   - Beat tracking for BPM
   - Chroma features for key detection
   - Spectral features for genre hints
   - RMS energy for energy level
4. **Cache Storage**: Saves results to `.audio_cache/analysis_cache.json`

### Audio Features Extracted

- **BPM (Tempo)**: Beats per minute
- **Key**: Estimated musical key (e.g., "C", "D#", "F")
- **Genre Hints**: Up to 3 genre suggestions based on audio characteristics
- **Energy Level**: Categorized as low, medium, or high
- **Duration**: Song length in seconds
- **Spectral Features**: Centroid, rolloff, and zero-crossing rate

### Genre Detection Heuristics

The system uses audio features to suggest genres:

- **BPM Range**: Different BPM ranges suggest different genres
  - 60-80 BPM: Blues, Ballad, Soul
  - 80-110 BPM: Rock, Alternative, Folk
  - 110-140 BPM: Rock, Pop, Indie
  - 140-180 BPM: Punk, Metal, Hard Rock

- **Spectral Brightness**: Higher spectral centroid suggests Pop/brighter genres
- **Zero-Crossing Rate**: Higher values suggest Rock/Metal (more distortion)
- **Energy Level**: Affects genre hints (Acoustic vs. Energetic)

## Cache Management

### Cache Location

The cache is stored in `.audio_cache/analysis_cache.json` in the project directory.

### Cache Structure

```json
{
  "hash_of_audio_url": {
    "analysis": {
      "bpm": 128.5,
      "key": "C",
      "genre_hints": ["Rock", "Alternative"],
      "energy": "high",
      "duration_seconds": 245.3,
      "spectral_features": {
        "centroid": 1500.2,
        "rolloff": 3200.5,
        "zero_crossing_rate": 0.08
      }
    },
    "timestamp": "2025-11-05T10:30:00",
    "file_hash": "abc123...",
    "audio_url": "https://example.com/song.mp3"
  }
}
```

### Clearing the Cache

To clear all cached analysis:

```python
from audio_analysis_cache import AudioAnalysisCache

cache = AudioAnalysisCache()
cache.clear_cache()
```

## Performance Considerations

- **First Analysis**: Takes 5-30 seconds per song depending on length
- **Cached Lookups**: Nearly instant
- **Memory Usage**: Minimal - analysis results are small JSON objects
- **Disk Usage**: Approximately 1-2 KB per cached song

## Fallback Behavior

If librosa is not installed or analysis fails:

- Returns default values (bpm=None, genre_hints=[], energy='medium')
- Does not block other functionality
- Logs warnings for debugging

## Troubleshooting

### "librosa not available" Warning

Install librosa and its dependencies:

```powershell
pip install librosa soundfile numpy
```

### Analysis Takes Too Long

- Use `--max-files` to limit the number of files analyzed
- Pre-analyze in batches during low-usage times
- The cache ensures you only analyze each file once

### Incorrect Genre Detection

Genre detection is heuristic-based and may not always be accurate. The system provides "hints" rather than definitive classifications. You can still override genres manually in the song metadata.

## Example Output

```
Analyzing audio file: song_0001.mp3
Analysis complete: BPM=132.4, Key=D, Energy=high
✓ Saved to cache

Cached analysis for song_0002.mp3:
  BPM: 88.2
  Key: E
  Genre Hints: Blues, Rock, Alternative
  Energy: medium
  Duration: 312.5 seconds
```

## Integration with RSS Feed

When the MCP server fetches songs from the RSS feed:

1. Parses RSS to extract song metadata
2. Checks cache for each audio URL
3. If cached analysis exists, enriches song with:
   - Accurate BPM
   - Musical key
   - Energy level
   - Genre hints (added to tags)
4. If no cache exists, uses inferred values from title/album

## Future Enhancements

- Automatic download and analysis on RSS fetch
- Parallel analysis for faster processing
- More sophisticated genre classification using ML
- Mood detection from audio features
- Automatic playlist generation based on audio similarity
