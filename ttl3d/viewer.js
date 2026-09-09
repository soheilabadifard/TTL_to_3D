const DATA = __DATA__;
const COLORS = __COLORS__;
const CONFIG = __CONFIG__;
// a legend selection keeps the group's own nodes, their direct neighbors, and
// the endpoints of every edge the group asserts (settled behavior; a strict
// isolation variant was tried and rejected)
const INCLUSIVE_SELECTION = true;
const DIM_NODE = '#d8dce3', DIM_LABEL = '#c3c8d1', DIM_LINK = '#eceff3';
const LINK_COLOR = '#aab1bf', LINK_LABEL = '#6b7280';
let showNodeLabels = !!CONFIG.labels.node, showEdgeLabels = !!CONFIG.labels.edge;

// degree + adjacency + relation lists, computed while endpoints are string ids
const deg = {}, nbr = {}, rels = {}, byId = {};
DATA.nodes.forEach(n => byId[n.id] = n);
DATA.links.forEach(l => {
  deg[l.source] = (deg[l.source]||0)+1; deg[l.target] = (deg[l.target]||0)+1;
  (nbr[l.source] ??= new Set()).add(l.target);
  (nbr[l.target] ??= new Set()).add(l.source);
  if (l.predicates.length) {
    (rels[l.source] ??= []).push({dir:'out', pred:l.predicates.join(', '), other:l.target, files:l.files});
    (rels[l.target] ??= []).push({dir:'in',  pred:l.predicates.join(', '), other:l.source, files:l.files});
  }
  if (l.reverse.length) {
    (rels[l.target] ??= []).push({dir:'out', pred:l.reverse.join(', '), other:l.source, files:l.files});
    (rels[l.source] ??= []).push({dir:'in',  pred:l.reverse.join(', '), other:l.target, files:l.files});
  }
});
// a link asserted both ways carries both predicate lists and no arrowhead
const linkText = l => l.reverse.length
  ? `${l.predicates.join(', ')} ⇄ ${l.reverse.join(', ')}`
  : l.predicates.join(', ');
const radius = n => 5 + Math.sqrt(deg[n.id]||0) * 1.8;
const rOf = x => radius(typeof x === 'object' ? x : {id: x});
const colorOf = n => COLORS[n.group] || COLORS['?'];
const linkColorOf = l => l.group ? (COLORS[l.group] || COLORS['?']) : LINK_COLOR;
const idOf = x => typeof x === 'object' ? x.id : x;

// pinned mode: every node sits at its precomputed stress-minimized position;
// the "free-float physics" toggle releases them into the live force layout
if (CONFIG.pinned) DATA.nodes.forEach(n => {
  n.__px = n.x; n.__py = n.y; n.__pz = n.z;
  n.fx = n.x; n.fy = n.y; n.fz = n.z;
});

// physically-shaded sphere + (optional) permanent label, one group per node;
// sprites are only created when labels are on, so big graphs stay light
function nodeObj(n) {
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
function linkObj(l) {
  l.__sprite = null;
  if (!showEdgeLabels) return undefined;
  const s = new SpriteText(linkText(l));
  s.color = l._dim ? DIM_LABEL : LINK_LABEL;
  s.textHeight = 2.4;
  l.__sprite = s;
  return s;
}

const Graph = ForceGraph3D()(document.getElementById('graph'))
  .graphData(DATA)
  .backgroundColor('#ffffff')
  .nodeLabel(n => `<b>${esc(n.label)}</b><br>${esc(n.types.join(', ') || 'untyped')}<br><i>${esc(n.group)}</i>`)
  .nodeThreeObject(nodeObj)
  .linkColor(l => l._dim ? DIM_LINK : linkColorOf(l))
  .linkWidth(1.2)
  .linkOpacity(0.55)
  .linkDirectionalArrowLength(l => l.reverse.length ? 0 : 4.5)
  .linkDirectionalArrowRelPos(1)
  .linkThreeObjectExtend(true)
  .linkThreeObject(linkObj)
  .linkPositionUpdate((obj, {start, end}) => {
    if (!obj) return false;
    obj.position.set((start.x+end.x)/2, (start.y+end.y)/2, (start.z+end.z)/2);
  })
  .onNodeClick(showNode)
  .onBackgroundClick(closeDetail);

// spacing scaled to sphere size so spheres and labels do not collide
Graph.d3Force('link').distance(l => 26 + 1.6 * (rOf(l.source) + rOf(l.target)));
Graph.d3Force('charge').strength(-80);

// studio-style lighting. Deliberately NO fog: white fog faded distant nodes
// into the white background, so parts of the graph vanished when zooming out.
const scene = Graph.scene();
scene.add(new THREE.HemisphereLight(0xffffff, 0xd9dee7, 0.85));
const key = new THREE.DirectionalLight(0xffffff, 1.1);
key.position.set(150, 220, 120);
scene.add(key);
const fill = new THREE.DirectionalLight(0xdfe6f0, 0.35);
fill.position.set(-140, -80, -100);
scene.add(fill);

// --- node detail card --------------------------------------------------------
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                  .replace(/"/g,'&quot;');
}

function focusNode(n) {
  const d = Math.hypot(n.x, n.y, n.z) || 1;   // origin guard
  const ratio = 1 + 60 / d;
  Graph.cameraPosition({x:n.x*ratio, y:n.y*ratio, z:n.z*ratio}, n, 900);
}

function showNode(n) {
  focusNode(n);
  let h = `<h2><span class="dot" style="background:${colorOf(n)}"></span>${esc(n.label)}</h2>`;
  h += `<div class="cls">${esc(n.types.join(', ') || 'untyped')} · ${esc(n.group)}</div>`;
  h += `<div class="iri">${esc(n.id)}</div>`;
  if (n.definition) h += `<p class="def">${esc(n.definition)}</p>`;
  h += `<table><tr><td>file</td><td>${esc(n.file)}</td></tr>` +
       `<tr><td>namespace</td><td>${esc(n.ns)}</td></tr></table>`;
  if (n.alt && n.alt.length)
    h += `<h3>also known as</h3>` + n.alt.map(a => `<span class="chip">${esc(a)}</span>`).join('');
  const props = Object.entries(n.props || {});
  if (props.length) {
    h += `<h3>properties</h3><table>`;
    props.forEach(([k, vs]) => vs.forEach(v =>
      h += `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`));
    h += `</table>`;
  }
  const rl = rels[n.id] || [];
  const out = rl.filter(r => r.dir === 'out'), inn = rl.filter(r => r.dir === 'in');
  const manyFiles = new Set(DATA.nodes.map(n => n.file)).size > 1;
  const relRow = r => {
    const o = byId[r.other];
    const name = o ? esc(o.label) : esc(r.other);
    const files = manyFiles && r.files.length ? ` <span class="pred">[${esc(r.files.join(', '))}]</span>` : '';
    return r.dir === 'out'
      ? `<div class="rel" data-node="${esc(r.other)}"><span class="pred">${esc(r.pred)}</span> → <b>${name}</b>${files}</div>`
      : `<div class="rel" data-node="${esc(r.other)}"><b>${name}</b> <span class="pred">${esc(r.pred)}</span> →${files}</div>`;
  };
  if (out.length) h += `<h3>outgoing (${out.length})</h3>` + out.map(relRow).join('');
  if (inn.length) h += `<h3>incoming (${inn.length})</h3>` + inn.map(relRow).join('');
  if (n.sources && n.sources.length) {
    h += `<h3>sources</h3>`;
    n.sources.forEach(s => {
      h += `<div class="src">${s.url
        ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a>`
        : esc(s.label)}</div>`;
    });
  }
  document.getElementById('detail-body').innerHTML = h;
  document.getElementById('detail').classList.add('open');
  document.querySelectorAll('#detail .rel').forEach(el =>
    el.addEventListener('click', () => {
      const t = byId[el.dataset.node];
      if (t) showNode(t);
    }));
}

function closeDetail() {
  document.getElementById('detail').classList.remove('open');
}
document.getElementById('close').addEventListener('click', closeDetail);

// --- one shared filter: legend group selection AND label search -------------
const activeGroups = new Set();
let query = '';

function applyFilter() {
  const core = new Set();       // ids of nodes in the selected groups
  const edgeKeep = new Set();   // endpoints of edges the selected groups assert
  if (activeGroups.size) {
    DATA.nodes.forEach(n => { if (activeGroups.has(n.group)) core.add(n.id); });
    DATA.links.forEach(l => {
      if (l.group && activeGroups.has(l.group)) {
        edgeKeep.add(idOf(l.source)); edgeKeep.add(idOf(l.target));
      }
    });
  }
  const isKept = n => {
    if (!activeGroups.size) return true;
    if (core.has(n.id) || edgeKeep.has(n.id)) return true;
    if (INCLUSIVE_SELECTION) for (const m of (nbr[n.id] || [])) if (core.has(m)) return true;
    return false;
  };
  DATA.nodes.forEach(n => {
    const qOk = !query || n.label.toLowerCase().includes(query);
    n._dim = !(isKept(n) && qOk);
    if (n.__mesh) n.__mesh.material.color.set(n._dim ? DIM_NODE : colorOf(n));
    if (n.__sprite) n.__sprite.color = n._dim ? DIM_LABEL : colorOf(n);
  });
  DATA.links.forEach(l => {
    const grpLink = l.group && activeGroups.has(l.group);
    const touchesCore = !activeGroups.size ||
      core.has(idOf(l.source)) || core.has(idOf(l.target));
    l._dim = (l.source._dim && l.target._dim) || !(touchesCore || grpLink);
    if (l.__sprite) l.__sprite.color = l._dim ? DIM_LABEL : LINK_LABEL;
  });
  Graph.linkColor(Graph.linkColor());
  document.getElementById('panel').classList.toggle('filtered', activeGroups.size > 0);
}

document.querySelectorAll('.row.grp').forEach(row => {
  // a bucket row ("other") toggles every group it stands for
  const members = row.dataset.groups ? JSON.parse(row.dataset.groups) : [row.dataset.group];
  row.addEventListener('click', () => {
    if (members.some(g => activeGroups.has(g))) {
      members.forEach(g => activeGroups.delete(g)); row.classList.remove('active');
    } else {
      members.forEach(g => activeGroups.add(g)); row.classList.add('active');
    }
    applyFilter();
  });
});

document.getElementById('q').addEventListener('input', e => {
  query = e.target.value.trim().toLowerCase();
  applyFilter();
});

const nodeLabelBox = document.getElementById('nodelabels');
nodeLabelBox.checked = showNodeLabels;
nodeLabelBox.addEventListener('change', e => {
  showNodeLabels = e.target.checked;
  Graph.refresh();
});

const edgeLabelBox = document.getElementById('edgelabels');
edgeLabelBox.checked = showEdgeLabels;
edgeLabelBox.addEventListener('change', e => {
  showEdgeLabels = e.target.checked;
  Graph.refresh();
});

const physicsBox = document.getElementById('physics');
physicsBox.checked = !CONFIG.pinned;
physicsBox.addEventListener('change', e => {
  if (e.target.checked) {
    DATA.nodes.forEach(n => { delete n.fx; delete n.fy; delete n.fz; });
  } else {
    DATA.nodes.forEach(n => { n.fx = n.__px ?? n.x; n.fy = n.__py ?? n.y; n.fz = n.__pz ?? n.z; });
  }
  Graph.d3ReheatSimulation();
});

document.getElementById('clear').addEventListener('click', () => {
  activeGroups.clear();
  query = '';
  document.getElementById('q').value = '';
  document.querySelectorAll('.row.grp.active').forEach(r => r.classList.remove('active'));
  applyFilter();
});
