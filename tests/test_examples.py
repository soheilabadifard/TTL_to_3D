"""The Solar System demo in TriG mirrors the two Turtle files: the same triples, split into the default
graph (the schema) and two named graphs, so the demo site shows named graphs as legend rows."""
from pathlib import Path

from rdflib import URIRef

from ttl3d import graph, load

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"
TURTLE = [EXAMPLES / "solar-system.ttl", EXAMPLES / "solar-system-missions.ttl"]
TRIG = EXAMPLES / "solar-system.trig"


def test_the_trig_demo_holds_exactly_the_triples_of_the_two_turtle_files():
    trig, turtle = load.load_files([TRIG]), load.load_files(TURTLE)
    assert set(trig.merged) == set(turtle.merged)                 # a drift guard: the twin never diverges
    assert trig.stems == ["solar-system", ":bodies", ":missions"]
    assert trig.named == {":bodies": URIRef("https://example.org/solar#bodies"),
                          ":missions": URIRef("https://example.org/solar#missions")}


def test_the_trig_demo_draws_the_same_picture_as_the_two_files():
    trig, turtle = graph.build(load.load_files([TRIG])), graph.build(load.load_files(TURTLE))
    assert {n["id"] for n in trig["nodes"]} == {n["id"] for n in turtle["nodes"]}
    edges = lambda d: {(l["source"], l["target"], tuple(l["predicates"]), tuple(l["reverse"]))
                       for l in d["links"]}
    assert edges(trig) == edges(turtle)                            # 48 links, 12 two-way, as test_graph pins
    assert trig["groups"] == [":bodies", ":missions", "solar-system"]
    owner = {n["label"]: n["file"] for n in trig["nodes"]}
    assert owner["planet"] == "solar-system" and owner["Earth"] == ":bodies"
    assert owner["Voyager 2"] == ":missions"


def test_the_demo_site_and_the_identical_pages_job_build_the_trig_page():
    pages = (REPO / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "examples/solar-system.trig" in pages and "site/solar-system-trig.html" in pages
    index = (REPO / "docs" / "demo" / "index.html").read_text(encoding="utf-8")
    assert 'href="solar-system-trig.html"' in index
    tests_yml = (REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "examples/solar-system.trig" in tests_yml       # built on three operating systems, compared
