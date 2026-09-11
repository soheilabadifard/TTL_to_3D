// 3D renderer: a WebGL scene from 3d-force-graph. Function declarations only:
// this file is appended after viewer.js and its functions are called from
// there through hoisting; a top-level const here would still be in its
// temporal dead zone when the shared code runs. See RENDERERS in viewer.js
// for the contract (create / focus / restyle / relabel / unmount).

// physically-shaded sphere + (optional) permanent label, one group per node;
// sprites are only created when labels are on, so big graphs stay light
function nodeObj3d(n) {
  const g = new THREE.Group();
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(radius(n), 28, 28),
    new THREE.MeshPhysicalMaterial({
      color: n._dim ? DIM_NODE : colorOf(n),
      roughness: 0.32, metalness: 0.1, clearcoat: 0.65, clearcoatRoughness: 0.3,
    }));
  g.add(mesh); n.__mesh = mesh; n.__sprite = null;
  if (showNodeLabels) {
    const s = new SpriteText(n.label);
    s.color = n._dim ? DIM_LABEL : colorOf(n);
    s.textHeight = 4.4; s.fontWeight = '600';
    s.position.y = radius(n) + 4.2;
    g.add(s); n.__sprite = s;
  }
  return g;
}

// predicate label at the middle of every edge (falsy = default line only)
function linkObj3d(l) {
  l.__sprite = null;
  if (!showEdgeLabels) return undefined;
  const s = new SpriteText(linkText(l));
  s.color = l._dim ? DIM_LABEL : LINK_LABEL;
  s.textHeight = 2.4;
  l.__sprite = s;
  return s;
}

function create3d(el) {
  const G = ForceGraph3D()(el)
    .graphData(DATA)
    .backgroundColor('#ffffff')
    .nodeLabel(tooltip)
    .nodeThreeObject(nodeObj3d)
    .linkColor(l => l._dim ? DIM_LINK : linkColorOf(l))
    .linkWidth(1.2)
    .linkOpacity(0.55)
    .linkDirectionalArrowLength(l => l.reverse.length ? 0 : 4.5)
    .linkDirectionalArrowRelPos(1)
    .linkThreeObjectExtend(true)
    .linkThreeObject(linkObj3d)
    .linkPositionUpdate((obj, {start, end}) => {
      if (!obj) return false;
      obj.position.set((start.x+end.x)/2, (start.y+end.y)/2, (start.z+end.z)/2);
    })
    .onNodeClick(showNode)
    .onBackgroundClick(closeDetail);
  // studio-style lighting. Deliberately NO fog: white fog faded distant nodes
  // into the white background, so parts of the graph vanished when zooming out.
  const scene = G.scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0xd9dee7, 0.85));
  const key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(150, 220, 120);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xdfe6f0, 0.35);
  fill.position.set(-140, -80, -100);
  scene.add(fill);
  return G;
}

function focus3d(n) {
  const d = Math.hypot(n.x, n.y, n.z) || 1;   // origin guard
  const ratio = 1 + 60 / d;
  Graph.cameraPosition({x:n.x*ratio, y:n.y*ratio, z:n.z*ratio}, n, 900);
}

// push `_dim` into the existing meshes and sprites
function restyle3d() {
  DATA.nodes.forEach(n => {
    if (n.__mesh) n.__mesh.material.color.set(n._dim ? DIM_NODE : colorOf(n));
    if (n.__sprite) n.__sprite.color = n._dim ? DIM_LABEL : colorOf(n);
  });
  DATA.links.forEach(l => { if (l.__sprite) l.__sprite.color = l._dim ? DIM_LABEL : LINK_LABEL; });
  Graph.linkColor(Graph.linkColor());
}

function relabel3d() { Graph.refresh(); }

// release the controls and the WebGL context so repeated switches do not pile
// up contexts (browsers keep only a handful alive)
function unmount3d() {
  Graph.controls().dispose();
  Graph.renderer().dispose();
  Graph.renderer().forceContextLoss();
  // drop our handles on the dead scene so its meshes and sprite canvases can be collected
  DATA.nodes.forEach(n => { n.__mesh = null; n.__sprite = null; });
  DATA.links.forEach(l => { l.__sprite = null; });
}
