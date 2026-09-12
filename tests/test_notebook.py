"""examples/ttl3d.ipynb runs as written, offline: its code cells execute in order in this process
(magics stripped, the example files read from the repository instead of GitHub) and the show()
cells produce pages. No nbformat, no kernel, no network. What this does not prove, a front end
rendering the iframe and the published wheel exposing show(), the CI wheel job and the pre-merge
front-end check cover."""
import ast
import json
from pathlib import Path

import ttl3d

REPO = Path(__file__).resolve().parents[1]


def _run_cell(code: str, namespace: dict):
    """Execute a cell; return the value of its last expression, as a notebook would display it."""
    tree = ast.parse(code)
    last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
    exec(compile(tree, "<cell>", "exec"), namespace)  # noqa: S102 -- runs this repo's own notebook
    if last is None:
        return None
    return eval(compile(ast.Expression(last.value), "<cell>", "eval"), namespace)


def test_the_example_notebook_runs_and_shows_pages(monkeypatch):
    nb = json.loads((REPO / "examples" / "ttl3d.ipynb").read_text(encoding="utf-8"))
    monkeypatch.chdir(REPO)             # the notebook reads examples/ locally when it exists
    namespace: dict = {}
    shown = []
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        lines = "".join(cell["source"]).splitlines()
        code = "\n".join(line for line in lines if not line.lstrip().startswith(("%", "!")))
        if not code.strip():
            continue
        value = _run_cell(code, namespace)
        if isinstance(value, ttl3d.Page):
            shown.append(value)
    assert len(shown) == 2
    assert all("<iframe srcdoc=" in p._repr_html_() for p in shown)
    assert '"view": "2d"' in shown[1].html    # the options reached the page
    assert '"colorBy": "type"' in shown[1].html
