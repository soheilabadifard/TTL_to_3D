"""tools/release_notes.py prints one version's changelog section; the install lines that pin a
minimum ttl3d version never ask for a version that does not exist yet."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

import ttl3d

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("release_notes", REPO / "tools" / "release_notes.py")
release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes)

CHANGELOG = """# Changelog

## Unreleased

Nothing yet.

## 0.3.0 (2026-09-12)

A Python entry point.
Two lines long.

## 0.2.3 (2026-09-11)

Older.
"""


def test_section_returns_the_body_of_one_version_only():
    assert release_notes.section(CHANGELOG, "0.3.0") == "A Python entry point.\nTwo lines long.\n"
    assert release_notes.section(CHANGELOG, "0.2.3") == "Older.\n"


def test_a_version_without_a_section_is_none():
    assert release_notes.section(CHANGELOG, "9.9.9") is None


def test_main_prints_the_section_and_fails_loudly_without_one(tmp_path, capsys, monkeypatch):
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert release_notes.main(["0.3.0"]) == 0
    assert capsys.readouterr().out == "A Python entry point.\nTwo lines long.\n"
    assert release_notes.main(["9.9.9"]) == 1
    assert "9.9.9" in capsys.readouterr().err


def _version(s: str) -> tuple:
    return tuple(int(x) for x in s.split("."))


def _pins():
    """Every `ttl3d>=X` in the README and the notebook, as version strings."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    nb = json.loads((REPO / "examples" / "ttl3d.ipynb").read_text(encoding="utf-8"))
    cells = "".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    return re.findall(r"ttl3d>=(\d+\.\d+\.\d+)", readme + cells)


def test_the_install_lines_pin_a_minimum_version_that_exists():
    pins = _pins()
    assert len(pins) >= 2                       # the notebook's pip cell and the README's Python section
    for pin in pins:
        assert _version(pin) <= _version(ttl3d.__version__), pin


@pytest.mark.parametrize("path", ["CITATION.cff"])
def test_the_citation_file_carries_the_package_version(path):
    text = (REPO / path).read_text(encoding="utf-8")
    assert f"version: {ttl3d.__version__}\n" in text
