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
        (out_dir / "video1.json").write_text("{}")
        assert is_compiled("video1", tmp_path)


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
            tmp_path, "claude", "sonnet", "abc123hash",
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
            tmp_path, "claude", None, "hash123",
        )
        md = (tmp_path / "compilation" / "test_video.md").read_text()
        assert "Agent**: claude" in md
        assert "hash123" in md


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
