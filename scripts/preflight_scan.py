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

# A single short token (number, unit, short label) alone on its own line — the
# signature of a table whose columns collapsed into one cell per line during
# PDF-to-text conversion (column layout lost, but not the content). A lone
# short line doesn't mean much; a *run* of several in a row is the signal.
SHORT_LINE_RE = re.compile(r'^\S{1,20}$')
MIN_BURST_RUN = 4

# --- Reverse-engineering ("Blackhat Mode", Item 11) candidacy signals ---------
# On-screen / UI deixis: the speaker points at something visual instead of
# describing it in words. Multilingual (EN + PT-BR), the two languages this
# pipeline is exercised on; the list is signal, not an exhaustive grammar.
UI_DEIXIS_RES = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\blook at (this|that|here)\b', r'\bas you can see\b', r'\byou can see\b',
        r'\bhere you (can )?see\b', r'\bover here\b', r'\bthis (button|screen|window|panel|chart|column|line)\b',
        r'\bclick (on|here)\b', r'\bright here\b', r'\bon (the|your) screen\b',
        r'\bolh[ae] (aqui|s[óo]|para|isso|aqui\b)', r'\brepara?( n[oa])?\b', r'\bveja( aqui| s[óo]| bem)?\b',
        r'\baqui (no|na|nessa|nesse|em|voc[êe])\b', r'\bnessa tela\b', r'\bna tela\b',
        r'\bclic(a|ar|ando)( aqui| n[oa])?\b', r'\baperta( aqui| n[oa])?\b',
        r'\bseleciona( aqui| n[oa])?\b', r'\bpercebe( n[oa])?\b',
    ]
]

# Outputs presented as objects (a signal/indicator/result shown) rather than
# derived — the frontend of a system whose computation stays hidden.
OUTPUT_MENTION_RES = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\bsignal(s)?\b', r'\bsinal(is|z)?\b', r'\bindicator\b', r'\bindicador(es)?\b',
        r'\boutput(s)?\b', r'\bresultado(s)?\b', r'\balert(a|s)?\b', r'\bsetup(s)?\b',
        r'\bthe system (shows|gives|tells|marks|paints|plots)\b',
        r'\bo sistema (mostra|d[áa]|marca|pinta|plota|indica)\b',
    ]
]

# A named proprietary system: a repeated short ALL-CAPS acronym (ASG, TPO) or a
# repeated Capitalized proper noun that isn't a sentence-start artifact.
ACRONYM_RE = re.compile(r'\b([A-Z]{2,6})\b')
STOP_ACRONYMS = {"PDF", "URL", "API", "CEO", "USA", "OK", "TV", "PC", "ID", "FAQ", "AI", "II", "III", "IV"}
MIN_SYSTEM_MENTIONS = 3
MIN_UI_DEIXIS_FOR_CANDIDATE = 3

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'-]{2,}")
_STOPWORDS = {
    "the", "and", "that", "this", "with", "for", "you", "your", "are", "was", "not",
    "但是", "para", "com", "que", "uma", "dos", "das", "por", "como", "mais", "isso",
    "voce", "você", "aqui", "então", "entao", "quando", "porque", "tem", "the",
    "here", "there", "when", "what", "have", "will", "can", "our", "they", "them",
}


def short_line_burst_ratio(lines: list) -> float:
    """Fraction of (non-empty) lines that belong to a run of at least
    MIN_BURST_RUN consecutive single-token short lines."""
    if not lines:
        return 0.0
    is_short = [bool(SHORT_LINE_RE.match(l.strip())) for l in lines]
    burst_lines = 0
    run = 0
    for s in is_short:
        if s:
            run += 1
        else:
            if run >= MIN_BURST_RUN:
                burst_lines += run
            run = 0
    if run >= MIN_BURST_RUN:
        burst_lines += run
    return burst_lines / len(lines)


def detect_named_system(text: str):
    """Most-repeated ALL-CAPS acronym (excluding common ones) appearing at least
    MIN_SYSTEM_MENTIONS times — the fingerprint of a named proprietary system
    demonstrated in the material. Returns (name, count) or (None, 0)."""
    counts = {}
    for m in ACRONYM_RE.finditer(text):
        tok = m.group(1)
        if tok in STOP_ACRONYMS:
            continue
        counts[tok] = counts.get(tok, 0) + 1
    if not counts:
        return None, 0
    name, count = max(counts.items(), key=lambda kv: kv[1])
    if count >= MIN_SYSTEM_MENTIONS:
        return name, count
    return None, 0


def salient_terms(text: str, top_k: int = 6) -> list:
    """Most frequent non-stopword content terms, lowercased — the source's own
    vocabulary, used to propose (not hardcode) an analyst lens for the operator
    to confirm. Domain-agnostic: no subject keywords are baked in."""
    counts = {}
    for m in _WORD_RE.finditer(text.lower()):
        w = m.group(0)
        if w in _STOPWORDS or len(w) < 4:
            continue
        counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, c in ranked[:top_k] if c > 1]


def propose_analyst_lens(text: str, system_name: str = None) -> dict:
    """Proposes a base analyst lens plus the vocabulary evidence the operator
    uses to sharpen it. Deliberately does NOT guess the domain: the base lens is
    the generic 'systems-architect' (right for reverse-engineering any system),
    and the source's salient terms are surfaced so the human refines it one-key
    (e.g. -> 'quantitative-systems-architect'). Nothing subject-specific is
    hardcoded, preserving agnosticism."""
    evidence = salient_terms(text)
    return {
        "lens": "systems-architect",
        "evidence": evidence,
        "system": system_name,
        "note": ("base lens is generic; sharpen it from the surfaced vocabulary before approving "
                 "(e.g. 'systems-architect' -> '<domain>-systems-architect')"),
    }


def analyze_re_candidacy(text: str) -> dict:
    """Detects whether the material *demonstrates a system* (a reverse-engineering
    candidate) from on-screen deixis, a named system, and outputs-shown-without-
    computation. Candidacy is a content property; the RE ('Blackhat') mode is
    only ever activated by explicit operator declaration, never auto-selected —
    so this only sets a suggestion flag."""
    ui_deixis = sum(len(rx.findall(text)) for rx in UI_DEIXIS_RES)
    output_mentions = sum(len(rx.findall(text)) for rx in OUTPUT_MENTION_RES)
    system_name, system_count = detect_named_system(text)

    re_candidate = (
        ui_deixis >= MIN_UI_DEIXIS_FOR_CANDIDATE
        or (system_name is not None and output_mentions >= 2)
    )
    return {
        "re_candidate": re_candidate,
        "system_demonstration": {
            "ui_deixis": ui_deixis,
            "named_system": system_name,
            "named_system_mentions": system_count,
            "output_mentions": output_mentions,
        },
        "analyst_lens_suggestion": propose_analyst_lens(text, system_name),
    }


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
    tabular/aligned data versus prose, via two independent signals:
    - tabular_line_ratio: lines with multi-space-aligned columns on one line.
    - burst_ratio: runs of single-token lines, the signature of a table whose
      columns collapsed one-cell-per-line during PDF-to-text conversion
      (alignment lost, content intact) — a pattern the first signal can't see."""
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return {"n_lines": 0, "tabular_line_ratio": 0.0, "burst_ratio": 0.0}
    tabular_lines = sum(1 for l in lines if TABULAR_LINE_RE.search(l))
    return {
        "n_lines": len(lines),
        "tabular_line_ratio": tabular_lines / len(lines),
        "burst_ratio": short_line_burst_ratio(lines),
    }


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
        sampled_text_parts = []
        for i in indices:
            page = reader.pages[i]
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            sampled_text_parts.append(text)
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

    result = _summarize(total_pages, indices, pages, any_images)
    result.update(analyze_re_candidacy("\n".join(sampled_text_parts)))
    return result


def _summarize(total_pages: int, sampled_pages: list, pages: list, any_images: bool) -> dict:
    ratios = [p["tabular_line_ratio"] for p in pages if p["n_lines"] > 0]
    avg_tabular_ratio = sum(ratios) / len(ratios) if ratios else 0.0
    burst_ratios = [p.get("burst_ratio", 0.0) for p in pages if p["n_lines"] > 0]
    avg_burst_ratio = sum(burst_ratios) / len(burst_ratios) if burst_ratios else 0.0
    pages_with_images = sum(1 for p in pages if p["n_images"] > 0)
    pages_with_burst = sum(1 for p in pages if p.get("burst_ratio", 0.0) > 0.1)

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
    if pages_with_burst > 0:
        warnings.append(
            f"{pages_with_burst}/{len(pages)} sampled windows contain runs of short, "
            "single-token lines — the signature of a table whose columns collapsed to "
            "one cell per line during PDF-to-text conversion (structure lost, content "
            "intact). If confirmed, choose technical regardless of the overall ratio, "
            "and treat any reconstructed table as needing a provenance check against "
            "the raw source before trusting the row/column pairing the extractor infers."
        )

    is_technical_signal = avg_tabular_ratio > 0.15 or any_images or avg_burst_ratio > 0.1
    if is_technical_signal:
        suggestion = "technical"
        strong = avg_tabular_ratio > 0.3 or pages_with_images >= len(pages) / 2 or avg_burst_ratio > 0.25
        confidence = "high" if strong else "medium"
    else:
        suggestion = "text"
        confidence = "medium" if avg_tabular_ratio < 0.05 and not any_images and avg_burst_ratio < 0.05 else "low"

    if confidence in ("medium", "low"):
        warnings.append(
            "Signal is not strong either way — this is a heuristic sample, not a full-document "
            "scan. Confirm by opening a few more pages by hand before committing to BOOK_TYPE, "
            "especially any pages the table of contents suggests are diagram/exhibit-heavy."
        )

    # The final actionable call is deliberately biased toward `technical` whenever
    # *any* sampled window shows hard evidence (an image, or a burst run) — even if
    # the average across a large, mostly-prose document dilutes that signal below
    # the suggestion threshold above. The two failure costs are not symmetric:
    # choosing `technical` needlessly only costs processing time, while choosing
    # `text` on a source with even sparse load-bearing tables/diagrams silently
    # loses that content, often undiscovered until well after a full run.
    localized_hard_evidence = pages_with_images > 0 or pages_with_burst > 0
    if suggestion == "text" and localized_hard_evidence:
        recommendation = "technical"
        recommendation_reason = (
            f"overriding the raw '{suggestion}' suggestion: {pages_with_images} sampled "
            f"window(s) had embedded images and {pages_with_burst} had collapsed-table "
            "bursts. In a large, mostly-prose document these can dilute the *average* "
            "signal below the auto-suggestion threshold while still being real, "
            "load-bearing content in a minority of the source. Missing that content "
            "silently costs far more than the extra processing time of technical mode."
        )
    else:
        recommendation = suggestion
        recommendation_reason = (
            "matches the raw signal — no localized hard evidence (images or collapsed-"
            "table bursts) was found in the sampled windows beyond what the ratio "
            "already reflects."
        )

    return {
        "total_pages": total_pages,
        "sampled_pages": sampled_pages,
        "pages": pages,
        "any_images": any_images,
        "avg_tabular_ratio": round(avg_tabular_ratio, 3),
        "avg_burst_ratio": round(avg_burst_ratio, 3),
        "suggestion": suggestion,
        "confidence": confidence,
        "recommendation": recommendation,
        "recommendation_reason": recommendation_reason,
        "warnings": warnings,
    }


SUBTITLE_EXTS = (".srt", ".vtt")

SRT_CUE_INDEX_RE = re.compile(r'^\d+$')
SUBTITLE_TIMESTAMP_RE = re.compile(r'\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}')
VTT_HEADER_RE = re.compile(r'^WEBVTT\b')
VTT_META_RE = re.compile(r'^(NOTE|STYLE|REGION)\b')


def strip_subtitle_markup(raw_text: str) -> str:
    """Strips SRT/VTT structure (cue-index numbers, timestamp lines, WEBVTT
    headers, NOTE/STYLE/REGION blocks) down to the spoken-word text, so the
    tabular/burst/re-candidacy heuristics score actual speech instead of being
    diluted or confused by subtitle syntax that isn't prose."""
    out = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if VTT_HEADER_RE.match(stripped) or VTT_META_RE.match(stripped):
            continue
        if SUBTITLE_TIMESTAMP_RE.search(stripped):
            continue
        if SRT_CUE_INDEX_RE.match(stripped):
            continue
        out.append(line)
    return "\n".join(out)


def scan_transcript(path: str, sample_n: int = 5, window_lines: int = 200) -> dict:
    """Samples a subtitle transcript (.srt/.vtt) the same way as plain text,
    after stripping cue indices/timestamps/headers so the heuristics (and the
    Item 11 reverse-engineering candidacy signal) score the spoken words, not
    subtitle syntax. Video-course transcripts are exactly the material Item 11
    targets — a screen-demonstrated system described in spoken words — so this
    format must get real signal, not the generic low-confidence default."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw_text = f.read()

    cleaned = strip_subtitle_markup(raw_text)
    lines = [l + "\n" for l in cleaned.splitlines()]

    total_lines = len(lines)
    if total_lines == 0:
        result = _summarize(0, [], [], any_images=False)
        result["unit"] = "line-window"
        result["source_kind"] = "transcript"
        result.update(analyze_re_candidacy(""))
        return result

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
    result["source_kind"] = "transcript"
    result.update(analyze_re_candidacy(cleaned))
    return result


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
    result.update(analyze_re_candidacy("".join(lines)))
    return result


def scan_source(path: str, sample_n: int = 5) -> dict:
    """Dispatches by file extension. PDF gets true page sampling; plain-text
    formats (.txt/.md) get line-window sampling with the same heuristic;
    subtitle transcripts (.srt/.vtt) get the same line-window sampling after
    stripping cue indices/timestamps, so both the tabular/burst heuristics and
    the Item 11 reverse-engineering candidacy signal get real signal instead
    of the generic low-confidence default — video-course transcripts are
    exactly the material Item 11 targets; other binary formats (epub/docx/
    rtf/mobi) aren't sampled by this tool yet and get a low-confidence default."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return scan_pdf(path, sample_n=sample_n)
    if ext in (".txt", ".md", ".markdown"):
        return scan_plain_text(path, sample_n=sample_n)
    if ext in SUBTITLE_EXTS:
        return scan_transcript(path, sample_n=sample_n)
    return {
        "suggestion": "text",
        "confidence": "low",
        "recommendation": "text",
        "recommendation_reason": "no scanner coverage for this format — this is an unexamined default, not a finding.",
        "warnings": [
            f"'{ext}' sources are not sampled by this tool (only PDF, plain-text "
            ".txt/.md, and subtitle .srt/.vtt are). If this source has embedded "
            "tables, code blocks, or diagrams that carry load-bearing content, "
            "choose technical manually regardless of this default."
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
              f"Avg short-line burst ratio: {result.get('avg_burst_ratio', 0.0)*100:.1f}% | "
              f"Pages with embedded images: {sum(1 for p in result['pages'] if p['n_images'] > 0)}")
    print(f"\nRaw signal suggestion: {result['suggestion']}  (confidence: {result['confidence']})")
    for w in result.get("warnings", []):
        print(f"⚠️  {w}")

    recommendation = result.get("recommendation", result["suggestion"])
    if result.get("source_kind") == "transcript":
        print(f"\n{'='*60}")
        print("RECOMMENDATION: BOOK_TYPE=transcript")
        print(f"{'='*60}")
        print("This is a subtitle transcript (.srt/.vtt) — SKILL.md Step 1.5 option 3 "
              "(video course transcript) applies regardless of the technical/text signal "
              f"above ('{recommendation}'). That signal is a secondary check: rare but real "
              "cases where the speaker reads out a table/formula that a transcript-mode "
              "extractor might flatten — note it for the executor if strong, but BOOK_TYPE "
              "itself is transcript.")
    else:
        print(f"\n{'='*60}")
        print(f"RECOMMENDATION: BOOK_TYPE={recommendation}")
        print(f"Why: {result.get('recommendation_reason', '')}")
        print(f"{'='*60}")
    print("\nThis is a recommendation, not an automatic decision — confirm against "
          "docs/EXTRACTION_PREFLIGHT_CHECKLIST.md before running Full Conversion.")

    if result.get("re_candidate"):
        sd = result.get("system_demonstration", {})
        lens = result.get("analyst_lens_suggestion", {})
        print(f"\n{'='*60}")
        print("🕶  REVERSE-ENGINEERING CANDIDATE (Blackhat Mode available)")
        print(f"{'='*60}")
        sys_name = sd.get('named_system')
        sys_suffix = f" (x{sd.get('named_system_mentions')})" if sys_name else ""
        print(f"Signals: {sd.get('ui_deixis', 0)} on-screen/UI deixis reference(s), "
              f"named system: {sys_name or 'none detected'}{sys_suffix}, "
              f"{sd.get('output_mentions', 0)} output/signal mention(s).")
        print("This material demonstrates a system — you MAY reverse-engineer its backend from the "
              "observable frontend. This is opt-in and never assumed; choose:")
        print("  [A] faithful doctrine only (normal audit -> SKILL.md)          [default]")
        print("  [B] Blackhat Mode: faithful doctrine + reverse-engineering layer "
              "(adds <system>_architecture.md with [OBSERVED]/[INFERRED] seals)")
        proposed = lens.get("lens", "systems-architect")
        evidence = ", ".join(lens.get("evidence", []) or []) or "(no strong vocabulary signal)"
        print(f"Proposed analyst lens (confirm/override one-key): {proposed}")
        print(f"  Derived from source vocabulary: {evidence}")
        print(f"  {lens.get('note', '')}")


def slugify_filename(path: str) -> str:
    """Derives a skill-name slug from a source filename: lowercase, non-
    alphanumeric runs collapsed to single hyphens, trimmed."""
    stem = os.path.splitext(os.path.basename(path))[0]
    slug = re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-')
    return slug or "extracted-skill"


def build_prompt_draft(result: dict, path: str, depth: str = None,
                        skill_name: str = None, skills_home: str = "~/.claude/skills",
                        lineage: str = None) -> str:
    """Drafts a ready-to-approve, fully-filled Full Conversion prompt: BOOK_TYPE
    comes from the scan recommendation (a measured finding); DEPTH, name, and
    lineage get sensible, clearly-labeled defaults the scanner cannot verify
    against content (SKILL.md Steps 4, 5, 5.5) — the operator reviews and
    approves/overrides rather than filling blanks from scratch."""
    is_transcript = result.get("source_kind") == "transcript"
    recommendation = "transcript" if is_transcript else result.get("recommendation", result.get("suggestion", "text"))
    reason = result.get("recommendation_reason", "")
    confidence = result.get("confidence", "unknown")

    depth = depth or "study"
    skill_name = skill_name or slugify_filename(path)
    destino = f"{skills_home.rstrip('/')}/{skill_name}"
    lineage = lineage or (
        "isolated extraction (default — no other Set assumed; override explicitly "
        "if this source belongs to a deliberate lineage/grouping with other sources)"
    )

    if is_transcript:
        secondary = result.get("recommendation", result.get("suggestion", "text"))
        step_1_5_note = (
            f"    [medido] Fonte é um transcript (.srt/.vtt) — SKILL.md Step 1.5 opção 3 se aplica "
            f"independente do sinal técnico secundário ('{secondary}', confidence: {confidence})."
        )
    else:
        step_1_5_note = f"    [medido] Pre-flight scan (confidence: {confidence}). {reason}"

    lines = [
        "Execute a skill book-to-skill para realizar a conversão completa (Full Conversion) do seguinte documento:",
        f'"{path}"',
        "",
        "Respostas (pre-flight scan + defaults — revise antes de aprovar):",
        f"- Step 1.5 (Content Type): BOOK_TYPE={recommendation}",
        step_1_5_note,
        f"- Step 4 (Purpose): DEPTH={depth}",
        "    [default] Assume \"All of the above\" (Option 4) unless you only want quick reference lookup (Option 3 -> DEPTH=reference).",
        f"- Step 5 (Skill Name e Destino): nome=\"{skill_name}\", destino=\"{destino}\"",
        "    [default] Nome derivado do arquivo de origem. Confirme overwrite vs. fold-in/rename se o destino já existir.",
        f"- Step 5.5 (Lineage): {lineage}",
    ]

    if result.get("re_candidate"):
        lens = result.get("analyst_lens_suggestion", {})
        proposed = lens.get("lens", "systems-architect")
        evidence = ", ".join(lens.get("evidence", []) or []) or "(no strong vocabulary signal)"
        lines += [
            "- Item 11 (Reverse-Engineering / Blackhat Mode): material demonstra um sistema (RE-candidate).",
            "    [A] Doutrina fiel apenas (default) — só SKILL.md.",
            "    [B] Blackhat Mode — adiciona <system>_architecture.md com selos [OBSERVED]/[INFERRED].",
            f"    Se [B]: analyst_lens proposta=\"{proposed}\" (derivada do vocabulário: {evidence}) — confirme/ajuste.",
            "    [default] [A] — o modo RE nunca é assumido; só ligue [B] declarando explicitamente.",
        ]

    lines += [
        "",
        "Assuma o Pre-flight Cost Estimate como aprovado e proceda seguindo as restrições de Token Budget.",
        "",
        "Confirma estas escolhas e autoriza a execução? (S/N)",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-flight content-type scan for a source.")
    parser.add_argument("source_path", help="Path to the source file (PDF, epub, docx, txt, md...)")
    parser.add_argument("--sample-n", type=int, default=5, help="Number of pages to sample (PDF only)")
    parser.add_argument("--emit-prompt", action="store_true",
                         help="Also print a ready-to-approve Full Conversion prompt: BOOK_TYPE from "
                              "the recommendation, DEPTH/name/lineage filled with sensible defaults "
                              "(override with --depth/--skill-name/--skills-home/--lineage)")
    parser.add_argument("--depth", choices=["study", "reference"], default=None,
                         help="Override the DEPTH default (study) used in --emit-prompt")
    parser.add_argument("--skill-name", default=None,
                         help="Override the skill name default (derived from the filename) used in --emit-prompt")
    parser.add_argument("--skills-home", default="~/.claude/skills",
                         help="Skill root used to build the destination path in --emit-prompt (default: ~/.claude/skills)")
    parser.add_argument("--lineage", default=None,
                         help="Override the lineage default (isolated extraction) used in --emit-prompt")
    args = parser.parse_args()

    if not os.path.isfile(args.source_path):
        print(f"Error: file not found: {args.source_path}", file=sys.stderr)
        sys.exit(1)

    out = scan_source(args.source_path, sample_n=args.sample_n)
    print_report(out, args.source_path)

    if args.emit_prompt:
        print(f"\n{'='*60}")
        print("FULL CONVERSION PROMPT — review and approve (S/N)")
        print(f"{'='*60}\n")
        print(build_prompt_draft(
            out, args.source_path,
            depth=args.depth, skill_name=args.skill_name,
            skills_home=args.skills_home, lineage=args.lineage,
        ))

    sys.exit(0)
