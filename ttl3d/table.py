"""Tables as sources: a CSV or TSV file, standard input, or a DataFrame becomes one RDF graph.

    path / stdin bytes / DataFrame.to_csv --read--> Table (header, rows with line numbers)
        --classify (roles by header name, --columns)--> edge table / node table, rows checked
        --to_graphs (all tables together, after every RDF source is parsed)--> one Graph per table

A node row says things about its id; an edge row asserts `source relation target` and, when it has
property cells, a reified rdf:Statement carrying them. Ids written as IRIs (`<...>`, `://`) or as
CURIEs whose prefix an RDF source of the run binds are used as such (ttl3d.iri, the rule --focus uses
too); every other id is minted under `base` (bound to the prefix `csv`), percent-encoded so that
distinct ids stay distinct.
"""
from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from . import iri

TABLE_FORMATS = ("csv", "tsv")
SUFFIXES = {".csv": "csv", ".tsv": "tsv"}
DEFAULT_BASE = "urn:x-ttl3d:"
PREFIX = "csv"
RELATED = "related"            # the predicate of an edge row without a relation

# role -> header names in priority order; ":kind" stands for a Neo4j import header of that kind
NAMES = {
    "id": ("id", "node", "key", ":id", "_id"),
    "label": ("label", "name", "title"),
    "type": ("type", "types", "class", "category", "kind", ":label", "_labels", "labels"),
    "description": ("description", "definition", "comment"),
    "source": ("source", "src", "from", "start", "subject", "head", ":start_id", "_start"),
    "target": ("target", "dst", "to", "end", "object", "tail", ":end_id", "_end"),
    "relation": ("relation", "predicate", "rel", ":type", "_type", "label", "type"),
}
ROLES = tuple(NAMES)
EDGE_ROLES = ("source", "target", "relation")
NODE_ROLES = ("id", "label", "type", "description")

_NEO4J_KINDS = {"id", "start_id", "end_id", "type", "label", "ignore"}
_NEO4J_TYPES = {"int", "long", "float", "double", "boolean", "byte", "short", "char", "string", "point",
                "date", "localtime", "time", "localdatetime", "datetime", "duration"}
_NEO4J = re.compile(r"(?P<name>.*):(?P<kind>[A-Za-z_]+)(?:\((?P<group>[^()]*)\))?(?P<array>\[\])?")
_UNSAFE = re.compile(r'[\x00-\x20<>"{}|\\^`%/#?]')         # what a minted local name must not hold as is
_STATEMENT = frozenset({RDF.type, RDF.subject, RDF.predicate, RDF.object})   # a statement's own predicates
_LABELS = frozenset({RDFS.label, SKOS.prefLabel})        # a property column with one of these labels the node


class TableError(ValueError):
    """A table could not be read; load re-raises it as a LoadError."""


@dataclass(frozen=True)
class Column:
    header: str             # as written, trimmed
    name: str               # the property name: the header, or a Neo4j header's part before the colon
    key: str | None         # what NAMES are matched against; None for an ignored column
    group: str | None = None
    array: bool = False


def column(header: str, neo4j: bool = False) -> Column:
    """One header cell, with Neo4j's `name:KIND(group)[]` read when KIND is a Neo4j kind, in upper case as
    Neo4j writes it (so `rdfs:label` and `dc:type` stay CURIEs), or, in a Neo4j table only (`neo4j`),
    a data type in any case; otherwise the colon belongs to the name (`foaf:name`, `dc:date`)."""
    m = _NEO4J.fullmatch(header)
    if m:
        kind = m["kind"].lower()
        if (kind in _NEO4J_KINDS and m["kind"].isupper() and not m["array"]
                and (m["group"] is None or "id" in kind)):
            if kind == "ignore":
                return Column(header, m["name"], None)
            return Column(header, m["name"], f":{kind}", m["group"] or None)
        if neo4j and kind in _NEO4J_TYPES and m["group"] is None:
            name = m["name"].strip()
            return Column(header, name, name.lower() or None, None, bool(m["array"]))
    return Column(header, header, header.lower() or None)


@dataclass
class Table:
    name: str                                   # for messages: the path, "stdin" or the source's name
    columns: list[Column]
    rows: list[tuple[int, list[str]]]           # (line where the row starts, trimmed cells)
    roles: dict[str, int] = field(default_factory=dict)    # role -> column index, set by classify

    @property
    def is_edges(self) -> bool:
        return "source" in self.roles and "target" in self.roles


def table_format(path: Path, fmt: str | None) -> str | None:
    """"csv" or "tsv" when the path is read as a table: `fmt` decides when given, else the suffix."""
    if fmt is not None:
        return fmt if fmt in TABLE_FORMATS else None
    return SUFFIXES.get(path.suffix.lower())


def is_frame(obj) -> bool:
    """A DataFrame, recognised without importing pandas: it can write CSV and has columns."""
    return hasattr(obj, "to_csv") and hasattr(obj, "columns")


def _delimiter(line: str) -> str:
    """The most frequent of comma, tab and semicolon outside double quotes; ties in that order; a comma
    when none occurs (a one-column table)."""
    counts = dict.fromkeys(",\t;", 0)
    quoted = False
    for ch in line:
        if ch == '"':
            quoted = not quoted
        elif not quoted and ch in counts:
            counts[ch] += 1
    best = max(counts.values())
    return next(d for d in counts if counts[d] == best) if best else ","


def _is_neo4j(cells: list[str]) -> bool:
    """A Neo4j import file: a node file has an `:ID` column, a relationship file `:START_ID` and `:END_ID`
    (upper case, as in `column`)."""
    for cell in cells:
        m = _NEO4J.fullmatch(cell)
        if m and m["kind"].isupper() and m["kind"].lower() in ("id", "start_id", "end_id"):
            return True
    return False


def parse(text: str, name: str, delimiter: str | None = None) -> Table:
    """A table from text; `delimiter` None guesses it from the header line."""
    if delimiter is None:
        # lazily: splitlines() would copy the whole file just to find the header
        first = next((line.rstrip("\r\n") for line in io.StringIO(text, newline="") if line.strip()), "")
        delimiter = _delimiter(first)
    # strict: an unclosed quote is an error, not a cell that swallows the rest of the file
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, skipinitialspace=True,
                        strict=True)
    columns: list[Column] | None = None
    rows: list[tuple[int, list[str]]] = []
    end = 0
    try:
        for row in reader:
            start, end = end + 1, reader.line_num
            cells = [c.strip() for c in row]
            if not any(cells):                  # a blank line, or a row of empty cells (",,,")
                continue
            if columns is None:
                neo4j = _is_neo4j(cells)
                columns = [column(c, neo4j) for c in cells]
                continue
            if len(cells) > len(columns):
                if any(cells[len(columns):]):
                    raise TableError(f"{name}: line {start}: {len(cells)} cells, but the header has "
                                     f"{len(columns)}")
                cells = cells[:len(columns)]
            rows.append((start, cells + [""] * (len(columns) - len(cells))))
    except csv.Error as e:
        raise TableError(f"{name}: line {end + 1}: {e}") from None
    return Table(name, columns or [], rows)


def _text(data: bytes, name: str) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise TableError(f"{name}: not UTF-8 text; save the table as UTF-8") from None


def read_path(path: Path, fmt: str) -> Table:
    return parse(_text(path.read_bytes(), str(path)), str(path), "\t" if fmt == "tsv" else None)


def read_bytes(data: bytes, fmt: str, name: str = "stdin") -> Table:
    return parse(_text(data, name), name, "\t" if fmt == "tsv" else None)


def read_frame(frame, name: str) -> Table:
    """A DataFrame through to_csv: a named index (set_index("id")) is written as columns, the unnamed
    default index is not."""
    index = any(n is not None for n in getattr(getattr(frame, "index", None), "names", ()))
    text = frame.to_csv(index=index)
    if not isinstance(text, str):
        raise TypeError(f"{name}: to_csv gave {type(text).__name__}, not text")
    return parse(text, name, ",")


def check_columns(columns: Mapping[str, str] | None) -> dict[str, str]:
    """`columns` as {role: header in lower case}; ValueError for an unknown role or an empty header."""
    if columns is None:
        return {}
    if not isinstance(columns, Mapping):
        raise TypeError(f"columns must be a mapping of role to header, got {type(columns).__name__}")
    out = {}
    for role, header in columns.items():
        if role not in ROLES:
            raise ValueError(f"unknown column role {role!r}; roles are {', '.join(ROLES)}")
        if not isinstance(header, str) or not header.strip():
            raise ValueError(f"the column for {role} must be a non-empty header, got {header!r}")
        out[role] = header.strip().lower()
    return out


def check_base(base: str | None) -> str:
    """The namespace minted ids go under: an absolute IRI ending in /, # or :."""
    if base is None:
        return DEFAULT_BASE
    scheme = re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", base) if isinstance(base, str) else None
    if not scheme or iri.NOT_IN_IRI.search(base) or not base.endswith(("/", "#", ":")):
        raise ValueError(f"base must be an absolute IRI ending in /, # or :, got {base!r}")
    return base


def _find(columns: list[Column], role: str, mapped: Mapping[str, str], claimed: set[int]) -> int | None:
    if role in mapped:
        return next((i for i, c in enumerate(columns) if c.header.lower() == mapped[role]), None)
    for wanted in NAMES[role]:
        for i, c in enumerate(columns):
            if c.key == wanted and i not in claimed:
                return i
    return None


def _roles(columns: list[Column], mapped: Mapping[str, str]) -> dict[str, int]:
    """Role -> column index. Within the node roles and within the edge roles, a column that --columns
    maps is never taken by another role's known names; one column may serve a node role and an edge
    role (a mixed table's `label`)."""
    roles: dict[str, int] = {}
    for group in (NODE_ROLES, EDGE_ROLES):
        claimed = {i for r in group if r in mapped and (i := _find(columns, r, mapped, set())) is not None}
        for role in group:
            if (i := _find(columns, role, mapped, claimed)) is not None:
                roles[role] = i
    return roles


def classify(t: Table, columns: Mapping[str, str]) -> None:
    """Find the roles and check every row; a table without rows is an empty source, whatever its header."""
    if not t.rows:
        return
    roles = t.roles = _roles(t.columns, columns)
    if t.is_edges:
        src, tgt, ident = roles["source"], roles["target"], roles.get("id")
        for line, cells in t.rows:
            if cells[src] and cells[tgt]:
                continue
            if not cells[src] and not cells[tgt] and ident is not None and cells[ident]:
                continue                        # a node row in a mixed table (APOC's export)
            raise TableError(f"{t.name}: line {line}: an edge needs both a source and a target")
    elif "id" in roles:
        for line, cells in t.rows:
            if not cells[roles["id"]]:
                raise TableError(f"{t.name}: line {line}: no id")
    else:
        found = ", ".join(c.header for c in t.columns)
        raise TableError(f"{t.name}: no source and target columns and no id column (found: {found}); "
                         "name them, or map them with --columns")


def check_mapped(columns: Mapping[str, str], tables: list[Table]) -> None:
    """Every header that `columns` names is in some table of the run."""
    for role, header in columns.items():
        if not any(c.header.lower() == header for t in tables for c in t.columns):
            raise ValueError(f"no table has the column {header!r} that {role}={header} names")


def enc(text: str) -> str:
    """Percent-encode what a minted local name must not hold as is; Unicode stays."""
    return _UNSAFE.sub(lambda m: "".join(f"%{b:02X}" for b in m.group().encode("utf-8")), text)


class _Minter:
    """Ids and vocabulary to IRIs: <...> and :// as written, a CURIE through the RDF sources' prefixes,
    anything else under `base`."""

    def __init__(self, prefixes: Mapping[str, str], base: str):
        self.namespaces = iri.by_prefix(prefixes)
        self.base = base
        self.vocab_cache: dict[str, URIRef] = {}

    def written(self, text: str, where: str) -> URIRef | None:
        try:
            return iri.written(text, self.namespaces)
        except ValueError as e:
            raise TableError(f"{where}: {e}") from None

    def node(self, text: str, where: str, group: str | None = None) -> tuple[URIRef, bool]:
        """(IRI, minted?) of an id cell."""
        written = self.written(text, where)
        if written is not None:
            return written, False
        local = enc(text) if group is None else f"{enc(group)}/{enc(text)}"
        return URIRef(self.base + local), True

    def minted(self, text: str) -> URIRef:
        return URIRef(self.base + enc(re.sub(r"\s+", "_", text)))

    def vocab(self, text: str, where: str) -> URIRef:
        """A relation, a type or a property name; minted with whitespace runs as _."""
        if text not in self.vocab_cache:
            written = self.written(text, where)
            self.vocab_cache[text] = written if written is not None else self.minted(text)
        return self.vocab_cache[text]

    def edge_prop(self, text: str, where: str) -> URIRef:
        """An edge property's predicate, never one of the statement's own (rdf:type, rdf:subject,
        rdf:predicate, rdf:object): such a header is minted, or it would break the statement."""
        q = self.vocab(text, where)
        return self.minted(text) if q in _STATEMENT else q


def _values(cell: str, col: Column) -> list[str]:
    return [v for v in (part.strip() for part in cell.split(";")) if v] if col.array else [cell]


def to_graphs(tables: list[Table], prefixes: Mapping[str, str], base: str,
              said: Callable[[URIRef], bool] | None = None) -> tuple[list[Graph], dict[URIRef, int]]:
    """One graph per table, built together: ids meet across tables, and a minted node that no node
    row labels gets its id as rdfs:label from the table holding its first node row, else from the
    first table that mentions it. Also returns the IRI and CURIE ids whose node rows said nothing
    (IRI -> table index), which the loader still makes nodes of. `said(iri)` tells whether an RDF source
    already has that IRI as a subject: such a node keeps the label and the owner that source gives it,
    so it gets no automatic label."""
    mint = _Minter(prefixes, base)
    graphs = [Graph() for _ in tables]
    bare: dict[URIRef, int] = {}
    raw: dict[URIRef, str] = {}             # minted node -> its id as written
    home: dict[URIRef, int] = {}            # minted node -> table of its first node row
    seen: dict[URIRef, int] = {}            # minted node -> first table that mentions it
    labelled: set[URIRef] = set()
    related = URIRef(base + RELATED)

    def node(text: str, col: Column, where: str, ti: int) -> URIRef:
        n, minted = mint.node(text, where, col.group)
        if minted:
            raw.setdefault(n, text)
            seen.setdefault(n, ti)
        return n

    for ti, t in enumerate(tables):
        g, roles, cols = graphs[ti], t.roles, t.columns
        edge_skip = {roles.get(r) for r in EDGE_ROLES}
        node_skip = {roles.get(r) for r in NODE_ROLES}
        for line, cells in t.rows:
            where = f"{t.name}: line {line}"
            if t.is_edges and cells[roles["source"]]:
                s = node(cells[roles["source"]], cols[roles["source"]], where, ti)
                o = node(cells[roles["target"]], cols[roles["target"]], where, ti)
                rel = roles.get("relation")
                p = mint.vocab(cells[rel], where) if rel is not None and cells[rel] else related
                g.add((s, p, o))
                props = [(mint.edge_prop(c.name, where), Literal(v))
                         for i, c in enumerate(cols) if i not in edge_skip and c.key and c.name and cells[i]
                         for v in _values(cells[i], c)]
                if props:
                    b = BNode()
                    for q, v in ((RDF.type, RDF.Statement), (RDF.subject, s), (RDF.predicate, p),
                                 (RDF.object, o), *props):
                        g.add((b, q, v))
                continue
            n = node(cells[roles["id"]], cols[roles["id"]], where, ti)
            if n in raw:
                home.setdefault(n, ti)
            elif not any(cells[i] and c.key for i, c in enumerate(cols) if i != roles["id"]):
                bare.setdefault(n, ti)             # an IRI id with nothing else: load makes it a node
            for i, c in enumerate(cols):
                if not cells[i] or not c.key or i == roles["id"]:
                    continue
                if i == roles.get("label"):
                    for v in _values(cells[i], c):
                        g.add((n, RDFS.label, Literal(v)))
                        labelled.add(n)
                elif i == roles.get("type"):
                    # APOC writes ":Person:Actor"; everyone else separates types with ";"
                    for v in (part.strip() for part in cells[i].split(":" if c.key == "_labels" else ";")):
                        if v:
                            g.add((n, RDF.type, mint.vocab(v, where)))
                elif i == roles.get("description"):
                    g.add((n, RDFS.comment, Literal(cells[i])))
                elif i not in node_skip and c.name:
                    q = mint.vocab(c.name, where)
                    for v in _values(cells[i], c):
                        g.add((n, q, Literal(v)))
                    if q in _LABELS:
                        labelled.add(n)
    for n, text in raw.items():
        if n not in labelled and not (said and said(n)):
            graphs[home.get(n, seen[n])].add((n, RDFS.label, Literal(text)))
    return graphs, bare
