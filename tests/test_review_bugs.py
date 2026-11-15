"""A bug review of ttl3d: correctness defects found by reading every module, each with a test.

Real bugs (both fixed since; the tests failed when the review wrote them and now pin the fix):

1. ttl3d/graph.py:243-246 -- a node's `sources` card list repeated an entry when the same source
   IRI was reached through two source predicates (prov:wasDerivedFrom and dcterms:source).
   Expected: each source listed once; it was one duplicate row per extra predicate.

2. ttl3d/graph.py:226-228 -- a node's `types` list could hold the same name twice: `type_name`
   (graph.py:207-208) is built from URIRef types only, but the per-node comprehension iterated
   every rdf:type object, so a literal type spelling the same name as a class IRI duplicated it.
   Expected: unique display names; it was ["Person", "Person"]. Only IRI types are types now
   (tests/test_graph.py::test_only_an_iri_type_is_a_type has the blank-node case).

Suspicious but deliberate behaviours (characterization tests; they PASS and document the
behaviour with a NOTE):

3. ttl3d/load.py:266-272, 275-281 -- `load((path_a, path_b))` reads ONE source: a tuple is always
   a (name, item) pair, so path_a becomes the legend NAME and only path_b is loaded. Documented
   in the docstrings, but a silent data-loss trap for anyone passing a tuple of paths
   (`load_files` wraps its argument in `list()` precisely to avoid it).

4. ttl3d/table.py:379-381 -- a Neo4j `:LABEL` column (key ":label", table.py:80) never splits its
   cells on colons; only APOC's `_labels` header does. The review took colons for neo4j-admin's
   multi-label spelling; it is the semicolon (`Movie;Sequel`, or --array-delimiter), so the code
   reads `:LABEL` as Neo4j does, and a `:Person:Actor` cell there is one label in both.

5. ttl3d/table.py:298 + ttl3d/load.py:80-94 -- a grouped minted id (":ID(Person)") contains a raw
   "/" (base + group + "/" + text), and split_iri's bound-namespace fallback refuses a remainder
   with "/", so under --color-by namespace one minted namespace shows as two legend groups: the
   bound "csv" for ungrouped ids and the raw IRI "urn:x-ttl3d:Person/" for grouped ones.
"""
from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from ttl3d import graph, load, table

PRELUDE = (
    "@prefix ex: <http://example.org/r#> .\n"
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
    "@prefix prov: <http://www.w3.org/ns/prov#> .\n"
    "@prefix dcterms: <http://purl.org/dc/terms/> .\n"
)


def build_text(turtle, **kw):
    """The model of one in-memory turtle text."""
    g = Graph()
    g.parse(data=(PRELUDE + turtle).encode(), format="turtle")
    return graph.build(load.load([g]), **kw)


def by_local(data, local):
    return next(n for n in data["nodes"] if n["id"].endswith("#" + local))


def test_bug_1_duplicate_card_source_rows():
    """ttl3d/graph.py:243-246.

    Bug (fixed): the `sources` list of a node was built with one entry per (predicate, object)
    pair of SOURCE_PREDS, without deduplicating the source IRIs. A node whose derivation is
    asserted with both prov:wasDerivedFrom and dcterms:source pointing at the SAME IRI got that
    source twice on its card.

    Expected: the source "B" is listed once.
    Was:      sources == [{...B...}, {...B...}] -- the same row twice.
    """
    data = build_text(
        'ex:a prov:wasDerivedFrom ex:b ;\n'
        '    dcterms:source ex:b .\n'
        'ex:b rdfs:label "B" .\n')
    a = by_local(data, "a")
    assert a["sources"] == [{"label": "B", "url": None}]


def test_bug_2_duplicate_type_names():
    """ttl3d/graph.py:226-228.

    Bug (fixed): `type_name` (graph.py:207-208) is built from the URIRef rdf:type objects only,
    but the per-node `types` comprehension iterated every rdf:type object (including literals and
    blank nodes) and fell back to `local()`. When a literal type spelled the same name as a class
    IRI, both mapped to the same display name and the card's type list repeated it.

    Expected: types == ["Person"] -- display names are unique.
    Was:      types == ["Person", "Person"].
    """
    data = build_text('ex:a a ex:Person, "Person" .\n')
    a = by_local(data, "a")
    assert a["types"] == ["Person"]


def test_bug_3_tuple_of_paths_loads_one_named_source(tmp_path):
    """ttl3d/load.py:266-272 (_items) and 275-281 (_named).

    NOTE: `load()` treats any 2-tuple as a (name, item) pair. Passing a tuple of two paths
    therefore loads ONLY the second path, under the first path as its name -- the first file's
    triples silently vanish. This is documented ("a tuple is always a (name, item) pair, never
    two sources") and `load_files` wraps its argument in `list()` to avoid it, but `load()`
    itself accepts the tuple without complaint. This test documents the behaviour.
    """
    x = tmp_path / "x.ttl"
    y = tmp_path / "y.ttl"
    x.write_text("@prefix ex: <http://example.org/r#> .\nex:x ex:p ex:xx .\n", encoding="utf-8")
    y.write_text("@prefix ex: <http://example.org/r#> .\nex:y ex:p ex:yy .\n", encoding="utf-8")

    ds = load.load((str(x), str(y)))          # meant as "two files"; read as one named pair

    # the legend name is the FIRST path; only the SECOND file was actually loaded
    assert ds.sources == [str(x)]
    ex = "http://example.org/r#"
    assert len(ds.merged) == 1
    assert (URIRef(ex + "y"), URIRef(ex + "p"), URIRef(ex + "yy")) in ds.merged
    assert (URIRef(ex + "x"), URIRef(ex + "p"), URIRef(ex + "xx")) not in ds.merged


def test_bug_4_neo4j_label_column_cells_are_not_split_on_colons():
    """ttl3d/table.py:379-381.

    NOTE: the type-cell split on ":" applies only to APOC's `_labels` header (key "_labels");
    a Neo4j `:LABEL` column gets key ":label" (table.py:80), so its cells are split on ";".
    That is neo4j-admin's own rule ("multiple labels are separated by ;, or by the character
    specified with --array-delimiter"; its example row reads `Movie;Sequel`), not the gap the
    review took it for: a ":Person:Actor" cell in `:LABEL` is ONE label there and one type here.
    """
    t = table.parse("personId:ID,:LABEL\n1,:Person:Actor\n", "nodes.csv")
    table.classify(t, {})
    made, _ = table.to_graphs([t], {}, table.DEFAULT_BASE)

    types = sorted(str(o) for o in made[0].objects(None, RDF.type))
    assert types == [table.DEFAULT_BASE + ":Person:Actor"]     # one minted type, not Person+Actor

    # the APOC spelling of the same data does split, which is what the comment promises
    t2 = table.parse("_id,_labels\n1,:Person:Actor\n", "apoc.csv")
    table.classify(t2, {})
    made2, _ = table.to_graphs([t2], {}, table.DEFAULT_BASE)
    assert sorted(str(o).rsplit(":", 1)[-1] for o in made2[0].objects(None, RDF.type)) == [
        "Actor", "Person"]


def test_bug_5_grouped_minted_ids_split_the_namespace_group(tmp_path):
    """ttl3d/table.py:298 (the raw "/" in a grouped id) + ttl3d/load.py:80-94 (split_iri).

    NOTE: a grouped minted id is base + enc(group) + "/" + enc(text), and split_iri only falls
    back to a bound namespace when the remainder holds no "/" or "#". The base is bound (to
    "csv"), yet its grouped ids do not resolve back to it, so --color-by namespace shows ONE
    minted namespace as TWO legend groups: "csv" for ungrouped ids and the raw IRI
    "urn:x-ttl3d:Person/" for grouped ones.
    """
    grouped = tmp_path / "grouped.csv"      # :ID(Person): the id is minted under group/1
    grouped.write_text("personId:ID(Person),name\n1,Keanu\n", encoding="utf-8")
    plain = tmp_path / "plain.csv"          # a plain id: minted under the base itself
    plain.write_text("id,name\n9,Nobody\n", encoding="utf-8")

    ds = load.load_files([grouped, plain])
    data = graph.build(ds, color_by="namespace")

    groups = {n["id"]: n["group"] for n in data["nodes"]}
    assert groups[table.DEFAULT_BASE + "9"] == "csv"                       # the bound base
    assert groups[table.DEFAULT_BASE + "Person/1"] == table.DEFAULT_BASE + "Person/"
    assert sorted(set(groups.values())) == ["csv", table.DEFAULT_BASE + "Person/"]
