# QR Label Maker

**Offline print-and-cut QR label sheets — hand it text or a URL, choose a label
grid size, and get print-ready PDF/HTML sheets with a numbered legend.**

Great for garage-sale signs on every table, numbered tool bins, recipe cards
that open a cooking video, and home library lending (one label per book, and a
legend page to track who borrowed what). Built with beginners in mind by
**Asdale Dynamics, LLC**: plain English, step by step, no condensation, and no
clouds involved.

- 100% offline: never touches the network, no accounts, no tracking.
- Pure Python standard library plus a vendored pure-QR encoder — nothing to
  install beyond Python 3.9+.
- Entries live in a small local registry file, so labels keep stable ids you
  can re-print or manage later.

## Quick start

```bash
# from this folder, no installation needed:
python -m qrlabel make "https://example.com/free-stuff" --grid 3x4

# or after `pip install .`:
qrlabel make "https://dylanasdale.github.io/"
qrlabel make "Tool bin 7 - screws and nails" --size 40 --grid 2x4 --copies 2
qrlabel make --from-registry ab12cd,ef34ab --title "Recipe cards"
```

Options you will actually use:

| Option       | Meaning                                             | Default     |
| ------------ | --------------------------------------------------- | ----------- |
| `--grid CxR` | labels per page (columns x rows)                    | `3x4`       |
| `--size MM`  | fixed label side in mm (auto-fit if omitted)        | auto        |
| `--copies N` | each entry repeated on the sheet                    | 1           |
| `--page`     | `letter` or `a4`                                    | `letter`    |
| `--ecl`      | QR error correction `L`, `M`, `Q`, `H`              | `M`         |
| `--out NAME` | output file prefix (writes `NAME.pdf`, `NAME.html`) | `qr-labels` |
| `--format`   | `pdf`, `html`, or `both`                            | `both`      |
| `--title`    | sheet title for the header and legend               | auto        |
| `--no-legend`| omit the numbered legend                            | legend on   |
| `--no-save`  | don't add the entries to the registry               | saves       |
| `--force`    | overwrite existing output files                     | off         |

Print the PDF (or open the HTML in a browser and print from there) at 100%
scale, then cut along the dashed lines. Each label has a number; the legend
under the grid (and on trailing legend pages) maps every number to its text
and registry id.

## The registry

Saving entries to the registry means your next batch can re-print by id, and
you can track what each label belongs to.

```bash
qrlabel add "Tool bin 7 - screws and nails"     # -> prints the new id
qrlabel list
qrlabel show ab12cd
qrlabel remove ab12cd --yes
qrlabel make --from-registry ab12cd --no-save   # print without re-saving
```

The registry is a plain JSON file, `./qrlabel-registry.json` by default
(override with `--registry PATH` or the `QRLABEL_REGISTRY` environment
variable). Keep it in your backup file next to your label folder. It stores
only what you type: ids, timestamps and the entry text.

## Ideas from real life

- Garage sale: one URL per sign, `--copies 12`, print once, cut once.
- Tool bins: text labels like `BIN 9 - PLYERS AND WIRE`, `--size 40`.
- Recipe cards: each card opens the video at its step, `--grid 3x4`.
- Home library: each book gets a number; the legend page is your lending log
  (write who borrowed under the line with a pen).

## Output formats

- **PDF**: self-contained, standard `Helvetica` fonts, drawn page-by-page, no
  external images or fonts. Deterministic: same inputs give byte-identical
  files (nice for tests and reprints).
- **HTML**: one self-contained file with inline SVG QR codes and print CSS.
  Also a great fallback if you do not have a PDF viewer.

## What the QR codes are

Standard QR Code Model 2 symbols (ISO/IEC 18004), versions 1–40, all four
error-correction levels, chosen automatically to be as small and as strongly
corrected as possible. They decode with any phone camera or QR scanner.

## Testing

```bash
pip install -e .[test]   # only packages pytest; the tool itself has no deps
pytest
```

The suite covers the vendored QR encoder, the registry, sheet geometry and the
exact bytes of committed printed-sheet fixtures (`tests/fixtures/`), plus a
full CLI round trip in a temp directory.

## Notes for the curious

- The vendored encoder is adapted from the MIT-licensed
  [Project Nayuki QR Code generator](https://www.nayuki.io/page/qr-code-generator-library);
  its copyright notice is preserved in `qrlabel/_vendor/qrcodegen.py`.
- PDF writing is hand-rolled (no reportlab needed): text plus `re f` rectangles
  for QR modules. Legend text is restricted to characters that PDF base fonts
  can print; the HTML output happily carries every Unicode character.
- This tool is local-first and dependency-free: no network code exists in it.

## License

MIT — Copyright (c) 2026 Asdale Dynamics, LLC. See `LICENSE`.
