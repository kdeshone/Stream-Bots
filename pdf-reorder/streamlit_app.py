import io
import re
import tempfile
from pathlib import Path

import fitz
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image
from pypdf import PdfReader, PdfWriter
from streamlit_drawable_canvas import st_canvas

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AICE Textbook Reorder + TOC",
    page_icon="📚",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# Session state defaults
# ─────────────────────────────────────────────────────────────────────────────
_DEFAULTS = {
    "step": 1,
    "pdf_bytes": None,
    "pdf_name": None,
    "page_count": 0,
    "regions": [],        # [{x,y,w,h,_source_page}, ...] normalised 0-1
    "page_order": [],     # [{pdf_index, detected_number}, ...]
    "page_texts": {},     # {pdf_index: str} – full-page OCR cache
    "toc_entries": [],    # [{page_num, title, level}, ...]
    "output_pdf": None,   # bytes
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ─────────────────────────────────────────────────────────────────────────────
# PDF / OCR helpers
# ─────────────────────────────────────────────────────────────────────────────

def render_page(page_num: int, scale: float = 1.5) -> Image.Image:
    doc = fitz.open(stream=st.session_state.pdf_bytes, filetype="pdf")
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def ocr_region(page_num: int, bbox: dict) -> str:
    """OCR a normalised rectangle on a page (digits only)."""
    doc = fitz.open(stream=st.session_state.pdf_bytes, filetype="pdf")
    page = doc[page_num]
    pw, ph = page.rect.width, page.rect.height
    clip = fitz.Rect(
        bbox["x"] * pw,
        bbox["y"] * ph,
        (bbox["x"] + bbox["w"]) * pw,
        (bbox["y"] + bbox["h"]) * ph,
    )
    pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=clip, colorspace=fitz.csRGB)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
    doc.close()
    # Ensure minimum size for Tesseract
    if img.width < 80 or img.height < 40:
        s = max(80 / img.width, 40 / img.height)
        img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    return pytesseract.image_to_string(
        img, config="--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789"
    ).strip()


def ocr_full_page(page_num: int) -> str:
    """Full-page OCR, cached in session state."""
    if page_num in st.session_state.page_texts:
        return st.session_state.page_texts[page_num]
    doc = fitz.open(stream=st.session_state.pdf_bytes, filetype="pdf")
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
    doc.close()
    text = pytesseract.image_to_string(img, config="--psm 3 --oem 3")
    st.session_state.page_texts[page_num] = text
    return text


def parse_number(text: str):
    nums = re.findall(r"\d+", text)
    return int(nums[0]) if nums else None


# ─────────────────────────────────────────────────────────────────────────────
# Heading detection  (AICE Thinking Skills–aware)
# ─────────────────────────────────────────────────────────────────────────────

# (pattern, heading_level)  — level 1 = chapter, 2 = section, 3 = sub-section
_HEADING_RE = [
    (re.compile(r"^\s*(unit|chapter|part)\s+\d+", re.I), 1),
    (re.compile(r"^\s*\d+[\.\d]*\s+[A-Z]", re.I), 2),
    (re.compile(
        r"^\s*(introduction|conclusion|summary|glossary|index|appendix|"
        r"preface|foreword|exam\s+practice|key\s+terms?|skills?\s+focus|"
        r"exercises?|answers?|how\s+to\s+use|acknowledgements?|contents?|"
        r"critical\s+thinking|argument\s+analysis|reasoning|inference|"
        r"assumption|flaw|credibility|evidence|data\s+analysis|"
        r"decision[\s-]making|problem[\s-]solving)\s*[:\.]?$",
        re.I,
    ), 2),
]


def detect_headings(text: str, display_page: int) -> list[dict]:
    entries = []
    lines = text.splitlines()
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or len(line) < 3 or len(line) > 120:
            continue

        score, level = 0, 3

        for pattern, lvl in _HEADING_RE:
            if pattern.search(line):
                score += 5
                level = min(level, lvl)
                break

        if len(line) < 60:
            score += 1
        if len(line) < 35:
            score += 1
        if line.isupper() and len(line) > 3:
            score += 3
            level = min(level, 2)
        elif line.istitle():
            score += 1
        if line.endswith(":") and len(line) < 50:
            score += 2
        # Blank line after → paragraph separator typical of headings
        if i + 1 < len(lines) and not lines[i + 1].strip():
            score += 1

        if score >= 4:
            entries.append({"page_num": display_page, "title": line, "level": level})

    return entries


# ─────────────────────────────────────────────────────────────────────────────
# TOC page (PDF) generator
# ─────────────────────────────────────────────────────────────────────────────

def build_toc_pdf_pages(entries: list[dict]) -> bytes:
    """Return bytes of a fitz-generated PDF containing the visual TOC."""
    doc = fitz.open()
    W, H = 595, 842  # A4 points

    def new_page():
        p = doc.new_page(width=W, height=H)
        return p, 80.0

    page, y = new_page()
    page.insert_text(
        (W / 2 - 70, 50), "Table of Contents", fontsize=18, fontname="helv"
    )

    for entry in entries:
        indent = 20 * (entry["level"] - 1)
        fs = max(8, 12 - entry["level"])
        font = "helv-bold" if entry["level"] == 1 else "helv"

        title = entry["title"]
        if len(title) > 75:
            title = title[:72] + "…"
        pg_str = str(entry["page_num"])

        # Right-align page number
        pg_w = fitz.get_text_length(pg_str, fontname=font, fontsize=fs)
        page.insert_text((54 + indent, y), title, fontsize=fs, fontname=font)
        page.insert_text((W - 54 - pg_w, y), pg_str, fontsize=fs, fontname=font)

        y += fs + 7
        if entry["level"] == 1:
            y += 3

        if y > H - 60:
            page, y = new_page()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Final PDF assembly
# ─────────────────────────────────────────────────────────────────────────────

def assemble_pdf(
    order: list[dict],
    toc_entries: list[dict],
    include_toc_page: bool,
) -> bytes:
    src = PdfReader(io.BytesIO(st.session_state.pdf_bytes))
    writer = PdfWriter()

    toc_page_count = 0
    if include_toc_page and toc_entries:
        toc_bytes = build_toc_pdf_pages(toc_entries)
        toc_reader = PdfReader(io.BytesIO(toc_bytes))
        for pg in toc_reader.pages:
            writer.add_page(pg)
        toc_page_count = len(toc_reader.pages)

    for item in order:
        writer.add_page(src.pages[item["pdf_index"]])

    # PDF outline bookmarks (jump-to links in a PDF viewer)
    if toc_entries:
        num_to_writer_idx = {}
        for i, item in enumerate(order):
            n = item["detected_number"]
            if n is not None and n not in num_to_writer_idx:
                num_to_writer_idx[n] = toc_page_count + i

        for entry in toc_entries:
            pg_num = entry["page_num"]
            writer_idx = num_to_writer_idx.get(pg_num)
            if writer_idx is not None:
                try:
                    writer.add_outline_item(entry["title"], writer_idx)
                except Exception:
                    pass

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Progress indicator
# ─────────────────────────────────────────────────────────────────────────────

STEP_LABELS = ["Upload", "Mark regions", "Reorder", "Build TOC", "Download"]


def draw_steps():
    cols = st.columns(len(STEP_LABELS))
    for i, (col, label) in enumerate(zip(cols, STEP_LABELS)):
        n = i + 1
        if n < st.session_state.step:
            col.markdown(f"✅ ~~{label}~~")
        elif n == st.session_state.step:
            col.markdown(f"**🔵 {label}**")
        else:
            col.markdown(f"⚪ {label}")


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

st.title("📚 AICE Textbook — Reorder & Table of Contents")
st.caption(
    "Upload a scanned PDF, mark where page numbers appear, reorder pages by "
    "detected number, then auto-generate an editable table of contents."
)
draw_steps()
st.divider()


# ═══════════════════════════════════════════════════════════════════
# STEP 1 — Upload
# ═══════════════════════════════════════════════════════════════════
if st.session_state.step == 1:
    st.subheader("Step 1 — Upload your scanned PDF")

    uploaded = st.file_uploader(
        "Choose a PDF file (up to 500 MB)", type=["pdf"], label_visibility="collapsed"
    )
    if uploaded:
        data = uploaded.read()
        doc = fitz.open(stream=data, filetype="pdf")
        n = doc.page_count
        doc.close()
        st.session_state.pdf_bytes = data
        st.session_state.pdf_name = uploaded.name
        st.session_state.page_count = n
        st.success(f"**{uploaded.name}** — {n} pages loaded.")

        if st.button("Next: Mark page number location →", type="primary"):
            st.session_state.step = 2
            st.rerun()


# ═══════════════════════════════════════════════════════════════════
# STEP 2 — Mark page-number regions
# ═══════════════════════════════════════════════════════════════════
elif st.session_state.step == 2:
    st.subheader("Step 2 — Mark where page numbers appear")
    st.markdown(
        "Select any page, then **drag a rectangle** over the page number. "
        "If odd and even pages have numbers in different corners, add a region for each."
    )

    left_col, right_col = st.columns([3, 1], gap="large")

    with left_col:
        page_pick = st.number_input(
            "Page to display",
            min_value=1,
            max_value=st.session_state.page_count,
            value=1,
            step=1,
            help="Change this to browse different pages",
        )
        page_idx = page_pick - 1

        img = render_page(page_idx, scale=1.5)
        canvas_w, canvas_h = img.width, img.height

        canvas_result = st_canvas(
            fill_color="rgba(255, 80, 70, 0.15)",
            stroke_width=3,
            stroke_color="#e63946",
            background_image=img,
            update_streamlit=True,
            height=canvas_h,
            width=canvas_w,
            drawing_mode="rect",
            key=f"canvas_{page_idx}",
        )

    with right_col:
        st.markdown("**How to mark a region:**")
        st.markdown(
            "1. Choose the page with `Page to display`\n"
            "2. Click and drag on the page to draw a box around the page number\n"
            "3. Click **Add region** below"
        )
        st.divider()

        # Extract last drawn rectangle
        pending_bbox = None
        if canvas_result.json_data:
            objs = canvas_result.json_data.get("objects", [])
            rects = [o for o in objs if o.get("type") == "rect"]
            if rects:
                obj = rects[-1]
                rx = obj["left"] / canvas_w
                ry = obj["top"] / canvas_h
                rw = (obj["width"] * obj.get("scaleX", 1)) / canvas_w
                rh = (obj["height"] * obj.get("scaleY", 1)) / canvas_h
                if rw > 0.01 and rh > 0.005:
                    pending_bbox = {"x": rx, "y": ry, "w": rw, "h": rh}
                    st.info(
                        f"Box drawn on page {page_pick}  \n"
                        f"`x={rx:.2f}  y={ry:.2f}  w={rw:.2f}  h={rh:.2f}`"
                    )

        if st.button(
            "➕ Add this region",
            disabled=pending_bbox is None,
            type="primary",
        ):
            entry = {**pending_bbox, "_source_page": page_pick}
            st.session_state.regions.append(entry)
            st.rerun()

        st.divider()
        st.markdown("**Saved regions:**")
        if not st.session_state.regions:
            st.caption("None yet.")
        else:
            for i, r in enumerate(st.session_state.regions):
                c1, c2 = st.columns([4, 1])
                c1.write(f"Region {i + 1}  *(page {r['_source_page']})*")
                if c2.button("✕", key=f"del_{i}"):
                    st.session_state.regions.pop(i)
                    st.rerun()

        if st.session_state.regions:
            st.divider()
            st.markdown("**Test on current page:**")
            if st.button("👁 Preview OCR"):
                for i, r in enumerate(st.session_state.regions):
                    raw = ocr_region(page_idx, r)
                    num = parse_number(raw)
                    st.write(
                        f"Region {i + 1}: `{raw or '(empty)'}` "
                        f"→ **{num if num is not None else 'not detected'}**"
                    )

    st.divider()
    nav1, nav2 = st.columns(2)
    if nav1.button("← Back"):
        st.session_state.step = 1
        st.rerun()
    if nav2.button(
        "Next: Reorder →",
        disabled=not st.session_state.regions,
        type="primary",
    ):
        st.session_state.step = 3
        st.rerun()


# ═══════════════════════════════════════════════════════════════════
# STEP 3 — Reorder
# ═══════════════════════════════════════════════════════════════════
elif st.session_state.step == 3:
    st.subheader("Step 3 — Detect page numbers & reorder")

    if not st.session_state.page_order:
        st.info(
            f"Ready to OCR all **{st.session_state.page_count}** pages using "
            f"{len(st.session_state.regions)} marked region(s)."
        )
        if st.button("▶ Run detection", type="primary"):
            prog = st.progress(0, text="Scanning pages…")
            numbered, unknown = [], []
            total = st.session_state.page_count

            for i in range(total):
                found = None
                for bbox in st.session_state.regions:
                    raw = ocr_region(i, bbox)
                    n = parse_number(raw)
                    if n is not None:
                        found = n
                        break
                if found is not None:
                    numbered.append({"pdf_index": i, "detected_number": found})
                else:
                    unknown.append({"pdf_index": i, "detected_number": None})
                prog.progress((i + 1) / total, text=f"Page {i + 1} / {total}")

            numbered.sort(key=lambda x: x["detected_number"])
            st.session_state.page_order = numbered + unknown
            st.rerun()

    else:
        order = st.session_state.page_order
        found = sum(1 for p in order if p["detected_number"] is not None)
        total = len(order)

        st.success(f"Detected page numbers on **{found} / {total}** pages.")
        if total - found:
            st.warning(
                f"{total - found} page(s) with no detected number will be placed at the end."
            )

        with st.expander("Preview reordered sequence (first 40 pages)"):
            st.table(
                pd.DataFrame(
                    [
                        {
                            "Order": i + 1,
                            "PDF position": p["pdf_index"] + 1,
                            "Detected page #": p["detected_number"] or "—",
                        }
                        for i, p in enumerate(order[:40])
                    ]
                )
            )

        nav1, nav2, nav3 = st.columns(3)
        if nav1.button("← Back"):
            st.session_state.page_order = []
            st.session_state.step = 2
            st.rerun()
        if nav2.button("↩ Re-run"):
            st.session_state.page_order = []
            st.rerun()
        if nav3.button("Next: Build TOC →", type="primary"):
            st.session_state.step = 4
            st.rerun()


# ═══════════════════════════════════════════════════════════════════
# STEP 4 — Table of contents
# ═══════════════════════════════════════════════════════════════════
elif st.session_state.step == 4:
    st.subheader("Step 4 — Table of Contents")

    if not st.session_state.toc_entries:
        st.markdown(
            "The tool will OCR every page and look for headings using "
            "AICE Thinking Skills–aware keyword detection.  "
            "You can review and edit the results before downloading."
        )
        if st.button("🔍 Scan all pages for headings", type="primary"):
            prog = st.progress(0, text="Scanning for headings…")
            all_entries: list[dict] = []
            order = st.session_state.page_order

            for i, item in enumerate(order):
                pdf_idx = item["pdf_index"]
                display_pg = item["detected_number"] or (i + 1)
                text = ocr_full_page(pdf_idx)
                all_entries.extend(detect_headings(text, display_pg))
                prog.progress((i + 1) / len(order), text=f"Page {i + 1} / {len(order)}")

            # Deduplicate entries with the same title on the same page
            seen: set[tuple] = set()
            deduped: list[dict] = []
            for e in all_entries:
                key = (e["title"].lower(), e["page_num"])
                if key not in seen:
                    deduped.append(e)
                    seen.add(key)

            st.session_state.toc_entries = deduped
            st.rerun()

    else:
        entries = st.session_state.toc_entries
        st.success(f"Found **{len(entries)}** heading(s). Edit the table below — delete any false positives.")

        df = pd.DataFrame(
            [{"Page #": e["page_num"], "Level": e["level"], "Title": e["title"]} for e in entries]
        )
        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Level": st.column_config.SelectboxColumn(
                    "Level", options=[1, 2, 3], required=True,
                    help="1 = chapter/unit, 2 = section, 3 = sub-section",
                ),
                "Page #": st.column_config.NumberColumn("Page #", min_value=1),
            },
        )
        # Sync edits back to session state
        st.session_state.toc_entries = [
            {"page_num": int(r["Page #"]), "level": int(r["Level"]), "title": str(r["Title"])}
            for _, r in edited_df.iterrows()
            if str(r.get("Title", "")).strip()
        ]

        # Live TOC preview
        with st.expander("📋 TOC preview", expanded=True):
            for e in st.session_state.toc_entries[:60]:
                pad = "&nbsp;" * (6 * (e["level"] - 1))
                bold_open  = "<b>" if e["level"] == 1 else ""
                bold_close = "</b>" if e["level"] == 1 else ""
                colour = "#555" if e["level"] > 1 else "#111"
                lvl = e["level"]
                title = e["title"]
                pg = e["page_num"]
                fs = 15 - lvl
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;"
                    f"color:{colour};font-size:{fs}px'>"
                    f"<span>{pad}{bold_open}{title}{bold_close}</span>"
                    f"<span style='color:#999;min-width:3rem;text-align:right'>{pg}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            if len(st.session_state.toc_entries) > 60:
                st.caption(f"… and {len(st.session_state.toc_entries) - 60} more entries")

        nav1, nav2, nav3 = st.columns(3)
        if nav1.button("← Back"):
            st.session_state.step = 3
            st.rerun()
        if nav2.button("↩ Re-scan"):
            st.session_state.toc_entries = []
            st.session_state.page_texts = {}
            st.rerun()
        if nav3.button("Next: Download →", type="primary"):
            st.session_state.step = 5
            st.rerun()


# ═══════════════════════════════════════════════════════════════════
# STEP 5 — Download
# ═══════════════════════════════════════════════════════════════════
elif st.session_state.step == 5:
    st.subheader("Step 5 — Download")

    include_toc = st.checkbox(
        "Prepend a Table of Contents page to the PDF", value=True
    )
    st.caption(
        "PDF bookmarks (jump-to links visible in most PDF readers) are always included."
    )

    if st.button("📦 Build final PDF", type="primary"):
        with st.spinner("Assembling PDF…"):
            result = assemble_pdf(
                st.session_state.page_order,
                st.session_state.toc_entries,
                include_toc_page=include_toc,
            )
        st.session_state.output_pdf = result
        st.success("PDF ready!")

    if st.session_state.output_pdf:
        base = Path(st.session_state.pdf_name or "output").stem
        st.download_button(
            label="⬇ Download reordered PDF",
            data=st.session_state.output_pdf,
            file_name=f"{base}_reordered.pdf",
            mime="application/pdf",
            type="primary",
        )

        if st.session_state.toc_entries:
            st.divider()
            st.markdown("#### Table of Contents at a glance")
            for e in st.session_state.toc_entries:
                pad = "　" * (e["level"] - 1)
                marker = "**" if e["level"] == 1 else ""
                st.markdown(
                    f"{pad}{marker}{e['title']}{marker}"
                    f"{'  —  p. ' + str(e['page_num'])}"
                )

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("← Back"):
        st.session_state.step = 4
        st.rerun()
    if c2.button("🔄 Start over"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()
