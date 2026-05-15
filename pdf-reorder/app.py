import io
import os
import re
import uuid
import tempfile
from pathlib import Path

import fitz  # pymupdf
import pytesseract
from PIL import Image
from flask import Flask, jsonify, render_template, request, send_file
from pypdf import PdfReader, PdfWriter

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

TEMP_DIR = Path(tempfile.gettempdir()) / "pdf_reorder"
TEMP_DIR.mkdir(exist_ok=True)

RENDER_DPI = 1.5   # matrix scale for thumbnails (~108 DPI)
OCR_DPI    = 4.0   # matrix scale for OCR crops (~288 DPI)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def session_dir(sid: str) -> Path:
    d = TEMP_DIR / sid
    d.mkdir(exist_ok=True)
    return d


def pdf_path(sid: str) -> Path:
    return session_dir(sid) / "input.pdf"


def render_page_image(sid: str, page_num: int, scale: float = RENDER_DPI) -> bytes:
    doc = fitz.open(str(pdf_path(sid)))
    page = doc[page_num]
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    data = pix.tobytes("png")
    doc.close()
    return data


def ocr_region(sid: str, page_num: int, bbox: dict) -> str:
    """
    OCR a rectangular region of a page.
    bbox: {x, y, w, h} as fractions of the page (0.0–1.0).
    Returns raw OCR string (digits only config).
    """
    doc = fitz.open(str(pdf_path(sid)))
    page = doc[page_num]
    pw, ph = page.rect.width, page.rect.height

    x0 = bbox["x"] * pw
    y0 = bbox["y"] * ph
    x1 = (bbox["x"] + bbox["w"]) * pw
    y1 = (bbox["y"] + bbox["h"]) * ph

    mat = fitz.Matrix(OCR_DPI, OCR_DPI)
    clip = fitz.Rect(x0, y0, x1, y1)
    pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csRGB)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()

    # Upscale tiny crops so Tesseract has enough pixels
    min_dim = 60
    if img.width < min_dim or img.height < min_dim:
        scale = max(min_dim / img.width, min_dim / img.height)
        img = img.resize(
            (int(img.width * scale), int(img.height * scale)),
            Image.LANCZOS,
        )

    # Greyscale + mild contrast boost helps digit recognition
    grey = img.convert("L")
    config = "--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789"
    return pytesseract.image_to_string(grey, config=config).strip()


def parse_number(text: str):
    nums = re.findall(r"\d+", text)
    return int(nums[0]) if nums else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return jsonify(error="No file uploaded"), 400
    f = request.files["pdf"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify(error="Please upload a PDF file"), 400

    sid = str(uuid.uuid4())
    f.save(str(pdf_path(sid)))

    try:
        doc = fitz.open(str(pdf_path(sid)))
        count = doc.page_count
        doc.close()
    except Exception as e:
        return jsonify(error=f"Could not read PDF: {e}"), 500

    return jsonify(session_id=sid, page_count=count)


@app.route("/page/<sid>/<int:page_num>")
def get_page(sid, page_num):
    p = pdf_path(sid)
    if not p.exists():
        return "Session not found", 404
    try:
        data = render_page_image(sid, page_num)
        return send_file(io.BytesIO(data), mimetype="image/png")
    except Exception as e:
        return str(e), 500


@app.route("/ocr-preview", methods=["POST"])
def ocr_preview():
    """
    Test OCR for given regions on a sample of pages.
    Body: { session_id, regions: [{x,y,w,h}, ...], sample_pages: [0,1,2,...] }
    Returns: [{ page: N, results: ["12", "", "7", ...] }]
    """
    data = request.json or {}
    sid = data.get("session_id")
    regions = data.get("regions", [])
    sample = data.get("sample_pages", [])

    if not sid or not regions:
        return jsonify(error="Missing session_id or regions"), 400

    p = pdf_path(sid)
    if not p.exists():
        return jsonify(error="Session expired or not found"), 404

    rows = []
    for pg in sample:
        region_texts = []
        chosen = None
        for bbox in regions:
            text = ocr_region(sid, pg, bbox)
            region_texts.append(text)
            if chosen is None and parse_number(text) is not None:
                chosen = parse_number(text)
        rows.append({"page": pg, "region_texts": region_texts, "detected": chosen})

    return jsonify(rows=rows)


@app.route("/reorder-by-ocr", methods=["POST"])
def reorder_by_ocr():
    """
    OCR every page using the supplied regions, sort by detected page number,
    append any undetected pages at the end, return the reordered PDF.
    Body: { session_id, regions: [{x,y,w,h}, ...] }
    """
    data = request.json or {}
    sid = data.get("session_id")
    regions = data.get("regions", [])

    if not sid or not regions:
        return jsonify(error="Missing session_id or regions"), 400

    p = pdf_path(sid)
    if not p.exists():
        return jsonify(error="Session expired"), 404

    reader = PdfReader(str(p))
    total = len(reader.pages)

    numbered = []   # (page_number, pdf_index)
    unknown  = []   # pdf_index

    for i in range(total):
        found = None
        for bbox in regions:
            text = ocr_region(sid, i, bbox)
            n = parse_number(text)
            if n is not None:
                found = n
                break
        if found is not None:
            numbered.append((found, i))
        else:
            unknown.append(i)

    numbered.sort(key=lambda t: t[0])

    writer = PdfWriter()
    order_info = []
    for pg_num, idx in numbered:
        writer.add_page(reader.pages[idx])
        order_info.append({"pdf_index": idx, "detected_number": pg_num})
    for idx in unknown:
        writer.add_page(reader.pages[idx])
        order_info.append({"pdf_index": idx, "detected_number": None})

    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)

    # Cache so /download can serve it
    out = session_dir(sid) / "output.pdf"
    out.write_bytes(buf.getvalue())

    return jsonify(order=order_info, session_id=sid, total=total)


@app.route("/download/<sid>")
def download(sid):
    out = session_dir(sid) / "output.pdf"
    if not out.exists():
        return "Not found", 404
    return send_file(
        str(out),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="reordered.pdf",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
