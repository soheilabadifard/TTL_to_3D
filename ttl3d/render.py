"""Render the node/link model as one self-contained HTML page.

The vendored fg3d bundle (3d-force-graph + three-spritetext over one shared
three.js) is inlined, so the page works offline with zero installs and never
fetches from a CDN. The viewer's CSS and JS live in viewer.css / viewer.js
next to this file and are inlined at render time. Nodes are shaded spheres
with optional permanent labels, links are colored by the file asserting them
(file mode) with predicate labels at their midpoints, the legend filters
inclusively, and a card opens on click with the node's definition, synonyms,
literal properties, relations and sources.
"""
from __future__ import annotations
import html as _html
import json
import re
from pathlib import Path

VENDOR_JS = Path(__file__).parent / "vendor" / "fg3d-bundle.min.js"
VIEWER_CSS = Path(__file__).parent / "viewer.css"
VIEWER_JS = Path(__file__).parent / "viewer.js"
# saturated-on-white categorical palette; cycles past twelve groups
PALETTE = ["#ca8a04", "#dc2626", "#2563eb", "#7c3aed", "#16a34a", "#0891b2",
           "#ea580c", "#db2777", "#4d7c0f", "#b45309", "#0f766e", "#111827"]
UNKNOWN_COLOR = "#9ca3af"


def assign_colors(groups) -> dict:
    colors = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(g for g in groups if g != "?")}
    colors["?"] = UNKNOWN_COLOR
    return colors


def _bundle() -> str:
    lib = _read(VENDOR_JS)
    if "</script" in lib:  # would break the inline embedding
        raise ValueError("vendored bundle contains a closing script tag")
    return "\n".join(l for l in lib.splitlines() if not l.startswith("//# sourceMappingURL"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


_PLACEHOLDER = re.compile(r"__[A-Z]+__")


def script_safe(value) -> str:
    """JSON that is safe inside a <script> block: every '<', '>' and '&' becomes a
    JS unicode escape, so no label, title or IRI can open or close a tag or an
    HTML comment (the HTML5 tokenizer treats "<!--" + "<script" specially)."""
    return (json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026"))


def fill(template: str, values: dict[str, str]) -> str:
    """Substitute every known __KEY__ in one pass. Unknown tokens (the vendor bundle
    contains __THREE__) are left alone, and substituted text is never rescanned,
    so data containing a placeholder name cannot be substituted a second time."""
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(), m.group()), template)


def render_html(data: dict, *, title: str, pinned: bool, labels: dict) -> str:
    esc = lambda s: _html.escape(str(s), quote=True)
    colors = assign_colors(data["groups"])
    legend = "".join(
        f'<div class="row grp" data-group="{esc(g)}"><span class="dot" '
        f'style="background:{colors.get(g, UNKNOWN_COLOR)}"></span>{esc(g)}</div>'
        for g in data["groups"])
    config = {"title": title, "colorBy": data.get("color_by", "file"),
              "pinned": bool(pinned), "labels": {"node": bool(labels["node"]),
                                                 "edge": bool(labels["edge"])}}
    app = fill(_read(VIEWER_JS), {"__DATA__": script_safe(data),
                                  "__COLORS__": script_safe(colors),
                                  "__CONFIG__": script_safe(config)})
    return fill(HTML_TEMPLATE, {
        "__CSS__": _read(VIEWER_CSS), "__LIB__": _bundle(), "__APP__": app,
        "__LEGEND__": legend, "__TITLE__": esc(title), "__COLORBY__": esc(config["colorBy"]),
        "__COUNTS__": f'{len(data["nodes"])} nodes / {len(data["links"])} links'})


def write_html(html: str, out: Path | str) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
__CSS__</style>
</head>
<body>
<div id="panel">
  <h1>__TITLE__</h1>
  <div class="sub">__COUNTS__ · colored by __COLORBY__</div>
  __LEGEND__
  <input id="q" placeholder="search labels…" autocomplete="off">
  <label class="tog"><input type="checkbox" id="nodelabels"> node labels</label>
  <label class="tog"><input type="checkbox" id="edgelabels"> edge relation labels</label>
  <label class="tog"><input type="checkbox" id="physics"> free-float physics
    <span title="off = pinned stress-minimized layout (Kamada-Kawai); on = live force simulation" style="color:#9ca3af">?</span></label>
  <button id="clear">clear filters</button>
  <div id="hint">click legend rows to light a group's nodes, their neighbors, and the edges it asserts ·
    edges wear the color of the file asserting them when coloring by file ·
    drag to rotate · scroll to zoom · click a node for details</div>
</div>
<div id="detail"><button id="close">×</button><div id="detail-body"></div></div>
<div id="graph"></div>
<script>__LIB__</script>
<script>
__APP__</script>
</body>
</html>
"""
