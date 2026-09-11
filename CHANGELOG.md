# Changelog

## Unreleased

Fixes: a page written on Windows uses LF newlines, so the same input gives the
same bytes on every platform (CI now builds the demo on Linux, Windows and
macOS and compares them; only the pinned coordinates may drift by a few
tenths); `-o` refuses an input file even when only the letter case differs;
the summary line survives a console that cannot encode the output path. CI
also runs the suite on macOS and the browser tests on Firefox and WebKit.

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
