#!/usr/bin/env python3
"""Tests for scripts/compile.py — knowledge compilation pipeline.

Tests the prompt generation, source discovery, and output writing logic.
Agent subprocess calls are mocked to avoid requiring claude CLI in CI.
"""
import json
import os
import textwrap
from unittest import mock

import pytest

# Allow running from repo root
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from compile import (
    generate_prompt,
    call_agent,
    write_compilation,
    write_batch_summary,
    discover_sources,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_source(tmp_path):
    """Create a minimal source file for testing."""
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
def batch_sources(tmp_path):
    """Create multiple source files for batch testing."""
    files = []
    for i, name in enumerate(["video_a.txt", "video_b.txt", "video_c.txt"]):
        path = tmp_path / name
        path.write_text(f"Source {i+1} content about topic {i+1}.", encoding="utf-8")
        files.append(path)
    return tmp_path, files


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

    def test_prompt_has_sop_section(self, sample_source):
        content = sample_source.read_text()
        prompt = generate_prompt(sample_source, content)
        assert "SOPs (Standard Operating Procedures)" in prompt

    def test_prompt_has_principles_section(self, sample_source):
        content = sample_source.read_text()
        prompt = generate_prompt(sample_source, content)
        assert "Fundamental Principles" in prompt

    def test_prompt_has_concepts_section(self, sample_source):
        content = sample_source.read_text()
        prompt = generate_prompt(sample_source, content)
        assert "Key Concepts" in prompt

    def test_prompt_has_epistemic_rule(self, sample_source):
        content = sample_source.read_text()
        prompt = generate_prompt(sample_source, content)
        assert "Epistemic status" in prompt

    def test_prompt_has_no_fabrication_rule(self, sample_source):
        content = sample_source.read_text()
        prompt = generate_prompt(sample_source, content)
        assert "Do not fabricate" in prompt


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------

class TestDiscoverSources:
    def test_finds_txt_files(self, batch_sources):
        tmp_dir, _ = batch_sources
        sources = discover_sources(tmp_dir)
        assert len(sources) == 3

    def test_finds_srt_files(self, tmp_path):
        (tmp_path / "video.srt").write_text("srt content")
        sources = discover_sources(tmp_path)
        assert len(sources) == 1

    def test_finds_md_files(self, tmp_path):
        (tmp_path / "doc.md").write_text("markdown content")
        sources = discover_sources(tmp_path)
        assert len(sources) == 1

    def test_skips_metadata_json(self, tmp_path):
        (tmp_path / "video_metadata.json").write_text("{}")
        (tmp_path / "video.txt").write_text("content")
        sources = discover_sources(tmp_path)
        assert len(sources) == 1
        assert sources[0].name == "video.txt"

    def test_skips_underscore_files(self, tmp_path):
        (tmp_path / "_hidden.txt").write_text("hidden")
        (tmp_path / "visible.txt").write_text("visible")
        sources = discover_sources(tmp_path)
        assert len(sources) == 1
        assert sources[0].name == "visible.txt"

    def test_empty_dir(self, tmp_path):
        sources = discover_sources(tmp_path)
        assert len(sources) == 0

    def test_sorted_output(self, batch_sources):
        tmp_dir, _ = batch_sources
        sources = discover_sources(tmp_dir)
        names = [s.name for s in sources]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

class TestWriteCompilation:
    def test_writes_md_file(self, sample_source, tmp_path):
        prompt = "test prompt"
        response = "## SOPs\n- Step 1\n## Principles\n- Rule 1"
        write_compilation(sample_source, prompt, response, tmp_path)

        md_path = tmp_path / "compilation" / "test_video.md"
        assert md_path.exists()
        content = md_path.read_text()
        assert "Knowledge Compilation" in content
        assert "test_video.txt" in content
        assert "SOPs" in content

    def test_writes_json_provenance(self, sample_source, tmp_path):
        prompt = "test prompt"
        response = "test response"
        write_compilation(sample_source, prompt, response, tmp_path)

        json_path = tmp_path / "compilation" / "test_video.json"
        assert json_path.exists()
        meta = json.loads(json_path.read_text())
        assert meta["source"] == "test_video.txt"
        assert meta["prompt_chars"] == len(prompt)
        assert meta["response_chars"] == len(response)
        assert "compiled_at" in meta

    def test_creates_compilation_dir(self, sample_source, tmp_path):
        write_compilation(sample_source, "prompt", "response", tmp_path)
        assert (tmp_path / "compilation").is_dir()


class TestWriteBatchSummary:
    def test_writes_summary_md(self, tmp_path):
        results = [
            {"filename": "a.txt", "success": True, "response_chars": 100, "elapsed": 1.5},
            {"filename": "b.txt", "success": True, "response_chars": 200, "elapsed": 2.0},
            {"filename": "c.txt", "success": False, "error": "timeout", "response_chars": 0, "elapsed": 5.0},
        ]
        write_batch_summary(results, tmp_path)

        summary_path = tmp_path / "compilation" / "batch_summary.md"
        assert summary_path.exists()
        content = summary_path.read_text()
        assert "3" in content  # total files
        assert "FAILED" in content
        assert "timeout" in content

    def test_writes_run_json(self, tmp_path):
        results = [
            {"filename": "a.txt", "success": True, "response_chars": 100, "elapsed": 1.5},
        ]
        write_batch_summary(results, tmp_path)

        run_path = tmp_path / "compilation" / "run.json"
        assert run_path.exists()
        data = json.loads(run_path.read_text())
        assert data["total_files"] == 1
        assert data["successful"] == 1


# ---------------------------------------------------------------------------
# Agent CLI (mocked)
# ---------------------------------------------------------------------------

class TestCallAgent:
    @mock.patch("compile.subprocess.run")
    def test_successful_call(self, mock_run):
        mock_run.return_value = mock.Mock(
            returncode=0,
            stdout="## SOPs\n- Test procedure",
            stderr="",
        )
        result = call_agent("test prompt", model="haiku", timeout=30)
        assert result == "## SOPs\n- Test procedure"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "claude" in cmd
        assert "-p" in cmd
        assert "--allowedTools" in cmd

    @mock.patch("compile.subprocess.run")
    def test_empty_response(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        result = call_agent("test prompt")
        assert result == ""

    @mock.patch("compile.subprocess.run")
    def test_nonzero_return(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=1, stdout="partial", stderr="error msg")
        result = call_agent("test prompt")
        assert result == "partial"

    @mock.patch("compile.subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="claude", timeout=30)
        result = call_agent("test prompt", timeout=30)
        assert result == ""

    @mock.patch("compile.subprocess.run")
    def test_claude_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("claude not found")
        result = call_agent("test prompt")
        assert result == ""


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

class TestCLI:
    def test_help(self):
        """compile.py --help should not crash."""
        result = os.popen("python3 scripts/compile.py --help").read()
        assert "Knowledge compilation" in result
        assert "--batch" in result
        assert "--dry-run" in result

    def test_dry_run_no_agent_call(self, sample_source):
        """--dry-run should not call the agent."""
        result = os.popen(
            f"python3 scripts/compile.py {sample_source} --dry-run 2>&1"
        ).read()
        assert "DRY RUN" in result
        assert "Prompt preview" in result

    def test_missing_path(self):
        """Non-existent path should error."""
        result = os.popen(
            "python3 scripts/compile.py /nonexistent/path.txt 2>&1"
        ).read()
        assert "not found" in result.lower() or "error" in result.lower()
