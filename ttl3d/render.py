"""Render the node/link model as one self-contained HTML page.

The vendored bundle (3d-force-graph + force-graph + three-spritetext over one
shared three.js) is inlined, so the page works offline with zero installs and
never fetches from a CDN. The viewer's CSS and JS live next to this file
(viewer.css; viewer.js shared by both views plus one renderer file per view)
and are inlined at render time. Nodes are shaded spheres with optional
permanent labels, links are colored by the file asserting them (file mode)
with predicate labels at their midpoints, the legend filters inclusively, and
a card opens on click with the node's definition, synonyms, literal
properties, relations and sources.
"""
from __future__ import annotations

import html as _html
import json
import re
from collections import Counter
from pathlib import Path

VENDOR_JS = Path(__file__).parent / "vendor" / "fg-bundle.min.js"
VIEWER_CSS = Path(__file__).parent / "viewer.css"
VIEWER_JS = Path(__file__).parent / "viewer.js"          # shared app
VIEWER_3D_JS = Path(__file__).parent / "viewer-3d.js"    # one renderer file per view, appended after it
VIEWER_2D_JS = Path(__file__).parent / "viewer-2d.js"
# saturated-on-white categorical palette
PALETTE = ["#ca8a04", "#dc2626", "#2563eb", "#7c3aed", "#16a34a", "#0891b2",
           "#ea580c", "#db2777", "#4d7c0f", "#b45309", "#0f766e", "#111827"]
UNKNOWN_COLOR = "#9ca3af"
OTHER_COLOR = "#94a3b8"
MAX_COLORED_GROUPS = 11   # past len(PALETTE) groups, only the largest keep a colour
VIEWS = ("3d", "2d")      # the starting view; the page switches between them
ANNOTATION_ONLY = "declares no node and asserts no edge; what it adds shows on the cards"


def group_counts(data: dict) -> dict:
    """Nodes per group; in file mode every source also counts the links it asserts (all of them, not
    only the ones it asserted first). A source absent from the result owns nothing drawable."""
    counts = Counter(n["group"] for n in data["nodes"])
    if data.get("color_by") == "file":
        counts.update(f for l in data["links"] for f in l["files"])
    return dict(counts)


def annotation_only(group, counts) -> bool:
    """A legend group with nothing drawable of its own: it neither owns a node nor asserts a link.
    Without counts nothing can be told apart, so every group is taken as real."""
    return group != "?" and bool(counts) and not counts.get(group)


def rank_groups(groups, counts=None) -> tuple[set, list]:
    """(groups that get their own colour, groups bucketed as "other"). Annotation-only groups take no
    colour and never join the bucket: their row is drawn muted instead."""
    counts = counts or {}
    named = [g for g in groups if g != "?" and not annotation_only(g, counts)]
    if len(named) <= len(PALETTE):
        return set(named), []
    ranked = sorted(named, key=lambda g: (-counts.get(g, 0), g))
    return set(ranked[:MAX_COLORED_GROUPS]), ranked[MAX_COLORED_GROUPS:]


def assign_colors(groups, counts=None) -> dict:
    top, rest = rank_groups(groups, counts)
    colors = {g: PALETTE[i] for i, g in enumerate(sorted(top))}
    colors.update({g: OTHER_COLOR for g in rest})
    colors["?"] = UNKNOWN_COLOR
    return colors


def _legend(groups, colors, counts, graphs=None) -> str:
    """One clickable row per coloured group. A named-graph key carries its IRI as the hover title; an
    annotation-only source (no node, no link of its own) is muted, keeps its row outside the colour
    ranking, and its title says why."""
    esc = lambda s: _html.escape(str(s), quote=True)
    graphs = graphs or {}
    top, rest = rank_groups(groups, counts)

    def row(g):
        annot = annotation_only(g, counts)
        hints = ([graphs[g]] if g in graphs else []) + ([ANNOTATION_ONLY] if annot else [])
        title = f' title="{esc(". ".join(hints))}"' if hints else ""
        cls = "row grp annot" if annot else "row grp"
        return (f'<div class="{cls}" data-group="{esc(g)}"{title}><span class="dot" '
                f'style="background:{colors.get(g, UNKNOWN_COLOR)}"></span>{esc(g)}</div>')

    rows = [row(g) for g in groups if g in top or g == "?" or annotation_only(g, counts)]
    if rest:
        rows.append(f'<div class="row grp" data-groups="{esc(json.dumps(rest))}"><span class="dot" '
                    f'style="background:{OTHER_COLOR}"></span>other ({len(rest)} groups)</div>')
    return "".join(rows)


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


def viewer_source() -> str:
    """The app script with its placeholders intact: the shared viewer followed by one
    renderer file per view. The renderer files hold function declarations only, so the
    shared top-level code can call them through hoisting; the page and the JavaScript
    syntax test both go through here so they never disagree on the order."""
    return "\n".join(_read(p) for p in (VIEWER_JS, VIEWER_3D_JS, VIEWER_2D_JS))


def render_html(data: dict, *, title: str, pinned: bool, labels: dict, view: str = "3d") -> str:
    if view not in VIEWS:
        raise ValueError(f"view must be one of {VIEWS}, got {view!r}")
    esc = lambda s: _html.escape(str(s), quote=True)
    counts = group_counts(data)
    colors = assign_colors(data["groups"], counts)
    legend = _legend(data["groups"], colors, counts, data["graphs"])
    config = {"title": title, "colorBy": data.get("color_by", "file"),
              "pinned": bool(pinned), "labels": {"node": bool(labels["node"]),
                                                 "edge": bool(labels["edge"])},
              "view": view}
    app = fill(viewer_source(), {"__DATA__": script_safe(data),
                                 "__COLORS__": script_safe(colors),
                                 "__CONFIG__": script_safe(config)})
    return fill(HTML_TEMPLATE, {
        "__CSS__": _read(VIEWER_CSS), "__LIB__": _bundle(), "__APP__": app,
        "__LEGEND__": legend, "__TITLE__": esc(title), "__COLORBY__": esc(config["colorBy"]),
        "__COUNTS__": f'{len(data["nodes"])} nodes / {len(data["links"])} links'})


def write_html(html: str, out: Path | str) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8", newline="\n")   # LF on Windows too: same bytes everywhere
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
  <div class="row views">view
    <label><input type="radio" name="view" value="3d"> 3D</label>
    <label><input type="radio" name="view" value="2d"> 2D</label></div>
  <label class="tog"><input type="checkbox" id="nodelabels"> node labels</label>
  <label class="tog"><input type="checkbox" id="edgelabels"> edge relation labels</label>
  <label class="tog"><input type="checkbox" id="physics"> free-float physics
    <span title="off = pinned stress-minimized layout (Kamada-Kawai); on = live force simulation" style="color:#9ca3af">?</span></label>
  <button id="clear">clear filters</button>
  <div id="hint">click legend rows to light a group's nodes, their neighbors, and the edges it asserts ·
    edges wear the color of the file asserting them when coloring by file ·
    <span id="nav"></span> · click a node for details</div>
</div>
<div id="detail"><button id="close">×</button><div id="detail-body"></div></div>
<div id="graph"></div>
<script>__LIB__</script>
<script>
__APP__</script>
</body>
</html>
"""
