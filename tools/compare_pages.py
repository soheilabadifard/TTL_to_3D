"""Compare the pages other machines built against the ones in the first directory.

    python tools/compare_pages.py <dir> <dir> [<dir> ...]

Every directory holds the same page file names, each set built on one platform. The pages
must be byte-identical except for the pinned layout coordinates ("x", "y", "z", "x2", "y2"
in the embedded DATA), which Kamada-Kawai lets drift by a few tenths across scipy and BLAS
builds while the shape stays the same. Exit code 1 when a page differs anywhere else, is
missing, or drifts beyond the tolerance.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

COORD = re.compile(r'"(x|y|z|x2|y2)": (-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)')
TOLERANCE = 1.0   # layout units; the force rest length is about 60


def strip_coordinates(text: str) -> tuple[str, list[float]]:
    """Mask every pinned coordinate with `#` and return the masked text plus the numbers in order."""
    coords: list[float] = []

    def mask(m: re.Match) -> str:
        coords.append(float(m.group(2)))
        return f'"{m.group(1)}": #'

    return COORD.sub(mask, text), coords


def compare(reference: str, other: str, tolerance: float = TOLERANCE) -> tuple[bool, str]:
    """(ok, note): identical, or equal up to a coordinate drift within `tolerance`."""
    if reference == other:
        return True, "identical"
    ref_text, ref_coords = strip_coordinates(reference)
    oth_text, oth_coords = strip_coordinates(other)
    if ref_text != oth_text:
        at = next((i for i, (a, b) in enumerate(zip(ref_text, oth_text)) if a != b),
                  min(len(ref_text), len(oth_text)))
        lo = max(0, at - 12)
        return False, (f"differs beyond coordinates at offset {at}: "
                       f"{ref_text[lo:at + 28]!r} vs {oth_text[lo:at + 28]!r}")
    drift = max((abs(a - b) for a, b in zip(ref_coords, oth_coords)), default=0.0)
    if drift > tolerance:
        return False, f"coordinates drift by up to {drift:.2f}, above the tolerance of {tolerance:.2f}"
    return True, f"coordinates drift by up to {drift:.2f}"


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as f:   # newline="" keeps a CR visible
        return f.read()


def main(dirs: list[str]) -> int:
    first, *others = (Path(d) for d in dirs)
    failed = False
    for page in sorted(p.name for p in first.iterdir() if p.is_file()):
        reference = _read(first / page)
        for d in others:
            if not (d / page).is_file():
                print(f"{page}: missing in {d.name}")
                failed = True
                continue
            ok, note = compare(reference, _read(d / page))
            print(f"{page}: {first.name} vs {d.name}: {note}")
            failed |= not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
