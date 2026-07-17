#!/usr/bin/env python3
"""Static HTML viewer for a generated skill (Item 13.4).

Renders a skill directory (SKILL.md, chapters/, optional
<system>_architecture.md, optional determinism_score.json) into ONE
self-contained HTML file — inline CSS, no JS dependency, no server, no build
step — so a generated skill's actual content (provenance tags, [OBSERVED]/
[INFERRED] seals, determinism score) is readable start-to-finish without
opening six separate Markdown files in an editor.

This is intentionally a light markdown-to-HTML pass, not a full CommonMark
renderer — headings, bullet lists, paragraphs, bold/inline-code, and the
seal/provenance badges are enough to make a skill's structure and grounding
visible; it is not meant to reproduce every markdown edge case.
"""

import argparse
import glob
import html
import json
import os
import re
import sys

HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
LIST_ITEM_RE = re.compile(r'^[-*]\s+(.*)$')
BOLD_RE = re.compile(r'\*\*(.+?)\*\*')
INLINE_CODE_RE = re.compile(r'`([^`]+)`')

SEAL_RE = re.compile(r'\[(OBSERVED|INFERRED)\b[^\]]*\]')
PROV_RE = re.compile(r'\[([\w.-]+/\d{4}[^\]]*)\]')


def _slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or "section"


def _inline_format(escaped_line: str) -> str:
    """Applies seal/provenance badges and bold/inline-code to an already
    HTML-escaped line. Order matters: seals first (more specific pattern),
    then generic provenance tags, then bold/code — none of these patterns
    can re-match inside a span already emitted by an earlier pass since the
    brackets are consumed."""
    def seal_sub(m):
        kind = m.group(1)
        cls = "badge-observed" if kind == "OBSERVED" else "badge-inferred"
        return f'<span class="badge {cls}">{m.group(0)}</span>'

    line = SEAL_RE.sub(seal_sub, escaped_line)

    def prov_sub(m):
        return f'<span class="badge badge-prov">[{m.group(1)}]</span>'

    line = PROV_RE.sub(prov_sub, line)
    line = BOLD_RE.sub(r'<strong>\1</strong>', line)
    line = INLINE_CODE_RE.sub(r'<code>\1</code>', line)
    return line


def markdown_lite_to_html(text: str) -> str:
    """Escapes the source, then converts headings/lists/paragraphs and
    seal/provenance badges. Not a full CommonMark implementation — sufficient
    to make a skill's structure and grounding readable in one page."""
    out = []
    list_open = False
    para_lines = []

    def flush_para():
        if para_lines:
            out.append("<p>" + " ".join(para_lines) + "</p>")
            para_lines.clear()

    for raw_line in text.splitlines():
        line = html.escape(raw_line)
        heading_m = HEADING_RE.match(raw_line)
        list_m = LIST_ITEM_RE.match(raw_line)

        if heading_m:
            flush_para()
            if list_open:
                out.append("</ul>")
                list_open = False
            level = len(heading_m.group(1))
            title_raw = heading_m.group(2)
            title = _inline_format(html.escape(title_raw))
            slug = _slugify(title_raw)
            out.append(f'<h{level} id="{slug}">{title}</h{level}>')
            continue

        if list_m:
            flush_para()
            if not list_open:
                out.append("<ul>")
                list_open = True
            item = _inline_format(html.escape(list_m.group(1)))
            out.append(f"<li>{item}</li>")
            continue

        if list_open and not raw_line.strip():
            out.append("</ul>")
            list_open = False

        if not raw_line.strip():
            flush_para()
            continue

        para_lines.append(_inline_format(line))

    flush_para()
    if list_open:
        out.append("</ul>")
    return "\n".join(out)


def extract_headings(markdown_text: str, max_level: int = 2):
    """Returns [(level, title, slug), ...] for nav — headings up to max_level."""
    headings = []
    for raw_line in markdown_text.splitlines():
        m = HEADING_RE.match(raw_line)
        if m and len(m.group(1)) <= max_level:
            title = m.group(2)
            headings.append((len(m.group(1)), title, _slugify(title)))
    return headings


def discover_skill_files(skill_dir: str) -> dict:
    """Locates the standard skill artifacts. Missing optional files (no
    architecture doc, no determinism score) are simply omitted, not an error."""
    skill_md = os.path.join(skill_dir, "SKILL.md")
    chapters_dir = os.path.join(skill_dir, "chapters")
    chapter_files = []
    if os.path.isdir(chapters_dir):
        chapter_files = sorted(
            glob.glob(os.path.join(chapters_dir, "ch*.md")) +
            glob.glob(os.path.join(chapters_dir, "mod*.md"))
        )

    architecture_files = sorted(
        f for f in glob.glob(os.path.join(skill_dir, "*_architecture.md"))
    )

    determinism_path = os.path.join(skill_dir, "determinism_score.json")
    determinism_data = None
    if os.path.isfile(determinism_path):
        try:
            with open(determinism_path, "r", encoding="utf-8") as f:
                determinism_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            determinism_data = None

    return {
        "skill_md": skill_md if os.path.isfile(skill_md) else None,
        "chapters": chapter_files,
        "architecture": architecture_files,
        "determinism": determinism_data,
    }


CSS = """
:root { --bg:#0e1116; --fg:#e6e6e6; --muted:#9aa4b2; --accent:#5aa9e6;
        --observed:#2e7d32; --inferred:#b45309; --prov:#37474f; --card:#161b22; }
* { box-sizing: border-box; }
body { margin:0; display:flex; min-height:100vh; background:var(--bg); color:var(--fg);
       font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; }
nav { width:260px; flex-shrink:0; background:var(--card); padding:1rem; overflow-y:auto;
      border-right:1px solid #263043; }
nav a { display:block; color:var(--muted); text-decoration:none; padding:.25rem 0; font-size:.9rem; }
nav a:hover { color:var(--accent); }
nav .nav-h1 { font-weight:600; color:var(--fg); margin-top:.75rem; }
main { flex:1; padding:2rem 3rem; max-width:900px; }
main section { margin-bottom:3rem; padding-bottom:1rem; border-bottom:1px solid #263043; }
h1,h2,h3 { line-height:1.3; }
code { background:#1c2333; padding:.1rem .3rem; border-radius:3px; font-size:.9em; }
.badge { display:inline-block; padding:.05rem .4rem; border-radius:4px; font-size:.78em;
         font-family: ui-monospace, monospace; margin:0 .1rem; }
.badge-observed { background:var(--observed); color:#e8f5e9; }
.badge-inferred { background:var(--inferred); color:#fff3e0; }
.badge-prov { background:var(--prov); color:#cfd8dc; }
.det-score { display:inline-block; padding:.3rem .8rem; border-radius:6px; background:#1c2333;
             margin-bottom:1rem; font-family: ui-monospace, monospace; }
"""


def render_skill_viewer(skill_dir: str) -> str:
    files = discover_skill_files(skill_dir)
    nav_html = ['<div class="nav-h1">SKILL.md</div>']
    body_sections = []

    if files["skill_md"]:
        with open(files["skill_md"], "r", encoding="utf-8") as f:
            text = f.read()
        for level, title, slug in extract_headings(text):
            nav_html.append(f'<a href="#{slug}">{html.escape(title)}</a>')
        body_sections.append(f'<section id="skill-md">{markdown_lite_to_html(text)}</section>')

    if files["chapters"]:
        nav_html.append('<div class="nav-h1">Chapters</div>')
        for path in files["chapters"]:
            name = os.path.basename(path)
            slug = _slugify(name)
            nav_html.append(f'<a href="#{slug}">{html.escape(name)}</a>')
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            body_sections.append(
                f'<section id="{slug}"><h2>{html.escape(name)}</h2>{markdown_lite_to_html(text)}</section>'
            )

    if files["architecture"]:
        nav_html.append('<div class="nav-h1">Reverse-Engineering</div>')
        for path in files["architecture"]:
            name = os.path.basename(path)
            slug = _slugify(name)
            nav_html.append(f'<a href="#{slug}">🕶 {html.escape(name)}</a>')
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            body_sections.append(
                f'<section id="{slug}"><h2>🕶 {html.escape(name)}</h2>{markdown_lite_to_html(text)}</section>'
            )

    det_html = ""
    det = files["determinism"]
    if det and det.get("book_determinism_pct") is not None:
        pct = det["book_determinism_pct"] * 100
        det_html = f'<div class="det-score">Determinism: {pct:.1f}% SOP-backed</div>'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(os.path.basename(os.path.normpath(skill_dir)))} — skill viewer</title>
<style>{CSS}</style></head>
<body>
<nav>{''.join(nav_html)}</nav>
<main>{det_html}{''.join(body_sections)}</main>
</body></html>
"""


def write_skill_viewer(skill_dir: str, out_path: str = None) -> str:
    out_path = out_path or os.path.join(skill_dir, "viewer.html")
    html_content = render_skill_viewer(skill_dir)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Render a skill directory into one static HTML viewer (Item 13.4).")
    parser.add_argument("skill_dir", help="Path to the skill directory")
    parser.add_argument("--out", default=None, help="Output HTML path (default: <skill_dir>/viewer.html)")
    args = parser.parse_args()

    if not os.path.isdir(args.skill_dir):
        print(f"Error: not a directory: {args.skill_dir}", file=sys.stderr)
        sys.exit(1)

    out_path = write_skill_viewer(args.skill_dir, args.out)
    print(out_path)


if __name__ == "__main__":
    main()
