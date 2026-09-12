# Changelog

## Unreleased

Nothing yet.

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
