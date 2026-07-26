#!/usr/bin/env python3
"""Tests for table detection and extraction.

Tests: table_heuristics, extract_tables, preflight_scan table detection.
"""
import os
import sys
import json
import csv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from table_heuristics import TABULAR_LINE_RE, SHORT_LINE_RE
from extract_tables import (
    extract_all_tables,
    save_tables_csv,
    save_tables_json,
)


# ---------------------------------------------------------------------------
# Table heuristics
# ---------------------------------------------------------------------------

class TestTabularLineRe:
    def test_multi_space_aligned(self):
        assert TABULAR_LINE_RE.search("Name    Value    Unit")

    def test_three_consecutive_numbers(self):
        assert TABULAR_LINE_RE.search("1 2 3")

    def test_three_numbers_with_text(self):
        assert TABULAR_LINE_RE.search("1 Bronze Breastplate 400 20 3")

    def test_prose_no_match(self):
        assert not TABULAR_LINE_RE.search("The quick brown fox jumps over the lazy dog")

    def test_short_line_no_match(self):
        assert not TABULAR_LINE_RE.search("Body Armor")


class TestShortLineRe:
    def test_short_token(self):
        assert SHORT_LINE_RE.match("Armor")

    def test_long_line_no_match(self):
        assert not SHORT_LINE_RE.match("This is a very long line that should not match")


# ---------------------------------------------------------------------------
# Table extraction (extract_all_tables)
# ---------------------------------------------------------------------------

class TestExtractAllTables:
    def test_no_pdf_returns_empty(self):
        """Non-existent PDF returns empty list."""
        tables = extract_all_tables("/nonexistent/file.pdf")
        assert tables == []


# ---------------------------------------------------------------------------
# Save functions
# ---------------------------------------------------------------------------

class TestSaveTablesCsv:
    def test_save_creates_files(self, tmp_path):
        tables = [
            {"page": 1, "rows": [["A", "B"], ["C", "D"]], "n_rows": 2},
            {"page": 2, "rows": [["X", "Y"]], "n_rows": 1},
        ]
        save_tables_csv(tables, str(tmp_path))
        files = list(tmp_path.glob("*.csv"))
        assert len(files) == 2

    def test_csv_content(self, tmp_path):
        tables = [{"page": 1, "rows": [["Name", "Value"], ["Foo", "42"]], "n_rows": 2}]
        save_tables_csv(tables, str(tmp_path))
        csv_file = tmp_path / "table_1_page1.csv"
        with open(csv_file) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert rows[0] == ["Name", "Value"]
        assert rows[1] == ["Foo", "42"]


class TestSaveTablesJson:
    def test_save_creates_file(self, tmp_path):
        tables = [{"page": 1, "rows": [["A"]], "n_rows": 1}]
        save_tables_json(tables, str(tmp_path))
        json_file = tmp_path / "tables.json"
        assert json_file.exists()
        with open(json_file) as f:
            data = json.load(f)
        assert len(data) == 1
