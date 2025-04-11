### ✅ `README.md` for `staffScrapper_Apr2025.py`

```markdown
# 🏫 Staff Directory Scraper for Athletic Websites

This Python script automates the extraction of staff contact information (such as name, email, title, department, and phone number) from college athletics staff directories. It is designed to handle diverse and dynamic HTML structures, including those rendered with JavaScript.

---

## 📌 Features

- ✅ Scrapes data from multiple URLs using a `.csv` input list
- ✅ Handles complex HTML structures (including JavaScript-rendered content with Selenium)
- ✅ Extracts:
  - Full name
  - Position / title
  - Email address (even from obfuscated JS formats)
  - Phone number
  - Associated department or sport (when available)
  - Source URL
- ✅ Gracefully handles errors and logs them for debugging
- ✅ Supports headless scraping for automation pipelines

---

## 📂 File Structure

| File | Description |
|------|-------------|
| `staffScrapper_Apr2025.py` | Main scraper script |
| `target_urls.csv` | Input CSV with URLs (one per line) |
| `staff_directory.csv` | Output file with scraped data |
| `scrape_errors.txt` | Error Output log showing failed URLs and parsing issues |

---

## 🛠 Requirements

Install dependencies using:

```bash
pip install -r requirements.txt
```

### `requirements.txt` content:

```
requests
beautifulsoup4
selenium
webdriver-manager
```

---

## 📥 Usage

1. Prepare a CSV file named `target_urls.csv` with this structure:

```
https://example.edu/staff-directory
https://another.edu/staff-directory
...
```

> **Note**: No header row is required.

2. Run the script:

```bash
python staffScrapper_Apr2025.py
```

3. Output will be saved as:
   - `staff_directory.csv` — extracted contact info
   - `scrape_errors.txt` — any URLs that couldn’t be processed

---

## 🧠 How It Works

- Tries multiple parsing strategies (table, definition list, generic row matching)
- Uses `Selenium` headless Chrome if the page is JavaScript-heavy
- Identifies email patterns even when obfuscated with JS `document.write` or `innerText` replacement
- Categorizes staff into departments based on headings where possible

---

## ⚠️ Known Limitations

- Pages with extreme JavaScript complexity may not be 100% compatible
- Obfuscated email formats beyond standard patterns may be missed
- Sites using CAPTCHAs or anti-bot protection are unsupported


## 👤 Author

**Jaya Saran Teja Pavuluri**  
[GitHub](https://github.com/toofanCodes)  
📧 saran.in.usa@gmail.com

---

## 📝 License

MIT License – do what you want, just don't spam the scrapped contacts 😉
