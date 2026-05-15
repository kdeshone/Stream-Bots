# PDF Page Reorder

Upload a scanned PDF, mark where the page numbers appear on a few pages, and download a correctly ordered PDF.

## How it works

1. **Upload** your scanned PDF
2. **Mark regions** — click any page thumbnail and drag to draw a box around where the page number is printed. Repeat on a second page if odd and even pages have numbers in different positions (e.g., alternating corners)
3. **Preview OCR** — the tool shows you what numbers it reads from a sample of pages so you can confirm the region is correct
4. **Download** — pages are sorted by detected number; any pages where a number couldn't be found are placed at the end

## Setup

### System requirement

You need [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed:

```bash
# Ubuntu / Debian
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract

# Windows — download installer from:
# https://github.com/UB-Mannheim/tesseract/wiki
```

### Python dependencies

```bash
pip install -r requirements.txt
```

### Run

```bash
python app.py
# Open http://localhost:5000
```

## Command-line alternative

If you prefer a script, `reorder_cli.py` can fix the common single-sided scan pattern (odd pages first, then reversed even pages) without OCR:

```bash
python reorder_cli.py scanned_book.pdf
python reorder_cli.py scanned_book.pdf -o fixed.pdf
python reorder_cli.py scanned_book.pdf --order 1,3,5,2,4,6
```

## Tips for best OCR results

- Make sure the box you draw tightly surrounds just the page number — extra text in the region reduces accuracy
- If the number is printed faintly, try a larger region with a bit of padding around the digit
- Page numbers in headers/footers with roman numerals won't be detected (digits only); those pages will appear at the end and you can manually move them
