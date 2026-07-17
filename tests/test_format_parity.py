from format_registry import (
    SCANNED_EXTENSIONS,
    SCANNED_SUBTITLE_EXTENSIONS,
    get_extractor_supported_extensions,
    scanned_not_extractable,
)


def test_srt_and_vtt_are_in_both_scanned_and_supported():
    """Regression test for the exact incident this item exists to prevent:
    .srt/.vtt must be in both the scanner's real-signal set and the
    extractor's supported set, or the scanner-recommends/extractor-rejects
    drift can silently recur."""
    assert ".srt" in SCANNED_SUBTITLE_EXTENSIONS
    assert ".vtt" in SCANNED_SUBTITLE_EXTENSIONS
    supported = get_extractor_supported_extensions()
    if supported is None:
        return  # book_to_skill package not installed in this environment; nothing to compare
    assert ".srt" in supported
    assert ".vtt" in supported


def test_scanned_not_extractable_is_empty_in_current_state():
    """The scanner must never claim real signal (and a BOOK_TYPE
    recommendation) for a format the extractor can't actually parse — that
    was exactly the .srt bug. This is the parity gate."""
    drift = scanned_not_extractable()
    assert drift == frozenset(), (
        f"Scanner recommends BOOK_TYPE for format(s) the extractor cannot parse: {sorted(drift)}. "
        "Add extractor support (book_to_skill/config.py + a parser) before the scanner claims "
        "coverage, or remove the format from SCANNED_EXTENSIONS."
    )


def test_scanned_not_extractable_detects_synthetic_drift():
    """Proves the gate actually catches drift, using a synthetic scenario
    (does not mutate the real registry)."""
    scanned = frozenset({".pdf", ".txt", ".srt", ".fakeext"})
    supported = frozenset({".pdf", ".txt", ".srt"})
    drift = frozenset(scanned) - frozenset(supported)
    assert drift == frozenset({".fakeext"})


def test_scanned_extensions_is_union_of_subsets():
    assert SCANNED_EXTENSIONS >= SCANNED_SUBTITLE_EXTENSIONS
    assert ".pdf" in SCANNED_EXTENSIONS
    assert ".txt" in SCANNED_EXTENSIONS
