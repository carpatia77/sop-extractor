#!/usr/bin/env python3
"""Knowledge compilation pipeline — automated hand-off from scan to agent.

Closes the hand-off gap: reads source files, generates a compilation prompt,
calls claude CLI via subprocess, parses the response, and writes structured
output (SOPs, principles, concepts, cross-analysis).

Usage:
    python scripts/compile.py <path>                    # single file
    python scripts/compile.py <dir> --batch             # all .txt in dir
    python scripts/compile.py <path> --dry-run          # prompt preview only
    python scripts/compile.py <path> --model sonnet     # override model
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Compilation prompt template
# ---------------------------------------------------------------------------

COMPILATION_PROMPT = textwrap.dedent("""\
You are a knowledge compiler. Read the following source text and extract
DECISION LOGIC only — no summaries, no opinions, no filler.

For each source, produce a structured compilation with these sections:

## SOPs (Standard Operating Procedures)
For each procedure the author teaches:
- **Name**: short descriptive name
- **Steps**: numbered step-by-step procedure
- **When to use**: decision conditions

## Fundamental Principles
For each absolute rule the author states:
- **Statement**: one sentence
- **Epistemic status**: certain | probable | speculative
- **Evidence**: brief quote or paraphrase from source

## Key Concepts
For each technical term:
- **Term**: name
- **Definition**: one sentence
- **Used in**: which SOPs or principles reference it

## Named References
People, papers, books, models mentioned.

RULES:
1. Extract DECISION LOGIC, not summaries
2. Every principle MUST have epistemic status (certain/probable/speculative)
3. Be concise — one line per principle, one line per concept
4. Do not fabricate — if something is not in the source, don't invent it
5. Group related SOPs under thematic headers

---
SOURCE: {filename}
CONTENT:
{content}
""")


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------

def generate_prompt(filepath: Path, content: str) -> str:
    """Generate a compilation prompt for a single source file."""
    return COMPILATION_PROMPT.format(
        filename=filepath.name,
        content=content,
    )


# ---------------------------------------------------------------------------
# Agent CLI invocation (subprocess)
# ---------------------------------------------------------------------------

def call_agent(prompt: str, model: str = None, timeout: int = 300) -> str:
    """Call claude CLI via subprocess in print mode.

    Uses -p (print mode) for non-interactive output.
    Restricts tools to Read only — agent can read but not write.
    """
    cmd = ["claude", "-p", "--allowedTools", "Read"]

    if model:
        cmd.extend(["--model", model])

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                print(f"  Agent error: {stderr[:200]}", file=sys.stderr)
            return result.stdout.strip()
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print(f"  Agent timed out after {timeout}s", file=sys.stderr)
        return ""
    except FileNotFoundError:
        print("  Error: 'claude' CLI not found. Install with: npm install -g @anthropic-ai/claude-code", file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def write_compilation(filepath: Path, prompt: str, response: str, output_dir: Path):
    """Write compilation output for a single source file."""
    stem = filepath.stem
    out_dir = output_dir / "compilation"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Human-readable markdown
    md_path = out_dir / f"{stem}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Knowledge Compilation: {filepath.name}\n\n")
        f.write(f"**Source**: {filepath.name}\n")
        f.write(f"**Compiled**: {datetime.now(timezone.utc).isoformat()}\n\n---\n\n")
        f.write(response)
    print(f"  Written: {md_path}")

    # Prompt + response as JSON (provenance)
    meta_path = out_dir / f"{stem}.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "source": filepath.name,
            "source_path": str(filepath),
            "compiled_at": datetime.now(timezone.utc).isoformat(),
            "prompt_chars": len(prompt),
            "response_chars": len(response),
            "response_lines": response.count("\n") + 1,
        }, f, indent=2)


def write_batch_summary(results: list, output_dir: Path):
    """Write batch compilation summary."""
    out_dir = output_dir / "compilation"
    out_dir.mkdir(parents=True, exist_ok=True)

    total_files = len(results)
    successful = sum(1 for r in results if r["success"])
    failed = total_files - successful
    total_chars = sum(r["response_chars"] for r in results)

    summary = f"""# Batch Compilation Summary

**Date**: {datetime.now(timezone.utc).isoformat()}
**Files processed**: {total_files}
**Successful**: {successful}
**Failed**: {failed}
**Total output**: {total_chars:,} characters

## Per-file results

| File | Status | Output (chars) | Time (s) |
|---|---|---|---|
"""
    for r in results:
        status = "OK" if r["success"] else "FAILED"
        summary += f"| {r['filename']} | {status} | {r['response_chars']:,} | {r['elapsed']:.1f} |\n"

    if failed > 0:
        summary += "\n## Failed files\n\n"
        for r in results:
            if not r["success"]:
                summary += f"- {r['filename']}: {r.get('error', 'unknown')}\n"

    summary_path = out_dir / "batch_summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"\n  Batch summary: {summary_path}")

    # Provenance
    run_path = out_dir / "run.json"
    with open(run_path, "w", encoding="utf-8") as f:
        json.dump({
            "compiled_at": datetime.now(timezone.utc).isoformat(),
            "total_files": total_files,
            "successful": successful,
            "failed": failed,
            "total_chars": total_chars,
            "results": results,
        }, f, indent=2)


# ---------------------------------------------------------------------------
# Batch discovery
# ---------------------------------------------------------------------------

def discover_sources(directory: Path) -> list[Path]:
    """Find all compilable source files in a directory."""
    extensions = {".txt", ".srt", ".md"}
    sources = []
    for f in sorted(directory.iterdir()):
        if f.is_file() and f.suffix.lower() in extensions and not f.name.startswith("_"):
            # Skip metadata files
            if "_metadata.json" in f.name:
                continue
            sources.append(f)
    return sources


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Knowledge compilation — automated hand-off from scan to agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              sopx compile transcript.txt           # single file
              sopx compile transcripts/ --batch     # all files in dir
              sopx compile transcript.txt --dry-run  # preview prompt only
              sopx compile transcripts/ --model sonnet  # override model
        """),
    )
    parser.add_argument("path", help="Source file or directory")
    parser.add_argument("--batch", action="store_true",
                        help="Process all .txt/.srt/.md files in directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show prompt without calling agent")
    parser.add_argument("--model", default=None,
                        help="Override default model (e.g., sonnet, haiku)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output directory (default: same as input)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="Agent timeout in seconds (default: 300)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Delay between files in batch mode (default: 2.0s)")

    args = parser.parse_args()
    input_path = Path(args.path)

    if not input_path.exists():
        print(f"Error: path not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Determine output directory
    if args.output:
        output_dir = Path(args.output)
    elif input_path.is_dir():
        output_dir = input_path
    else:
        output_dir = input_path.parent

    # Discover sources
    if args.batch or input_path.is_dir():
        sources = discover_sources(input_path)
        if not sources:
            print(f"No compilable files found in {input_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(sources)} sources to compile")
    else:
        sources = [input_path]

    # Compile
    results = []
    for i, filepath in enumerate(sources, 1):
        print(f"\n[{i}/{len(sources)}] {filepath.name}")

        # Read source
        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  Read error: {e}", file=sys.stderr)
            results.append({
                "filename": filepath.name,
                "success": False,
                "error": str(e),
                "response_chars": 0,
                "elapsed": 0,
            })
            continue

        # Generate prompt
        prompt = generate_prompt(filepath, content)
        print(f"  Prompt: {len(prompt):,} chars")

        if args.dry_run:
            print("\n--- DRY RUN: Prompt preview ---\n")
            print(prompt[:2000])
            if len(prompt) > 2000:
                print(f"\n... ({len(prompt) - 2000} more chars)")
            results.append({
                "filename": filepath.name,
                "success": True,
                "response_chars": 0,
                "elapsed": 0,
            })
            continue

        # Call agent
        t0 = time.time()
        response = call_agent(prompt, model=args.model, timeout=args.timeout)
        elapsed = time.time() - t0

        if not response:
            print("  FAILED: empty response from agent")
            results.append({
                "filename": filepath.name,
                "success": False,
                "error": "empty agent response",
                "response_chars": 0,
                "elapsed": elapsed,
            })
            continue

        # Write output
        write_compilation(filepath, prompt, response, output_dir)

        print(f"  OK: {len(response):,} chars, {elapsed:.1f}s")
        results.append({
            "filename": filepath.name,
            "success": True,
            "response_chars": len(response),
            "elapsed": elapsed,
        })

        # Rate limit between files
        if i < len(sources) and not args.dry_run:
            time.sleep(args.delay)

    # Batch summary
    if len(sources) > 1:
        write_batch_summary(results, output_dir)

    # Final stats
    successful = sum(1 for r in results if r["success"])
    total_chars = sum(r["response_chars"] for r in results)
    total_time = sum(r["elapsed"] for r in results)
    print(f"\n{'='*50}")
    print(f"Done: {successful}/{len(sources)} files, {total_chars:,} chars, {total_time:.1f}s")


if __name__ == "__main__":
    main()
