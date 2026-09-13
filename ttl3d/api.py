"""The Python entry point: the same pipeline as the command line, on paths and in-memory graphs.

    import ttl3d
    html = ttl3d.to_html(["a.ttl", ("live", some_rdflib_graph)], view="2d")
    ttl3d.write("a.ttl", "a.html")

Options mirror the command line. Errors are raised, never printed.

    sources --> load.load --> Dataset --> [slice.select] --> graph.build --> data --> layout --> html
    (paths, Graphs, Datasets,                                                         (stress: positions +
     (name, item), {name: item})                                                      notice, force: nothing)
                                     build_page <-- cli.main -- notice -> stderr, summary line, exit code
                                         |
                                         +-- to_html(...) -> str     +-- write(..., out) -> Path
                                         `-- show(...) -> Page  (an iframe with the page in srcdoc)
"""
from __future__ import annotations

import html as _html
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdflib.term import URIRef

from . import graph, load
from . import layout as _layout
from . import render as _render
from . import slice as _slice
from .load import Sources


@dataclass
class Built:
    """A page plus what the command line prints about it."""
    html: str
    n_nodes: int
    n_links: int
    layout_mode: str
    labels: dict


def check_hops(hops: object) -> None:
    """The one place the hop count is validated: a non-negative int, not a bool. The CLI calls it
    before it reads standard input; build_page calls it before it reads any file."""
    if isinstance(hops, bool) or not isinstance(hops, int) or hops < 0:
        raise ValueError(f"hops must be a non-negative integer, got {hops!r}")


def _terms(terms: Iterable[str | URIRef], ds) -> set:
    """URIRefs as they are (URIRef is a str subclass); plain strings resolve like the CLI's."""
    terms = list(terms)
    return {t for t in terms if isinstance(t, URIRef)} | graph.resolve_terms(
        [t for t in terms if not isinstance(t, URIRef)], ds)


def build_page(sources: Sources, *, title: str | None = None, color_by: str = "file", layout: str = "auto",
               labels: str = "auto", view: str = "3d", lang: str | None = "en", type_links: bool = False,
               attribute_preds: Iterable[str | URIRef] = (), fmt: str | None = None,
               focus: Iterable[str | URIRef] | None = None, hops: int = 1, schema: bool = False,
               notice: Callable[[str], None] | None = None) -> Built:
    """Run every stage once. `notice` receives the stress-layout announcement, if any (the CLI
    prints it to stderr; the API stays silent). Option values are checked before any work.
    `focus`, `hops` and `schema` cut the data down before the model is built (see ttl3d.slice);
    `hops` is checked before any file is read, a focus that is not a node in the data raises
    after loading."""
    if view not in _render.VIEWS:
        raise ValueError(f"view must be one of {_render.VIEWS}, got {view!r}")
    if layout not in _layout.LAYOUT_MODES:
        raise ValueError(f"layout must be one of {_layout.LAYOUT_MODES}, got {layout!r}")
    if labels not in _layout.LABEL_MODES:
        raise ValueError(f"labels must be one of {_layout.LABEL_MODES}, got {labels!r}")
    if color_by not in graph.COLOR_KEYS:
        raise ValueError(f"color_by must be one of {graph.COLOR_KEYS}, got {color_by!r}")
    check_hops(hops)
    ds = load.load(sources, fmt)
    if not ds.sources:
        raise ValueError("at least one source is needed")
    extra = _terms(attribute_preds, ds)
    # focus terms keep their order for the notice; each resolves like an attribute predicate
    seeds = [t if isinstance(t, URIRef) else graph.resolve_terms([t], ds).pop() for t in (focus or ())]
    cut = None
    if seeds or schema:
        cut = _slice.select(ds, focus=seeds, hops=hops, schema=schema, type_links=type_links,
                            attribute_preds=extra)
        ds = cut.dataset
    data = graph.build(ds, color_by=color_by, lang=lang, type_links=type_links, attribute_preds=extra)
    if cut is not None and notice:
        notice(_slice.describe(len(data["nodes"]), cut.total, seeds, hops, schema, ds.prefixes))
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
    html = _render.render_html(data, title=ds.sources[0] if title is None else title,
                               pinned=(mode == "stress"), labels=flags, view=view)
    return Built(html, len(data["nodes"]), len(data["links"]), mode, flags)


def to_html(sources: Sources, *, title: str | None = None, color_by: str = "file", layout: str = "auto",
            labels: str = "auto", view: str = "3d", lang: str | None = "en", type_links: bool = False,
            attribute_preds: Iterable[str | URIRef] = (), fmt: str | None = None,
            focus: Iterable[str | URIRef] | None = None, hops: int = 1, schema: bool = False) -> str:
    """The page as HTML text. `sources`: a path, an rdflib.Graph or rdflib.Dataset, a (name, item)
    pair, or a list of those; a path is named by its stem, a Graph by its pair name or "graph", a
    Dataset by its pair name or "dataset". A quad file or a Dataset adds one source per named graph.
    `title=None` means the first source's name; an empty string is an empty title (unlike
    `--title ""` on the command line, which the CLI maps to `None`).
    `attribute_preds` takes the command line's strings ("prefix:local", an IRI, "<urn:...>")
    or rdflib terms. `focus`, `hops` and `schema` slice the data first (a neighbourhood, the
    schema, or the neighbourhood inside the schema). Raises LoadError / FileNotFoundError /
    ValueError / TypeError."""
    return build_page(sources, title=title, color_by=color_by, layout=layout, labels=labels, view=view,
                      lang=lang, type_links=type_links, attribute_preds=attribute_preds, fmt=fmt,
                      focus=focus, hops=hops, schema=schema).html


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
        # quote=True escapes " as well as < > &, so no page content can end the attribute;
        # sandbox without allow-same-origin: the page runs its JavaScript and WebGL and
        # cannot reach the notebook's origin, which is all it needs
        return (f'<iframe srcdoc="{_html.escape(self.html, quote=True)}" sandbox="allow-scripts" '
                f'style="width:100%;height:{int(self.height)}px;border:0" title="ttl3d"></iframe>')

    def write(self, out: str | os.PathLike) -> Path:
        """Write the page (UTF-8, LF newlines, parents created) and return the path."""
        return _render.write_html(self.html, out)

    def __repr__(self) -> str:      # never dump 1.9 MB into a terminal
        return f"Page({len(self.html)} bytes, height={self.height})"


def show(sources: Sources, *, height: int = 600, **options: Any) -> Page:
    """Render for a notebook: the options of `to_html`, plus the iframe height in pixels.
    The last expression of a cell is displayed, so `ttl3d.show(...)` alone shows the page."""
    return Page(to_html(sources, **options), int(height))    # a bad height fails here, not at display time
