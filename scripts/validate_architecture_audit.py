#!/usr/bin/env python3
"""Architecture Reverse-Engineering Audit validator ("Blackhat Mode", Item 11).

Deterministic, no-LLM validator for a `<system>_architecture.md` artifact — the
optional reverse-engineering layer that reconstructs a hypothesis of a
demonstrated system's backend from its observable frontend. This script does
NOT produce the artifact (that is an isolated human+agent pass, like the
coherence audit); it only *validates* one, keeping the speculative inference
walled off from the anti-fabrication extraction core.

The artifact grammar it enforces
--------------------------------
1. YAML-style front matter between `---` fences, recording who authorised the
   inference and under which analytical lens:

       ---
       intent: reverse-engineering
       approved_by: <operator>
       analyst_lens: <slug>
       system: <name>
       ---

2. A body of bulleted claim lines (`- ` / `* `). Every claim line carries
   exactly one seal:

       - [OBSERVED O1 src2/12:34] The dashboard shows a volume-profile chart.
       - [INFERRED I1 ← O1, O3] The backend maintains a running TPO histogram.

   - `[OBSERVED <Oid> <source_ref>]` — a fact the author showed/stated,
     traceable to a source location.
   - `[INFERRED <Iid> ← <Oid>[, <Oid>...]]` — a hypothesis about internal
     mechanism, which must cite the observed evidence it rests on.

Four gates (mirroring validate_evolution_audit's structure)
-----------------------------------------------------------
- Seal Gate           — every claim line has exactly one seal.
- Grounding Gate      — every INFERRED cites ≥1 OBSERVED id that exists in the
                        artifact. Persona-blind: an expert lens never exempts a
                        line from needing observed evidence.
- Non-Contamination   — SKILL.md / first_principles.md / sops.md must contain
                        no [INFERRED …] seal (inference never leaks into the
                        faithful core). Skipped only if the skill dir is absent.
- Intent Gate         — front matter records intent=reverse-engineering, a
                        non-empty approved_by, and a non-empty analyst_lens.
"""

import argparse
import os
import re
import sys

CLAIM_LINE_RE = re.compile(r'^\s*[-*]\s+\S')
OBSERVED_RE = re.compile(r'\[OBSERVED\s+(O\d+)\s+([^\]]+?)\]')
INFERRED_RE = re.compile(r'\[INFERRED\s+(I\d+)\s*(?:←|<-)\s*([^\]]+?)\]')
OBS_ID_RE = re.compile(r'O\d+')
CONTAMINATION_RE = re.compile(r'\[INFERRED\b')

CORE_FILES = ("SKILL.md", "first_principles.md", "sops.md")


def split_front_matter(text: str):
    """Returns (front_matter_dict, body_text). If no `---`-fenced front matter
    is present at the top, returns ({}, original_text)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    fm = {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    for line in lines[1:end]:
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    body = "\n".join(lines[end + 1:])
    return fm, body


def find_claim_lines(body: str) -> list:
    """Claim lines are bulleted list items (`- `/`* `). Headings, blank lines,
    prose, and table rows are not claims and are exempt from the Seal Gate."""
    out = []
    for n, line in enumerate(body.splitlines(), 1):
        if CLAIM_LINE_RE.match(line):
            out.append((n, line))
    return out


def seals_on_line(line: str) -> list:
    """All seals on a line, as (kind, id, payload) tuples."""
    seals = []
    for m in OBSERVED_RE.finditer(line):
        seals.append(("OBSERVED", m.group(1), m.group(2).strip()))
    for m in INFERRED_RE.finditer(line):
        seals.append(("INFERRED", m.group(1), m.group(2).strip()))
    return seals


def check_seal_gate(body: str):
    """Every claim line must carry exactly one seal."""
    errors = []
    for n, line in find_claim_lines(body):
        seals = seals_on_line(line)
        if len(seals) == 0:
            errors.append(f"line {n}: claim line has no [OBSERVED …]/[INFERRED …] seal: {line.strip()}")
        elif len(seals) > 1:
            errors.append(f"line {n}: claim line has {len(seals)} seals (expected exactly one): {line.strip()}")
    return (len(errors) == 0), errors


def collect_observed_ids(body: str) -> set:
    return {m.group(1) for m in OBSERVED_RE.finditer(body)}


def check_grounding_gate(body: str):
    """Every INFERRED must cite ≥1 OBSERVED id that exists in the artifact."""
    errors = []
    observed = collect_observed_ids(body)
    for n, line in enumerate(body.splitlines(), 1):
        for m in INFERRED_RE.finditer(line):
            iid, payload = m.group(1), m.group(2)
            refs = OBS_ID_RE.findall(payload)
            if not refs:
                errors.append(f"line {n}: {iid} is an inference with no cited OBSERVED evidence "
                              f"(expected '[INFERRED {iid} ← O#, …]'): {line.strip()}")
                continue
            missing = [r for r in refs if r not in observed]
            if missing:
                errors.append(f"line {n}: {iid} cites OBSERVED id(s) {missing} that are not "
                              f"defined anywhere in the artifact: {line.strip()}")
    return (len(errors) == 0), errors


def check_intent_gate(front: dict):
    """Front matter must record the authorisation and the analytical POV."""
    errors = []
    if front.get("intent", "").lower() != "reverse-engineering":
        errors.append("front matter: 'intent' must be 'reverse-engineering' "
                      f"(got {front.get('intent')!r}) — the artifact cannot exist without a recorded intent.")
    if not front.get("approved_by"):
        errors.append("front matter: 'approved_by' is missing/empty — a human must own the authorisation to infer.")
    if not front.get("analyst_lens"):
        errors.append("front matter: 'analyst_lens' is missing/empty — the analytical POV that produced "
                      "the inferences must be recorded (auditable which expertise lens was used).")
    return (len(errors) == 0), errors


def check_non_contamination_gate(skill_dir: str):
    """The faithful core must contain no [INFERRED …] seal. Returns
    (ok, errors, skipped)."""
    if not skill_dir or not os.path.isdir(skill_dir):
        return True, [], True
    errors = []
    checked_any = False
    for name in CORE_FILES:
        path = os.path.join(skill_dir, name)
        if not os.path.isfile(path):
            continue
        checked_any = True
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for n, line in enumerate(f, 1):
                if CONTAMINATION_RE.search(line):
                    errors.append(f"{name} line {n}: an [INFERRED …] seal leaked into the faithful core — "
                                  "inference must live only in the architecture artifact.")
    return (len(errors) == 0), errors, (not checked_any)


def run_validation(arch_path: str, skill_dir: str = None) -> int:
    if not os.path.isfile(arch_path):
        print(f"Error: architecture artifact not found: {arch_path}")
        return 1

    with open(arch_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    front, body = split_front_matter(text)

    intent_ok, intent_errors = check_intent_gate(front)
    seal_ok, seal_errors = check_seal_gate(body)
    grounding_ok, grounding_errors = check_grounding_gate(body)
    contam_ok, contam_errors, contam_skipped = check_non_contamination_gate(skill_dir)

    def report(name, ok, errors, skipped=False):
        if skipped:
            print(f"  ~ {name}: SKIPPED (no skill dir given, or no core files found to check)")
            return
        print(f"  {'✓' if ok else '✗'} {name}: {'PASS' if ok else 'FAIL'}")
        for e in errors:
            print(f"      - {e}")

    print(f"=== Architecture Reverse-Engineering Audit: {os.path.basename(arch_path)} ===")
    report("Intent Gate", intent_ok, intent_errors)
    report("Seal Gate", seal_ok, seal_errors)
    report("Grounding Gate", grounding_ok, grounding_errors)
    report("Non-Contamination Gate", contam_ok, contam_errors, skipped=contam_skipped)

    passed = intent_ok and seal_ok and grounding_ok and contam_ok
    n_obs = len(collect_observed_ids(body))
    n_inf = len(set(INFERRED_RE.findall(body)))
    print(f"\n{n_obs} observed claim(s), {n_inf} inferred claim(s). "
          f"{'ALL GATES PASSED' if passed else 'AUDIT FAILED'}.")
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(
        description="Validate a <system>_architecture.md reverse-engineering audit artifact (Item 11).")
    parser.add_argument("architecture_path", help="Path to the <system>_architecture.md artifact")
    parser.add_argument("--skill-dir", default=None,
                        help="Path to the extracted skill folder, used to enforce the Non-Contamination "
                             "Gate against SKILL.md / first_principles.md / sops.md")
    args = parser.parse_args()
    sys.exit(run_validation(args.architecture_path, skill_dir=args.skill_dir))


if __name__ == "__main__":
    main()
