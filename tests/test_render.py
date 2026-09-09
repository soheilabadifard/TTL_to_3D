"""ttl3d.render: the self-contained HTML page and the behaviors settled with the user."""
import shutil, subprocess
import pytest
from ttl3d import load, graph, render


@pytest.fixture
def data(library, library_extra):
    return graph.build(load.load_files([library, library_extra]))


@pytest.fixture
def html(data):
    return render.render_html(data, title="Library", pinned=True,
                              labels={"node": True, "edge": True})


def test_page_is_self_contained(html):
    assert "<script src=" not in html
    assert 'src="http' not in html and 'href="http' not in html
    assert "sourceMappingURL" not in html
    for g in ("ForceGraph3D", "SpriteText", "THREE"):
        assert g in html, g
    assert '"nodes"' in html and 'id="detail"' in html
    assert "<title>Library</title>" in html


def test_legend_lists_every_group_with_its_color_and_is_clickable(html):
    colors = render.assign_colors(["library", "library-extra"])
    for g in ("library", "library-extra"):
        assert f'data-group="{g}"' in html, g
        assert colors[g] in html


def test_no_fog(html):
    # white fog made distant nodes vanish on zoom-out; settled with the user.
    # three.js itself defines Fog classes, so only the app script is checked.
    app = html.rsplit("<script>", 1)[1]
    assert "Fog(" not in app and "FogExp2" not in app and "scene.fog" not in app


def test_inclusive_legend_selection_is_pinned(html):
    # a selected group keeps its nodes, their neighbors, and the edges it asserts
    assert "INCLUSIVE_SELECTION = true" in html


def test_settled_force_constants(html):
    assert "26 + 1.6 *" in html and "strength(-80)" in html


def test_label_that_closes_a_script_tag_cannot_break_the_page(html):
    assert "</script> label" not in html          # escaped inside the JSON payload
    assert html.count("</script>") == 2            # the bundle and the app, nothing else


def test_config_is_embedded(data):
    pinned = render.render_html(data, title="x", pinned=True, labels={"node": True, "edge": False})
    assert '"pinned": true' in pinned and '"node": true' in pinned and '"edge": false' in pinned
    free = render.render_html(data, title="x", pinned=False, labels={"node": False, "edge": False})
    assert '"pinned": false' in free


def test_palette_cycles_and_unknown_is_gray():
    colors = render.assign_colors([f"g{i}" for i in range(15)])
    assert len(colors) == 16 and colors["?"] == render.UNKNOWN_COLOR
    assert len(set(colors.values())) == len(render.PALETTE) + 1


def test_group_names_are_html_escaped_in_the_legend(data):
    for n in data["nodes"]:
        n["group"] = 'a"b<c'
    data["groups"] = ['a"b<c']
    html = render.render_html(data, title="t", pinned=False, labels={"node": True, "edge": True})
    assert 'data-group="a&quot;b&lt;c"' in html


def test_write_html_creates_parent_directories(tmp_path):
    out = render.write_html("<p>x</p>", tmp_path / "deep" / "er" / "page.html")
    assert out.read_text() == "<p>x</p>"


def test_viewer_assets_are_files_and_are_inlined(html):
    assert render.VIEWER_CSS.name == "viewer.css" and render.VIEWER_JS.name == "viewer.js"
    css = render.VIEWER_CSS.read_text(encoding="utf-8")
    js = render.VIEWER_JS.read_text(encoding="utf-8")
    assert css.strip() and css in html
    assert js.startswith("const DATA = __DATA__;") and "__DATA__" not in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_viewer_js_is_valid_javascript(tmp_path):
    js = render.VIEWER_JS.read_text(encoding="utf-8")
    for key in ("__DATA__", "__COLORS__", "__CONFIG__"):
        js = js.replace(key, "{}")
    probe = tmp_path / "viewer-probe.js"
    probe.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(probe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
