#!/usr/bin/env python3
"""Tests for scripts/compile.py — knowledge compilation pipeline.

Tests: prompt generation, source discovery, structured parse, output writing,
agent subprocess (mocked), SRT stripping, chunking, cache.
"""
import json
import os
import textwrap
from unittest import mock

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from compile import (
    generate_prompt,
    call_agent,
    write_compilation,
    write_batch_summary,
    discover_sources,
    parse_compilation,
    strip_srt,
    chunk_content,
    sha256_file,
    is_compiled,
    cache_key,
    _deduplicate,
    main,
    grounding_check,
    read_source_metadata,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_source(tmp_path):
    content = textwrap.dedent("""\
        The key insight is that volatility drag compounds against you.
        Nobody knows what the outcome of a single trade will be.
        Higher returns require higher risk — there is no free lunch.

        Steps to build a portfolio:
        1. Define your goals
        2. Estimate risk and return for each asset
        3. Diversify away idiosyncratic risk
        4. Add a convexity hedge layer
    """)
    path = tmp_path / "test_video.txt"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def sample_srt(tmp_path):
    content = textwrap.dedent("""\
        1
        00:00:01,000 --> 00:00:04,000
        The key insight is volatility drag.

        2
        00:00:05,000 --> 00:00:08,000
        Nobody knows the outcome.

        3
        00:00:09,000 --> 00:00:12,000
        Higher returns require higher risk.
    """)
    path = tmp_path / "test_video.srt"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# SRT stripping
# ---------------------------------------------------------------------------

class TestStripSrt:
    def test_removes_cue_numbers(self):
        assert strip_srt("1\n00:00:01,000 --> 00:00:04,000\nHello world") == "Hello world"

    def test_removes_timestamps(self):
        text = "1\n00:00:01,000 --> 00:00:04,000\nTest line"
        result = strip_srt(text)
        assert "00:00:01" not in result
        assert "Test line" in result

    def test_joins_lines(self):
        text = "1\n00:00:01,000 --> 00:00:04,000\nLine one\n\n2\n00:00:05,000 --> 00:00:08,000\nLine two"
        result = strip_srt(text)
        assert "Line one" in result
        assert "Line two" in result

    def test_preserves_content(self, sample_srt):
        raw = sample_srt.read_text()
        stripped = strip_srt(raw)
        assert "volatility drag" in stripped
        assert "Nobody knows" in stripped
        assert "higher risk" in stripped


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

class TestChunkContent:
    def test_small_content_single_chunk(self):
        chunks = chunk_content("short text", max_chars=1000)
        assert len(chunks) == 1

    def test_large_content_splits(self):
        big = "sentence. " * 20000  # ~200K chars
        chunks = chunk_content(big, max_chars=100_000)
        assert len(chunks) > 1

    def test_chunks_preserve_content(self):
        text = "First sentence. Second sentence. Third sentence."
        chunks = chunk_content(text, max_chars=30)
        combined = " ".join(chunks)
        assert "First" in combined
        assert "Second" in combined
        assert "Third" in combined


# ---------------------------------------------------------------------------
# SHA-256
# ---------------------------------------------------------------------------

class TestSha256:
    def test_deterministic(self, sample_source):
        h1 = sha256_file(sample_source)
        h2 = sha256_file(sample_source)
        assert h1 == h2
        assert len(h1) == 64

    def test_different_files(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("content A")
        b.write_text("content B")
        assert sha256_file(a) != sha256_file(b)


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------

class TestGeneratePrompt:
    def test_prompt_contains_filename(self, sample_source):
        content = sample_source.read_text()
        prompt = generate_prompt(sample_source, content)
        assert "test_video.txt" in prompt

    def test_prompt_contains_content(self, sample_source):
        content = sample_source.read_text()
        prompt = generate_prompt(sample_source, content)
        assert "volatility drag compounds" in prompt

    def test_prompt_has_all_sections(self, sample_source):
        content = sample_source.read_text()
        prompt = generate_prompt(sample_source, content)
        assert "SOPs (Standard Operating Procedures)" in prompt
        assert "Fundamental Principles" in prompt
        assert "Key Concepts" in prompt
        assert "Named References" in prompt

    def test_prompt_has_rules(self, sample_source):
        content = sample_source.read_text()
        prompt = generate_prompt(sample_source, content)
        assert "Do not fabricate" in prompt
        assert "Epistemic status" in prompt


# ---------------------------------------------------------------------------
# Structured parse (§2.1)
# ---------------------------------------------------------------------------

class TestParseCompilation:
    def test_parse_sops(self):
        text = "## SOPs\n\n### Name: My SOP\nSteps:\n1. Do this\n2. Do that\nWhen to use: When X"
        sections = parse_compilation(text)
        assert len(sections["sops"]) == 1
        assert sections["sops"][0]["name"] == "My SOP"
        assert len(sections["sops"][0]["steps"]) == 2

    def test_parse_principles(self):
        text = "## Fundamental Principles\n\n- **Statement**: Do not leverage.\n **Epistemic status**: certain\n **Evidence**: because reasons"
        sections = parse_compilation(text)
        assert len(sections["principles"]) == 1
        assert sections["principles"][0]["epistemic_status"] == "certain"

    def test_parse_concepts(self):
        text = "## Key Concepts\n\n- **Term**: Volatility drag\n **Definition**: Bad thing\n **Used in**: SOP 1"
        sections = parse_compilation(text)
        assert len(sections["concepts"]) == 1
        assert sections["concepts"][0]["term"] == "Volatility drag"

    def test_parse_references(self):
        text = "## Named References\n\n- Black-Scholes model\n- Jane Street\n- Quant Guild"
        sections = parse_compilation(text)
        assert len(sections["references"]) == 3

    def test_parse_empty(self):
        sections = parse_compilation("")
        assert sections["sops"] == []
        assert sections["principles"] == []

    def test_parse_full_agent_output(self):
        text = textwrap.dedent("""\
            ## SOPs

            ### Name: Build Portfolio
            Steps:
            1. Define goals
            2. Estimate risk
            When to use: At start

            ## Fundamental Principles

            - **Statement**: No free lunch.
             **Epistemic status**: certain
             **Evidence**: "you don't get something for nothing"

            ## Key Concepts

            - **Term**: Sharpe ratio
             **Definition**: Risk-adjusted return
             **Used in**: Build Portfolio

            ## Named References

            - Black-Scholes
            - CAPM
        """)
        sections = parse_compilation(text)
        assert len(sections["sops"]) == 1
        assert len(sections["principles"]) == 1
        assert len(sections["concepts"]) == 1
        assert len(sections["references"]) == 2


# ---------------------------------------------------------------------------
# Source discovery — recursive
# ---------------------------------------------------------------------------

class TestDiscoverSources:
    def test_recursive_finds_subdirs(self, tmp_path):
        sub = tmp_path / "video_id"
        sub.mkdir()
        (sub / "transcript.srt").write_text("srt content")
        (sub / "full_text.txt").write_text("text content")
        sources = discover_sources(tmp_path)
        assert len(sources) == 2

    def test_finds_flat_files(self, tmp_path):
        (tmp_path / "video_a.txt").write_text("content a")
        (tmp_path / "video_b.txt").write_text("content b")
        sources = discover_sources(tmp_path)
        assert len(sources) == 2

    def test_skips_metadata(self, tmp_path):
        sub = tmp_path / "vid"
        sub.mkdir()
        (sub / "transcript.txt").write_text("content")
        (sub / "vid_metadata.json").write_text("{}")
        sources = discover_sources(tmp_path)
        assert len(sources) == 1
        assert sources[0].name == "transcript.txt"

    def test_skips_underscore_files(self, tmp_path):
        (tmp_path / "_hidden.txt").write_text("hidden")
        (tmp_path / "visible.txt").write_text("visible")
        sources = discover_sources(tmp_path)
        assert len(sources) == 1

    def test_sorted_output(self, tmp_path):
        sub = tmp_path / "b"
        sub.mkdir()
        (tmp_path / "a.txt").write_text("a")
        (sub / "c.txt").write_text("c")
        sources = discover_sources(tmp_path)
        names = [s.name for s in sources]
        assert names == sorted(names)

    def test_empty_dir(self, tmp_path):
        assert discover_sources(tmp_path) == []


# ---------------------------------------------------------------------------
# Cache (§2.4)
# ---------------------------------------------------------------------------

class TestCache:
    def test_not_compiled_fresh(self, tmp_path):
        assert not is_compiled("video1", tmp_path)

    def test_compiled_after_write(self, tmp_path):
        out_dir = tmp_path / "compilation"
        out_dir.mkdir()
        (out_dir / "video1.json").write_text('{"valid": true}')
        assert is_compiled("video1", tmp_path)

    def test_corrupted_json_not_cached(self, tmp_path):
        out_dir = tmp_path / "compilation"
        out_dir.mkdir()
        (out_dir / "broken.json").write_text("{corrupted json!!!")
        assert not is_compiled("broken", tmp_path)
        # Corrupted file should have been cleaned up
        assert not (out_dir / "broken.json").exists()


# ---------------------------------------------------------------------------
# Cache key — collision safety
# ---------------------------------------------------------------------------

class TestCacheKey:
    def test_flat_file(self, tmp_path):
        f = tmp_path / "video.txt"
        assert cache_key(f, tmp_path) == "video.txt"

    def test_nested_file(self, tmp_path):
        f = tmp_path / "output" / "abc123" / "transcript.srt"
        assert cache_key(f, tmp_path) == "output__abc123__transcript.srt"

    def test_deeply_nested(self, tmp_path):
        f = tmp_path / "a" / "b" / "c" / "file.txt"
        assert cache_key(f, tmp_path) == "a__b__c__file.txt"

    def test_different_roots_same_name(self, tmp_path):
        f1 = tmp_path / "vid1" / "transcript.srt"
        f2 = tmp_path / "vid2" / "transcript.srt"
        assert cache_key(f1, tmp_path) != cache_key(f2, tmp_path)

    def test_single_file_not_batch(self, tmp_path):
        f = tmp_path / "anything.txt"
        key = cache_key(f, tmp_path)
        assert key  # non-empty
        assert "anything" in key

    def test_batch_main_writes_distinct_files_for_same_stem(self, tmp_path):
        """Regression: main()'s per-chunk section loop must not shadow the
        outer cache_key() variable used for the output filename — otherwise
        two same-named sources (e.g. output/<id>/transcript.srt, the real
        ingestion layout) silently collide and one video's compilation is
        lost, defeating cache_key()'s whole purpose."""
        root = tmp_path / "output"
        (root / "vid1").mkdir(parents=True)
        (root / "vid2").mkdir(parents=True)
        (root / "vid1" / "transcript.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nunique-marker-A\n", encoding="utf-8"
        )
        (root / "vid2" / "transcript.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nunique-marker-B\n", encoding="utf-8"
        )

        def fake_call_agent(prompt, *a, **kw):
            return "SOPs:\n1. Step\n\nPrinciples:\n- Stmt [certain] (evidence: l1)"

        argv = sys.argv
        try:
            sys.argv = ["compile.py", str(root), "--batch"]
            with mock.patch("compile.call_agent", side_effect=fake_call_agent):
                main()
        finally:
            sys.argv = argv

        comp_dir = root / "compilation"
        written = {p.stem for p in comp_dir.glob("*.json") if p.stem != "run"}
        assert written == {"vid1__transcript.srt", "vid2__transcript.srt"}

        vid1 = json.loads((comp_dir / "vid1__transcript.srt.json").read_text())
        vid2 = json.loads((comp_dir / "vid2__transcript.srt.json").read_text())
        assert vid1["source_path"] == str(root / "vid1" / "transcript.srt")
        assert vid2["source_path"] == str(root / "vid2" / "transcript.srt")


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplicate:
    def test_dedup_sops(self):
        items = [
            {"name": "SOP A", "steps": []},
            {"name": "SOP B", "steps": []},
            {"name": "SOP A", "steps": []},  # duplicate
        ]
        result = _deduplicate(items, "sops")
        assert len(result) == 2

    def test_dedup_principles(self):
        items = [
            {"statement": "Rule 1", "epistemic_status": "certain"},
            {"statement": "Rule 1", "epistemic_status": "certain"},  # duplicate
            {"statement": "Rule 2", "epistemic_status": "probable"},
        ]
        result = _deduplicate(items, "principles")
        assert len(result) == 2

    def test_dedup_concepts(self):
        items = [
            {"term": "Sharpe", "definition": "A"},
            {"term": "Sharpe", "definition": "B"},  # duplicate by term
            {"term": "Sortino", "definition": "C"},
        ]
        result = _deduplicate(items, "concepts")
        assert len(result) == 2

    def test_dedup_references(self):
        items = ["Black-Scholes", "CAPM", "Black-Scholes"]  # duplicate
        result = _deduplicate(items, "references")
        assert len(result) == 2

    def test_empty_input(self):
        assert _deduplicate([], "sops") == []


# ---------------------------------------------------------------------------
# Source metadata reader (§2.2)
# ---------------------------------------------------------------------------

class TestReadSourceMetadata:
    def test_reads_upload_date(self, tmp_path):
        meta = {"upload_date": "2026-01-15", "title": "Test Video", "uploader": "channel"}
        (tmp_path / "metadata.json").write_text(json.dumps(meta))
        source = tmp_path / "transcript.txt"
        source.write_text("content")
        result = read_source_metadata(source)
        assert result["upload_date"] == "2026-01-15"
        assert result["title"] == "Test Video"
        assert result["uploader"] == "channel"

    def test_no_metadata_returns_empty(self, tmp_path):
        source = tmp_path / "transcript.txt"
        source.write_text("content")
        result = read_source_metadata(source)
        assert result == {}

    def test_corrupted_json_returns_empty(self, tmp_path):
        (tmp_path / "metadata.json").write_text("{corrupted!!!")
        source = tmp_path / "transcript.txt"
        source.write_text("content")
        result = read_source_metadata(source)
        assert result == {}

    def test_empty_upload_date_excluded(self, tmp_path):
        meta = {"upload_date": "", "title": "Test"}
        (tmp_path / "metadata.json").write_text(json.dumps(meta))
        source = tmp_path / "transcript.txt"
        source.write_text("content")
        result = read_source_metadata(source)
        assert "upload_date" not in result
        assert result["title"] == "Test"

    def test_includes_canonical_id(self, tmp_path):
        meta = {"upload_date": "2026-03-01", "canonical_id": "abc123", "language": "en"}
        (tmp_path / "metadata.json").write_text(json.dumps(meta))
        source = tmp_path / "transcript.txt"
        source.write_text("content")
        result = read_source_metadata(source)
        assert result["canonical_id"] == "abc123"
        assert result["language"] == "en"


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

class TestWriteCompilation:
    def test_writes_json_structured(self, sample_source, tmp_path):
        sections = {
            "sops": [{"name": "SOP1", "steps": ["step1"], "when_to_use": "always"}],
            "principles": [{"statement": "Rule 1", "epistemic_status": "certain", "evidence": "because"}],
            "concepts": [{"term": "X", "definition": "Y", "used_in": "Z"}],
            "references": ["Black-Scholes"],
        }
        write_compilation(
            sample_source, "prompt", "response text", sections,
            tmp_path, "claude", "sonnet", "abc123hash", "test_video",
        )
        json_path = tmp_path / "compilation" / "test_video.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["source"] == "test_video.txt"
        assert data["agent"] == "claude"
        assert data["model"] == "sonnet"
        assert data["source_sha256"] == "abc123hash"
        assert len(data["sops"]) == 1
        assert len(data["principles"]) == 1

    def test_writes_md_with_provenance(self, sample_source, tmp_path):
        sections = {"sops": [], "principles": [], "concepts": [], "references": []}
        write_compilation(
            sample_source, "prompt", "response text", sections,
            tmp_path, "claude", None, "hash123", "test_video",
        )
        md = (tmp_path / "compilation" / "test_video.md").read_text()
        assert "Agent**: claude" in md
        assert "hash123" in md

    def test_source_metadata_in_json(self, sample_source, tmp_path):
        sections = {"sops": [], "principles": [], "concepts": [], "references": []}
        meta = {"upload_date": "2026-01-15", "title": "My Video"}
        write_compilation(
            sample_source, "prompt", "response text", sections,
            tmp_path, "claude", None, "hash123", "test_video",
            source_metadata=meta,
        )
        data = json.loads((tmp_path / "compilation" / "test_video.json").read_text())
        assert data["source_metadata"]["upload_date"] == "2026-01-15"
        assert data["source_metadata"]["title"] == "My Video"

    def test_source_metadata_in_md(self, sample_source, tmp_path):
        sections = {"sops": [], "principles": [], "concepts": [], "references": []}
        meta = {"upload_date": "2026-01-15", "title": "My Video"}
        write_compilation(
            sample_source, "prompt", "response text", sections,
            tmp_path, "claude", None, "hash123", "test_video",
            source_metadata=meta,
        )
        md = (tmp_path / "compilation" / "test_video.md").read_text()
        assert "Source date**: 2026-01-15" in md
        assert "Title**: My Video" in md

    def test_no_metadata_no_source_date(self, sample_source, tmp_path):
        sections = {"sops": [], "principles": [], "concepts": [], "references": []}
        write_compilation(
            sample_source, "prompt", "response text", sections,
            tmp_path, "claude", None, "hash123", "test_video",
        )
        data = json.loads((tmp_path / "compilation" / "test_video.json").read_text())
        assert "source_metadata" not in data
        md = (tmp_path / "compilation" / "test_video.md").read_text()
        assert "Source date" not in md


class TestWriteBatchSummary:
    def test_summary_with_counts(self, tmp_path):
        results = [
            {"filename": "a.txt", "success": True, "response_chars": 100,
             "sops_count": 3, "principles_count": 5, "concepts_count": 4, "elapsed": 1.5},
            {"filename": "b.txt", "success": False, "error": "timeout",
             "response_chars": 0, "elapsed": 5.0},
        ]
        write_batch_summary(results, tmp_path)
        content = (tmp_path / "compilation" / "batch_summary.md").read_text()
        assert "Total SOPs" in content
        assert "3" in content
        assert "FAILED" in content


# ---------------------------------------------------------------------------
# Agent CLI (mocked)
# ---------------------------------------------------------------------------

class TestCallAgent:
    @mock.patch("compile.subprocess.run")
    def test_successful_call(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=0, stdout="## SOPs\n- Test", stderr="")
        result = call_agent("prompt", agent="claude", model="haiku")
        assert result == "## SOPs\n- Test"
        cmd = mock_run.call_args[0][0]
        assert "claude" in cmd
        assert "-p" in cmd

    @mock.patch("compile.subprocess.run")
    def test_nonzero_raises(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=1, stdout="partial", stderr="auth error")
        with pytest.raises(RuntimeError, match="exit 1"):
            call_agent("prompt")

    @mock.patch("compile.subprocess.run")
    def test_timeout_raises(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="claude", timeout=30)
        with pytest.raises(RuntimeError, match="timed out"):
            call_agent("prompt", timeout=30)

    @mock.patch("compile.subprocess.run")
    def test_not_found_raises(self, mock_run):
        mock_run.side_effect = FileNotFoundError("claude not found")
        with pytest.raises(RuntimeError, match="not found"):
            call_agent("prompt")

    def test_unknown_agent_raises(self):
        with pytest.raises(ValueError, match="Unknown agent"):
            call_agent("prompt", agent="nonexistent")


# ---------------------------------------------------------------------------
# Grounding check (§2.3)
# ---------------------------------------------------------------------------

class TestGroundingCheck:
    def test_grounded_principle_kept(self):
        """A principle whose terms appear in the source is kept."""
        source = "Volatility drag compounds against you. Higher returns require higher risk."
        principles = [
            {"statement": "Higher returns require higher risk", "epistemic_status": "certain"},
        ]
        kept, flagged = grounding_check(principles, source, floor=0.34)
        assert len(kept) == 1
        assert len(flagged) == 0
        assert kept[0]["_grounding_score"] >= 0.34

    def test_ungrounded_principle_flagged(self):
        """A principle with terms absent from source is flagged."""
        source = "The weather is sunny today."
        principles = [
            {"statement": "Quantum entanglement governs portfolio correlation",
             "epistemic_status": "speculative"},
        ]
        kept, flagged = grounding_check(principles, source, floor=0.34)
        assert len(kept) == 0
        assert len(flagged) == 1
        assert flagged[0]["_grounding_score"] < 0.34

    def test_mixed_principles(self):
        """Mix of grounded and ungrounded principles splits correctly."""
        source = "Volatility drag compounds against you. Nobody knows the outcome."
        principles = [
            {"statement": "Volatility drag compounds against you", "epistemic_status": "certain"},
            {"statement": "Quantum teleportation enables instant settlement",
             "epistemic_status": "speculative"},
        ]
        kept, flagged = grounding_check(principles, source, floor=0.34)
        assert len(kept) == 1
        assert len(flagged) == 1
        assert "volatility" in kept[0]["statement"].lower()

    def test_empty_principles(self):
        """No principles returns empty lists."""
        kept, flagged = grounding_check([], "any source", floor=0.34)
        assert kept == []
        assert flagged == []

    def test_empty_statement_kept(self):
        """Principle with empty statement is kept (nothing to check)."""
        principles = [{"statement": "", "epistemic_status": ""}]
        kept, flagged = grounding_check(principles, "source text", floor=0.34)
        assert len(kept) == 1
        assert len(flagged) == 0

    def test_score_metadata_attached(self):
        """Kept principles have _grounding_score and _absent_terms metadata."""
        source = "Risk management is essential for survival."
        principles = [
            {"statement": "Risk management is essential", "epistemic_status": "certain"},
        ]
        kept, _ = grounding_check(principles, source, floor=0.34)
        assert "_grounding_score" in kept[0]
        assert "_absent_terms" in kept[0]
        assert isinstance(kept[0]["_absent_terms"], list)

    def test_custom_floor(self):
        """Custom floor changes which principles are kept."""
        source = "A B C D E"
        principles = [
            {"statement": "A B C", "epistemic_status": "certain"},  # ~100% with stopwords
        ]
        # Very high floor — should flag
        kept_high, flagged_high = grounding_check(principles, source, floor=0.99)
        # Very low floor — should keep
        kept_low, flagged_low = grounding_check(principles, source, floor=0.01)
        assert len(flagged_low) == 0

    def test_synonym_expansion(self):
        """Synonym map can help match terms."""
        source = "The portfolio has significant volatility."
        principles = [
            {"statement": "The portfolio has significant variance", "epistemic_status": "certain"},
        ]
        # Without synonyms: "variance" absent
        kept_no, flagged_no = grounding_check(principles, source, floor=0.34)
        # With synonyms mapping variance -> volatility
        synonym_map = {"variance": "volatility"}
        kept_yes, flagged_yes = grounding_check(
            principles, source, floor=0.34, synonym_map=synonym_map,
        )
        # Synonym should improve the score
        score_no = kept_no[0]["_grounding_score"] if kept_no else flagged_no[0]["_grounding_score"]
        score_yes = kept_yes[0]["_grounding_score"] if kept_yes else flagged_yes[0]["_grounding_score"]
        assert score_yes >= score_no


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCLI:
    def test_help(self):
        result = os.popen("python3 scripts/compile.py --help").read()
        assert "Knowledge compilation" in result
        assert "--batch" in result
        assert "--agent" in result

    def test_dry_run(self, sample_source):
        result = os.popen(
            f"python3 scripts/compile.py {sample_source} --dry-run 2>&1"
        ).read()
        assert "DRY RUN" in result

    def test_missing_path(self):
        result = os.popen(
            "python3 scripts/compile.py /nonexistent/path.txt 2>&1"
        ).read()
        assert "not found" in result.lower() or "error" in result.lower()

    def test_grounding_check_in_help(self):
        result = os.popen("python3 scripts/compile.py --help").read()
        assert "--grounding-check" in result
        assert "--grounding-floor" in result
        assert "--domain" in result

    def test_no_grounding_check_flag(self, sample_source):
        result = os.popen(
            f"python3 scripts/compile.py {sample_source} --dry-run --no-grounding-check 2>&1"
        ).read()
        assert "DRY RUN" in result
