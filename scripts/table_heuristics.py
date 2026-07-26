#!/usr/bin/env python3
"""Shared table detection heuristics.

TABULAR_LINE_RE and SHORT_LINE_RE are used by both preflight_scan.py
and extract_tables.py. Centralized here to avoid divergence.
"""
import re

# Lines with multi-space-aligned columns OR 3+ numbers in sequence.
# The third alternative handles GURPS-style equipment tables where
# columns are separated by single spaces but have 3+ numeric values.
TABULAR_LINE_RE = re.compile(
    r'(\S+\s{2,}\S+\s{2,}\S+)'   # multi-space aligned
    r'|(\d+\s+\d+\s+\d+)'          # 3 consecutive numbers
    r'|((?:^|\s)\d+(?:\s+\d+){2,})'  # 3+ numbers anywhere in line
)

# Single short token alone on its own line — the signature of a table
# whose columns collapsed into one cell per line during PDF-to-text
# conversion (column layout lost, but not the content).
SHORT_LINE_RE = re.compile(r'^\S{1,20}$')
MIN_BURST_RUN = 4
