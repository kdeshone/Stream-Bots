import os
import io
from flask import Flask, request, send_file, render_template, jsonify
from pypdf import PdfReader, PdfWriter

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB


def reorder_single_sided_scan(reader: PdfReader) -> PdfWriter:
    """
    Fixes page order for a book scanned with a single-sided scanner.

    Scanning workflow:
      1. Scan all front (odd) pages in order:  1, 3, 5, ...
      2. Flip the stack, scan back (even) pages — they come out reversed: ..., 6, 4, 2

    The PDF therefore contains pages in this physical order:
      [front_0, front_1, ..., front_n, back_n, ..., back_1, back_0]

    This function interleaves them back into reading order:
      front_0, back_0, front_1, back_1, ...
    """
    total = len(reader.pages)
    half = total // 2

    fronts = list(range(half))           # indices 0 .. half-1
    backs = list(range(total - 1, half - 1, -1))  # indices total-1 .. half (reversed)

    writer = PdfWriter()
    for f, b in zip(fronts, backs):
        writer.add_page(reader.pages[f])
        writer.add_page(reader.pages[b])

    # If there's an odd page out (e.g. a blank last back), append it
    if total % 2 != 0:
        writer.add_page(reader.pages[half])

    return writer


def reorder_custom(reader: PdfReader, order: list[int]) -> PdfWriter:
    """Reorder pages according to a user-supplied 1-based index list."""
    writer = PdfWriter()
    for i in order:
        writer.add_page(reader.pages[i - 1])
    return writer


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/reorder", methods=["POST"])
def reorder():
    if "pdf" not in request.files:
        return jsonify(error="No file uploaded"), 400

    pdf_file = request.files["pdf"]
    if not pdf_file.filename.lower().endswith(".pdf"):
        return jsonify(error="Please upload a PDF file"), 400

    mode = request.form.get("mode", "single_sided")

    try:
        reader = PdfReader(pdf_file)
        total_pages = len(reader.pages)

        if mode == "single_sided":
            if total_pages < 2:
                return jsonify(error="PDF must have at least 2 pages"), 400
            writer = reorder_single_sided_scan(reader)

        elif mode == "custom":
            raw = request.form.get("order", "")
            try:
                order = [int(x.strip()) for x in raw.split(",") if x.strip()]
            except ValueError:
                return jsonify(error="Custom order must be comma-separated page numbers"), 400
            if not order:
                return jsonify(error="Custom order is empty"), 400
            if any(i < 1 or i > total_pages for i in order):
                return jsonify(error=f"Page numbers must be between 1 and {total_pages}"), 400
            writer = reorder_custom(reader, order)

        else:
            return jsonify(error="Unknown mode"), 400

        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)

        base = os.path.splitext(pdf_file.filename)[0]
        return send_file(
            buf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{base}_reordered.pdf",
        )

    except Exception as e:
        return jsonify(error=f"Failed to process PDF: {str(e)}"), 500


@app.route("/page-count", methods=["POST"])
def page_count():
    if "pdf" not in request.files:
        return jsonify(error="No file"), 400
    pdf_file = request.files["pdf"]
    try:
        reader = PdfReader(pdf_file)
        return jsonify(pages=len(reader.pages))
    except Exception as e:
        return jsonify(error=str(e)), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
