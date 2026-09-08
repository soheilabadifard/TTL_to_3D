"""The vendored bundle is the only JavaScript the page loads; it must carry all three globals."""
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / "ttl3d" / "vendor" / "fg3d-bundle.min.js"


def test_bundle_exposes_required_globals():
    lib = VENDOR.read_text()
    for g in ("window.ForceGraph3D", "window.SpriteText", "window.THREE"):
        assert g in lib, g
    assert "</script" not in lib
