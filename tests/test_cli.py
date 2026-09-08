"""ttl3d.cli: the command line entry point."""
import subprocess
import sys
from pathlib import Path
import pytest
from ttl3d import cli

REPO = Path(__file__).resolve().parents[1]


def test_cli_writes_the_page_and_reports_what_it_did(tmp_path, library, library_extra, capsys):
    out = tmp_path / "lib.html"
    rc = cli.main([str(library), str(library_extra), "-o", str(out), "--title", "Lib"])
    assert rc == 0
    html = out.read_text()
    assert "<title>Lib</title>" in html and '"pinned": true' in html
    printed = capsys.readouterr().out
    assert "12 nodes" in printed and "6 links" in printed and "stress" in printed


def test_cli_default_output_is_named_after_the_first_file(tmp_path, library, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main([str(library)]) == 0
    assert (tmp_path / "library-3d.html").exists()


def test_cli_color_by_type_puts_types_in_the_legend(tmp_path, library):
    out = tmp_path / "t.html"
    cli.main([str(library), "-o", str(out), "--color-by", "type"])
    assert 'data-group="Book"' in out.read_text()


def test_cli_force_layout_leaves_nodes_unpinned(tmp_path, library):
    out = tmp_path / "f.html"
    cli.main([str(library), "-o", str(out), "--layout", "force"])
    assert '"pinned": false' in out.read_text()


def test_cli_hover_labels_disable_both_label_layers(tmp_path, library):
    out = tmp_path / "h.html"
    cli.main([str(library), "-o", str(out), "--labels", "hover"])
    assert '"node": false' in out.read_text() and '"edge": false' in out.read_text()


def test_cli_rejects_an_unknown_color_key(library):
    with pytest.raises(SystemExit) as e:
        cli.main([str(library), "--color-by", "colour"])
    assert e.value.code == 2


def test_module_entry_point_runs(tmp_path, library):
    out = tmp_path / "m.html"
    r = subprocess.run([sys.executable, "-m", "ttl3d", str(library), "-o", str(out)],
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stderr
    assert out.exists()
