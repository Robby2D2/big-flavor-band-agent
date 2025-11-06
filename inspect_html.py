"""
Quick script to inspect the HTML structure of the Big Flavor Band website
"""

import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup Chrome
chrome_options = Options()
# chrome_options.add_argument("--headless")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

try:
    # Navigate to the site
    logger.info("Navigating to Big Flavor Band website...")
    driver.get("https://bigflavorband.com/")
    
    # Wait for page to load
    time.sleep(3)
    
    # Get page source
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    
    # Save to file for inspection
    with open('bigflavor_source.html', 'w', encoding='utf-8') as f:
        f.write(soup.prettify())
    
    logger.info("HTML saved to bigflavor_source.html")
    
    # Find the table
    table = soup.find('table')
    if table:
        logger.info(f"Found table with class: {table.get('class')}")
        logger.info(f"Table ID: {table.get('id')}")
        
        # Get all rows
        rows = table.find_all('tr')
        logger.info(f"Found {len(rows)} rows")
        
        if len(rows) > 1:
            # Show first data row structure
            first_row = rows[1]
            logger.info("\nFirst row HTML:")
            print(first_row.prettify())
            
            cells = first_row.find_all(['td', 'th'])
            logger.info(f"\nFound {len(cells)} cells in first row")
            
            for i, cell in enumerate(cells):
                logger.info(f"Cell {i}: {cell.get_text(strip=True)[:50]}")
                if cell.find('a'):
                    link = cell.find('a')
                    logger.info(f"  - Link href: {link.get('href')}")
                    logger.info(f"  - Link class: {link.get('class')}")
    
    input("\nPress ENTER to close browser...")
    
finally:
    driver.quit()
