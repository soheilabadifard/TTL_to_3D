// 2D renderer: a canvas scene from force-graph. Function declarations only
// (see viewer.js: this file is appended after the shared code and its
// functions are called from there through hoisting). The draw callbacks read
// `_dim` and the label flags on every paint; the canvas itself pauses once the
// engine is idle (the library default), so restyle2d/relabel2d only have to
// mark it dirty. Sizes are in graph units (the context arrives already
// scaled), so zooming out declutters the labels exactly like the 3D sprites.

function create2d(el) {
  let fitted = false;
  // a late fit (force layout: the engine settles seconds after load) must not
  // snap the view away from something the user is already looking at: the
  // shared pointer/wheel listener in viewer.js and focus2d mark the instance touched
  const fitOnce = () => {        // frame the picture once the engine settles, unless framed, touched or unmounted
    if (fitted || G.__touched || Graph !== G) return;
    fitted = true; G.zoomToFit(400, 40);
  };
  const G = ForceGraph()(el)
    .graphData(DATA)
    .backgroundColor('#ffffff')
    .nodeLabel(tooltip)
    .nodeRelSize(1).nodeVal(n => radius(n) ** 2)   // arrowheads and hit areas use sqrt(val) * relSize = radius
    .nodeCanvasObject(drawNode2d)
    .nodePointerAreaPaint(paintNodeArea2d)
    .linkColor(l => (l._dim ? DIM_LINK : linkColorOf(l)) + '8c')   // ~55% alpha, like linkOpacity(0.55) in 3D
    .linkWidth(1.2)
    .linkDirectionalArrowLength(l => l.reverse.length ? 0 : 4.5)
    .linkDirectionalArrowRelPos(1)
    .linkCanvasObjectMode(() => 'after')
    .linkCanvasObject(drawLinkLabel2d)
    .onNodeClick(showNode)
    .onBackgroundClick(closeDetail)
    .onEngineStop(fitOnce);
  if (!physicsBox.checked) { G.zoomToFit(0, 40); fitted = true; }   // pinned: frame the picture at once
  return G;
}

// the node's circle, shared by the visible canvas and the hit-test canvas so
// the hit area can never drift from what is drawn
function disc2d(n, ctx, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(n.x, n.y, radius(n), 0, 2 * Math.PI);
  ctx.fill();
}

function drawNode2d(n, ctx) {
  disc2d(n, ctx, n._dim ? DIM_NODE : colorOf(n));
  if (!showNodeLabels) return;
  ctx.font = '600 4.4px -apple-system, "Segoe UI", sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.fillStyle = n._dim ? DIM_LABEL : colorOf(n);
  ctx.fillText(n.label, n.x, n.y + radius(n) + 1.5);
}

// the hit area for hover, click and drag: the same circle in the lookup colour
function paintNodeArea2d(n, color, ctx) { disc2d(n, ctx, color); }

// predicate label at the middle of every edge, horizontal like the 3D sprites
function drawLinkLabel2d(l, ctx) {
  if (!showEdgeLabels) return;
  const s = l.source, t = l.target;
  ctx.font = '2.4px -apple-system, "Segoe UI", sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillStyle = l._dim ? DIM_LABEL : LINK_LABEL;
  ctx.fillText(linkText(l), (s.x + t.x) / 2, (s.y + t.y) / 2);
}

function focus2d(n) {
  Graph.__touched = true;        // the user is looking at something; no late fit
  Graph.centerAt(n.x, n.y, 900);
  Graph.zoom(Math.max(Graph.zoom(), 3), 900);
}

// after a filter or label change nothing the engine sees has changed, so the
// paused canvas must be told: re-setting any styling property runs the
// library's notifyRedraw and paints exactly one frame
function restyle2d() { Graph.nodeCanvasObject(Graph.nodeCanvasObject()); }
function relabel2d() { restyle2d(); }
