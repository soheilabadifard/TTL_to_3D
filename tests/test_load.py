"""ttl3d.load: parse one or more RDF files, keeping which file said what."""
import pytest
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
        p.write_text(library.read_text())
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
