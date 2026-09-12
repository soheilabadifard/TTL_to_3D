"""ttl3d.graph: the node/link model built from a Dataset."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from rdflib import URIRef

from ttl3d import graph, load

REPO = Path(__file__).resolve().parents[1]

EX = "http://example.org/library#"


def build(*files, **kw):
    return graph.build(load.load_files(files), **kw)


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
        'ex:src rdfs:label "Source X" ; dcterms:identifier "https://doi.org/10.1/x" .\n',
        encoding="utf-8")
    data = build(ttl)
    a = next(n for n in data["nodes"] if n["id"].endswith("#a"))
    assert a["sources"] == [{"label": "Source X", "url": "https://doi.org/10.1/x"},
                            {"label": "src2", "url": None}]
    assert data["links"] == []


def test_parallel_edges_collapse_into_one_link(tmp_path):
    ttl = tmp_path / "p.ttl"
    ttl.write_text("@prefix ex: <http://example.org/p#> .\nex:a ex:p ex:b .\nex:a ex:q ex:b .\n", encoding="utf-8")
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


def _by_local(data):
    return {n["id"].rsplit("#", 1)[1]: n for n in data["nodes"]}


def test_label_prefers_the_requested_language_then_untagged(tmp_path):
    ttl = tmp_path / "lang.ttl"
    ttl.write_text("@prefix ex: <http://example.org/l#> .\n"
                   "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
                   'ex:z rdfs:label "Zebra"@en, "Antilope"@de, "Cebra"@es .\n'
                   'ex:u rdfs:label "Untagged", "Getaggt"@de .\n'
                   'ex:s rdfs:label "Sol"@en, "Sol"@la .\n', encoding="utf-8")
    en = _by_local(build(ttl, lang="en"))
    assert en["z"]["label"] == "Zebra" and en["z"]["alt"] == ["Antilope", "Cebra"]
    assert en["u"]["label"] == "Untagged" and en["u"]["alt"] == ["Getaggt"]
    assert en["s"]["label"] == "Sol" and en["s"]["alt"] == []
    de = _by_local(build(ttl, lang="de"))
    assert de["z"]["label"] == "Antilope" and de["u"]["label"] == "Getaggt"
    none = _by_local(build(ttl))
    assert none["u"]["label"] == "Untagged" and none["z"]["label"] == "Antilope"


def test_losing_definition_literals_stay_on_the_card(tmp_path):
    ttl = tmp_path / "def.ttl"
    ttl.write_text("@prefix ex: <http://example.org/d#> .\n"
                   "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
                   "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n"
                   'ex:a skos:definition "Def." ; rdfs:comment "Comment." .\n', encoding="utf-8")
    a = _by_local(build(ttl))["a"]
    assert a["definition"] == "Def." and a["props"] == {"comment": ["Comment."]}


def test_a_losing_definition_with_the_same_text_is_still_kept(tmp_path):
    ttl = tmp_path / "same.ttl"
    ttl.write_text("@prefix ex: <http://example.org/d#> .\n"
                   "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
                   "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n"
                   'ex:a skos:definition "Same." ; rdfs:comment "Same." .\n', encoding="utf-8")
    a = _by_local(build(ttl))["a"]
    assert a["definition"] == "Same." and a["props"] == {"comment": ["Same."]}


def test_literal_sources_go_to_properties_not_the_sources_list(tmp_path):
    ttl = tmp_path / "src.ttl"
    ttl.write_text("@prefix ex: <http://example.org/s#> .\n"
                   "@prefix dcterms: <http://purl.org/dc/terms/> .\n"
                   "@prefix prov: <http://www.w3.org/ns/prov#> .\n"
                   'ex:a dcterms:source "NASA fact sheets, 2020/21" ; prov:wasDerivedFrom ex:src .\n',
                   encoding="utf-8")
    a = _by_local(build(ttl))["a"]
    assert a["sources"] == [{"label": "src", "url": None}]
    assert a["props"] == {"source": ["NASA fact sheets, 2020/21"]}


def test_empty_default_prefix_is_a_bound_namespace(tmp_path):
    ttl = tmp_path / "default.ttl"
    ttl.write_text("@prefix : <http://example.org/default#> .\n:a :p :b .\n", encoding="utf-8")
    data = build(ttl, color_by="namespace")
    assert data["groups"] == [":"] and {n["ns"] for n in data["nodes"]} == {":"}


def test_inverse_pairs_collapse_into_one_bidirectional_link(tmp_path):
    ttl = tmp_path / "inv.ttl"
    ttl.write_text("@prefix ex: <http://example.org/i#> .\n"
                   "ex:earth ex:hasMoon ex:luna .\nex:luna ex:orbits ex:earth .\n", encoding="utf-8")
    data = build(ttl)
    assert len(data["links"]) == 1
    link = data["links"][0]
    assert link["source"].endswith("#earth") and link["target"].endswith("#luna")
    assert link["predicates"] == ["hasMoon"] and link["reverse"] == ["orbits"]


def test_a_link_only_asserted_backwards_still_points_forwards(tmp_path):
    ttl = tmp_path / "back.ttl"
    ttl.write_text("@prefix ex: <http://example.org/i#> .\nex:zeta ex:p ex:alpha .\n", encoding="utf-8")
    link = build(ttl)["links"][0]
    assert link["source"].endswith("#zeta") and link["predicates"] == ["p"] and link["reverse"] == []


def test_one_way_links_have_an_empty_reverse_list(library):
    assert all(l["reverse"] == [] for l in build(library)["links"])


def test_demo_has_no_stacked_inverse_links():
    data = graph.build(load.load_files([REPO / "examples" / "solar-system.ttl",
                                        REPO / "examples" / "solar-system-missions.ttl"]))
    pairs = {(l["source"], l["target"]) for l in data["links"]}
    assert not any((t, s) in pairs for s, t in pairs)
    assert sum(1 for l in data["links"] if l["reverse"]) == 12


def test_type_links_connect_instances_to_their_classes(library):
    data = build(library, type_links=True)
    assert ("Herbert", "type", "Author") in edges(data)
    assert ("Book", "type", "Class") not in edges(data)      # owl:Class is reserved vocabulary


def test_attribute_preds_demote_a_relation_to_the_card(tmp_path):
    ttl = tmp_path / "attr.ttl"
    ttl.write_text("@prefix ex: <http://example.org/a#> .\n"
                   "@prefix foaf: <http://xmlns.com/foaf/0.1/> .\n"
                   "ex:alice foaf:homepage <https://alice.example/> ; ex:knows ex:bob .\n",
                   encoding="utf-8")
    ds = load.load_files([ttl])
    data = graph.build(ds, attribute_preds=graph.resolve_terms(["foaf:homepage"], ds))
    assert [l["predicates"] for l in data["links"]] == [["knows"]]
    assert not any(n["id"].startswith("https://alice.example") for n in data["nodes"])


def test_resolve_terms_expands_curies_and_rejects_unknown_prefixes(library):
    ds = load.load_files([library])
    assert graph.resolve_terms(["ex:wrote", "http://example.org/x#p"], ds) == {
        URIRef("http://example.org/library#wrote"), URIRef("http://example.org/x#p")}
    with pytest.raises(ValueError):
        graph.resolve_terms(["nope:thing"], ds)


def test_resolve_terms_accepts_angle_bracketed_iris_without_a_scheme_separator(library):
    ds = load.load_files([library])
    assert graph.resolve_terms(["<urn:isbn:0451450523>", "<mailto:x@example.org>"], ds) == {
        URIRef("urn:isbn:0451450523"), URIRef("mailto:x@example.org")}
    with pytest.raises(ValueError) as e:
        graph.resolve_terms(["urn:isbn:0451450523"], ds)
    assert "<urn:isbn:0451450523>" in str(e.value)


def test_iri_valued_attribute_predicates_show_on_the_card(tmp_path):
    ttl = tmp_path / "iri.ttl"
    ttl.write_text("@prefix ex: <http://example.org/c#> .\n"
                   "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
                   "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
                   'ex:onto rdfs:label "The onto" .\n'
                   "ex:a rdfs:isDefinedBy ex:onto ; owl:priorVersion <http://example.org/c/v1> ; ex:p ex:b .\n",
                   encoding="utf-8")
    a = _by_local(build(ttl))["a"]
    assert a["props"] == {"isDefinedBy": ["The onto"], "priorVersion": ["http://example.org/c/v1"]}
    assert [l["predicates"] for l in build(ttl)["links"]] == [["p"]]


def test_a_link_asserted_by_two_files_lists_both(tmp_path):
    for name in ("first", "second"):
        (tmp_path / f"{name}.ttl").write_text(
            "@prefix ex: <http://example.org/f#> .\nex:a ex:p ex:b .\n", encoding="utf-8")
    data = build(tmp_path / "first.ttl", tmp_path / "second.ttl")
    assert data["links"][0]["files"] == ["first", "second"] and data["links"][0]["group"] == "first"


def test_a_bound_prefix_shortens_urn_namespaces_for_groups_and_labels(tmp_path):
    ttl = tmp_path / "urn.ttl"
    ttl.write_text("@prefix g: <urn:graphs:> .\ng:a g:p g:b .\n", encoding="utf-8")
    data = build(ttl, color_by="namespace")
    assert data["groups"] == ["g"] and {n["ns"] for n in data["nodes"]} == {"g"}
    assert sorted(n["label"] for n in data["nodes"]) == ["a", "b"]           # local names, not the whole URN
    assert data["links"][0]["predicates"] == ["p"]


def test_a_named_graph_owns_its_nodes_and_edges_like_a_file(library_trig):
    data = build(library_trig)
    assert data["groups"] == [":catalogue", "ex:extra", "library"]
    assert node(data, "Book")["file"] == "library"                 # declared in the default graph
    # the repeated "Dune" label in ex:extra does not steal the node from :catalogue
    assert node(data, "Dune")["file"] == ":catalogue"
    assert node(data, "Asimov")["file"] == "ex:extra"
    link = next(l for l in data["links"] if l["predicates"] == ["relatedTo"])
    assert link["files"] == ["ex:extra"] and link["group"] == "ex:extra"
    assert len(data["nodes"]) == 12 and len(data["links"]) == 6    # the same picture as the two Turtle files


def test_type_and_namespace_colouring_ignore_the_graph_split(library, library_extra, library_trig):
    for color_by in ("type", "namespace"):
        assert build(library_trig, color_by=color_by)["groups"] == build(library, library_extra,
                                                                          color_by=color_by)["groups"]


def test_an_nquads_graph_without_a_prefix_is_grouped_under_its_full_iri(tiny_nq):
    data = build(tiny_nq)
    assert data["groups"] == ["http://example.org/nt#G", "tiny"]
    assert {n["file"] for n in data["nodes"]} == {"tiny", "http://example.org/nt#G"}


def test_a_source_with_several_identifier_urls_shows_the_smallest_whatever_the_hash_seed(tmp_path):
    ttl = tmp_path / "ids.ttl"
    ttl.write_text(
        "@prefix ex: <http://example.org/i#> .\n@prefix dcterms: <http://purl.org/dc/terms/> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "ex:src dcterms:identifier <http://b.example/two>, <http://a.example/one> ; rdfs:label \"src\" .\n"
        "ex:n dcterms:source ex:src ; ex:p ex:m .\n", encoding="utf-8")
    code = ("import sys\nfrom ttl3d import graph, load\n"
            "data = graph.build(load.load_files([sys.argv[1]]))\n"
            "print(next(n for n in data['nodes'] if n['id'].endswith('#n'))['sources'][0]['url'])\n")
    urls = {subprocess.run([sys.executable, "-c", code, str(ttl)], capture_output=True, text=True, cwd=REPO,
                           check=False, env={**os.environ, "PYTHONHASHSEED": seed}).stdout.strip()
            for seed in ("1", "2", "3")}
    assert urls == {"http://a.example/one"}


def test_build_returns_the_graph_iri_behind_each_named_graph_key(library_trig, library):
    assert build(library_trig)["graphs"] == {":catalogue": "http://example.org/graphs/catalogue",
                                             "ex:extra": "http://example.org/library#extra"}
    assert build(library)["graphs"] == {}                          # plain files: no named graphs
