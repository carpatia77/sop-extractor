#!/usr/bin/env python3
"""Knowledge compilation pipeline — automated hand-off from scan to agent.

Closes the hand-off gap: reads source files, generates a compilation prompt,
calls agent CLI via subprocess, parses the response, and writes structured
output (SOPs, principles, concepts, cross-analysis).

Usage:
    python scripts/compile.py <path>                    # single file
    python scripts/compile.py <dir> --batch             # all .txt/.srt recursively
    python scripts/compile.py <path> --dry-run          # prompt preview only
    python scripts/compile.py <path> --model sonnet     # override model
    python scripts/compile.py <path> --agent copilot    # use copilot instead
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Grounding check — reuse verify_concept_presence functions (§2.3)
# ---------------------------------------------------------------------------

try:
    from scripts.verify_concept_presence import (
        score_principle as _score_principle,
        REVIEW_FLOOR as _REVIEW_FLOOR,
    )
    from scripts.domain_synonyms import load_domain_synonyms, normalize_text
    from scripts.review_gate import (
        compute_sample_indices,
        prompt_operator,
        record_review,
        record_not_reviewed,
        should_abort_batch,
    )
except ImportError:
    from verify_concept_presence import (
        score_principle as _score_principle,
        REVIEW_FLOOR as _REVIEW_FLOOR,
    )
    from domain_synonyms import load_domain_synonyms, normalize_text
    from review_gate import (
        compute_sample_indices,
        prompt_operator,
        record_review,
        record_not_reviewed,
        should_abort_batch,
    )

# ---------------------------------------------------------------------------
# SRT stripping
# ---------------------------------------------------------------------------

_SRT_CUE_RE = re.compile(
    r"^\d+\s*\n"                              # cue number
    r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*"  # timestamps
    r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*\n",      # timestamps
    re.MULTILINE,
)


def strip_srt(text: str) -> str:
    """Strip SRT markup: cue numbers, timestamps, blank lines between cues."""
    text = _SRT_CUE_RE.sub("", text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Source hash
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_pdf(path: Path) -> str:
    """Extract text from PDF via pdfplumber (if available) or fallback."""
    try:
        import pdfplumber
        texts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    texts.append(text)
        return "\n\n".join(texts)
    except ImportError:
        raise RuntimeError(
            "pdfplumber is required for PDF extraction. "
            "Install with: pip install pdfplumber"
        )


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
# Chunking for large sources
# ---------------------------------------------------------------------------

MAX_CHARS_PER_CHUNK = 120_000  # ~30K tokens, safe for most context windows


def chunk_content(content: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> list[str]:
    """Split content into chunks that fit within context window."""
    if len(content) <= max_chars:
        return [content]
    chunks = []
    sentences = re.split(r"(?<=[.!?])\s+", content)
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 > max_chars:
            if current:
                chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip() if current else sentence
    if current:
        chunks.append(current)
    return chunks


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

AGENT_COMMANDS = {
    "claude": ["claude", "-p", "--allowedTools", "Read"],
    "copilot": ["copilot", "ask", "--stdio"],
    "amp": ["amp", "-p"],
}

# Direct API models (no CLI needed — just API key)
DIRECT_API_MODELS = {
    "claude-sonnet-4-20250514": "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022": "claude-3-5-sonnet-20241022",
    "claude-3-haiku-20240307": "claude-3-haiku-20240307",
}


def _call_api_direct(
    prompt: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    base_url: str = "",
    timeout: int = 300,
) -> str:
    """Call any OpenAI-compatible API directly via HTTP (no CLI dependency).

    Supports: Anthropic, OpenAI, Nvidia NIM, Groq, Ollama, Together, DeepSeek, etc.
    """
    import urllib.request
    import urllib.error

    # Determine API format from base_url
    is_anthropic = "anthropic" in (base_url or "").lower() or model.startswith("claude")

    if is_anthropic:
        return _call_anthropic_api(prompt, api_key, model, timeout)

    # OpenAI-compatible format (default for most providers)
    base = (base_url or "https://api.openai.com").rstrip("/")
    # If base URL already ends with a path (e.g. /v1), don't append /v1 again
    if base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/v1/chat/completions"

    payload = json.dumps({
        "model": model,
        "max_tokens": 16384,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"API error {e.code}: {body}")
    except Exception as e:
        raise RuntimeError(f"API call failed: {e}")


def _call_anthropic_api(
    prompt: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    timeout: int = 300,
) -> str:
    """Call Anthropic Messages API directly."""
    import urllib.request
    import urllib.error

    model_id = DIRECT_API_MODELS.get(model, model)
    payload = json.dumps({
        "model": model_id,
        "max_tokens": 16384,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            texts = []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    texts.append(block["text"])
            return "\n".join(texts)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"API error {e.code}: {body}")
    except Exception as e:
        raise RuntimeError(f"API call failed: {e}")


def call_agent(
    prompt: str,
    agent: str = "claude",
    model: str = None,
    timeout: int = 300,
) -> str:
    """Call agent CLI via subprocess in print mode.

    If LLM_API_KEY env var is set, calls API directly (no CLI needed).
    LLM_BASE_URL and LLM_MODEL env vars configure the endpoint.
    Raises RuntimeError on non-zero exit (never silently returns partial output).
    """
    api_key = os.environ.get("LLM_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "")

    # Direct API mode — no CLI dependency
    if api_key:
        return _call_api_direct(
            prompt, api_key,
            model=model or os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514"),
            base_url=base_url,
            timeout=timeout,
        )

    # CLI mode
    if agent not in AGENT_COMMANDS:
        raise ValueError(f"Unknown agent: {agent}. Supported: {list(AGENT_COMMANDS)}")

    cmd = list(AGENT_COMMANDS[agent])

    if agent == "claude" and model:
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
            stdout = result.stdout.strip()
            detail = stderr[:300] if stderr else stdout[:300]
            raise RuntimeError(
                f"Agent '{agent}' failed (exit {result.returncode}): {detail}"
            )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Agent '{agent}' timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError(
            f"Agent '{agent}' CLI not found. "
            f"Set ANTHROPIC_API_KEY or install: npm install -g @anthropic-ai/claude-code"
        )


# ---------------------------------------------------------------------------
# Structured parse (§2.1)
# ---------------------------------------------------------------------------

def parse_compilation(text: str) -> dict:
    """Parse agent output into structured sections."""
    sections = {"sops": [], "principles": [], "concepts": [], "references": []}

    # Split by ## or ### headers (LLMs may use either level)
    parts = re.split(r"^#{2,3} ", text, flags=re.MULTILINE)

    for part in parts:
        header = part.split("\n", 1)[0].strip().lower()
        body = part.split("\n", 1)[1] if "\n" in part else ""

        if "sop" in header or "procedure" in header:
            sections["sops"] = _parse_sops(body)
        elif "principle" in header or "fundamental" in header:
            sections["principles"] = _parse_principles(body)
        elif "concept" in header or "key" in header:
            sections["concepts"] = _parse_concepts(body)
        elif "reference" in header or "named" in header:
            sections["references"] = _parse_references(body)

    return sections


def _parse_sops(text: str) -> list[dict]:
    sops = []
    # Split on ### **Name**: or #### **Title** patterns (h3/h4 + bold)
    # Also handles: * **Name**: value
    blocks = re.split(
        r"\n#{2,4}\s+\*{0,2}(?:[Nn]ame|[A-Z][^\n]{2,60})\*{0,2}\s*:?\s*"
        r"|\n\*{0,2}[Nn]ame\*{0,2}\s*:\s*",
        text,
    )
    for block in blocks[1:]:  # skip preamble
        name_match = re.match(r"\s*\*{0,2}(.+?)\*{0,2}(?:\n|$)", block)
        name = name_match.group(1).strip().rstrip("*") if name_match else ""
        # Strip **Name**: prefix if present
        name = re.sub(r"^\*{0,2}[Nn]ame\*{0,2}\s*:\s*", "", name).strip()

        steps = []
        for m in re.finditer(r"\d+\.\s+(.+?)(?=\n\d+\.|\n\*{0,2}When|\Z)", block, re.DOTALL):
            steps.append(m.group(1).strip())

        when = ""
        when_match = re.search(r"\*{0,2}When to use\*{0,2}:\s*(.+?)(?=\n#{2,3}\s|\n\*{0,2}Name|\Z)", block, re.DOTALL)
        if when_match:
            when = when_match.group(1).strip()

        if name:
            sops.append({"name": name, "steps": steps, "when_to_use": when})
    return sops


def _parse_principles(text: str) -> list[dict]:
    principles = []
    # Match both "- **Statement**:" and "* **Statement**:" formats
    blocks = re.split(r"\n[-*]\s+\*{0,2}Statement\*{0,2}:", text)
    for block in blocks[1:]:
        statement = re.match(r"\s*(.+?)(?:\n|$)", block)
        statement = statement.group(1).strip() if statement else ""

        epistemic = ""
        ep_match = re.search(r"\*{0,2}Epistemic status\*{0,2}:\s*(\w+)", block)
        if ep_match:
            epistemic = ep_match.group(1).strip()

        evidence = ""
        ev_match = re.search(r"\*{0,2}Evidence\*{0,2}:\s*(.+?)(?=\n-\s|\Z)", block, re.DOTALL)
        if ev_match:
            evidence = ev_match.group(1).strip()

        if statement:
            principles.append({
                "statement": statement,
                "epistemic_status": epistemic,
                "evidence": evidence,
            })
    return principles


def _parse_concepts(text: str) -> list[dict]:
    concepts = []
    # Match both "- **Term**:" and "* **Term**:" formats
    blocks = re.split(r"\n[-*]\s+\*{0,2}Term\*{0,2}:", text)
    for block in blocks[1:]:
        term = re.match(r"\s*(.+?)(?:\n|$)", block)
        term = term.group(1).strip() if term else ""

        definition = ""
        def_match = re.search(r"\*{0,2}Definition\*{0,2}:\s*(.+?)(?:\n|$)", block)
        if def_match:
            definition = def_match.group(1).strip()

        used_in = ""
        ui_match = re.search(r"\*{0,2}Used in\*{0,2}:\s*(.+?)(?:\n|$)", block)
        if ui_match:
            used_in = ui_match.group(1).strip()

        if term:
            concepts.append({
                "term": term,
                "definition": definition,
                "used_in": used_in,
            })
    return concepts


def _parse_references(text: str) -> list[str]:
    refs = []
    for line in text.strip().splitlines():
        line = line.strip().lstrip("-*").strip()
        if line and not line.startswith("#"):
            refs.append(line)
    return refs


def _deduplicate(items: list, kind: str) -> list:
    """Remove duplicate entries across chunk boundaries."""
    if kind == "references":
        seen = set()
        unique = []
        for item in items:
            normalized = item.strip().lower()
            if normalized not in seen:
                seen.add(normalized)
                unique.append(item)
        return unique
    # For sops/principles/concepts: dedupe by name/term/statement
    key_field = {"sops": "name", "principles": "statement", "concepts": "term"}.get(kind)
    if not key_field:
        return items
    seen = set()
    unique = []
    for item in items:
        k = item.get(key_field, "").strip().lower()
        if k and k not in seen:
            seen.add(k)
            unique.append(item)
        elif not k:
            unique.append(item)
    return unique


# ---------------------------------------------------------------------------
# Grounding check (§2.3) — anti-hallucination gate
# ---------------------------------------------------------------------------

def grounding_check(
    principles: list[dict],
    source_content: str,
    floor: float = _REVIEW_FLOOR,
    synonym_map: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """Score each principle against the source corpus and filter ungrounded ones.

    Returns (kept, flagged) where:
      - kept: principles with score >= floor (written to output)
      - flagged: principles with score < floor (logged, not written)

    Reuses salient_terms + score_principle from verify_concept_presence.py.
    """
    if not principles:
        return [], []

    # Build corpus from source content (lowercased, hyphen-split)
    corpus = source_content.lower()
    corpus = re.sub(r'[-/]', ' ', corpus)
    if synonym_map:
        corpus = normalize_text(corpus, synonym_map)

    kept = []
    flagged = []
    for p in principles:
        statement = p.get("statement", "")
        if not statement:
            kept.append(p)
            continue

        r = _score_principle(statement, corpus, synonym_map)
        p_with_meta = {**p, "_grounding_score": r["score"], "_absent_terms": r["absent"]}

        if r["score"] < floor:
            flagged.append(p_with_meta)
        else:
            kept.append(p_with_meta)

    return kept, flagged


# ---------------------------------------------------------------------------
# Batch discovery — RECURSIVE (§2.1 blocker fix)
# ---------------------------------------------------------------------------

def discover_sources(directory: Path) -> list[Path]:
    """Find all compilable source files recursively.

    Searches subdirectories to handle ingestion output structure:
      output/<video_id>/transcript.srt
      output/<video_id>/full_text.txt

    Excludes compilation/ subdirectory (output from previous runs).
    """
    extensions = {".txt", ".srt", ".md"}
    sources = []
    for f in sorted(directory.rglob("*")):
        if not f.is_file():
            continue
        if "compilation" in f.parts:
            continue
        if f.suffix.lower() not in extensions:
            continue
        if f.name.startswith("_"):
            continue
        if "_metadata.json" in f.name:
            continue
        sources.append(f)
    return sources


# ---------------------------------------------------------------------------
# Safe cache/output key — uses relative path, not bare stem
# ---------------------------------------------------------------------------

def cache_key(filepath: Path, input_root: Path) -> str:
    """Generate a collision-safe key from the file's relative path.

    output/<id>/transcript.srt → "output__<id>__transcript"
    flat_file.txt              → "flat_file"
    """
    try:
        rel = filepath.relative_to(input_root)
    except ValueError:
        rel = filepath.name
    return str(rel).replace("/", "__").replace(os.sep, "__")


# ---------------------------------------------------------------------------
# Source metadata reader (§2.2) — propagates upload_date into provenance
# ---------------------------------------------------------------------------

def read_source_metadata(filepath: Path) -> dict:
    """Read metadata.json from the source file's parent directory.

    Ingestion writes metadata.json with upload_date, title, uploader, etc.
    Returns a dict with provenance-relevant fields, or empty dict if not found.
    """
    meta_path = filepath.parent / "metadata.json"
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    provenance = {}
    for key in ("upload_date", "title", "uploader", "canonical_id", "language"):
        if key in meta and meta[key]:
            provenance[key] = meta[key]
    return provenance


# ---------------------------------------------------------------------------
# Output writing with provenance (§2.2) — atomic writes
# ---------------------------------------------------------------------------

def write_compilation(
    filepath: Path,
    prompt: str,
    response: str,
    sections: dict,
    output_dir: Path,
    agent: str,
    model: str,
    source_hash: str,
    key: str,
    source_metadata: dict | None = None,
):
    """Write compilation output for a single source file.

    Uses atomic writes (write to .tmp, then rename) to prevent corrupted
    JSON from being treated as a cache hit on resume.
    """
    out_dir = output_dir / "compilation"
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    data = {
        "source": filepath.name,
        "source_path": str(filepath),
        "source_sha256": source_hash,
        "compiled_at": now,
        "agent": agent,
        "model": model or "default",
        "prompt_chars": len(prompt),
        "response_chars": len(response),
        "sops": sections["sops"],
        "principles": sections["principles"],
        "concepts": sections["concepts"],
        "references": sections["references"],
    }

    # Include refutation summary if present (§2.7)
    ref_summary = sections.get("refutation_summary")
    if ref_summary:
        data["refutation_summary"] = ref_summary

    # Include evidence ledger if present (§2.8)
    ledger = sections.get("evidence_ledger")
    if ledger:
        data["evidence_ledger"] = ledger

    # Propagate source ingestion metadata (§2.2)
    if source_metadata:
        data["source_metadata"] = source_metadata

    meta = source_metadata or {}

    # Atomic JSON write (write tmp, then rename)
    json_path = out_dir / f"{key}.json"
    tmp_json = out_dir / f"{key}.json.tmp"
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp_json.rename(json_path)

    # Atomic markdown write
    md_path = out_dir / f"{key}.md"
    tmp_md = out_dir / f"{key}.md.tmp"
    with open(tmp_md, "w", encoding="utf-8") as f:
        f.write(f"# Knowledge Compilation: {filepath.name}\n\n")
        f.write(f"**Source**: {filepath.name}\n")
        if meta.get("upload_date"):
            f.write(f"**Source date**: {meta['upload_date']}\n")
        if meta.get("title"):
            f.write(f"**Title**: {meta['title']}\n")
        f.write(f"**Compiled**: {now}\n")
        f.write(f"**Agent**: {agent}\n")
        f.write(f"**Model**: {model or 'default'}\n")
        f.write(f"**Source SHA-256**: {source_hash[:16]}...\n\n---\n\n")
        f.write(response)
    tmp_md.rename(md_path)

    print(f"  Written: {json_path.name}")


def write_batch_summary(results: list, output_dir: Path, review_log: list | None = None):
    """Write batch compilation summary with provenance."""
    out_dir = output_dir / "compilation"
    out_dir.mkdir(parents=True, exist_ok=True)

    total_files = len(results)
    successful = sum(1 for r in results if r["success"])
    failed = total_files - successful
    total_chars = sum(r.get("response_chars", 0) for r in results)
    total_principles = sum(r.get("principles_count", 0) for r in results)
    total_sops = sum(r.get("sops_count", 0) for r in results)
    total_grounding_flagged = sum(r.get("grounding_flagged", 0) for r in results)

    summary = f"""# Batch Compilation Summary

**Date**: {datetime.now(timezone.utc).isoformat()}
**Files processed**: {total_files}
**Successful**: {successful}
**Failed**: {failed}
**Total output**: {total_chars:,} characters
**Total SOPs**: {total_sops}
**Total principles**: {total_principles}
**Grounding flagged**: {total_grounding_flagged} (dropped, score < floor)

## Per-file results

| File | Status | SOPs | Principles | Concepts | Flagged | Chars | Time (s) |
|---|---|---|---|---|---|---|---|
"""
    for r in results:
        status = "OK" if r["success"] else "FAILED"
        sops = r.get("sops_count", 0)
        prins = r.get("principles_count", 0)
        cons = r.get("concepts_count", 0)
        flagged = r.get("grounding_flagged", 0)
        chars = r.get("response_chars", 0)
        t = r.get("elapsed", 0)
        summary += f"| {r['filename']} | {status} | {sops} | {prins} | {cons} | {flagged} | {chars:,} | {t:.1f} |\n"

    if failed > 0:
        summary += "\n## Failed files\n\n"
        for r in results:
            if not r["success"]:
                summary += f"- `{r['filename']}`: {r.get('error', 'unknown')}\n"

    summary_path = out_dir / "batch_summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"\n  Batch summary: {summary_path}")

    # Provenance
    run_path = out_dir / "run.json"
    provenance = {
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "total_files": total_files,
        "successful": successful,
        "failed": failed,
        "total_chars": total_chars,
        "total_sops": total_sops,
        "total_principles": total_principles,
        "total_grounding_flagged": total_grounding_flagged,
        "results": results,
    }
    if review_log is not None:
        provenance["review_gate"] = review_log
    with open(run_path, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)


# ---------------------------------------------------------------------------
# Cache check for batch resume (§2.4)
# ---------------------------------------------------------------------------

def is_compiled(key: str, output_dir: Path) -> bool:
    """Check if a source was already compiled (cache sentinel).

    Checks for valid JSON (not just file existence) to handle corrupted
    writes from crashes.
    """
    json_path = output_dir / "compilation" / f"{key}.json"
    if not json_path.exists():
        return False
    # Validate JSON is not corrupted (crash during write)
    try:
        with open(json_path, encoding="utf-8") as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, OSError):
        json_path.unlink(missing_ok=True)
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Knowledge compilation — automated hand-off from scan to agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              sopx compile transcript.txt              # single file
              sopx compile output/ --batch             # recursive batch
              sopx compile transcript.txt --dry-run    # preview prompt only
              sopx compile output/ --model sonnet      # override model
              sopx compile output/ --agent copilot     # use copilot CLI
        """),
    )
    parser.add_argument("path", help="Source file or directory")
    parser.add_argument("--batch", action="store_true",
                        help="Recursively process all .txt/.srt/.md files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show prompt without calling agent")
    parser.add_argument("--model", default=None,
                        help="Override default model (e.g., sonnet, haiku)")
    parser.add_argument("--agent", default="claude", choices=list(AGENT_COMMANDS),
                        help="Agent CLI to use (default: claude)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output directory (default: same as input)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="Agent timeout in seconds (default: 300)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Delay between files in batch mode (default: 2.0s)")
    parser.add_argument("--grounding-check", action="store_true", default=True,
                        help="Run grounding check on principles before writing (default: on)")
    parser.add_argument("--no-grounding-check", dest="grounding_check", action="store_false",
                        help="Disable grounding check (principles written as-is)")
    parser.add_argument("--grounding-floor", type=float, default=_REVIEW_FLOOR,
                        help=f"Minimum grounding score to keep a principle (default: {_REVIEW_FLOOR})")
    parser.add_argument("--domain", default=None,
                        help="Domain ID for synonym expansion during grounding check")
    parser.add_argument("--review-sample-rate", type=float, default=0.10,
                        help="Fraction of batch items to sample for human review (default: 0.10). Set to 0 to disable.")
    parser.add_argument("--continue-on-reject", action="store_true",
                        help="Continue batch after a sampled item is rejected (default: abort)")
    parser.add_argument("--refutation-chain", action="store_true", default=True,
                        help="Generate refutation chains for principles (default: on)")
    parser.add_argument("--no-refutation-chain", dest="refutation_chain", action="store_false",
                        help="Disable refutation chain generation")
    parser.add_argument("--refutation-overlap-threshold", type=float, default=0.7,
                        help="Max semantic overlap between claim and alternative (default 0.7)")

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
    batch_mode = args.batch or input_path.is_dir()
    if batch_mode:
        sources = discover_sources(input_path)
        if not sources:
            print(f"No compilable files found in {input_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(sources)} sources to compile")
    else:
        sources = [input_path]

    # Compile
    results = []
    review_log = []
    skipped = 0

    # Pre-compute sample indices for review gate (§2.5)
    sample_indices = set()
    if batch_mode and not args.dry_run and args.review_sample_rate > 0:
        sample_indices = set(compute_sample_indices(
            len(sources), sample_rate=args.review_sample_rate,
        ))
        print(f"Review gate: {len(sample_indices)}/{len(sources)} items sampled "
              f"(rate={args.review_sample_rate:.0%})")

    for i, filepath in enumerate(sources, 1):
        # Collision-safe key from relative path
        key = cache_key(filepath, input_path)

        # Cache check (§2.4)
        if not args.dry_run and is_compiled(key, output_dir):
            skipped += 1
            continue

        print(f"\n[{i}/{len(sources)}] {filepath.name}  [{key}]")

        # Read source (PDF extraction via pdfplumber, everything else as text)
        try:
            if filepath.suffix.lower() == ".pdf":
                content = _extract_pdf(filepath)
            else:
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

        # Strip SRT if needed (keep original for Evidence Ledger locator)
        original_text = content
        if filepath.suffix.lower() == ".srt":
            content = strip_srt(content)

        # Source hash for provenance
        source_hash = sha256_file(filepath)

        # Chunk if too large
        chunks = chunk_content(content)
        if len(chunks) > 1:
            print(f"  Large source: {len(content):,} chars → {len(chunks)} chunks")

        all_response_parts = []
        all_sections = {"sops": [], "principles": [], "concepts": [], "references": []}
        total_elapsed = 0

        for ci, chunk in enumerate(chunks):
            if len(chunks) > 1:
                print(f"  Chunk {ci+1}/{len(chunks)}: {len(chunk):,} chars")

            prompt = generate_prompt(filepath, chunk)
            print(f"  Prompt: {len(prompt):,} chars")

            if args.dry_run:
                print("\n--- DRY RUN: Prompt preview ---\n")
                print(prompt[:2000])
                if len(prompt) > 2000:
                    print(f"\n... ({len(prompt) - 2000} more chars)")
                all_response_parts.append("[dry-run]")
                continue

            # Call agent (§blocker #2: raises on error)
            t0 = time.time()
            response = call_agent(
                prompt, agent=args.agent, model=args.model, timeout=args.timeout,
            )
            elapsed = time.time() - t0
            total_elapsed += elapsed

            if not response:
                raise RuntimeError("Empty response from agent")

            all_response_parts.append(response)

            # Parse structured output (§2.1)
            sections = parse_compilation(response)
            for section_key in all_sections:
                all_sections[section_key].extend(sections[section_key])

        if args.dry_run:
            results.append({
                "filename": filepath.name,
                "success": True,
                "response_chars": 0,
                "elapsed": 0,
            })
            continue

        # Combine chunks
        combined_response = "\n\n".join(all_response_parts)

        # Deduplicate SOPs/principles across chunk boundaries
        for key_name in all_sections:
            all_sections[key_name] = _deduplicate(all_sections[key_name], key_name)

        # Grounding check (§2.3) — anti-hallucination gate
        grounding_flagged = []
        if args.grounding_check and all_sections["principles"]:
            synonym_map = load_domain_synonyms(args.domain) if args.domain else None
            kept, flagged = grounding_check(
                all_sections["principles"], content,
                floor=args.grounding_floor, synonym_map=synonym_map,
            )
            if flagged:
                print(f"  Grounding: {len(flagged)} principles flagged "
                      f"(score < {args.grounding_floor}), {len(kept)} kept")
                for fp in flagged:
                    print(f"    DROPPED: {fp['statement'][:60]}  "
                          f"score={fp['_grounding_score']:.2f}  "
                          f"absent={fp['_absent_terms'][:5]}")
            all_sections["principles"] = kept
            grounding_flagged = flagged

        # Refutation chain (§2.7) — adversarial quality gate
        refutation_flagged = []
        if args.refutation_chain and all_sections["principles"]:
            try:
                from refutation_chain import enrich_principles as _enrich
                enriched, refutation_flagged = _enrich(
                    all_sections["principles"], content,
                    agent=args.agent, model=args.model, timeout=args.timeout,
                    overlap_threshold=args.refutation_overlap_threshold,
                    dry_run=args.dry_run,
                )
                if refutation_flagged:
                    print(f"  Refutation: {len(refutation_flagged)} principles flagged "
                          f"(overlap or validation issue)")
                all_sections["principles"] = enriched
                # Build refutation summary for output
                dissent_counts = {}
                for p in enriched:
                    ref = p.get("refutation")
                    if ref and not ref.get("_dry_run"):
                        dt = ref.get("dissent_type", "unknown")
                        dissent_counts[dt] = dissent_counts.get(dt, 0) + 1
                all_sections["refutation_summary"] = {
                    "total": len(enriched),
                    "enriched": sum(
                        1 for p in enriched
                        if p.get("refutation") and not p["refutation"].get("_dry_run")
                    ),
                    "flagged": len(refutation_flagged),
                    "dissent_types": dissent_counts,
                }
            except Exception as e:
                print(f"  WARN: Refutation chain failed: {e}")

        # Evidence Ledger (§2.8) — provenance per claim
        source_metadata = read_source_metadata(filepath)
        if all_sections["principles"]:
            try:
                from evidence_ledger import build_ledger
                ledger = build_ledger(
                    all_sections["principles"],
                    filepath=str(filepath),
                    source_hash=source_hash,
                    source_metadata=source_metadata,
                    original_text=original_text,
                )
                all_sections["evidence_ledger"] = ledger
                entry_count = ledger["metadata"]["total_entries"]
                print(f"  Evidence Ledger: {entry_count} entries")
            except Exception as e:
                print(f"  WARN: Evidence ledger failed: {e}")

        # Write output (§2.1 + §2.2) with collision-safe key
        write_compilation(
            filepath, prompt, combined_response, all_sections,
            output_dir, args.agent, args.model, source_hash, key,
            source_metadata=source_metadata,
        )

        # Semantic Field (§2.6) — build graph from compilation
        try:
            from semantic_field import build_semantic_field, validate_semantic_field
            from semantic_field import export_graphml as _export_graphml
            from semantic_field import export_jsonld as _export_jsonld
            from semantic_field import export_markdown as _export_markdown
            from semantic_field import export_html as _export_html
            from semantic_field import export_lightrag as _export_lightrag

            sf_data = {
                "source": filepath.name,
                "source_sha256": source_hash,
                "compiled_at": datetime.now(timezone.utc).isoformat(),
                "sops": all_sections["sops"],
                "principles": all_sections["principles"],
                "concepts": all_sections["concepts"],
                "references": all_sections["references"],
            }
            sf = build_semantic_field(sf_data, evidence_ledger=all_sections.get("evidence_ledger"))
            sf_errors = validate_semantic_field(sf)
            if sf_errors:
                print(f"  Semantic Field: {len(sf_errors)} validation errors")
                for err in sf_errors[:3]:
                    print(f"    WARN: {err}")

            sf_dir = output_dir / "compilation"
            sf_json = sf_dir / f"{key}.semantic_field.json"
            tmp_sf = sf_dir / f"{key}.semantic_field.json.tmp"
            with open(tmp_sf, "w", encoding="utf-8") as f:
                json.dump(sf, f, indent=2, ensure_ascii=False)
            tmp_sf.rename(sf_json)

            try:
                _export_graphml(sf, sf_dir / f"{key}.graphml")
            except RuntimeError:
                pass  # networkx not installed, skip GraphML

            _export_jsonld(sf, sf_dir / f"{key}.jsonld")
            _export_markdown(sf, sf_dir / f"{key}.semantic_field.md")
            _export_html(sf, sf_dir / f"{key}.semantic_field.html")
            _export_lightrag(sf, sf_dir / f"{key}.lightrag.json")
            print(f"  Semantic Field: {sf['metadata']['total_nodes']} nodes, {sf['metadata']['total_edges']} edges")
        except Exception as e:
            print(f"  Semantic Field: skipped ({e})")

        print(f"  OK: {len(combined_response):,} chars, "
              f"{len(all_sections['sops'])} SOPs, "
              f"{len(all_sections['principles'])} principles, "
              f"{total_elapsed:.1f}s")

        results.append({
            "filename": filepath.name,
            "success": True,
            "response_chars": len(combined_response),
            "sops_count": len(all_sections["sops"]),
            "principles_count": len(all_sections["principles"]),
            "concepts_count": len(all_sections["concepts"]),
            "grounding_flagged": len(grounding_flagged),
            "elapsed": total_elapsed,
        })

        # Review gate (§2.5) — inline, after each item, before next
        batch_idx = i - 1  # 0-based
        if batch_idx in sample_indices:
            decision = prompt_operator(
                batch_idx, len(sources), filepath.name, all_sections, content,
            )
            record_review(review_log, batch_idx, filepath.name, decision)
            if decision["verdict"] == "reject":
                if should_abort_batch(review_log, args.continue_on_reject):
                    print("\n  REJECTED — aborting remaining batch "
                          "(use --continue-on-reject to override)")
                    break
                else:
                    print("  REJECTED — continuing (--continue-on-reject)")

        # Rate limit between files
        if i < len(sources) and not args.dry_run:
            time.sleep(args.delay)

    # Record items that were not sampled (§2.5 provenance)
    if batch_mode and sample_indices:
        sampled_set = {r["index"] for r in review_log}
        for idx in range(len(sources)):
            if idx not in sampled_set:
                record_not_reviewed(review_log, idx, sources[idx].name)

    # Batch summary
    if skipped > 0:
        print(f"\n  Skipped {skipped} already-compiled files (cache hit)")
    if len(results) > 0:
        write_batch_summary(results, output_dir, review_log=review_log)

    # Final stats
    successful = sum(1 for r in results if r["success"])
    total_chars = sum(r.get("response_chars", 0) for r in results)
    total_time = sum(r.get("elapsed", 0) for r in results)
    total_flagged = sum(r.get("grounding_flagged", 0) for r in results)
    print(f"\n{'='*50}")
    print(f"Done: {successful}/{len(results)} compiled, {skipped} cached, "
          f"{total_chars:,} chars, {total_time:.1f}s")
    if total_flagged > 0:
        print(f"Grounding: {total_flagged} principles dropped (ungrounded)")


if __name__ == "__main__":
    main()
