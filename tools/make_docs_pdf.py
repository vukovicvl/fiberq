#!/usr/bin/env python3
"""Render the published docs as PDFs for fiberq.net.

Dev-only tooling. WeasyPrint is a repo-root dependency and must never reach the
plugin zip -- the plugin itself exports HTML, JSON and CSV, and that is
deliberate: a QGIS plugin cannot carry a PDF engine's native libraries across
three operating systems. Everything here runs from the repo root, in the root
virtualenv, and writes to ``dist/docs/``, which is gitignored.

Usage:
    .venv/bin/python tools/make_docs_pdf.py            # every guide
    .venv/bin/python tools/make_docs_pdf.py docs/i18n.md  # just these

The Markdown is the source of truth. Nothing is written back into docs/, and
the PDF is a rendering of the committed file, not a separate document that can
drift from it.
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = ROOT / "dist" / "docs"

#: The documents published on the website, in reading order. Anything not
#: listed here is internal or generated, and is not offered as a download.
PUBLISHED = [
    "interchange-guide.md",
    "interchange-format.md",
    "interchange-mapping.md",
    "validation-guide.md",
    "validation-rules.md",
    "project-versioning-guide.md",
    "schema.md",
    "TRANSLATING.md",
]

#: The filename each document is published under on fiberq.net. The site has
#: used Title-Case FiberQ-prefixed names since the first grant deliverable, and
#: the links are already out in payment requests and release notes -- so the
#: renaming happens here, once, rather than by hand on every upload.
WEB_NAMES = {
    "interchange-guide": "FiberQ-Interchange-Guide",
    "interchange-format": "FiberQ-Interchange-Format-Specification",
    "interchange-mapping": "FiberQ-Interchange-Field-Mapping",
    "validation-guide": "FiberQ-Validation-Guide",
    "validation-rules": "FiberQ-Validation-Rules-Reference",
    "project-versioning-guide": "FiberQ-Project-Versioning-Guide",
    "schema": "FiberQ-Schema-Reference",
    "TRANSLATING": "FiberQ-Translator-Guide",
}

#: Print stylesheet. Deliberately plain: these are reference documents that get
#: read on screen, printed on office paper and emailed to a client, so they use
#: a serif body at a size that survives all three, and no colour that turns to
#: mud in greyscale.
CSS = """
@page {
    size: A4;
    margin: 22mm 20mm 20mm 20mm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-family: "DejaVu Sans", sans-serif;
        font-size: 8pt;
        color: #767676;
    }
    @bottom-left {
        content: "FiberQ — __FOOTER__";
        font-family: "DejaVu Sans", sans-serif;
        font-size: 8pt;
        color: #767676;
    }
}
@page :first { @bottom-left { content: ""; } @bottom-center { content: ""; } }

html { font-size: 10.5pt; }
body {
    font-family: "DejaVu Serif", Georgia, serif;
    line-height: 1.52;
    color: #1a1a1a;
    hyphens: auto;
}
h1, h2, h3, h4 {
    font-family: "DejaVu Sans", Helvetica, sans-serif;
    line-height: 1.25;
    color: #111;
    page-break-after: avoid;
}
h1 {
    font-size: 21pt;
    margin: 0 0 4pt;
    padding-bottom: 8pt;
    border-bottom: 2.5pt solid #1a7f5a;
}
h2 {
    font-size: 14pt;
    margin: 20pt 0 6pt;
    padding-top: 4pt;
    border-top: 0.5pt solid #d8d8d8;
}
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; }
h4 { font-size: 10.5pt; margin: 12pt 0 3pt; font-style: italic; }
p, ul, ol, table { page-break-inside: avoid; }
p { margin: 0 0 7pt; text-align: justify; }
ul, ol { margin: 0 0 8pt; padding-left: 16pt; }
li { margin-bottom: 3pt; }

a { color: #10553c; text-decoration: none; border-bottom: 0.4pt solid #b7d6c8; }

code {
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 0.86em;
    background: #f2f4f3;
    padding: 0.5pt 2pt;
    border-radius: 2pt;
}
pre {
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 8.2pt;
    line-height: 1.38;
    background: #f6f8f7;
    border-left: 2.5pt solid #1a7f5a;
    padding: 7pt 9pt;
    margin: 0 0 9pt;
    white-space: pre-wrap;
    word-wrap: break-word;
    page-break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: inherit; }

blockquote {
    margin: 0 0 9pt;
    padding: 6pt 10pt;
    background: #f7f7f4;
    border-left: 2.5pt solid #c8b273;
}
blockquote p:last-child { margin-bottom: 0; }

table {
    border-collapse: collapse;
    width: 100%;
    margin: 0 0 10pt;
    font-size: 9pt;
    font-family: "DejaVu Sans", sans-serif;
}
th, td {
    border: 0.4pt solid #ccc;
    padding: 3.5pt 5pt;
    text-align: left;
    vertical-align: top;
}
th { background: #eef2f0; font-weight: 600; }
tr:nth-child(even) td { background: #fafafa; }

hr { border: none; border-top: 0.5pt solid #ddd; margin: 14pt 0; }

.subject {
    font-family: "DejaVu Sans", sans-serif;
    font-size: 8.5pt;
    color: #767676;
    margin: 0 0 16pt;
}
"""

HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title></head>
<body>
__BODY__
</body></html>
"""


def _relative_links_to_absolute(html, base_url):
    """Point cross-document links at the published copies.

    A link to ``validation-rules.md`` is meaningless in a PDF. Readers of the
    PDF get the file on GitHub, which is where the current version always is.
    """
    def fix(match):
        href = match.group(1)
        if href.startswith(("http://", "https://", "#", "mailto:")):
            return match.group(0)
        anchor = ""
        if "#" in href:
            href, anchor = href.split("#", 1)
            anchor = "#" + anchor
        return f'href="{base_url}{href}{anchor}"'

    return re.sub(r'href="([^"]+)"', fix, html)


def render(md_path, out_dir=OUT, base_url=None):
    """Render one Markdown file to a PDF and return the output path."""
    try:
        import markdown
        from weasyprint import CSS as WeasyCSS, HTML as WeasyHTML
    except ImportError as e:
        raise SystemExit(
            f"{e}. This is dev-only tooling and its dependencies are not part "
            "of the plugin. Install them in the root virtualenv:\n"
            "    .venv/bin/pip install weasyprint markdown")

    base_url = base_url or "https://github.com/vukovicvl/fiberq/blob/main/docs/"
    text = md_path.read_text(encoding="utf-8")

    # The first heading is the document's name; everything else is content.
    first_line = text.lstrip().splitlines()[0] if text.strip() else md_path.stem
    title = first_line.lstrip("# ").strip() or md_path.stem
    footer = title.split("—")[-1].strip() if "—" in title else title

    body = markdown.markdown(
        text,
        extensions=["extra", "sane_lists", "toc"],
        output_format="html5",
    )
    body = _relative_links_to_absolute(body, base_url)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (WEB_NAMES.get(md_path.stem, md_path.stem) + ".pdf")
    # str.replace, not %-formatting: the CSS contains "width: 100%" and the
    # rendered body contains percentages of its own, both of which a format
    # string would try to interpret.
    page = HTML.replace("__TITLE__", title).replace("__BODY__", body)
    WeasyHTML(string=page, base_url=str(md_path.parent)).write_pdf(
        out_path, stylesheets=[WeasyCSS(string=CSS.replace("__FOOTER__", footer))])
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "paths", nargs="*",
        help="Markdown files to render (default: the published set)")
    parser.add_argument(
        "--out", default=str(OUT), help="output directory (default: dist/docs)")
    args = parser.parse_args(argv)

    if args.paths:
        targets = [pathlib.Path(p).resolve() for p in args.paths]
    else:
        targets = [DOCS / name for name in PUBLISHED]

    missing = [t for t in targets if not t.is_file()]
    if missing:
        for path in missing:
            print(f"not found: {path}", file=sys.stderr)
        return 1

    out_dir = pathlib.Path(args.out).resolve()
    for target in targets:
        out_path = render(target, out_dir)
        size = out_path.stat().st_size
        print(f"{target.relative_to(ROOT)}  ->  "
              f"{out_path.relative_to(ROOT)}  ({size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
