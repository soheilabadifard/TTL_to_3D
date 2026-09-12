"""ttl3d.api: the Python entry point, the same pipeline as the command line."""
import json
import re

import pytest
from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef

import ttl3d
from ttl3d import api, cli, layout

EX = Namespace("http://example.org/mem#")


def _page_data(html: str) -> dict:
    """The DATA object the page embeds (render.script_safe escapes <, > and & as \\u00XX)."""
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.DOTALL)
    return json.loads(m.group(1))


def test_to_html_returns_the_page_for_paths(library, library_extra):
    html = ttl3d.to_html([library, library_extra])
    assert html.count("</script>") == 2 and "<title>library</title>" in html
    assert len(_page_data(html)["nodes"]) == 12          # the counts the CLI test pins for these two files


def test_to_html_takes_an_in_memory_graph_and_names_the_title_after_it():
    g = Graph()
    g.add((EX.a, EX.p, EX.b))
    html = ttl3d.to_html(("planets", g))
    assert "<title>planets</title>" in html and len(_page_data(html)["nodes"]) == 2


def test_options_reach_the_page(library, library_extra):
    html = ttl3d.to_html([library, library_extra], title="Lib", view="2d", color_by="type",
                        labels="hover", layout="force", lang="fr", type_links=True)
    assert "<title>Lib</title>" in html
    assert '"view": "2d"' in html and '"pinned": false' in html
    assert '"labels": {"node": false, "edge": false}' in html
    assert _page_data(html)["color_by"] == "type"


def test_lang_picks_the_label_and_type_links_draw_rdf_type():
    g = Graph()
    g.add((EX.apple, RDFS.label, Literal("apple", lang="en")))
    g.add((EX.apple, RDFS.label, Literal("Apfel", lang="de")))
    g.add((EX.apple, RDF.type, EX.Fruit))
    labels = {lang: {n["id"]: n["label"] for n in _page_data(ttl3d.to_html(("g", g), lang=lang))["nodes"]}
              for lang in ("en", "de")}
    assert labels["en"][str(EX.apple)] == "apple" and labels["de"][str(EX.apple)] == "Apfel"
    plain = _page_data(ttl3d.to_html(("g", g)))
    typed = _page_data(ttl3d.to_html(("g", g), type_links=True))
    assert len(plain["links"]) == 0 and len(typed["links"]) == 1       # rdf:type became the only edge


def test_attribute_preds_accept_cli_strings_and_rdflib_terms(library):
    as_strings = ttl3d.to_html(library, attribute_preds=["ex:wrote"])
    as_terms = ttl3d.to_html(library, attribute_preds=[URIRef("http://example.org/library#wrote")])
    assert as_strings == as_terms


def test_bad_options_and_sources_raise(library, tmp_path):
    with pytest.raises(ValueError, match="view"):
        ttl3d.to_html(library, view="4d")
    with pytest.raises(ValueError, match="layout"):
        ttl3d.to_html(library, layout="random")
    with pytest.raises(ValueError, match="labels"):
        ttl3d.to_html(library, labels="sometimes")
    with pytest.raises(ValueError, match="color_by"):
        ttl3d.to_html(tmp_path / "missing.ttl", color_by="colour")      # checked before any file is read
    with pytest.raises(ValueError, match="prefix"):
        ttl3d.to_html(library, attribute_preds=["nope:thing"])
    with pytest.raises(FileNotFoundError):
        ttl3d.to_html(tmp_path / "missing.ttl")
    with pytest.raises(TypeError):
        ttl3d.to_html(42)
    with pytest.raises(ValueError, match="source"):
        ttl3d.to_html([])


def test_write_creates_parents_and_writes_lf(tmp_path, library):
    out = ttl3d.write(library, tmp_path / "deep" / "er" / "lib.html", view="2d")
    data = out.read_bytes()
    assert out.exists() and b"\r" not in data and b'"view": "2d"' in data


def test_the_api_is_silent_even_when_the_cli_would_announce_the_layout(capsys, library, monkeypatch):
    monkeypatch.setattr(layout, "PROGRESS_MIN_NODES", 0)      # the fixture is small; force the notice path
    ttl3d.to_html(library)
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_fmt_reaches_the_parser(library):
    # a forced parser that does not fit proves fmt is forwarded (the loader would otherwise
    # guess Turtle and succeed)
    with pytest.raises(ValueError, match="cannot parse as xml"):
        ttl3d.to_html(library, fmt="xml")


def test_write_raises_when_the_path_cannot_be_written(tmp_path, library):
    with pytest.raises(OSError):
        ttl3d.write(library, tmp_path)                 # a directory, not a file


def test_build_page_reports_what_the_cli_prints(library, library_extra):
    built = api.build_page([library, library_extra], title="Lib", color_by="file", layout="auto",
                           labels="auto", view="3d", lang="en", type_links=False,
                           attribute_preds=(), fmt=None, notice=None)
    assert (built.n_nodes, built.n_links, built.layout_mode) == (12, 6, "stress")
    assert built.labels == {"node": True, "edge": True} and "<title>Lib</title>" in built.html


def test_write_and_the_cli_produce_the_same_bytes(tmp_path, library, library_extra):
    via_api = ttl3d.write([library, library_extra], tmp_path / "api.html",
                          title="Lib", view="2d", color_by="type", attribute_preds=["ex:wrote"])
    rc = cli.main([str(library), str(library_extra), "-o", str(tmp_path / "cli.html"),
                   "--title", "Lib", "--view", "2d", "--color-by", "type", "--attribute-preds", "ex:wrote"])
    assert rc == 0
    assert via_api.read_bytes() == (tmp_path / "cli.html").read_bytes()


def test_the_cli_runs_on_the_shared_builder(tmp_path, library, monkeypatch):
    # byte identity alone would pass before the refactor; this proves the call
    seen = {}
    real = api.build_page

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(api, "build_page", spy)
    assert cli.main([str(library), "-o", str(tmp_path / "lib.html"), "--view", "2d", "--title", ""]) == 0
    assert seen["view"] == "2d" and seen["title"] is None          # --title "" still means "use the stem"
    assert "<title>library</title>" in (tmp_path / "lib.html").read_text(encoding="utf-8")


def test_the_cli_still_announces_the_stress_layout_on_stderr(tmp_path, library, library_extra, capsys,
                                                             monkeypatch):
    monkeypatch.setattr(layout, "PROGRESS_MIN_NODES", 0)
    assert cli.main([str(library), str(library_extra), "-o", str(tmp_path / "lib.html")]) == 0
    captured = capsys.readouterr()
    assert "stress" in captured.err.lower() and captured.out.startswith("12 nodes")


def test_show_returns_a_page_that_notebooks_render_as_a_sandboxed_iframe(library):
    page = ttl3d.show(library, height=420)
    assert isinstance(page, ttl3d.Page) and page.html == ttl3d.to_html(library)
    tag = page._repr_html_()
    assert tag.startswith("<iframe srcdoc=\"") and tag.endswith("</iframe>")
    assert 'sandbox="allow-scripts"' in tag and "height:420px" in tag and "allow-same-origin" not in tag


def test_the_iframe_escapes_a_page_that_could_break_out_of_the_attribute(library):
    import html as _html
    page = ttl3d.show(library, title='Say "hi" </iframe><script>')
    tag = page._repr_html_()
    assert tag.count("</iframe>") == 1 and "<script" not in tag[len("<iframe srcdoc=\""):]
    srcdoc = tag[len('<iframe srcdoc="'):tag.index('" sandbox=')]
    assert '"' not in srcdoc and "<" not in srcdoc            # nothing can end the attribute or open a tag
    # the browser unescapes the attribute and gets the exact page back
    assert _html.unescape(srcdoc) == page.html


def test_page_repr_is_short_and_write_writes_the_html(tmp_path, library):
    page = ttl3d.show(library)
    assert repr(page) == f"Page({len(page.html)} bytes, height=600)"
    out = page.write(tmp_path / "lib.html")
    assert out.read_text(encoding="utf-8") == page.html


def test_the_package_promises_exactly_these_names():
    expected = ["Page", "Source", "Sources", "__version__", "show", "to_html", "write"]  # ruff RUF022
    assert ttl3d.__all__ == expected


def test_show_checks_the_height_when_called_not_when_displayed(library):
    with pytest.raises(ValueError):
        ttl3d.show(library, height="tall")
    assert ttl3d.show(library, height=500.0).height == 500
