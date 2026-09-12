"""Parse one or more RDF files, or in-memory graphs, into a merged graph that
remembers which source said what."""
from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

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


# one source; a tuple is always a (name, item) pair, never two sources
Source = str | os.PathLike | Graph | tuple[str, str | os.PathLike | Graph]
# what load() and the API accept: one source, several, or a mapping of name to source
Sources = Source | Iterable[Source] | Mapping[str, str | os.PathLike | Graph]

_NOT_A_SOURCE = (
    "a source is a path, an rdflib.Graph, a (name, source) pair or a "
    "mapping of names to those, not {}"
)


def _items(sources) -> list:
    """One source or an iterable of sources, as a list. A str, a path, a Graph or a tuple is one
    source: a tuple is always a (name, item) pair, never two sources; several go in a list. A
    mapping names its values: {"planets": g} is the same as [("planets", g)]."""
    if isinstance(sources, Mapping):
        return list(sources.items())
    if isinstance(sources, (str, os.PathLike, Graph, tuple)):
        return [sources]
    try:
        return list(sources)
    except TypeError:
        raise TypeError(_NOT_A_SOURCE.format(type(sources).__name__)) from None


def _named(item) -> tuple:
    if isinstance(item, tuple):
        if len(item) != 2 or not isinstance(item[0], str):
            raise TypeError(f"a named source is a (name, path-or-Graph) pair, got {item!r}")
        return item
    return None, item


def load(sources, fmt: str | None = None) -> Dataset:
    """Parse and merge paths and in-memory graphs, keeping which source said what.

    A path is named by its stem, an rdflib.Graph by its (name, graph) pair or "graph"; a
    duplicate name gets ~2, ~3. A Graph is used as it is, never copied; the merged union is
    a new Graph. `fmt` forces one parser for every path, as --format does."""
    files: list[Path] = []
    graphs: dict[str, Graph] = {}
    merged = Graph()
    prefixes: dict[str, str] = {}
    for item in _items(sources):
        name, obj = _named(item)
        if isinstance(obj, Graph):
            g, key = obj, name or "graph"
        elif isinstance(obj, (str, os.PathLike)):
            f = Path(obj)
            if not f.is_file():
                raise FileNotFoundError(f)
            g, key = _parse(f, fmt), name or f.stem
            files.append(f)
        else:
            raise TypeError(_NOT_A_SOURCE.format(type(obj).__name__))
        graphs[_unique_key(key, graphs)] = g
        for triple in g:
            merged.add(triple)
        for prefix, ns in g.namespaces():
            prefixes.setdefault(str(ns), prefix)
    return Dataset(files, graphs, merged, prefixes)


def load_files(paths: Iterable[str | Path], fmt: str | None = None) -> Dataset:
    """Paths only; the original entry point, kept as an alias of `load`."""
    return load(list(paths), fmt)
