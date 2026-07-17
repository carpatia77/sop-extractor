#!/usr/bin/env python3
"""Merges N per-source Blackhat Mode architecture artifacts into one
consolidated `<system>_architecture.md` (Item 14.1).

Why this exists: processing a multi-part course one part at a time (Item 11's
own recommended flow when the operator declines to fold-in at extraction time)
produces one `<system>_architecture.md` per part, each with its own O1/I1
numbering starting from scratch. Getting a single coherent picture then meant
manually renumbering O/I ids across files, re-pointing INFERRED citations at
the new ids, and re-validating the four gates — real, repeatable, mechanical
labor with no domain judgment in it. This script automates exactly that
mechanical part.

What it does NOT do: it does not invent new cross-source inferences (spotting
that vid1's histogram and vid2's CVD hypothesis are the same mechanism is a
human/agent synthesis step, same as producing the artifact in the first
place) — it only concatenates and renumbers what each source already
concluded, then re-runs the same four gates
(scripts/validate_architecture_audit.py) on the result so the merge itself
can't silently produce an invalid artifact.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_architecture_audit import (  # noqa: E402
    split_front_matter,
    check_seal_gate,
    check_grounding_gate,
    check_intent_gate,
    OBSERVED_RE,
    INFERRED_RE,
    OBS_ID_RE,
)

SECTION_RE = re.compile(r'^##\s+(.+?)\s*$')

CANONICAL_OBSERVATIONS = "frontend observations"
CANONICAL_INFERENCES = "inferred backend"


def split_into_sections(body: str):
    """Splits a body into an ordered list of (heading, [lines]) by level-2
    (`## `) headings. Content before the first heading is dropped (title/
    intro prose, not claim data)."""
    sections = []
    current_heading = None
    current_lines = []
    for line in body.splitlines():
        m = SECTION_RE.match(line)
        if m:
            if current_heading is not None:
                sections.append((current_heading, current_lines))
            current_heading = m.group(1).strip()
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)
    if current_heading is not None:
        sections.append((current_heading, current_lines))
    return sections


def _build_id_map(body: str, seal_re, prefix: str, start: int):
    """Scans body for seal ids (in document order, first-occurrence-wins),
    assigning new sequential ids starting at `start`. Returns (id_map, next_start)."""
    id_map = {}
    counter = start
    for m in seal_re.finditer(body):
        old_id = m.group(1)
        if old_id not in id_map:
            id_map[old_id] = f"{prefix}{counter}"
            counter += 1
    return id_map, counter


def _rewrite_line(line: str, o_map: dict, i_map: dict) -> str:
    """Rewrites a single line's seal id(s) — and, for INFERRED, its cited
    OBSERVED ids — using the per-source id maps."""

    def obs_sub(m):
        new_id = o_map.get(m.group(1), m.group(1))
        return f"[OBSERVED {new_id} {m.group(2)}]"

    def inf_sub(m):
        new_id = i_map.get(m.group(1), m.group(1))
        new_payload = OBS_ID_RE.sub(lambda mm: o_map.get(mm.group(0), mm.group(0)), m.group(2))
        return f"[INFERRED {new_id} ← {new_payload}]"

    line = OBSERVED_RE.sub(obs_sub, line)
    line = INFERRED_RE.sub(inf_sub, line)
    return line


def merge_front_matter(front_matters: list, approved_by_override: str = None) -> dict:
    """Merges N front-matter dicts. intent must be reverse-engineering on all
    (or the merge is refusing to produce an unauthorised artifact); system and
    analyst_lens are kept from the first source, with any differing values
    from later sources recorded (not silently dropped) so a human notices."""
    merged = dict(front_matters[0]) if front_matters else {}

    intents = {fm.get("intent", "") for fm in front_matters}
    if intents - {"reverse-engineering"}:
        merged["intent"] = "reverse-engineering"  # Intent Gate re-checks this; mismatches surface as a gate failure if truly missing

    approvers = [fm.get("approved_by", "") for fm in front_matters if fm.get("approved_by")]
    merged["approved_by"] = approved_by_override or "; ".join(dict.fromkeys(approvers))

    lenses = [fm.get("analyst_lens", "") for fm in front_matters if fm.get("analyst_lens")]
    unique_lenses = list(dict.fromkeys(lenses))
    merged["analyst_lens"] = unique_lenses[0] if unique_lenses else ""
    if len(unique_lenses) > 1:
        merged["analyst_lens_variants"] = "; ".join(unique_lenses[1:])

    systems = [fm.get("system", "") for fm in front_matters if fm.get("system")]
    unique_systems = list(dict.fromkeys(systems))
    merged["system"] = unique_systems[0] if unique_systems else ""
    if len(unique_systems) > 1:
        merged["system_variants"] = "; ".join(unique_systems[1:])

    return merged


def merge_architecture_files(paths: list, approved_by: str = None):
    """Merges N architecture artifacts into one (front_matter, body_text)
    pair, with continuous O/I numbering. Does not write to disk — see
    write_merged_architecture for the CLI entrypoint."""
    front_matters = []
    obs_lines = []
    inf_lines = []
    other_sections = []  # (source_label, heading, lines)

    o_next = 1
    i_next = 1

    for path in paths:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        front, body = split_front_matter(text)
        front_matters.append(front)

        o_map, o_next = _build_id_map(body, OBSERVED_RE, "O", o_next)
        i_map, i_next = _build_id_map(body, INFERRED_RE, "I", i_next)

        source_label = os.path.basename(path)
        for heading, lines in split_into_sections(body):
            rewritten = [_rewrite_line(line, o_map, i_map) for line in lines]
            norm = heading.strip().lower()
            if norm == CANONICAL_OBSERVATIONS:
                obs_lines.extend(rewritten)
            elif norm == CANONICAL_INFERENCES:
                inf_lines.extend(rewritten)
            else:
                other_sections.append((source_label, heading, rewritten))

    merged_front = merge_front_matter(front_matters, approved_by_override=approved_by)

    out_lines = ["---"]
    for key, val in merged_front.items():
        out_lines.append(f"{key}: {val}")
    out_lines.append("---")
    out_lines.append("")
    out_lines.append(f"## {CANONICAL_OBSERVATIONS.title()}")
    out_lines.append("")
    out_lines.extend(obs_lines)
    out_lines.append("")
    out_lines.append(f"## {CANONICAL_INFERENCES.title()}")
    out_lines.append("")
    out_lines.extend(inf_lines)

    if other_sections:
        out_lines.append("")
        out_lines.append("## Per-source notes")
        out_lines.append("")
        for source_label, heading, lines in other_sections:
            out_lines.append(f"### {heading} ({source_label})")
            out_lines.append("")
            out_lines.extend(lines)
            out_lines.append("")

    merged_text = "\n".join(out_lines) + "\n"
    return merged_front, merged_text


def write_merged_architecture(paths: list, out_path: str, approved_by: str = None) -> int:
    """Merges the given architecture files, writes the result to out_path, and
    re-validates it with the same three content gates
    validate_architecture_audit.py runs (Non-Contamination needs a skill dir
    and is out of scope for a merge that doesn't know one). Returns 0 if the
    merged artifact passes, 1 otherwise — mirroring run_validation's contract."""
    merged_front, merged_text = merge_architecture_files(paths, approved_by=approved_by)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(merged_text)

    _, body = split_front_matter(merged_text)
    intent_ok, intent_errors = check_intent_gate(merged_front)
    seal_ok, seal_errors = check_seal_gate(body)
    grounding_ok, grounding_errors = check_grounding_gate(body)

    print(f"=== Merged {len(paths)} source(s) -> {out_path} ===")

    def report(name, ok, errors):
        print(f"  {'✓' if ok else '✗'} {name}: {'PASS' if ok else 'FAIL'}")
        for e in errors:
            print(f"      - {e}")

    report("Intent Gate", intent_ok, intent_errors)
    report("Seal Gate", seal_ok, seal_errors)
    report("Grounding Gate", grounding_ok, grounding_errors)

    if merged_front.get("analyst_lens_variants"):
        print(f"\n⚠️  Sources disagreed on analyst_lens; kept {merged_front['analyst_lens']!r}, "
              f"others were: {merged_front['analyst_lens_variants']}")
    if merged_front.get("system_variants"):
        print(f"⚠️  Sources disagreed on system name; kept {merged_front['system']!r}, "
              f"others were: {merged_front['system_variants']}")

    passed = intent_ok and seal_ok and grounding_ok
    print(f"\n{'ALL GATES PASSED' if passed else 'MERGE PRODUCED AN INVALID ARTIFACT — fix inputs and re-merge'}.")
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(
        description="Merge N per-source Blackhat Mode architecture artifacts into one, "
                    "with continuous O/I numbering (Item 14.1).")
    parser.add_argument("architecture_paths", nargs="+",
                        help="Two or more <system>_architecture.md files, in source order")
    parser.add_argument("--out", required=True, help="Output path for the merged artifact")
    parser.add_argument("--approved-by", default=None,
                        help="Override the merged front matter's approved_by (default: union of all sources')")
    args = parser.parse_args()

    if len(args.architecture_paths) < 2:
        print("Error: provide at least two architecture files to merge.", file=sys.stderr)
        sys.exit(1)
    for p in args.architecture_paths:
        if not os.path.isfile(p):
            print(f"Error: file not found: {p}", file=sys.stderr)
            sys.exit(1)

    sys.exit(write_merged_architecture(args.architecture_paths, args.out, approved_by=args.approved_by))


if __name__ == "__main__":
    main()
