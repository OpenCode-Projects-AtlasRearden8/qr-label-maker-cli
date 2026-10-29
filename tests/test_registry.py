"""Tests for the local JSON registry."""

import json

import pytest

from qrlabel.registry import Registry, RegistryError, open_registry


def test_add_and_get(tmp_path):
    r = Registry(tmp_path / "reg.json").load()
    e1 = r.add("Tool bin 7 - screws and nails")
    assert e1["text"] == "Tool bin 7 - screws and nails"
    assert len(e1["id"]) == 6
    assert e1["created"].endswith("Z")
    assert r.get(e1["id"]) == e1
    assert r.ids() == [e1["id"]]


def test_ids_unique(tmp_path):
    r = Registry(tmp_path / "reg.json").load()
    ids = {r.add(f"entry-{i}")["id"] for i in range(50)}
    assert len(ids) == 50


def test_roundtrip_save_load(tmp_path):
    r = Registry(tmp_path / "reg.json").load()
    a = r.add("first")
    b = r.add("second")
    r.save()
    r2 = Registry(tmp_path / "reg.json").load()
    assert r2.get(a["id"])["text"] == "first"
    assert r2.get(b["id"])["text"] == "second"
    data = json.loads((tmp_path / "reg.json").read_text())
    assert data["schema"] == 1
    assert isinstance(data["entries"], list) and len(data["entries"]) == 2


def test_load_missing_file_creates_empty(tmp_path):
    r = Registry(tmp_path / "never.json").load()
    assert r.entries == []


def test_load_bad_registry_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    with pytest.raises(RegistryError):
        Registry(p).load()


def test_bad_schema_raises(tmp_path):
    p = tmp_path / "v2.json"
    p.write_text(json.dumps({"schema": 99, "entries": []}))
    with pytest.raises(RegistryError):
        Registry(p).load()


def test_remove(tmp_path):
    r = Registry(tmp_path / "reg.json").load()
    e = r.add("doomed")
    removed = r.remove(e["id"])
    assert removed == e
    with pytest.raises(RegistryError):
        r.remove(e["id"])


def test_empty_text_rejected_and_coercion(tmp_path):
    r = Registry(tmp_path / "reg.json").load()
    with pytest.raises(RegistryError):
        r.add("   ")
    with pytest.raises(RegistryError):
        r.add("")
    r.add(123)  # non-strings are coerced
    assert r.entries[0]["text"] == "123"


def test_unknown_id_raises(tmp_path):
    r = Registry(tmp_path / "reg.json").load()
    with pytest.raises(RegistryError):
        r.get("zzzzzz")


def test_open_registry_default_path_uses_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("QRLABEL_REGISTRY", str(tmp_path / "envreg.json"))
    r = open_registry()
    assert r.path == tmp_path / "envreg.json"
    e = r.add("from env")
    r.save()
    assert (tmp_path / "envreg.json").exists()
