#!/usr/bin/env python3
"""
CLI tool to fix PDF page order after single-sided scanning of a duplex book.

Scanning workflow:
  1. Scan all front (odd) pages in order:   1, 3, 5, ...
  2. Flip the stack, scan back (even) pages — they come out reversed: ..., 6, 4, 2

Usage:
  python reorder_cli.py input.pdf                  # auto single-sided fix
  python reorder_cli.py input.pdf -o output.pdf    # specify output name
  python reorder_cli.py input.pdf --order 1,3,5,2,4,6  # custom order
"""

import argparse
import sys
from pathlib import Path
from pypdf import PdfReader, PdfWriter


def reorder_single_sided(reader: PdfReader) -> PdfWriter:
    total = len(reader.pages)
    half = total // 2
    fronts = list(range(half))
    backs = list(range(total - 1, half - 1, -1))

    writer = PdfWriter()
    for f, b in zip(fronts, backs):
        writer.add_page(reader.pages[f])
        writer.add_page(reader.pages[b])

    if total % 2 != 0:
        writer.add_page(reader.pages[half])

    return writer


def reorder_custom(reader: PdfReader, order: list[int]) -> PdfWriter:
    writer = PdfWriter()
    for i in order:
        writer.add_page(reader.pages[i - 1])
    return writer


def main():
    parser = argparse.ArgumentParser(description="Reorder PDF pages from a single-sided scan.")
    parser.add_argument("input", help="Input PDF file")
    parser.add_argument("-o", "--output", help="Output PDF file (default: input_reordered.pdf)")
    parser.add_argument(
        "--order",
        help="Custom comma-separated 1-based page order, e.g. --order 1,3,5,2,4,6",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else input_path.with_stem(input_path.stem + "_reordered")

    reader = PdfReader(str(input_path))
    total = len(reader.pages)
    print(f"Input: {input_path.name} ({total} pages)")

    if args.order:
        try:
            order = [int(x.strip()) for x in args.order.split(",")]
        except ValueError:
            print("Error: --order must be comma-separated integers", file=sys.stderr)
            sys.exit(1)
        if any(i < 1 or i > total for i in order):
            print(f"Error: page numbers must be between 1 and {total}", file=sys.stderr)
            sys.exit(1)
        writer = reorder_custom(reader, order)
        print(f"Custom order applied: {order}")
    else:
        writer = reorder_single_sided(reader)
        print("Single-sided scan interleaving applied.")

    with open(output_path, "wb") as f:
        writer.write(f)

    print(f"Output: {output_path} ({len(writer.pages)} pages)")


if __name__ == "__main__":
    main()
