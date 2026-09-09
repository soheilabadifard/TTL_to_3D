# Changelog

## Unreleased

Fixes: the pinned layout is reproducible run to run; header-only files and
reflexive triples no longer crash the layout; `-o` refuses to overwrite an
input; missing, malformed and unwritable paths give a one-line error instead
of a traceback; labels containing `<!--`, `</script>` or placeholder-like
tokens and titles containing `</script>` can no longer blank the page; output
is always UTF-8; islands get their own stress layout and never overlap; the
empty default prefix colours as `:`; literal `dcterms:source` values stay on
the card as properties.

Features: `--lang`, `--format`, `--type-links`, `--attribute-preds`; inverse
edge pairs merge into one two-way link; only the eleven largest groups keep a
colour past twelve; IRI-valued attributes and the files asserting each
relation show on the card; the viewer's CSS/JS live in `viewer.css` /
`viewer.js`; optional Playwright smoke test; CI covers Python 3.13, Windows
and an installed wheel.

## 0.1.0 (2026-09-08)

Initial release: command line tool, colouring by file / type / namespace,
pinned 3D stress layout with a live-force fallback for large graphs, label
thresholds, per-node detail cards, inclusive legend filter, label search, and
fully self-contained HTML output.
