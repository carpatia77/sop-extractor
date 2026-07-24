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
import json
import os
import re
import sys
from pathlib import Path

try:
    from format_registry import SCANNED_TEXT_EXTENSIONS, SCANNED_SUBTITLE_EXTENSIONS
except ImportError:
    from scripts.format_registry import SCANNED_TEXT_EXTENSIONS, SCANNED_SUBTITLE_EXTENSIONS

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
# Conversational filler and function words in EN + PT-BR — NOT domain vocabulary
# in any subject. Excluding these from salient_terms() is what keeps the
# analyst_lens proposal pointing at actual domain terms (e.g. "mercado",
# "sinal") instead of generic speech filler ("gente", "cara", "pessoas") that
# dominates raw word-frequency counts in any spoken transcript regardless of
# subject matter.
_STOPWORDS = {
    "the", "and", "that", "this", "with", "for", "you", "your", "are", "was", "not",
    "here", "there", "when", "what", "have", "will", "can", "our", "they", "them",
    "但是",
    "para", "com", "que", "uma", "dos", "das", "por", "como", "mais", "isso", "essa",
    "esse", "essas", "esses", "nessa", "nesse", "nessas", "nesses", "dessa", "desse",
    "dessas", "desses", "voce", "você", "voces", "vocês", "aqui", "então", "entao",
    "quando", "porque", "tem", "muito", "muita", "muitos", "muitas", "assim", "bem",
    "tudo", "toda", "todo", "todos", "todas", "outra", "outro", "outros", "outras",
    "mesmo", "mesma", "sobre", "onde", "quer", "quero", "vai", "vou", "vamos", "veja",
    "vejam", "olha", "olhe", "olhem", "nosso", "nossa", "nossos", "nossas", "pra",
    "pro", "certo", "certeza", "tipo", "cada", "algum", "alguma", "alguns", "algumas",
    "sendo", "acho", "acha", "achar", "gente", "cara", "pessoas", "pessoa", "parte",
    "coisa", "coisas", "vez", "vezes", "esta", "está", "estao", "estão", "estar",
    "exemplo", "exemplos", "entender", "entendeu", "entendendo", "entendi",
    "hoje", "tambem", "também", "agora", "ainda", "depois", "antes",
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
            "error": "pypdf não instalado — instale com: pip install '.[pdf]'",
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
            f"{pages_with_images}/{len(pages)} páginas com imagens — verifique se são diagramas essenciais"
        )
    if pages_with_burst > 0:
        warnings.append(
            f"{pages_with_burst}/{len(pages)} janelas com tabelas colapsadas — revise antes de confiar"
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
            "Sinal incerto — amostra heurística, varredura parcial. "
            "Revise páginas manualmente antes de confirmar BOOK_TYPE."
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
            f"Motivo: {pages_with_images} janela(s) com imagens, "
            f"{pages_with_burst} com tabelas colapsadas."
        )
    else:
        recommendation = suggestion
        recommendation_reason = (
            "Sinal consistente — sem evidência forte de imagens ou tabelas colapsadas."
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


# SUBTITLE_EXTS kept as an alias (same set as format_registry.SCANNED_SUBTITLE_EXTENSIONS)
# for backward compatibility with any external caller referencing this name.
SUBTITLE_EXTS = tuple(sorted(SCANNED_SUBTITLE_EXTENSIONS))

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
    if ext in SCANNED_TEXT_EXTENSIONS:
        return scan_plain_text(path, sample_n=sample_n)
    if ext in SUBTITLE_EXTS:
        return scan_transcript(path, sample_n=sample_n)
    return {
        "suggestion": "text",
        "confidence": "low",
        "recommendation": "text",
        "recommendation_reason": "formato não amostrado — padrão conservador, não um achado.",
        "warnings": [
            f"Formato '{ext}' não amostrado (apenas PDF, .txt/.md, .srt/.vtt). "
            "Se tiver tabelas ou diagramas, escolha technical manualmente."
        ],
    }


def print_report(result: dict, path: str):
    print(f"\n{'─'*50}")
    print("  PRE-FLIGHT SCAN")
    print(f"{'─'*50}")
    print(f"  Arquivo:    {os.path.basename(path)}")

    if "error" in result:
        print(f"  ⚠️  {result['error']}")
        return

    if "total_pages" in result:
        unit = "páginas" if result.get("unit") != "line-window" else "linhas"
        n_sampled = len(result['sampled_pages'])
        total = result['total_pages']
        print(f"  Amostra:    {n_sampled}/{total} {unit}")

        tabular = result['avg_tabular_ratio'] * 100
        burst = result.get('avg_burst_ratio', 0.0) * 100
        images = sum(1 for p in result['pages'] if p['n_images'] > 0)
        print(f"  Sinais:     Tabelas {tabular:.0f}% │ Tabelas colapsadas {burst:.0f}% │ Imagens {images}")

    suggestion = result['suggestion']
    confidence = result['confidence']
    confidence_icon = {"high": "●", "medium": "◐", "low": "○"}.get(confidence, "?")
    confidence_label = {"high": "alta", "medium": "média", "low": "baixa"}.get(confidence, confidence)
    print(f"\n  Detecção:   {suggestion}  {confidence_icon} {confidence_label}")

    for w in result.get("warnings", []):
        print(f"  ⚠  {w}")

    recommendation = result.get("recommendation", result["suggestion"])

    print(f"\n{'─'*50}")
    if result.get("source_kind") == "transcript":
        print("  → RECOMENDAÇÃO: BOOK_TYPE=transcript")
        print("    Fonte é .srt/.vtt — opção 3 do SKILL.md Step 1.5.")
    else:
        print(f"  → RECOMENDAÇÃO: BOOK_TYPE={recommendation}")
        reason = result.get('recommendation_reason', '')
        if reason:
            print(f"    {reason}")
    print(f"{'─'*50}")
    print("  Não é automático — revise antes de confirmar.")

    if result.get("re_candidate"):
        sd = result.get("system_demonstration", {})
        lens = result.get("analyst_lens_suggestion", {})
        print(f"\n{'─'*50}")
        print("  🕶  CANDIDATO A REVERSE-ENGINEERING")
        print(f"{'─'*50}")
        sys_name = sd.get('named_system')
        sys_suffix = f" (x{sd.get('named_system_mentions')})" if sys_name else ""
        print(f"  Deixis UI: {sd.get('ui_deixis', 0)} | Sistema: {sys_name or 'nenhum'}{sys_suffix}")
        print("  [A] Doutrina fiel (default)  [B] Blackhat Mode")
        proposed = lens.get("lens", "systems-architect")
        print(f"  Lente proposta: {proposed}")


def slugify_filename(path: str) -> str:
    """Derives a skill-name slug from a source filename: lowercase, non-
    alphanumeric runs collapsed to single hyphens, trimmed."""
    stem = os.path.splitext(os.path.basename(path))[0]
    slug = re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-')
    return slug or "extracted-skill"


def build_prompt_draft(result: dict, path: str, depth: str = None,
                        skill_name: str = None, skills_home: str = "~/.claude/skills",
                        lineage: str = None, source_date: str = None) -> str:
    """Drafts a ready-to-approve, fully-filled Full Conversion prompt: BOOK_TYPE
    comes from the scan recommendation (a measured finding); DEPTH, name, and
    lineage get sensible, clearly-labeled defaults the scanner cannot verify
    against content (SKILL.md Steps 4, 5, 5.5) — the operator reviews and
    approves/overrides rather than filling blanks from scratch.

    source_date: Optional YYYY-MM-DD from ingestion metadata (upload_date).
                 If provided, included in prompt for provenance tracking.
                 If None, shows placeholder for manual entry."""
    is_transcript = result.get("source_kind") == "transcript"
    recommendation = "transcript" if is_transcript else result.get("recommendation", result.get("suggestion", "text"))
    confidence = result.get("confidence", "unknown")

    depth = depth or "study"
    skill_name = skill_name or slugify_filename(path)
    destino = f"{skills_home.rstrip('/')}/{skill_name}"
    lineage = lineage or "isolada (default)"

    if is_transcript:
        step_1_5_note = (
            "    [medido] Transcript (.srt/.vtt) — opção 3 do Step 1.5."
        )
    else:
        step_1_5_note = f"    [medido] Confiança: {confidence}"

    # Source date for provenance
    if source_date:
        date_line = f"  SOURCE_DATE = {source_date}  [medido da ingestão]"
    else:
        date_line = "  SOURCE_DATE = <preencher>  [não detectado]"

    lines = [
        "Extraia o seguinte documento como skill completa:",
        f'  {path}',
        "",
        "Configuração (auto-detectado + defaults — revise):",
        f"  BOOK_TYPE = {recommendation}  ({step_1_5_note.strip()})",
        f"  DEPTH     = {depth}  [default: study]",
        f"  Nome      = {skill_name}",
        f"  Destino   = {destino}",
        f"  Linhagem  = {lineage}",
        date_line,
    ]

    if result.get("re_candidate"):
        lens = result.get("analyst_lens_suggestion", {})
        proposed = lens.get("lens", "systems-architect")
        lines += [
            "",
            "  Modo Blackhat disponível (RE-candidate).",
            f"  [A] Doutrina fiel (default)  [B] Blackhat Mode (lente: {proposed})",
        ]

    lines += [
        "",
        "Confirma? (S/N)",
    ]
    return "\n".join(lines)


def scan_batch(paths: list, sample_n: int = 5) -> list:
    """Scans multiple sources and returns [(path, result), ...] in the given
    order. Pure orchestration — no new scanning logic, just scan_source per
    path (Item 14.2: batch dispatch for multi-part courses)."""
    return [(p, scan_source(p, sample_n=sample_n)) for p in paths]


def build_multi_part_prompt_draft(results: list, paths: list, depth: str = None,
                                   skill_name: str = None, skills_home: str = "~/.claude/skills",
                                   lineage: str = None) -> str:
    """Drafts one Full Conversion prompt covering all parts of a multi-part
    course, using SKILL.md's existing multi-part convention (PART_ID
    part1..partN, module numbering continues across parts) instead of making
    the operator run --emit-prompt once per file and stitch the answers by
    hand. BOOK_TYPE is taken from the first part and a warning is raised if
    parts disagree, rather than silently picking one."""
    recommendations = []
    for result in results:
        is_transcript = result.get("source_kind") == "transcript"
        recommendations.append("transcript" if is_transcript else result.get("recommendation", result.get("suggestion", "text")))
    recommendation = recommendations[0]
    disagreement = len(set(recommendations)) > 1

    depth = depth or "study"
    skill_name = skill_name or slugify_filename(paths[0])
    destino = f"{skills_home.rstrip('/')}/{skill_name}"
    lineage = lineage or "isolada (default)"

    part_lines = [f'  Parte {i+1}: {p}' for i, p in enumerate(paths)]

    lines = [
        f"Extraia curso multi-parte ({len(paths)} partes):",
        *part_lines,
        "",
        "Configuração (auto-detectado + defaults — revise):",
        f"  BOOK_TYPE = {recommendation}",
    ]
    if disagreement:
        lines.append(f"  ⚠️  Partes divergem ({', '.join(recommendations)}) — confirme manualmente.")
    lines += [
        f"  DEPTH     = {depth}  [default: study]",
        f"  Nome      = {skill_name}",
        f"  Destino   = {destino}",
    ]

    any_re_candidate = any(r.get("re_candidate") for r in results)
    if any_re_candidate:
        lens = next((r.get("analyst_lens_suggestion", {}) for r in results if r.get("re_candidate")), {})
        proposed = lens.get("lens", "systems-architect")
        n_candidates = sum(1 for r in results if r.get("re_candidate"))
        lines += [
            "",
            f"  Modo Blackhat: {n_candidates}/{len(paths)} partes candidatas.",
            f"  [A] Doutrina fiel (default)  [B] Blackhat Mode (lente: {proposed})",
        ]

    lines += [
        "",
        "Confirma? (S/N)",
    ]
    return "\n".join(lines)


def print_batch_report(results: list, paths: list):
    for path, result in results:
        print_report(result, path)
        print()
    if len(paths) > 1:
        print(f"{'─'*50}")
        print(f"  LOTE: {len(paths)} fontes escaneadas como curso multi-parte")
        print(f"{'─'*50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-flight content-type scan for a source.")
    parser.add_argument("source_path", nargs="+",
                         help="Path(s) to the source file(s) (PDF, epub, docx, txt, md...). "
                              "Pass multiple paths for a multi-part course — treated as part1..partN.")
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

    for p in args.source_path:
        if not os.path.isfile(p):
            print(f"Error: file not found: {p}", file=sys.stderr)
            sys.exit(1)

    if len(args.source_path) == 1:
        path = args.source_path[0]
        out = scan_source(path, sample_n=args.sample_n)
        print_report(out, path)

        if args.emit_prompt:
            # Try to read source_date from metadata.json
            source_date = None
            source_dir = Path(path).parent
            meta_path = source_dir / "metadata.json"
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    source_date = meta.get("upload_date")
                except (json.JSONDecodeError, KeyError):
                    pass

            print(f"\n{'─'*50}")
            print("  PROMPT DE EXTRAÇÃO — revise e aprove (S/N)")
            print(f"{'─'*50}\n")
            print(build_prompt_draft(
                out, path,
                depth=args.depth, skill_name=args.skill_name,
                skills_home=args.skills_home, lineage=args.lineage,
                source_date=source_date,
            ))
    else:
        batch = scan_batch(args.source_path, sample_n=args.sample_n)
        print_batch_report(batch, args.source_path)

        if args.emit_prompt:
            results = [r for _, r in batch]
            print(f"\n{'─'*50}")
            print("  PROMPT DE EXTRAÇÃO (multi-parte) — revise e aprove (S/N)")
            print(f"{'─'*50}\n")
            print(build_multi_part_prompt_draft(
                results, args.source_path,
                depth=args.depth, skill_name=args.skill_name,
                skills_home=args.skills_home, lineage=args.lineage,
            ))

    sys.exit(0)
