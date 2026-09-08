"""Build the node/link model of a Dataset.

Nodes are every IRI that is a subject of some triple or the object of a link,
except IRIs of the RDF/RDFS/OWL/XSD vocabularies and ontology headers.
Links are IRI-to-IRI triples whose predicate describes a relation rather than
an attribute (rdf:type, imports and provenance go to the node card instead).
Parallel edges collapse into one link listing every predicate. Each node
remembers the file that first declares it; each link remembers the file(s)
asserting it, so a file that only adds edges between other files' nodes still
owns something visible.
"""
from __future__ import annotations
import re
from collections import defaultdict
from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD
from .load import Dataset

COLOR_KEYS = ("file", "type", "namespace")
RESERVED = tuple(str(ns) for ns in (RDF, RDFS, OWL, XSD))
ATTRIBUTE_PREDS = {RDF.type, OWL.imports, OWL.versionIRI, OWL.priorVersion,
                   RDFS.isDefinedBy, PROV.wasDerivedFrom, DCTERMS.source}
LABEL_PREDS = (RDFS.label, SKOS.prefLabel)
DEFINITION_PREDS = (SKOS.definition, RDFS.comment, DCTERMS.description)
SOURCE_PREDS = (PROV.wasDerivedFrom, DCTERMS.source)
_CARD_SLOTS = set(LABEL_PREDS) | set(DEFINITION_PREDS) | {SKOS.altLabel}


def local(u) -> str:
    return re.split(r"[/#]", str(u))[-1] or str(u)


def namespace_of(u) -> str:
    s = str(u)
    return s[:max(s.rfind("#"), s.rfind("/")) + 1]


def _first(g, s, preds):
    for p in preds:
        vals = sorted(str(o) for o in g.objects(s, p))
        if vals:
            return vals[0]
    return None


def build(ds: Dataset, color_by: str = "file") -> dict:
    if color_by not in COLOR_KEYS:
        raise ValueError(f"color_by must be one of {COLOR_KEYS}, got {color_by!r}")
    g = ds.merged
    headers = set(g.subjects(RDF.type, OWL.Ontology))

    def eligible(t) -> bool:
        return (isinstance(t, URIRef) and t not in headers
                and not str(t).startswith(RESERVED))

    def is_link(s, p, o) -> bool:
        return eligible(s) and eligible(o) and p not in ATTRIBUTE_PREDS

    node_file: dict = {}          # node -> first file declaring it as a subject
    mention_file: dict = {}       # node -> first file asserting a link touching it
    link_files: dict = defaultdict(list)   # (s, o) -> files asserting any predicate
    for key, fg in ds.graphs.items():
        for s, p, o in fg:
            if eligible(s):
                node_file.setdefault(s, key)
            if is_link(s, p, o):
                mention_file.setdefault(s, key)
                mention_file.setdefault(o, key)
                if key not in link_files[(s, o)]:
                    link_files[(s, o)].append(key)

    merged_links: dict = defaultdict(set)
    node_ids = set()
    for s, p, o in g:
        if eligible(s):
            node_ids.add(s)
        if is_link(s, p, o):
            node_ids.add(o)
            merged_links[(s, o)].add(local(p))

    labels = {}
    for s in node_ids:
        labels[s] = _first(g, s, LABEL_PREDS) or local(s)
    src_url = {s: str(o) for s, _, o in g.triples((None, DCTERMS.identifier, None))
               if str(o).startswith("http")}

    def group_of(n, types) -> str:
        if color_by == "file":
            return node_file.get(n) or mention_file.get(n) or "?"
        if color_by == "type":
            return types[0] if types else "?"
        ns = namespace_of(n)
        return ds.prefixes.get(ns) or ns

    nodes = []
    for n in sorted(node_ids, key=str):
        types = sorted(local(t) for t in g.objects(n, RDF.type) if t != OWL.NamedIndividual)
        props = defaultdict(list)
        for _, p, o in g.triples((n, None, None)):
            if isinstance(o, Literal) and p not in _CARD_SLOTS:
                props[local(p)].append(str(o))
        sources = sorted(
            ({"label": labels.get(s) or _first(g, s, LABEL_PREDS) or local(s),
              "url": src_url.get(s)}
             for p in SOURCE_PREDS for s in g.objects(n, p)),
            key=lambda d: d["label"])
        ns = namespace_of(n)
        nodes.append({
            "id": str(n), "label": labels[n], "types": types,
            "file": node_file.get(n) or mention_file.get(n) or "?",
            "ns": ds.prefixes.get(ns) or ns,
            "group": group_of(n, types),
            "definition": _first(g, n, DEFINITION_PREDS),
            "alt": sorted(str(o) for o in g.objects(n, SKOS.altLabel)),
            "props": {k: sorted(v) for k, v in sorted(props.items())},
            "sources": sources,
        })

    links = []
    for (s, o), preds in sorted(merged_links.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        files = link_files.get((s, o), [])
        links.append({"source": str(s), "target": str(o), "predicates": sorted(preds),
                      "files": files,
                      "group": (files[0] if files else "?") if color_by == "file" else None})

    groups = {n["group"] for n in nodes}
    if color_by == "file":
        groups |= {l["group"] for l in links}
    return {"nodes": nodes, "links": links, "groups": sorted(groups), "color_by": color_by}
