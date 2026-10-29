"""End-to-end CLI tests (qrlabel.cli.main) run inside a temp directory."""

import json
from pathlib import Path

import pytest

from qrlabel import cli


def run(argv):
    return cli.main(argv)


@pytest.fixture()
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", Path("/dev/null").open("r"))
    return tmp_path


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        run(["--version"])
    assert exc.value.code == 0
    assert "1.0.0" in capsys.readouterr().out


def test_make_writes_outputs_and_registry(workdir, capsys):
    code = run(["make", "https://example.com/sign-up",
                "--out", "labels", "--registry", "reg.json"])
    assert code == 0
    out = capsys.readouterr().out
    assert (workdir / "labels.pdf").exists()
    assert (workdir / "labels.html").exists()
    assert (workdir / "labels.pdf").read_bytes().startswith(b"%PDF-1.4")
    reg = json.loads((workdir / "reg.json").read_text())
    assert len(reg["entries"]) == 1
    entry_id = reg["entries"][0]["id"]
    assert entry_id in out
    assert entry_id in (workdir / "labels.html").read_text()


def test_make_no_save_leaves_no_registry(workdir):
    run(["make", "URL HERE", "--no-save", "--out", "x", "--format", "pdf"])
    assert not (workdir / "qrlabel-registry.json").exists()
    assert not (workdir / "reg.json").exists()
    assert (workdir / "x.pdf").exists()


def test_make_refuses_overwrite(workdir, capsys):
    run(["make", "text", "--out", "same", "--no-save", "--format", "pdf"])
    with pytest.raises(SystemExit) as exc:
        run(["make", "text", "--out", "same", "--no-save", "--format", "pdf"])
    assert exc.value.code == 2
    assert "--force" in capsys.readouterr().err


def test_make_with_force_overwrites(workdir):
    run(["make", "text", "--out", "same", "--no-save", "--format", "pdf"])
    run(["make", "text two", "--out", "same", "--no-save", "--format", "pdf",
         "--force"])
    assert (workdir / "same.pdf").exists()
    with pytest.raises(SystemExit):
        run(["make", "text three", "--out", "same", "--no-save",
             "--format", "pdf"])


def test_make_html_only(workdir):
    run(["make", "text", "--out", "only-html", "--no-save", "--format", "html"])
    assert (workdir / "only-html.html").exists()
    assert not (workdir / "only-html.pdf").exists()


def test_make_pdf_only(workdir):
    run(["make", "text", "--out", "only-pdf", "--no-save", "--format", "pdf"])
    assert (workdir / "only-pdf.pdf").exists()
    assert not (workdir / "only-pdf.html").exists()


def test_make_file_input(workdir):
    src = workdir / "entries.txt"
    src.write_text("first entry\n\nsecond entry\n", encoding="utf-8")
    run(["make", "--file", str(src), "--no-save", "--out", "s",
         "--format", "pdf"])
    pdf = (workdir / "s.pdf").read_bytes()
    assert b"first entry" in pdf
    assert b"second entry" in pdf


def test_add_list_show_remove(workdir, capsys):
    run(["add", "Tool bin 7", "https://example.com/x",
         "--registry", "reg.json"])
    out1 = capsys.readouterr().out
    assert "Added 2 entries" in out1
    ids = json.loads((workdir / "reg.json").read_text())["entries"]
    first_id = ids[0]["id"]

    run(["list", "--registry", "reg.json"])
    out2 = capsys.readouterr().out
    assert "Tool bin 7" in out2 and first_id in out2

    run(["show", first_id, "--registry", "reg.json"])
    out3 = capsys.readouterr().out
    assert "Tool bin 7" in out3

    run(["remove", first_id, "--yes", "--registry", "reg.json"])
    out4 = capsys.readouterr().out
    assert f"Removed {first_id}" in out4
    reg = json.loads((workdir / "reg.json").read_text())
    assert [e["id"] for e in reg["entries"]] == [ids[1]["id"]]


def test_empty_registry_list_message(workdir, capsys):
    assert run(["list", "--registry", "empty-reg.json"]) == 0
    assert "Registry is empty" in capsys.readouterr().out


def test_make_from_registry(workdir, capsys):
    run(["add", "BIN 7 SCREWS", "--registry", "reg.json"])
    ids = json.loads((workdir / "reg.json").read_text())["entries"]
    entry_id = ids[0]["id"]
    run(["make", "--from-registry", entry_id, "--no-save",
         "--out", "reprint", "--grid", "2x4", "--format", "pdf",
         "--registry", "reg.json"])
    # registry unchanged (one entry) even though labels were printed
    reg = json.loads((workdir / "reg.json").read_text())
    assert len(reg["entries"]) == 1


def test_make_unknown_registry_id_exits(workdir):
    with pytest.raises(SystemExit) as exc:
        run(["make", "--from-registry", "nope00", "--registry", "reg.json"])
    assert exc.value.code == 2


def test_make_no_text_exits(workdir):
    with pytest.raises(SystemExit) as exc:
        run(["make", "--registry", "reg.json"])
    assert exc.value.code == 2


def test_no_command_prints_help_exits(capsys):
    assert run([]) == 2
    assert "usage:" in capsys.readouterr().out


def test_sample_registry_fixture_loads():
    data = json.loads((Path(__file__).parent / "fixtures"
                       / "sample-registry.json").read_text())
    assert data["schema"] == 1
    assert all(len(e["id"]) == 6 for e in data["entries"])
