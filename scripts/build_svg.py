#!/usr/bin/env python3
"""Wrap the built index.html into a self-rendering SVG document.

The output (index.svg) embeds the entire application as XHTML inside an SVG
foreignObject. Served over a CDN (jsDelivr) with Content-Type image/svg+xml,
navigating to the file renders it as a live, script-executing page - no static
host required. The build re-serializes the HTML into strict XML (self-closing
void elements, quoted attributes, escaped text, CDATA-wrapped scripts) and
refuses to write anything that does not re-parse as well-formed XML.
"""
import pathlib
import sys
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
IN = ROOT / "index.html"
OUT = ROOT / "index.svg"

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr", "path", "rect", "circle", "ellipse",
    "line", "polyline", "polygon", "use", "stop",
}


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def esc_attr(value: str) -> str:
    return esc(value).replace('"', "&quot;")


class Extractor(HTMLParser):
    """Collect <style> blocks, body markup, and <script> blocks from an HTML document."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.styles: list[str] = []
        self.scripts: list[str] = []
        self.body: list[str] = []
        self._in_body = False
        self._depth = 0
        self._stack: list[str] = []
        self._buf: list[str] | None = None
        self._mode = None  # None | 'style' | 'script'

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self._in_body = True
            return
        if tag == "style":
            self._mode, self._buf = "style", []
            return
        if tag == "script":
            self._mode, self._buf = "script", []
            return
        if not self._in_body:
            return
        attr_str = "".join(
            f' {k}="{esc_attr(v if v is not None else k)}"' for k, v in attrs
        )
        if tag in VOID:
            self.body.append(f"<{tag}{attr_str}/>")
        else:
            self.body.append(f"<{tag}{attr_str}>")
            self._stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if not self._in_body:
            return
        attr_str = "".join(
            f' {k}="{esc_attr(v if v is not None else k)}"' for k, v in attrs
        )
        self.body.append(f"<{tag}{attr_str}/>")

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            if self._mode == "style":
                self.styles.append("".join(self._buf or []))
            elif self._mode == "script":
                self.scripts.append("".join(self._buf or []))
            self._mode = self._buf = None
            return
        if not self._in_body:
            return
        if tag == "body":
            self._in_body = False
            return
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
            self.body.append(f"</{tag}>")
        elif tag in VOID:
            return  # void element closed redundantly; already self-closed
        else:
            self.body.append(f"</{tag}>")  # tolerate imbalance as-is; XML check will catch real problems

    def handle_data(self, data):
        if self._mode == "style":
            self._buf.append(data)
        elif self._mode == "script":
            self._buf.append(data)
        elif self._in_body:
            self.body.append(esc(data))

    def handle_comment(self, data):
        if self._in_body and "--" not in data:
            self.body.append(f"<!--{data}-->")

    def handle_entityref(self, name):  # pragma: no cover - convert_charrefs handles these
        pass


def build_svg(css: list[str], body: str, scripts: list[str]) -> str:
    style_block = "".join(f"<style>{c}</style>" for c in css)
    script_block = "".join(
        "<script type=\"text/javascript\">\n//<![CDATA[\n"
        + s.strip("\n")
        + "\n//]]>\n</script>"
        for s in scripts
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%">\n'
        "  <title>SynapticCut</title>\n"
        '  <foreignObject x="0" y="0" width="100%" height="100%">\n'
        '    <div xmlns="http://www.w3.org/1999/xhtml" id="sc-xhtml-root" '
        'style="width:100%;height:100%;overflow:hidden">\n'
        f"      {style_block}\n"
        f"      {body}\n"
        f"      {script_block}\n"
        "    </div>\n"
        "  </foreignObject>\n"
        "</svg>\n"
    )


def main() -> int:
    if not IN.exists():
        print("svg: index.html not built yet - run build.py first", file=sys.stderr)
        return 1
    ex = Extractor()
    ex.feed(IN.read_text(encoding="utf-8"))
    ex.close()

    if ex._stack:  # unbalanced markup would produce invalid XML
        print(f"svg: unbalanced tags in body markup: {ex._stack}", file=sys.stderr)
        return 1

    svg = build_svg(ex.styles, "".join(ex.body), ex.scripts)

    try:
        ET.fromstring(svg)
    except ET.ParseError as e:
        bad = ROOT / ".dist" / "index.rejected.svg"
        bad.parent.mkdir(exist_ok=True)
        bad.write_text(svg, encoding="utf-8")
        print(f"svg: XML validation failed ({e}); rejected artifact saved to {bad}", file=sys.stderr)
        return 1

    OUT.write_text(svg, encoding="utf-8")
    print(f"svg: wrote {OUT.name} ({len(svg)} bytes), XML well-formed, "
          f"{len(ex.styles)} style block(s), {len(ex.scripts)} script block(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
