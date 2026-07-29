#!/usr/bin/env python3
"""Table Extractor — extract tables from PDFs using pdfplumber.

Uses pdfplumber's table detection which parses the actual PDF layout
(coordinates, column positions) to extract properly separated columns.

Falls back to pypdf heuristics if pdfplumber is not installed.

Usage:
    python scripts/extract_tables.py <pdf_path> [--output <dir>]
    python scripts/extract_tables.py <pdf_path> --pages 10-20
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# pdfplumber extraction (preferred)
# ---------------------------------------------------------------------------

def extract_with_pdfplumber(pdf_path: str, pages: list[int] | None = None) -> list[dict]:
    """Extract tables using pdfplumber's layout-aware parser.

    Returns list of tables: [{page, rows: [[cells]], n_rows, method}]
    """
    try:
        import pdfplumber
    except ImportError:
        return []

    all_tables = []
    with pdfplumber.open(pdf_path) as pdf:
        page_indices = pages if pages else range(len(pdf.pages))

        for page_num in page_indices:
            if page_num >= len(pdf.pages):
                continue
            page = pdf.pages[page_num]

            try:
                tables = page.extract_tables()
            except (TypeError, ValueError, AttributeError, RuntimeError):
                tables = []

            for table in tables:
                if not table or len(table) < 2:
                    continue
                # Clean rows: strip whitespace, replace None with empty string
                clean_rows = []
                for row in table:
                    clean_row = [str(cell).strip() if cell else "" for cell in row]
                    if any(clean_row):  # Skip empty rows
                        clean_rows.append(clean_row)

                if len(clean_rows) >= 2:
                    all_tables.append({
                        "page": page_num + 1,  # 1-indexed
                        "rows": clean_rows,
                        "n_rows": len(clean_rows),
                        "n_cols": max(len(r) for r in clean_rows),
                        "method": "pdfplumber",
                    })

    return all_tables


# ---------------------------------------------------------------------------
# pypdf fallback (heuristics)
# ---------------------------------------------------------------------------

def extract_with_pypdf(pdf_path: str, pages: list[int] | None = None) -> list[dict]:
    """Fallback extraction using pypdf text + heuristics."""
    try:
        import pypdf
    except ImportError:
        return []

    try:
        from table_heuristics import TABULAR_LINE_RE
    except ImportError:
        from scripts.table_heuristics import TABULAR_LINE_RE

    all_tables = []
    with open(pdf_path, "rb") as f:
        reader = pypdf.PdfReader(f)
        page_indices = pages if pages else range(len(reader.pages))

        for page_num in page_indices:
            if page_num >= len(reader.pages):
                continue
            try:
                text = reader.pages[page_num].extract_text() or ""
            except (TypeError, ValueError, AttributeError, RuntimeError):
                continue

            lines = [l for l in text.splitlines() if l.strip()]
            if not lines:
                continue

            # Detect table regions
            current_table = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    if current_table and len(current_table) >= 3:
                        all_tables.append({
                            "page": page_num + 1,
                            "rows": current_table,
                            "n_rows": len(current_table),
                            "n_cols": max(len(r) for r in current_table) if current_table else 0,
                            "method": "pypdf-heuristic",
                        })
                    current_table = []
                    continue

                if TABULAR_LINE_RE.search(stripped):
                    import re
                    cells = re.split(r'\s{2,}|\t|\$|(?<=\d) (?=[A-Z])', stripped)
                    cells = [c.strip() for c in cells if c.strip()]
                    if len(cells) >= 2:
                        current_table.append(cells)

            if current_table and len(current_table) >= 3:
                all_tables.append({
                    "page": page_num + 1,
                    "rows": current_table,
                    "n_rows": len(current_table),
                    "n_cols": max(len(r) for r in current_table) if current_table else 0,
                    "method": "pypdf-heuristic",
                })

    return all_tables


# ---------------------------------------------------------------------------
# Unified extraction
# ---------------------------------------------------------------------------

def extract_all_tables(pdf_path: str, pages: list[int] | None = None) -> list[dict]:
    """Extract tables from PDF. Uses pdfplumber if available, falls back to pypdf.

    Returns list of tables with page number, rows, and column count.
    """
    if not os.path.exists(pdf_path):
        return []

    # Try pdfplumber first (layout-aware, proper column separation)
    tables = extract_with_pdfplumber(pdf_path, pages)
    if tables:
        return tables

    # Fallback to pypdf heuristics
    return extract_with_pypdf(pdf_path, pages)


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

    # Group by method
    methods = {}
    for t in tables:
        m = t.get("method", "unknown")
        methods[m] = methods.get(m, 0) + 1

    print(f"\n  {len(tables)} tabelas detectadas:")
    for method, count in methods.items():
        print(f"    Método: {method} ({count} tabelas)")

    for i, table in enumerate(tables[:10]):
        n_rows = table.get("n_rows", len(table.get("rows", [])))
        n_cols = table.get("n_cols", 0)
        page = table.get("page", "?")
        print(f"    Tabela {i+1}: página {page}, {n_rows}x{n_cols}")

    if len(tables) > 10:
        print(f"    ... e mais {len(tables) - 10} tabelas")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extrair tabelas de PDFs (pdfplumber ou pypdf fallback)",
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

    # Check available libraries
    try:
        import pdfplumber  # noqa: F401
        print("  Método: pdfplumber (layout-aware)")
    except ImportError:
        print("  Método: pypdf heuristics (pdfplumber não disponível)")

    tables = extract_all_tables(args.pdf_path, pages)
    print_table_summary(tables)

    if tables:
        if args.format == "csv":
            save_tables_csv(tables, output_dir)
        else:
            save_tables_json(tables, output_dir)
    else:
        print("  Nenhuma tabela encontrada.")


if __name__ == "__main__":
    main()
