"""ttl3d.slice: a neighbourhood or the schema of a Dataset, cut before the node/link model is built.
Expected sets were traced on the library fixtures: 12 nodes, 6 links, schema terms Author, Book,
Person, pages, wrote."""
import pytest
from rdflib import BNode, URIRef

from ttl3d import graph, load, slice

EX = "http://example.org/library#"
RDFS = "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
OWL = "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"


def ex(local):
    return URIRef(EX + local)


def names(data):
    return sorted(n["id"].rsplit("#", 1)[-1] for n in data["nodes"])


def edges(data):
    return sorted((l["source"].rsplit("#", 1)[-1], "/".join(l["predicates"]), l["target"].rsplit("#", 1)[-1])
                  for l in data["links"])


@pytest.fixture
def two(library, library_extra):
    return load.load_files([library, library_extra])


def sliced(ds, **kw):
    """The model of the slice, built with the same type_links the slice used."""
    return graph.build(slice.select(ds, **kw).dataset, type_links=kw.get("type_links", False))


def test_hops_zero_keeps_the_focus_node_with_its_card_content_and_nothing_else(two):
    data = sliced(two, focus=[ex("Dune")], hops=0)
    assert names(data) == ["Dune"] and data["links"] == []
    dune = data["nodes"][0]
    assert dune["types"] == ["Book"] and dune["props"] == {"pages": ["412"]}
    assert dune["definition"] == "Science-fiction novel."


def test_one_hop_follows_links_both_ways_but_never_an_attribute(two):
    data = sliced(two, focus=[ex("Dune")], hops=1)
    # in through wrote, out through relatedTo; Book is only a type
    assert names(data) == ["Dune", "Herbert", "Prefonly"]
    assert edges(data) == [("Dune", "relatedTo", "Prefonly"), ("Herbert", "wrote", "Dune")]
    # nothing further within two hops
    assert names(sliced(two, focus=[ex("Dune")], hops=2)) == ["Dune", "Herbert", "Prefonly"]


def test_an_attribute_predicate_is_not_a_hop_but_its_triple_survives_on_the_card(tmp_path):
    ttl = tmp_path / "c.ttl"
    ttl.write_text("@prefix ex: <http://example.org/c#> .\nex:a ex:custom ex:b ; ex:p ex:c .\n",
                   encoding="utf-8")
    def ex_c(s):
        return URIRef("http://example.org/c#" + s)

    cut = slice.select(load.load_files([ttl]), focus=[ex_c("a")], hops=1, attribute_preds=[ex_c("custom")])
    data = graph.build(cut.dataset, attribute_preds=[ex_c("custom")])
    assert names(data) == ["a", "c"] and edges(data) == [("a", "p", "c")]
    assert (ex_c("a"), ex_c("custom"), ex_c("b")) in cut.dataset.merged       # kept for the card, not walked


def test_type_links_make_classes_hops_and_a_class_is_a_hub(two):
    one = names(sliced(two, focus=[ex("Dune")], hops=1, type_links=True))
    assert one == ["Author", "Book", "Dune", "Herbert", "Prefonly"]
    assert names(sliced(two, focus=[ex("Dune")], hops=2, type_links=True)) == [
        "Author", "Book", "Dune", "Foundation", "Herbert", "Prefonly", "Unlabeled", "Weird", "wrote"]


def test_type_links_keep_every_kept_nodes_classes_even_at_hops_zero(two):
    data = sliced(two, focus=[ex("Dune")], hops=0, type_links=True)
    assert names(data) == ["Book", "Dune"] and edges(data) == [("Dune", "type", "Book")]


def test_type_links_closure_keeps_the_classes_of_kept_classes_too(tmp_path):
    ttl = tmp_path / "m.ttl"
    ttl.write_text("@prefix ex: <http://example.org/m#> .\nex:Dune a ex:Book .\nex:Book a ex:Genre .\n",
                   encoding="utf-8")
    data = sliced(load.load_files([ttl]), focus=[URIRef("http://example.org/m#Dune")], hops=0,
                  type_links=True)
    assert names(data) == ["Book", "Dune", "Genre"]
    assert edges(data) == [("Book", "type", "Genre"), ("Dune", "type", "Book")]


def test_schema_keeps_classes_and_properties_and_drops_individuals(two):
    data = sliced(two, schema=True)
    assert names(data) == ["Author", "Book", "Person", "pages", "wrote"]        # pages: an island
    assert edges(data) == [("Author", "subClassOf", "Person"), ("wrote", "domain", "Author"),
                           ("wrote", "range", "Book")]


def test_a_focus_inside_the_schema_walks_the_schema_only(two):
    data = sliced(two, focus=[ex("Book")], hops=1, schema=True)
    assert names(data) == ["Book", "wrote"] and edges(data) == [("wrote", "range", "Book")]
    assert names(sliced(two, focus=[ex("Book")], hops=2, schema=True)) == ["Author", "Book", "wrote"]


def test_a_focus_outside_the_schema_is_kept_and_type_links_bring_its_classes(two):
    assert names(sliced(two, focus=[ex("Dune")], hops=1, schema=True)) == ["Dune"]
    assert names(sliced(two, focus=[ex("Dune")], hops=1, schema=True, type_links=True)) == ["Book", "Dune"]


def test_several_focus_iris_give_the_union_of_their_neighbourhoods(two):
    assert names(sliced(two, focus=[ex("Dune"), ex("Asimov")], hops=1)) == [
        "Asimov", "Dune", "Foundation", "Herbert", "Prefonly"]


def test_every_unknown_focus_is_named_in_the_error_in_order(two):
    with pytest.raises(ValueError) as e:
        slice.select(two, focus=[ex("Nope"), ex("Nada")])
    assert str(e.value) == ("focus <http://example.org/library#Nope> is not a node in the data; "
                            "focus <http://example.org/library#Nada> is not a node in the data")


def test_without_focus_or_schema_the_model_is_unchanged(two):
    assert graph.build(slice.select(two).dataset) == graph.build(two)


def test_ownership_and_the_total_survive_on_the_fixtures(two):
    full = graph.build(two)
    result = slice.select(two, focus=[ex("Dune")], hops=1)
    owner = {n["id"]: n["file"] for n in full["nodes"]}
    assert all(owner[n["id"]] == n["file"] for n in graph.build(result.dataset)["nodes"])
    assert result.total == len(full["nodes"]) == 12


def test_ownership_follows_the_surviving_triples(tmp_path):
    prefix = "@prefix ex: <http://example.org/o#> .\n"
    (tmp_path / "one.ttl").write_text(prefix + "ex:a ex:p ex:b .\n", encoding="utf-8")
    (tmp_path / "two.ttl").write_text(prefix + RDFS + 'ex:a rdfs:label "A" .\n', encoding="utf-8")
    ds = load.load_files([tmp_path / "one.ttl", tmp_path / "two.ttl"])
    full = graph.build(ds)
    assert next(n for n in full["nodes"] if n["id"].endswith("#a"))["file"] == "one"
    cut = graph.build(slice.select(ds, focus=[URIRef("http://example.org/o#a")], hops=0).dataset)
    assert [n["file"] for n in cut["nodes"]] == ["two"]       # one asserted only the dropped edge
    assert cut["groups"] == ["two"]


def test_named_graphs_left_empty_leave_the_legend_but_not_the_title(library_trig):
    result = slice.select(load.load_files([library_trig]), focus=[ex("Dune")], hops=1)
    assert result.dataset.stems == [":catalogue", "ex:extra"]           # the schema graph `library` is empty
    assert list(result.dataset.named) == [":catalogue", "ex:extra"]
    assert result.dataset.sources == ["library"]


def test_a_header_referenced_by_a_kept_node_is_dropped_with_its_edge(tmp_path):
    ttl = tmp_path / "h.ttl"
    ttl.write_text("@prefix ex: <http://example.org/h#> .\n" + OWL + RDFS
                   + "<http://example.org/h> a owl:Ontology .\n"
                   + 'ex:a rdfs:label "A" ; ex:p <http://example.org/h> ; ex:q ex:b .\n',
                   encoding="utf-8")
    a, header = URIRef("http://example.org/h#a"), URIRef("http://example.org/h")
    cut = slice.select(load.load_files([ttl]), focus=[a], hops=0)
    data = graph.build(cut.dataset)
    assert names(data) == ["a"] and data["links"] == []
    assert not list(cut.dataset.merged.triples((None, None, header)))   # the header went with its edge
    assert not list(cut.dataset.merged.triples((header, None, None)))   # and so did the header's own triples


def test_a_focus_that_is_only_a_link_object_has_nothing_of_its_own_at_hops_zero(tmp_path):
    ttl = tmp_path / "o.ttl"
    ttl.write_text("@prefix ex: <http://example.org/o#> .\nex:a ex:p ex:b .\n", encoding="utf-8")
    ds = load.load_files([ttl])
    b = URIRef("http://example.org/o#b")
    cut = slice.select(ds, focus=[b], hops=0)
    assert cut.total == 2 and graph.build(cut.dataset)["nodes"] == []
    assert names(sliced(ds, focus=[b], hops=1)) == ["a", "b"]


def test_blank_node_structure_below_a_kept_node_survives_whole(tmp_path):
    ttl = tmp_path / "r.ttl"
    ttl.write_text("@prefix ex: <http://example.org/r#> .\n" + OWL + RDFS
                   + "ex:Book rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:wrote ;"
                   " owl:someValuesFrom ex:Person ] .\n"
                   "ex:a ex:order ( ex:x ex:y ) .\n", encoding="utf-8")
    ds = load.load_files([ttl])
    focus = [URIRef("http://example.org/r#Book"), URIRef("http://example.org/r#a")]
    cut = slice.select(ds, focus=focus, hops=0).dataset
    assert sum(1 for s, _, _ in cut.merged if isinstance(s, BNode)) == 7   # 3 restriction + 4 list cells
    assert names(graph.build(cut)) == ["Book", "a"]                          # blank nodes are still not nodes


def test_describe_names_what_was_kept():
    p = {EX: "ex"}
    assert slice.describe(3, 12, [ex("Dune")], 1, False, p) == "kept 3 of 12 nodes (focus ex:Dune, 1 hop)"
    assert slice.describe(5, 12, [], 1, True, p) == "kept 5 of 12 nodes (schema only)"
    both = slice.describe(3, 12, [ex("Book")], 2, True, p)
    assert both == "kept 3 of 12 nodes (schema only; focus ex:Book, 2 hops)"
    unbound = slice.describe(1, 2, [URIRef("http://g/s0")], 0, False, {})
    assert unbound == "kept 1 of 2 nodes (focus http://g/s0, 0 hops)"
