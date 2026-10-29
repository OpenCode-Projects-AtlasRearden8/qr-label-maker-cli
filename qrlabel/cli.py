"""Command line interface for QR Label Maker.

Typical use:
  qrlabel make "https://example.com/sign-up" --grid 2x4
  qrlabel add "Tool bin 7 - screws and nails"
  qrlabel list
  qrlabel show ab12cd
  qrlabel remove ab12cd --yes
"""

import argparse
import sys
from pathlib import Path

from . import __version__
from . import registry as reg
from .sheets import LayoutError, make_sheet, write_html, write_pdf

PROGRAM = "qrlabel"
EPILOG = ("No network access is ever used. Entries are stored in a small "
          "local JSON registry so your labels keep their ids.")


# ---------------------------------------------------------------------------
# Shared helpers

def _die(msg, code=2):
    print(f"qrlabel: error: {msg}", file=sys.stderr)
    sys.exit(code)


def _load_registry(args):
    try:
        return reg.open_registry(args.registry)
    except reg.RegistryError as exc:
        _die(str(exc))


def _add_layout_options(parser):
    group = parser.add_argument_group("sheet options")
    group.add_argument("--grid", default="3x4", metavar="CxR",
                       help="label grid, columns x rows (default: 3x4)")
    group.add_argument("--size", type=float, default=None, metavar="MM",
                       help="fixed label side in mm (default: auto-fit page)")
    group.add_argument("--page", default="letter", choices=("letter", "a4"),
                       help="paper size (default: letter)")
    group.add_argument("--copies", type=int, default=1, metavar="N",
                       help="copies of each entry (default: 1)")
    group.add_argument("--ecl", default="M", choices=("L", "M", "Q", "H"),
                       help="QR error correction level (default: M)")
    group.add_argument("--quiet", type=int, default=4, metavar="MODULES",
                       help="QR quiet zone modules, 2-8 (default: 4)")
    group.add_argument("--title", default=None,
                       help="sheet title for header and legend")
    group.add_argument("--out", default="qr-labels", metavar="PREFIX",
                       help="output file prefix (default: qr-labels)")
    group.add_argument("--format", dest="fmt", default="both",
                       choices=("pdf", "html", "both"),
                       help="output format (default: both)")
    group.add_argument("--no-legend", action="store_true",
                       help="omit the number legend (numbers stay on labels)")
    group.add_argument("--no-save", action="store_true",
                       help="do not add entries to the registry")
    group.add_argument("--force", action="store_true",
                       help="overwrite existing output files")
    group.add_argument("--registry", default=None, metavar="PATH",
                       help="registry file (default: ./qrlabel-registry.json)")
    group.add_argument("--file", default=None, metavar="PATH",
                       help="read one entry per line from this text file")
    group.add_argument("--from-registry", default=None, metavar="IDS",
                       help="comma-separated entry ids from the registry")


def _gather_entries(args):
    """Returns (texts, label_ids or None)."""
    texts, label_ids = [], None
    if getattr(args, "file", None):
        try:
            with open(args.file, "r", encoding="utf-8") as fh:
                texts.extend(line.strip() for line in fh if line.strip())
        except OSError as exc:
            _die(f"Cannot read {args.file}: {exc}")
    if getattr(args, "from_registry", None):
        registry = _load_registry(args)
        ids = [i.strip() for i in args.from_registry.split(",") if i.strip()]
        if not ids:
            _die("--from-registry needs at least one id")
        label_ids = []
        for entry_id in ids:
            try:
                entry = registry.get(entry_id)
            except reg.RegistryError as exc:
                _die(str(exc))
            texts.append(entry["text"])
            label_ids.append(entry["id"])
    texts.extend(getattr(args, "texts", None) or [])
    return texts, label_ids


def _texts_only(args):
    texts, _ = _gather_entries(args)
    return texts


# ---------------------------------------------------------------------------
# Commands

def cmd_make(args):
    texts, label_ids = _gather_entries(args)
    if not texts:
        _die("make needs at least one entry (text) or --file/--from-registry")

    registry = None
    if not args.no_save:
        registry = _load_registry(args)
        for i, text in enumerate(texts):
            try:
                entry = registry.add(text)
            except reg.RegistryError as exc:
                _die(str(exc))
            if label_ids is None:
                label_ids = []
            label_ids.append(entry["id"])
        registry.save()

    try:
        layout = make_sheet(
            texts,
            label_ids=label_ids,
            page=args.page,
            grid=args.grid,
            size_mm=args.size,
            title=args.title,
            copies=args.copies,
            ecl=args.ecl,
            quiet=args.quiet,
            legend=not args.no_legend,
        )
    except (LayoutError,) as exc:
        _die(str(exc))

    outs = []
    for ext, writer in (("pdf", write_pdf), ("html", write_html)):
        if args.fmt not in ("both", ext):
            continue
        path = Path(f"{args.out}.{ext}")
        if path.exists() and not args.force:
            _die(f"{path} exists (use --force to overwrite)")
        writer(layout, path)
        outs.append(path)

    label_count = sum(len(p.labels) for p in layout["pages"])
    print(f"Wrote {label_count} labels on {len(layout['pages'])} page(s):")
    for path in outs:
        print(f"  {path}")
    if not args.no_save and registry is not None:
        if label_ids:
            print("Entry ids: " + ", ".join(label_ids))
        print(f"Registry: {registry.path} ({len(registry.entries)} entries)")
    return 0


def cmd_add(args):
    texts = [t.strip() for t in _texts_only(args) if t.strip()]
    if not texts:
        _die("add needs at least one entry (text) or --file")
    registry = _load_registry(args)
    for text in texts:
        registry.add(text)
    registry.save()
    nouns = ("entry", "entries")
    print(f"Added {len(texts)} {nouns[0] if len(texts) == 1 else nouns[1]}:")
    for entry in registry.entries[-len(texts):]:
        preview = entry["text"][:50] + ("..." if len(entry["text"]) > 50 else "")
        print(f"  {entry['id']}  {preview}")
    print(f"Registry: {registry.path}")
    return 0


def cmd_list(args):
    registry = _load_registry(args)
    if not registry.entries:
        print("Registry is empty. Add entries with: qrlabel add \"text or URL\"")
        return 0
    for entry in registry.entries:
        preview = entry["text"].replace("\n", " / ")[:60]
        if len(entry["text"]) > 60:
            preview += "..."
        print(f"{entry['id']}  {entry['created']}  {preview}")
    print(f"-- {len(registry.entries)} entr"
          f"{'y' if len(registry.entries) == 1 else 'ies'} in {registry.path}")
    return 0


def cmd_show(args):
    registry = _load_registry(args)
    try:
        entry = registry.get(args.id)
    except reg.RegistryError as exc:
        _die(str(exc))
    print(f"id: {entry['id']}")
    print(f"created: {entry['created']}")
    print(f"text:\n{entry['text']}")
    return 0


def cmd_remove(args):
    registry = _load_registry(args)
    if not args.yes:
        answer = input(f"Remove {args.id}? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 1
    try:
        entry = registry.remove(args.id)
    except reg.RegistryError as exc:
        _die(str(exc))
    registry.save()
    print(f"Removed {entry['id']}: {entry['text'][:60]}")
    print(f"Registry: {registry.path}")
    return 0


# ---------------------------------------------------------------------------
# Argument parsing

def build_parser():
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=("Offline print-and-cut QR label sheets: hand it text or "
                     "a URL, choose a label grid, print PDF/HTML sheets with "
                     "a numbered legend."),
        epilog=EPILOG,
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("make", help="make a label sheet from text/URLs",
                       description="Make print-ready label sheets. Entries "
                                   "are saved to the local registry unless "
                                   "--no-save.")
    p.add_argument("texts", nargs="*", help="entries: text or URL for the QR")
    _add_layout_options(p)
    p.set_defaults(func=cmd_make)

    p = sub.add_parser("add", help="save entries to the local registry",
                       description="Save entries to the local registry and "
                                   "print their ids.")
    p.add_argument("texts", nargs="*", help="entries to save")
    p.add_argument("--registry", default=None, metavar="PATH",
                   help="registry file (default: ./qrlabel-registry.json)")
    p.add_argument("--file", default=None, metavar="PATH",
                   help="read one entry per line from this text file")
    p.add_argument("--from-registry", default=None, help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="list registry entries",
                       description="List all entries in the local registry")
    p.add_argument("--registry", default=None, metavar="PATH",
                   help="registry file (default: ./qrlabel-registry.json)")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="show one registry entry in full",
                       description="Show one registry entry in full.")
    p.add_argument("id", help="entry id (see qrlabel list)")
    p.add_argument("--registry", default=None, metavar="PATH",
                   help="registry file (default: ./qrlabel-registry.json)")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("remove", help="remove one registry entry",
                       description="Remove one entry from the local registry.")
    p.add_argument("id", help="entry id (see qrlabel list)")
    p.add_argument("--yes", action="store_true", help="skip confirmation")
    p.add_argument("--registry", default=None, metavar="PATH",
                   help="registry file (default: ./qrlabel-registry.json)")
    p.set_defaults(func=cmd_remove)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
