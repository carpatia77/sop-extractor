from __future__ import annotations
import re

from book_to_skill.parsers.text import read_text_file

# Mirrors scripts/preflight_scan.py's strip_subtitle_markup — same grammar,
# same rationale: strip SRT/VTT structure (cue-index numbers, timestamp
# lines, WEBVTT headers, NOTE/STYLE/REGION blocks) down to the spoken-word
# text, so the rest of the pipeline (chapter/module summarization) works from
# prose, not subtitle syntax.
SRT_CUE_INDEX_RE = re.compile(r'^\d+$')
SUBTITLE_TIMESTAMP_RE = re.compile(r'\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}')
VTT_HEADER_RE = re.compile(r'^WEBVTT\b')
VTT_META_RE = re.compile(r'^(NOTE|STYLE|REGION)\b')


def strip_subtitle_markup(raw_text: str) -> str:
    """Strips SRT/VTT structure down to the spoken-word text. Kept in sync
    with scripts/preflight_scan.py's function of the same name."""
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


def read_subtitle_file(path: str) -> str | None:
    """Reads a .srt/.vtt file and returns the spoken-word text with subtitle
    structure stripped, or None if the file can't be decoded."""
    raw = read_text_file(path)
    if raw is None:
        return None
    return strip_subtitle_markup(raw)
