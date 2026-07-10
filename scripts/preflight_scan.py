#!/usr/bin/env python3
"""Content-type pre-flight scanner.

Samples pages spread across a source PDF and produces a BOOK_TYPE
recommendation (with confidence and reasons) before a Full Conversion run,
instead of relying on a human guessing from the first chapter or a filename.
Domain-agnostic: makes no assumption about subject matter, only about
whether the *structure* of the sampled pages (embedded images, tabular
line layout) suggests load-bearing tables/diagrams that a plain-text
extractor would lose.

Uses only the optional `pypdf` dependency already declared in
pyproject.toml's `pdf` extra — no new dependency. Degrades gracefully
(with an explicit "manual check needed" result) if pypdf isn't installed
or the source isn't a PDF.
"""

import argparse
import os
import re
import sys

TABULAR_LINE_RE = re.compile(r'(\S+\s{2,}\S+\s{2,}\S+)|(\d+\s+\d+\s+\d+)')


def sample_page_indices(total_pages: int, sample_n: int = 5) -> list:
    """Evenly-spread page indices across the document (0-indexed), not just the front."""
    if total_pages <= 0:
        return []
    if total_pages <= sample_n:
        return list(range(total_pages))
    step = total_pages / sample_n
    return sorted({int(i * step) for i in range(sample_n)})


def score_page_text(text: str) -> dict:
    """Heuristic signal from one page's extracted text: how much of it reads as
    tabular/aligned data versus prose."""
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return {"n_lines": 0, "tabular_line_ratio": 0.0}
    tabular_lines = sum(1 for l in lines if TABULAR_LINE_RE.search(l))
    return {"n_lines": len(lines), "tabular_line_ratio": tabular_lines / len(lines)}


def scan_pdf(path: str, sample_n: int = 5) -> dict:
    """Samples pages spread across the PDF and returns a BOOK_TYPE recommendation.

    Returns a dict with: total_pages, sampled_pages, pages (per-page stats),
    any_images (bool), avg_tabular_ratio, suggestion, confidence, warnings.
    """
    try:
        import pypdf
    except ImportError:
        return {
            "error": "pypdf not installed — cannot auto-scan. Install the 'pdf' extra "
                     "(pip install '.[pdf]') or inspect the source manually using the "
                     "checklist in docs/EXTRACTION_PREFLIGHT_CHECKLIST.md.",
            "suggestion": None,
            "confidence": "none",
        }

    with open(path, "rb") as f:
        reader = pypdf.PdfReader(f)
        total_pages = len(reader.pages)
        indices = sample_page_indices(total_pages, sample_n)

        pages = []
        any_images = False
        for i in indices:
            page = reader.pages[i]
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            try:
                n_images = len(page.images)
            except Exception:
                n_images = 0
            if n_images > 0:
                any_images = True
            stats = score_page_text(text)
            stats["page_index"] = i
            stats["n_images"] = n_images
            pages.append(stats)

    return _summarize(total_pages, indices, pages, any_images)


def _summarize(total_pages: int, sampled_pages: list, pages: list, any_images: bool) -> dict:
    ratios = [p["tabular_line_ratio"] for p in pages if p["n_lines"] > 0]
    avg_tabular_ratio = sum(ratios) / len(ratios) if ratios else 0.0
    pages_with_images = sum(1 for p in pages if p["n_images"] > 0)

    warnings = []
    if pages_with_images > 0:
        warnings.append(
            f"{pages_with_images}/{len(pages)} sampled pages contain embedded images. "
            "Verify manually whether these are load-bearing diagrams/tables (central to "
            "the book's argument) or incidental illustration. If load-bearing, choose "
            "technical regardless of how prose-heavy the rest of the book reads — a "
            "plain-text extractor will not preserve them, and if they are rasterized "
            "images, no BOOK_TYPE recovers them; document that gap upfront."
        )

    if avg_tabular_ratio > 0.15 or any_images:
        suggestion = "technical"
        confidence = "high" if (avg_tabular_ratio > 0.3 or pages_with_images >= len(pages) / 2) else "medium"
    else:
        suggestion = "text"
        confidence = "medium" if avg_tabular_ratio < 0.05 and not any_images else "low"

    if confidence in ("medium", "low"):
        warnings.append(
            "Signal is not strong either way — this is a heuristic sample, not a full-document "
            "scan. Confirm by opening a few more pages by hand before committing to BOOK_TYPE, "
            "especially any pages the table of contents suggests are diagram/exhibit-heavy."
        )

    return {
        "total_pages": total_pages,
        "sampled_pages": sampled_pages,
        "pages": pages,
        "any_images": any_images,
        "avg_tabular_ratio": round(avg_tabular_ratio, 3),
        "suggestion": suggestion,
        "confidence": confidence,
        "warnings": warnings,
    }


def scan_plain_text(path: str, sample_n: int = 5, window_lines: int = 200) -> dict:
    """Samples fixed-size line windows spread across a plain-text file (.txt/.md)
    using the same tabular-line heuristic as scan_pdf. No image signal is
    possible for plain text, so the suggestion leans on tabular_line_ratio alone."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    total_lines = len(lines)
    if total_lines == 0:
        return _summarize(0, [], [], any_images=False)

    n_windows = min(sample_n, max(1, total_lines // window_lines)) or 1
    indices = sample_page_indices(max(total_lines - window_lines, 0) + 1, n_windows) or [0]

    pages = []
    for start in indices:
        chunk = "".join(lines[start:start + window_lines])
        stats = score_page_text(chunk)
        stats["page_index"] = start
        stats["n_images"] = 0
        pages.append(stats)

    result = _summarize(total_lines, indices, pages, any_images=False)
    result["unit"] = "line-window"
    return result


def scan_source(path: str, sample_n: int = 5) -> dict:
    """Dispatches by file extension. PDF gets true page sampling; plain-text
    formats (.txt/.md) get line-window sampling with the same heuristic;
    other binary formats (epub/docx/rtf/mobi) aren't sampled by this tool yet
    and get a low-confidence default."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return scan_pdf(path, sample_n=sample_n)
    if ext in (".txt", ".md", ".markdown"):
        return scan_plain_text(path, sample_n=sample_n)
    return {
        "suggestion": "text",
        "confidence": "low",
        "warnings": [
            f"'{ext}' sources are not sampled by this tool (only PDF and plain-text "
            ".txt/.md are). If this source has embedded tables, code blocks, or "
            "diagrams that carry load-bearing content, choose technical manually "
            "regardless of this default."
        ],
    }


def print_report(result: dict, path: str):
    print(f"=== Pre-flight content-type scan: {path} ===")
    if "error" in result:
        print(f"⚠️  {result['error']}")
        return
    if "total_pages" in result:
        unit = "line" if result.get("unit") == "line-window" else "page"
        print(f"Sampled {len(result['sampled_pages'])} {unit}-window(s) out of "
              f"{result['total_pages']} total {unit}s (start indices {result['sampled_pages']}).")
        print(f"Avg tabular-line ratio: {result['avg_tabular_ratio']*100:.1f}% | "
              f"Pages with embedded images: {sum(1 for p in result['pages'] if p['n_images'] > 0)}")
    print(f"\nSuggested BOOK_TYPE: {result['suggestion']}  (confidence: {result['confidence']})")
    for w in result.get("warnings", []):
        print(f"⚠️  {w}")
    print("\nThis is a suggestion, not an automatic decision — confirm against "
          "docs/EXTRACTION_PREFLIGHT_CHECKLIST.md before running Full Conversion.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-flight content-type scan for a source.")
    parser.add_argument("source_path", help="Path to the source file (PDF, epub, docx, txt, md...)")
    parser.add_argument("--sample-n", type=int, default=5, help="Number of pages to sample (PDF only)")
    args = parser.parse_args()

    if not os.path.isfile(args.source_path):
        print(f"Error: file not found: {args.source_path}", file=sys.stderr)
        sys.exit(1)

    out = scan_source(args.source_path, sample_n=args.sample_n)
    print_report(out, args.source_path)
    sys.exit(0)
