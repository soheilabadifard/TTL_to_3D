"""ttl3d.load: parse one or more RDF files, keeping which file said what."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from rdflib import Graph, Namespace, URIRef

from ttl3d import graph, load

REPO = Path(__file__).resolve().parents[1]


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


def test_a_hierarchical_iri_under_a_bound_base_keeps_its_slash_cut():
    p = {"http://example.org/": "ex"}
    assert load.split_iri("http://example.org/data/x", p) == ("http://example.org/data/", "x")
    assert load.local("http://example.org/data/x", p) == "x"                # not "data/x"
    assert load.split_iri("http://example.org/x", p) == ("http://example.org/", "x")   # rule 1: bound cut


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


def test_a_plain_file_keeps_the_parsed_default_graph_instead_of_copying_it(library):
    ds = load.load_files([library])
    # type(...) is Graph holds for a context graph too on this rdflib version, so it can't
    # tell a copy from the original; the no-copy property is what the final review measured.
    assert len(ds.graphs["library"]) == len(ds.merged) > 0


def test_blank_node_graphs_are_folded_into_a_fresh_default_graph(tiny_nq):
    ds = load.load_files([tiny_nq])
    assert len(ds.graphs["tiny"]) == 2                    # default triple + the blank-node graph's triple
    assert type(ds.graphs["tiny"]) is Graph               # a fresh Graph, since folding had to copy


def test_the_same_graph_iri_in_two_files_is_one_key_holding_the_union(tmp_path):
    for name, subj in (("a", "ex:x"), ("b", "ex:y")):
        (tmp_path / f"{name}.trig").write_text(
            f"@prefix ex: <http://example.org/s#> .\nex:shared {{ {subj} ex:p ex:z . }}\n", encoding="utf-8")
    ds = load.load_files([tmp_path / "a.trig", tmp_path / "b.trig"])
    assert ds.stems == ["ex:shared"] and ds.sources == ["a", "b"]   # empty default graphs add no key
    assert len(ds.graphs["ex:shared"]) == 2
    assert ds.named == {"ex:shared": URIRef("http://example.org/s#shared")}


def test_a_prefix_bound_by_a_later_file_shortens_an_earlier_graph_name(tmp_path):
    (tmp_path / "first.trig").write_text(
        "<http://example.org/g/one> { <http://example.org/g/a> <http://example.org/g/p> "
        "<http://example.org/g/b> . }\n", encoding="utf-8")
    trig_text = "@prefix g: <http://example.org/g/> .\ng:c g:p g:d .\n"
    (tmp_path / "second.ttl").write_text(trig_text, encoding="utf-8")
    assert load.load_files([tmp_path / "first.trig", tmp_path / "second.ttl"]).stems == ["g:one", "second"]


def test_two_graph_iris_that_shorten_alike_get_distinct_keys(tmp_path):
    # both files bind ex: to a different namespace; first binding wins, so both graphs read ex:g
    for name in ("a", "b"):
        (tmp_path / f"{name}.trig").write_text(
            f"@prefix ex: <http://example.org/{name}#> .\nex:g {{ ex:s ex:p ex:o . }}\n", encoding="utf-8")
    ds = load.load_files([tmp_path / "a.trig", tmp_path / "b.trig"])
    assert ds.stems == ["ex:g", "ex:g~2"]
    assert ds.named == {"ex:g": URIRef("http://example.org/a#g"), "ex:g~2": URIRef("http://example.org/b#g")}


def test_two_alike_graph_iris_in_one_source_are_ordered_by_iri_not_hash_order(tmp_path):
    # file A binds p: to one namespace, file B binds p: to another and holds a graph in each, so
    # both of B's graphs shorten to p:g; the (curie, IRI) sort decides which one is p:g
    (tmp_path / "a.ttl").write_text("@prefix p: <http://x/1#> .\np:s p:q p:o .\n", encoding="utf-8")
    (tmp_path / "b.trig").write_text("@prefix p: <http://x/2#> .\n"
                                     "<http://x/2#g> { p:a p:q p:b . }\n<http://x/1#g> { p:c p:q p:d . }\n",
                                     encoding="utf-8")
    ds = load.load_files([tmp_path / "a.ttl", tmp_path / "b.trig"])
    assert ds.stems == ["a", "p:g", "p:g~2"]
    assert ds.named == {"p:g": URIRef("http://x/1#g"), "p:g~2": URIRef("http://x/2#g")}


def test_a_source_name_and_a_graph_key_that_collide_get_a_suffix_whichever_comes_second(tmp_path):
    trig = tmp_path / "a.trig"
    trig.write_text("@prefix ex: <http://example.org/a#> .\nex:g { ex:s ex:p ex:o . }\n", encoding="utf-8")
    graph_then_source = load.load([trig, ("ex:g", _mem_graph())])
    assert graph_then_source.stems == ["ex:g", "ex:g~2"] and list(graph_then_source.named) == ["ex:g"]
    source_then_graph = load.load([("ex:g", _mem_graph()), trig])
    assert source_then_graph.stems == ["ex:g", "ex:g~2"] and list(source_then_graph.named) == ["ex:g~2"]


def test_the_same_graph_iri_still_merges_after_its_key_got_a_suffix(tmp_path):
    for name in ("a", "c"):
        (tmp_path / f"{name}.trig").write_text(
            f"@prefix ex: <http://example.org/a#> .\nex:g {{ ex:{name} ex:p ex:o . }}\n", encoding="utf-8")
    ds = load.load([("ex:g", _mem_graph()), tmp_path / "a.trig", tmp_path / "c.trig"])
    # not ex:g~3: identity is the IRI, not the key
    assert ds.stems == ["ex:g", "ex:g~2"]
    assert len(ds.graphs["ex:g~2"]) == 2
    assert ds.named == {"ex:g~2": URIRef("http://example.org/a#g")}


def test_a_graph_iri_with_an_empty_local_part_keeps_its_full_iri_as_key(tmp_path):
    trig = tmp_path / "root.trig"
    trig.write_text("@prefix : <http://example.org/graphs/> .\n@prefix h: <http://example.org/h#> .\n"
                    "<http://example.org/graphs/> { :a :p :b . }\n"
                    "<http://example.org/h#> { h:a h:p h:b . }\n", encoding="utf-8")
    stems = load.load_files([trig]).stems
    assert stems == ["http://example.org/graphs/", "http://example.org/h#"]


def test_a_graph_named_by_a_urn_shortens_through_its_bound_prefix(tmp_path):
    trig = tmp_path / "u.trig"
    trig.write_text("@prefix g: <urn:graphs:> .\n@prefix ex: <http://example.org/u#> .\n"
                    "g:planets { ex:a ex:p ex:b . }\n", encoding="utf-8")
    assert load.load_files([trig]).stems == ["g:planets"]


def test_an_rdflib_dataset_is_a_source_whose_named_graphs_expand(library_trig):
    rds = load.parse_data(library_trig.read_bytes(), "trig")
    bare = load.load(rds)
    assert bare.stems == ["dataset", ":catalogue", "ex:extra"] and bare.sources == ["dataset"]
    paired = load.load(("lib", rds))
    assert paired.stems == ["lib", ":catalogue", "ex:extra"] and len(paired.merged) == 37
    assert paired.files == []


def test_parse_data_parses_bytes_as_the_given_format_and_names_the_source_in_errors(tiny_nq):
    rds = load.parse_data(tiny_nq.read_bytes(), "nquads", "stdin")
    assert load.load(("stdin", rds)).stems == ["stdin", "http://example.org/nt#G"]
    turtle_by_default = load.parse_data(b"<http://e/a> <http://e/p> <http://e/b> .")
    assert len(load.load(turtle_by_default).merged) == 1
    with pytest.raises(load.LoadError) as e:
        load.parse_data(b"this is not turtle @@@\n", None, "stdin")
    assert str(e.value).startswith("stdin: cannot parse as turtle") and "\n" not in str(e.value)


def test_a_file_that_fails_both_its_guessed_parser_and_the_turtle_retry_names_the_guessed_one(tmp_path):
    bad = tmp_path / "bad.rdf"                                   # guessed as xml, then retried as Turtle
    bad.write_text("this is neither RDF/XML nor Turtle @@@\n", encoding="utf-8")
    with pytest.raises(load.LoadError, match=r"bad\.rdf: cannot parse as xml"):
        load.load_files([bad])


def test_json_ld_named_and_anonymous_graphs_load_like_trig(tmp_path):
    doc = tmp_path / "g.jsonld"
    doc.write_text(json.dumps({
        "@context": {"ex": "http://example.org/j#"},
        "@graph": [
            {"@id": "ex:g1", "@graph": [{"@id": "ex:a", "ex:p": {"@id": "ex:b"}}]},     # a named graph
            {"@graph": [{"@id": "ex:b", "ex:q": {"@id": "ex:c"}}]},                     # an anonymous graph
            {"@id": "ex:a", "ex:r": {"@id": "ex:c"}}]}), encoding="utf-8")              # the default graph
    ds = load.load_files([doc])
    assert ds.stems == ["g", "ex:g1"]        # rdflib parses an anonymous @graph into the default graph itself
    assert len(ds.graphs["g"]) == 2 and len(ds.graphs["ex:g1"]) == 1 and len(ds.merged) == 3
    owners = {n["id"].rsplit("#", 1)[1]: n["file"] for n in graph.build(ds)["nodes"]}
    # ex:a is declared in both: the first key wins
    assert owners == {"a": "g", "b": "g", "c": "g"}


def test_key_order_is_the_same_across_hash_seeds_and_the_loader_raises_no_deprecation_warning(library_trig):
    # the filter is armed after the imports: numpy/scipy import-time deprecations must not fail
    # this test, while a deprecated rdflib call inside load() still would (rdflib 7.6 deprecates
    # Dataset.contexts and default_context; the loader shields rdflib's own warning in parse)
    code = ("import sys, warnings\nfrom ttl3d import load\n"
            "warnings.simplefilter('error', DeprecationWarning)\n"
            "print(load.load_files([sys.argv[1]]).stems)\n")
    runs = [subprocess.run([sys.executable, "-c", code, str(library_trig)], capture_output=True, text=True,
                           cwd=REPO, check=False, env={**os.environ, "PYTHONHASHSEED": seed})
            for seed in ("1", "2")]
    for r in runs:
        assert r.returncode == 0, r.stderr
    assert runs[0].stdout == runs[1].stdout == "['library', ':catalogue', 'ex:extra']\n"
