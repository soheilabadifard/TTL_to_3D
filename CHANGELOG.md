# Changelog

## Unreleased

Nothing yet.

## 0.8.0 (2026-10-09)

The rest of the September review: the design items it left open.

Keyboard and screen readers: Tab reaches the legend rows, which toggle with Enter or Space and say
whether they are pressed; Enter in the search box opens the card of the best match among the lit
nodes (the exact label, then labels starting with the text); Tab and Enter walk the card's relations
to the neighbours' cards, and Esc closes the card and puts the focus back in the search box. The
search box, the card and its close button carry labels, and focused controls show a ring. A card
opened with the pointer leaves the focus where it was.

Names: a type, edge label or property whose local name another one on the page shares shows as
`prefix:local` (the full IRI when its namespace has no prefix), so FOAF's classes read `owl:Class,
rdfs:Class` rather than `Class, Class` and `dc:title` no longer merges with `dcterms:title`; what the
page never names (`rdf:type` as a predicate, `rdfs:label`) clashes with nothing. Pages without such a
clash carry the same data as before; of the demo inputs only FOAF changes.

XML: rdflib's RDF/XML and TriX parsers spent about a minute of CPU on a 1 KB "billion laughs" file
or SPARQL answer before expat's own limit stopped them. Every XML input now passes through bare expat
first, which refuses it in milliseconds at about 1% of a normal load; external entities were and are
never fetched.

Errors: running out of memory is one line (`out of memory while building the page; ...`) instead of a
traceback, and no longer passes for a syntax error. A file whose guessed parser fails no longer
prints rdflib's "does not look like a valid URI" lines from the Turtle retry before its error.
Endpoint messages and the fetch line name the port when the endpoint's URL gives one
(`endpoint h.org:8890/sparql answered 500`); source names stay the bare host.

Tests: a TriX fixture loads like its N-Quads twin on rdflib 7.0 and 7.6; a sliced run picks its
layout from the slice and announces the slice before the stress layout; every test subprocess has a
timeout.

## 0.7.2 (2026-10-09)

Fixes from three code reviews. A page that built before carries the same data; only the card's
source check in the inlined viewer changed (below).

Errors: `--max-mb 1e308` and `--endpoint 'http://[bad'` were Python tracebacks and are one-line errors
now (`--max-mb is too large`; `ttl3d.Query` refuses a malformed endpoint as "the endpoint is not a
well-formed URL"). A directory, a missing file or a pipe given as input says which (`X is a directory,
not a file`, `X: no such file`, `X is not a regular file`) instead of printing the bare path; the
exception is still FileNotFoundError. A `--focus` or `--attribute-preds` term holding a character
Turtle refuses in an IRI (a space or control character, `<`, `{`, `|`, ...), or an empty term, is an
error naming it, so rdflib no longer logs a warning about it and the Python API stays silent. Terms
may have spaces around their commas (`--focus "ex:Dune, ex:Asimov"`).

SPARQL: an answer without a Content-Length is read a megabyte at a time (the read sized its buffer by
the limit, so a huge `max_bytes` failed and the default reserved 100 MB for any answer); an HTTP error
whose body timed out or broke off is still "answered 500", and the response is closed; a redirect
message has the request's credentials blanked like any other server text, and no credential stays on
the exception chain (`__context__` included, also for a header value http.client refuses).

The node card names the sources of its relations whenever more than one source owns a node or asserts
a link; a source that only adds links owns no node, so the card left them out. A `set` of sources
raises TypeError, since its order, which names the page and orders the legend, followed the hash seed.
`Page`'s repr counts UTF-8 bytes rather than characters. `tools/compare_pages.py` masks only the run of
five coordinates each pinned node carries, so no other number can be taken for layout drift, and prints
its usage on bad arguments. New tests cover `tools/licenses.py`, cyclic and shared blank nodes in a
slice, answers read in many chunks, `--max-mb inf`/`nan` and the card's source attribution in the
browser.

## 0.7.1 (2026-10-05)

Vendored bundle: force-graph 1.51.5 and three.js 0.186.1 (Dependabot #23). Pages look and
behave as before. A browser test that checked the 3D scene straight after a 2D-to-3D switch now
waits for it: the scene is rebuilt a few milliseconds later, so the test failed on fast machines.

## 0.7.0 (2026-09-14)

SPARQL endpoints as sources: `--endpoint URL --query TEXT|@FILE` (repeatable) fetches a CONSTRUCT or
DESCRIBE result with one POST at build time and treats it like a file, with its own legend row named
after the query file or the endpoint's host; `ttl3d.Query(endpoint, query, auth=, token=, timeout=,
max_bytes=)` is the same source in Python and checks itself when built. Credentials come from
`TTL3D_SPARQL_USER`/`TTL3D_SPARQL_PASSWORD` or `TTL3D_SPARQL_TOKEN`, never from the command line; an
endpoint URL carrying them is refused, `repr` never shows them, and server text quoted in an error has
them blanked. The query's PREFIX lines name the page's namespaces; the answer is parsed by its media
type (Turtle, N-Triples, RDF/XML, or a quad format folded into the query's one row) with the endpoint as
base, and a JSON-LD answer is refused, since its parser would fetch a remote @context. One-line errors
cover SELECT, ASK and updates (before anything is sent), HTTP errors, redirects (with the URL to use),
timeouts (`--timeout`, 60 s per network step), answers over `--max-mb` (100 MB) and answers that break
off midway. `load.load` gained a `notice` callback, and the CLI prints `fetched N triples from HOST in S
s`. Files become optional on the command line. Runs without a query are byte-identical to 0.6.0.
Example: `examples/wikidata-moons.rq` draws the planets and their moons (916 triples, 308 nodes) from
Wikidata in about a second. The fetch line says when credentials went out, and when over plain http; a
token must be printable ASCII without spaces (a trailing line break in a variable is dropped); a query
file may start with a byte-order mark.

## 0.6.0 (2026-09-12)

Slicing at build time, for graphs too big to draw: `--focus IRI --hops N` keeps a node's
neighbourhood over link predicates, `--schema` keeps classes and properties without instances, both
together keep the neighbourhood inside the schema, and ttl3d prints what it kept (`kept 12 of 41
nodes (focus :Earth, 2 hops)`). The same keyword arguments exist on `to_html`, `write` and `show`.
The slice runs on the RDF before the node/link model, keeps blank-node structure whole, brings each
kept node's classes along under `--type-links`, and leaves cards, legend and named-graph ownership to
the unchanged model code; an unsliced run is byte-identical to 0.5.0. On a million-triple file the
parse takes about 13 s; a two-hop slice then builds in under 1.5 s and a schema slice in under
1.5 s; the cost follows the surviving triples, not the node count.

## 0.5.0 (2026-09-12)

Every source has a legend row, including a file or named graph that only annotates other sources'
nodes (its row is muted and its hover text says why), and selecting a row keeps the endpoints of
every edge that source asserts, not only the edges it asserted first, as the README always said;
the colour ranking past twelve sources counts links the same way, and an annotation-only source
takes no colour. The node card shows the IRI behind a named-graph key under the source name, and
legend rows carry it as hover text (`DATA.graphs`, one additive key in the page). The demo site
gains the Solar System as one TriG dataset, and CI builds that page on three operating systems.

## 0.4.0 (2026-09-12)

Named graphs: TriG and N-Quads files load every graph, and each named graph is a source like a
file, with a legend row of its own named by its prefixed IRI (`ex:planets`); the file's default graph
keeps the file's name, and the same graph IRI in several files is one source. Before this a quad
format silently kept only its default graph; JSON-LD `@graph` blocks with an `@id` and TriX graphs
were lost the same way and now load too. `-` reads standard input (`--format` or Turtle), and
`ttl3d.to_html`, `write` and `show` accept an `rdflib.Dataset`. IRIs whose namespace does not end in
`/` or `#` (URNs, path fragments) now shorten through the longest bound prefix, for legend keys,
node namespaces and labels alike; pages whose namespaces were already bound are unchanged. The node
card calls the owning file or graph its "source".

Fixed: a source with several `dcterms:identifier` URLs showed one chosen in hash order; the smallest
now wins, so the page is identical across runs.

## 0.3.0 (2026-09-12)

Releases are archived on Zenodo; `CITATION.cff` and the README carry the DOI.
A merge to `main` that changes the version now tags it, publishes the GitHub
release from the changelog section and pushes the package to PyPI on its own;
the notebook and the README install `ttl3d>=0.3.0`, so an older PyPI fails
clearly instead of at first use.

A Python entry point: `ttl3d.to_html`, `ttl3d.write` and `ttl3d.show` take file paths and
in-memory rdflib graphs, named through pairs or a mapping, with the command line's options;
`show` displays the page inline in notebooks. The command line runs on the same code path.
An example notebook with an Open-in-Colab badge.

## 0.2.3 (2026-09-11)

Published on PyPI (`pip install ttl3d`) by a release workflow with trusted
publishing; a demo site (https://soheilabadifard.github.io/TTL_to_3D/) with the
Solar System, FOAF, SKOS, PROV-O and Pizza pages, rebuilt on every push to
`main`; the README shows the viewer in motion. `CITATION.cff` for citing the tool; a
tutorial page on the demo site.

## 0.2.2 (2026-09-11)

Fixes: a page written on Windows uses LF newlines, so the same input gives the
same bytes on every platform (CI now builds the demo on Linux, Windows and
macOS and compares them; only the pinned coordinates may drift by a few
tenths); `-o` refuses an input file even when only the letter case differs;
the summary line survives a console that cannot encode the output path. CI
also runs the suite on macOS and the browser tests on Firefox and WebKit. A
browser without WebGL now falls back to the 2D view with a clean console: the
page asks for a context itself before three.js can log a failed one.

## 0.2.1 (2026-09-11)

Vendored bundle: 3d-force-graph 1.80.0 and three.js 0.185.1 (Dependabot #7).
Dependabot now keeps the GitHub Actions, the Python extras and the vendored
pins current, and CI runs on the v7 actions.

## 0.2.0 (2026-09-11)

Fixes: the pinned layout is reproducible run to run; header-only files and
reflexive triples no longer crash the layout; `-o` refuses to overwrite an
input; missing, malformed and unwritable paths give a one-line error instead
of a traceback; labels containing `<!--`, `</script>` or placeholder-like
tokens and titles containing `</script>` can no longer blank the page; output
is always UTF-8; islands get their own stress layout and never overlap; the
empty default prefix colours as `:`; literal `dcterms:source` values stay on
the card as properties; blank-node sources are skipped, like every other
blank node.

Features: `--lang`, `--format`, `--type-links`, `--attribute-preds`; inverse
edge pairs merge into one two-way link; only the eleven largest groups keep a
colour past twelve; IRI-valued attributes and the files asserting each
relation show on the card; the viewer's CSS/JS live in `viewer.css` /
`viewer.js`; optional Playwright smoke test; CI covers Python 3.13, Windows
and an installed wheel. Because an inverse pair is one edge, node degree and
sphere size shrink slightly for bidirectionally-asserted nodes compared with
0.1.0.

2D: `--view 2d|3d` picks the starting view and every page has a `3D | 2D`
switch; the 2D view is a canvas renderer (force-graph) with the same filters,
search and cards, and each view is pinned to its own stress layout, so the
layout step runs twice. The vendored bundle is now `fg-bundle.min.js`,
carries force-graph next to 3d-force-graph and is rebuilt from committed exact
pins, and `LICENSES.md` now lists every package it inlines.

Follow-ups: a pinned page stops the force engine on its first tick instead of
running its 15 s cooldown, so the 2D canvas idles right after a mount or a
pin-back; CI runs the headless-browser tests in a job of their own.

## 0.1.0 (2026-09-08)

Initial release: command line tool, colouring by file / type / namespace,
pinned 3D stress layout with a live-force fallback for large graphs, label
thresholds, per-node detail cards, inclusive legend filter, label search, and
fully self-contained HTML output.
