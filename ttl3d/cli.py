"""Command line entry point: ttl3d [FILE ...] [--endpoint URL --query TEXT|@FILE ...] [-o OUT] ..."""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

from . import __version__, api, graph, layout, load, render, sparql


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ttl3d",
        description="Render Turtle / RDF files as one self-contained 2D/3D HTML viewer.")
    p.add_argument("files", nargs="*",
                   help="RDF files, or - for standard input; the format is guessed from the extension")
    p.add_argument("-o", "--out",
                   help="output HTML path (default: <first source name>-<view>.html in the current "
                        "directory; stdin for -)")
    p.add_argument("--color-by", choices=graph.COLOR_KEYS, default="file",
                   help="what the node colors and legend mean (default: file; a named graph of a TriG or "
                        "N-Quads file counts as a file)")
    p.add_argument("--layout", choices=layout.LAYOUT_MODES, default="auto",
                   help=f"stress = pinned Kamada-Kawai (auto up to {layout.STRESS_MAX_NODES} nodes); "
                        "force = live simulation")
    p.add_argument("--labels", choices=layout.LABEL_MODES, default="auto",
                   help=f"permanent labels (auto: nodes up to {layout.LABEL_MAX_NODES}, "
                        f"edges up to {layout.LABEL_MAX_LINKS}); hover = tooltips only")
    p.add_argument("--view", choices=render.VIEWS, default="3d",
                   help="starting view; the page can switch between 3d and 2d (default: 3d)")
    p.add_argument("--title", help="page title (default: the first source's name; stdin for -)")
    p.add_argument("--lang", default="en",
                   help="preferred language tag for labels and definitions (default: en); "
                        "untagged literals rank next, other languages become synonyms"
                        "; matched exactly (en does not select en-GB)")
    p.add_argument("--type-links", action="store_true",
                   help="draw rdf:type as an edge from each instance to its class (default: card only)")
    p.add_argument("--attribute-preds", action="append", default=[], metavar="PRED[,PRED...]",
                   help="predicates to show on the card instead of drawing, as prefix:local, full IRIs, "
                        "or <urn:...> in angle brackets (e.g. foaf:homepage,rdfs:seeAlso); repeatable")
    p.add_argument("--focus", action="append", default=[], metavar="IRI[,IRI...]",
                   help="keep only this node's neighbourhood (see --hops), as prefix:local, a full IRI or "
                        "<urn:...>; repeatable")
    p.add_argument("--hops", type=int, metavar="N",
                   help="how many link steps from a focus node to keep "
                        "(default: 1; 0 = the focus nodes only)")
    p.add_argument("--schema", action="store_true",
                   help="keep classes and properties only: the schema, without instances")
    p.add_argument("--endpoint", metavar="URL",
                   help="SPARQL endpoint to run every --query against; credentials come from the environment "
                        "(TTL3D_SPARQL_USER/TTL3D_SPARQL_PASSWORD or TTL3D_SPARQL_TOKEN), never from here")
    p.add_argument("--query", action="append", default=[], metavar="TEXT|@FILE",
                   help="a CONSTRUCT or DESCRIBE query, or @file holding one; its result is a source named "
                        "after the file or the endpoint's host; repeatable")
    p.add_argument("--timeout", type=float, default=60.0, metavar="SECONDS",
                   help="how long to wait for each network step of the endpoint's answer (default: 60)")
    p.add_argument("--max-mb", type=float, default=sparql.MAX_BYTES / 1e6, metavar="MB",
                   help="largest answer to accept, in megabytes (default: 100); the parse needs about 35 "
                        "times an N-Triples answer's size in memory, and more for Turtle")
    p.add_argument("--format", metavar="NAME",
                   help="rdflib parser name for every input (turtle, xml, nt, n3, json-ld, trig, nquads); "
                        "default: guess from the extension, then try turtle")
    p.add_argument("--version", action="version", version=f"ttl3d {__version__}")
    return p


def _fail(problem) -> int:
    """Print one line to stderr and return the exit code; `problem` is an exception or a string."""
    print(f"ttl3d: error: {problem}", file=sys.stderr)
    return 1


def _query_name(text: str, endpoint: str) -> str:
    """A query given as @file is named by the file's stem, inline text by the endpoint's host."""
    return Path(text[1:]).stem if text.startswith("@") else sparql.host(endpoint)


def _query_text(text: str) -> str:
    if not text.startswith("@"):
        return text
    path = Path(text[1:])
    try:
        return path.read_text(encoding="utf-8-sig")   # a leading byte-order mark is dropped, not sent
    except UnicodeDecodeError:
        raise ValueError(f"{path}: the query file is not UTF-8 text") from None


def _secret(name: str) -> str | None:
    """An environment variable with a trailing line break stripped: a secrets file or pasted value
    often ends with one. Spaces are kept; a token or password might genuinely have them."""
    value = os.environ.get(name)
    return value.rstrip("\r\n") if value is not None else None


def main(argv: list[str] | None = None) -> int:
    # stderr already replaces characters it cannot encode; stdout raises instead, and a console
    # that cannot show the output path (Windows with stdout redirected, an ASCII locale) must
    # still get the summary line, not a UnicodeEncodeError traceback
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    if args.query and not args.endpoint:
        return _fail("--query needs --endpoint")
    if args.endpoint and not args.query:
        return _fail("--endpoint needs --query")
    if not args.files and not args.query:
        return _fail("at least one file or --query is needed")
    if args.query:
        max_bytes = int(args.max_mb * 1_000_000) if math.isfinite(args.max_mb) else 0
        if max_bytes < 1:
            return _fail("--max-mb must be a positive number of megabytes")
        user, token = _secret("TTL3D_SPARQL_USER"), _secret("TTL3D_SPARQL_TOKEN")
        if user and token:
            return _fail("set either TTL3D_SPARQL_TOKEN or TTL3D_SPARQL_USER, not both")
    else:                                         # a query-free run never looks at these at all
        max_bytes = sparql.MAX_BYTES
        user = token = None
    if args.files.count("-") > 1:
        return _fail("standard input can be given only once")
    # files first, then queries: the first source names the page and the default output
    names = [("stdin" if f == "-" else Path(f).stem) for f in args.files]
    names += [_query_name(q, args.endpoint) for q in args.query]
    out = Path(args.out) if args.out else Path.cwd() / f"{names[0]}-{args.view}.html"
    inputs = [f for f in args.files if f != "-"] + [q[1:] for q in args.query if q.startswith("@")]
    # by identity, not by spelling: on case-insensitive filesystems Graph.ttl is graph.ttl
    if out.exists() and any(Path(f).exists() and out.samefile(f) for f in inputs):
        return _fail(f"output {out} is also an input file; pick another -o path")
    if args.hops is not None and not args.focus:
        return _fail("--hops needs --focus")
    focus = [t for arg in args.focus for t in arg.split(",") if t]
    if args.focus and not focus:
        return _fail("--focus is empty")
    hops = 1 if args.hops is None else args.hops
    try:
        api.check_hops(hops)
        auth = (user, _secret("TTL3D_SPARQL_PASSWORD") or "") if user else None
        # every Query is built, and so checked, before standard input is read or anything is sent
        queries = [(name, sparql.Query(args.endpoint, _query_text(q), auth=auth, token=token or None,
                                       timeout=args.timeout, max_bytes=max_bytes))
                   for name, q in zip(names[len(args.files):], args.query)]
        # "-" becomes a named in-memory source; the API itself never sees the dash
        sources = [
            ("stdin", load.parse_data(sys.stdin.buffer.read(), args.format, "stdin"))
            if f == "-" else f for f in args.files
        ] + queries
        built = api.build_page(
            sources, title=args.title or None,          # --title "" meant "the first stem" before; keep it
            color_by=args.color_by, layout=args.layout, labels=args.labels,
            view=args.view, lang=args.lang, type_links=args.type_links,
            attribute_preds=[t for arg in args.attribute_preds for t in arg.split(",") if t],
            fmt=args.format,
            focus=focus or None, hops=hops,
            schema=args.schema, notice=lambda message: print(message, file=sys.stderr))
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
