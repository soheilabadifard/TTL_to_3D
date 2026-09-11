"""Headless-browser smoke test of the generated page. Skips unless Playwright is installed
(`pip install -e .[browser] && playwright install chromium`). TTL3D_BROWSER=firefox or webkit
runs the same tests on another engine (`playwright install firefox webkit`)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

REPO = Path(__file__).resolve().parents[1]
BROWSER = os.environ.get("TTL3D_BROWSER", "chromium")
# software WebGL for headless Chromium; the other engines take no such flags
SWIFTSHADER = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] if BROWSER == "chromium" else []


def _new_page(browser, errors):
    page = browser.new_page()
    page.set_default_timeout(90_000)       # CI VMs render WebGL in software; a first click can take a while
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    return page


def _require_3d(page):
    """Skip where the browser could give no WebGL context and the page fell back to 2D at load."""
    if page.evaluate("document.querySelector('input[name=view][value=\"3d\"]').disabled"):
        pytest.skip(f"{BROWSER} has no WebGL here; the page fell back to 2D")


def _launch(p, args=None):
    if BROWSER == "firefox":
        # without a GPU Firefox's blocklist refuses any WebGL context; force its software path
        return p.firefox.launch(firefox_user_prefs={"webgl.force-enabled": True})
    if BROWSER == "webkit":
        return p.webkit.launch()
    return p.chromium.launch(args=SWIFTSHADER if args is None else args)


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
        browser = _launch(p)
        try:
            page = _new_page(browser, errors)
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
        browser = _launch(p)
        try:
            page = _new_page(browser, errors)
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


def _open(p, url, errors, args=None):
    browser = _launch(p, args)
    page = _new_page(browser, errors)
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
            page.wait_for_timeout(600)  # a wrongly fired 400 ms fit would have finished by now
            assert page.evaluate("Graph.zoom()") == zoom                       # the late fit stood down
            page.uncheck("#physics")                    # no precomputed layout: pins where the nodes are
            assert page.evaluate("DATA.nodes.every(n => n.fx === n.x && n.fy === n.y && !('fz' in n))")
        finally:
            browser.close()
    assert errors == []


def test_untouched_force_layout_2d_page_frames_itself_when_the_engine_settles(tmp_path):
    out = tmp_path / "solar-2d-force.html"
    _run_cli(*DEMO, "-o", str(out), "--view", "2d", "--layout", "force")
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors)
        try:
            page.wait_for_function("DATA.nodes.every(n => typeof n.x === 'number')")
            zoom = page.evaluate("Graph.zoom()")
            page.evaluate("window.__stopped = false; const prev = Graph.onEngineStop();"
                          " Graph.onEngineStop(() => { prev(); window.__stopped = true; });"
                          " void Graph.cooldownTicks(30)")
            page.wait_for_function("window.__stopped", timeout=30000)
            page.wait_for_timeout(600)                        # let the 400 ms fit animation finish
            assert page.evaluate("!Graph.__touched")          # nobody pressed or wheeled
            assert page.evaluate("Graph.zoom()") != zoom      # so the late fit framed the graph
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
            _require_3d(page)
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


def test_pinned_2d_canvas_paints_one_frame_per_reheat_and_repaints_on_a_filter_change(tmp_path):
    out = tmp_path / "solar-2d.html"
    _run_cli(*DEMO, "-o", str(out), "--view", "2d")
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors)
        try:
            # every node is pinned, so the engine has nothing to do: it must stop on its first tick
            # instead of redrawing the canvas for the library's 15 s cooldown. The engine may already
            # have stopped before this hook exists (and onRenderFramePre marks nothing dirty), so a
            # reheat starts it at a known moment: one painted frame, then idle
            page.evaluate("window.__frames = 0; void Graph.onRenderFramePre(() => { window.__frames++; })")
            page.evaluate("void Graph.d3ReheatSimulation()")
            page.wait_for_function("window.__frames >= 1", timeout=5000)
            page.wait_for_timeout(1000)
            idle = page.evaluate("window.__frames")
            assert idle <= 2                                      # the stopping frame plus at most one stray
            page.click(".row.grp")
            page.wait_for_function(f"window.__frames > {idle}", timeout=5000)   # restyle2d marked it dirty
        finally:
            browser.close()
    assert errors == []


def test_dragging_a_node_on_a_pinned_2d_page_moves_it_and_leaves_the_canvas_idle(tmp_path):
    out = tmp_path / "solar-2d.html"
    _run_cli(*DEMO, "-o", str(out), "--view", "2d")
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors)
        try:
            page.evaluate("window.__frames = 0; void Graph.onRenderFramePre(() => { window.__frames++; })")
            page.evaluate("window.__hover = null; void Graph.onNodeHover(n => { window.__hover = n ? n.label : null; })")
            page.evaluate("void Graph.d3ReheatSimulation()")
            page.wait_for_function("window.__frames >= 1", timeout=5000)
            before = page.evaluate("(() => { const n = DATA.nodes.find(n => n.label === 'Earth');"
                                   " const s = Graph.graph2ScreenCoords(n.x, n.y); return [n.x, n.y, s.x, s.y]; })()")
            box = page.locator("#graph canvas").first.bounding_box()
            sx, sy = box["x"] + before[2], box["y"] + before[3]
            # the hit-test canvas refreshes at most every 800 ms after a paint: press only once it finds the node
            page.mouse.move(sx, sy)
            page.wait_for_function("window.__hover === 'Earth'", timeout=5000)
            page.mouse.down()
            for i in range(1, 9):
                page.mouse.move(sx + 5 * i, sy + 3 * i)
                page.wait_for_timeout(30)
            page.mouse.up()
            after = page.evaluate("(() => { const n = DATA.nodes.find(n => n.label === 'Earth');"
                                  " return [n.x, n.y, n.fx, n.fy]; })()")
            assert (after[0], after[1]) != (before[0], before[1])              # the node followed the pointer
            assert after[2] == after[0] and after[3] == after[1]                # and stays pinned where it was left
            assert not page.evaluate("document.getElementById('detail').classList.contains('open')")
            page.wait_for_timeout(300)                                          # the post-drag reheat stops
            settled = page.evaluate("window.__frames")
            page.wait_for_timeout(600)
            assert page.evaluate("window.__frames") - settled <= 1              # idle again, not a 15 s cooldown
        finally:
            browser.close()
    assert errors == []


def test_free_float_toggle_restarts_the_simulation_and_pinning_back_stops_it(tmp_path):
    out = tmp_path / "solar-2d.html"
    _run_cli(*DEMO, "-o", str(out), "--view", "2d")
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors)
        try:
            page.wait_for_timeout(300)
            page.evaluate("window.__frames = 0; void Graph.onRenderFramePre(() => { window.__frames++; })")
            page.check("#physics")                                # released: the simulation runs on
            page.wait_for_function("window.__frames > 10", timeout=5000)
            page.uncheck("#physics")                              # pinned back: one repaint, then idle
            page.wait_for_timeout(300)
            settled = page.evaluate("window.__frames")
            page.wait_for_timeout(400)
            assert page.evaluate("window.__frames") - settled <= 1
            assert page.evaluate("DATA.nodes.every(n => n.fx === n.__pos['2d'][0] && n.fy === n.__pos['2d'][1])")
        finally:
            browser.close()
    assert errors == []


def test_pinned_page_stops_the_simulation_on_its_first_tick_in_3d_too(tmp_path):
    out = tmp_path / "solar.html"
    _run_cli(*DEMO, "-o", str(out))
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors)
        try:
            _require_3d(page)
            assert page.evaluate("typeof Graph.scene") == "function"
            # a reheat on a pinned page ends on the next tick, not after the 15 s cooldown
            page.evaluate("window.__stopped = false; Graph.onEngineStop(() => { window.__stopped = true; });"
                          " void Graph.d3ReheatSimulation()")
            page.wait_for_function("window.__stopped", timeout=5000)
        finally:
            browser.close()
    assert errors == []


@pytest.mark.skipif(BROWSER != "chromium", reason="--disable-3d-apis is a Chromium flag")
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
    assert errors == []     # the page asks for WebGL itself, so three.js never logs a failed context


def test_view_switch_keeps_the_filter_and_pins_each_view_to_its_own_layout(tmp_path):
    out = tmp_path / "solar.html"
    _run_cli(*DEMO, "-o", str(out))
    errors = []
    with pw.sync_playwright() as p:
        browser, page = _open(p, out.as_uri(), errors)
        try:
            _require_3d(page)
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
