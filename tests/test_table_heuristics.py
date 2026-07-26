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
    extract_tables_from_page,
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
# Table extraction from page text
# ---------------------------------------------------------------------------

class TestExtractTablesFromPage:
    def test_gurs_style_table(self):
        """GURPS-style equipment table with TL/Name/DR/Cost/Weight."""
        text = """Low-Tech Armor Table
TL Armor Location DR Cost Weight LC Notes
0 Fur Loincloth groin 1* $10 neg. – [1]
0 Fur Tunic torso 1* $25 2 – [1]
1 Bronze Breastplate torso 4F $400 20 3 [2]
1 Cloth Armor torso, groin 1* $30 6 – [1]"""
        tables = extract_tables_from_page(text, 285)
        assert len(tables) >= 1
        assert tables[0]["page"] == 285
        assert tables[0]["n_rows"] >= 3

    def test_narrative_no_table(self):
        """Narrative text should not produce tables."""
        text = """The quick brown fox jumps over the lazy dog.
This is a paragraph of text that describes something.
It contains no tabular data whatsoever."""
        tables = extract_tables_from_page(text, 1)
        assert len(tables) == 0

    def test_two_separate_tables(self):
        """Two tables separated by multiple blank lines."""
        text = """1 Sword 1d6 cut 1 10 3
2 Axe 1d+1 cut 2 15 4
3 Dagger 1d-2 imp 1 5 1


1 Shield 2 $50 10 4
2 Buckler 1 $25 5 4
3 Tower 4 $200 30 3"""
        tables = extract_tables_from_page(text, 10)
        assert len(tables) >= 2

    def test_empty_page(self):
        tables = extract_tables_from_page("", 1)
        assert tables == []

    def test_page_number_preserved(self):
        text = "1 Sword 1d6 cut 1 10 3\n2 Axe 1d+1 cut 2 15 4\n3 Dagger 1d-2 imp 1 5 1"
        tables = extract_tables_from_page(text, 42)
        assert len(tables) >= 1
        assert tables[0]["page"] == 42


# ---------------------------------------------------------------------------
# Page parsing
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
