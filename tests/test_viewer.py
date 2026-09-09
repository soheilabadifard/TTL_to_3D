"""Headless-browser smoke test of the generated page. Skips unless Playwright is installed
(`pip install -e .[browser] && playwright install chromium`)."""
import subprocess
import sys
from pathlib import Path
import pytest

pw = pytest.importorskip("playwright.sync_api")

REPO = Path(__file__).resolve().parents[1]


def test_demo_page_runs_without_console_errors(tmp_path):
    out = tmp_path / "solar.html"
    r = subprocess.run([sys.executable, "-m", "ttl3d",
                        str(REPO / "examples" / "solar-system.ttl"),
                        str(REPO / "examples" / "solar-system-missions.ttl"), "-o", str(out)],
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stderr
    # the CLI prints "<nodes> nodes, <links> links -> <path> ..." on success (see tests/test_cli.py)
    n_nodes = int(r.stdout.split()[0])
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        try:
            page = browser.new_page()
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri())
            page.wait_for_function("document.querySelectorAll('.row.grp').length > 0")
            assert page.evaluate("DATA.nodes.length") == n_nodes
            page.click(".row.grp")
            assert page.evaluate("document.querySelectorAll('.row.grp.active').length") == 1
            page.fill("#q", "earth")
            assert page.evaluate("DATA.nodes.filter(n => !n._dim).length") >= 1
            page.click("#clear")
            assert page.evaluate("document.querySelectorAll('.row.grp.active').length") == 0
        finally:
            browser.close()
    assert errors == []
