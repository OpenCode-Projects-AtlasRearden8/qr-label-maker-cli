"""Small local JSON registry of label entries.

The registry is a plain JSON file (default: ./qrlabel-registry.json,
override with --registry or the QRLABEL_REGISTRY environment variable).
It is local-only: nothing is ever uploaded anywhere.
"""

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_NAME = "qrlabel-registry.json"


def default_path():
    env = os.environ.get("QRLABEL_REGISTRY")
    return Path(env) if env else Path.cwd() / DEFAULT_NAME


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RegistryError(Exception):
    pass


class Registry:
    def __init__(self, path):
        self.path = Path(path)
        self.entries = []
        self._loaded = False

    # -- persistence -------------------------------------------------

    def load(self):
        self._loaded = True
        if not self.path.exists():
            self.entries = []
            return self
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            raise RegistryError(f"Cannot read registry {self.path}: {exc}") from exc
        schema = data.get("schema", SCHEMA_VERSION)
        if schema != SCHEMA_VERSION:
            raise RegistryError(f"Unsupported registry schema {schema} in {self.path}")
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            raise RegistryError(f"Registry entries in {self.path} are not a list")
        self.entries = []
        for raw in entries:
            text = raw.get("text", "")
            self.entries.append({
                "id": str(raw.get("id", "")),
                "text": str(text),
                "created": str(raw.get("created", _now_iso())),
            })
        return self

    def save(self):
        if not self._loaded:
            self.load()
        payload = {
            "schema": SCHEMA_VERSION,
            "created": _now_iso(),
            "registry": "qr-label-maker",
            "entries": self.entries,
        }
        parent = self.path.parent if str(self.path.parent) else Path(".")
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=parent, prefix=".qrregistry-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return self

    # -- entry operations --------------------------------------------

    def new_id(self):
        while True:
            candidate = secrets.token_hex(3)
            if candidate not in {e["id"] for e in self.entries}:
                return candidate

    def add(self, text, entry_id=None, created=None):
        text = str(text)
        if not text.strip():
            raise RegistryError("Entry text must not be empty")
        entry = {
            "id": entry_id or self.new_id(),
            "text": text,
            "created": created or _now_iso(),
        }
        self.entries.append(entry)
        return entry

    def get(self, entry_id):
        for entry in self.entries:
            if entry["id"] == entry_id:
                return entry
        raise RegistryError(f"Unknown entry id {entry_id!r} in {self.path}")

    def remove(self, entry_id):
        for i, entry in enumerate(self.entries):
            if entry["id"] == entry_id:
                return self.entries.pop(i)
        raise RegistryError(f"Unknown entry id {entry_id!r} in {self.path}")

    def ids(self):
        return [e["id"] for e in self.entries]


def open_registry(path=None):
    return Registry(path if path is not None else default_path()).load()
