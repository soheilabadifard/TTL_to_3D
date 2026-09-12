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
const tooltip = n => `<b>${esc(n.label)}</b><br>${esc(n.types.join(', ') || 'untyped')}<br><i>${esc(n.group)}</i>`;

// --- views -------------------------------------------------------------------
// One renderer per view, each a set of function declarations in viewer-3d.js /
// viewer-2d.js (appended after this file, so hoisting makes them callable here).
// create(el) builds the graph on DATA and returns the instance; focus(n) frames
// a node for its card. Optional: restyle() after a filter change, relabel()
// after a label toggle, unmount() before the instance is thrown away.
const RENDERERS = {
  '3d': {create: create3d, focus: focus3d, restyle: restyle3d, relabel: relabel3d, unmount: unmount3d},
  '2d': {create: create2d, focus: focus2d, restyle: restyle2d, relabel: relabel2d},   // no WebGL to release
};
let view = CONFIG.view, Graph = null;

// pinned mode: every node keeps a precomputed stress-minimized position per
// view; the "free-float physics" toggle releases them into the live force
// layout and pins them back where they were
if (CONFIG.pinned) DATA.nodes.forEach(n => { n.__pos = {'3d': [n.x, n.y, n.z], '2d': [n.x2, n.y2]}; });

function pin(v) {
  DATA.nodes.forEach(n => {
    // without a precomputed layout a node pins where it currently is (z = 0 if it never had one)
    const p = n.__pos ? n.__pos[v] : (v === '2d' ? [n.x, n.y] : [n.x, n.y, n.z ?? 0]);
    n.x = n.fx = p[0]; n.y = n.fy = p[1];
    if (p.length > 2) n.z = n.fz = p[2]; else delete n.fz;
  });
}
function unpin() {
  DATA.nodes.forEach(n => { delete n.fx; delete n.fy; delete n.fz; });
}
// a pinned picture has nothing to simulate: stop the engine on its first tick
// instead of running the library's 15 s cooldown, so the 2D canvas pauses at
// once. With cooldownTicks 0 the d3 tick never runs; pin() has already written
// x/y/z, 3D copies them onto its objects in the same tickFrame that stops the
// engine, and 2D paints from them directly. A drag resets the countdown and
// moves the node itself, so dragging keeps working.
function cooldown() { Graph.cooldownTicks(physicsBox.checked ? Infinity : 0); }

// tear down the current renderer (if any) and build view `v` on the same
// node and link objects; both libraries accept links whose endpoints are
// already node objects and clear their own per-object bindings on _destructor
//
//   startup ──mount(CONFIG.view)──▶ [3d] ◀───radios───▶ [2d]
//                                    │ create3d throws (no WebGL)
//                                    ▼
//                                   [2d], 3D radio disabled, reason in #nav
//
//   each mount: destroy old ─▶ pin(v) unless free-floating ─▶ create ─▶
//               shared forces + cooldown ─▶ restyle?.() ─▶ hint + radio
function mount(v) {
  const el = document.getElementById('graph');
  if (Graph) { Graph._destructor(); RENDERERS[view].unmount?.(); el.replaceChildren(); }
  view = v;
  if (physicsBox.checked) {
    // free-floating: x/y carry over, and 3D restarts from the flat 2D sheet every
    // time (d3 jiggles coincident coordinates, so the layout leaves the plane on its own)
    if (v === '3d') DATA.nodes.forEach(n => { n.z = 0; n.vz = 0; });
  } else pin(v);
  try {
    Graph = RENDERERS[v].create(el);
  } catch (e) {
    // no WebGL (remote desktops, locked-down VMs, acceleration off): three.js
    // throws while creating its renderer. The canvas view needs none.
    if (v !== '3d') throw e;
    console.warn('3D view unavailable, falling back to 2D:', e);
    Graph = null; el.replaceChildren();
    document.querySelector('input[name="view"][value="3d"]').disabled = true;
    mount('2d');
    document.getElementById('nav').textContent += ' · 3D needs WebGL, which this browser cannot provide';
    return;
  }
  // spacing scaled to sphere size so spheres and labels do not collide
  Graph.d3Force('link').distance(l => 26 + 1.6 * (rOf(l.source) + rOf(l.target)));
  Graph.d3Force('charge').strength(-80);
  cooldown();
  RENDERERS[v].restyle?.();
  document.getElementById('nav').textContent =
    v === '2d' ? 'drag to pan · scroll to zoom' : 'drag to rotate · scroll to zoom';
  document.querySelector(`input[name="view"][value="${v}"]`).checked = true;
}

// --- node detail card --------------------------------------------------------
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                  .replace(/"/g,'&quot;');
}

function showNode(n) {
  RENDERERS[view].focus(n);
  let h = `<h2><span class="dot" style="background:${colorOf(n)}"></span>${esc(n.label)}</h2>`;
  h += `<div class="cls">${esc(n.types.join(', ') || 'untyped')} · ${esc(n.group)}</div>`;
  h += `<div class="iri">${esc(n.id)}</div>`;
  if (n.definition) h += `<p class="def">${esc(n.definition)}</p>`;
  const iri = DATA.graphs[n.file];                // the IRI behind a named-graph key, if the owner is one
  h += `<table><tr><td>source</td><td>${esc(n.file)}` +
       (iri ? `<div class="iri">${esc(iri)}</div>` : '') + `</td></tr>` +
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
// in file mode a selected row is a source, and it keeps every edge that source asserts, not only the
// edges it asserted first; in the other modes rows are types or namespaces and say nothing about edges
const assertedBy = l => CONFIG.colorBy === 'file' && l.files.some(f => activeGroups.has(f));

function applyFilter() {
  const core = new Set();       // ids of nodes in the selected groups
  const edgeKeep = new Set();   // endpoints of edges the selected sources assert
  if (activeGroups.size) {
    DATA.nodes.forEach(n => { if (activeGroups.has(n.group)) core.add(n.id); });
    DATA.links.forEach(l => {
      if (assertedBy(l)) { edgeKeep.add(idOf(l.source)); edgeKeep.add(idOf(l.target)); }
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
  });
  DATA.links.forEach(l => {
    const grpLink = assertedBy(l);
    const touchesCore = !activeGroups.size ||
      core.has(idOf(l.source)) || core.has(idOf(l.target));
    l._dim = (l.source._dim && l.target._dim) || !(touchesCore || grpLink);
  });
  RENDERERS[view].restyle?.();
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
  RENDERERS[view].relabel?.();
});

const edgeLabelBox = document.getElementById('edgelabels');
edgeLabelBox.checked = showEdgeLabels;
edgeLabelBox.addEventListener('change', e => {
  showEdgeLabels = e.target.checked;
  RENDERERS[view].relabel?.();
});

const physicsBox = document.getElementById('physics');
physicsBox.checked = !CONFIG.pinned;
physicsBox.addEventListener('change', e => {
  if (e.target.checked) unpin(); else pin(view);
  cooldown();
  Graph.d3ReheatSimulation();
});

document.getElementById('clear').addEventListener('click', () => {
  activeGroups.clear();
  query = '';
  document.getElementById('q').value = '';
  document.querySelectorAll('.row.grp.active').forEach(r => r.classList.remove('active'));
  applyFilter();
});

document.querySelectorAll('input[name="view"]').forEach(r =>
  r.addEventListener('change', e => { if (e.target.checked && e.target.value !== view) mount(e.target.value); }));

// the first pointer press or wheel on the picture means the user is looking at
// something, so a late 2D fit must not snap the view away from it. Capture
// phase: d3-zoom sits on the canvas itself and stops the wheel event there.
['pointerdown', 'wheel'].forEach(type => document.getElementById('graph').addEventListener(
  type, () => { if (Graph) Graph.__touched = true; }, {capture: true, passive: true}));

// the controls above must exist before the first mount (mount reads physicsBox)
mount(view);
