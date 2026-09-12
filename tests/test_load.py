"""ttl3d.load: parse one or more RDF files, keeping which file said what."""
import pytest
from rdflib import Graph, Namespace

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
