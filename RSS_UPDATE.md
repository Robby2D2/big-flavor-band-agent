# MCP Server Update: Real Songs from BigFlavorBand.com

## Summary

The MCP Server has been successfully updated to use **real songs** from the Big Flavor Band website via their RSS feed at https://bigflavorband.com/rss.

## Key Changes

### 1. RSS Feed Integration
- Added RSS feed parsing using Python's built-in `xml.etree.ElementTree`
- The server now fetches **1,452 real songs** from the live RSS feed
- Songs are cached for performance and include full metadata

### 2. Song Data Structure

Each song now includes:
- **id**: Unique identifier (e.g., `song_0001`)
- **title**: Clean song name (e.g., "So Tired")
- **full_title**: Original title with variants (e.g., "So Tired - angry goddess")
- **variant**: Performance variation or performers (e.g., "angry goddess", "KWE", "live")
- **album_session**: Recording session name (e.g., "Broken Pitchfork Retreat", "Kevin's Bar+Cart Birthday Bash")
- **url**: Web page URL for the song
- **audio_url**: Direct MP3 download link
- **audio_type**: MIME type (audio/x-mp3)
- **pub_date**: Raw publication date from RSS
- **recording_date**: Parsed ISO date (YYYY-MM-DD)
- **genre**: Inferred genre (Rock, Blues, Acoustic/Folk, Jazz, Rock/Alternative)
- **mood**: Inferred mood (melancholic, upbeat, romantic, energetic, reflective)
- **tags**: Generated tags from title/session (e.g., "guitar", "live", "piano", "drums")

### 3. Intelligent Metadata Inference

The parser includes smart inference functions:

- **Genre Detection**: Analyzes titles and session names for keywords
  - Jazz/Swing → "Jazz"
  - Blues/Blue → "Blues"
  - Rock/Metal → "Rock"
  - Acoustic/Folk → "Acoustic/Folk"
  - Default → "Rock/Alternative"

- **Mood Detection**: Infers emotional tone from song titles
  - Sad/tired/dark words → "melancholic"
  - Happy/fun/party words → "upbeat"
  - Love/heart/kiss words → "romantic"
  - Rock/roll/metal words → "energetic"
  - Default → "reflective"

- **Tag Generation**: Automatically tags songs based on:
  - Recording session name
  - Instruments mentioned (guitar, piano, drums, bass)
  - Performance style (live, acoustic, electric)
  - Vocal presence

### 4. All Existing Features Still Work

All the original MCP tools continue to function:
- ✅ `get_song_library` - Now returns real songs from RSS
- ✅ `search_songs` - Search through 1,452 real songs
- ✅ `get_song_details` - Get details for any real song
- ✅ `filter_songs_by_genre` - Filter by inferred genres
- ✅ `filter_songs_by_tempo` - Still available (would need audio analysis for real data)
- ✅ `analyze_song_metadata` - Provides analysis of real songs

## Example Songs

Here are some real songs now in the system:

1. **"So Tired"** - Multiple variants including "angry goddess", "Strega", "key-bass"
2. **"Here Comes a Regular"** - Various sessions including "space", "lead gtr", "classical"
3. **"This Year"** - From multiple sessions with different arrangements
4. **"Hallelujah"** - Sam's version from Kevin's Bar+Cart Birthday Bash
5. **"Rock and Roll"** - Multiple live versions and studio takes

## Testing

Run the test script to verify everything works:

```powershell
python test_rss_parser.py
```

This will:
- Fetch all songs from the RSS feed
- Display the first 5 songs with full metadata
- Test search functionality (searching for "tired")
- Test genre filtering (finding "Rock" songs)

## What's Next?

### Optional Enhancements:
1. **Audio Analysis**: Add librosa integration to detect actual tempo, key, and energy
2. **Caching**: Implement persistent caching to avoid refetching RSS on every startup
3. **Batch Operations**: Add tools for creating playlists or albums from songs
4. **Similar Songs**: Use metadata to find similar songs for recommendations
5. **Session Browser**: Add tools to browse all songs from a specific recording session

## Using the Updated Server

The server continues to work exactly as before, but now with real data:

```python
# In your AI agent or MCP client
result = await call_tool("get_song_library")
# Returns 1,452 real songs from bigflavorband.com

search_result = await call_tool("search_songs", {"query": "tired"})
# Finds 45 songs with "tired" in title/tags

details = await call_tool("get_song_details", {"song_id": "song_0004"})
# Returns full details for "Pale Blue Eyes - 4harm"
```

## No Breaking Changes

- ✅ All existing tool interfaces remain unchanged
- ✅ Mock data is still available as fallback if RSS fails
- ✅ All response formats are consistent
- ✅ The server will gracefully fall back to mock data if the RSS feed is unavailable

---

**Status**: ✅ Complete and tested with 1,452 real songs!
