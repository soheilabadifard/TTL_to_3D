"""Write LICENSES.md for every runtime package in package-lock.json.

    python tools/licenses.py <build dir with node_modules> ttl3d/vendor/LICENSES.md

MIT and ISC both require the copyright notice to travel with copies, and the bundle
inlines every runtime package of the lockfile, so each one gets a line. A package under
any other licence stops the script: add that licence's text below before rerunning.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MIT = """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE."""

ISC = """Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE."""

BSD_3_CLAUSE = """Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the author nor the names of contributors may be used to
  endorse or promote products derived from this software without specific prior
  written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."""

TEXTS = {"MIT": ("The MIT License", MIT), "ISC": ("The ISC License", ISC),
         "BSD-3-Clause": ("The BSD 3-Clause License", BSD_3_CLAUSE)}
LICENSE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "LICENCE.md", "license", "License.txt")


def copyright_line(pkg_dir: Path, author) -> str:
    for name in LICENSE_FILES:
        f = pkg_dir / name
        if f.exists():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if "copyright" in line.lower():
                    return line.strip()
    if isinstance(author, dict):
        author = author.get("name", "")
    return f"Copyright (c) {author}" if author else "(no copyright line in the package)"


def main(build_dir: str, out: str) -> None:
    lock = json.loads((Path(build_dir) / "package-lock.json").read_text(encoding="utf-8"))
    rows: dict[str, list[str]] = {}
    for path, meta in sorted(lock["packages"].items()):
        if not path or meta.get("dev"):
            continue
        name = path.split("node_modules/")[-1]
        pkg = json.loads((Path(build_dir) / path / "package.json").read_text(encoding="utf-8"))
        lic = meta.get("license") or pkg.get("license")
        if lic not in TEXTS:
            sys.exit(f"{name}: licence {lic!r} has no text in licenses.py; add it before rerunning")
        cr = copyright_line(Path(build_dir) / path, pkg.get("author"))
        rows.setdefault(lic, []).append(f"- {name} {meta['version']} — {cr}")
    lines = ["# Licenses of the vendored libraries", "",
             "`fg-bundle.min.js` inlines every package listed here. The list is generated from",
             "`package-lock.json` by `tools/licenses.py` (see the recipe in `VENDOR.md`); regenerate it",
             "whenever the bundle is rebuilt. The licence texts follow the list.", ""]
    for lic in sorted(rows):
        lines += [f"## {lic}", "", *rows[lic], ""]
    for lic in sorted(rows):
        title, text = TEXTS[lic]
        lines += [f"## {title}", "", text, ""]
    Path(out).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
