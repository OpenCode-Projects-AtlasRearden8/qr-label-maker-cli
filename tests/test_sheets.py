"""Tests for sheet layout, the PDF writer and the HTML writer."""

import hashlib
import re
import zlib
from pathlib import Path

import pytest

from qrlabel.sheets import (LayoutError, MARGIN, build_html, build_pdf_bytes,
                            make_sheet, parse_grid, write_pdf, write_html)

FIXTURES = Path(__file__).parent / "fixtures"


def layout_for(**kw):
    return make_sheet(["BIN 7 SCREWS", "BIN 8 NAILS", "BIN 9 WIRE"],
                      label_ids=["id111", "id222", "id333"],
                      grid="3x2", size_mm=40, copies=2,
                      title="Tool bins", **kw)


def test_parse_grid():
    assert parse_grid("3x4") == (3, 4)
    assert parse_grid(" 2 x 2 ") == (2, 2)
    for bad in ("3", "x4", "axb", "0x4", "31x1"):
        with pytest.raises(LayoutError):
            parse_grid(bad)


def test_label_ordering_across_copies():
    layout = layout_for()
    items = _labels(layout)
    assert [i.number for i in items] == [1, 2, 3, 4, 5, 6]
    assert [i.text for i in items] == ["BIN 7 SCREWS", "BIN 8 NAILS",
                                       "BIN 9 WIRE"] * 2
    assert items[0].entry_id == "id111" and items[3].entry_id == "id111"


def _labels(layout):
    return [it for page in layout["pages"] for it in page.labels]


def test_label_side_geometry_letter():
    layout = make_sheet(["A URL", "B URL"], page="letter", grid="2x4")
    # printable width 612-72=540; (540-6)/2 = 267; height: (792-72-24-18)/4=169.5
    assert layout["label_side_pt"] == min(267.0, 169.5) == 169.5
    assert layout["grid_bottom_y"] == MARGIN + 24 + 4 * 169.5 + 3 * 6


def test_fixed_size_validation():
    with pytest.raises(LayoutError):
        make_sheet(["a"], grid="1x1", size_mm=300)
    with pytest.raises(LayoutError):
        make_sheet(["a"], grid="8x8", size_mm=40)   # 40mm x8 > page height
    with pytest.raises(LayoutError):
        make_sheet(["a"], grid="10x10", size_mm=13)  # below 14mm minimum


def test_legend_spill_pages():
    # 20 entries, small grid: the legend cannot fit, so trailing pages appear
    texts = [f"entry number {i}" for i in range(1, 21)]
    layout = make_sheet(texts, grid="3x4")
    kinds = [p.kind for p in layout["pages"]]
    assert "legend" in kinds
    legend_lines = [l for p in layout["pages"] if p.kind == "legend"
                    for l in p.legend_lines]
    # every entry appears in the spilled legend exactly once
    assert len(legend_lines) == 20
    for i in range(1, 21):
        assert any(str(i).zfill(2) in l for l in legend_lines)


def test_page_numbers_are_sequential():
    layout = make_sheet([f"e{i}" for i in range(1, 13)], grid="3x4")
    assert [p.number for p in layout["pages"]] == list(
        range(1, len(layout["pages"]) + 1))


def test_pdf_determinism_and_structure():
    data1 = build_pdf_bytes(layout_for())
    data2 = build_pdf_bytes(layout_for())
    assert data1 == data2
    assert data1.startswith(b"%PDF-1.4\n")
    assert b"/Type /Catalog" in data1
    # one label page: content stream is object 5, page object is 6
    assert b"/Kids [6 0 R]" in data1
    assert b"BIN 7 SCREWS" in data1
    # content streams are uncompressed, so QR bitmaps appear as raw "re f" ops
    assert data1.count(b" re f") > 500


def test_pdf_object_offsets_are_valid():
    data = build_pdf_bytes(layout_for())
    m = re.search(rb"startxref\s+(\d+)\n%%EOF", data)
    xref_pos = int(m.group(1))
    assert data[xref_pos:xref_pos + 4] == b"xref"
    # every xref entry must point at "N 0 obj"
    table = data[xref_pos:]
    entries = re.findall(rb"(\d{10}) 00000 n \n", table)
    for i, entry in enumerate(entries, start=1):
        assert data[int(entry):int(entry) + 7] == f"{i} 0 obj".encode()


def test_pdf_matches_golden_fixture():
    data = build_pdf_bytes(layout_for())
    golden = (FIXTURES / "golden-tool-bin.pdf").read_bytes()
    assert data == golden


def test_html_matches_golden_fixture():
    html = build_html(layout_for())
    golden = (FIXTURES / "golden-tool-bin.html").read_text(encoding="utf-8")
    assert html == golden


def test_html_contains_svg_and_legend():
    html = build_html(layout_for())
    assert html.count("<svg") == 6
    assert "#04" in html and "BIN 7 SCREWS" in html
    assert "[id111]" in html  # registry id in the legend
    assert "aria-label='QR code'" in html


def test_html_escapes_task_text():
    html = build_html(make_sheet(["Bang & Olufsen <3"], title="t&"))
    assert "Bang &amp; Olufsen &lt;3" in html
    assert "t&amp;" in html


def test_writers(tmp_path):
    layout = layout_for()
    p1 = write_pdf(layout, tmp_path / "out.pdf")
    p2 = write_html(layout, tmp_path / "out.html")
    assert p1.read_bytes() == build_pdf_bytes(layout)
    assert p2.read_text(encoding="utf-8") == build_html(layout)


def test_single_label_small_grid_no_legend():
    layout = make_sheet(["https://example.com"], grid="1x1")
    assert len(_labels(layout)) == 1
    assert layout["pages"][0].kind == "labels"


def test_no_entries_raises():
    with pytest.raises(LayoutError):
        make_sheet(["", "   "])
