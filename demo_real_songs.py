"""
Quick Demo: Using the Updated MCP Server with Real Songs
Shows practical examples of how to work with 1,452 real songs from bigflavorband.com
"""

import asyncio
import json
from mcp_server import BigFlavorMCPServer


async def demo():
    """Demonstrate the MCP server with real songs."""
    
    server = BigFlavorMCPServer()
    
    print("🎸 Big Flavor Band MCP Server - Real Songs Demo")
    print("=" * 60)
    
    # 1. Get the song library
    print("\n1️⃣  Fetching the complete song library...")
    library = await server.get_song_library()
    print(f"   ✅ Loaded {library['total_songs']} real songs!")
    print(f"   📡 Source: {library.get('source', 'RSS feed')}")
    
    # 2. Show some interesting songs
    print("\n2️⃣  Sample of interesting songs:")
    interesting_titles = ["Hallelujah", "Rock and Roll", "Here Comes a Regular"]
    for title in interesting_titles:
        result = await server.search_songs(title)
        if result['results_count'] > 0:
            song = result['songs'][0]
            print(f"\n   🎵 {song['title']}")
            print(f"      Session: {song['album_session']}")
            print(f"      Variant: {song['variant'] or 'Standard'}")
            print(f"      Genre: {song['genre']}")
            print(f"      Recorded: {song['recording_date']}")
    
    # 3. Browse by genre
    print("\n3️⃣  Songs by Genre:")
    genres = ["Rock", "Blues", "Jazz", "Acoustic/Folk"]
    for genre in genres:
        result = await server.filter_songs_by_genre([genre])
        print(f"   {genre}: {result['results_count']} songs")
    
    # 4. Find all versions of a popular song
    print("\n4️⃣  All versions of 'This Year':")
    result = await server.search_songs("This Year")
    print(f"   Found {result['results_count']} versions:")
    for song in result['songs'][:5]:  # Show first 5
        print(f"   • {song['full_title']} - {song['album_session']}")
    
    # 5. Find songs with specific instruments
    print("\n5️⃣  Songs featuring piano/keys:")
    result = await server.search_songs("keys")
    print(f"   Found {result['results_count']} songs with piano/keys")
    for song in result['songs'][:3]:
        print(f"   • {song['full_title']}")
    
    # 6. Find live recordings
    print("\n6️⃣  Live recordings:")
    result = await server.search_songs("live")
    print(f"   Found {result['results_count']} live recordings")
    for song in result['songs'][:3]:
        print(f"   • {song['title']} - {song['album_session']}")
    
    # 7. Get detailed info for a specific song
    print("\n7️⃣  Detailed song information:")
    song_id = library['songs'][0]['id']
    details = await server.get_song_details(song_id)
    if details['status'] == 'found':
        song = details['song']
        print(f"\n   ID: {song['id']}")
        print(f"   Title: {song['title']}")
        print(f"   Full Title: {song['full_title']}")
        print(f"   Session: {song['album_session']}")
        print(f"   Genre: {song['genre']}")
        print(f"   Mood: {song['mood']}")
        print(f"   Tags: {', '.join(song['tags'])}")
        print(f"   Audio URL: {song['audio_url']}")
        print(f"   Recording Date: {song['recording_date']}")
    
    # 8. Recent recordings
    print("\n8️⃣  Most recent recordings:")
    # Sort by recording date (songs are already in reverse chronological order)
    recent = library['songs'][:5]
    for song in recent:
        print(f"   • {song['recording_date']} - {song['title']} ({song['album_session']})")
    
    # 9. Find songs from a specific session
    print("\n9️⃣  Songs from 'Kevin's Bar+Cart Birthday Bash':")
    result = await server.search_songs("Kevin's Bar+Cart Birthday Bash")
    print(f"   Found {result['results_count']} songs from this session:")
    for song in result['songs'][:5]:
        print(f"   • {song['title']}")
    
    # 10. Summary statistics
    print("\n🔟  Library Statistics:")
    all_genres = {}
    all_moods = {}
    for song in library['songs']:
        genre = song['genre']
        mood = song['mood']
        all_genres[genre] = all_genres.get(genre, 0) + 1
        all_moods[mood] = all_moods.get(mood, 0) + 1
    
    print(f"   Total Songs: {library['total_songs']}")
    print(f"\n   Genres:")
    for genre, count in sorted(all_genres.items(), key=lambda x: x[1], reverse=True):
        print(f"      {genre}: {count} songs")
    print(f"\n   Moods:")
    for mood, count in sorted(all_moods.items(), key=lambda x: x[1], reverse=True):
        print(f"      {mood}: {count} songs")
    
    print("\n" + "=" * 60)
    print("✨ Demo complete! The MCP server is ready to use.")
    print("   Try searching for your favorite songs or browsing by session!")


if __name__ == "__main__":
    asyncio.run(demo())
