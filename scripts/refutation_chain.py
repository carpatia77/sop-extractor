#!/usr/bin/env python3
"""Refutation Chain — adversarial quality gate for extracted principles.

For every claim/principle extracted by the LLM, this module generates:
  1. strongest_alternative — the best counter-argument or alternative interpretation
  2. disconfirming_evidence — what would falsify the claim
  3. dissent_type — qualifies | contradicts | context_limited

Then validates that the alternative genuinely OPPOSES the original claim
(risk: "refutation confirma em vez de contrapor").

Usage:
    python scripts/refutation_chain.py compilation.json           # single file
    python scripts/refutation_chain.py compilation/ --batch       # all JSON files
    python scripts/refutation_chain.py compilation.json --dry-run # prompt preview
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Imports — reuse existing modules
# ---------------------------------------------------------------------------

try:
    from scripts.verify_concept_presence import salient_terms
except ImportError:
    from verify_concept_presence import salient_terms

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_DISSENT_TYPES = {"qualifies", "contradicts", "context_limited"}

NEGATION_WORDS = frozenset({
    "not", "never", "unless", "except", "only", "depends", "generally",
    "usually", "sometimes", "often", "rarely", "however", "although",
    "despite", "regardless", "nevertheless", "whereas", "if",
})

DEFAULT_OVERLAP_THRESHOLD = 0.7
DEFAULT_AGENT = "claude"
DEFAULT_TIMEOUT = 300
DEFAULT_DELAY = 2.0

AGENT_COMMANDS = {
    "claude": ["claude", "-p", "--allowedTools", "Read"],
    "copilot": ["copilot", "ask", "--stdio"],
    "amp": ["amp", "-p"],
}

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

REFUTATION_PROMPT = """\
You are a critical reviewer. For the following claim extracted from source material,
generate the STRONGEST counter-argument or alternative interpretation.

CLAIM: {claim}
EVIDENCE FROM SOURCE: {evidence}

Respond in this EXACT format (no extra text):

- **Strongest Alternative**: <best counter-argument or qualifying condition — one sentence>
- **Disconfirming Evidence**: <what would need to be true for the original claim to be wrong — one sentence>
- **Dissent Type**: qualifies | contradicts | context_limited

RULES:
1. The alternative MUST genuinely oppose or narrow the original claim
2. Do NOT simply rephrase or agree with the claim
3. Be specific — name the exact condition under which the claim fails
4. Keep it concise — one sentence each for alternative and disconfirming evidence

SOURCE EXCERPT (for context):
{source_excerpt}
"""

# ---------------------------------------------------------------------------
# Semantic overlap (deterministic validation)
# ---------------------------------------------------------------------------


def _semantic_overlap(claim: str, alternative: str) -> float:
    """Jaccard similarity of salient terms between claim and alternative."""
    t_claim = set(salient_terms(claim))
    t_alt = set(salient_terms(alternative))
    if not t_claim or not t_alt:
        return 0.0
    return len(t_claim & t_alt) / len(t_claim | t_alt)


def _is_genuine_dissent(
    claim: str, alternative: str, threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> tuple[bool, str]:
    """Check if alternative genuinely opposes the claim.

    Returns (is_valid, reason).
    """
    overlap = _semantic_overlap(claim, alternative)

    alt_lower = alternative.lower()
    has_negation = any(w in alt_lower for w in NEGATION_WORDS)

    # High overlap + negation = genuine dissent (same words, opposite meaning)
    if overlap > threshold and has_negation:
        return True, "OK"

    if overlap > threshold:
        return (
            False,
            f"Overlap {overlap:.2f} > {threshold} — alternative may be confirming",
        )

    if overlap < 0.1 and not has_negation:
        return (
            False,
            f"Overlap {overlap:.2f} too low and no negation — possible unrelated text",
        )

    return True, "OK"


# ---------------------------------------------------------------------------
# Agent call (subprocess)
# ---------------------------------------------------------------------------


def call_agent(
    prompt: str,
    agent: str = DEFAULT_AGENT,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Call agent CLI via subprocess. Raises RuntimeError on failure."""
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
            f"Install: npm install -g @anthropic-ai/claude-code"
        )


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------


def build_refutation_prompt(
    claim: str,
    evidence: str,
    source_content: str,
    max_source_excerpt: int = 2000,
) -> str:
    """Build a refutation prompt for a single principle."""
    source_excerpt = source_content[:max_source_excerpt]
    if len(source_content) > max_source_excerpt:
        source_excerpt += f"\n... ({len(source_content) - max_source_excerpt} chars truncated)"
    return REFUTATION_PROMPT.format(
        claim=claim,
        evidence=evidence or "(no evidence provided)",
        source_excerpt=source_excerpt,
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def parse_refutation_response(text: str) -> dict | None:
    """Parse agent response into structured refutation dict.

    Returns None if parsing fails.
    """
    result = {}

    # Extract Strongest Alternative
    alt_match = re.search(
        r"\*{0,2}Strongest Alternative\*{0,2}\s*:\s*(.+?)(?=\n-|\n\*{0,2}Dis|\Z)",
        text, re.DOTALL,
    )
    result["strongest_alternative"] = alt_match.group(1).strip() if alt_match else ""

    # Extract Disconfirming Evidence
    dis_match = re.search(
        r"\*{0,2}Disconfirming Evidence\*{0,2}\s*:\s*(.+?)(?=\n-|\n\*{0,2}Dissent|\Z)",
        text, re.DOTALL,
    )
    result["disconfirming_evidence"] = dis_match.group(1).strip() if dis_match else ""

    # Extract Dissent Type
    dissent_match = re.search(
        r"\*{0,2}Dissent Type\*{0,2}\s*:\s*(\w+)",
        text,
    )
    dissent_type = dissent_match.group(1).strip().lower() if dissent_match else ""
    result["dissent_type"] = dissent_type if dissent_type in VALID_DISSENT_TYPES else ""

    # Metadata
    result["generated_at"] = datetime.now(timezone.utc).isoformat()

    # Require at least the alternative
    if not result["strongest_alternative"]:
        return None

    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_refutation(
    claim: str,
    refutation: dict,
    threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> tuple[bool, str]:
    """Validate a refutation entry deterministically.

    Returns (is_valid, reason).
    """
    alternative = refutation.get("strongest_alternative", "")
    if not alternative:
        return False, "No strongest_alternative provided"

    dissent_type = refutation.get("dissent_type", "")
    if dissent_type and dissent_type not in VALID_DISSENT_TYPES:
        return False, f"Invalid dissent_type '{dissent_type}'"

    return _is_genuine_dissent(claim, alternative, threshold)


# ---------------------------------------------------------------------------
# Enrich principles
# ---------------------------------------------------------------------------


def enrich_principles(
    principles: list[dict],
    source_content: str,
    agent: str = DEFAULT_AGENT,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
    dry_run: bool = False,
    delay: float = DEFAULT_DELAY,
) -> tuple[list[dict], list[dict]]:
    """Add refutation chains to each principle.

    Returns (enriched_principles, flagged_principles).
    """
    enriched = []
    flagged = []

    for i, p in enumerate(principles):
        statement = p.get("statement", "")
        evidence = p.get("evidence", "")

        if not statement:
            p["refutation"] = None
            enriched.append(p)
            continue

        # Build prompt
        prompt = build_refutation_prompt(statement, evidence, source_content)

        if dry_run:
            print(f"  [DRY RUN] Refutation prompt for: {statement[:60]}...")
            p["refutation"] = {"_dry_run": True, "_prompt": prompt}
            enriched.append(p)
            continue

        # Call agent
        try:
            response = call_agent(prompt, agent=agent, model=model, timeout=timeout)
        except RuntimeError as e:
            print(f"  WARN: Refutation agent error: {e}")
            p["refutation"] = None
            enriched.append(p)
            continue

        if not response:
            print(f"  WARN: Empty refutation response for: {statement[:40]}...")
            p["refutation"] = None
            enriched.append(p)
            continue

        # Parse response
        refutation = parse_refutation_response(response)
        if refutation is None:
            print(f"  WARN: Failed to parse refutation for: {statement[:40]}...")
            p["refutation"] = None
            enriched.append(p)
            continue

        refutation["model"] = model or "default"

        # Validate
        is_valid, reason = validate_refutation(statement, refutation, overlap_threshold)
        refutation["_valid"] = is_valid
        refutation["_validation_reason"] = reason

        if not is_valid:
            print(f"  WARN: Refutation flagged: {reason} — {statement[:40]}...")
            flagged.append({"statement": statement, "reason": reason})

        p["refutation"] = refutation
        enriched.append(p)

        # Delay between calls
        if i < len(principles) - 1:
            time.sleep(delay)

    return enriched, flagged


# ---------------------------------------------------------------------------
# Run refutation chain on compilation
# ---------------------------------------------------------------------------


def run_refutation_chain(
    compilation: dict,
    source_content: str,
    agent: str = DEFAULT_AGENT,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
    dry_run: bool = False,
    delay: float = DEFAULT_DELAY,
) -> dict:
    """Enrich a compilation dict with refutation chains for all principles.

    Returns the enriched compilation with refutation_summary added.
    """
    principles = compilation.get("principles", [])
    if not principles:
        compilation["refutation_summary"] = {
            "total": 0, "enriched": 0, "flagged": 0, "dissent_types": {},
        }
        return compilation

    print(f"  Refutation chain: {len(principles)} principles")
    enriched, flagged = enrich_principles(
        principles, source_content,
        agent=agent, model=model, timeout=timeout,
        overlap_threshold=overlap_threshold,
        dry_run=dry_run, delay=delay,
    )

    # Build summary
    dissent_counts: dict[str, int] = {}
    for p in enriched:
        ref = p.get("refutation")
        if ref and not ref.get("_dry_run"):
            dt = ref.get("dissent_type", "unknown")
            dissent_counts[dt] = dissent_counts.get(dt, 0) + 1

    compilation["principles"] = enriched
    compilation["refutation_summary"] = {
        "total": len(principles),
        "enriched": sum(
            1 for p in enriched
            if p.get("refutation") and not p["refutation"].get("_dry_run")
        ),
        "flagged": len(flagged),
        "dissent_types": dissent_counts,
    }

    return compilation


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Refutation Chain — adversarial quality gate for extracted principles.",
    )
    parser.add_argument(
        "path", help="Compilation JSON file or directory (with --batch)",
    )
    parser.add_argument(
        "--batch", action="store_true",
        help="Process all .json files in directory",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show prompts without calling agent",
    )
    parser.add_argument(
        "--agent", default=DEFAULT_AGENT, choices=list(AGENT_COMMANDS),
        help=f"Agent CLI to use (default: {DEFAULT_AGENT})",
    )
    parser.add_argument(
        "--model", default=None,
        help="Model to use for agent calls",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help=f"Agent timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY,
        help=f"Delay between agent calls (default: {DEFAULT_DELAY}s)",
    )
    parser.add_argument(
        "--overlap-threshold", type=float, default=DEFAULT_OVERLAP_THRESHOLD,
        help=f"Max semantic overlap for valid dissent (default: {DEFAULT_OVERLAP_THRESHOLD})",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output directory (default: same as input)",
    )

    args = parser.parse_args()
    input_path = Path(args.path)

    if not input_path.exists():
        print(f"Error: path not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Discover files
    if args.batch or input_path.is_dir():
        json_files = sorted(input_path.glob("*.json"))
        if not json_files:
            print(f"No .json files found in {input_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(json_files)} compilation files")
    else:
        json_files = [input_path]

    output_dir = Path(args.output) if args.output else input_path

    for i, json_path in enumerate(json_files, 1):
        print(f"\n[{i}/{len(json_files)}] {json_path.name}")

        # Read compilation
        try:
            with open(json_path, encoding="utf-8") as f:
                compilation = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  Error reading {json_path.name}: {e}", file=sys.stderr)
            continue

        # Read source content (for LLM context)
        source_path = compilation.get("source_path", "")
        source_content = ""
        if source_path and os.path.exists(source_path):
            try:
                source_content = Path(source_path).read_text(encoding="utf-8")
            except OSError:
                pass

        # Run refutation chain
        compilation = run_refutation_chain(
            compilation, source_content,
            agent=args.agent, model=args.model, timeout=args.timeout,
            overlap_threshold=args.overlap_threshold,
            dry_run=args.dry_run, delay=args.delay,
        )

        # Write enriched compilation
        if not args.dry_run:
            out_path = output_dir / json_path.name
            tmp_path = output_dir / f"{json_path.name}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(compilation, f, indent=2, ensure_ascii=False)
            tmp_path.rename(out_path)
            print(f"  Written: {out_path.name}")

        summary = compilation.get("refutation_summary", {})
        print(
            f"  Summary: {summary.get('enriched', 0)}/{summary.get('total', 0)} enriched, "
            f"{summary.get('flagged', 0)} flagged | "
            f"types: {summary.get('dissent_types', {})}"
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
