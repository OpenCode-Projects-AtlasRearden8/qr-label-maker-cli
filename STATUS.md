# STATUS

Last updated: 2026-10-29

## What was built

**qr-label-maker** — an offline CLI that turns text or URLs into print-and-cut
QR label sheets. `qrlabel make "https://example.com/sign" --grid 3x4` produces:

- a **PDF** sheet (letter or A4) with a grid of dashed-border labels, each
  holding a standard QR code, its number (`#01`, `#02`, …) and a one-line
  caption, plus a numbered legend mapping numbers back to entry text and
  registry ids; legend overflow spills onto trailing legend pages;
- a self-contained **HTML** version of the same sheets (inline SVG QR codes,
  print CSS) as a no-PDF-viewer fallback;
- each printed label number maps 1:1 to the legend, so cut-apart labels stay
  traceable to their registry entry.

Subcommands: `make`, `add`, `list`, `show`, `remove`. Entries live in a small
local JSON registry (`./qrlabel-registry.json` by default; `--registry PATH`
or the `QRLABEL_REGISTRY` environment variable override it).

Implementation facts:

- Pure Python 3.9+ **standard library only** at runtime. Zero dependencies.
- The QR encoder is vendored at `qrlabel/_vendor/qrcodegen.py`, adapted from
  the MIT-licensed Project Nayuki QR Code generator (attribution and the
  original MIT notice are preserved in the file header). It supports QR
  Model 2, versions 1–40, all four ECC levels, automatic mask selection and
  automatic version choice with ECC boosting.
- The PDF writer is hand-rolled (a few hundred lines): text ops with PDF base
  fonts plus `re f` rectangles for dark modules. Output is deterministic:
  same inputs → byte-identical PDFs and HTML (no timestamps embedded).
- There is **no network code anywhere in the project** — it never touches
  the network by construction, not just by policy.
- MIT LICENSE, copyright line `Copyright (c) 2026 Asdale Dynamics, LLC`;
  README credits Asdale Dynamics, LLC.

## How to run it

```bash
# no install:
python -m qrlabel make "https://example.com/free-stuff" --grid 3x4

# optional install, then use the `qrlabel` command:
pip install -e .          # (add [test] extra for pytest)
qrlabel make "tool bin 7" --copies 3 ...
```

Common options: `--grid CxR`, `--size MM`, `--copies N`, `--page letter|a4`,
`--ecl L|M|Q|H`, `--title`, `--out PREFIX`, `--format pdf|html|both`,
`--no-legend`, `--no-save`, `--force`. Registry: `add/list/show/remove` with
`--registry PATH`.

## Verification results (all passing as of this commit)

- `pytest`: **89 passed, 1 skipped** — the skipped test is the optional
  OpenCV real-reader decode check (runs when `cv2` is importable; it passed
  in this dev environment: rendered PDF pages and fixture matrices decode to
  the exact payloads, verified with `cv2.QRCodeDetector` on rounded PDFs via
  `pdftoppm` renders).
- **Vendor encoder vs pristine reference**: a differential test run during
  development (not vendored, dev-only) compared this vendored encoder against
  a pristine copy of Nayuki's `qrcodegen.py` across 60+ payloads (URLs,
  alphanumeric bin names, ASCII noise, UTF-8, 400-char strings) × 4 ECC
  levels — matrix-identical versions, masks and module grids. That invariance
  is pinned in the suite via `tests/fixtures/qr-matrices.json` goldens.
- A static fixture test verifies `encode_text` on the known example
  ("HELLO WORLD" → v1-alphanumeric, mask chosen automatically) and BCH(15,5)
  format-info validity for every (ECC level, mask) pair; capacity math is
  checked against known v1/v10 codeword counts.
- Printed-sheet fixtures: byte-equal goldens (`tests/fixtures/golden-tool-bin.pdf`
  and `.html`) covering a 3x2 grid, 6 labels, 3 entries, copies and legend
  head. PDF xref offsets are re-validated structurally by a test.
- End-to-end CLI test: full session under a temp dir — make (which adds to
  the registry and reports ids), re-make from registry ids, overwrite rules,
  add/list/show/remove, `--file` batch input, `--no-save`.
- Manual smoke checks: rendered pages visually inspected (title header,
  dashed cut borders, QR captions, legend under grid, footer); all QRs on a
  rendered page decode with OpenCV.

## Known gaps / limits

- PDF legend and captions are restricted to characters encodable in cp1252
  (PDF base fonts cannot print arbitrary Unicode); unencodable characters are
  replaced with `?`. The HTML output carries every Unicode character as-is.
- Caption/legend truncation uses rough character-count estimates rather than
  exact Helvetica metrics — a too-long line can slightly overrun a label.
- No CLI config file and no per-entry notes yet; registry entries hold only
  id, text, created-at.
- `remove` prompts interactively unless `--yes` is passed (piped input ends
  up as Cancelled).
- Sheet margins are fixed at 0.5 in; no die-cut template presets (Avery
  etc.) yet — sized squares are the supported model.
- No image output (PNG) and no batch multi-sheet ordering guarantees beyond
  row-major fill.
- The suite's OpenCV decode check is skipped in environments without `cv2`
  (by design; it is dev-only and not a runtime dependency).

## File map

```
qrlabel/            package (cli, registry, sheets, qrcodes, _vendor/qrcodegen.py)
tests/              pytest suite + fixtures (golden PDF/HTML, QR matrix goldens, sample registry)
LICENSE             MIT, Copyright (c) 2026 Asdale Dynamics, LLC
README.md           usage and background, credits Asdale Dynamics, LLC
pyproject.toml      package metadata (no runtime deps), pytest config
STATUS.md           this file
```
