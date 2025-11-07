"""Test script for RSS parser functionality."""

import asyncio
import json
from mcp_server import BigFlavorMCPServer


async def test_rss_parser():
    """Test the RSS parser with real data from bigflavorband.com."""
    print("Testing Big Flavor Band RSS Parser")
    print("=" * 50)
    
    server = BigFlavorMCPServer()
    
    # Fetch song library
    print("\nFetching song library from RSS feed...")
    result = await server.get_song_library()
    
    print(f"\nStatus: {result['status']}")
    print(f"Total songs: {result['total_songs']}")
    
    if result['total_songs'] > 0:
        print(f"\nFirst 5 songs:")
        for song in result['songs'][:5]:
            print(f"\n  {song['id']}: {song['title']}")
            print(f"    Full title: {song['full_title']}")
            print(f"    Album/Session: {song['album_session']}")
            print(f"    Genre: {song['genre']}")
            print(f"    Mood: {song['mood']}")
            print(f"    Tags: {', '.join(song['tags'])}")
            print(f"    Recording date: {song['recording_date']}")
            print(f"    Audio URL: {song['audio_url'][:80]}...")
        
        # Test search functionality
        print("\n" + "=" * 50)
        print("\nTesting search for 'tired':")
        search_result = await server.search_songs("tired")
        print(f"Found {search_result['results_count']} songs")
        for song in search_result['songs'][:3]:
            print(f"  - {song['title']} ({song['full_title']})")
        
        # Test genre filter
        print("\n" + "=" * 50)
        print("\nTesting genre filter for 'Rock':")
        genre_result = await server.filter_songs_by_genre(["Rock"])
        print(f"Found {genre_result['results_count']} Rock songs")
        for song in genre_result['songs'][:3]:
            print(f"  - {song['title']}")
    
    print("\n" + "=" * 50)
    print("Test complete!")


if __name__ == "__main__":
    asyncio.run(test_rss_parser())
