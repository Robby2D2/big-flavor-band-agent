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
    
    def __init__(self, headless: bool = True, download_audio: bool = True):
        """
        Initialize the scraper
        
        Args:
            headless: Run browser in headless mode
            download_audio: Download MP3 files
        """
        self.headless = headless
        self.download_audio = download_audio
        self.driver: Optional[webdriver.Chrome] = None
        self.audio_dir = "audio_library"
        
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
    
    def get_all_songs(self) -> List[Dict[str, Any]]:
        """
        Get list of all songs from the main page (Vaadin grid)
        
        Returns:
            List of song dictionaries with basic info
        """
        logger.info("Fetching all songs from main page")
        self.driver.get(self.BASE_URL)
        
        # Wait for Vaadin grid to load
        wait = WebDriverWait(self.driver, 10)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "v-grid-body")))
        
        # Additional wait for content to render
        time.sleep(2)
        
        # Get page source and parse with BeautifulSoup
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        
        songs = []
        
        # Find all song rows in Vaadin grid (only data rows, not header rows)
        song_rows = soup.find_all('tr', class_='v-grid-row-has-data')
        
        for row in song_rows:
            try:
                song_data = self._parse_song_row(row)
                if song_data:
                    songs.append(song_data)
            except Exception as e:
                logger.error(f"Error parsing song row: {e}")
                continue
        
        logger.info(f"Found {len(songs)} songs")
        return songs
    
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
    
    def get_song_details(self, song_id: str, edit_url: str) -> Dict[str, Any]:
        """
        Get detailed information for a song from its edit page
        
        Args:
            song_id: Song ID
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
            
            # Download audio if enabled
            if self.download_audio:
                local_path = self._download_audio(song_id, audio_url)
                if local_path:
                    details['local_audio_path'] = local_path
        
        return details
    
    def _extract_form_fields(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract fields from the edit form"""
        fields = {}
        
        # Extract title
        title_input = soup.find('input', {'name': re.compile(r'title', re.I)})
        if title_input:
            fields['title'] = title_input.get('value', '')
        
        # Extract session
        session_select = soup.find('select', {'name': re.compile(r'session', re.I)})
        if session_select:
            selected_option = session_select.find('option', selected=True)
            if selected_option:
                fields['session'] = selected_option.get_text(strip=True)
        
        # Extract is_original checkbox
        original_checkbox = soup.find('input', {'type': 'checkbox', 'name': re.compile(r'original', re.I)})
        if original_checkbox:
            fields['is_original'] = original_checkbox.has_attr('checked')
        
        # Extract dates
        recorded_on = soup.find('input', {'name': re.compile(r'recorded', re.I)})
        if recorded_on:
            fields['recorded_on'] = recorded_on.get('value', '')
        
        uploaded_on = soup.find('input', {'name': re.compile(r'uploaded', re.I)})
        if uploaded_on:
            fields['uploaded_on'] = uploaded_on.get('value', '')
        
        # Extract rating
        rating_input = soup.find('input', {'name': re.compile(r'rating', re.I)})
        if rating_input:
            try:
                fields['rating'] = int(rating_input.get('value', 0))
            except ValueError:
                pass
        
        return fields
    
    def _extract_instruments(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract instruments and musicians from the edit page"""
        instruments = []
        
        # Look for instrument sections (adjust selector based on actual HTML)
        instrument_rows = soup.find_all('tr', class_=re.compile(r'instrument', re.I))
        
        for row in instrument_rows:
            musician = row.find('td', class_=re.compile(r'musician', re.I))
            instrument = row.find('td', class_=re.compile(r'instrument', re.I))
            
            if musician and instrument:
                instruments.append({
                    'musician': musician.get_text(strip=True),
                    'instrument': instrument.get_text(strip=True)
                })
        
        # Alternative: look for select dropdowns
        if not instruments:
            musician_selects = soup.find_all('select', {'name': re.compile(r'musician', re.I)})
            instrument_selects = soup.find_all('select', {'name': re.compile(r'instrument', re.I)})
            
            for mus_select, inst_select in zip(musician_selects, instrument_selects):
                mus_option = mus_select.find('option', selected=True)
                inst_option = inst_select.find('option', selected=True)
                
                if mus_option and inst_option:
                    instruments.append({
                        'musician': mus_option.get_text(strip=True),
                        'instrument': inst_option.get_text(strip=True)
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
    
    def _download_audio(self, song_id: str, audio_url: str) -> Optional[str]:
        """
        Download audio file
        
        Args:
            song_id: Song ID for filename
            audio_url: URL to download from
            
        Returns:
            Local file path if successful
        """
        try:
            # Create safe filename
            filename = f"{song_id}.mp3"
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
    
    def scrape_all_songs(self) -> List[Dict[str, Any]]:
        """
        Scrape all songs with full details
        
        Returns:
            List of dictionaries with complete song data
        """
        # Get list of all songs
        songs = self.get_all_songs()
        
        # Get details for each song
        detailed_songs = []
        for i, song in enumerate(songs, 1):
            try:
                logger.info(f"Processing song {i}/{len(songs)}: {song.get('title', 'Unknown')}")
                
                if 'edit_url' in song:
                    details = self.get_song_details(song['id'], song['edit_url'])
                    # Merge basic info with details
                    song.update(details)
                
                detailed_songs.append(song)
                
                # Be polite - add delay between requests
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error processing song {song.get('id', 'unknown')}: {e}")
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
