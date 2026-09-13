"""ttl3d.cli: the command line entry point."""
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import pytest
from rdflib import URIRef

from ttl3d import cli

REPO = Path(__file__).resolve().parents[1]


def test_cli_writes_the_page_and_reports_what_it_did(tmp_path, library, library_extra, capsys):
    out = tmp_path / "lib.html"
    rc = cli.main([str(library), str(library_extra), "-o", str(out), "--title", "Lib"])
    assert rc == 0
    html = out.read_text(encoding="utf-8")
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
    assert 'data-group="Book"' in out.read_text(encoding="utf-8")


def test_cli_force_layout_leaves_nodes_unpinned(tmp_path, library):
    out = tmp_path / "f.html"
    cli.main([str(library), "-o", str(out), "--layout", "force"])
    assert '"pinned": false' in out.read_text(encoding="utf-8")


def test_cli_hover_labels_disable_both_label_layers(tmp_path, library):
    out = tmp_path / "h.html"
    cli.main([str(library), "-o", str(out), "--labels", "hover"])
    assert '"node": false' in out.read_text(encoding="utf-8") and '"edge": false' in out.read_text(encoding="utf-8")


def test_cli_rejects_an_unknown_color_key(library):
    with pytest.raises(SystemExit) as e:
        cli.main([str(library), "--color-by", "colour"])
    assert e.value.code == 2


def test_module_entry_point_runs(tmp_path, library):
    out = tmp_path / "m.html"
    r = subprocess.run([sys.executable, "-m", "ttl3d", str(library), "-o", str(out)],
                       capture_output=True, text=True, cwd=REPO, check=False)
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


SOLAR = ("examples/solar-system.ttl", "examples/solar-system-missions.ttl")
TRIG = ("tests/fixtures/library.trig",)


FOCUS = ("--focus", ":Earth", "--hops", "2")


@pytest.mark.parametrize(("view", "inputs", "extra"),
                         [("3d", SOLAR, ()), ("2d", SOLAR, ()), ("3d", TRIG, ()), ("3d", SOLAR, FOCUS)],
                         ids=["solar-3d", "solar-2d", "trig-3d", "solar-focus"])
def test_cli_output_is_identical_across_processes(tmp_path, view, inputs, extra):
    pages = []
    for seed in ("1", "2"):
        out = tmp_path / f"page-{seed}.html"
        r = subprocess.run([sys.executable, "-m", "ttl3d", *(str(REPO / p) for p in inputs),
                            "-o", str(out), "--view", view, *extra],
                           capture_output=True, text=True, cwd=REPO, check=False,
                           env={**os.environ, "PYTHONHASHSEED": seed})
        assert r.returncode == 0, r.stderr
        pages.append(out.read_bytes())
    assert pages[0] == pages[1]


def test_cli_lang_picks_the_label_language(tmp_path):
    ttl = tmp_path / "lang.ttl"
    ttl.write_text("@prefix ex: <http://example.org/l#> .\n"
                   "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
                   'ex:z rdfs:label "Zebra"@en, "Antilope"@de ; ex:p ex:b .\n', encoding="utf-8")
    out = tmp_path / "l.html"
    cli.main([str(ttl), "-o", str(out)])
    assert '"label": "Zebra"' in out.read_text(encoding="utf-8")
    cli.main([str(ttl), "-o", str(out), "--lang", "de"])
    assert '"label": "Antilope"' in out.read_text(encoding="utf-8")


def test_cli_format_flag(tmp_path, library):
    weird = tmp_path / "data.txt"
    weird.write_text(library.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "f.html"
    assert cli.main([str(weird), "-o", str(out), "--format", "xml"]) == 1      # forced parser rejects Turtle
    assert cli.main([str(weird), "-o", str(out), "--format", "turtle"]) == 0 and out.exists()


def test_cli_type_links_and_attribute_preds(tmp_path, library):
    out = tmp_path / "t.html"
    cli.main([str(library), "-o", str(out), "--type-links", "--attribute-preds", "ex:wrote,rdfs:subClassOf"])
    payload = out.read_text(encoding="utf-8").split("const DATA = ", 1)[1].split(";\n", 1)[0]
    assert '"predicates": ["type"]' in payload          # Herbert -> Author is now drawn
    assert '"predicates": ["wrote"]' not in payload     # ex:wrote is demoted to the card
    assert '"predicates": ["subClassOf"]' not in payload


def test_cli_unknown_prefix_in_attribute_preds_is_a_clean_error(tmp_path, library, capsys):
    rc = cli.main([str(library), "-o", str(tmp_path / "x.html"), "--attribute-preds", "nope:thing"])
    assert rc == 1 and "nope" in capsys.readouterr().err


def test_cli_pages_start_in_3d(tmp_path, library):
    out = tmp_path / "d.html"
    assert cli.main([str(library), "-o", str(out)]) == 0
    assert '"view": "3d"' in out.read_text(encoding="utf-8")


def _first_node(page_path):
    payload = page_path.read_text(encoding="utf-8").split("const DATA = ", 1)[1].split(";\n", 1)[0]
    return json.loads(payload)["nodes"][0]


def test_cli_pinned_pages_carry_a_layout_per_view(tmp_path, library):
    out = tmp_path / "p.html"
    assert cli.main([str(library), "-o", str(out)]) == 0
    assert {"x", "y", "z", "x2", "y2"} <= set(_first_node(out))
    assert cli.main([str(library), "-o", str(out), "--layout", "force"]) == 0
    assert not {"x", "y", "z", "x2", "y2"} & set(_first_node(out))


def test_cli_view_flag_sets_the_starting_view_and_the_default_name(tmp_path, library, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main([str(library), "--view", "2d"]) == 0
    assert '"view": "2d"' in (tmp_path / "library-2d.html").read_text(encoding="utf-8")
    assert "view: 2d" in capsys.readouterr().out


def test_cli_rejects_an_unknown_view(library):
    with pytest.raises(SystemExit) as e:
        cli.main([str(library), "--view", "4d"])
    assert e.value.code == 2


def test_output_naming_an_input_in_another_case_is_refused_where_the_filesystem_ignores_case(tmp_path, library,
                                                                                            capsys):
    (tmp_path / "probe").write_text("", encoding="utf-8")
    if not (tmp_path / "PROBE").exists():
        pytest.skip("case-sensitive filesystem")
    src = tmp_path / "graph.ttl"
    src.write_text(library.read_text(encoding="utf-8"), encoding="utf-8")
    rc = cli.main([str(src), "-o", str(tmp_path / "GRAPH.TTL")])
    assert rc == 1 and "also an input" in capsys.readouterr().err
    assert src.read_text(encoding="utf-8") == library.read_text(encoding="utf-8")   # the input is intact


ASCII_CONSOLE = {**os.environ, "PYTHONIOENCODING": "ascii"}   # a console that cannot show an é


def test_an_error_message_survives_a_console_that_cannot_encode_it(tmp_path):
    bad = tmp_path / "données.ttl"
    bad.write_text("@prefix ex: <http://example.org/é#> .\nex:a ex:b \"unterminated .\n", encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "ttl3d", str(bad), "-o", str(tmp_path / "out.html")],
                       capture_output=True, env=ASCII_CONSOLE, cwd=REPO, check=False)
    err = r.stderr.decode("ascii")
    assert r.returncode == 1 and err.startswith("ttl3d: error:") and "Traceback" not in err, err


def test_the_summary_line_survives_a_console_that_cannot_encode_the_output_path(tmp_path, library):
    out = tmp_path / "sortie-é.html"
    r = subprocess.run([sys.executable, "-m", "ttl3d", str(library), "-o", str(out)],
                       capture_output=True, env=ASCII_CONSOLE, cwd=REPO, check=False)
    assert r.returncode == 0 and out.exists(), r.stderr.decode("ascii", "replace")
    assert r.stdout.decode("ascii").split()[0].isdigit()


def _run_with_stdin(args, stdin: bytes, cwd):
    return subprocess.run([sys.executable, "-m", "ttl3d", *args], input=stdin, capture_output=True,
                          cwd=cwd, check=False)


def test_a_dash_reads_turtle_from_standard_input_and_names_the_page_stdin(tmp_path, library):
    r = _run_with_stdin(["-"], library.read_bytes(), tmp_path)
    assert r.returncode == 0, r.stderr.decode()
    page = (tmp_path / "stdin-3d.html").read_text(encoding="utf-8")
    assert "<title>stdin</title>" in page and b"stdin-3d.html" in r.stdout


def test_format_applies_to_standard_input(tmp_path, tiny_nq):
    r = _run_with_stdin(["-", "--format", "nquads", "-o", "nq.html"], tiny_nq.read_bytes(), tmp_path)
    assert r.returncode == 0, r.stderr.decode()
    assert 'nt#G"' in (tmp_path / "nq.html").read_text(encoding="utf-8")     # the named graph is a group


def test_a_dash_mixes_with_files(tmp_path, library, library_extra):
    r = _run_with_stdin([str(library), "-", "-o", "mix.html"], library_extra.read_bytes(), tmp_path)
    assert r.returncode == 0, r.stderr.decode()
    assert b"12 nodes" in r.stdout and b"6 links" in r.stdout


def test_bad_standard_input_is_a_one_line_error_naming_stdin(tmp_path):
    r = _run_with_stdin(["-", "-o", "x.html"], b"this is not turtle @@@\n", tmp_path)
    assert r.returncode == 1
    err = r.stderr.decode()
    assert err.startswith("ttl3d: error: stdin: cannot parse as turtle") and err.count("\n") == 1
    assert not (tmp_path / "x.html").exists()


def test_standard_input_can_be_given_only_once(tmp_path, capsys):
    assert cli.main(["-", "-", "-o", str(tmp_path / "x.html")]) == 1     # fails before reading stdin
    assert capsys.readouterr().err == "ttl3d: error: standard input can be given only once\n"


def test_focus_and_schema_slice_the_page_and_announce_it(tmp_path, library, library_extra, capsys):
    out = tmp_path / "s.html"
    both = [str(library), str(library_extra)]
    assert cli.main([*both, "--focus", "ex:Dune", "-o", str(out)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("3 nodes, 2 links")
    assert captured.err == "kept 3 of 12 nodes (focus ex:Dune, 1 hop)\n"
    assert cli.main([*both, "--focus", "http://example.org/library#Dune,ex:Asimov", "--focus", "ex:Book",
                     "--hops", "0", "-o", str(out)]) == 0
    assert capsys.readouterr().out.startswith("3 nodes, 0 links")     # a union; no links at hop 0
    assert cli.main([*both, "--schema", "-o", str(out)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("5 nodes, 3 links")
    assert captured.err == "kept 5 of 12 nodes (schema only)\n"
    # library-extra owns no schema term, so it has no legend row here
    assert '"groups": ["library"]' in out.read_text(encoding="utf-8")


def test_an_empty_focus_is_an_error(tmp_path, library, capsys):
    out = tmp_path / "s.html"
    assert cli.main([str(library), "--focus", ",", "-o", str(out)]) == 1
    assert capsys.readouterr().err == "ttl3d: error: --focus is empty\n"
    assert not out.exists()


def test_hops_needs_focus_and_bad_focus_or_hops_are_one_line_errors(tmp_path, library, capsys):
    out = tmp_path / "s.html"
    assert cli.main([str(library), "--hops", "2", "-o", str(out)]) == 1
    assert capsys.readouterr().err == "ttl3d: error: --hops needs --focus\n"
    assert cli.main([str(library), "--focus", "ex:Nope", "-o", str(out)]) == 1
    assert capsys.readouterr().err == ("ttl3d: error: focus <http://example.org/library#Nope> "
                                       "is not a node in the data\n")
    assert cli.main([str(library), "--focus", "ex:Dune", "--hops", "-1", "-o", str(out)]) == 1
    assert capsys.readouterr().err.startswith("ttl3d: error: hops must be a non-negative integer")
    assert not out.exists()


def test_a_bad_hop_count_is_refused_before_standard_input_is_read(tmp_path):
    # the write end stays open and unfed: a CLI that read standard input before checking --hops would
    # block here until the timeout, so a fast exit with the hops error proves the order
    proc = subprocess.Popen([sys.executable, "-m", "ttl3d", "-", "--focus", "ex:a", "--hops", "-1",
                             "-o", str(tmp_path / "x.html")], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=REPO)
    try:
        code = proc.wait(timeout=30)
        err = proc.stderr.read()
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        pytest.fail("the CLI read standard input before checking --hops")
    finally:
        proc.stdin.close()
        proc.stdout.close()
        proc.stderr.close()
    assert code == 1 and err.startswith("ttl3d: error: hops must be a non-negative integer")


def _generated(tmp_path, subjects=2000, links=9):
    """A seeded random graph: every subject has a label and `links` outgoing edges."""
    rnd = random.Random(7)
    lines = []
    for i in range(subjects):
        lines.append(f'<http://g/s{i}> <http://www.w3.org/2000/01/rdf-schema#label> "s {i}" .')
        for k in range(links):
            lines.append(f'<http://g/s{i}> <http://g/p{k % 3}> <http://g/s{rnd.randrange(subjects)}> .')
    nt = tmp_path / "gen.nt"
    nt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return nt


def test_a_two_hop_slice_of_a_generated_graph_is_identical_across_processes(tmp_path):
    nt = _generated(tmp_path)
    pages = []
    for seed in ("1", "2"):
        out = tmp_path / f"gen-{seed}.html"
        r = subprocess.run([sys.executable, "-m", "ttl3d", str(nt), "--focus", "<http://g/s0>", "--hops", "2",
                            "--layout", "force", "-o", str(out)], capture_output=True, text=True, cwd=REPO,
                           check=False, env={**os.environ, "PYTHONHASHSEED": seed})
        assert r.returncode == 0, r.stderr
        assert r.stderr.startswith("kept ")
        assert r.stderr.endswith(" of 2000 nodes (focus http://g/s0, 2 hops)\n")
        pages.append(out.read_bytes())
    assert pages[0] == pages[1]


def test_a_two_hop_slice_of_twenty_thousand_triples_takes_well_under_two_seconds(tmp_path):
    from ttl3d import graph, load, slice
    ds = load.load_files([_generated(tmp_path)])
    start = time.perf_counter()
    data = graph.build(slice.select(ds, focus=[URIRef("http://g/s0")], hops=2).dataset)
    assert time.perf_counter() - start < 2.0                                  # about ten times what it takes
    assert 100 < len(data["nodes"]) < 2000
