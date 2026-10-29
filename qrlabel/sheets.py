"""Print-and-cut sheet layout, PDF writer and HTML writer.

Layout model
------------
A run of entries is turned into zero-padded label numbers (#01, #02, ...),
laid out on a grid ("cols x rows") over US Letter or A4 pages. Each label
holds one QR code (with a quiet zone and a number/text caption). A legend
maps every number back to its entry id and text; each label page carries the
legend head, and legend lines that do not fit spill onto trailing
legend-only pages.

Both writers are deterministic: same inputs produce byte-identical files.
"""

import html
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .qrcodes import encode_matrix

MM_PER_PT = 25.4 / 72.0
PT_PER_MM = 72.0 / 25.4

PAGE_SIZES = {"letter": (612.0, 792.0), "a4": (595.28, 841.89)}
PAGE_SIZE_NAMES = ", ".join(sorted(PAGE_SIZES))

MARGIN = 36.0
HEADER_HEIGHT = 24.0
GUTTER = 6.0
QPAD = 6.0          # padding inside each label
CAPTION_HEIGHT = 13.0
LEGEND_FONT = 8.0
LEGEND_LINE_HEIGHT = 12.0
LEGEND_MAX_TEXT = 66
MIN_LABEL_PT = 14.0 * PT_PER_MM
WIDE_CAPTION_PT = 40.0


class LayoutError(Exception):
    """Raised when the requested geometry cannot produce a printable sheet."""


@dataclass
class Entry:
    text: str
    label_id: str | None = None


@dataclass
class LabelItem:
    number: int
    entry_index: int
    matrix: list | None        # QR module grid; True = dark
    qr_modules: int            # modules per side of the QR
    quiet: int                 # quiet-zone modules drawn around the QR
    entry_id: str | None
    text: str


@dataclass
class Page:
    number: int
    labels: list = field(default_factory=list)   # LabelItem list (labels pages)
    legend_lines: list = field(default_factory=list)
    kind: str = "labels"                         # "labels" or "legend"


# ---------------------------------------------------------------------------
# Basic parsing helpers

def parse_grid(value):
    parts = str(value).replace(" ", "").lower().split("x")
    if len(parts) != 2:
        raise LayoutError(f"Grid must look like '3x4', got {value!r}")
    try:
        cols, rows = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise LayoutError(f"Grid must be integers 'CxR', got {value!r}") from exc
    if not (1 <= cols <= 30 and 1 <= rows <= 60):
        raise LayoutError("Grid columns must be 1..30 and rows 1..60")
    return cols, rows


def parse_page(name):
    key = str(name).lower()
    if key not in PAGE_SIZES:
        raise LayoutError(f"Unknown page size {name!r} (use {PAGE_SIZE_NAMES})")
    return PAGE_SIZES[key]


def normalize_ecl(ecl):
    key = str(ecl).upper()
    if key not in ("L", "M", "Q", "H"):
        raise LayoutError(f"ECC level must be L, M, Q or H, got {ecl!r}")
    return key


# ---------------------------------------------------------------------------
# Entries, labels and legend

def build_entries(texts, label_ids=None):
    """Turn raw strings into Entry items, one per nonblank text."""
    texts = [str(t).strip() for t in texts if str(t).strip()]
    if not texts:
        raise LayoutError("At least one non-empty entry is required")
    if label_ids:
        if len(label_ids) < len(texts):
            label_ids = list(label_ids) + [None] * (len(texts) - len(label_ids))
    else:
        label_ids = [None] * len(texts)
    return [Entry(text=t, label_id=ids) for t, ids in zip(texts, label_ids)]


def build_labels(entries, *, copies=1, start_number=1, ecl="M", quiet=4):
    """One LabelItem per printed label; entries are repeated --copies times."""
    if copies < 1:
        raise LayoutError("--copies must be at least 1")
    if not (2 <= int(quiet) <= 8):
        raise LayoutError("Quiet zone must be 2..8 modules")
    ecl = normalize_ecl(ecl)
    items = []
    number = start_number
    for _ in range(copies):
        for idx, entry in enumerate(entries):
            qr = encode_matrix(entry.text, ecl=ecl)
            items.append(LabelItem(
                number=number,
                entry_index=idx,
                matrix=qr["matrix"],
                qr_modules=qr["size"],
                quiet=quiet,
                entry_id=entry.label_id,
                text=entry.text,
            ))
            number += 1
    return items, number - 1


def legend_lines_for(labels, entries):
    """Legend lines for the whole run: all numbers of one entry share a line."""
    by_entry = {}
    order = []
    for item in labels:
        if item.entry_index not in by_entry:
            by_entry[item.entry_index] = []
            order.append(item.entry_index)
        by_entry[item.entry_index].append(item.number)
    lines = []
    for key in order:
        entry = entries[key]
        nums = ", ".join(f"#{n:02d}" for n in by_entry[key])
        text = entry.text.replace("\n", " / ")
        if len(text) > LEGEND_MAX_TEXT:
            text = text[: LEGEND_MAX_TEXT - 3].rstrip() + "..."
        ident = f" [{entry.label_id}]" if entry.label_id else ""
        lines.append(f"{nums}{ident}  {text}")
    return lines


def plan_layout(labels, entries, *, page="letter", grid, size_mm=None,
                title=None, legend=True):
    """Compute pages, label geometry and legend distribution."""
    page_w, page_h = parse_page(page)
    cols, rows = grid
    per_page = cols * rows

    printable_w = page_w - 2 * MARGIN
    auto_side = min(
        (printable_w - (cols - 1) * GUTTER) / cols,
        (page_h - 2 * MARGIN - HEADER_HEIGHT - (rows - 1) * GUTTER) / rows,
    )
    if size_mm is not None:
        if size_mm < 12 or size_mm > 250:
            raise LayoutError("--size must be between 12 and 250 mm")
        side = size_mm * PT_PER_MM
        if side > auto_side + 0.01:
            raise LayoutError(
                f"Label size {size_mm:.1f} mm does not fit on {page} pages "
                f"with grid {cols}x{rows} (max {auto_side * MM_PER_PT:.1f} mm)")
    else:
        side = auto_side
    if side < MIN_LABEL_PT:
        raise LayoutError(
            "Label side is too small for a printable QR code (min 14 mm); "
            "use a smaller grid, e.g. --grid 2x2")

    all_lines = legend_lines_for(labels, entries) if legend else []

    # All geometry below is measured from the TOP edge (top origin).
    grid_top = MARGIN + HEADER_HEIGHT
    grid_bottom = grid_top + rows * side + (rows - 1) * GUTTER
    per_page_lines = 0
    if legend and grid_bottom <= page_h - MARGIN:
        per_page_lines = int((page_h - MARGIN - grid_bottom) // LEGEND_LINE_HEIGHT)

    pages = []
    for i in range(0, len(labels), per_page):
        pages.append(Page(number=0, kind="labels",
                          labels=list(labels[i:i + per_page]),
                          legend_lines=all_lines[:per_page_lines]))

    if legend and len(all_lines) > per_page_lines:
        lines_per_page = max(1, int((page_h - 2 * MARGIN) // LEGEND_LINE_HEIGHT))
        leftover = all_lines[max(per_page_lines, 0):]
        for i in range(0, len(leftover), lines_per_page):
            pages.append(Page(number=0, kind="legend",
                              legend_lines=leftover[i:i + lines_per_page]))

    for n, page in enumerate(pages):
        page.number = n + 1

    return {
        "version": __version__,
        "pages": pages,
        "page": page,
        "page_size": (page_w, page_h),
        "grid": (cols, rows),
        "label_side_pt": side,
        "title": title or "QR Labels",
        "legend": legend,
        "grid_top_y": grid_top,
        "grid_bottom_y": grid_bottom,
    }


def make_sheet(texts, *, label_ids=None, page="letter", grid="3x4",
               size_mm=None, title=None, copies=1, ecl="M", quiet=4,
               start_number=1, legend=True):
    """High-level: entry texts -> a complete printable plan."""
    entries = build_entries(texts, label_ids=label_ids)
    labels, last_number = build_labels(entries, copies=copies,
                                       start_number=start_number, ecl=ecl,
                                       quiet=quiet)
    cols, rows = parse_grid(grid)
    if title is None:
        first = entries[0].text[:38]
        title = ("QR Labels - " + first + (" ..." if len(entries) > 1 else "")
                 if len(entries) == 1 else
                 f"QR Labels - {len(entries)} entries")
    layout = plan_layout(labels, entries, page=page, grid=(cols, rows),
                         size_mm=size_mm, title=title, legend=legend)
    layout["ecl"] = ecl
    layout["quiet"] = quiet
    layout["start_number"] = start_number
    layout["last_number"] = last_number
    return layout


# ---------------------------------------------------------------------------
# PDF writer (stdlib only, deterministic bytes, no timestamps)

def _f(v):
    s = f"{float(v):.2f}"
    return s[:-3] if s.endswith(".00") else s


def _pdf_text(text):
    raw = str(text).encode("cp1252", errors="replace")
    for byte, esc in ((0x5C, b"\\\\"), (0x28, b"\\("), (0x29, b"\\)")):
        raw = raw.replace(bytes([byte]), esc)
    return raw.decode("latin-1").replace("\n", " ")


def _truncate(text, max_chars):
    line = str(text).replace("\n", " / ")
    if len(line) > max_chars:
        return line[: max_chars - 3].rstrip() + "..."
    return line


def _footer(layout, page):
    width = layout["label_side_pt"] * MM_PER_PT
    if page.kind == "legend":
        note = "legend continuation"
    else:
        note = "cut along dashed lines"
    return (f"QR Label Maker {__version__} (offline)  -  page {page.number}  -  "
            f"{note}  -  labels approx {width:.0f} mm")


def _content_legend_head(layout, page):
    lines = []
    top = layout["page_size"][1]
    y = top - MARGIN - 16
    for line in page.legend_lines:
        lines.append(f"BT /F1 {_f(LEGEND_FONT)} Tf {_f(MARGIN)} {_f(y)} Td "
                     f"({_pdf_text(line)}) Tj ET")
        y -= LEGEND_LINE_HEIGHT
    return lines


def _page_content(layout, page):
    page_w, page_h = layout["page_size"]
    cols, rows = layout["grid"]
    side = layout["label_side_pt"]
    out = []

    if page.kind == "legend":
        out.append("0 g")
        out.append(f"BT /F2 10 Tf {_f(MARGIN)} {_f(page_h - MARGIN - 2)} Td "
                   f"({_pdf_text(layout['title'])}) Tj ET")
        y = page_h - MARGIN - 30
        for line in page.legend_lines:
            out.append(f"BT /F1 {_f(LEGEND_FONT)} Tf {_f(MARGIN + 4)} {_f(y)} Td "
                       f"({_pdf_text(line)}) Tj ET")
            y -= LEGEND_LINE_HEIGHT
        out.append(f"BT /F1 6 Tf {_f(MARGIN)} {_f(MARGIN - 12)} Td "
                   f"({_pdf_text(_footer(layout, page))}) Tj ET")
        return "\n".join(out)

    # All label geometry is measured from the TOP edge (top-origin, in
    # points); PDF drawing converts with `page_h - y`.
    grid_top_pdf = page_h - (MARGIN + HEADER_HEIGHT)  # grid's first row top edge

    # Title
    out.append("0 g")
    out.append(f"BT /F2 11 Tf {_f(MARGIN)} {_f(page_h - MARGIN - 9)} Td "
               f"({_pdf_text(layout['title'])}) Tj ET")

    # Labels
    for slot, item in enumerate(page.labels):
        col = slot % cols
        row = slot // cols
        x = MARGIN + col * (side + GUTTER)
        y_top_pdf = grid_top_pdf - row * (side + GUTTER)   # label top edge
        y_bot_pdf = y_top_pdf - side                        # label bottom edge
        wide = side >= WIDE_CAPTION_PT

        # Cut border (dashed)
        out.append("0.5 G 0.7 w [2 2.5] 0 d")
        out.append(f"{_f(x)} {_f(y_bot_pdf)} {_f(side)} {_f(side)} re S")
        out.append("0 G [] 0 d")

        # QR code with quiet zone (QR top sits QPAD below the label top edge)
        qr_box = side - 2 * QPAD - (CAPTION_HEIGHT if wide else 0.0)
        code_modules = item.qr_modules + 2 * item.quiet
        module = qr_box / code_modules
        qx = x + QPAD + item.quiet * module
        qy = y_top_pdf - QPAD - item.quiet * module      # QR top, PDF coords
        out.append("0 g")
        for my, rowpix in enumerate(item.matrix):
            for mx, dark in enumerate(rowpix):
                if dark:
                    out.append(f"{_f(qx + mx * module)} "
                               f"{_f(qy - (my + 1) * module)} "
                               f"{_f(module)} {_f(module)} re f")

        # Caption: number, then one truncated text line
        out.append("0 g")
        if wide:
            num = f"#{item.number:02d}"
            text = _truncate(item.text, max(0, int((side - 12) / 3.4)))
            cap_y = y_bot_pdf + 4.5
            out.append(f"BT /F2 7.5 Tf {_f(x + 4)} {_f(cap_y)} Td "
                       f"({_pdf_text(num)}) Tj ET")
            tx = x + 4 + len(num) * 4.6
            out.append(f"BT /F1 5.6 Tf {_f(tx)} {_f(cap_y)} Td "
                       f"({_pdf_text(text)}) Tj ET")
        else:
            num = f"#{item.number:02d}"
            out.append(f"BT /F2 8 Tf {_f(x + 3)} {_f(y_bot_pdf + 5)} Td "
                       f"({_pdf_text(num)}) Tj ET")

    # Legend head under the grid (only where it was planned to fit)
    for dy, line in enumerate(page.legend_lines):
        y = grid_top_pdf - rows * side - (rows - 1) * GUTTER - 10 \
            - dy * LEGEND_LINE_HEIGHT
        if y < MARGIN:
            break
        out.append(f"BT /F1 {_f(LEGEND_FONT)} Tf {_f(MARGIN)} {_f(y)} Td "
                   f"({_pdf_text(line)}) Tj ET")

    out.append(f"BT /F1 6 Tf {_f(MARGIN)} {_f(MARGIN - 12)} Td "
               f"({_pdf_text(_footer(layout, page))}) Tj ET")
    return "\n".join(out)


def build_pdf_bytes(layout):
    """Serializes the layout into a PDF bytestring."""
    page_w, page_h = layout["page_size"]
    pages = [_page_content(layout, page) for page in layout["pages"]]

    contents, page_obj_numbers = [], []
    next_num = 5
    for stream in pages:
        body = stream.encode("cp1252", errors="replace")
        contents.append((next_num,
                         b"<< /Length " + str(len(body)).encode()
                         + b" >>\nstream\n" + body + b"\nendstream"))
        page_obj_numbers.append(next_num + 1)
        contents.append((next_num + 1,
                         (f"<< /Type /Page /Parent 2 0 R "
                          f"/MediaBox [0 0 {_f(page_w)} {_f(page_h)}] "
                          f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                          f"/Contents {next_num} 0 R >>").encode("latin-1")))
        next_num += 2

    kids = " ".join(f"{n} 0 R" for n in page_obj_numbers)
    objects = [(1, b"<< /Type /Catalog /Pages 2 0 R >>"),
               (2, f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>"
                   .encode("latin-1")),
               (3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                   b"/Encoding /WinAnsiEncoding >>"),
               (4, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                   b"/Encoding /WinAnsiEncoding >>")]
    objects.extend(contents)
    objects.sort(key=lambda pair: pair[0])

    buf = bytearray()
    buf += b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = {}
    for number, body in objects:
        offsets[number] = len(buf)
        buf += f"{number} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"
    xref_start = len(buf)
    size = len(objects) + 1
    buf += f"xref\n0 {size}\n".encode("latin-1")
    buf += b"0000000000 65535 f \n"
    for number in range(1, size):
        buf += f"{offsets[number]:010d} 00000 n \n".encode("latin-1")
    buf += (f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_start}\n"
            "%%EOF\n").encode("latin-1")
    return bytes(buf)


def write_pdf(layout, path):
    Path(path).write_bytes(build_pdf_bytes(layout))
    return Path(path)


# ---------------------------------------------------------------------------
# HTML writer (single self-contained file, print-ready)

_CSS = """\
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; padding: 12px; font-family: "Segoe UI", Helvetica, Arial,
  sans-serif; color: #111; background: #f2f2f2; }
.sheet { background: #fff; max-width: 8.5in; margin: 0 auto 16px; padding:
  12mm; box-shadow: 0 1px 4px rgba(0,0,0,.15); break-after: page; }
h1 { font-size: 13pt; margin: 0 0 4mm; }
.hint { color: #555; font-size: 8pt; margin: 0 0 5mm; }
.grid { display: grid; gap: 2mm; }
.cell { border: 1px dashed #999; padding: 2mm; text-align: center;
  break-inside: avoid; display: flex; flex-direction: column; align-items:
  center; justify-content: space-between; min-height: __SIDE_MM__mm; }
.cell svg { display: block; margin: 0 auto; }
.qrbox { display: flex; align-items: flex-start; justify-content: center; }
.num { font-weight: 700; font-size: 7.5pt; }
.txt { font-size: 6pt; color: #333; max-width: 100%; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.numonly { font-weight: 700; font-size: 9pt; }
.legend { margin: 6mm 0 0; font-size: 8pt; padding-left: 16mm;
  columns: 2; column-gap: 8mm; }
.legend li { margin: 0 0 1.2mm; line-height: 1.35; word-break: break-word; }
@page { size: 8.5in 11in; margin: 0; }
@media print { body { background: none; padding: 0; } .sheet { box-shadow:
  none; margin: 0; width: auto; max-width: none; } }
"""


def _qr_svg(item, width_mm):
    n = item.qr_modules + 2 * item.quiet
    rects = []
    for y, row in enumerate(item.matrix):
        for x, dark in enumerate(row):
            if dark:
                rects.append(f"<rect x='{x + item.quiet}' y='{y + item.quiet}' "
                             "width='1' height='1' shape-rendering='crispEdges'/>")
    dims = f" width='{width_mm:.2f}mm' height='{width_mm:.2f}mm'"
    path = "<g fill='#000'>" + "".join(rects) + "</g>" if rects else ""
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {n} {n}'{dims} "
            f"role='img' aria-label='QR code'>"
            f"<rect width='{n}' height='{n}' fill='#fff'/>{path}</svg>")


def build_html(layout):
    page_w, page_h = layout["page_size"]
    cols, rows = layout["grid"]
    side_mm = layout["label_side_pt"] * MM_PER_PT
    wide = layout["label_side_pt"] >= WIDE_CAPTION_PT
    css = _CSS.replace("__SIDE_MM__", f"{side_mm:.2f}")

    out = ["<!doctype html>", "<html lang='en'>", "<head>",
           "<meta charset='utf-8'>",
           "<meta name='generator' content='qr-label-maker " + __version__ + "'>",
           f"<title>{html.escape(layout['title'], quote=True)}</title>",
           "<style>" + css + "</style>", "</head>", "<body>"]

    for page in layout["pages"]:
        out.append("<section class='sheet'>")
        out.append(f"<h1>{html.escape(layout['title'])} "
                   f"&middot; page {page.number}</h1>")
        if page.kind == "labels":
            out.append("<p class='hint'>Print at 100% scale, black &amp; white. "
                       "Cut along the dashed lines. Match the number on each "
                       "label to the legend below.</p>")
            out.append(f"<div class='grid' style=\"grid-template-columns:"
                       f"repeat({cols}, 1fr)\">")
            for item in page.labels:
                qr_mm = (side_mm - 2 * QPAD * MM_PER_PT
                         - (CAPTION_HEIGHT * MM_PER_PT if wide else 0))
                out.append("<div class='cell'>")
                out.append(f"<div class='qrbox'>{_qr_svg(item, qr_mm)}</div>")
                if wide:
                    text = html.escape(_truncate(item.text, int(side_mm * 2.2)))
                    out.append(f"<div class='num'>#{item.number:02d} "
                               f"<span class='txt' title='{html.escape(item.text, quote=True)}'>"
                               f"{text}</span></div>")
                else:
                    out.append(f"<div class='numonly'>#{item.number:02d}</div>")
                out.append("</div>")
            out.append("</div>")
        else:
            out.append("<p class='hint'>Legend continuation (see label pages "
                       "for sheet context).</p>")
        if page.legend_lines:
            out.append("<ol class='legend'>")
            for line in page.legend_lines:
                out.append(f"<li>{html.escape(line)}</li>")
            out.append("</ol>")
        out.append("</section>")

    out.append("</body></html>")
    return "\n".join(out)


def write_html(layout, path):
    Path(path).write_text(build_html(layout), encoding="utf-8")
    return Path(path)
