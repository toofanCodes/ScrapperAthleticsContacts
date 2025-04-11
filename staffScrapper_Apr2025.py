import requests
from bs4 import BeautifulSoup
import csv
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuration ---
# Input file containing target URLs (one per line, no header)
INPUT_CSV_PATH = 'target_urls.csv'
# Output file for scraped staff data
OUTPUT_CSV_PATH = 'staff_directory.csv'
# Log file for URLs that failed or had issues
ERROR_LOG_PATH = 'scrape_errors.txt'

# Regex pattern for typical North American phone numbers
# Allows for variations in separators (dash, dot, space)
PHONE_REGEX_PATTERN = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
# Regex pattern for mailto links (case-insensitive)
MAILTO_REGEX_PATTERN = re.compile(r'^mailto:', re.IGNORECASE)
# Specific row class pattern observed on some sites (adjust if needed)
GENERIC_ROW_CLASS_PATTERN = re.compile("s-table-body__row")

# Web request settings
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
REQUESTS_TIMEOUT = 15 # seconds

# Selenium settings
SELENIUM_WAIT_TIMEOUT = 15 # Max time to wait for elements (seconds)
SELENIUM_SLEEP_DELAY = 2 # Small delay after page load for JS rendering (seconds)

# --- Helper Functions ---

def _setup_selenium_driver():
    """Initializes and returns a headless Selenium WebDriver instance."""
    print("Setting up Selenium WebDriver...")
    options = Options()
    options.headless = True # Run in background without opening a browser window
    options.add_argument("--disable-gpu") # Often necessary for headless mode
    options.add_argument("--no-sandbox") # Important for running in restricted environments (like Docker)
    options.add_argument("--window-size=1920x1080") # Set a reasonable window size
    options.add_argument(f'user-agent={USER_AGENT}') # Set user agent for Selenium too
    try:
        # Automatically downloads/manages the correct ChromeDriver version
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        print("WebDriver setup complete.")
        return driver
    except Exception as e:
        print(f"FATAL: Failed to initialize Selenium WebDriver: {e}")
        print("Please ensure Chrome and Chromedriver are compatible or check network connection.")
        return None

def _find_contact_info(elements):
    """
    Searches through a list of BeautifulSoup elements (like <td> or <dd>)
    to find the first email (mailto link) and phone number.
    """
    email = ""
    phone = ""
    found_email = False
    found_phone = False

    for element in elements:
        # Look for mailto link first
        if not found_email:
            email_tag = element.find('a', href=MAILTO_REGEX_PATTERN)
            if email_tag:
                # Get text content if available, otherwise parse from href
                email_text = email_tag.get_text(strip=True)
                if email_text and '@' in email_text:
                    email = email_text
                else:
                    # Fallback: extract from href (remove 'mailto:')
                    href = email_tag.get('href', '')
                    if href.startswith('mailto:'):
                        email = href[len('mailto:'):]
                found_email = True

        # Look for phone number text
        if not found_phone:
            phone_match = PHONE_REGEX_PATTERN.search(element.get_text(" ", strip=True))
            if phone_match:
                phone = phone_match.group(0) # Get the matched phone number
                found_phone = True

        # Stop early if both found
        if found_email and found_phone:
            break

    return email, phone

# --- Extraction Strategies ---
# These functions attempt to parse staff info based on common HTML structures.
# They take the BeautifulSoup `soup` object, the `url`, and the `csv_writer`.
# They return the number of entries successfully extracted.

def _try_extract_from_sidearm_table(soup, url, csv_writer):
    """
    Attempts extraction from tables often used by Sidearm Sports websites,
    looking for rows with a specific class pattern.
    (Class: 's-table-body__row')
    """
    rows = soup.find_all('tr', class_=GENERIC_ROW_CLASS_PATTERN)
    if not rows:
        return 0 # Indicate no matching rows found

    entries_found = 0
    print(f"   Trying Sidearm-style table format... found {len(rows)} potential rows.")
    for row in rows:
        cells = row.find_all('td')
        # Expecting at least Name and Title columns
        if len(cells) < 2:
            continue

        # Column 1 often has image, Column 2 usually has Name link
        name_cell = cells[1] if len(cells) > 1 else None
        title_cell = cells[2] if len(cells) > 2 else None

        name = ""
        if name_cell:
            name_tag = name_cell.find('a')
            name = name_tag.get_text(strip=True) if name_tag else name_cell.get_text(strip=True)

        title = title_cell.get_text(strip=True) if title_cell else ""

        # Search all cells in the row for contact info
        email, phone = _find_contact_info(cells)

        if name: # Only write if we at least found a name
            csv_writer.writerow({
                'Name': name,
                'Email': email,
                'Position/Title': title,
                'Phone': phone,
                'Sport/Department': '', # This format often lacks department headers in the row
                'Source URL': url
            })
            entries_found += 1
    print(f"   -> Extracted {entries_found} entries using Sidearm-style table.")
    return entries_found

def _try_extract_from_generic_table(soup, url, csv_writer):
    """
    Attempts extraction from the first generic <table> found on the page.
    Handles simple category rows and assumes a Name, Title structure.
    """
    table = soup.find('table')
    if not table:
        return 0 # Indicate no table found

    entries_found = 0
    current_category = "General" # Default category
    print(f"   Trying generic table format...")

    for row in table.find_all('tr'):
        cells = row.find_all('td')
        if not cells:
            # Skip header rows (th) or empty rows
            continue

        # Simple check for a category heading row (one cell spanning columns or looking like a title)
        # This might need refinement for complex tables
        is_heading = (len(cells) == 1 and cells[0].get_text(strip=True)) or \
                     (cells[0].get('colspan') and len(cells[0].get_text(strip=True)) < 50 and not cells[0].find('a'))

        if is_heading:
            category_text = cells[0].get_text(" ", strip=True)
            if category_text: # Avoid setting empty categories
                current_category = category_text
                print(f"      Detected category: {current_category}")
            continue # Move to the next row after finding a category

        # --- Data Row Processing ---
        # Detect if the first column might be an image/avatar
        start_idx = 1 if cells[0].find('img') and len(cells) > 1 else 0

        # Extract Name (usually in the first or second cell)
        name = ""
        name_cell = cells[start_idx] if len(cells) > start_idx else None
        if name_cell:
            # Prefer link text if available
            name_anchor = name_cell.find('a')
            name = name_anchor.get_text(strip=True) if name_anchor else name_cell.get_text(" ", strip=True)

        # Extract Title (usually the cell after the name)
        title = cells[start_idx + 1].get_text(" ", strip=True) if len(cells) > start_idx + 1 else ""

        # Search all cells for email and phone
        email, phone = _find_contact_info(cells)

        # Write row if a name was found
        if name:
            csv_writer.writerow({
                'Name': name,
                'Email': email,
                'Position/Title': title,
                'Phone': phone,
                'Sport/Department': current_category,
                'Source URL': url
            })
            entries_found += 1

    print(f"   -> Extracted {entries_found} entries using generic table format.")
    return entries_found

def _try_extract_from_definition_list(soup, url, csv_writer):
    """
    Attempts extraction from definition lists (<dl>, <dt>, <dd>).
    Assumes <dt> contains the category/department and <dd> contains staff info.
    """
    definition_lists = soup.find_all('dl')
    if not definition_lists:
        return 0 # No definition lists found

    entries_found = 0
    print(f"   Trying definition list format...")

    for dl in definition_lists:
        current_category = "Unknown Department" # Default for this list
        for element in dl.find_all(['dt', 'dd']):
            if element.name == 'dt':
                # Update category when a <dt> (term/category) is encountered
                category_text = element.get_text(" ", strip=True)
                if category_text: # Ensure category isn't empty
                    current_category = category_text
                    print(f"      Detected category: {current_category}")
            elif element.name == 'dd':
                # Process <dd> (definition/details) for staff info
                dd_text = element.get_text(" ", strip=True)
                if not dd_text:
                    continue # Skip empty <dd> tags

                # Extract contact info first using the helper
                email, phone = _find_contact_info([element])

                # Simple text parsing for Name and Title (basic approach)
                # Assumes Name is usually first, Title follows. This is fragile.
                # Remove email/phone text to avoid confusion (if found in text)
                cleaned_text = dd_text
                if email:
                    cleaned_text = cleaned_text.replace(email, '')
                if phone:
                    cleaned_text = cleaned_text.replace(phone, '')

                # Attempt to split remaining text. Often separated by comma, title, etc.
                # This part is heuristic and might need site-specific tuning.
                parts = [part.strip() for part in cleaned_text.split(None, 1)] # Split only once
                name = parts[0] if parts else ""
                title = parts[1] if len(parts) > 1 else ""
                # Refine title: remove leftover common separators like '-' or ',' at the beginning
                title = re.sub(r"^[,\-–\s]+", "", title).strip()

                if name:
                    csv_writer.writerow({
                        'Name': name,
                        'Email': email,
                        'Position/Title': title,
                        'Phone': phone,
                        'Sport/Department': current_category,
                        'Source URL': url
                    })
                    entries_found += 1

    print(f"   -> Extracted {entries_found} entries using definition list format.")
    return entries_found


# --- Main Scraping Orchestrator ---

def scrape_directory(url, csv_writer, error_log_file, selenium_driver):
    """
    Fetches content from a URL (using requests, falling back to Selenium)
    and attempts various strategies to extract staff directory info.
    Logs errors and returns the number of entries found.
    """
    print(f"\nProcessing URL: {url}")
    soup = None
    page_content = None

    # 1. Try fetching with 'requests' first (faster, less resource intensive)
    try:
        print("   Attempting fetch with 'requests'...")
        response = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=REQUESTS_TIMEOUT)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        page_content = response.text
        print("   'requests' fetch successful.")
    except requests.exceptions.RequestException as e:
        print(f"   'requests' failed: {e}. Will try Selenium.")
        # Proceed to Selenium fallback

    # 2. If 'requests' failed or didn't get content, try Selenium
    if not page_content and selenium_driver:
        try:
            print("   Attempting fetch with Selenium (may take a moment)...")
            selenium_driver.get(url)
            # Wait for *some* common element to appear, suggesting page load. 'body' is safe.
            # Waiting for specific tables/rows might fail if the structure varies.
            WebDriverWait(selenium_driver, SELENIUM_WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # Give JavaScript a moment to render dynamic content after initial load
            print(f"   Page loaded, waiting {SELENIUM_SLEEP_DELAY}s for dynamic content...")
            time.sleep(SELENIUM_SLEEP_DELAY)
            page_content = selenium_driver.page_source
            print("   Selenium fetch successful.")
        except Exception as e:
            # Log Selenium errors specifically
            error_message = f"ERROR: Selenium failed for URL: {url}\n       Reason: {e}\n-------\n"
            print(f"   Selenium also failed: {e}")
            error_log_file.write(error_message)
            return 0 # Failed to get content from both methods

    elif not page_content and not selenium_driver:
         print("   'requests' failed and Selenium driver is not available. Skipping URL.")
         error_log_file.write(f"ERROR: Could not fetch URL (requests failed, no Selenium): {url}\n-------\n")
         return 0

    # 3. If we have page content, parse it with BeautifulSoup
    try:
        soup = BeautifulSoup(page_content, 'html.parser')
    except Exception as e:
        error_message = f"ERROR: BeautifulSoup parsing failed for URL: {url}\n       Reason: {e}\n-------\n"
        print(f"   BeautifulSoup parsing failed: {e}")
        error_log_file.write(error_message)
        return 0 # Cannot proceed without parsing

    # 4. Try extraction strategies in order of preference/commonality
    entries_found = 0

    # Strategy 1: Specific Sidearm table format
    if not entries_found:
        entries_found = _try_extract_from_sidearm_table(soup, url, csv_writer)

    # Strategy 2: Generic tables
    if not entries_found:
        entries_found = _try_extract_from_generic_table(soup, url, csv_writer)

    # Strategy 3: Definition lists
    if not entries_found:
        entries_found = _try_extract_from_definition_list(soup, url, csv_writer)

    # 5. Log if no data was extracted after trying all methods
    if entries_found == 0:
        warning_message = f"WARNING: No staff data extracted from URL: {url}\n         (Tried Sidearm Table, Generic Table, Definition List formats)\n-------\n"
        print(f"   No data extracted using known formats.")
        error_log_file.write(warning_message)

    return entries_found

# --- Main Execution ---

if __name__ == "__main__":
    print("Starting Staff Directory Scraper...")

    # Attempt to set up Selenium (might fail)
    driver = _setup_selenium_driver()

    # Read target URLs from input file
    urls_to_scrape = []
    try:
        # Use utf-8-sig to handle potential BOM (Byte Order Mark) in CSV saved by Excel
        with open(INPUT_CSV_PATH, 'r', newline='', encoding='utf-8-sig') as infile:
            # Simple reader assuming one URL per line
            urls_to_scrape = [line.strip() for line in infile if line.strip() and line.strip().lower().startswith('http')]
        print(f"Read {len(urls_to_scrape)} URLs from {INPUT_CSV_PATH}")
    except FileNotFoundError:
        print(f"FATAL: Input file not found at {INPUT_CSV_PATH}")
        if driver: driver.quit()
        exit(1) # Exit if input file is missing
    except Exception as e:
        print(f"FATAL: Error reading input file {INPUT_CSV_PATH}: {e}")
        if driver: driver.quit()
        exit(1) # Exit on other read errors


    # Open output CSV and error log files
    try:
        with open(OUTPUT_CSV_PATH, 'w', newline='', encoding='utf-8') as csvfile, \
             open(ERROR_LOG_PATH, 'w', encoding='utf-8') as errfile:

            # Define CSV header
            fieldnames = ['Name', 'Email', 'Position/Title', 'Phone', 'Sport/Department', 'Source URL']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader() # Write the header row

            total_entries_extracted = 0
            urls_failed_or_empty = 0

            # Process each URL
            for i, url in enumerate(urls_to_scrape):
                print(f"--- URL {i+1} of {len(urls_to_scrape)} ---")
                try:
                    result = scrape_directory(url, writer, errfile, driver)
                    if result > 0:
                        total_entries_extracted += result
                    else:
                        urls_failed_or_empty += 1
                except Exception as e:
                    # Catch unexpected errors during the processing of a single URL
                    print(f"   UNEXPECTED ERROR processing {url}: {e}")
                    errfile.write(f"FATAL ERROR: Unexpected issue processing URL: {url}\n       Reason: {e}\n-------\n")
                    urls_failed_or_empty += 1
                # Optional: Add a small delay between requests to be polite to servers
                # time.sleep(0.5)

            # --- Summary ---
            print("\n--- Scraping Complete ---")
            print(f"Total URLs processed: {len(urls_to_scrape)}")
            print(f"Total staff entries extracted: {total_entries_extracted}")
            print(f"URLs with errors or no data found: {urls_failed_or_empty}")
            print(f"Results saved to: {OUTPUT_CSV_PATH}")
            print(f"Errors/Warnings logged to: {ERROR_LOG_PATH}")

    except IOError as e:
        print(f"FATAL: Could not open or write to output/error files ({OUTPUT_CSV_PATH} / {ERROR_LOG_PATH}): {e}")
    finally:
        # Important: Always close the Selenium driver cleanly
        if driver:
            print("Closing Selenium WebDriver...")
            driver.quit()
            print("WebDriver closed.")

    print("Script finished.")