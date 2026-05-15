# PDF Page Reorder

Fix the page order of a PDF scanned with a single-sided scanner from a double-sided book.

## The problem

When you scan a two-sided book with a one-sided scanner you typically:
1. Scan all the **front (odd) pages** face-down through the feeder — they land in your PDF in order: 1, 3, 5, …
2. **Flip the whole stack** and run the **back (even) pages** through — because the stack is now upside-down they land in *reverse* order: …, 6, 4, 2

This tool interleaves the two halves back into correct reading order.

## Web app (recommended)

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 in your browser, upload your PDF, and download the fixed version.

## Command-line tool

```bash
pip install pypdf

# Fix a single-sided scan automatically
python reorder_cli.py scanned_book.pdf

# Specify output filename
python reorder_cli.py scanned_book.pdf -o fixed_book.pdf

# Provide a completely custom page order
python reorder_cli.py scanned_book.pdf --order 1,3,5,7,8,6,4,2
```

## How the reordering works

Given a PDF with `N` pages:

| Position in PDF | Represents |
|----------------|------------|
| 0 … N/2-1 | Front (odd) pages: book pages 1, 3, 5, … |
| N/2 … N-1 (reversed) | Back (even) pages: book pages 2, 4, 6, … |

The algorithm zips `fronts` with `reversed(backs)` to produce the correct sequence.

## Modes

| Mode | Description |
|------|-------------|
| **Single-sided scan** (default) | Auto-interleave: assumes fronts in first half, reversed backs in second half |
| **Custom order** | Supply any comma-separated 1-based page list |
