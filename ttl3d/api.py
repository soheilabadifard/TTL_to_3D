"""The Python entry point: the same pipeline as the command line, on paths and in-memory graphs.

    import ttl3d
    html = ttl3d.to_html(["a.ttl", ("live", some_rdflib_graph)], view="2d")
    ttl3d.write("a.ttl", "a.html")

Options mirror the command line. Errors are raised, never printed.

    sources --> load.load --> Dataset --> graph.build --> data --> layout --> render.render_html --> html
    (paths, Graphs,                                              (stress: positions + notice,
     (name, item), {name: item})                                  force: nothing)
                                     build_page <-- cli.main -- notice -> stderr, summary line, exit code
                                         |
                                         +-- to_html(...) -> str     +-- write(..., out) -> Path
                                         `-- show(...) -> Page  (an iframe with the page in srcdoc)
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdflib.term import URIRef

from . import graph, load
from . import layout as _layout
from . import render as _render
from .load import Sources


@dataclass
class Built:
    """A page plus what the command line prints about it."""
    html: str
    n_nodes: int
    n_links: int
    layout_mode: str
    labels: dict


def build_page(sources: Sources, *, title: str | None = None, color_by: str = "file", layout: str = "auto",
               labels: str = "auto", view: str = "3d", lang: str | None = "en", type_links: bool = False,
               attribute_preds: Iterable[str | URIRef] = (), fmt: str | None = None,
               notice: Callable[[str], None] | None = None) -> Built:
    """Run every stage once. `notice` receives the stress-layout announcement, if any (the CLI
    prints it to stderr; the API stays silent). Option values are checked before any work."""
    if view not in _render.VIEWS:
        raise ValueError(f"view must be one of {_render.VIEWS}, got {view!r}")
    if layout not in _layout.LAYOUT_MODES:
        raise ValueError(f"layout must be one of {_layout.LAYOUT_MODES}, got {layout!r}")
    if labels not in _layout.LABEL_MODES:
        raise ValueError(f"labels must be one of {_layout.LABEL_MODES}, got {labels!r}")
    ds = load.load(sources, fmt)
    if not ds.stems:
        raise ValueError("at least one source is needed")
    preds = list(attribute_preds)
    # URIRef is a str subclass: keep terms as they are, resolve the plain strings like the CLI
    extra = {t for t in preds if isinstance(t, URIRef)}
    extra |= graph.resolve_terms([t for t in preds if not isinstance(t, URIRef)], ds)
    data = graph.build(ds, color_by=color_by, lang=lang, type_links=type_links, attribute_preds=extra)
    mode = _layout.choose_layout(len(data["nodes"]), layout)
    if mode == "stress":
        message = _layout.stress_notice(len(data["nodes"]))
        if message and notice:
            notice(message)
        ids = [n["id"] for n in data["nodes"]]
        pos3 = _layout.stress_positions(ids, data["links"], dim=3)
        pos2 = _layout.stress_positions(ids, data["links"], dim=2)
        for n in data["nodes"]:
            n["x"], n["y"], n["z"] = pos3[n["id"]]
            n["x2"], n["y2"] = pos2[n["id"]]
    flags = _layout.choose_labels(len(data["nodes"]), len(data["links"]), labels)
    html = _render.render_html(data, title=ds.stems[0] if title is None else title,
                               pinned=(mode == "stress"), labels=flags, view=view)
    return Built(html, len(data["nodes"]), len(data["links"]), mode, flags)


def to_html(sources: Sources, *, title: str | None = None, color_by: str = "file", layout: str = "auto",
            labels: str = "auto", view: str = "3d", lang: str | None = "en", type_links: bool = False,
            attribute_preds: Iterable[str | URIRef] = (), fmt: str | None = None) -> str:
    """The page as HTML text. `sources`: a path, an rdflib.Graph, a (name, path-or-Graph) pair,
    or a list of those; a path is named by its stem, a Graph by its pair name or "graph".
    `attribute_preds` takes the command line's strings ("prefix:local", an IRI, "<urn:...>")
    or rdflib terms. Raises LoadError / FileNotFoundError / ValueError / TypeError."""
    return build_page(sources, title=title, color_by=color_by, layout=layout, labels=labels, view=view,
                      lang=lang, type_links=type_links, attribute_preds=attribute_preds, fmt=fmt).html


def write(sources: Sources, out: str | os.PathLike, **options: Any) -> Path:
    """Render and write the page (UTF-8, LF newlines, parent directories created); the options
    of `to_html`. Returns the path written."""
    return _render.write_html(to_html(sources, **options), out)


@dataclass
class Page:
    """A rendered page that notebooks display inline: Jupyter, JupyterLab, VS Code and Colab
    call `_repr_html_`, which returns an iframe carrying the whole page in `srcdoc`. Nothing is
    written to disk and no server is needed; each output stores the full page (about 1.9 MB,
    measured) in the notebook file."""
    html: str
    height: int = 600

    def _repr_html_(self) -> str:
        # Escape for the srcdoc attribute: avoid double-escaping entities already in self.html.
        # Replace unsafe characters but not & (which is already part of entities like &quot;).
        escaped = self.html.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        return (f'<iframe srcdoc="{escaped}" sandbox="allow-scripts" '
                f'style="width:100%;height:{int(self.height)}px;border:0" title="ttl3d"></iframe>')

    def write(self, out) -> Path:
        """Write the page (UTF-8, LF newlines, parents created) and return the path."""
        return _render.write_html(self.html, out)

    def __repr__(self) -> str:      # never dump 1.9 MB into a terminal
        return f"Page({len(self.html)} bytes, height={self.height})"


def show(sources: Sources, *, height: int = 600, **options: Any) -> Page:
    """Render for a notebook: the options of `to_html`, plus the iframe height in pixels.
    The last expression of a cell is displayed, so `ttl3d.show(...)` alone shows the page."""
    return Page(to_html(sources, **options), int(height))    # a bad height fails here, not at display time
