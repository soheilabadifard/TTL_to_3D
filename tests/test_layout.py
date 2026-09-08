"""ttl3d.layout: scale rules and the pinned stress layout."""
import pytest
from ttl3d import layout


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
