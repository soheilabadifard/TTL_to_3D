"""Completeness review: documented or implemented behaviour no test pinned down.

Gaps found (one test each below; "uncovered" refers to `pytest --cov=ttl3d`, baseline 99%):

1.  api.py:62/88 -- `focus` and `attribute_preds` are typed `Iterable[str | URIRef]`, which a
    plain `str` (or a single `URIRef`, itself a str subclass) satisfies, but `build_page` iterated
    it into characters and died with "unknown prefix in 'e'". A bare term is one term now, as
    `load._items` already treated a bare path string (fixed; the test failed when written).
2.  README "Options" table, `--version`; cli.py:74 -- the flag is documented ("Print ttl3d
    <version> and exit") and implemented, but no test ever runs it.
3.  README "From tables" -- "A minted id is percent-encoded, so --focus names an id with a space
    as `csv:New%20York`". The minting is tested (test_table.py) but the documented --focus round
    trip onto a minted node never is.
4.  README "Options" table, the `-` row -- "Relative IRIs resolve against the working directory".
    Only the endpoint-relative case is tested (test_load.py); standard input never is.
5.  table.py:199 (uncovered) -- `columns=` that is not a Mapping is a documented TypeError
    ("columns must be a mapping of role to header") that no test exercises.
6.  table.py:189 (uncovered) -- a DataFrame-like whose `to_csv` returns non-text is refused with
    a TypeError naming the source; untested user-facing failure mode.
7.  render.py:99 (uncovered) -- the vendored bundle is refused if it ever contains `</script`
    (the VENDOR.md rebuild recipe could reintroduce one); the guard is never exercised.
8.  sparql.py:116-117 (uncovered) -- a server-sent redirect URL with a malformed port must not
    crash the one-line redirect refusal; `_clean` is never run against such a URL.
9.  README "Slicing a big graph" -- "The same three keyword arguments exist on ttl3d.to_html,
    write and show": to_html and show are tested, `write(..., focus=...)` is not.
10. api.to_html docstring -- "`title=None` means the first source's name; an empty string is an
    empty title". Only the CLI's `--title ""` -> stem mapping is tested, never the API's "".
11. load.py:_split -- an in-memory rdflib.Dataset whose default graph is empty (only named
    graphs) is documented loader behaviour ("no key when it is empty and named graphs exist");
    tested for TriG files only, never for a Dataset object. (load.py:227, the `default is None`
    fallback, is defensive dead code: rdflib always yields a default context, even after
    `remove_graph(default_context)`; reported, not testable.)
12. cli.py:206 -- the summary line's `labels:` field ("node+edge", "hover only") is part of the
    CLI's printed contract but no test asserts it.

Also reported without a test: cli.py:111/113 and 127-130 measure as uncovered only because the
tests that exercise them run the CLI in a subprocess; sparql.py:254 (a URLError whose reason is a
connect-phase TimeoutError) is not reliably reproducible on CI machines.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from rdflib import Dataset as RdfDataset
from rdflib import URIRef

import ttl3d
from ttl3d import cli, render, sparql


def _page_data(html: str) -> dict:
    """The DATA object the page embeds (render.script_safe escapes <, > and & as \\u00XX)."""
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.DOTALL)
    return json.loads(m.group(1))


def test_comp_1_a_bare_string_or_uriref_term_is_one_term(library, library_extra):
    # `focus: Iterable[str | URIRef]` and `attribute_preds: Iterable[str | URIRef]` admitted a bare
    # string (and a single URIRef, a str subclass), but build_page iterated it into characters
    # and raised "unknown prefix in 'e'". Sources already treated a bare str as one item
    # (load._items); terms do too now (api._listed).
    both = [library, library_extra]
    listed = ttl3d.to_html(both, focus=["ex:Dune"])
    assert ttl3d.to_html(both, focus="ex:Dune") == listed
    assert ttl3d.to_html(both, focus=URIRef("http://example.org/library#Dune")) == listed
    as_pred = ttl3d.to_html(library, attribute_preds=["ex:wrote"])
    assert ttl3d.to_html(library, attribute_preds="ex:wrote") == as_pred


def test_comp_2_the_version_flag_prints_the_version_and_exits_zero(capsys):
    # NOTE: previously untested. README "Options": "--version | flag | Print ttl3d <version> and exit."
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out == f"ttl3d {ttl3d.__version__}\n"


def test_comp_3_focus_names_a_minted_table_id_by_its_encoded_curie(tmp_path):
    # NOTE: previously untested. README "From tables": "--focus names an id with a space as
    # csv:New%20York (the card's IRI shows the form to use)".
    f = tmp_path / "places.csv"
    f.write_text("source,target\nNew York,Boston\n", encoding="utf-8")
    data = _page_data(ttl3d.to_html([f], focus=["csv:New%20York"]))
    assert sorted(n["id"] for n in data["nodes"]) == ["urn:x-ttl3d:Boston", "urn:x-ttl3d:New%20York"]
    label = {n["id"]: n["label"] for n in data["nodes"]}
    assert label["urn:x-ttl3d:New%20York"] == "New York"     # a minted node keeps its id as label


def test_comp_4_relative_iris_on_standard_input_resolve_against_the_working_directory(tmp_path):
    # NOTE: previously untested. README "Options", the `-` row: "Relative IRIs resolve against
    # the working directory (a file's resolve against its folder)". pytest replaces sys.stdin,
    # so like test_cli.py this runs the module in a subprocess.
    r = subprocess.run([sys.executable, "-m", "ttl3d", "-", "-o", "rel.html"],
                       input=b"<rel/a> <http://example.org/q#p> <rel/b> .\n",
                       capture_output=True, cwd=tmp_path, check=False, timeout=300)
    assert r.returncode == 0, r.stderr.decode("ascii", "replace")
    here = Path(os.path.realpath(tmp_path))
    ids = {n["id"] for n in _page_data((tmp_path / "rel.html").read_text(encoding="utf-8"))["nodes"]}
    assert ids == {(here / "rel" / "a").as_uri(), (here / "rel" / "b").as_uri()}


def test_comp_5_columns_that_is_not_a_mapping_is_a_type_error(people):
    # NOTE: previously untested (table.py:199). The API documents columns as a Mapping; a list
    # of pairs is a plausible mistake and must be refused before any file is read.
    with pytest.raises(TypeError, match="columns must be a mapping of role to header, got list"):
        ttl3d.to_html(people, columns=[("label", "name")])


def test_comp_6_a_frame_whose_to_csv_is_not_text_is_refused():
    # NOTE: previously untested (table.py:189). A DataFrame is recognised duck-typed through
    # to_csv; one whose to_csv does not return text is a user-facing failure mode.
    class Frame:
        columns = ("id",)

        def to_csv(self, index=True):
            return None

    with pytest.raises(TypeError, match="bad: to_csv gave NoneType, not text"):
        ttl3d.to_html(("bad", Frame()))


def test_comp_7_a_vendored_bundle_holding_a_closing_script_tag_is_refused(tmp_path, monkeypatch):
    # NOTE: previously untested (render.py:99). The guard protects the page against a rebuilt
    # bundle (VENDOR.md) that inlines `</script>`; it has never been exercised.
    bad = tmp_path / "bundle.js"
    bad.write_text("x = '</script>';\n", encoding="utf-8")
    monkeypatch.setattr(render, "VENDOR_JS", bad)
    data = {"nodes": [], "links": [], "groups": [], "graphs": {}}
    with pytest.raises(ValueError, match="vendored bundle contains a closing script tag"):
        render.render_html(data, title="t", pinned=False, labels={"node": False, "edge": False})


def test_comp_8_a_redirect_url_with_a_malformed_port_survives_the_message():
    # NOTE: previously untested (sparql.py:116-117). A server can send anything in Location;
    # the redirect refusal must still name scheme, host and path without crashing on the port.
    assert sparql._clean("http://h:8080/x?q=1#f") == "http://h:8080/x"
    assert sparql._clean("http://h:abc/x?q=1#f") == "http://h/x"


def test_comp_9_write_takes_the_slicing_options(library, library_extra, tmp_path):
    # NOTE: previously untested. README "Slicing a big graph": "The same three keyword arguments
    # exist on ttl3d.to_html, write and show" -- to_html and show were tested, write was not.
    out = ttl3d.write([library, library_extra], tmp_path / "w.html", focus=["ex:Dune"], hops=0)
    data = _page_data(out.read_text(encoding="utf-8"))
    assert [n["label"] for n in data["nodes"]] == ["Dune"]
    assert out.exists()


def test_comp_10_an_empty_string_title_is_an_empty_title(library):
    # NOTE: previously untested. api.to_html's docstring: "an empty string is an empty title
    # (unlike `--title ""` on the command line, which the CLI maps to `None`)".
    html = ttl3d.to_html(library, title="")
    assert "<title></title>" in html and "<h1></h1>" in html


def test_comp_11_a_dataset_with_only_named_graphs_loads_them_and_keeps_the_pair_name():
    # NOTE: previously untested. load()'s rule "no key when [the default graph] is empty and
    # named graphs exist" was pinned for TriG files only, never for an rdflib.Dataset object.
    rds = RdfDataset()
    rds.graph(URIRef("urn:g")).add((URIRef("urn:s"), URIRef("urn:p"), URIRef("urn:o")))
    data = _page_data(ttl3d.to_html(("d", rds)))
    assert data["groups"] == ["urn:g"] and data["graphs"] == {"urn:g": "urn:g"}
    assert sorted(n["id"] for n in data["nodes"]) == ["urn:o", "urn:s"]


def test_comp_12_the_summary_line_names_the_label_layers(tmp_path, library, capsys):
    # NOTE: previously untested (cli.py:206). The summary's labels field is part of the CLI's
    # printed contract: "node+edge" when a layer is on, "hover only" when neither is.
    out = tmp_path / "l.html"
    assert cli.main([str(library), "-o", str(out)]) == 0
    assert "labels: node+edge)" in capsys.readouterr().out
    assert cli.main([str(library), "-o", str(out), "--labels", "hover"]) == 0
    assert "labels: hover only)" in capsys.readouterr().out
