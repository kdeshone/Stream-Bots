# PDF Reorder + Table of Contents

Streamlit app for fixing the page order of a scanned textbook and auto-generating
a navigable table of contents.  Built for AICE Thinking Skills, but works with any
scanned textbook.

## What it does

| Step | Description |
|------|-------------|
| **1 Upload** | Upload your scanned PDF (up to 500 MB) |
| **2 Mark regions** | Click any page thumbnail, drag to draw a box around where the page number is printed. Add a second region if odd/even pages have numbers in different corners |
| **3 Reorder** | OCRs every page in your marked region(s) and sorts pages by detected number |
| **4 Build TOC** | OCRs every page for headings using AICE TS–aware keyword detection, then shows you an editable table you can clean up |
| **5 Download** | Downloads the reordered PDF with an optional visual TOC page prepended and PDF bookmarks embedded |

## Setup

### 1. Install Tesseract OCR

```bash
# Ubuntu / Debian
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract

# Windows — https://github.com/UB-Mannheim/tesseract/wiki
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Run

```bash
streamlit run streamlit_app.py
```

Open http://localhost:8501 in your browser.

## Deploying to Streamlit Community Cloud

1. Push this repository to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect the repo
3. Set **Main file path** to `pdf-reorder/streamlit_app.py`
4. Add a `packages.txt` at the repo root containing:
   ```
   tesseract-ocr
   ```
   Streamlit Cloud runs this with `apt-get install` before starting the app.

## Command-line alternative

`reorder_cli.py` handles the common single-sided scan pattern (odd pages first,
reversed even pages) without OCR — useful for quick fixes:

```bash
python reorder_cli.py scanned_book.pdf
python reorder_cli.py scanned_book.pdf -o fixed.pdf
python reorder_cli.py scanned_book.pdf --order 1,3,5,2,4,6
```

## Tips

- Draw the page-number box **tightly** — extra text in the region reduces OCR accuracy
- If OCR misses many pages, try drawing on a different sample page and adding a second region
- The TOC scan is smart enough to find "Unit 1", "Chapter 2", "Skills Focus", "Key Terms", "Exam Practice", etc. out of the box
- After scanning, use the editable table to delete any false-positive headings before downloading
