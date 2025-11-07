"""
Test the web scraper on a single song
Useful for debugging and verifying selectors work correctly
"""

import logging
import json
from web_scraper import BigFlavorScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_main_page():
    """Test scraping the main song list"""
    logger.info("Testing main page scraping...")
    
    with BigFlavorScraper(headless=False, download_audio=False) as scraper:
        # Get list of songs from main page
        songs = scraper.get_all_songs()
        
        logger.info(f"Found {len(songs)} songs on main page")
        
        if songs:
            print("\n=== First 3 Songs ===")
            for song in songs[:3]:
                print(json.dumps(song, indent=2))
            
            return songs
        else:
            logger.warning("No songs found! Check the HTML selectors.")
            return []


def test_song_details(song_id: str, edit_url: str):
    """Test scraping a single song's details"""
    logger.info(f"Testing song details for ID: {song_id}")
    
    with BigFlavorScraper(headless=False, download_audio=False) as scraper:
        # Get detailed info for one song
        details = scraper.get_song_details(song_id, edit_url)
        
        print(f"\n=== Song Details for {song_id} ===")
        print(json.dumps(details, indent=2, default=str))
        
        return details


def interactive_test():
    """Interactive test - scrapes first song then shows details"""
    print("=" * 60)
    print("Web Scraper Test Tool")
    print("=" * 60)
    
    # First, get the song list
    songs = test_main_page()
    
    if not songs:
        print("\nNo songs found on main page.")
        print("Recommendations:")
        print("1. Check if the website requires login")
        print("2. Inspect the HTML and update selectors in web_scraper.py")
        print("3. Look for errors in the console above")
        return
    
    # Ask user which song to test in detail
    print(f"\n\nFound {len(songs)} songs. Testing first song's details...")
    first_song = songs[0]
    
    if 'edit_url' not in first_song:
        print("ERROR: No edit_url found in song data!")
        print("Check the _parse_song_row() method in web_scraper.py")
        return
    
    # Get details for first song
    input("\nPress ENTER to navigate to edit page and extract details...")
    details = test_song_details(first_song['id'], first_song['edit_url'])
    
    # Show summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    print(f"\nSong: {details.get('title', 'N/A')}")
    print(f"Session: {details.get('session', 'N/A')}")
    print(f"Rating: {details.get('rating', 'N/A')}")
    print(f"Is Original: {details.get('is_original', 'N/A')}")
    print(f"Recorded On: {details.get('recorded_on', 'N/A')}")
    print(f"Uploaded On: {details.get('uploaded_on', 'N/A')}")
    
    if details.get('instruments'):
        print(f"\nInstruments ({len(details['instruments'])}):")
        for inst in details['instruments']:
            print(f"  - {inst.get('musician', 'N/A')} on {inst.get('instrument', 'N/A')}")
    else:
        print("\nNo instruments found - check _extract_instruments() method")
    
    if details.get('comments'):
        print(f"\nComments ({len(details['comments'])}):")
        for comment in details['comments']:
            author = comment.get('author', 'Unknown')
            text = comment.get('text', '')[:50]  # First 50 chars
            print(f"  - {author}: {text}...")
    else:
        print("\nNo comments found - check _extract_comments() method")
    
    if details.get('audio_url'):
        print(f"\nAudio URL: {details['audio_url']}")
    else:
        print("\nNo audio URL found - check _extract_audio_url() method")
    
    print("\n" + "=" * 60)
    print("\nIf any data is missing:")
    print("1. The browser window should still be open")
    print("2. Inspect the HTML elements")
    print("3. Update the selectors in web_scraper.py")
    print("4. Run this test again")
    print("=" * 60)


def main():
    """Main entry point"""
    try:
        interactive_test()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        print(f"\nERROR: {e}")
        print("\nCheck the traceback above for details.")


if __name__ == "__main__":
    main()
