"""tools/licenses.py: LICENSES.md lists every runtime package of the vendored lockfile with its
copyright line and stops at a licence it has no text for."""
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "licenses", Path(__file__).resolve().parents[1] / "tools" / "licenses.py")
licenses = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(licenses)


def _build_dir(tmp_path, packages):
    """A build directory as `npm ci` leaves it: package-lock.json plus node_modules/<name>/ for each
    package, holding package.json and the given extra files. `packages` maps a lockfile path to
    (lockfile entry, package.json, {file name: text})."""
    lock = {"packages": {"": {"name": "vendor"}}}
    for path, (entry, pkg, files) in packages.items():
        lock["packages"][path] = entry
        d = tmp_path / path
        d.mkdir(parents=True)
        (d / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        for name, text in files.items():
            (d / name).write_text(text, encoding="utf-8")
    (tmp_path / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return tmp_path


def test_every_runtime_package_gets_a_line_under_its_licence_and_the_texts_follow(tmp_path):
    build = _build_dir(tmp_path / "build", {
        "node_modules/kapsule": ({"version": "1.16.3", "license": "MIT"}, {},
                                 {"LICENSE": "MIT License\n\nCopyright (c) 2019 Vasco Asturiano\n"}),
        "node_modules/@scope/d3-x": ({"version": "3.0.1"},
                                     {"license": "ISC", "author": {"name": "Mike"}}, {}),
        "node_modules/a/node_modules/nested": ({"version": "0.1.0", "license": "BSD-3-Clause"},
                                               {"author": "Someone"}, {}),
        "node_modules/bare": ({"version": "2.0.0", "license": "MIT"}, {}, {}),
        "node_modules/esbuild": ({"version": "0.25.0", "license": "GPL-3.0", "dev": True}, {}, {}),
    })
    out = tmp_path / "LICENSES.md"
    licenses.main(str(build), str(out))
    text = out.read_text(encoding="utf-8")
    sections = text.split("\n## ")
    assert [s.split("\n", 1)[0] for s in sections[1:]] == [
        "BSD-3-Clause", "ISC", "MIT", "The BSD 3-Clause License", "The ISC License", "The MIT License"]
    assert "- nested 0.1.0 — Copyright (c) Someone\n" in sections[1]          # the innermost name
    assert "- @scope/d3-x 3.0.1 — Copyright (c) Mike\n" in sections[2]        # an author given as a dict
    assert sections[3].splitlines()[2:4] == [
        "- bare 2.0.0 — (no copyright line in the package)",                   # sorted by lockfile path
        "- kapsule 1.16.3 — Copyright (c) 2019 Vasco Asturiano",               # the LICENSE file's line
    ]
    assert "esbuild" not in text                                               # dev packages never ship
    assert licenses.MIT in sections[6]


@pytest.mark.parametrize("name", licenses.LICENSE_FILES)
def test_the_copyright_line_comes_from_any_licence_file_spelling_before_the_author(tmp_path, name):
    (tmp_path / name).write_text("Some licence\n  Copyright 2024 The Authors  \n", encoding="utf-8")
    assert licenses.copyright_line(tmp_path, "Ignored") == "Copyright 2024 The Authors"


def test_a_licence_file_without_a_copyright_line_falls_back_to_the_author(tmp_path):
    (tmp_path / "LICENSE").write_text("Permission is hereby granted\n", encoding="utf-8")
    assert licenses.copyright_line(tmp_path, {"name": "Ann"}) == "Copyright (c) Ann"
    assert licenses.copyright_line(tmp_path, {}) == "(no copyright line in the package)"
    assert licenses.copyright_line(tmp_path, None) == "(no copyright line in the package)"


def test_a_licence_without_a_text_stops_the_script_and_names_the_package(tmp_path):
    build = _build_dir(tmp_path / "build", {
        "node_modules/ok": ({"version": "1.0.0", "license": "MIT"}, {}, {}),
        "node_modules/copyleft": ({"version": "2.0.0"}, {"license": "GPL-3.0"}, {}),
    })
    out = tmp_path / "LICENSES.md"
    with pytest.raises(SystemExit) as e:
        licenses.main(str(build), str(out))
    assert str(e.value) == "copyleft: licence 'GPL-3.0' has no text in licenses.py; add it before rerunning"
    assert not out.exists()
