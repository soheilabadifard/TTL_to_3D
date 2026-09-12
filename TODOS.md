# TODOS

## Open

- **Inputs after the Python API** (ranked 2026-09-11; each is its own spec and plan):
  1. Slicing a big graph at build time (a focus IRI with a hop count, schema-only): what makes a
     knowledge graph of millions of triples drawable. Medium; pairs with 2.
  2. SPARQL endpoint input (a CONSTRUCT query rendered directly): build time only, never in the
     page; needs authentication, timeouts and a stubbed endpoint in tests. Medium.
  3. CSV edge lists and property graphs: a column-to-RDF mapping language of its own; last.
- **Follow-ups from the 0.4.0 engineering review** (2026-09-12; small, independent of the list above):
  - A TriG page on the demo site: `examples/solar-system.trig` wrapping the planets and the missions
    in two named graphs, one `pages.yml` line, one index.html entry, so visitors see named graphs as
    legend rows. Watch `tests/test_graph.py`'s 48-links/12-two-way assertion, which pins the Turtle
    demo; the TriG twin needs its own numbers or a shared source.
  - The graph IRI on the node card: `Dataset.named` (key -> IRI) exists for this; put `{key: iri}`
    into the page CONFIG (additive) and show the IRI as a tooltip or second line of the `source`
    row in `viewer.js` `showNode`. A key like `ex:g~2` is a display label; the IRI is what a user
    pastes into `GRAPH <...>`.
  - A legend row for every source: today a file or graph made of annotations only (labels, repeated
    edges) owns nothing and gets no row, and `applyFilter` reads `l.group` (the first asserter) only,
    although the README promises "the endpoints of every edge it asserts". Add every key of
    `Dataset.graphs` to the groups in `file` mode and let the filter honour `l.files`; decide how a
    literal-only source should look when selected. graph.build plus viewer.js plus browser tests.

## Completed

- Named-graph formats (TriG, N-Quads) and reading from standard input, items 1 and 4 of the
  2026-09-11 input list: shipped in 0.4.0 (branch `named-graphs`).
- Follow-ups from the 2026-09-10 final review of the 2D view: the pinned-page cooldown (the 2D canvas idled only after force-graph's 15 s cooldown), browser tests in CI, the last test reads and writes without `encoding="utf-8"`, and the README saying twice that the stress layout runs twice.
- The idle-redraw follow-up raised in the 2026-09-09 plan review was folded into the 2D view itself (`ttl3d/viewer-2d.js`, `restyle2d`/`relabel2d`).
