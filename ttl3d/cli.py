"""Command line entry point: ttl3d FILE [FILE ...] [-o OUT] [--view 3d|2d] [--color-by KEY] ..."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, api, graph, layout, render


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ttl3d",
        description="Render Turtle / RDF files as one self-contained 2D/3D HTML viewer.")
    p.add_argument("files", nargs="+", help="RDF files; the format is guessed from the extension")
    p.add_argument("-o", "--out",
                   help="output HTML path (default: <first file stem>-<view>.html in the current directory)")
    p.add_argument("--color-by", choices=graph.COLOR_KEYS, default="file",
                   help="what the node colors and legend mean (default: file)")
    p.add_argument("--layout", choices=layout.LAYOUT_MODES, default="auto",
                   help=f"stress = pinned Kamada-Kawai (auto up to {layout.STRESS_MAX_NODES} nodes); "
                        "force = live simulation")
    p.add_argument("--labels", choices=layout.LABEL_MODES, default="auto",
                   help=f"permanent labels (auto: nodes up to {layout.LABEL_MAX_NODES}, "
                        f"edges up to {layout.LABEL_MAX_LINKS}); hover = tooltips only")
    p.add_argument("--view", choices=render.VIEWS, default="3d",
                   help="starting view; the page can switch between 3d and 2d (default: 3d)")
    p.add_argument("--title", help="page title (default: first file stem)")
    p.add_argument("--lang", default="en",
                   help="preferred language tag for labels and definitions (default: en); "
                        "untagged literals rank next, other languages become synonyms"
                        "; matched exactly (en does not select en-GB)")
    p.add_argument("--type-links", action="store_true",
                   help="draw rdf:type as an edge from each instance to its class (default: card only)")
    p.add_argument("--attribute-preds", action="append", default=[], metavar="PRED[,PRED...]",
                   help="predicates to show on the card instead of drawing, as prefix:local, full IRIs, "
                        "or <urn:...> in angle brackets (e.g. foaf:homepage,rdfs:seeAlso); repeatable")
    p.add_argument("--format", metavar="NAME",
                   help="rdflib parser name for every input (turtle, xml, nt, n3, json-ld, trig, nquads); "
                        "default: guess from the extension, then try turtle")
    p.add_argument("--version", action="version", version=f"ttl3d {__version__}")
    return p


def _fail(problem) -> int:
    """Print one line to stderr and return the exit code; `problem` is an exception or a string."""
    print(f"ttl3d: error: {problem}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    # stderr already replaces characters it cannot encode; stdout raises instead, and a console
    # that cannot show the output path (Windows with stdout redirected, an ASCII locale) must
    # still get the summary line, not a UnicodeEncodeError traceback
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    first = Path(args.files[0]).stem
    out = Path(args.out) if args.out else Path.cwd() / f"{first}-{args.view}.html"
    # by identity, not by spelling: on case-insensitive filesystems Graph.ttl is graph.ttl
    if out.exists() and any(Path(f).exists() and out.samefile(f) for f in args.files):
        return _fail(f"output {out} is also an input file; pick another -o path")
    try:
        built = api.build_page(
            args.files, title=args.title or None,       # --title "" meant "the first stem" before; keep it
            color_by=args.color_by, layout=args.layout, labels=args.labels,
            view=args.view, lang=args.lang, type_links=args.type_links,
            attribute_preds=[t for arg in args.attribute_preds for t in arg.split(",") if t],
            fmt=args.format, notice=lambda message: print(message, file=sys.stderr))
    except (OSError, ValueError) as e:      # LoadError is a ValueError; an unknown prefix too
        return _fail(e)
    try:
        render.write_html(built.html, out)
    except OSError as e:
        return _fail(e)
    shown = "+".join(k for k, v in built.labels.items() if v) or "hover only"
    print(f'{built.n_nodes} nodes, {built.n_links} links -> {out} '
          f'(view: {args.view}, layout: {built.layout_mode}, labels: {shown})')
    return 0
