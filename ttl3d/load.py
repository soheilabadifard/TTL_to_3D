"""Parse one or more RDF sources (files, standard input, in-memory rdflib graphs and datasets) into a
merged graph that remembers which source said what. A named graph of a quad format (TriG, N-Quads,
TriX, JSON-LD with named @graph blocks) is a source of its own, keyed by its prefixed IRI.

    path / bytes --rdflib Dataset.parse--> rdflib Dataset --_split--> default graph (+ blank-node graphs)
    rdflib.Dataset ---------------------------------------_split--> named graphs {IRI: Graph}
    rdflib.Graph -------------------------------------------------> used as is, no named graphs
    sparql.Query --sparql.fetch--> bytes --parse, base = endpoint--> one key (named graphs folded in)
         |                                    one (name, default, named) part per source, in input order
         v
    prefixes: namespace -> prefix from every source, first binding wins   (collected before any key)
         |
         v
    keys, source by source:   default graph -> the source name        (~2 on a clash; no key when it
                                                                        is empty and named graphs exist)
                              named graphs, sorted by (curie, IRI) -> curie = prefix:local, or the IRI
                                  same IRI seen before   -> joins that key   (by_iri: IRI -> key)
                                  key taken by another name -> ~2, ~3
         |
         v
    merged = union of every key. A node belongs to its first key in this order (graph.build), so keys
    sit where their graph first appeared, even when a later file adds to it.
"""
from __future__ import annotations

import os
import time
import warnings
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from rdflib import Dataset as RdfDataset
from rdflib import Graph, URIRef
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID
from rdflib.util import guess_format

from . import sparql


class LoadError(ValueError):
    """An input could not be parsed; the message names the file (or `stdin`)."""


@dataclass
class Dataset:
    files: list[Path]             # real paths only, in order; stdin and in-memory sources add none
    graphs: dict[str, Graph]      # legend key -> that source's triples: a source's default graph under
                                  # its name, each named graph under its prefixed IRI
    merged: Graph                 # union of every key
    prefixes: dict[str, str]      # namespace IRI -> prefix, first binding wins
    sources: list[str]            # one name per input, in input order (not a key: a duplicate name is
                                  # suffixed in graphs); the title uses the first
    named: dict[str, URIRef]      # graph key -> graph IRI, for the keys that came from named graphs

    @property
    def stems(self) -> list[str]:
        return list(self.graphs)


def _unique_key(stem: str, taken: dict) -> str:
    key, i = stem, 2
    while key in taken:
        key = f"{stem}~{i}"
        i += 1
    return key


def split_iri(iri, prefixes: Mapping[str, str] | None = None) -> tuple[str, str]:
    """(namespace, local name) of an IRI. Cut at the last '#' or '/' when that namespace is bound,
    or when nothing else matches; otherwise at the longest bound namespace the IRI starts with and
    extends whose remainder holds no '/' or '#', so `urn:graphs:planets` with `ex: <urn:graphs:>`
    splits as ('urn:graphs:', 'planets') while `http://example.org/data/x` under a bound
    `<http://example.org/>` keeps the cut ('http://example.org/data/', 'x'). Legend keys, node
    namespaces and local names all go through here, so they always agree."""
    s = str(iri)
    ns = s[:max(s.rfind("#"), s.rfind("/")) + 1]
    if prefixes and ns not in prefixes:
        bound = [b for b in prefixes
                 if len(b) < len(s) and s.startswith(b) and "/" not in s[len(b):] and "#" not in s[len(b):]]
        if bound:
            ns = max(bound, key=len)
    return ns, s[len(ns):]


def namespace_of(u, prefixes: Mapping[str, str] | None = None) -> str:
    return split_iri(u, prefixes)[0]


def local(u, prefixes: Mapping[str, str] | None = None) -> str:
    """The local name; the whole IRI when nothing follows the namespace (`http://e/a/`, `urn:x`)."""
    return split_iri(u, prefixes)[1] or str(u)


def _parsed(name: str, fmt: str, parse) -> RdfDataset:
    """Run `parse(dataset, fmt)` on a fresh rdflib Dataset, turning any parser failure into a
    one-line LoadError that names the source."""
    rds = RdfDataset()
    try:
        with warnings.catch_warnings():
            # rdflib 7.6's Dataset.parse reads its own deprecated default_context and warns
            # (catch_warnings edits the process-wide filter for the parse's duration; not
            # thread-safe, as Python documents)
            warnings.simplefilter("ignore", DeprecationWarning)
            parse(rds, fmt)
    except Exception as e:  # every rdflib parser plugin raises its own class
        # collapse whitespace: rdflib's BadSyntax (and others) embed literal
        # newlines, and the message must stay on one stderr line
        detail = " ".join(str(e).split())
        raise LoadError(f"{name}: cannot parse as {fmt}: {detail}") from e
    return rds


def _parse(f: Path, fmt: str | None = None) -> RdfDataset:
    """Parse one file. Without an explicit format the extension decides; if that
    parser rejects the file, try Turtle once (Turtle saved as .owl is common)."""
    guessed = fmt or guess_format(str(f)) or "turtle"
    try:
        return _parsed(str(f), guessed, lambda rds, fm: rds.parse(f, format=fm))
    except LoadError:
        if fmt is None and guessed != "turtle":
            try:
                return _parse(f, "turtle")
            except LoadError:
                pass
        raise


def parse_data(data: bytes, fmt: str | None = None, name: str = "data",
               base: str | None = None) -> RdfDataset:
    """Parse in-memory bytes (standard input, a SPARQL answer) as `fmt`, Turtle by default: there is
    no extension to guess from and no retry. A failure is a LoadError naming `name`. Relative IRIs
    resolve against `base` (a SPARQL answer passes its endpoint), else against the working
    directory, as rdflib does for data without a base; declare @base in the data to be explicit."""
    return _parsed(name, fmt or "turtle", lambda rds, fm: rds.parse(data=data, format=fm, publicID=base))


def _contexts(rds: RdfDataset):
    """Every graph of an rdflib Dataset. `graphs()` is missing in rdflib 7.0 and 7.1 and `contexts()`
    warns from 7.6, so use whichever the installed version has without a deprecation warning."""
    graphs = getattr(rds, "graphs", None)
    return graphs() if graphs else rds.contexts()


def _split(rds: RdfDataset) -> tuple[Graph, dict[URIRef, Graph]]:
    """A parsed dataset as (default graph, {graph IRI: graph}). The default graph is the parsed
    store's own context, not a copy, so a plain Turtle file costs one copy (into `merged`) as
    before; named graphs are fresh copies because same-IRI merges write into them. Graphs named
    by a blank node have no stable name and are folded into a fresh default graph."""
    default: Graph | None = None
    folded: list[Graph] = []
    named: dict[URIRef, Graph] = {}
    for ctx in _contexts(rds):
        ident = ctx.identifier
        if ident == DATASET_DEFAULT_GRAPH_ID:
            default = ctx
        elif isinstance(ident, URIRef):
            target = named.setdefault(ident, Graph())
            for triple in ctx:
                target.add(triple)
        else:
            folded.append(ctx)
    if default is None:
        default = Graph()
    if folded:
        together = Graph()
        for g in (default, *folded):
            for triple in g:
                together.add(triple)
        default = together
    return default, named


def curie(iri: URIRef, prefixes: Mapping[str, str]) -> str:
    """The legend key of a graph IRI, and the short form the slice notice uses: `prefix:local`
    (`:local` for the empty default prefix) through split_iri; the IRI itself when its namespace is
    unbound or nothing follows the namespace."""
    ns, name = split_iri(iri, prefixes)
    return f"{prefixes[ns]}:{name}" if name and ns in prefixes else str(iri)


# one source; a tuple is always a (name, item) pair, never two sources
Source = str | os.PathLike | Graph | sparql.Query | tuple[str, str | os.PathLike | Graph | sparql.Query]

_NOT_A_SOURCE = (
    "a source is a path, an rdflib.Graph, a sparql.Query, a (name, source) pair or a "
    "mapping of names to those, not {}"
)


def _items(sources) -> list:
    """One source or an iterable of sources, as a list. A str, a path, a Graph, a Query or a tuple is one
    source: a tuple is always a (name, item) pair, never two sources; several go in a list. A
    mapping names its values: {"planets": g} is the same as [("planets", g)]."""
    if isinstance(sources, Mapping):
        return list(sources.items())
    if isinstance(sources, (str, os.PathLike, Graph, tuple, sparql.Query)):
        return [sources]
    try:
        return list(sources)
    except TypeError:
        raise TypeError(_NOT_A_SOURCE.format(type(sources).__name__)) from None


def _named(item) -> tuple:
    if isinstance(item, tuple):
        if len(item) != 2 or not isinstance(item[0], str):
            raise TypeError(f"a named source is a (name, path, Graph or Query) pair, got {item!r}")
        return item
    return None, item


# what load() and the API accept: one source, several, or a mapping of name to source
Sources = Source | Iterable[Source] | Mapping[str, str | os.PathLike | Graph | sparql.Query]


def load(sources: Sources, fmt: str | None = None, *,
         notice: Callable[[str], None] | None = None) -> Dataset:
    """Parse and merge paths and in-memory graphs, keeping which source said what.

    A path is named by its stem, an rdflib.Graph by its (name, graph) pair or "graph", an
    rdflib.Dataset by its pair or "dataset"; a duplicate name gets ~2, ~3. A Graph is used as it
    is, never copied; a quad source's default graph is used as is too, its named graphs are
    copied. A quad source (a TriG, N-Quads, TriX or JSON-LD file, or an rdflib.Dataset)
    contributes its default graph under the source name and every named graph under its prefixed
    IRI (`ex:planets`); the same graph IRI in several sources is one key, sitting where the graph
    first appeared. A sparql.Query is fetched (one POST) and its answer parsed by the response's
    media type against the endpoint as base, under the endpoint's host unless paired; its named
    graphs fold into that one key and its PREFIX lines bind before the answer's own; `notice` gets
    one "fetched N triples from HOST in S s" line per query. `fmt` forces one parser for every
    path, as --format does."""
    files: list[Path] = []
    names: list[str] = []
    prefixes: dict[str, str] = {}
    parts: list[tuple[str, Graph, dict[URIRef, Graph]]] = []    # (name, default graph, named graphs)
    for item in _items(sources):
        name, obj = _named(item)
        if isinstance(obj, sparql.Query):                        # checked when it was built
            key, started = name or sparql.host(obj.endpoint), time.perf_counter()
            body, media = sparql.fetch(obj)
            rds = parse_data(body, media or "text/turtle", key, base=obj.endpoint)
            if notice:
                notice(f"fetched {len(rds)} triples from {sparql.host(obj.endpoint)} "
                       f"in {time.perf_counter() - started:.1f} s{sparql.sent_with(obj)}")
            for prefix, ns in sparql.prefixes_in(obj.query).items():   # the author's names first
                prefixes.setdefault(ns, prefix)
            bound = rds
            default, named_graphs = _split(rds)
            for g in named_graphs.values():                      # one legend row per query (spec D4)
                for triple in g:
                    default.add(triple)
            named_graphs = {}
        elif isinstance(obj, RdfDataset):                          # before Graph: a Dataset is a Graph
            key, bound = name or "dataset", obj
            default, named_graphs = _split(obj)
        elif isinstance(obj, Graph):
            key, bound = name or "graph", obj
            default, named_graphs = obj, {}
        elif isinstance(obj, (str, os.PathLike)):
            f = Path(obj)
            if not f.is_file():
                raise FileNotFoundError(f)
            rds = _parse(f, fmt)
            key, bound = name or f.stem, rds
            default, named_graphs = _split(rds)
            files.append(f)
        else:
            raise TypeError(_NOT_A_SOURCE.format(type(obj).__name__))
        names.append(key)
        parts.append((key, default, named_graphs))
        for prefix, ns in bound.namespaces():
            prefixes.setdefault(str(ns), prefix)
    # keys are assigned only now, so a prefix bound by a later source shortens every graph name
    graphs: dict[str, Graph] = {}
    named: dict[str, URIRef] = {}       # key -> graph IRI (Dataset.named)
    by_iri: dict[URIRef, str] = {}      # graph IRI -> key: the inverse, so identity follows the IRI
    for key, default, named_graphs in parts:
        if len(default) or not named_graphs:
            graphs[_unique_key(key, graphs)] = default
        for iri in sorted(named_graphs, key=lambda i: (curie(i, prefixes), str(i))):
            if iri in by_iri:                                    # the same graph, asserted by another source
                for triple in named_graphs[iri]:
                    graphs[by_iri[iri]].add(triple)
                continue
            gkey = _unique_key(curie(iri, prefixes), graphs)
            graphs[gkey] = named_graphs[iri]
            named[gkey] = iri
            by_iri[iri] = gkey
    merged = Graph()
    for g in graphs.values():
        for triple in g:
            merged.add(triple)
    return Dataset(files, graphs, merged, prefixes, names, named)


def load_files(paths: Iterable[str | Path], fmt: str | None = None) -> Dataset:
    """Paths only; the original entry point, kept as an alias of `load`. `list()` first so a
    tuple of paths stays several sources, not one `(name, path)` pair."""
    return load(list(paths), fmt)
