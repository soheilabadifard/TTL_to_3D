"""Scale rules and the pinned stress layout (one per view: 3D and 2D).

Kamada-Kawai is quadratic in nodes and the label sprites die past a few
thousand scene objects, so the automatic modes degrade: above
STRESS_MAX_NODES the page runs the live force simulation instead of a
precomputed layout, and past the label thresholds the sprites are not
created (hover tooltips still work).
"""
from __future__ import annotations

import math

STRESS_MAX_NODES = 1000
LABEL_MAX_NODES = 800
LABEL_MAX_LINKS = 800
LAYOUT_MODES = ("auto", "stress", "force")
LABEL_MODES = ("auto", "always", "hover")

SEED = 0   # networkx seeds 3-D Kamada-Kawai from a random layout; fix it so a rebuild keeps the picture
ISLAND_GAP = 60.0        # clearance between components, in scene units (about one rest length)
ISLANDS_PER_ROW = 10     # islands are shelved left to right, then a new row starts
PROGRESS_MIN_NODES = 200   # below this the stress layout is instant; say nothing


def choose_layout(n_nodes: int, mode: str = "auto") -> str:
    if mode not in LAYOUT_MODES:
        raise ValueError(f"layout must be one of {LAYOUT_MODES}, got {mode!r}")
    if mode == "auto":
        return "stress" if n_nodes <= STRESS_MAX_NODES else "force"
    return mode


def choose_labels(n_nodes: int, n_links: int, mode: str = "auto") -> dict:
    if mode not in LABEL_MODES:
        raise ValueError(f"labels must be one of {LABEL_MODES}, got {mode!r}")
    if mode == "always":
        return {"node": True, "edge": True}
    if mode == "hover":
        return {"node": False, "edge": False}
    return {"node": n_nodes <= LABEL_MAX_NODES, "edge": n_links <= LABEL_MAX_LINKS}


def stress_notice(n_nodes: int) -> str | None:
    """One stderr line before the stress layouts that will take a while (None when they won't).
    Kamada-Kawai is quadratic and runs twice (3D and 2D): ~1.2 s at 200 nodes, ~5 s at 500,
    ~18 s at 1000."""
    if n_nodes <= PROGRESS_MIN_NODES:
        return None
    msg = f"computing stress layouts (3D and 2D) for {n_nodes} nodes..."
    if n_nodes > STRESS_MAX_NODES:
        msg += (f" (more than {STRESS_MAX_NODES}: this is quadratic and may take minutes;"
                " --layout force skips it)")
    return msg


def _kk(G, dim: int = 3) -> dict:
    """`dim`-D Kamada-Kawai positions for one connected graph, identical in every
    process for the same input: a subgraph view iterates in set order (which
    follows Python's per-process hash seed), so the nodes and edges are handed
    to networkx in sorted order and the start positions are seeded. A single
    node sits at the origin."""
    import networkx as nx
    nodes = sorted(G, key=str)
    if len(nodes) == 1:
        return {nodes[0]: [0.0] * dim}
    S = nx.Graph()
    S.add_nodes_from(nodes)
    S.add_edges_from(sorted((min(u, v, key=str), max(u, v, key=str)) for u, v in G.edges()))
    return nx.kamada_kawai_layout(S, dim=dim, pos=nx.random_layout(S, dim=dim, seed=SEED))


def _scaled(p: dict, links: list[dict]) -> dict[str, list[float]]:
    """Scale raw positions so the mean edge length is about 60 (the live rest length)."""
    lens = [d for d in (math.dist(p[l["source"]], p[l["target"]])
                        for l in links if l["source"] in p and l["target"] in p) if d > 0]
    scale = 60 / (sum(lens) / len(lens)) if lens else 60
    return {n: [round(float(c) * scale, 2) for c in xyz] for n, xyz in p.items()}


def stress_positions(node_ids: list[str], links: list[dict], dim: int = 3) -> dict[str, list[float]]:
    """Kamada-Kawai positions per connected component, in `dim` (3 or 2) dimensions.
    The largest component sits at the origin; every other component gets its own
    layout and is shelved to the right of the main body, ISLANDS_PER_ROW per row,
    with ISLAND_GAP of clearance between components. Only coordinates 0 and 1 are
    shifted by the packing, so the same code serves both views."""
    import networkx as nx
    if not node_ids:
        return {}
    H = nx.Graph()
    H.add_nodes_from(node_ids)
    H.add_edges_from((l["source"], l["target"]) for l in links if l["source"] != l["target"])
    comps = sorted(nx.connected_components(H), key=lambda c: (-len(c), min(c)))
    pos = _scaled(_kk(H.subgraph(comps[0]), dim), links)
    reach = max((abs(c) for xyz in pos.values() for c in xyz), default=0.0)
    x_start = reach + ISLAND_GAP
    x, row_y, row_h, col = x_start, 0.0, 0.0, 0
    for comp in comps[1:]:
        island = _scaled(_kk(H.subgraph(comp), dim), links)
        xs = [q[0] for q in island.values()]
        ys = [q[1] for q in island.values()]
        if col == ISLANDS_PER_ROW:
            x, row_y, row_h, col = x_start, row_y + row_h + ISLAND_GAP, 0.0, 0
        for n, p in island.items():
            pos[n] = [round(p[0] - min(xs) + x, 2), round(p[1] - min(ys) + row_y, 2), *p[2:]]
        x += max(xs) - min(xs) + ISLAND_GAP
        row_h = max(row_h, max(ys) - min(ys))
        col += 1
    return pos
