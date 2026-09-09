"""Scale rules and the pinned stress layout.

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


def _kk(G) -> dict:
    """3-D Kamada-Kawai positions for one connected graph, seeded so the same
    input always gives the same picture. A single node sits at the origin."""
    import networkx as nx
    if G.number_of_nodes() == 1:
        return {next(iter(G)): [0.0, 0.0, 0.0]}
    return nx.kamada_kawai_layout(G, dim=3, pos=nx.random_layout(G, dim=3, seed=SEED))


def _scaled(p: dict, links: list[dict]) -> dict[str, list[float]]:
    """Scale raw positions so the mean edge length is about 60 (the live rest length)."""
    lens = [d for d in (math.dist(p[l["source"]], p[l["target"]])
                        for l in links if l["source"] in p and l["target"] in p) if d > 0]
    scale = 60 / (sum(lens) / len(lens)) if lens else 60
    return {n: [round(float(c) * scale, 2) for c in xyz] for n, xyz in p.items()}


def stress_positions(node_ids: list[str], links: list[dict]) -> dict[str, list[float]]:
    """3D Kamada-Kawai positions per connected component. The largest component
    sits at the origin; every other component gets its own layout and is shelved
    to the right of the main body, ISLANDS_PER_ROW per row, with ISLAND_GAP of
    clearance between components."""
    import networkx as nx
    if not node_ids:
        return {}
    H = nx.Graph()
    H.add_nodes_from(node_ids)
    H.add_edges_from((l["source"], l["target"]) for l in links if l["source"] != l["target"])
    comps = sorted(nx.connected_components(H), key=lambda c: (-len(c), sorted(c)[0]))
    pos = _scaled(_kk(H.subgraph(comps[0])), links)
    reach = max((abs(c) for xyz in pos.values() for c in xyz), default=0.0)
    x_start = reach + ISLAND_GAP
    x, row_y, row_h, col = x_start, 0.0, 0.0, 0
    for comp in comps[1:]:
        island = _scaled(_kk(H.subgraph(comp)), links)
        xs = [q[0] for q in island.values()]
        ys = [q[1] for q in island.values()]
        if col == ISLANDS_PER_ROW:
            x, row_y, row_h, col = x_start, row_y + row_h + ISLAND_GAP, 0.0, 0
        for n, (px, py, pz) in island.items():
            pos[n] = [round(px - min(xs) + x, 2), round(py - min(ys) + row_y, 2), round(pz, 2)]
        x += max(xs) - min(xs) + ISLAND_GAP
        row_h = max(row_h, max(ys) - min(ys))
        col += 1
    return pos
