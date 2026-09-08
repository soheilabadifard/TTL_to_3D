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


def stress_positions(node_ids: list[str], links: list[dict]) -> dict[str, list[float]]:
    """3D Kamada-Kawai positions for the largest component, scaled so the mean
    edge length lands near the live rest length (~60); smaller components are
    parked on a grid beyond the main body."""
    import networkx as nx
    H = nx.Graph()
    H.add_nodes_from(node_ids)
    H.add_edges_from((l["source"], l["target"]) for l in links)
    comps = sorted(nx.connected_components(H), key=lambda c: (-len(c), sorted(c)[0]))
    pos: dict[str, list[float]] = {}
    main = comps[0]
    if len(main) == 1:
        p = {next(iter(main)): [0.0, 0.0, 0.0]}
    else:
        p = nx.kamada_kawai_layout(H.subgraph(main), dim=3)
    lens = [math.dist(p[l["source"]], p[l["target"]])
            for l in links if l["source"] in p and l["target"] in p]
    scale = 60 / (sum(lens) / len(lens)) if lens else 60
    for n, xyz in p.items():
        pos[n] = [round(float(c) * scale, 2) for c in xyz]
    reach = max((abs(c) for xyz in pos.values() for c in xyz), default=0.0)
    for i, comp in enumerate(comps[1:]):
        col, row = i % 10, i // 10
        for j, n in enumerate(sorted(comp)):
            pos[n] = [reach + 60 + col * 80, row * 80.0 + j * 45.0, 0.0]
    return pos
