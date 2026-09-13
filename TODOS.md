# TODOS

## Open

- **Inputs after the Python API** (ranked 2026-09-11; each is its own spec and plan):
  1. SPARQL endpoint input (a CONSTRUCT query rendered directly): build time only, never in the
     page; needs authentication, timeouts and a stubbed endpoint in tests. A CONSTRUCT result feeds
     the same `slice.select` as a file does, and is the way to avoid parsing a million triples for a
     forty-node picture. Medium.
  2. CSV edge lists and property graphs: a column-to-RDF mapping language of its own; last.
  3. An optional faster parser: use pyoxigraph through oxrdflib when installed (`pip install
     ttl3d[fast]`), falling back to rdflib's parser. The parse is the floor after slicing (about 13 s
     and 2.3 GB per million triples here); gate it on `importlib.util.find_spec("oxrdflib")` in
     `load._parsed`, keep the identity tests green on both stores, add a CI leg with the extra.
  4. Write the slice out as RDF: `--write-slice PATH` (and an API function) serialising the sliced
     Dataset as TriG, one named graph per source, so a neighbourhood or schema can be loaded into a
     store or shared. The blank-node closure makes the slice a true subset; decide the graph name for
     a file's default graph and keep the serialisation order deterministic.

## Completed

- Slicing a big graph at build time (`--focus`/`--hops`, `--schema`), item 1 of the 2026-09-11 input
  list: shipped in 0.6.0 (branch `slicing`).
- The three follow-ups of the 0.4.0 engineering review, shipped in 0.5.0: the Solar System as one TriG
  dataset on the demo site, the graph IRI on the node card and as legend hover text, and a legend row for
  every source with the filter honouring every asserting source.
- Named-graph formats (TriG, N-Quads) and reading from standard input, items 1 and 4 of the
  2026-09-11 input list: shipped in 0.4.0 (branch `named-graphs`).
- Follow-ups from the 2026-09-10 final review of the 2D view: the pinned-page cooldown (the 2D canvas idled only after force-graph's 15 s cooldown), browser tests in CI, the last test reads and writes without `encoding="utf-8"`, and the README saying twice that the stress layout runs twice.
- The idle-redraw follow-up raised in the 2026-09-09 plan review was folded into the 2D view itself (`ttl3d/viewer-2d.js`, `restyle2d`/`relabel2d`).
