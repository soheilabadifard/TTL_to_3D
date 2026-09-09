"""Parse one or more RDF files into a merged graph that remembers which file said what."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from rdflib import Graph
from rdflib.util import guess_format


class LoadError(ValueError):
    """An input file could not be parsed; the message names the file."""


@dataclass
class Dataset:
    files: list[Path]
    graphs: dict[str, Graph]      # file key -> that file's own triples, in input order
    merged: Graph                 # union of all files
    prefixes: dict[str, str]      # namespace IRI -> prefix, first binding wins

    @property
    def stems(self) -> list[str]:
        return list(self.graphs)


def _unique_key(stem: str, taken: dict) -> str:
    key, i = stem, 2
    while key in taken:
        key = f"{stem}~{i}"
        i += 1
    return key


def _parse(f: Path, fmt: str | None = None) -> Graph:
    """Parse one file. Without an explicit format the extension decides; if that
    parser rejects the file, try Turtle once (Turtle saved as .owl is common)."""
    g = Graph()
    guessed = fmt or guess_format(str(f)) or "turtle"
    try:
        g.parse(f, format=guessed)
    except Exception as e:  # every rdflib parser plugin raises its own class
        if fmt is None and guessed != "turtle":
            try:
                return _parse(f, "turtle")
            except LoadError:
                pass
        # collapse whitespace: rdflib's BadSyntax (and others) embed literal
        # newlines, and the message must stay on one stderr line
        detail = " ".join(str(e).split())
        raise LoadError(f"{f}: cannot parse as {guessed}: {detail}") from e
    return g


def load_files(paths: Iterable[str | Path], fmt: str | None = None) -> Dataset:
    files = [Path(p) for p in paths]
    graphs: dict[str, Graph] = {}
    merged = Graph()
    prefixes: dict[str, str] = {}
    for f in files:
        if not f.is_file():
            raise FileNotFoundError(f)
        g = _parse(f, fmt)
        graphs[_unique_key(f.stem, graphs)] = g
        for triple in g:
            merged.add(triple)
        for prefix, ns in g.namespaces():
            prefixes.setdefault(str(ns), prefix)
    return Dataset(files, graphs, merged, prefixes)
