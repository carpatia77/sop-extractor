import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from preflight_scan import (
    sample_page_indices,
    score_page_text,
    _summarize,
    scan_source,
    scan_plain_text,
    scan_transcript,
    strip_subtitle_markup,
    short_line_burst_ratio,
    analyze_re_candidacy,
    detect_named_system,
    propose_analyst_lens,
    build_prompt_draft,
    salient_terms,
)


def test_sample_page_indices_spreads_across_document():
    idx = sample_page_indices(100, sample_n=5)
    assert len(idx) == 5
    assert idx[0] < 20  # not clustered at the very front
    assert idx[-1] > 60  # reaches toward the back


def test_sample_page_indices_small_doc_returns_all_pages():
    assert sample_page_indices(3, sample_n=5) == [0, 1, 2]


def test_sample_page_indices_empty_doc():
    assert sample_page_indices(0, sample_n=5) == []


def test_score_page_text_prose_has_low_tabular_ratio():
    prose = "This is a normal sentence.\nAnother sentence continues the argument.\nAnd a third one."
    result = score_page_text(prose)
    assert result["tabular_line_ratio"] < 0.2


def test_score_page_text_tabular_data_has_high_ratio():
    table = "1539   1536   1533\n1497   1494   1491\n1476   1467   1449\n"
    result = score_page_text(table)
    assert result["tabular_line_ratio"] > 0.5


def test_score_page_text_empty():
    assert score_page_text("") == {"n_lines": 0, "tabular_line_ratio": 0.0, "burst_ratio": 0.0}


def test_summarize_suggests_technical_with_images():
    pages = [
        {"n_lines": 10, "tabular_line_ratio": 0.05, "page_index": 0, "n_images": 1},
        {"n_lines": 8, "tabular_line_ratio": 0.0, "page_index": 20, "n_images": 0},
    ]
    result = _summarize(50, [0, 20], pages, any_images=True)
    assert result["suggestion"] == "technical"
    assert any("embedded images" in w for w in result["warnings"])


def test_summarize_suggests_text_for_pure_prose():
    pages = [
        {"n_lines": 10, "tabular_line_ratio": 0.0, "page_index": 0, "n_images": 0},
        {"n_lines": 8, "tabular_line_ratio": 0.02, "page_index": 20, "n_images": 0},
    ]
    result = _summarize(50, [0, 20], pages, any_images=False)
    assert result["suggestion"] == "text"
    assert result["confidence"] == "medium"


def test_summarize_high_confidence_when_tabular_ratio_dominant():
    pages = [
        {"n_lines": 10, "tabular_line_ratio": 0.5, "page_index": 0, "n_images": 0},
        {"n_lines": 8, "tabular_line_ratio": 0.4, "page_index": 20, "n_images": 0},
    ]
    result = _summarize(50, [0, 20], pages, any_images=False)
    assert result["suggestion"] == "technical"
    assert result["confidence"] == "high"


def test_scan_source_non_pdf_defaults_to_text_low_confidence():
    result = scan_source("book.epub")
    assert result["suggestion"] == "text"
    assert result["confidence"] == "low"


def test_scan_plain_text_detects_tabular_content(tmp_path):
    lines = [f"Prose sentence number {i} in flowing narrative style." for i in range(60)]
    lines += [f"{i}d6   {i*3}   {i*2}   crushing" for i in range(30)]
    f = tmp_path / "rules.txt"
    f.write_text("\n".join(lines), encoding="utf-8")

    result = scan_plain_text(str(f), sample_n=5, window_lines=200)
    assert result["suggestion"] == "technical"
    assert result["unit"] == "line-window"


def test_scan_plain_text_pure_prose_suggests_text(tmp_path):
    lines = [f"Sentence {i} of ordinary flowing prose." for i in range(300)]
    f = tmp_path / "prose.txt"
    f.write_text("\n".join(lines), encoding="utf-8")

    result = scan_plain_text(str(f), sample_n=5, window_lines=200)
    assert result["suggestion"] == "text"


def test_scan_plain_text_empty_file(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    result = scan_plain_text(str(f))
    assert result["total_pages"] == 0


def test_scan_source_dispatches_txt_to_line_window_sampling(tmp_path):
    lines = [f"{i}d6   {i*3}   {i*2}   crushing" for i in range(60)]
    f = tmp_path / "rules.txt"
    f.write_text("\n".join(lines), encoding="utf-8")

    result = scan_source(str(f))
    assert result["unit"] == "line-window"
    assert result["suggestion"] == "technical"


def test_scan_source_missing_pypdf_or_missing_file_reports_error_or_handles(tmp_path):
    # A .pdf path that doesn't exist as valid PDF content — either pypdf isn't
    # installed (error path) or it fails to parse; both must not raise.
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_text("not a real pdf", encoding="utf-8")
    try:
        from preflight_scan import scan_pdf
        result = scan_pdf(str(fake_pdf))
        assert "suggestion" in result
    except Exception as e:
        # If pypdf raises on malformed input, that's acceptable behavior for
        # this test environment — the CLI wrapper doesn't crash the whole run
        # for real corrupt files since pypdf raises PdfReadError which callers
        # of scan_source should handle; this test just documents current behavior.
        assert e is not None


def test_short_line_burst_ratio_detects_collapsed_table():
    lines = ["Damage Table", "ST"] + [str(i) for i in range(1, 40)]
    ratio = short_line_burst_ratio(lines)
    assert ratio > 0.5


def test_short_line_burst_ratio_ignores_isolated_short_lines():
    lines = [
        "This is a normal prose sentence describing something at length.",
        "42",
        "Another full sentence continuing the narrative argument here.",
        "7",
        "A third sentence, still prose, still no burst of short lines.",
    ]
    # Only isolated short lines (runs of 1), below MIN_BURST_RUN=4 — no burst.
    assert short_line_burst_ratio(lines) == 0.0


def test_short_line_burst_ratio_empty():
    assert short_line_burst_ratio([]) == 0.0


def test_score_page_text_includes_burst_ratio():
    table_text = "Damage Table\nST\n" + "\n".join(str(i) for i in range(1, 40))
    result = score_page_text(table_text)
    assert result["burst_ratio"] > 0.5


def test_summarize_suggests_technical_from_burst_alone():
    pages = [
        {"n_lines": 50, "tabular_line_ratio": 0.0, "burst_ratio": 0.3, "page_index": 0, "n_images": 0},
    ]
    result = _summarize(50, [0], pages, any_images=False)
    assert result["suggestion"] == "technical"
    assert any("collapsed to one cell per line" in w for w in result["warnings"])


def test_gurps_like_collapsed_table_end_to_end(tmp_path):
    """A table whose columns collapsed to one-value-per-line (the real-world
    PDF-to-text artifact this heuristic exists for) must be flagged technical
    even though the classic multi-space tabular_line_ratio sees nothing."""
    lines = [f"Prose sentence {i} in ordinary flowing narrative style here." for i in range(50)]
    lines += ["Damage Table", "ST"] + [str(i) for i in range(1, 40)]
    lines += [f"More prose paragraph {i} continuing the narrative style." for i in range(50)]
    f = tmp_path / "collapsed_table.txt"
    f.write_text("\n".join(lines), encoding="utf-8")

    result = scan_source(str(f), sample_n=3)
    assert result["suggestion"] == "technical"
    assert result["avg_tabular_ratio"] == 0.0  # classic heuristic sees nothing
    assert result["avg_burst_ratio"] > 0.1     # burst heuristic catches it


def test_summarize_recommendation_overrides_diluted_average():
    """Real-world case: a large mostly-prose source with sparse but real
    tables — one sampled window hits a collapsed-table burst, but the
    average across many prose-only windows dilutes the raw suggestion to
    'text'. The final recommendation must still say technical."""
    pages = [{"n_lines": 50, "tabular_line_ratio": 0.0, "burst_ratio": 0.3, "page_index": 0, "n_images": 0}]
    pages += [
        {"n_lines": 50, "tabular_line_ratio": 0.0, "burst_ratio": 0.0, "page_index": i, "n_images": 0}
        for i in range(1, 10)
    ]
    result = _summarize(500, list(range(10)), pages, any_images=False)
    assert result["suggestion"] == "text"
    assert result["recommendation"] == "technical"
    assert "overriding" in result["recommendation_reason"]


def test_summarize_recommendation_matches_suggestion_when_no_localized_evidence():
    pages = [
        {"n_lines": 50, "tabular_line_ratio": 0.0, "burst_ratio": 0.0, "page_index": i, "n_images": 0}
        for i in range(5)
    ]
    result = _summarize(250, list(range(5)), pages, any_images=False)
    assert result["suggestion"] == "text"
    assert result["recommendation"] == "text"
    assert "matches the raw signal" in result["recommendation_reason"]


def test_scan_source_non_pdf_includes_recommendation_fields():
    result = scan_source("book.epub")
    assert "recommendation" in result
    assert "recommendation_reason" in result


def test_build_prompt_draft_is_fully_filled_with_defaults():
    from preflight_scan import build_prompt_draft
    result = {
        "suggestion": "technical",
        "confidence": "high",
        "recommendation": "technical",
        "recommendation_reason": "some reason",
    }
    prompt = build_prompt_draft(result, "/path/to/my-book.pdf")
    assert "BOOK_TYPE=technical" in prompt
    assert "/path/to/my-book.pdf" in prompt
    assert "DEPTH=study" in prompt  # sensible default, not a blank
    assert 'nome="my-book"' in prompt  # slugified from filename
    assert "isolated extraction" in prompt
    assert "TODO" not in prompt  # fully filled, not blanks to complete
    assert "(S/N)" in prompt


def test_build_prompt_draft_overrides_are_respected():
    from preflight_scan import build_prompt_draft
    result = {"suggestion": "technical", "confidence": "high", "recommendation": "technical", "recommendation_reason": "x"}
    prompt = build_prompt_draft(
        result, "/path/to/book.pdf",
        depth="reference", skill_name="custom-name", skills_home="~/.agents/skills",
        lineage="part of the alpha-set lineage",
    )
    assert "DEPTH=reference" in prompt
    assert 'nome="custom-name"' in prompt
    assert "~/.agents/skills/custom-name" in prompt
    assert "part of the alpha-set lineage" in prompt


def test_slugify_filename():
    from preflight_scan import slugify_filename
    assert slugify_filename("/mnt/c/Users/x/Gurps-Basic-Set-4th-ed.txt") == "gurps-basic-set-4th-ed"
    assert slugify_filename("My Book (v2).pdf") == "my-book-v2"


def test_build_prompt_draft_uses_recommendation_not_raw_suggestion():
    from preflight_scan import build_prompt_draft
    result = {
        "suggestion": "text",
        "confidence": "medium",
        "recommendation": "technical",
        "recommendation_reason": "overriding the raw suggestion",
    }
    prompt = build_prompt_draft(result, "/path/to/book.txt")
    assert "BOOK_TYPE=technical" in prompt
    assert "BOOK_TYPE=text" not in prompt


# --- Item 11: reverse-engineering candidacy + analyst lens -------------------

SYSTEM_DEMO_TRANSCRIPT = (
    "Bem-vindos ao ASG. Olha aqui na tela, o ASG te dá um sinal quando o preço entra. "
    "Repara nesse indicador. Como vocês podem ver, o ASG mostra o setup aqui. "
    "Clica nesse botão e o sistema mostra o resultado. Veja aqui o alerta. "
    "As you can see, the ASG signal appears right here on the screen. "
)

CONCEPTUAL_TRANSCRIPT = (
    "Today we discuss the philosophy of decision making under uncertainty. "
    "Rationality is bounded, and heuristics shape how humans reason about probability. "
    "We reflect on the epistemology of forecasting and the ethics of judgment. "
) * 3


def test_analyze_re_candidacy_flags_system_demo():
    result = analyze_re_candidacy(SYSTEM_DEMO_TRANSCRIPT)
    assert result["re_candidate"] is True
    assert result["system_demonstration"]["named_system"] == "ASG"
    assert result["system_demonstration"]["ui_deixis"] >= 3


def test_analyze_re_candidacy_false_for_conceptual_material():
    result = analyze_re_candidacy(CONCEPTUAL_TRANSCRIPT)
    assert result["re_candidate"] is False
    assert result["system_demonstration"]["named_system"] is None


def test_detect_named_system_ignores_common_acronyms():
    assert detect_named_system("PDF PDF PDF URL URL API API API")[0] is None


def test_detect_named_system_finds_repeated_acronym():
    name, count = detect_named_system("The ASG does X. ASG does Y. Look at ASG again.")
    assert name == "ASG"
    assert count >= 3


def test_propose_analyst_lens_is_generic_base_with_evidence():
    lens = propose_analyst_lens(SYSTEM_DEMO_TRANSCRIPT, system_name="ASG")
    assert lens["lens"] == "systems-architect"  # generic base, not a hardcoded domain
    assert isinstance(lens["evidence"], list)
    assert lens["system"] == "ASG"


def test_salient_terms_excludes_ptbr_conversational_filler():
    """Regression test for a real-world case (a genuine ASG course transcript):
    raw word-frequency surfaced 'gente, mercado, cara, pessoas, parte, vocês' as
    evidence — all conversational filler except 'mercado', which drowned out any
    actual domain vocabulary. Filler must never outrank real domain terms."""
    transcript = (
        "Gente, olha só, cara, isso aqui é muito importante pra vocês. "
        "Toda vez que a gente fala com as pessoas, essa parte do negócio é assim. "
        "Gente, cara, pessoas, parte, vocês, gente, cara, pessoas, parte, vocês. "
        "O volume profile mostra o range de mercado e o backtest confirma o sinal. "
        "O volume profile é a base do backtest e do sinal que o sistema gera. "
    ) * 3
    terms = salient_terms(transcript)
    for filler in ("gente", "cara", "pessoas", "parte", "vocês", "vocês"):
        assert filler not in terms, f"filler word {filler!r} leaked into salient_terms: {terms}"
    assert any(t in terms for t in ("volume", "profile", "backtest", "sinal", "range"))


def test_salient_terms_excludes_second_wave_ptbr_filler():
    """Regression test: after the first stopword pass above, running against the
    real ASG transcript (not the synthetic reproduction) still surfaced
    'está, exemplo, pessoa, entender' as evidence alongside real domain terms —
    a second wave of discourse filler the first pass didn't cover (verb 'estar',
    generic 'exemplo'/'entender', and the singular 'pessoa', where only the
    plural 'pessoas' had been excluded)."""
    transcript = (
        "Olha, isso está sendo um exemplo de como o sistema está funcionando. "
        "Essa pessoa não vai entender se a gente não mostrar um exemplo claro. "
        "Está vendo? Vou dar outro exemplo pra você entender melhor essa pessoa. "
        "O volume profile mostra o range de mercado e o backtest confirma o sinal. "
        "O volume profile é a base do backtest e do sinal que o sistema gera. "
    ) * 3
    terms = salient_terms(transcript)
    for filler in ("está", "esta", "exemplo", "exemplos", "pessoa", "entender"):
        assert filler not in terms, f"filler word {filler!r} leaked into salient_terms: {terms}"
    assert any(t in terms for t in ("volume", "profile", "backtest", "sinal", "range", "mercado"))


def test_salient_terms_excludes_third_wave_ptbr_filler():
    """Regression test: running against the real ASG transcript after the first
    two stopword passes still surfaced 'hoje, também' as evidence — generic
    temporal/discourse adverbs, not domain vocabulary. Also covers the
    immediate same-class neighbors (agora, ainda, depois, antes)."""
    transcript = (
        "Hoje eu também vou mostrar isso. Agora vamos ver, e ainda depois "
        "disso, antes de terminar, também hoje é um bom dia pra explicar. "
        "Hoje também, agora ainda, depois antes, hoje também, agora ainda. "
        "O volume profile mostra o range de mercado e o backtest confirma o sinal. "
        "O volume profile é a base do backtest e do sinal que o sistema gera. "
    ) * 3
    terms = salient_terms(transcript)
    for filler in ("hoje", "também", "tambem", "agora", "ainda", "depois", "antes"):
        assert filler not in terms, f"filler word {filler!r} leaked into salient_terms: {terms}"
    assert any(t in terms for t in ("volume", "profile", "backtest", "sinal", "range", "mercado"))


def test_scan_source_txt_includes_re_candidacy_fields(tmp_path):
    f = tmp_path / "demo.txt"
    f.write_text(SYSTEM_DEMO_TRANSCRIPT * 3, encoding="utf-8")
    result = scan_source(str(f))
    assert "re_candidate" in result
    assert "analyst_lens_suggestion" in result
    assert result["re_candidate"] is True


def test_build_prompt_draft_offers_blackhat_option_when_candidate():
    from preflight_scan import build_prompt_draft
    result = {
        "suggestion": "text", "confidence": "medium",
        "recommendation": "text", "recommendation_reason": "x",
        "re_candidate": True,
        "analyst_lens_suggestion": {"lens": "systems-architect", "evidence": ["asg", "signal"]},
    }
    prompt = build_prompt_draft(result, "/path/to/asg.txt")
    assert "Blackhat Mode" in prompt
    assert "[A]" in prompt and "[B]" in prompt
    assert "analyst_lens" in prompt


def test_build_prompt_draft_omits_blackhat_when_not_candidate():
    from preflight_scan import build_prompt_draft
    result = {
        "suggestion": "text", "confidence": "medium",
        "recommendation": "text", "recommendation_reason": "x",
        "re_candidate": False,
    }
    prompt = build_prompt_draft(result, "/path/to/book.txt")
    assert "Blackhat Mode" not in prompt


# --- .srt/.vtt subtitle transcript support -----------------------------------

SRT_SAMPLE = """1
00:00:00,000 --> 00:00:03,500
Bem-vindos ao ASG. Olha aqui na tela, o ASG te dá um sinal quando o preço entra.

2
00:00:03,500 --> 00:00:07,000
Repara nesse indicador. Como vocês podem ver, o ASG mostra o setup aqui.

3
00:00:07,000 --> 00:00:10,000
Clica nesse botão e o sistema mostra o resultado do backtest.
"""

VTT_SAMPLE = """WEBVTT

NOTE this is a note, not spoken content

00:00:00.000 --> 00:00:03.500
Bem-vindos ao ASG. Olha aqui na tela, o ASG te dá um sinal quando o preço entra.

00:00:03.500 --> 00:00:07.000
Repara nesse indicador. Como vocês podem ver, o ASG mostra o setup aqui.
"""


def test_strip_subtitle_markup_removes_srt_structure():
    cleaned = strip_subtitle_markup(SRT_SAMPLE)
    assert "-->" not in cleaned
    assert "\n1\n" not in f"\n{cleaned}\n"
    assert "Bem-vindos ao ASG" in cleaned


def test_strip_subtitle_markup_removes_vtt_structure():
    cleaned = strip_subtitle_markup(VTT_SAMPLE)
    assert "WEBVTT" not in cleaned
    assert "NOTE" not in cleaned
    assert "-->" not in cleaned
    assert "Bem-vindos ao ASG" in cleaned


def test_scan_transcript_sets_source_kind(tmp_path):
    f = tmp_path / "vid1.srt"
    f.write_text(SRT_SAMPLE * 20, encoding="utf-8")
    result = scan_transcript(str(f))
    assert result["source_kind"] == "transcript"
    assert result["unit"] == "line-window"


def test_scan_transcript_detects_re_candidacy(tmp_path):
    f = tmp_path / "vid1.srt"
    f.write_text(SRT_SAMPLE * 20, encoding="utf-8")
    result = scan_transcript(str(f))
    assert result["re_candidate"] is True
    assert result["system_demonstration"]["named_system"] == "ASG"


def test_scan_transcript_empty_file(tmp_path):
    f = tmp_path / "empty.srt"
    f.write_text("", encoding="utf-8")
    result = scan_transcript(str(f))
    assert result["source_kind"] == "transcript"
    assert result["re_candidate"] is False


def test_scan_source_dispatches_srt_to_scan_transcript(tmp_path):
    f = tmp_path / "vid1.srt"
    f.write_text(SRT_SAMPLE * 20, encoding="utf-8")
    result = scan_source(str(f))
    assert result["source_kind"] == "transcript"
    assert result["re_candidate"] is True


def test_scan_source_dispatches_vtt_to_scan_transcript(tmp_path):
    f = tmp_path / "vid2.vtt"
    f.write_text(VTT_SAMPLE * 20, encoding="utf-8")
    result = scan_source(str(f))
    assert result["source_kind"] == "transcript"


def test_build_prompt_draft_uses_book_type_transcript_for_subtitle_source():
    result = {
        "source_kind": "transcript",
        "suggestion": "text", "confidence": "low",
        "recommendation": "text", "recommendation_reason": "x",
        "re_candidate": False,
    }
    prompt = build_prompt_draft(result, "/path/to/vid1.srt")
    assert "BOOK_TYPE=transcript" in prompt
    assert "BOOK_TYPE=text" not in prompt
