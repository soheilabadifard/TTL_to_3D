# TODOS

## Open

- **Inputs after the Python API** (ranked 2026-09-11; each is its own spec and plan):
  1. Slicing a big graph at build time (a focus IRI with a hop count, schema-only): what makes a
     knowledge graph of millions of triples drawable. Medium; pairs with 2.
  2. SPARQL endpoint input (a CONSTRUCT query rendered directly): build time only, never in the
     page; needs authentication, timeouts and a stubbed endpoint in tests. Medium.
  3. CSV edge lists and property graphs: a column-to-RDF mapping language of its own; last.

## Completed

- The three follow-ups of the 0.4.0 engineering review, shipped in 0.5.0: the Solar System as one TriG
  dataset on the demo site, the graph IRI on the node card and as legend hover text, and a legend row for
  every source with the filter honouring every asserting source.
- Named-graph formats (TriG, N-Quads) and reading from standard input, items 1 and 4 of the
  2026-09-11 input list: shipped in 0.4.0 (branch `named-graphs`).
- Follow-ups from the 2026-09-10 final review of the 2D view: the pinned-page cooldown (the 2D canvas idled only after force-graph's 15 s cooldown), browser tests in CI, the last test reads and writes without `encoding="utf-8"`, and the README saying twice that the stress layout runs twice.
- The idle-redraw follow-up raised in the 2026-09-09 plan review was folded into the 2D view itself (`ttl3d/viewer-2d.js`, `restyle2d`/`relabel2d`).
