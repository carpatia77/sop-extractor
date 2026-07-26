#!/usr/bin/env python3
"""Table Extractor — extract tables from PDFs using pypdf heuristics.

Since pdfplumber/camelot are not available, this module uses pypdf's text
extraction with heuristics to identify and extract tabular data.

Usage:
    python scripts/extract_tables.py <pdf_path> [--output <dir>]
    python scripts/extract_tables.py <pdf_path> --pages 10-20
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

try:
    from table_heuristics import TABULAR_LINE_RE, SHORT_LINE_RE, MIN_BURST_RUN
except ImportError:
    from scripts.table_heuristics import TABULAR_LINE_RE, SHORT_LINE_RE, MIN_BURST_RUN


def detect_table_regions(text: str) -> list[dict]:
    """Detect table regions in extracted text using heuristics.

    Returns list of regions: [{start_line, end_line, confidence, type}]
    """
    lines = text.splitlines()
    regions = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Check for tabular lines (multi-space aligned)
        if TABULAR_LINE_RE.search(line):
            start = i
            # Look ahead for continuation
            while i < len(lines) and (
                TABULAR_LINE_RE.search(lines[i].strip()) or
                (lines[i].strip() and len(lines[i].strip()) < 50)
            ):
                i += 1
            if i - start >= 3:  # Minimum 3 lines for a table
                regions.append({
                    "start_line": start,
                    "end_line": i - 1,
                    "confidence": "medium",
                    "type": "tabular_aligned",
                    "n_lines": i - start,
                })
            continue

        # Check for burst runs (collapsed tables)
        if SHORT_LINE_RE.match(line):
            start = i
            while i < len(lines) and SHORT_LINE_RE.match(lines[i].strip()):
                i += 1
            if i - start >= MIN_BURST_RUN:
                regions.append({
                    "start_line": start,
                    "end_line": i - 1,
                    "confidence": "low" if i - start < 8 else "medium",
                    "type": "collapsed",
                    "n_lines": i - start,
                })
            continue

        i += 1

    return regions


# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------

def extract_tables_from_page(page_text: str, page_num: int) -> list[dict]:
    """Extract table-like structures from a single page's text.

    Uses two detection strategies:
    1. Multi-space aligned columns (standard tables)
    2. Lines with multiple numeric values (GURPS-style equipment tables)

    Returns list of tables: [{page, rows: [[cells]], type, confidence}]
    """
    lines = page_text.splitlines()
    tables = []
    current_table = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_table and len(current_table) >= 3:
                tables.append({
                    "page": page_num,
                    "rows": current_table,
                    "type": "detected",
                    "confidence": "medium" if len(current_table) >= 5 else "low",
                    "n_rows": len(current_table),
                })
                current_table = []
                in_table = False
            continue

        # Check if line looks tabular (multi-space aligned OR multiple numbers)
        is_tabular = TABULAR_LINE_RE.search(stripped)
        if not is_tabular:
            # Check for GURPS-style tables: lines with 3+ numbers and text
            nums = re.findall(r'\b\d+\b', stripped)
            has_text = bool(re.search(r'[A-Za-z]{3,}', stripped))
            if len(nums) >= 3 and has_text:
                is_tabular = True

        if is_tabular:
            # Split by multiple spaces, tabs, or $ signs (for cost columns)
            cells = re.split(r'\s{2,}|\t|\$|(?<=\d) (?=[A-Z])', stripped)
            cells = [c.strip() for c in cells if c.strip()]
            if len(cells) >= 2:
                current_table.append(cells)
                in_table = True
            elif in_table and len(stripped) < 30:
                current_table.append([stripped])
            else:
                if in_table and len(current_table) >= 3:
                    tables.append({
                        "page": page_num,
                        "rows": current_table,
                        "type": "detected",
                        "confidence": "medium",
                        "n_rows": len(current_table),
                    })
                current_table = []
                in_table = False
        else:
            if in_table and len(current_table) >= 3:
                tables.append({
                    "page": page_num,
                    "rows": current_table,
                    "type": "detected",
                    "confidence": "medium",
                    "n_rows": len(current_table),
                })
            current_table = []
            in_table = False

    # Don't forget the last table
    if in_table and len(current_table) >= 3:
        tables.append({
            "page": page_num,
            "rows": current_table,
            "type": "detected",
            "confidence": "medium",
            "n_rows": len(current_table),
        })

    return tables


def extract_all_tables(pdf_path: str, pages: list[int] | None = None) -> list[dict]:
    """Extract tables from all pages (or specified pages) of a PDF.

    Returns list of tables with page number and rows.
    """
    if not os.path.exists(pdf_path):
        return []

    try:
        import pypdf
    except ImportError:
        print("pypdf não instalado — instale com: pip install '.[pdf]'", file=sys.stderr)
        return []

    with open(pdf_path, "rb") as f:
        reader = pypdf.PdfReader(f)
        total_pages = len(reader.pages)

        if pages is None:
            pages = list(range(total_pages))

        all_tables = []
        for page_num in pages:
            if page_num >= total_pages:
                continue
            try:
                text = reader.pages[page_num].extract_text() or ""
            except Exception:
                continue

            tables = extract_tables_from_page(text, page_num + 1)  # 1-indexed
            all_tables.extend(tables)

    return all_tables


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_tables_csv(tables: list[dict], output_path: str) -> None:
    """Save extracted tables to CSV files (one per table)."""
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, table in enumerate(tables):
        rows = table.get("rows", [])
        if not rows:
            continue

        csv_path = output_dir / f"table_{i+1}_page{table['page']}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(row)

    print(f"  {len(tables)} tabelas salvas em {output_path}/")


def save_tables_json(tables: list[dict], output_path: str) -> None:
    """Save extracted tables to a single JSON file."""
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "tables.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(tables, f, indent=2, ensure_ascii=False)

    print(f"  {len(tables)} tabelas salvas em {json_path}")


def print_table_summary(tables: list[dict]) -> None:
    """Print summary of extracted tables."""
    if not tables:
        print("  Nenhuma tabela detectada.")
        return

    print(f"\n  {len(tables)} tabelas detectadas:")
    for i, table in enumerate(tables):
        n_rows = table.get("n_rows", len(table.get("rows", [])))
        page = table.get("page", "?")
        conf = table.get("confidence", "?")
        print(f"    Tabela {i+1}: página {page}, {n_rows} linhas, confiança {conf}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extrair tabelas de PDFs usando heurísticas pypdf",
    )
    parser.add_argument("pdf_path", help="Caminho do PDF")
    parser.add_argument("--output", "-o", default=None,
                        help="Diretório de saída (padrão: mesmo local do PDF)")
    parser.add_argument("--pages", default=None,
                        help="Páginas específicas (ex: 10-20 ou 1,3,5)")
    parser.add_argument("--format", choices=["csv", "json"], default="csv",
                        help="Formato de saída (padrão: csv)")

    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"Arquivo não encontrado: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Parse pages
    pages = None
    if args.pages:
        pages = []
        for part in args.pages.split(","):
            if "-" in part:
                start, end = part.split("-", 1)
                pages.extend(range(int(start) - 1, int(end)))
            else:
                pages.append(int(part) - 1)  # 0-indexed

    # Output directory
    if args.output:
        output_dir = args.output
    else:
        output_dir = str(Path(args.pdf_path).parent / "tables")

    print(f"\nExtraindo tabelas de: {args.pdf_path}")
    tables = extract_all_tables(args.pdf_path, pages)
    print_table_summary(tables)

    if tables:
        if args.format == "csv":
            save_tables_csv(tables, output_dir)
        else:
            save_tables_json(tables, output_dir)
    else:
        print("  Nenhuma tabela encontrada. Tente ajustar os parâmetros ou usar modo técnico.")


if __name__ == "__main__":
    main()
