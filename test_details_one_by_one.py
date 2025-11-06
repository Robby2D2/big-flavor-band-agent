"""
Test collecting song details one at a time to avoid virtualization issues
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
    """Test the new get_all_songs_with_details method"""
    
    print("\n" + "="*60)
    print("Big Flavor Band Scraper - One-by-One Details Test")
    print("="*60 + "\n")
    
    print("This test will process songs one at a time:")
    print("1. Find visible song buttons")
    print("2. Click each one to get details")
    print("3. Close popup and move to next")
    print("4. Scroll to load more songs")
    print()
    
    # Choose number of songs
    print("\nHow many songs to process?")
    print("1. Just 3 songs (quick test)")
    print("2. 20 songs (medium test)")
    print("3. All songs (VERY slow - 30+ minutes)")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        max_scrolls = 1  # Just first screen
        limit = 3
    elif choice == "2":
        max_scrolls = 5
        limit = 20
    else:
        max_scrolls = None  # All songs
        limit = None
    
    scraper = None
    try:
        # Initialize scraper with visible browser
        print("\nInitializing scraper (browser will be visible)...")
        scraper = BigFlavorScraper(
            headless=False  # Browser visible for testing
        )
        
        # Navigate to songs page
        print("Navigating to songs page...")
        scraper.navigate_to_songs()
        
        # Get songs with details one at a time
        print(f"\nProcessing up to {limit if limit else 'all'} songs...")
        print("Watch the browser - you'll see it click each song!")
        print()
        
        songs = scraper.get_all_songs_with_details(max_scrolls=max_scrolls, limit=limit)
        
        print(f"\n✓ Successfully processed {len(songs)} songs!")
        
        # Show sample results
        print("\n" + "="*60)
        print("SAMPLE RESULTS (first 3 songs)")
        print("="*60)
        
        for i, song in enumerate(songs[:3], 1):
            print(f"\n{i}. {song.get('title', 'Unknown')}")
            print(f"   Rating: {song.get('rating', 'N/A')}")
            print(f"   Session: {song.get('session', 'N/A')}")
            print(f"   Original: {song.get('is_original', 'N/A')}")
            
            instruments = song.get('instruments', [])
            if instruments:
                print(f"   Instruments ({len(instruments)}):")
                for inst in instruments[:3]:
                    print(f"     - {inst.get('musician', 'Unknown')}: {inst.get('instrument', 'Unknown')}")
            else:
                print(f"   Instruments: None found")
            
            if song.get('audio_url'):
                print(f"   Audio: {song['audio_url'][:50]}...")
        
        # Full data for first song
        if songs:
            print("\n" + "="*60)
            print("FULL DATA FOR FIRST SONG")
            print("="*60)
            print(json.dumps(songs[0], indent=2, default=str))
        
        print("\n" + "="*60)
        print("\nTest complete! Browser will stay open.")
        print("Press Enter to close browser and exit...")
        input()
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        
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
