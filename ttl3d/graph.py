"""Build the node/link model of a Dataset.

Nodes are every IRI that is a subject of some triple or the object of a link,
except IRIs of the RDF/RDFS/OWL/XSD vocabularies and ontology headers.
Links are IRI-to-IRI triples whose predicate describes a relation rather than
an attribute (rdf:type, imports and provenance go to the node card instead).
Parallel edges collapse into one link listing every predicate; an edge
asserted in both directions is one link whose `reverse` list holds the
predicates pointing back. Each node remembers the file that first declares
it; each link remembers the file(s) asserting it, so a file that only adds
edges between other files' nodes still owns something visible.

A node's label is chosen by preference tier: the requested `--lang` language
first, then untagged literals, then any other language, alphabetical within
a tier; the same order picks the definition among skos:definition,
rdfs:comment and dcterms:description. Label and altLabel values that lose
that pick become synonyms in `alt`, and a definition-slot literal that loses
its pick stays visible in the property table instead of vanishing. Literal
`dcterms:source` / `prov:wasDerivedFrom` values land in the property table
too; only IRI sources appear in the node's `sources` list.
"""
from __future__ import annotations

from collections import defaultdict

from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD

from .load import Dataset, local, namespace_of

COLOR_KEYS = ("file", "type", "namespace")
RESERVED = tuple(str(ns) for ns in (RDF, RDFS, OWL, XSD))
ATTRIBUTE_PREDS = {RDF.type, OWL.imports, OWL.versionIRI, OWL.priorVersion,
                   RDFS.isDefinedBy, PROV.wasDerivedFrom, DCTERMS.source}
LABEL_PREDS = (RDFS.label, SKOS.prefLabel)
DEFINITION_PREDS = (SKOS.definition, RDFS.comment, DCTERMS.description)
SOURCE_PREDS = (PROV.wasDerivedFrom, DCTERMS.source)


def _literals(g, s, p, lang: str | None) -> list:
    """Literal objects of (s, p): the requested language first, then untagged,
    then any other language; alphabetical within a tier."""
    def rank(o):
        tag = (o.language or "").lower()
        tier = 0 if lang and tag == lang.lower() else 1 if not tag else 2
        return (tier, str(o))
    return sorted((o for o in g.objects(s, p) if isinstance(o, Literal)), key=rank)


def _first(g, s, preds, lang: str | None = None):
    for p in preds:
        vals = _literals(g, s, p, lang)
        if vals:
            return str(vals[0])
    return None


def _prefix(ds: Dataset, ns: str) -> str:
    """Prefix bound to a namespace; the empty default prefix shows as ':'.
    Unbound namespaces fall back to the IRI base itself."""
    if ns in ds.prefixes:
        return ds.prefixes[ns] or ":"
    return ns


def resolve_terms(terms, ds: Dataset) -> set:
    """Turn 'prefix:local', full IRIs, or '<...>'-wrapped IRIs into URIRefs using the
    dataset's bindings. Angle brackets are the Turtle convention for "this is a full
    IRI, not a CURIE" -- needed for schemes like urn: or mailto: that have no "://"."""
    by_prefix: dict = {}
    for ns, prefix in ds.prefixes.items():
        by_prefix.setdefault(prefix, ns)
    out = set()
    for term in terms:
        if term.startswith("<") and term.endswith(">"):
            out.add(URIRef(term[1:-1]))
            continue
        if "://" in term:
            out.add(URIRef(term))
            continue
        prefix, _, name = term.partition(":")
        if prefix not in by_prefix:
            raise ValueError(f"unknown prefix in {term!r}; bind it in an input file, "
                             f"or write the full IRI as <{term}>")
        out.add(URIRef(by_prefix[prefix] + name))
    return out


def build(ds: Dataset, color_by: str = "file", lang: str | None = None,
          type_links: bool = False, attribute_preds=()) -> dict:
    if color_by not in COLOR_KEYS:
        raise ValueError(f"color_by must be one of {COLOR_KEYS}, got {color_by!r}")
    g = ds.merged
    prefixes = ds.prefixes
    headers = set(g.subjects(RDF.type, OWL.Ontology))

    def eligible(t) -> bool:
        return (isinstance(t, URIRef) and t not in headers
                and not str(t).startswith(RESERVED))

    attribute = (set(ATTRIBUTE_PREDS) | set(attribute_preds)) - ({RDF.type} if type_links else set())

    def is_link(s, p, o) -> bool:
        return eligible(s) and eligible(o) and p not in attribute

    node_file: dict = {}          # node -> first file declaring it as a subject
    mention_file: dict = {}       # node -> first file asserting a link touching it
    link_files: dict = defaultdict(list)   # unordered pair -> files asserting any predicate
    for key, fg in ds.graphs.items():
        for s, p, o in fg:
            if eligible(s):
                node_file.setdefault(s, key)
            if is_link(s, p, o):
                mention_file.setdefault(s, key)
                mention_file.setdefault(o, key)
                pair = tuple(sorted((s, o), key=str))
                if key not in link_files[pair]:
                    link_files[pair].append(key)

    merged_links: dict = defaultdict(lambda: {"fwd": set(), "rev": set()})   # pair -> predicates per direction
    node_ids = set()
    for s, p, o in g:
        if eligible(s):
            node_ids.add(s)
        if is_link(s, p, o):
            node_ids.add(o)
            a, b = sorted((s, o), key=str)
            merged_links[(a, b)]["fwd" if s == a else "rev"].add(local(p, prefixes))

    labels = {}
    for s in node_ids:
        labels[s] = _first(g, s, LABEL_PREDS, lang) or local(s, prefixes)
    src_url: dict = {}                    # the smallest URL wins, whatever order rdflib yields them in
    for s, _, o in g.triples((None, DCTERMS.identifier, None)):
        if str(o).startswith("http") and (s not in src_url or str(o) < src_url[s]):
            src_url[s] = str(o)

    def group_of(n, types) -> str:
        if color_by == "file":
            return node_file.get(n) or mention_file.get(n) or "?"
        if color_by == "type":
            return types[0] if types else "?"
        return _prefix(ds, namespace_of(n, prefixes))

    nodes = []
    for n in sorted(node_ids, key=str):
        types = sorted(local(t, prefixes) for t in g.objects(n, RDF.type) if t != OWL.NamedIndividual)
        label_vals = [str(o) for p in LABEL_PREDS for o in _literals(g, n, p, lang)]
        definition = _first(g, n, DEFINITION_PREDS, lang)
        def_pred = next((p for p in DEFINITION_PREDS if _literals(g, n, p, lang)), None)
        props = defaultdict(list)
        for _, p, o in g.triples((n, None, None)):
            if isinstance(o, Literal):
                if p in LABEL_PREDS or p == SKOS.altLabel:
                    continue
                if p == def_pred and str(o) == definition:
                    continue
                props[local(p, prefixes)].append(str(o))
            elif isinstance(o, URIRef) and p in attribute and p != RDF.type and p not in SOURCE_PREDS:
                props[local(p, prefixes)].append(labels.get(o) or _first(g, o, LABEL_PREDS, lang) or str(o))
        alt = sorted(({str(o) for o in g.objects(n, SKOS.altLabel)} | set(label_vals)) - {labels[n]})
        sources = [{"label": label, "url": src_url.get(s)}
                   for label, s in sorted(
                       (labels.get(s) or _first(g, s, LABEL_PREDS, lang) or local(s, prefixes), s)
                       for p in SOURCE_PREDS for s in g.objects(n, p) if isinstance(s, URIRef))]
        ns = namespace_of(n, prefixes)
        nodes.append({
            "id": str(n), "label": labels[n], "types": types,
            "file": node_file.get(n) or mention_file.get(n) or "?",
            "ns": _prefix(ds, ns),
            "group": group_of(n, types),
            "definition": definition,
            "alt": alt,
            "props": {k: sorted(v) for k, v in sorted(props.items())},
            "sources": sources,
        })

    links = []
    for (a, b), d in sorted(merged_links.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        src, tgt, fwd, rev = (a, b, d["fwd"], d["rev"]) if d["fwd"] else (b, a, d["rev"], d["fwd"])
        files = link_files.get((a, b), [])
        links.append({"source": str(src), "target": str(tgt), "predicates": sorted(fwd),
                      "reverse": sorted(rev), "files": files,
                      "group": (files[0] if files else "?") if color_by == "file" else None})

    groups = {n["group"] for n in nodes}
    if color_by == "file":
        groups |= {l["group"] for l in links}
    return {"nodes": nodes, "links": links, "groups": sorted(groups), "color_by": color_by}
