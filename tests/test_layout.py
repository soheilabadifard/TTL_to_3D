"""ttl3d.layout: scale rules and the pinned stress layout."""
import itertools
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ttl3d import layout

REPO = Path(__file__).resolve().parents[1]


def test_auto_layout_is_stress_up_to_the_threshold_then_force():
    assert layout.choose_layout(10, "auto") == "stress"
    assert layout.choose_layout(layout.STRESS_MAX_NODES, "auto") == "stress"
    assert layout.choose_layout(layout.STRESS_MAX_NODES + 1, "auto") == "force"


def test_explicit_layout_modes_are_respected():
    assert layout.choose_layout(10_000, "stress") == "stress"
    assert layout.choose_layout(10, "force") == "force"


def test_invalid_layout_mode_is_rejected():
    with pytest.raises(ValueError):
        layout.choose_layout(1, "magic")


def test_auto_labels_switch_off_independently_past_the_thresholds():
    assert layout.choose_labels(10, 10, "auto") == {"node": True, "edge": True}
    assert layout.choose_labels(layout.LABEL_MAX_NODES + 1, 10, "auto") == {"node": False, "edge": True}
    assert layout.choose_labels(10, layout.LABEL_MAX_LINKS + 1, "auto") == {"node": True, "edge": False}


def test_explicit_label_modes_are_respected():
    assert layout.choose_labels(10_000, 10_000, "always") == {"node": True, "edge": True}
    assert layout.choose_labels(1, 1, "hover") == {"node": False, "edge": False}


def test_invalid_label_mode_is_rejected():
    with pytest.raises(ValueError):
        layout.choose_labels(1, 1, "sometimes")


def test_stress_positions_cover_every_node_and_park_islands_beyond_the_main_body():
    ids = ["a", "b", "c", "d", "e"]
    links = [{"source": "a", "target": "b"}, {"source": "b", "target": "c"},
             {"source": "d", "target": "e"}]
    pos = layout.stress_positions(ids, links)
    assert set(pos) == set(ids)
    assert all(len(p) == 3 for p in pos.values())
    reach = max(abs(c) for n in ("a", "b", "c") for c in pos[n])
    assert min(pos["d"][0], pos["e"][0]) > reach


def test_stress_positions_handle_no_links_and_a_single_node():
    assert set(layout.stress_positions(["x", "y", "z"], [])) == {"x", "y", "z"}
    only = layout.stress_positions(["only"], [])
    assert set(only) == {"only"} and len(only["only"]) == 3


def test_stress_positions_with_no_nodes_returns_nothing():
    assert layout.stress_positions([], []) == {}


def test_stress_positions_survive_a_lone_self_loop():
    pos = layout.stress_positions(["a"], [{"source": "a", "target": "a"}])
    assert pos == {"a": [0.0, 0.0, 0.0]}


def test_stress_positions_are_reproducible():
    ids = [f"n{i}" for i in range(12)]
    links = [{"source": f"n{i}", "target": f"n{i + 1}"} for i in range(11)]
    links.append({"source": "n0", "target": "n6"})
    assert layout.stress_positions(ids, links) == layout.stress_positions(ids, links)


def test_components_never_come_closer_than_the_island_gap():
    ids, links = ["m1", "m2"], [{"source": "m1", "target": "m2"}]
    for i in range(12):
        chain = [f"i{i}n{j}" for j in range(4)]
        ids += chain
        links += [{"source": a, "target": b} for a, b in itertools.pairwise(chain)]
    pos = layout.stress_positions(ids, links)
    component = {n: n.split("n")[0] if n.startswith("i") else "m" for n in ids}
    closest = min(math.dist(pos[a], pos[b]) for a in ids for b in ids
                  if component[a] != component[b])
    assert closest >= layout.ISLAND_GAP - 1e-6


def test_stress_notice_is_silent_for_small_graphs_and_warns_past_the_auto_limit():
    assert layout.stress_notice(layout.PROGRESS_MIN_NODES) is None
    assert "stress layout" in layout.stress_notice(layout.PROGRESS_MIN_NODES + 1)
    big = layout.stress_notice(layout.STRESS_MAX_NODES + 1)
    assert "--layout force" in big


def test_layout_is_identical_across_processes_with_different_hash_seeds():
    code = (
        "import json\n"
        "from ttl3d import layout\n"
        "ids = [f'n{i}' for i in range(30)]\n"
        "links = [{'source': f'n{i}', 'target': f'n{i + 1}'} for i in range(9)]\n"
        "links += [{'source': f'n{i}', 'target': f'n{i + 1}'} for i in range(10, 29) if i % 3 != 0]\n"
        "print(json.dumps(layout.stress_positions(ids, links), sort_keys=True))\n")
    outs = []
    for seed in ("1", "2"):
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO,
                           check=False, env={**os.environ, "PYTHONHASHSEED": seed})
        assert r.returncode == 0, r.stderr
        outs.append(r.stdout)
    assert outs[0] == outs[1]
