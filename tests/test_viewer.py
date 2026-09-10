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
                       capture_output=True, text=True, cwd=REPO, check=False)
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
            page.evaluate("showNode(Graph.graphData().nodes.find(n => n.label === 'Earth'))")
            assert page.evaluate("document.getElementById('detail').classList.contains('open')")
            assert page.evaluate("document.querySelectorAll('#detail .rel').length") >= 1
            assert page.evaluate("document.querySelectorAll('#detail .rel').length") == page.evaluate(
                "(rels[Graph.graphData().nodes.find(n => n.label === 'Earth').id] || []).length")
        finally:
            browser.close()
    assert errors == []


def test_bucket_row_click_selects_only_its_groups(tmp_path):
    ttl = tmp_path / "many.ttl"
    ttl.write_text("@prefix ex: <http://example.org/m#> .\n"
                   + "".join(f"ex:i{i} a ex:C{i:02d} .\n" for i in range(13))
                   + "ex:big1 a ex:C00 . ex:big2 a ex:C00 .\n", encoding="utf-8")
    out = tmp_path / "many.html"
    r = subprocess.run([sys.executable, "-m", "ttl3d", str(ttl), "-o", str(out), "--color-by", "type"],
                       capture_output=True, text=True, cwd=REPO, check=False)
    assert r.returncode == 0, r.stderr
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        try:
            page = browser.new_page()
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri())
            page.wait_for_function("document.querySelectorAll('.row.grp').length > 0")
            page.click(".row.grp[data-groups]")
            assert page.evaluate("document.querySelectorAll('.row.grp.active').length") == 1
            assert page.evaluate("DATA.nodes.filter(n => !n._dim).length") >= 2
            assert page.evaluate("DATA.nodes.filter(n => n._dim).length") >= 1
        finally:
            browser.close()
    assert errors == []


def _run_cli(*args):
    r = subprocess.run([sys.executable, "-m", "ttl3d", *args], capture_output=True, text=True, cwd=REPO,
                       check=False)
    assert r.returncode == 0, r.stderr
    return r


SWIFTSHADER = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]


def _open(p, url, errors, args=SWIFTSHADER):
    browser = p.chromium.launch(args=args)
    page = browser.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.wait_for_function("document.querySelectorAll('.row.grp').length > 0")
    return browser, page


DEMO = [str(REPO / "examples" / "solar-system.ttl"), str(REPO / "examples" / "solar-system-missions.ttl")]


def test_2d_page_filters_and_opens_cards_without_console_errors(tmp_path):
    out = tmp_path / "solar-2d.html"
    _run_cli(*DEMO, "-o", str(out), "--view", "2d")
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors)
        try:
            assert page.evaluate("view") == "2d"
            assert page.evaluate("document.querySelector('input[name=view][value=\"2d\"]').checked")
            assert page.evaluate("typeof Graph.scene") == "undefined"        # canvas renderer, not the WebGL one
            assert page.evaluate("document.querySelectorAll('#graph canvas').length") == 1
            assert "drag to pan" in page.evaluate("document.getElementById('nav').textContent")
            assert page.evaluate("DATA.nodes.every(n => n.fx === n.__pos['2d'][0] "
                                 "&& n.fy === n.__pos['2d'][1] && !('fz' in n))")
            page.click(".row.grp")
            assert page.evaluate("DATA.nodes.filter(n => n._dim).length") >= 1
            page.fill("#q", "earth")
            assert page.evaluate("DATA.nodes.filter(n => !n._dim).length") >= 1
            page.evaluate("showNode(DATA.nodes.find(n => n.label === 'Earth'))")
            assert page.evaluate("document.getElementById('detail').classList.contains('open')")
            page.uncheck("#nodelabels"); page.uncheck("#edgelabels")       # canvas callbacks read the flags
            page.check("#nodelabels"); page.check("#edgelabels")
            assert page.evaluate("showNodeLabels && showEdgeLabels")
        finally:
            browser.close()
    assert errors == []


def test_2d_page_without_a_precomputed_layout_runs_the_simulation(tmp_path):
    out = tmp_path / "solar-2d-force.html"
    _run_cli(*DEMO, "-o", str(out), "--view", "2d", "--layout", "force")
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors)
        try:
            assert page.evaluate("view") == "2d" and page.evaluate("document.getElementById('physics').checked")
            assert page.evaluate("DATA.nodes.every(n => n.fx === undefined && n.__pos === undefined)")
            page.wait_for_function("DATA.nodes.every(n => typeof n.x === 'number')")
            page.mouse.move(400, 300); page.mouse.wheel(0, -120)              # the user zooms in early
            page.wait_for_function("Graph.__touched === true")
            zoom = page.evaluate("Graph.zoom()")
            # trailing void: force-graph's setters return Graph (for chaining) and Playwright's
            # evaluate() auto-invokes a function-valued completion, so the last statement here
            # must not evaluate to the bare Graph instance
            page.evaluate("window.__stopped = false; const prev = Graph.onEngineStop();"
                          " Graph.onEngineStop(() => { prev(); window.__stopped = true; });"
                          " void Graph.cooldownTicks(30)")
            page.wait_for_function("window.__stopped", timeout=30000)
            assert page.evaluate("Graph.zoom()") == zoom                       # the late fit stood down
            page.uncheck("#physics")                    # no precomputed layout: pins where the nodes are
            assert page.evaluate("DATA.nodes.every(n => n.fx === n.x && n.fy === n.y && !('fz' in n))")
        finally:
            browser.close()
    assert errors == []


def test_free_float_survives_a_switch_and_pins_back_to_each_views_layout(tmp_path):
    out = tmp_path / "solar.html"
    _run_cli(*DEMO, "-o", str(out))
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors)
        try:
            page.check("#physics")
            assert page.evaluate("DATA.nodes.every(n => n.fx === undefined && n.fz === undefined)")
            page.check('input[name="view"][value="2d"]')
            assert page.evaluate("DATA.nodes.every(n => n.fx === undefined)")           # still free-floating
            # click and inspect in one JS turn, before the first simulation tick moves anything
            assert page.evaluate("(() => { document.querySelector('input[name=view][value=\"3d\"]').click();"
                                 " return DATA.nodes.every(n => n.fx === undefined && n.z === 0 && n.vz === 0); })()")
            page.uncheck("#nodelabels"); page.check("#nodelabels")                     # relabel3d rebuilds
            page.uncheck("#physics")
            assert page.evaluate("DATA.nodes.every(n => n.fx === n.__pos['3d'][0] "
                                 "&& n.fz === n.__pos['3d'][2])")
        finally:
            browser.close()
    assert errors == []


def test_2d_canvas_pauses_when_idle_and_repaints_on_a_filter_change(tmp_path):
    out = tmp_path / "solar-2d.html"
    _run_cli(*DEMO, "-o", str(out), "--view", "2d")
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors)
        try:
            # trailing void: see the same comment in test_2d_page_without_a_precomputed_layout_runs_the_simulation
            page.evaluate("window.__stopped = false; const prev = Graph.onEngineStop();"
                          " Graph.onEngineStop(() => { prev(); window.__stopped = true; });"
                          " void Graph.cooldownTicks(30)")                # settle in a few frames, not 15 s
            page.wait_for_function("window.__stopped", timeout=30000)
            page.evaluate("window.__frames = 0; void Graph.onRenderFramePre(() => { window.__frames++; })")
            page.wait_for_timeout(400)
            idle = page.evaluate("window.__frames")
            assert idle <= 1                                      # paused: at most one stray frame
            page.click(".row.grp")
            page.wait_for_function(f"window.__frames > {idle}")   # restyle2d marked the canvas dirty
        finally:
            browser.close()
    assert errors == []


def test_default_page_falls_back_to_2d_without_webgl(tmp_path):
    out = tmp_path / "solar.html"
    _run_cli(*DEMO, "-o", str(out))
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors, args=["--disable-3d-apis"])
        try:
            assert page.evaluate("view") == "2d"
            assert page.evaluate("document.querySelector('input[name=view][value=\"3d\"]').disabled")
            assert "WebGL" in page.evaluate("document.getElementById('nav').textContent")
            assert page.evaluate("typeof Graph.scene") == "undefined"        # the canvas renderer took over
            page.click(".row.grp")
            assert page.evaluate("DATA.nodes.filter(n => n._dim).length") >= 1
        finally:
            browser.close()
    # three.js may report the failed context on the console; nothing else may
    assert all("WebGL" in e for e in errors), errors


def test_view_switch_keeps_the_filter_and_pins_each_view_to_its_own_layout(tmp_path):
    out = tmp_path / "solar.html"
    _run_cli(*DEMO, "-o", str(out))
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors)
        try:
            page.click(".row.grp")
            page.fill("#q", "earth")
            dimmed = page.evaluate("DATA.nodes.filter(n => n._dim).length")
            assert dimmed >= 1
            # trailing void: see the same comment in test_2d_page_without_a_precomputed_layout_runs_the_simulation
            page.evaluate("showNode(DATA.nodes.find(n => n.label === 'Earth')); void (window.__g0 = Graph)")
            page.check('input[name="view"][value="2d"]')
            assert page.evaluate("view") == "2d" and page.evaluate("typeof Graph.scene") == "undefined"
            assert page.evaluate("Graph !== window.__g0")                                   # a fresh instance
            assert page.evaluate("document.getElementById('q').value") == "earth"           # search survives
            assert page.evaluate("document.getElementById('detail').classList.contains('open')")   # so does the card
            assert page.evaluate("DATA.nodes.filter(n => n._dim).length") == dimmed
            assert page.evaluate("DATA.nodes.every(n => n.fx === n.__pos['2d'][0] "
                                 "&& n.fy === n.__pos['2d'][1] && !('fz' in n))")
            assert page.evaluate("document.querySelectorAll('#graph canvas').length") == 1  # old scene gone
            page.check('input[name="view"][value="3d"]')
            assert page.evaluate("view") == "3d" and page.evaluate("typeof Graph.scene") == "function"
            assert page.evaluate("DATA.nodes.filter(n => n._dim).length") == dimmed
            assert page.evaluate("DATA.nodes.every(n => n.fx === n.__pos['3d'][0] "
                                 "&& n.fz === n.__pos['3d'][2])")
            assert page.evaluate("DATA.nodes.every(n => n.__threeObj && n.__threeObj.parent)")  # rebuilt
            assert page.evaluate("document.querySelectorAll('#graph canvas').length") == 1
            assert "drag to rotate" in page.evaluate("document.getElementById('nav').textContent")
        finally:
            browser.close()
    assert errors == []
