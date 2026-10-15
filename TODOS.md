# TODOS

## Open

- **Inputs after the Python API** (ranked 2026-09-11, items 4 and 5 added 2026-09-14; each is its own
  spec and plan):
  1. An optional faster parser: use pyoxigraph through oxrdflib when installed (`pip install
     ttl3d[fast]`), falling back to rdflib's parser. The parse is the floor after slicing (about 13 s
     and 2.3 GB per million triples here); gate it on `importlib.util.find_spec("oxrdflib")` in
     `load._parsed`, keep the identity tests green on both stores, add a CI leg with the extra.
  2. Write the slice out as RDF: `--write-slice PATH` (and an API function) serialising the sliced
     Dataset as TriG, one named graph per source, so a neighbourhood or schema can be loaded into a
     store or shared. The blank-node closure makes the slice a true subset; decide the graph name for
     a file's default graph and keep the serialisation order deterministic.
  3. Extra request headers for SPARQL endpoints that authenticate with an API key (`X-API-Key: ...`)
     rather than Basic or Bearer. The values are secrets, so they come from the environment (for example
     `TTL3D_SPARQL_HEADERS` as `Name: value` lines, never the command line) and are blanked from error
     messages like the password (`sparql._scrub`); `sparql.fetch` builds its headers in one place.
  4. GET as a fallback when an endpoint answers 405 to the POST: some read-only mirrors and caching
     proxies accept only GET. It bends 0.7.0's one-attempt rule and puts the query into a URL (length
     limits, server logs), so add it when an endpoint someone uses needs it.

- **Follow-ups of the tables input** (0.9.0, unranked):
  - Undirected edges: Gephi's edge `Type` column (`Directed`/`Undirected`) is an edge property today;
    an undirected row could assert both directions and draw as a two-way link.
  - Typed literals: Neo4j data types (`born:int`, `date`) are dropped and every value is text; they
    could become `xsd:` datatypes, which matters once the slice is written out as RDF.
  - Edge properties in the link hover text and edge labels, not only on the card.
  - A likely missing Neo4j ID group: when an edge endpoint without a group (`:START_ID`) matches no
    node row while a node table of the run uses ID groups (`:ID(Person)`) and has that raw id, warn
    on stderr through `notice`, naming the column. Today the two sides mint different IRIs and a
    second, unconnected copy of those nodes appears silently; Neo4j's own importer refuses such files.
    `table.to_graphs` knows every minted id and its group, so the check is a set lookup at its end.

## Completed

- Tables as sources (CSV, TSV, DataFrames) with edge properties on the card, item 1 of the 2026-09-11
  input list: shipped in 0.9.0 (branch `csv`).
- An IPv6 endpoint (`--endpoint http://[::1]:8890/sparql`) named the default output file `::1-3d.html`,
  which Windows refuses; colons in the default file name become `_` (`__1-3d.html`) while the legend
  row and title keep `::1`. Found in the 0.8.0 review, shipped in 0.8.1 (branch `ipv6-file-name`).
- SPARQL endpoint input (`--endpoint`/`--query`, `ttl3d.Query`), item 1 of the 2026-09-11 input list:
  shipped in 0.7.0 (branch `sparql`).
- Slicing a big graph at build time (`--focus`/`--hops`, `--schema`), item 1 of the 2026-09-11 input
  list: shipped in 0.6.0 (branch `slicing`).
- The three follow-ups of the 0.4.0 engineering review, shipped in 0.5.0: the Solar System as one TriG
  dataset on the demo site, the graph IRI on the node card and as legend hover text, and a legend row for
  every source with the filter honouring every asserting source.
- Named-graph formats (TriG, N-Quads) and reading from standard input, items 1 and 4 of the
  2026-09-11 input list: shipped in 0.4.0 (branch `named-graphs`).
- Follow-ups from the 2026-09-10 final review of the 2D view: the pinned-page cooldown (the 2D canvas idled only after force-graph's 15 s cooldown), browser tests in CI, the last test reads and writes without `encoding="utf-8"`, and the README saying twice that the stress layout runs twice.
- The idle-redraw follow-up raised in the 2026-09-09 plan review was folded into the 2D view itself (`ttl3d/viewer-2d.js`, `restyle2d`/`relabel2d`).
