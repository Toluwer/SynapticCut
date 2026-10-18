#!/usr/bin/env python3
"""Assemble src parts into the single-file index.html plus .dist/app.js for syntax checks.

Parts are concatenated in lexicographic order; filenames use numeric prefixes
(01-, 02-, ...) to make that order explicit and stable.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUT = ROOT / "index.html"
DIST = ROOT / ".dist"


def main() -> int:
    parts = sorted(SRC.glob("*.html"))
    if not parts:
        print("build: no src parts found", file=sys.stderr)
        return 1
    # Assemble in binary: the built file must be byte-identical to the
    # concatenation of its parts (no newline translation).
    raw = b"".join(p.read_bytes() for p in parts)
    OUT.write_bytes(raw)
    html = raw.decode("utf-8")

    DIST.mkdir(exist_ok=True)
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
    js = "\n;\n".join(scripts)
    if "]]>" in js:
        print("build: script content contains ']]>' which breaks XML CDATA wrapping", file=sys.stderr)
        return 1
    (DIST / "app.js").write_text(js, encoding="utf-8")

    print(f"build: {OUT.name} {len(html)} bytes from {len(parts)} parts, "
          f"{len(scripts)} script block(s), app.js {len(js)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
