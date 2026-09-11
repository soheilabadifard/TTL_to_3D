"""The vendored bundle is the only JavaScript the page loads; it must carry all four globals,
and its rebuild must be reproducible from the pins next to it."""
import json
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / "ttl3d" / "vendor" / "fg-bundle.min.js"


def test_bundle_exposes_required_globals():
    lib = VENDOR.read_text(encoding="utf-8")
    # `window.ForceGraph=` with the `=` so `ForceGraph3D` cannot stand in for the 2D library
    for g in ("ForceGraph3D", "ForceGraph", "SpriteText", "THREE"):
        assert f"window.{g}=" in lib, g
    assert "</script" not in lib and "sourceMappingURL" not in lib


def test_vendor_pins_are_exact_and_locked():
    pins = json.loads((VENDOR.parent / "package.json").read_text(encoding="utf-8"))
    for name, ver in {**pins["dependencies"], **pins["devDependencies"]}.items():
        assert ver[0].isdigit(), f"{name} is not pinned exactly: {ver}"
    assert pins["dependencies"]["force-graph"] == "1.51.4" and pins["dependencies"]["three"] == "0.185.0"
    assert (VENDOR.parent / "package-lock.json").exists()


def test_vendor_notices_cover_every_runtime_package_in_the_lockfile():
    # MIT and ISC both require the copyright notice to travel with copies; the bundle
    # inlines every runtime package of the lockfile, so every one needs a line here
    lock = json.loads((VENDOR.parent / "package-lock.json").read_text(encoding="utf-8"))
    notices = (VENDOR.parent / "LICENSES.md").read_text(encoding="utf-8")
    runtime = {(path.split("node_modules/")[-1], meta["version"])
               for path, meta in lock["packages"].items() if path and not meta.get("dev")}
    missing = sorted(f"{name} {version}" for name, version in runtime
                     if f"- {name} {version} " not in notices)
    assert not missing, missing
    assert "## The MIT License" in notices and "## The ISC License" in notices
