"""
Web scraper for Big Flavor Band website
Extracts comprehensive song data including ratings, sessions, comments, instruments, and audio files
"""

import logging
import time
import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)


class BigFlavorScraper:
    """Scraper for Big Flavor Band website"""
    
    BASE_URL = "https://bigflavorband.com/"
    
    def __init__(self, headless: bool = True, download_audio: bool = True, rss_song_map: Optional[Dict[str, int]] = None):
        """
        Initialize the scraper
        
        Args:
            headless: Run browser in headless mode
            download_audio: Download MP3 files
            rss_song_map: Optional mapping of "session--title" to numeric song ID from RSS feed
        """
        self.headless = headless
        self.download_audio = download_audio
        self.driver: Optional[webdriver.Chrome] = None
        self.audio_dir = "audio_library"
        self.rss_song_map = rss_song_map or {}  # Store RSS mapping
        
        # Create audio directory if downloading
        if self.download_audio:
            os.makedirs(self.audio_dir, exist_ok=True)
    
    def _setup_driver(self):
        """Set up Chrome WebDriver"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Install and setup ChromeDriver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("Chrome WebDriver initialized")
    
    def start(self):
        """Start the scraper"""
        if not self.driver:
            self._setup_driver()
    
    def stop(self):
        """Stop the scraper and clean up"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("Chrome WebDriver closed")
    
    def close(self):
        """Alias for stop() - close the browser"""
        self.stop()
    
    def navigate_to_songs(self):
        """Navigate to the songs page"""
        if not self.driver:
            self.start()
        
        # Navigate to main songs page
        logger.info("Navigating to songs page...")
        self.driver.get(self.BASE_URL)
        time.sleep(2)  # Wait for page to load
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()
    
    def login(self, username: str, password: str) -> bool:
        """
        Login to the website if required
        
        Args:
            username: Login username
            password: Login password
            
        Returns:
            True if login successful
        """
        try:
            self.driver.get(urljoin(self.BASE_URL, "Login/Login"))
            
            # Wait for login form
            wait = WebDriverWait(self.driver, 10)
            username_field = wait.until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            password_field = self.driver.find_element(By.NAME, "password")
            
            # Enter credentials
            username_field.send_keys(username)
            password_field.send_keys(password)
            
            # Submit form
            login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_button.click()
            
            # Wait for redirect
            time.sleep(2)
            
            logger.info("Login successful")
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def get_all_songs(self, max_scrolls: int = None) -> List[Dict[str, Any]]:
        """
        Get list of all songs from the main page (Vaadin grid with dynamic scrolling)
        
        Args:
            max_scrolls: Maximum number of scroll attempts (None = keep scrolling until no new songs)
        
        Returns:
            List of song dictionaries with basic info
        """
        logger.info("Fetching all songs from main page")
        self.driver.get(self.BASE_URL)
        
        # Wait for Vaadin grid to load
        wait = WebDriverWait(self.driver, 10)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "v-grid-body")))
        
        # Additional wait for initial content to render
        time.sleep(2)
        
        # Scroll through the grid to load all songs dynamically
        # Vaadin grids use virtualization - only visible rows are in DOM
        # We need to collect unique songs as we scroll
        logger.info("Scrolling to load all songs...")
        
        all_songs_dict = {}  # Use dict to deduplicate by title
        scroll_attempts = 0
        max_scroll_attempts = max_scrolls if max_scrolls else 500  # Use provided or default
        no_new_songs_count = 0
        max_no_new_songs = 10  # Stop if we don't find new songs for 10 attempts
        
        while no_new_songs_count < max_no_new_songs and scroll_attempts < max_scroll_attempts:
            scroll_attempts += 1
            previous_unique_count = len(all_songs_dict)
            
            # Parse currently visible rows and add to our collection
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            current_rows = soup.find_all('tr', class_='v-grid-row-has-data')
            
            for row in current_rows:
                try:
                    song_data = self._parse_song_row(row)
                    if song_data and song_data.get('title'):
                        # Use title as key to deduplicate
                        all_songs_dict[song_data['title']] = song_data
                except Exception as e:
                    logger.debug(f"Error parsing row during scroll: {e}")
                    continue
            
            current_unique_count = len(all_songs_dict)
            new_songs_this_scroll = current_unique_count - previous_unique_count
            
            if scroll_attempts % 10 == 0 or new_songs_this_scroll > 0:
                logger.info(f"Scroll {scroll_attempts}: Total unique songs collected: {current_unique_count} (+{new_songs_this_scroll} new)")
            
            # Check if we found new songs
            if new_songs_this_scroll == 0:
                no_new_songs_count += 1
                if no_new_songs_count % 3 == 0:
                    logger.info(f"No new songs found (attempt {no_new_songs_count}/{max_no_new_songs})")
            else:
                no_new_songs_count = 0  # Reset counter if we got new songs
            
            # Try multiple scrolling methods
            try:
                # Method 1: Find the scrollable container and scroll it
                scroll_worked = self.driver.execute_script("""
                    // Try to find the actual scrollable element
                    var scrollableElements = [
                        document.querySelector('.v-grid-tablewrapper'),
                        document.querySelector('.v-grid-scroller'),
                        document.querySelector('.v-grid-scroller-vertical'),
                        document.querySelector('.v-grid'),
                        document.querySelector('.v-grid-body').parentElement
                    ];
                    
                    var scrolled = false;
                    for (var i = 0; i < scrollableElements.length; i++) {
                        var elem = scrollableElements[i];
                        if (elem && elem.scrollHeight > elem.clientHeight) {
                            var oldScrollTop = elem.scrollTop;
                            elem.scrollTop = elem.scrollHeight;
                            if (elem.scrollTop > oldScrollTop) {
                                scrolled = true;
                                break;
                            }
                        }
                    }
                    return scrolled;
                """)
                
                if scroll_worked:
                    logger.info("Successfully scrolled grid container")
                
                # Method 2: Use Page Down key on the grid
                try:
                    grid_element = self.driver.find_element(By.CLASS_NAME, "v-grid")
                    grid_element.click()  # Focus on the grid
                    
                    # Send multiple Page Down keys - send more for faster scrolling
                    for _ in range(10):
                        grid_element.send_keys(Keys.PAGE_DOWN)
                        time.sleep(0.05)  # Very short delay between keys
                    
                    logger.debug("Sent PAGE_DOWN keys to grid")
                except Exception as e:
                    logger.debug(f"Could not send keys to grid: {e}")
                
                # Method 3: Scroll to last visible row
                self.driver.execute_script("""
                    var rows = document.querySelectorAll('.v-grid-row-has-data');
                    if (rows.length > 0) {
                        rows[rows.length - 1].scrollIntoView(false);
                    }
                """)
                
            except Exception as e:
                logger.warning(f"Error during scroll: {e}")
            
            # Wait for potential new content to load - longer wait every 10 scrolls
            if scroll_attempts % 10 == 0:
                time.sleep(1.5)  # Longer wait periodically to let content catch up
            else:
                time.sleep(0.5)  # Normal wait
        
        logger.info(f"Finished scrolling after {scroll_attempts} attempts")
        logger.info(f"Total unique songs collected: {len(all_songs_dict)}")
        
        # Convert dict to list
        songs = list(all_songs_dict.values())
        
        logger.info(f"Successfully parsed {len(songs)} unique songs")
        return songs
    
    def get_all_songs_with_details(self, max_scrolls: int = 10, limit: Optional[int] = None, start_from_song: Optional[str] = None, existing_song_ids: Optional[set] = None) -> List[Dict[str, Any]]:
        """
        Get all songs with full details by clicking into each one as we scroll.
        This method processes songs one at a time to avoid virtualization issues.
        
        Args:
            max_scrolls: Maximum number of scroll attempts (None = keep scrolling until no new songs)
            limit: Maximum number of songs to collect (None = collect all songs)
            start_from_song: Title of song to start from (will skip all songs before this one)
            existing_song_ids: Set of song IDs already in database (will skip processing these)
            
        Returns:
            List of song dictionaries with complete data including edit page details
        """
        if existing_song_ids is None:
            existing_song_ids = set()
        
        logger.info(f"Fetching all songs with details (one at a time)")
        if existing_song_ids:
            logger.info(f"Skipping {len(existing_song_ids)} songs already in database")
        self.driver.get(self.BASE_URL)
        
        # Wait for Vaadin grid to load
        wait = WebDriverWait(self.driver, 10)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "v-grid-body")))
        time.sleep(2)
        
        all_songs_dict = {}  # Track songs by song_id (unique) not title
        scroll_attempts = 0
        max_scroll_attempts = max_scrolls if max_scrolls else 500
        no_new_songs_count = 0
        max_no_new_songs = 10
        last_processed_song = None  # Track the last song we processed
        found_start_song = False if start_from_song else True  # Track if we've found the starting song
        
        if start_from_song:
            logger.info(f"Will start processing from song: {start_from_song}")
        
        logger.info("Processing songs one by one, row by row...")
        
        # Track current position by song title (more reliable than index)
        current_song_title = start_from_song if start_from_song else None
        found_start = False if start_from_song else True
        
        while no_new_songs_count < max_no_new_songs and scroll_attempts < max_scroll_attempts:
            # Check if we've reached the limit (only count non-skipped songs)
            if limit:
                non_skipped_count = len([s for s in all_songs_dict.values() if not s.get('skipped')])
                if non_skipped_count >= limit:
                    logger.info(f"Reached limit of {limit} new songs, stopping collection")
                    break
            
            scroll_attempts += 1
            songs_before = len(all_songs_dict)
            
            # Check if browser session is still valid
            try:
                # Quick check to see if driver is responsive
                self.driver.current_url
            except Exception as e:
                logger.error(f"Browser session lost (invalid session id). Collected {len(all_songs_dict)} songs before crash.")
                logger.info("This is normal after processing many songs. The data collected so far is still valid.")
                break
            
            # Get currently visible song buttons (not parsed HTML, actual buttons in DOM)
            try:
                song_buttons = self.driver.find_elements(By.CSS_SELECTOR, ".v-grid-cell button.v-nativebutton")
                
                # Collect visible song titles in order
                visible_songs = []
                for button in song_buttons:
                    song_title = button.text.strip()
                    if song_title:
                        visible_songs.append(song_title)
                
                # Check if we need to find the starting song
                if not found_start_song and start_from_song:
                    if start_from_song in visible_songs:
                        found_start_song = True
                        logger.info(f"Found starting song '{start_from_song}'")
                        # Don't continue - fall through to process songs
                    else:
                        # Haven't found the start song yet, skip this batch and scroll
                        logger.info(f"Start song '{start_from_song}' not visible yet, scrolling...")
                        # Don't increment scroll_attempts while searching for start song
                        # Just scroll and continue
                        try:
                            scroll_worked = self.driver.execute_script("""
                                var grid = document.querySelector('.v-grid-tablewrapper');
                                if (grid) {
                                    var oldScroll = grid.scrollTop;
                                    // Scroll more aggressively when searching for start song
                                    grid.scrollTop = grid.scrollTop + 300;
                                    return grid.scrollTop > oldScroll;
                                }
                                return false;
                            """)
                            time.sleep(0.5)
                        except Exception as e:
                            logger.debug(f"Scroll error: {e}")
                        continue
                
                # Find where to start processing
                start_index = 0
                
                # If we're looking for a start song and just found it, start from there
                if start_from_song and start_from_song in visible_songs and not last_processed_song:
                    start_index = visible_songs.index(start_from_song)
                    logger.info(f"Starting from song '{start_from_song}' at index {start_index}")
                elif last_processed_song:
                    # Verify the last processed song is still visible
                    if last_processed_song in visible_songs:
                        last_index = visible_songs.index(last_processed_song)
                        start_index = last_index + 1
                        logger.info(f"Found last processed song '{last_processed_song}' at index {last_index}, continuing from index {start_index}")
                    else:
                        logger.warning(f"Last processed song '{last_processed_song}' not visible after scroll, starting from beginning of visible songs")
                
                # Process songs starting from the correct index
                songs_to_process = visible_songs[start_index:]
                # Convert titles to IDs for checking (song_id is unique, titles may not be)
                processed_ids = set(all_songs_dict.keys())
                unprocessed_songs = []
                for s in songs_to_process:
                    song_id_check = re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')
                    if song_id_check not in processed_ids:
                        unprocessed_songs.append(s)
                
                logger.info(f"Visible songs: {len(visible_songs)}, Starting from index: {start_index}, Unprocessed: {len(unprocessed_songs)}")
                
                # Log each song we're checking row-by-row
                logger.info(f"--- Checking {len(songs_to_process)} songs starting from index {start_index} ---")
                
                # Filter out songs we already have in database
                if existing_song_ids:
                    songs_needing_processing = []
                    for idx, song_title in enumerate(songs_to_process, start=start_index):
                        # Generate text-based song ID from title  
                        text_song_id = re.sub(r'[^a-z0-9]+', '_', song_title.lower()).strip('_')
                        
                        # Check if we've already processed this in current session
                        if text_song_id in all_songs_dict:
                            logger.info(f"  [{idx:3d}] ⏭️  ALREADY PROCESSED THIS SESSION: '{song_title}' (ID: {text_song_id})")
                            continue
                        
                        # Try to get numeric ID from RSS feed if available
                        numeric_id = None
                        if self.rss_song_map:
                            # Try to match against RSS feed entries
                            for rss_key, rss_id in self.rss_song_map.items():
                                # RSS key format: "Session--Title"
                                # Extract title part after "--"
                                if '--' in rss_key:
                                    rss_title = rss_key.split('--', 1)[1]
                                    # Sanitize for comparison
                                    rss_title_clean = re.sub(r'[^a-z0-9]+', '_', rss_title.lower()).strip('_')
                                    if rss_title_clean == text_song_id:
                                        numeric_id = rss_id
                                        break
                        
                        # Check if numeric ID is in database (if we found it in RSS)
                        if numeric_id and numeric_id in existing_song_ids:
                            logger.info(f"  [{idx:3d}] ⏭️  SKIP (in database): '{song_title}' (RSS ID: {numeric_id})")
                            # Mark as processed so we don't try to get it again
                            all_songs_dict[text_song_id] = {'id': numeric_id, 'title': song_title, 'skipped': True}
                            last_processed_song = song_title
                        elif text_song_id not in existing_song_ids:
                            # New song or couldn't match in RSS
                            if numeric_id:
                                logger.info(f"  [{idx:3d}] ✨ NEW SONG - will process: '{song_title}' (RSS ID: {numeric_id})")
                            else:
                                logger.info(f"  [{idx:3d}] ✨ NEW SONG - will process: '{song_title}' (text ID: {text_song_id}, no RSS match)")
                            songs_needing_processing.append(song_title)
                        else:
                            logger.info(f"  [{idx:3d}] ⏭️  SKIP (in database): '{song_title}' (text ID: {text_song_id})")
                            all_songs_dict[text_song_id] = {'id': text_song_id, 'title': song_title, 'skipped': True}
                            last_processed_song = song_title
                    unprocessed_songs = songs_needing_processing
                    logger.info(f"After filtering existing songs: {len(unprocessed_songs)} songs need processing")
                else:
                    # No database filter - just log what we're checking
                    for idx, song_title in enumerate(songs_to_process, start=start_index):
                        song_id = re.sub(r'[^a-z0-9]+', '_', song_title.lower()).strip('_')
                        if song_id in all_songs_dict:
                            logger.info(f"  [{idx:3d}] ⏭️  ALREADY PROCESSED THIS SESSION: '{song_title}' (ID: {song_id})")
                        else:
                            logger.info(f"  [{idx:3d}] 📝 WILL PROCESS: '{song_title}' (ID: {song_id})")
                    logger.info(f"Songs to process: {len(unprocessed_songs)}")
                
                # If no unprocessed songs but we haven't hit our limit, we need to scroll to load more
                if len(unprocessed_songs) == 0 and (not limit or len(all_songs_dict) < limit):
                    logger.info("No unprocessed songs in current view, need to scroll to load more")
                    # We found songs but skipped them all, so reset the counter (we're making progress)
                    songs_after = len(all_songs_dict)
                    new_songs = songs_after - songs_before
                    if new_songs > 0:
                        no_new_songs_count = 0  # We're finding songs (even if skipped)
                    else:
                        no_new_songs_count += 1  # Truly no new songs found
                    # Don't continue yet - let the scroll happen below
                    # Skip to after the processing section
                else:
                    # Process each unprocessed song
                    for song_title in unprocessed_songs:
                        # Check if we've reached the limit (only count non-skipped songs)
                        if limit:
                            non_skipped_count = len([s for s in all_songs_dict.values() if not s.get('skipped')])
                            if non_skipped_count >= limit:
                                logger.info(f"Reached limit of {limit} new songs")
                                break
                        
                        try:
                            logger.info(f"Processing song: {song_title}")
                            
                            # Find and click the button (re-query each time as DOM changes)
                            # Escape apostrophes in XPath by using concat() function
                            if "'" in song_title:
                                # For titles with apostrophes, use concat() to avoid XPath syntax errors
                                parts = song_title.split("'")
                                xpath_text = "concat('" + "', \"'\", '".join(parts) + "')"
                                button = self.driver.find_element(
                                    By.XPATH,
                                    f"//button[@class='v-nativebutton' and text()={xpath_text}]"
                                )
                            else:
                                button = self.driver.find_element(
                                    By.XPATH,
                                    f"//button[@class='v-nativebutton' and text()='{song_title}']"
                                )
                            
                            # Extract comments from the grid row BEFORE clicking (since they're not in the edit form)
                            comments_from_row = []
                            try:
                                # Get the row containing this button
                                row = button.find_element(By.XPATH, "./ancestor::tr[contains(@class, 'v-grid-row')]")
                                # Parse row HTML to get comments from column 5
                                row_html = row.get_attribute('outerHTML')
                                from bs4 import BeautifulSoup
                                row_soup = BeautifulSoup(row_html, 'html.parser')
                                cells = row_soup.find_all('td', class_='v-grid-cell')
                                
                                # Column 5: Comments (in span with title attribute)
                                if len(cells) > 5:
                                    comment_span = cells[5].find('span', title=True)
                                    if comment_span:
                                        comments_text = comment_span.get('title', '')
                                        if comments_text:
                                            comment_list = [c.strip() for c in comments_text.split(' / ') if c.strip()]
                                            comments_from_row = [{'text': c, 'author': 'Unknown'} for c in comment_list]
                                            logger.debug(f"Extracted {len(comments_from_row)} comments from grid row")
                            except Exception as e:
                                logger.debug(f"Could not extract comments from row: {e}")
                            
                            button.click()
                            time.sleep(1)
                            
                            # Now get details from popup/edit page
                            song_data = self._extract_song_details_from_popup(song_title)
                            
                            # Merge comments from row into song_data
                            if song_data and comments_from_row:
                                song_data['comments'] = comments_from_row
                            
                            if song_data:
                                # Use song_id as key (unique), not title
                                song_id = song_data.get('id', re.sub(r'[^a-z0-9]+', '_', song_title.lower()).strip('_'))
                                all_songs_dict[song_id] = song_data
                                last_processed_song = song_title  # Update last processed
                                logger.info(f"  ✓ Got details for: {song_title} (ID: {song_id})")
                            else:
                                # Still save basic info even if details fail
                                song_id = re.sub(r'[^a-z0-9]+', '_', song_title.lower()).strip('_')
                                all_songs_dict[song_id] = {'id': song_id, 'title': song_title}
                                last_processed_song = song_title  # Update last processed
                                logger.warning(f"  ✗ Could not get full details for: {song_title} (ID: {song_id})")
                            
                            # Close the edit window by clicking the X button
                            try:
                                close_button = self.driver.find_element(By.CSS_SELECTOR, ".v-window-closebox")
                                close_button.click()
                                time.sleep(0.5)
                                logger.info("Closed edit window")
                            except Exception as close_err:
                                logger.warning(f"Could not find close button: {close_err}")
                                # If close button not found, window may have auto-closed or browser issue
                                # Don't try to continue processing, break out of this batch
                                break
                            
                        except Exception as e:
                            logger.error(f"Error processing song '{song_title}': {e}")
                            # Try to recover by closing any open windows
                            try:
                                close_button = self.driver.find_element(By.CSS_SELECTOR, ".v-window-closebox")
                                close_button.click()
                                time.sleep(0.5)
                            except:
                                pass
                            # Break out of processing this batch if we hit an error
                            break
                
            except Exception as e:
                logger.error(f"Error finding song buttons: {e}")
            
            songs_after = len(all_songs_dict)
            new_songs = songs_after - songs_before
            
            if scroll_attempts % 5 == 0 or new_songs > 0:
                logger.info(f"Scroll {scroll_attempts}: Total songs processed: {songs_after} (+{new_songs} new)")
            
            # Check if we found new songs
            if new_songs == 0:
                no_new_songs_count += 1
            else:
                no_new_songs_count = 0
            
            # Before scrolling, verify where we are in the list
            # Re-query visible songs to confirm our position
            try:
                verification_buttons = self.driver.find_elements(By.CSS_SELECTOR, ".v-grid-cell button.v-nativebutton")
                verification_songs = [b.text.strip() for b in verification_buttons if b.text.strip()]
                
                if last_processed_song:
                    if last_processed_song in verification_songs:
                        verify_index = verification_songs.index(last_processed_song)
                        next_index = verify_index + 1
                        
                        if next_index < len(verification_songs):
                            next_song = verification_songs[next_index]
                            logger.info(f"✓ Position verified: Last='{last_processed_song}' (index {verify_index}), Next='{next_song}' (index {next_index})")
                            
                            # Check if next song is near the end of visible list
                            # If we're within 5 songs of the end, scroll to load more
                            if next_index >= len(verification_songs) - 5:
                                logger.info(f"Near end of visible songs (index {next_index}/{len(verification_songs)}), will scroll")
                            else:
                                logger.info(f"Still have {len(verification_songs) - next_index} visible songs ahead, no scroll needed yet")
                        else:
                            logger.info(f"✓ Position verified: Last='{last_processed_song}' was the last visible song, will scroll")
                    else:
                        logger.warning(f"⚠ Position lost: Last processed song '{last_processed_song}' not in current view")
                        logger.info(f"Current visible songs: {verification_songs[:5]}..." if len(verification_songs) > 5 else f"Current visible songs: {verification_songs}")
            except Exception as e:
                logger.debug(f"Position verification error: {e}")

            
            if scroll_attempts % 5 == 0 or new_songs > 0:
                logger.info(f"Scroll {scroll_attempts}: Total songs processed: {songs_after} (+{new_songs} new)")
            
            # Check if we found new songs
            if new_songs == 0:
                no_new_songs_count += 1
            else:
                no_new_songs_count = 0
            
            # Scroll down to load more songs
            # Strategy: Find the last processed song and scroll it toward the top to reveal more songs below
            try:
                logger.info("Scrolling grid to load more songs...")
                
                # Try to scroll to position the last processed song near the top
                scroll_result = self.driver.execute_script("""
                    var lastSongTitle = arguments[0];
                    var grid = document.querySelector('.v-grid');
                    if (!grid) return {success: false, reason: 'No grid found'};
                    
                    var scroller = grid.querySelector('.v-grid-scroller') || 
                                   grid.querySelector('.v-grid-body') || 
                                   grid;
                    
                    var oldScrollTop = scroller.scrollTop;
                    
                    // If we have a last processed song, try to find it and scroll past it
                    if (lastSongTitle) {
                        var buttons = document.querySelectorAll('.v-grid-cell button.v-nativebutton');
                        for (var i = 0; i < buttons.length; i++) {
                            if (buttons[i].textContent.trim() === lastSongTitle) {
                                // Found it! Get the row position
                                var row = buttons[i].closest('.v-grid-row');
                                if (row) {
                                    var rowTop = row.offsetTop;
                                    var viewportHeight = scroller.clientHeight;
                                    
                                    // Scroll so this row is about 1/4 from the top of viewport
                                    // This ensures we can see several songs below it
                                    var targetScroll = rowTop - (viewportHeight / 4);
                                    
                                    // Make sure we're scrolling forward, not backward
                                    if (targetScroll > oldScrollTop) {
                                        scroller.scrollTop = targetScroll;
                                        return {
                                            success: true,
                                            method: 'found_song',
                                            song: lastSongTitle,
                                            scrolled: scroller.scrollTop - oldScrollTop,
                                            rowTop: rowTop,
                                            viewportHeight: viewportHeight
                                        };
                                    } else {
                                        // Already past this position, just scroll down a bit more
                                        scroller.scrollTop = oldScrollTop + 400;
                                        return {
                                            success: true,
                                            method: 'scroll_forward',
                                            scrolled: 400
                                        };
                                    }
                                }
                            }
                        }
                    }
                    
                    // If we didn't find the last song, just scroll down
                    scroller.scrollTop += 400;
                    
                    return {
                        success: true,
                        method: 'fixed_scroll',
                        scrolled: 400
                    };
                """, last_processed_song if last_processed_song else "")
                
                if scroll_result.get('success'):
                    method = scroll_result.get('method', 'unknown')
                    scrolled = scroll_result.get('scrolled', 0)
                    if method == 'found_song':
                        logger.info(f"Scrolled to position last song '{scroll_result.get('song')}' near top ({scrolled:.0f}px)")
                    elif method == 'scroll_forward':
                        logger.info(f"Already past last song position, scrolled forward {scrolled:.0f}px")
                    else:
                        logger.info(f"Last song not found, scrolled {scrolled:.0f}px")
                else:
                    logger.warning(f"Scroll failed: {scroll_result.get('reason', 'Unknown')}")
                
                # Give the grid time to update its virtualized content
                time.sleep(1.0)
                    
            except Exception as e:
                logger.debug(f"Scroll error: {e}")
        
        logger.info(f"Finished processing after {scroll_attempts} attempts")
        logger.info(f"Total songs collected: {len(all_songs_dict)}")
        
        return list(all_songs_dict.values())
    
    def sort_by_updated_date(self, descending: bool = True):
        """
        Click the 'Updated' column header to sort songs by update date.
        
        Args:
            descending: If True, sort newest first (default). If False, sort oldest first.
        """
        try:
            logger.info("Clicking 'Updated' column to sort by date...")
            
            # Find the "Updated" column header
            # The headers are in <th> elements with class "v-grid-column-header-cell"
            headers = self.driver.find_elements(By.CSS_SELECTOR, "th.v-grid-column-header-cell")
            
            updated_header = None
            for header in headers:
                if "Updated" in header.text:
                    updated_header = header
                    break
            
            if not updated_header:
                logger.warning("Could not find 'Updated' column header")
                return
            
            # Click once to sort (usually ascending first)
            updated_header.click()
            time.sleep(1)
            
            # Check if we need to click again for descending
            if descending:
                # Check the sort indicator - if it's ascending, click again
                sort_indicator = updated_header.find_elements(By.CSS_SELECTOR, ".v-grid-sorter")
                if sort_indicator:
                    # Look for ascending indicator, if found click again
                    classes = sort_indicator[0].get_attribute("class")
                    if "asc" in classes.lower():
                        updated_header.click()
                        time.sleep(1)
                        logger.info("Sorted by 'Updated' date (newest first)")
                    else:
                        logger.info("Sorted by 'Updated' date (newest first)")
                else:
                    # No indicator found, try clicking again to be safe
                    updated_header.click()
                    time.sleep(1)
                    logger.info("Sorted by 'Updated' date (newest first)")
            else:
                logger.info("Sorted by 'Updated' date (oldest first)")
                
        except Exception as e:
            logger.error(f"Error sorting by updated date: {e}")
    
    def get_new_songs_since(self, latest_date: Optional[datetime] = None, max_scrolls: int = 100) -> List[Dict[str, Any]]:
        """
        Get only songs that were updated after the given date.
        Assumes songs are already sorted by "Updated" date (newest first).
        Stops processing when it encounters a song older than latest_date.
        
        Args:
            latest_date: Only process songs updated after this date. If None, process all songs.
            max_scrolls: Maximum number of scroll attempts
            
        Returns:
            List of song dictionaries for new/updated songs only
        """
        if latest_date is None:
            logger.info("No latest date provided - will process all songs")
            return self.get_all_songs_with_details(max_scrolls=max_scrolls)
        
        logger.info(f"Fetching songs updated since: {latest_date}")
        
        # Ensure we're on the songs page
        self.driver.get(self.BASE_URL)
        
        # Wait for Vaadin grid to load
        wait = WebDriverWait(self.driver, 10)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "v-grid-body")))
        time.sleep(2)
        
        all_songs_dict = {}
        scroll_attempts = 0
        found_old_song = False  # Flag to stop when we find a song older than latest_date
        
        logger.info("Processing songs (will stop when reaching old songs)...")
        
        while scroll_attempts < max_scrolls and not found_old_song:
            scroll_attempts += 1
            songs_before = len(all_songs_dict)
            
            try:
                # Get currently visible song buttons
                song_buttons = self.driver.find_elements(By.CSS_SELECTOR, ".v-grid-cell button.v-nativebutton")
                
                # Collect visible song titles
                visible_songs = []
                for button in song_buttons:
                    song_title = button.text.strip()
                    if song_title and song_title not in all_songs_dict:
                        visible_songs.append(song_title)
                
                logger.info(f"Scroll {scroll_attempts}: Found {len(visible_songs)} unprocessed visible songs")
                
                # Process each visible song we haven't seen yet
                for song_title in visible_songs:
                    if found_old_song:
                        break
                    
                    try:
                        logger.info(f"Processing song: {song_title}")
                        
                        # Click on the song and get details
                        song_data = self.click_song_and_get_details(song_title)
                        
                        if song_data and 'updated_at' in song_data:
                            song_updated = song_data['updated_at']
                            
                            # Check if this song is newer than our cutoff
                            if isinstance(song_updated, str):
                                try:
                                    song_updated = datetime.fromisoformat(song_updated.replace('Z', '+00:00'))
                                except:
                                    logger.warning(f"Could not parse date: {song_updated}")
                                    song_updated = None
                            
                            if song_updated and song_updated <= latest_date:
                                logger.info(f"✓ Found old song: '{song_title}' (updated: {song_updated}) - stopping")
                                found_old_song = True
                                break
                            else:
                                logger.info(f"✓ New song: '{song_title}' (updated: {song_updated})")
                                all_songs_dict[song_title] = song_data
                        else:
                            # No update date found, include it to be safe
                            logger.warning(f"No updated_at date for '{song_title}' - including anyway")
                            all_songs_dict[song_title] = song_data
                            
                    except Exception as e:
                        logger.error(f"Error processing song '{song_title}': {e}")
                        # Continue with next song
                        
                if found_old_song:
                    break
                    
            except Exception as e:
                logger.error(f"Error finding song buttons: {e}")
            
            songs_after = len(all_songs_dict)
            new_songs = songs_after - songs_before
            
            if new_songs == 0:
                # No new songs found, scroll and try again
                logger.info("No new songs in this batch, scrolling...")
            
            # Scroll down to load more songs
            try:
                scroll_worked = self.driver.execute_script("""
                    var grid = document.querySelector('.v-grid-tablewrapper');
                    if (grid) {
                        var oldScroll = grid.scrollTop;
                        grid.scrollTop = grid.scrollTop + 400;
                        return grid.scrollTop > oldScroll;
                    }
                    return false;
                """)
                
                if not scroll_worked:
                    logger.info("Reached end of list or can't scroll further")
                    break
                    
                time.sleep(1)
                
            except Exception as e:
                logger.debug(f"Scroll error: {e}")
                break
        
        logger.info(f"Finished collecting new songs: {len(all_songs_dict)} total")
        return list(all_songs_dict.values())
    
    def _extract_song_details_from_popup(self, song_title: str) -> Optional[Dict[str, Any]]:
        """
        Extract song details from the popup/edit page that's currently open.
        Assumes the popup is already open from clicking the song.
        
        Args:
            song_title: Title of the song (for logging)
            
        Returns:
            Dictionary with song data, or None if extraction fails
        """
        try:
            # Wait a moment for popup to be ready
            time.sleep(1)
            
            # Initialize song data with title-based ID (will be replaced if we get audio URL)
            temp_id = re.sub(r'[^a-z0-9]+', '_', song_title.lower()).strip('_')
            
            song_data = {
                'id': temp_id,  # Temporary ID, will be replaced with numeric ID from audio URL
                'title': song_title
            }
            
            # The popup is a v-menubar-popup with v-menubar-menuitem spans
            # The first menuitem should be the edit button with the song title
            edit_clicked = False
            
            try:
                # Find the first menuitem in the popup (should be edit with song title)
                logger.debug(f"Looking for first menu item in popup")
                edit_menuitem = self.driver.find_element(
                    By.CSS_SELECTOR,
                    ".v-menubar-popup .v-menubar-menuitem:first-child"
                )
                logger.info(f"DEBUG: Found first menuitem, text: '{edit_menuitem.text[:100]}'")
                edit_menuitem.click()
                edit_clicked = True
                logger.info(f"Successfully clicked edit menu item")
                time.sleep(2)  # Wait for edit page to load
            except Exception as e:
                logger.debug(f"Failed to find/click first menuitem: {e}")
            
            if not edit_clicked:
                try:
                    # Alternative: Find menuitem containing the song title
                    logger.debug(f"Looking for menuitem containing song title")
                    edit_menuitem = self.driver.find_element(
                        By.XPATH,
                        f"//span[@class='v-menubar-menuitem']//span[contains(text(), '{song_title}')]/.."
                    )
                    logger.info(f"DEBUG: Found menuitem by title")
                    edit_menuitem.click()
                    edit_clicked = True
                    logger.info(f"Successfully clicked edit menu item by title")
                    time.sleep(2)
                except Exception as e:
                    logger.debug(f"Failed to find/click menuitem by title: {e}")
            
            if not edit_clicked:
                logger.warning(f"Could not find/click edit button for: {song_title}")
                return song_data
            
            # Now on edit page - extract data using Selenium (not BeautifulSoup)
            # because values are populated by JavaScript
            logger.debug("Extracting data from edit page using Selenium...")
            
            try:
                # Extract session
                session_input = self.driver.find_element(By.CSS_SELECTOR, "#sessionSelect input")
                song_data['session'] = session_input.get_attribute('value') or ''
            except:
                pass
            
            try:
                # Extract name (title)
                name_input = self.driver.find_element(By.ID, "nameTextField")
                song_data['title'] = name_input.get_attribute('value') or song_title
            except:
                pass
            
            try:
                # Extract recorded date
                recorded_input = self.driver.find_element(By.CSS_SELECTOR, "#recordedAtDateField input")
                song_data['recorded_on'] = recorded_input.get_attribute('value') or ''
            except:
                pass
            
            try:
                # Extract is_original checkbox
                original_checkbox = self.driver.find_element(By.CSS_SELECTOR, "#originalCompositionMCheckBox input[type='checkbox']")
                song_data['is_original'] = original_checkbox.is_selected()
            except:
                song_data['is_original'] = False
            
            try:
                # Extract audio URL
                audio_source = self.driver.find_element(By.CSS_SELECTOR, "audio source[type='audio/mpeg']")
                song_data['audio_url'] = audio_source.get_attribute('src') or ''
                
                # Extract numeric song ID from audio URL
                if song_data['audio_url']:
                    numeric_id = self._extract_song_id_from_url(song_data['audio_url'])
                    if numeric_id:
                        song_data['id'] = numeric_id  # Replace temp ID with numeric ID
                        logger.info(f"Extracted song ID {numeric_id} from audio URL")
                    else:
                        logger.warning(f"Could not extract numeric ID from URL: {song_data['audio_url']}")
                
                # Download the audio file if enabled
                if self.download_audio and song_data['audio_url']:
                    local_path = self._download_audio(
                        str(song_data['id']), 
                        song_data.get('title', song_title),
                        song_data['audio_url']
                    )
                    if local_path:
                        song_data['local_audio_path'] = local_path
            except Exception as e:
                logger.debug(f"Error extracting audio: {e}")
            
            # Extract instruments using Selenium
            song_data['instruments'] = self._extract_instruments_selenium()
            
            return song_data
            
        except Exception as e:
            logger.error(f"Error extracting details from popup: {e}")
            return None
    
    def _extract_instruments_selenium(self) -> List[Dict[str, str]]:
        """Extract instruments using Selenium to read JavaScript-populated values"""
        instruments = []
        
        try:
            # Find all performer select inputs
            for i in range(10):  # Check up to 10 performer slots
                try:
                    perf_input = self.driver.find_element(By.CSS_SELECTOR, f"#performerSelect-{i} input")
                    inst_input = self.driver.find_element(By.CSS_SELECTOR, f"#instrumentSelect-{i} input")
                    
                    musician = (perf_input.get_attribute('value') or '').strip()
                    instrument = (inst_input.get_attribute('value') or '').strip()
                    
                    # Add if musician has value (instrument is optional)
                    if musician:
                        instruments.append({
                            'musician': musician,
                            'instrument': instrument if instrument else 'Unknown'
                        })
                except:
                    # No more performers
                    break
        except Exception as e:
            logger.debug(f"Error extracting instruments: {e}")
        
        return instruments
    
    def _parse_song_row(self, row) -> Optional[Dict[str, Any]]:
        """
        Parse a song row from the main table (Vaadin v-grid structure)
        
        Args:
            row: BeautifulSoup row element
            
        Returns:
            Dictionary with song data
        """
        # Skip if this is a header row
        if 'v-grid-row-has-data' not in row.get('class', []):
            return None
        
        cells = row.find_all('td', class_='v-grid-cell')
        if len(cells) < 5:
            return None
        
        song_data = {}
        
        # Column 0: Title (in button element)
        title_cell = cells[0] if cells else None
        if title_cell:
            button = title_cell.find('button', class_='v-nativebutton')
            if button:
                song_data['title'] = button.get_text(strip=True)
                # Use title as ID for now (we'll need to click to get actual ID)
                song_data['id'] = song_data['title'].replace(' ', '_').replace('/', '_')
        
        # Column 1: Your Rating (skip - requires login)
        
        # Column 2: Average Rating (★)
        if len(cells) > 2:
            rating_text = cells[2].get_text(strip=True)
            if rating_text:
                try:
                    song_data['rating'] = int(rating_text)
                except ValueError:
                    pass
        
        # Column 3: Flame (skip as requested)
        
        # Column 4: Session
        if len(cells) > 4:
            session_text = cells[4].get_text(strip=True)
            if session_text:
                song_data['session'] = session_text
        
        # Column 5: Comments (in span with title attribute)
        if len(cells) > 5:
            comment_span = cells[5].find('span', title=True)
            if comment_span:
                # Comments are separated by " / "
                comments_text = comment_span.get('title', '')
                if comments_text:
                    comment_list = [c.strip() for c in comments_text.split(' / ') if c.strip()]
                    song_data['comments'] = [{'text': c, 'author': 'Unknown'} for c in comment_list]
        
        # Column 6: Recorded On
        if len(cells) > 6:
            recorded_text = cells[6].get_text(strip=True)
            if recorded_text:
                song_data['recorded_on'] = recorded_text
        
        # Column 7: Uploaded On  
        if len(cells) > 7:
            uploaded_text = cells[7].get_text(strip=True)
            if uploaded_text:
                song_data['uploaded_on'] = uploaded_text
        
        # Column 8: Updated
        if len(cells) > 8:
            updated_text = cells[8].get_text(strip=True)
            if updated_text:
                song_data['updated'] = updated_text
        
        # Note: We need to click on the song to get edit URL and more details
        # This will be done in a separate method using Selenium
        
        return song_data if song_data.get('title') else None
    
    def click_song_and_get_details(self, song_title: str) -> Dict[str, Any]:
        """
        Click on a song to open its popup, then click edit to get detailed information
        
        Args:
            song_title: Title of the song to click
            
        Returns:
            Dictionary with detailed song data from edit page
        """
        logger.info(f"Getting details for: {song_title}")
        
        try:
            # Find and click the song title button in the grid
            song_button = self.driver.find_element(
                By.XPATH, 
                f"//button[@class='v-nativebutton' and contains(text(), '{song_title}')]"
            )
            song_button.click()
            logger.debug(f"Clicked song: {song_title}")
            
            # Wait for popup to appear
            time.sleep(1)
            
            # Find and click the edit button (first row in popup)
            # The edit icon/button should be in the popup that just appeared
            try:
                # Try to find edit button by looking for common patterns
                edit_button = None
                
                # Method 1: Look for a button with edit icon or text
                try:
                    edit_button = self.driver.find_element(
                        By.XPATH,
                        "//span[@class='v-icon FontAwesome' and contains(., '')]/.."
                    )
                except NoSuchElementException:
                    pass
                
                # Method 2: Look for first clickable row in popup
                if not edit_button:
                    try:
                        edit_button = self.driver.find_element(
                            By.CSS_SELECTOR,
                            ".v-window .v-button, .v-window .v-menuitem"
                        )
                    except NoSuchElementException:
                        pass
                
                if edit_button:
                    edit_button.click()
                    logger.debug("Clicked edit button")
                    time.sleep(1)
                else:
                    logger.warning(f"Could not find edit button for: {song_title}")
                    # Try to close popup and return empty
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                    return {}
                
            except Exception as e:
                logger.warning(f"Error clicking edit button: {e}")
                # Try to close popup
                try:
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                except:
                    pass
                return {}
            
            # Now we should be on the edit page - extract details
            time.sleep(1.5)
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            details = {}
            
            # Extract form fields from edit page
            details.update(self._extract_form_fields(soup))
            
            # Extract instruments and musicians
            details['instruments'] = self._extract_instruments(soup)
            
            # Go back to main list
            try:
                # Try clicking back/close button
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(0.5)
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(0.5)
            except:
                pass
            
            return details
            
        except NoSuchElementException:
            logger.warning(f"Could not find song button for: {song_title}")
            return {}
        except Exception as e:
            logger.error(f"Error getting details for {song_title}: {e}")
            # Try to get back to main page
            try:
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(0.3)
            except:
                pass
            return {}
    
    def get_song_details(self, song_id: str, edit_url: str) -> Dict[str, Any]:
        """
        Get detailed information for a song from its edit page
        
        Args:
            song_id: Song ID (can be temporary title-based ID)
            edit_url: URL to the edit page
            
        Returns:
            Dictionary with detailed song data
        """
        logger.info(f"Fetching details for song {song_id}")
        
        self.driver.get(edit_url)
        
        # Wait for page to load
        wait = WebDriverWait(self.driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "form")))
        
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        
        details = {'id': song_id}
        
        # Extract form fields
        details.update(self._extract_form_fields(soup))
        
        # Extract instruments and musicians
        details['instruments'] = self._extract_instruments(soup)
        
        # Extract comments
        details['comments'] = self._extract_comments(song_id)
        
        # Extract audio URL
        audio_url = self._extract_audio_url(soup)
        if audio_url:
            details['audio_url'] = audio_url
            
            # Extract numeric song ID from audio URL
            numeric_id = self._extract_song_id_from_url(audio_url)
            if numeric_id:
                details['id'] = numeric_id  # Replace with numeric ID
                logger.info(f"Extracted song ID {numeric_id} from audio URL")
            
            # Download audio if enabled
            if self.download_audio:
                local_path = self._download_audio(
                    str(details['id']),
                    details.get('title', ''),
                    audio_url
                )
                if local_path:
                    details['local_audio_path'] = local_path
        
        return details
    
    def _extract_form_fields(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract fields from the edit form"""
        fields = {}
        
        # Extract session from filterselect with id="sessionSelect"
        session_input = soup.find('input', {'class': 'v-filterselect-input'})
        if session_input:
            # The parent should have id="sessionSelect"
            parent = session_input.find_parent('div', {'id': 'sessionSelect'})
            if parent:
                fields['session'] = session_input.get('value', '')
        
        # Extract name (song title) from id="nameTextField"
        name_input = soup.find('input', {'id': 'nameTextField'})
        if name_input:
            fields['title'] = name_input.get('value', '')
        
        # Extract base name from id="baseNameTextField"
        base_name_input = soup.find('input', {'id': 'baseNameTextField'})
        if base_name_input:
            fields['base_name'] = base_name_input.get('value', '')
        
        # Extract description from id="descriptionTextField"
        desc_input = soup.find('input', {'id': 'descriptionTextField'})
        if desc_input:
            fields['description'] = desc_input.get('value', '')
        
        # Extract recorded date from id="recordedAtDateField"
        recorded_input = soup.find('div', {'id': 'recordedAtDateField'})
        if recorded_input:
            date_field = recorded_input.find('input', {'class': 'v-datefield-textfield'})
            if date_field:
                fields['recorded_on'] = date_field.get('value', '')
        
        # Extract is_original checkbox from id="originalCompositionMCheckBox"
        original_checkbox = soup.find('input', {'type': 'checkbox'})
        if original_checkbox:
            # Find the parent span with id="originalCompositionMCheckBox"
            parent = original_checkbox.find_parent('span', {'id': 'originalCompositionMCheckBox'})
            if parent:
                fields['is_original'] = original_checkbox.has_attr('checked')
        
        # Extract MP3 URL from audio source
        audio_source = soup.find('source', {'type': 'audio/mpeg'})
        if audio_source:
            fields['audio_url'] = audio_source.get('src', '')
        
        # Extract mix name from id="mixNameTextField-0"
        mix_name_input = soup.find('input', {'id': 'mixNameTextField-0'})
        if mix_name_input:
            fields['mix_name'] = mix_name_input.get('value', '')
        
        return fields
    
    def _extract_instruments(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract instruments and musicians from the edit page"""
        instruments = []
        
        # The performers grid has pairs of selects with IDs like:
        # performerSelect-0, instrumentSelect-0
        # performerSelect-1, instrumentSelect-1, etc.
        
        # Find all performer selects
        performer_divs = soup.find_all('div', {'id': lambda x: x and x.startswith('performerSelect-')})
        
        for perf_div in performer_divs:
            # Get the index from the ID
            perf_id = perf_div.get('id', '')
            index = perf_id.split('-')[-1] if '-' in perf_id else None
            
            if index is None:
                continue
            
            # Find the corresponding instrument select
            inst_div = soup.find('div', {'id': f'instrumentSelect-{index}'})
            
            if inst_div:
                # Get the input values
                perf_input = perf_div.find('input', {'class': 'v-filterselect-input'})
                inst_input = inst_div.find('input', {'class': 'v-filterselect-input'})
                
                if perf_input and inst_input:
                    musician = perf_input.get('value', '').strip()
                    instrument = inst_input.get('value', '').strip()
                    
                    # Only add if both have values (not empty/prompt)
                    if musician and instrument and not inst_div.find('div', {'class': 'v-filterselect-prompt'}):
                        instruments.append({
                            'musician': musician,
                            'instrument': instrument
                        })
        
        return instruments
    
    def _extract_comments(self, song_id: str) -> List[Dict[str, str]]:
        """Extract comments for a song (may require clicking a popup)"""
        comments = []
        
        try:
            # Look for comments button/link
            comment_button = self.driver.find_element(
                By.CSS_SELECTOR, 
                f"a[href*='comment'], button[class*='comment']"
            )
            comment_button.click()
            
            # Wait for comments popup/section to load
            wait = WebDriverWait(self.driver, 5)
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "comment")))
            
            # Parse comments
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            comment_elements = soup.find_all('div', class_=re.compile(r'comment', re.I))
            
            for comment_elem in comment_elements:
                author = comment_elem.find('span', class_=re.compile(r'author', re.I))
                text = comment_elem.find('p', class_=re.compile(r'text', re.I))
                
                if text:
                    comments.append({
                        'author': author.get_text(strip=True) if author else 'Unknown',
                        'text': text.get_text(strip=True)
                    })
            
        except (TimeoutException, NoSuchElementException):
            logger.debug(f"No comments found for song {song_id}")
        
        return comments
    
    def _extract_audio_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract MP3 URL from the page"""
        # Look for audio element
        audio_elem = soup.find('audio')
        if audio_elem:
            source = audio_elem.find('source')
            if source:
                return urljoin(self.BASE_URL, source.get('src', ''))
        
        # Look for download link
        download_link = soup.find('a', href=re.compile(r'\.mp3$', re.I))
        if download_link:
            return urljoin(self.BASE_URL, download_link.get('href', ''))
        
        return None
    
    def _extract_song_id_from_url(self, audio_url: str) -> Optional[int]:
        """
        Extract numeric song ID from audio URL.
        Expected format: https://bigflavorband.com/audio/1864/filename.mp3
        
        Args:
            audio_url: Full URL to audio file
            
        Returns:
            Song ID as integer, or None if not found
        """
        try:
            # Extract ID from URL pattern: /audio/{id}/filename.mp3
            match = re.search(r'/audio/(\d+)/', audio_url)
            if match:
                return int(match.group(1))
        except Exception as e:
            logger.debug(f"Could not extract song ID from URL {audio_url}: {e}")
        
        return None
    
    def _download_audio(self, song_id: str, song_title: str, audio_url: str) -> Optional[str]:
        """
        Download audio file
        
        Args:
            song_id: Numeric song ID for filename
            song_title: Song title for filename
            audio_url: URL to download from
            
        Returns:
            Local file path if successful
        """
        try:
            # Create safe filename with ID and title: "12345_song_title.mp3"
            safe_title = re.sub(r'[^\w\s-]', '', song_title).strip()
            safe_title = re.sub(r'[-\s]+', '_', safe_title)
            filename = f"{song_id}_{safe_title}.mp3"
            filepath = os.path.join(self.audio_dir, filename)
            
            # Skip if already downloaded
            if os.path.exists(filepath):
                logger.info(f"Audio file already exists: {filepath}")
                return filepath
            
            # Download file
            logger.info(f"Downloading audio: {audio_url}")
            response = requests.get(audio_url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded audio to: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to download audio for song {song_id}: {e}")
            return None
    
    def scrape_all_songs(self, get_details: bool = False) -> List[Dict[str, Any]]:
        """
        Scrape all songs with full details
        
        Args:
            get_details: If True, click into each song to get edit page details
            
        Returns:
            List of dictionaries with complete song data
        """
        # Get list of all songs from main table
        songs = self.get_all_songs()
        
        if not get_details:
            logger.info(f"Scraped {len(songs)} songs (without detailed information)")
            return songs
        
        # Get details for each song by clicking into edit page
        logger.info(f"Getting detailed information for {len(songs)} songs...")
        detailed_songs = []
        
        for i, song in enumerate(songs, 1):
            try:
                logger.info(f"Processing song {i}/{len(songs)}: {song.get('title', 'Unknown')}")
                
                # Click into song and get details from edit page
                edit_details = self.click_song_and_get_details(song['title'])
                
                # Merge table data with edit page details
                if edit_details:
                    song.update(edit_details)
                
                detailed_songs.append(song)
                
                # Be polite - add delay between requests
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error processing song {song.get('id', 'unknown')}: {e}")
                # Still add the song with whatever data we have
                detailed_songs.append(song)
                continue
        
        return detailed_songs


def main():
    """Example usage"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Example: scrape all songs
    with BigFlavorScraper(headless=False, download_audio=True) as scraper:
        # Login if required
        # scraper.login("username", "password")
        
        # Scrape all songs
        songs = scraper.scrape_all_songs()
        
        logger.info(f"Scraped {len(songs)} songs")
        
        # Print first song as example
        if songs:
            print("\nExample song data:")
            import json
            print(json.dumps(songs[0], indent=2, default=str))


if __name__ == "__main__":
    main()
