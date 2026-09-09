"""Command line entry point: ttl3d FILE [FILE ...] [-o OUT] [--color-by KEY] ..."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from . import __version__, graph, layout, load, render


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ttl3d",
        description="Render Turtle / RDF files as one self-contained 3D HTML viewer.")
    p.add_argument("files", nargs="+", help="RDF files; the format is guessed from the extension")
    p.add_argument("-o", "--out",
                   help="output HTML path (default: <first file stem>-3d.html in the current directory)")
    p.add_argument("--color-by", choices=graph.COLOR_KEYS, default="file",
                   help="what the node colors and legend mean (default: file)")
    p.add_argument("--layout", choices=layout.LAYOUT_MODES, default="auto",
                   help=f"stress = pinned Kamada-Kawai (auto up to {layout.STRESS_MAX_NODES} nodes); "
                        "force = live simulation")
    p.add_argument("--labels", choices=layout.LABEL_MODES, default="auto",
                   help=f"permanent labels (auto: nodes up to {layout.LABEL_MAX_NODES}, "
                        f"edges up to {layout.LABEL_MAX_LINKS}); hover = tooltips only")
    p.add_argument("--title", help="page title (default: first file stem)")
    p.add_argument("--version", action="version", version=f"ttl3d {__version__}")
    return p


def _fail(problem) -> int:
    """Print one line to stderr and return the exit code; `problem` is an exception or a string."""
    print(f"ttl3d: error: {problem}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    first = Path(args.files[0]).stem
    out = Path(args.out) if args.out else Path.cwd() / f"{first}-3d.html"
    if out.resolve() in {Path(f).resolve() for f in args.files}:
        return _fail(f"output {out} is also an input file; pick another -o path")
    try:
        ds = load.load_files(args.files)
    except (OSError, load.LoadError) as e:
        return _fail(e)
    data = graph.build(ds, color_by=args.color_by)
    mode = layout.choose_layout(len(data["nodes"]), args.layout)
    if mode == "stress":
        notice = layout.stress_notice(len(data["nodes"]))
        if notice:
            print(notice, file=sys.stderr)
        pos = layout.stress_positions([n["id"] for n in data["nodes"]], data["links"])
        for n in data["nodes"]:
            n["x"], n["y"], n["z"] = pos[n["id"]]
    labels = layout.choose_labels(len(data["nodes"]), len(data["links"]), args.labels)
    html = render.render_html(data, title=args.title or first,
                              pinned=(mode == "stress"), labels=labels)
    try:
        render.write_html(html, out)
    except OSError as e:
        return _fail(e)
    shown = "+".join(k for k, v in labels.items() if v) or "hover only"
    print(f'{len(data["nodes"])} nodes, {len(data["links"])} links -> {out} '
          f'(layout: {mode}, labels: {shown})')
    return 0
