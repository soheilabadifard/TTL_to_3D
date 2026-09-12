"""Cut a Dataset down before the node/link model is built: the neighbourhood of focus IRIs, the
schema (classes and properties) without instances, or the neighbourhood inside the schema. Runs
between load and graph.build, so cards, legend and named-graph ownership come from the unchanged
model code.

    Dataset --Rules.of--> universe U: every IRI graph.build would draw (eligible subjects, link objects)
        |
        |  schema=True : within = U restricted to class and property terms          (schema_terms)
        |  focus given : kept = breadth-first over link triples, both directions, `hops` steps,
        |                never leaving `within`; seeds are always kept              (neighbourhood)
        |  type_links  : plus each seed's own classes inside `within` (a deeper node's classes
        |                come along through the BFS itself, since rdf:type is then a link)  (type closure)
        |  neither     : build_page does not call select at all
        v
    kept --copy--> for each source graph, the kept subjects' triples through the subject index; a
                   triple survives when its object is not an IRI, a kept node, an attribute target,
                   an ontology header or reserved vocabulary; blank-node objects are followed and
                   their triples kept whole; sources left empty drop out; merged is rebuilt
                   --> Dataset' + the size of U
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from .graph import RESERVED, Rules
from .load import Dataset, curie

# an IRI typed as one of these is a schema term
CLASS_TYPES = (OWL.Class, RDFS.Class, RDFS.Datatype, OWL.ObjectProperty, OWL.DatatypeProperty,
               OWL.AnnotationProperty, RDF.Property)
# both ends of a triple with one of these predicates are schema terms
SCHEMA_PREDS = (RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range, OWL.equivalentClass,
                OWL.equivalentProperty, OWL.inverseOf, OWL.disjointWith)


@dataclass
class Sliced:
    dataset: Dataset
    total: int          # nodes the full model would have had, for the notice


def universe(g: Graph, rules: Rules) -> set:
    """Every IRI graph.build would turn into a node: eligible subjects and the objects of links."""
    nodes = set()
    for s, p, o in g:
        if rules.eligible(s):
            nodes.add(s)
            if rules.is_link(s, p, o):
                nodes.add(o)
    return nodes


def schema_terms(g: Graph, rules: Rules, nodes: set) -> set:
    """Classes and properties among `nodes`: typed as one, used as an rdf:type object, or an end of
    a hierarchy, domain/range, equivalence, inverse or disjointness triple."""
    terms = set()
    for t in CLASS_TYPES:
        terms.update(g.subjects(RDF.type, t))
    terms.update(g.objects(None, RDF.type))
    for p in SCHEMA_PREDS:
        for s, o in g.subject_objects(p):
            terms.update((s, o))
    return terms & nodes


def neighbourhood(g: Graph, rules: Rules, seeds: Iterable[URIRef], hops: int, within: set) -> set:
    """Breadth-first over link triples in both directions, `hops` steps, never leaving `within`.
    The memory store indexes by subject and by object, so this costs the neighbourhood, not the file."""
    kept = set(seeds)
    frontier = set(kept)
    for _ in range(hops):
        found = set()
        for n in frontier:
            for s, p, o in g.triples((n, None, None)):
                if rules.is_link(s, p, o) and o in within and o not in kept:
                    found.add(o)
            for s, p, o in g.triples((None, None, n)):
                if rules.is_link(s, p, o) and s in within and s not in kept:
                    found.add(s)
        kept |= found
        frontier = found
        if not frontier:
            break
    return kept


def _copy(source: Graph, kept: set, rules: Rules) -> Graph:
    """The kept subjects' surviving triples from one source graph, through the subject index. An IRI
    object survives when it is a kept node, an attribute target, an ontology header or reserved
    vocabulary (never an edge to a dropped node); literals and blank nodes always survive, and a
    blank node's own triples are kept whole, recursively, so restrictions and lists stay intact. A
    referenced header is walked too, so its own `rdf:type owl:Ontology` triple survives and
    graph.build's own Rules.of still recognises it as a header rather than a leaked node."""
    part = Graph()
    pending, seen = list(kept), set()
    while pending:
        s = pending.pop()
        if s in seen:
            continue
        seen.add(s)
        for triple in source.triples((s, None, None)):
            _, p, o = triple
            if isinstance(s, BNode) or not isinstance(o, URIRef) or o in kept or p in rules.attribute \
                    or o in rules.headers or str(o).startswith(RESERVED):
                part.add(triple)
                if isinstance(o, BNode) or o in rules.headers:
                    pending.append(o)
    return part


def select(ds: Dataset, *, focus: Iterable[URIRef] = (), hops: int = 1, schema: bool = False,
           type_links: bool = False, attribute_preds: Iterable[URIRef] = ()) -> Sliced:
    """The slice as a Dataset (same files, prefixes and sources; per-source graphs filtered; sources
    left empty dropped from `graphs` and `named`) plus the size of the full model. A focus IRI that
    is not a node of the data raises ValueError naming every such IRI, in the order given."""
    g = ds.merged
    rules = Rules.of(g, type_links, attribute_preds)
    nodes = universe(g, rules)
    seeds = list(focus)
    missing = [str(f) for f in seeds if f not in nodes]
    if missing:
        raise ValueError("; ".join(f"focus <{m}> is not a node in the data" for m in missing))
    within = schema_terms(g, rules, nodes) if schema else nodes
    kept = neighbourhood(g, rules, seeds, hops, within) if seeds else within
    if type_links:      # a seed's own classes come along even at hops=0, so its card keeps its type;
        kept |= {o for s in seeds for o in g.objects(s, RDF.type) if o in within}  # deeper hops reach
        # a neighbour's classes through the BFS itself, since rdf:type is a link when type_links is set
    graphs: dict[str, Graph] = {}
    named: dict[str, URIRef] = {}
    for key, source in ds.graphs.items():
        part = _copy(source, kept, rules)
        if len(part):
            graphs[key] = part
            if key in ds.named:
                named[key] = ds.named[key]
    merged = Graph()
    for part in graphs.values():
        for triple in part:
            merged.add(triple)
    return Sliced(Dataset(ds.files, graphs, merged, ds.prefixes, ds.sources, named), len(nodes))


def describe(kept: int, total: int, focus: Iterable[URIRef], hops: int, schema: bool, prefixes) -> str:
    """The stderr notice, e.g. `kept 3 of 12 nodes (focus ex:Dune, 1 hop)`; focus IRIs are shortened
    like legend keys and listed in the order given."""
    parts = ["schema only"] if schema else []
    seeds = list(focus)
    if seeds:
        shown = ", ".join(curie(f, prefixes) for f in seeds)
        parts.append(f"focus {shown}, {hops} hop{'' if hops == 1 else 's'}")
    return f"kept {kept} of {total} nodes ({'; '.join(parts)})"
