"""ttl3d.load: parse one or more RDF files, keeping which file said what."""
import pytest
from rdflib import Graph, Namespace, URIRef

from ttl3d import load


def test_single_file_loads_all_triples(library):
    ds = load.load_files([library])
    assert ds.stems == ["library"]
    assert len(ds.merged) == len(ds.graphs["library"]) > 0


def test_two_files_merge_but_keep_per_file_graphs(library, library_extra):
    ds = load.load_files([library, library_extra])
    assert ds.stems == ["library", "library-extra"]
    # the repeated "Dune" label is one triple in the merged graph
    assert len(ds.merged) == len(ds.graphs["library"]) + len(ds.graphs["library-extra"]) - 1


def test_format_guessed_from_extension(tiny_nt):
    ds = load.load_files([tiny_nt])
    assert len(ds.merged) == 2


def test_same_stem_in_two_directories_gets_distinct_keys(tmp_path, library):
    a = tmp_path / "a" / "graph.ttl"
    b = tmp_path / "b" / "graph.ttl"
    for p in (a, b):
        p.parent.mkdir()
        p.write_text(library.read_text(encoding="utf-8"), encoding="utf-8")
    ds = load.load_files([a, b])
    assert len(ds.stems) == 2 and len(set(ds.stems)) == 2


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load.load_files([tmp_path / "nope.ttl"])


def test_namespace_prefixes_collected(library):
    ds = load.load_files([library])
    assert ds.prefixes["http://example.org/library#"] == "ex"


def test_malformed_file_raises_load_error_naming_the_file(tmp_path):
    bad = tmp_path / "bad.ttl"
    bad.write_text("this is not turtle @@@\n", encoding="utf-8")
    with pytest.raises(load.LoadError) as e:
        load.load_files([bad])
    assert "bad.ttl" in str(e.value)
    assert "\n" not in str(e.value)


def test_turtle_saved_with_an_owl_extension_still_loads(tmp_path, library):
    owl = tmp_path / "onto.owl"
    owl.write_text(library.read_text(encoding="utf-8"), encoding="utf-8")
    assert len(load.load_files([owl]).merged) == len(load.load_files([library]).merged)


def test_explicit_format_wins_over_the_extension(tmp_path, library):
    weird = tmp_path / "data.txt"
    weird.write_text(library.read_text(encoding="utf-8"), encoding="utf-8")
    assert len(load.load_files([weird], fmt="turtle").merged) > 0
    with pytest.raises(load.LoadError) as e:
        load.load_files([weird], fmt="xml")
    assert "as xml" in str(e.value)


EX = Namespace("http://example.org/mem#")


def _mem_graph():
    g = Graph()
    g.bind("mem", EX)
    g.add((EX.a, EX.p, EX.b))
    return g


def test_a_graph_in_memory_is_a_source_named_graph():
    ds = load.load(_mem_graph())
    assert ds.stems == ["graph"] and len(ds.merged) == 1 and ds.files == []


def test_a_named_pair_names_a_graph_or_a_path(library):
    ds = load.load([("planets", _mem_graph()), ("books", library)])
    assert ds.stems == ["planets", "books"]
    assert ds.files == [library]                       # only real paths are listed


def test_paths_and_graphs_mix_and_duplicate_names_get_suffixes(library):
    g = _mem_graph()
    ds = load.load([library, ("library", g), g, g])
    assert ds.stems == ["library", "library~2", "graph", "graph~2"]


def test_a_graph_source_is_used_as_is_and_its_prefixes_are_collected():
    g = _mem_graph()
    ds = load.load(("mem", g))                         # a top-level tuple is one named source
    assert ds.graphs["mem"] is g
    assert ds.prefixes[str(EX)] == "mem"


def test_a_single_path_needs_no_list(library):
    assert load.load(str(library)).stems == ["library"]


def test_a_source_of_another_type_raises_type_error_naming_the_type():
    with pytest.raises(TypeError, match="rdflib.Graph.*not int"):
        load.load([42])
    with pytest.raises(TypeError, match="rdflib.Graph.*not int"):
        load.load(42)                                      # at the top level too, not "int is not iterable"
    with pytest.raises(TypeError, match="pair"):
        load.load(("a", "b", "c"))


def test_load_files_is_load(library):
    assert load.load_files([library]).stems == load.load([library]).stems == ["library"]


def test_a_mapping_names_its_sources_in_order(library):
    ds = load.load({"planets": _mem_graph(), "books": library})
    assert ds.stems == ["planets", "books"]


def test_a_pair_or_mapping_key_that_is_not_a_str_raises_type_error():
    with pytest.raises(TypeError, match="pair"):
        load.load((1, _mem_graph()))
    with pytest.raises(TypeError, match="pair"):
        load.load({1: _mem_graph()})


def test_split_iri_cuts_at_the_last_hash_or_slash_when_that_namespace_is_bound_or_nothing_is():
    p = {"http://example.org/g#": "ex"}
    assert load.split_iri("http://example.org/g#Book", p) == ("http://example.org/g#", "Book")
    assert load.split_iri("http://example.org/g/Book", {}) == ("http://example.org/g/", "Book")
    assert load.split_iri("urn:x:y", {}) == ("", "urn:x:y")                    # no separator, nothing bound
    assert load.split_iri("http://example.org/g/", p) == ("http://example.org/g/", "")   # empty local part


def test_split_iri_falls_back_to_the_longest_bound_namespace_the_iri_extends():
    # the cut namespace http://example.org/ is unbound here, so rule 2 applies and the longest match wins
    p = {"urn:graphs:": "g", "http://example.org/g-": "ex", "http://example.org/g": "short"}
    assert load.split_iri("urn:graphs:planets", p) == ("urn:graphs:", "planets")
    assert load.split_iri("http://example.org/g-Book", p) == ("http://example.org/g-", "Book")
    assert load.split_iri("urn:graphs:", p) == ("", "urn:graphs:")


def test_a_bound_cut_namespace_wins_over_a_shorter_bound_one():
    p = {"http://example.org/": "root", "http://example.org/lib#": "ex"}
    assert load.split_iri("http://example.org/lib#Book", p) == ("http://example.org/lib#", "Book")
    assert load.local("http://example.org/lib#Book", p) == "Book"
    assert load.namespace_of("http://example.org/lib#Book", p) == "http://example.org/lib#"


def test_local_and_namespace_of_keep_their_old_results_without_prefixes():
    assert load.local("http://e/a#b") == "b" and load.namespace_of("http://e/a#b") == "http://e/a#"
    assert load.local("http://e/a/") == "http://e/a/"  # empty local part is the IRI itself
    assert load.local("urn:x") == "urn:x" and load.namespace_of("urn:x") == ""


def test_a_trig_file_keys_its_default_graph_by_stem_and_each_named_graph_by_prefixed_iri(library_trig):
    ds = load.load_files([library_trig])
    assert ds.stems == ["library", ":catalogue", "ex:extra"]     # default graph first, then sorted by key
    assert ds.sources == ["library"]
    assert ds.named == {":catalogue": URIRef("http://example.org/graphs/catalogue"),
                        "ex:extra": URIRef("http://example.org/library#extra")}
    assert sum(len(g) for g in ds.graphs.values()) == 38          # every quad of the file survives
    assert len(ds.merged) == 37                                  # "Dune" is labelled in two graphs
    assert ds.files == [library_trig]


def test_an_nquads_blank_node_graph_joins_the_stem_and_an_unbound_graph_iri_stays_whole(tiny_nq):
    ds = load.load_files([tiny_nq])
    assert ds.stems == ["tiny", "http://example.org/nt#G"]
    assert len(ds.graphs["tiny"]) == 2 and len(ds.graphs["http://example.org/nt#G"]) == 1
    assert ds.named == {"http://example.org/nt#G": URIRef("http://example.org/nt#G")}


def test_a_quad_file_with_an_empty_default_graph_has_no_stem_key_but_keeps_its_source_name(tmp_path):
    trig = tmp_path / "only.trig"
    trig.write_text("@prefix ex: <http://example.org/o#> .\nex:g { ex:a ex:p ex:b . }\n", encoding="utf-8")
    ds = load.load_files([trig])
    assert ds.stems == ["ex:g"] and ds.sources == ["only"]


def test_an_empty_turtle_file_still_has_its_one_key(tmp_path):
    empty = tmp_path / "empty.ttl"
    empty.write_text("", encoding="utf-8")
    assert load.load_files([empty]).stems == ["empty"]


def test_plain_files_and_graph_sources_carry_no_named_graphs(library):
    ds = load.load([library, ("mem", _mem_graph())])
    assert ds.named == {} and ds.sources == ["library", "mem"]
