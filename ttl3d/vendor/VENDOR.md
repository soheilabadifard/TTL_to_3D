# Vendored libraries

`fg3d-bundle.min.js` is a single esbuild IIFE bundle exposing
`window.ForceGraph3D` (3d-force-graph 1.77.0, MIT), `window.SpriteText`
(three-spritetext 1.10.0, MIT) and `window.THREE` (three.js, MIT), built over
ONE shared copy of three.js so the sprite labels and the scene use the same
version. It is inlined into every generated page, so the page is fully
self-contained: no CDN fetch, no blank page when a CDN is unreachable, and
nothing about your graph leaves your machine.

Rebuild recipe:

```bash
printf 'import ForceGraph3D from "3d-force-graph";\nimport SpriteText from "three-spritetext";\nimport * as THREE from "three";\nwindow.ForceGraph3D = ForceGraph3D;\nwindow.SpriteText = SpriteText;\nwindow.THREE = THREE;\n' > entry.js
npm install 3d-force-graph@1.77.0 three-spritetext@1.10.0
npx esbuild entry.js --bundle --minify --format=iife --outfile=fg3d-bundle.min.js
```

The viewer needs all three globals; `tests/test_bundle.py` checks them so a
rebuild that drops one fails the suite instead of breaking pages silently.

Pinned upstream versions in the shipped bundle: 3d-force-graph 1.77.0,
three-spritetext 1.10.0, three.js as resolved by those two on 2026-09-08
(the bundle's tail carries the three.js license banner with its version);
build with esbuild 0.24 or later. Copyright notices for all three libraries
are in `LICENSES.md` next to this file, as the MIT license requires.
