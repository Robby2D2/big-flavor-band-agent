"""
Test the click-through functionality to get detailed song information
"""

import logging
import json
from web_scraper import BigFlavorScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Test the click_song_and_get_details functionality"""
    
    print("\n" + "="*60)
    print("Big Flavor Band Scraper - Click-Through Test")
    print("="*60 + "\n")
    
    print("This test will:")
    print("1. Scrape the first few songs from the main table")
    print("2. Click into one song to get detailed info")
    print("3. Show the combined data")
    print()
    
    # Get credentials
    username = input("Enter username: ").strip()
    password = input("Enter password: ").strip()
    
    scraper = None
    try:
        # Initialize scraper with visible browser
        print("\nInitializing scraper (browser will be visible)...")
        scraper = BigFlavorScraper(
            username=username,
            password=password,
            headless=False  # Browser visible for testing
        )
        
        # Navigate to songs page
        print("Navigating to songs page...")
        scraper.navigate_to_songs()
        
        # Get first few songs
        print("\nGetting first few songs from main table...")
        songs = scraper.get_all_songs(max_scrolls=1)  # Just first screen
        songs = songs[:3]  # Limit to 3 for testing
        
        print(f"\nFound {len(songs)} songs:")
        for i, song in enumerate(songs, 1):
            print(f"  {i}. {song['title']}")
        
        # Choose a song to test
        print("\nSelect a song to test click-through (1-3):")
        choice = int(input("Enter number: ").strip())
        
        if choice < 1 or choice > len(songs):
            print("Invalid choice!")
            return
        
        test_song = songs[choice - 1]
        print(f"\nTesting with: {test_song['title']}")
        print("\n" + "-"*60)
        
        # Show main table data
        print("\n=== MAIN TABLE DATA ===")
        print(json.dumps(test_song, indent=2, default=str))
        
        # Click into song and get details
        print("\n" + "-"*60)
        print("Clicking into song to get detailed info...")
        print("(Watch the browser - you should see popup → edit page)")
        
        details = scraper.click_song_and_get_details(test_song['title'])
        
        if details:
            print("\n✓ Successfully got detailed info!")
            
            # Show edit page data
            print("\n=== EDIT PAGE DATA ===")
            print(json.dumps(details, indent=2, default=str))
            
            # Show merged data
            test_song.update(details)
            print("\n=== COMBINED DATA ===")
            print(json.dumps(test_song, indent=2, default=str))
            
            # Summary
            print("\n" + "="*60)
            print("SUMMARY")
            print("="*60)
            print(f"\nSong: {test_song['title']}")
            print(f"Rating: {test_song.get('avg_rating', 'N/A')}")
            print(f"Session: {test_song.get('session', 'N/A')}")
            print(f"Original: {test_song.get('is_original', 'N/A')}")
            
            if test_song.get('instruments'):
                print(f"\nInstruments ({len(test_song['instruments'])}):")
                for inst in test_song['instruments']:
                    print(f"  - {inst.get('musician', 'Unknown')}: {inst.get('instrument', 'Unknown')}")
            else:
                print("\nNo instruments found")
            
            if test_song.get('comments'):
                print(f"\nComments ({len(test_song['comments'])}):")
                for comment in test_song['comments'][:3]:
                    print(f"  - {comment.get('text', '')[:60]}...")
            else:
                print("\nNo comments found")
            
            if test_song.get('audio_url'):
                print(f"\nAudio URL: {test_song['audio_url']}")
            else:
                print("\nNo audio URL found")
            
        else:
            print("\n✗ Could not get detailed info")
            print("Check the logs above for errors")
            print("\nThe browser window is still open - inspect the page")
        
        print("\n" + "="*60)
        print("\nTest complete! Browser will stay open.")
        print("Press Enter to close browser and exit...")
        input()
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        
        print("\nBrowser will stay open for inspection.")
        print("Press Enter to close...")
        input()
        
    finally:
        if scraper:
            scraper.close()
            print("Browser closed.")


if __name__ == "__main__":
    main()
