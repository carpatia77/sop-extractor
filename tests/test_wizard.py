"""Tests for scripts/wizard.py — interactive guided workflow.

Tests: prompt_choice, prompt_text, run_script, wizard workflows.
"""
import os
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from wizard import (
    prompt_choice,
    prompt_text,
    run_script,
    wizard_status,
)


# ---------------------------------------------------------------------------
# prompt_choice
# ---------------------------------------------------------------------------

class TestPromptChoice:
    def test_valid_input(self):
        with patch("builtins.input", return_value="2"), \
             patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = prompt_choice("Pick one:", ["A", "B", "C"])
        assert result == 2

    def test_first_option(self):
        with patch("builtins.input", return_value="1"), \
             patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = prompt_choice("Pick:", ["X", "Y"])
        assert result == 1

    def test_non_interactive_uses_default(self):
        """Non-TTY returns 1 without looping."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = prompt_choice("Pick:", ["A", "B"])
        assert result == 1

    def test_eof_returns_default(self):
        """EOFError returns 1 without infinite loop."""
        with patch("builtins.input", side_effect=EOFError), \
             patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = prompt_choice("Pick:", ["A", "B"])
        assert result == 1


# ---------------------------------------------------------------------------
# prompt_text
# ---------------------------------------------------------------------------

class TestPromptText:
    def test_valid_input(self):
        with patch("builtins.input", return_value="hello"):
            result = prompt_text("Enter text:")
        assert result == "hello"

    def test_default_value(self):
        with patch("builtins.input", return_value=""):
            result = prompt_text("Enter text:", "default_val")
        assert result == "default_val"

    def test_eof_returns_default(self):
        with patch("builtins.input", side_effect=EOFError):
            result = prompt_text("Enter text:", "fallback")
        assert result == "fallback"


# ---------------------------------------------------------------------------
# run_script
# ---------------------------------------------------------------------------

class TestRunScript:
    def test_run_existing_script(self, tmp_path):
        """run_script calls subprocess correctly."""
        # Create a dummy script
        script = tmp_path / "test_script.py"
        script.write_text("print('hello')")

        import wizard
        old_dir = wizard.SCRIPTS_DIR
        wizard.SCRIPTS_DIR = tmp_path
        try:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                rc = run_script("test_script.py", ["arg1", "arg2"])
                assert rc == 0
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "arg1" in call_args
                assert "arg2" in call_args
        finally:
            wizard.SCRIPTS_DIR = old_dir

    def test_run_nonexistent_script(self, tmp_path):
        """run_script returns non-zero for missing script."""
        import wizard
        old_dir = wizard.SCRIPTS_DIR
        wizard.SCRIPTS_DIR = tmp_path
        try:
            rc = run_script("nonexistent.py", [])
            assert rc != 0
        finally:
            wizard.SCRIPTS_DIR = old_dir


# ---------------------------------------------------------------------------
# wizard_status
# ---------------------------------------------------------------------------

class TestWizardStatus:
    def test_no_output_dir(self, capsys):
        """wizard_status handles missing output/ gracefully."""
        with patch("pathlib.Path.exists", return_value=False):
            rc = wizard_status()
        assert rc == 0

    def test_with_compilations(self, tmp_path, capsys):
        """wizard_status counts compilations."""
        import wizard
        old_dir = wizard.SCRIPTS_DIR
        wizard.SCRIPTS_DIR = tmp_path
        # Create output structure
        comp_dir = tmp_path / "output" / "compilation"
        comp_dir.mkdir(parents=True)
        (comp_dir / "video1.json").write_text("{}")
        (comp_dir / "video2.json").write_text("{}")
        (comp_dir / "run.json").write_text("{}")  # excluded
        (comp_dir / "video1.semantic_field.json").write_text("{}")  # excluded
        try:
            original_path = Path
            def mock_path(p):
                if p == "output":
                    return tmp_path / "output"
                return original_path(p)
            with patch("wizard.Path", side_effect=mock_path):
                rc = wizard_status()
            assert rc == 0
            captured = capsys.readouterr()
            assert "Compilacoes: 2" in captured.out
        finally:
            wizard.SCRIPTS_DIR = old_dir
