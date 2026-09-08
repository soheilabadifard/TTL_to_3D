"""ttl3d.graph: the node/link model built from a Dataset."""
import pytest
from ttl3d import load, graph

EX = "http://example.org/library#"


def build(*files, color_by="file"):
    return graph.build(load.load_files(files), color_by=color_by)


def ids(data):
    return {n["id"] for n in data["nodes"]}


def node(data, local):
    return next(n for n in data["nodes"] if n["id"] == EX + local)


def edges(data):
    return {(l["source"].split("#")[1], p, l["target"].split("#")[1])
            for l in data["links"] for p in l["predicates"]}


def test_reserved_vocabulary_and_ontology_header_are_not_nodes(library):
    data = build(library)
    assert ids(data) == {EX + x for x in
                         ["Book", "Person", "Author", "wrote", "pages",
                          "Dune", "Herbert", "Unlabeled", "Prefonly", "Weird"]}


def test_links_are_iri_to_iri_triples_minus_type_and_dropped_nodes(library):
    assert edges(build(library)) == {
        ("Author", "subClassOf", "Person"),
        ("wrote", "domain", "Author"),
        ("wrote", "range", "Book"),
        ("Herbert", "wrote", "Dune"),
    }


def test_rdf_type_becomes_types_without_named_individual(library):
    data = build(library)
    assert node(data, "Herbert")["types"] == ["Author"]
    assert node(data, "Book")["types"] == ["Class"]


def test_label_preference_label_then_preflabel_then_local_name(library):
    data = build(library)
    assert node(data, "Dune")["label"] == "Dune"
    assert node(data, "Prefonly")["label"] == "Pref only"
    assert node(data, "Unlabeled")["label"] == "Unlabeled"


def test_card_fields(library):
    data = build(library)
    assert node(data, "Book")["definition"] == "A written work."
    dune = node(data, "Dune")
    assert dune["definition"] == "Science-fiction novel."      # rdfs:comment fallback
    assert dune["alt"] == ["Dune (novel)"]
    assert dune["props"] == {"pages": ["412"]}


def test_sources_go_to_the_card_not_the_links(tmp_path):
    ttl = tmp_path / "s.ttl"
    ttl.write_text(
        "@prefix ex: <http://example.org/s#> .\n"
        "@prefix prov: <http://www.w3.org/ns/prov#> .\n"
        "@prefix dcterms: <http://purl.org/dc/terms/> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "ex:a prov:wasDerivedFrom ex:src ; dcterms:source ex:src2 .\n"
        'ex:src rdfs:label "Source X" ; dcterms:identifier "https://doi.org/10.1/x" .\n')
    data = build(ttl)
    a = next(n for n in data["nodes"] if n["id"].endswith("#a"))
    assert a["sources"] == [{"label": "Source X", "url": "https://doi.org/10.1/x"},
                            {"label": "src2", "url": None}]
    assert data["links"] == []


def test_parallel_edges_collapse_into_one_link(tmp_path):
    ttl = tmp_path / "p.ttl"
    ttl.write_text("@prefix ex: <http://example.org/p#> .\nex:a ex:p ex:b .\nex:a ex:q ex:b .\n")
    data = build(ttl)
    assert len(data["links"]) == 1
    assert data["links"][0]["predicates"] == ["p", "q"]


def test_second_file_owns_its_edge_but_not_the_nodes(library, library_extra):
    data = build(library, library_extra)
    link = next(l for l in data["links"] if l["predicates"] == ["relatedTo"])
    assert link["files"] == ["library-extra"]
    assert node(data, "Dune")["file"] == "library"          # repeated label does not steal it
    assert node(data, "Asimov")["file"] == "library-extra"
    assert len(data["nodes"]) == 12 and len(data["links"]) == 6


def test_group_by_file_type_and_namespace(library, library_extra):
    by_file = build(library, library_extra)
    assert node(by_file, "Asimov")["group"] == "library-extra"
    assert by_file["groups"] == ["library", "library-extra"]
    by_type = build(library, color_by="type")
    assert node(by_type, "Dune")["group"] == "Book"
    assert node(by_type, "wrote")["group"] == "ObjectProperty"
    by_ns = build(library, color_by="namespace")
    assert node(by_ns, "Dune")["group"] == "ex"


def test_unbound_namespace_group_falls_back_to_the_iri_base(tiny_nt):
    data = build(tiny_nt, color_by="namespace")
    assert {n["group"] for n in data["nodes"]} == {"http://example.org/nt#"}


def test_node_mentioned_only_as_object_belongs_to_the_file_asserting_the_edge(tiny_nt):
    data = build(tiny_nt)
    assert {n["file"] for n in data["nodes"]} == {"tiny"}


def test_link_group_follows_the_asserting_file_only_in_file_mode(library, library_extra):
    assert all(l["group"] == l["files"][0] for l in build(library, library_extra)["links"])
    assert all(l["group"] is None
               for l in build(library, library_extra, color_by="type")["links"])


def test_invalid_color_by_is_rejected(library):
    with pytest.raises(ValueError):
        build(library, color_by="colour")
