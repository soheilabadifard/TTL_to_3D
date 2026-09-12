"""Print one version's section of CHANGELOG.md, for the GitHub release notes.

    python tools/release_notes.py 0.3.0 > notes.md

Exit code 1, with a message on stderr, when the changelog has no section for that version, so a
release cannot be created without notes."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def section(changelog: str, version: str) -> str | None:
    """The body under `## <version> (<date>)`, up to the next `## ` heading; None when absent."""
    pattern = rf"^## {re.escape(version)} \([^)]*\)\n(.*?)(?=^## |\Z)"
    m = re.search(pattern, changelog, re.DOTALL | re.MULTILINE)
    return m.group(1).strip() + "\n" if m else None


def main(argv: list[str]) -> int:
    version = argv[0]
    body = section(Path("CHANGELOG.md").read_text(encoding="utf-8"), version)
    if body is None:
        print(f"CHANGELOG.md has no section for {version}", file=sys.stderr)
        return 1
    sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
