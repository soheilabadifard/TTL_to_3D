"""ttl3d.cli: the command line entry point."""
import os
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


def test_cli_missing_file_is_a_clean_error(tmp_path, capsys):
    out = tmp_path / "x.html"
    rc = cli.main([str(tmp_path / "nope.ttl"), "-o", str(out)])
    assert rc == 1
    err = capsys.readouterr().err
    assert err.startswith("ttl3d: error:") and "nope.ttl" in err
    assert not out.exists()


def test_cli_malformed_file_is_a_clean_error(tmp_path, capsys):
    bad = tmp_path / "bad.ttl"
    bad.write_text("this is not turtle @@@\n", encoding="utf-8")
    rc = cli.main([str(bad), "-o", str(tmp_path / "x.html")])
    assert rc == 1
    err = capsys.readouterr().err
    assert err.startswith("ttl3d: error:") and "bad.ttl" in err
    assert err.count("\n") == 1


def test_cli_refuses_to_overwrite_an_input(tmp_path, library, capsys):
    victim = tmp_path / "victim.ttl"
    victim.write_text(library.read_text(encoding="utf-8"), encoding="utf-8")
    rc = cli.main([str(victim), "-o", str(victim)])
    assert rc == 1
    assert victim.read_text(encoding="utf-8") == library.read_text(encoding="utf-8")
    assert "input" in capsys.readouterr().err


def test_cli_output_directory_is_a_clean_error(tmp_path, library, capsys):
    rc = cli.main([str(library), "-o", str(tmp_path)])
    assert rc == 1
    assert capsys.readouterr().err.startswith("ttl3d: error:")


def test_cli_header_only_file_produces_an_empty_page(tmp_path, capsys):
    ttl = tmp_path / "header.ttl"
    ttl.write_text("@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
                   "<http://example.org/o> a owl:Ontology .\n", encoding="utf-8")
    out = tmp_path / "header.html"
    assert cli.main([str(ttl), "-o", str(out)]) == 0
    assert "0 nodes" in capsys.readouterr().out and out.exists()


def test_cli_announces_a_big_stress_layout_on_stderr(tmp_path, capsys):
    from ttl3d import layout
    n = layout.PROGRESS_MIN_NODES + 1
    ttl = tmp_path / "big.ttl"
    ttl.write_text("@prefix ex: <http://example.org/b#> .\n"
                   + "".join(f"ex:n{i} ex:p ex:n{i + 1} .\n" for i in range(n)), encoding="utf-8")
    assert cli.main([str(ttl), "-o", str(tmp_path / "big.html")]) == 0
    assert "stress layout" in capsys.readouterr().err


def test_cli_output_is_identical_across_processes(tmp_path):
    pages = []
    for seed in ("1", "2"):
        out = tmp_path / f"solar-{seed}.html"
        r = subprocess.run([sys.executable, "-m", "ttl3d",
                            str(REPO / "examples" / "solar-system.ttl"),
                            str(REPO / "examples" / "solar-system-missions.ttl"), "-o", str(out)],
                           capture_output=True, text=True, cwd=REPO,
                           env={**os.environ, "PYTHONHASHSEED": seed})
        assert r.returncode == 0, r.stderr
        pages.append(out.read_bytes())
    assert pages[0] == pages[1]
