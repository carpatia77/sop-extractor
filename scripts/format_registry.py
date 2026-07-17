"""Single source of truth for "formats this tool has real scanning coverage
for" (Item 13.2). Exists to prevent the class of bug fixed this week: the
pre-flight scanner recommended BOOK_TYPE=transcript for .srt/.vtt while the
extraction pipeline (book_to_skill package) rejected those same files outright
with "Unsupported format" — two independent, hand-copied literal lists that
silently drifted apart.

scripts/preflight_scan.py imports SCANNED_EXTENSIONS from here instead of
hardcoding format literals in its dispatch. tests/test_format_parity.py
verifies every scanned format is also extractor-supported — the direction
that actually caused the incident. (The reverse — an extractor format the
scanner doesn't sample, e.g. epub/docx — is allowed; those already get a
documented low-confidence default, not a bug.)
"""

SCANNED_PDF_EXTENSIONS = frozenset({".pdf"})
SCANNED_TEXT_EXTENSIONS = frozenset({".txt", ".md", ".markdown"})
SCANNED_SUBTITLE_EXTENSIONS = frozenset({".srt", ".vtt"})

# Everything preflight_scan.py samples with real signal (not the generic
# low-confidence default).
SCANNED_EXTENSIONS = SCANNED_PDF_EXTENSIONS | SCANNED_TEXT_EXTENSIONS | SCANNED_SUBTITLE_EXTENSIONS


def get_extractor_supported_extensions():
    """Returns the book_to_skill package's SUPPORTED_EXTENSIONS, or None if
    the package isn't installed/importable — the parity check should skip,
    not fail, in that case (scripts/ is usable standalone without the
    installed package)."""
    try:
        from book_to_skill.config import SUPPORTED_EXTENSIONS
        return SUPPORTED_EXTENSIONS
    except ImportError:
        return None


def scanned_not_extractable() -> frozenset:
    """Formats the scanner recommends a BOOK_TYPE for for that the extractor
    cannot actually parse — the failure direction that caused the .srt
    incident. Empty set means no drift; returns frozenset() (not an error)
    when the package isn't installed, since there's nothing to compare against."""
    supported = get_extractor_supported_extensions()
    if supported is None:
        return frozenset()
    return frozenset(SCANNED_EXTENSIONS) - frozenset(supported)
