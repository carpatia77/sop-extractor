#!/usr/bin/env python3
"""Run-report validator (Item 13.3).

Deterministic, no-LLM checker for `run_report.json` — the artifact SKILL.md's
convention asks an executor to write at the end of a run, listing every
numbered step (0-9, 7.5 when applicable) with `status: ran|skipped` and, for
any `skipped` step, a mandatory non-empty `reason`.

This does NOT judge whether a skip reason is *true* — verifying "was this
1.6GB claim real" against the actual source is out of scope for a mechanical
gate. It only enforces that a reason was recorded at all, which is what turns
a silent skip into something a human reviewer can catch.

Expected steps (matches SKILL.md's numbered workflow): 0, 1, "1.5", 2, "2.5",
3, 4, 5, "5.5", 6, 7, "7.5", 8, 9. Step "7.5" (frame rescue) is optional —
only required in the report if the source is a video course with a video path
provided (Step 7.5's own precondition); all other steps are always required.
"""

import argparse
import json
import os
import sys

ALWAYS_REQUIRED_STEPS = ["0", "1", "1.5", "2", "2.5", "3", "4", "5", "5.5", "6", "7", "8", "9"]
OPTIONAL_STEPS = ["7.5"]
VALID_STATUSES = ("ran", "skipped")


def load_run_report(path: str):
    if not os.path.isfile(path):
        return None, f"run_report.json not found at {path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return None, f"run_report.json is not valid JSON: {e}"
    return data, None


def check_run_report(data: dict):
    """Returns (ok: bool, errors: list[str])."""
    errors = []
    if not isinstance(data, dict) or "steps" not in data:
        return False, ["run_report.json must be an object with a top-level 'steps' field"]

    steps = data["steps"]
    if not isinstance(steps, dict):
        return False, ["'steps' must be an object keyed by step number (e.g. \"0\", \"1.5\")"]

    for step_id in ALWAYS_REQUIRED_STEPS:
        if step_id not in steps:
            errors.append(f"missing required step '{step_id}' — every run must record it")
            continue
        errors.extend(_check_step_entry(step_id, steps[step_id]))

    for step_id in OPTIONAL_STEPS:
        if step_id in steps:
            errors.extend(_check_step_entry(step_id, steps[step_id]))

    return (len(errors) == 0), errors


def _check_step_entry(step_id: str, entry) -> list:
    errors = []
    if not isinstance(entry, dict) or "status" not in entry:
        return [f"step '{step_id}': entry must be an object with a 'status' field"]

    status = entry["status"]
    if status not in VALID_STATUSES:
        errors.append(f"step '{step_id}': status must be one of {VALID_STATUSES}, got {status!r}")
        return errors

    if status == "skipped":
        reason = entry.get("reason", "")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"step '{step_id}': skipped with no (or empty) 'reason' recorded — "
                          "a skip must always carry a stated reason for human review")
    return errors


def run_validation(skill_dir: str) -> int:
    path = os.path.join(skill_dir, "run_report.json")
    data, load_error = load_run_report(path)
    if load_error:
        print(f"⚠️  {load_error}")
        return 1

    ok, errors = check_run_report(data)
    print(f"=== Run Report Check: {path} ===")
    if ok:
        n_skipped = sum(1 for s in data["steps"].values() if isinstance(s, dict) and s.get("status") == "skipped")
        print(f"✅ All recorded steps are complete; {n_skipped} step(s) skipped, each with a reason.")
        return 0

    print("❌ Run report incomplete or malformed:")
    for e in errors:
        print(f"  - {e}")
    return 1


def main():
    parser = argparse.ArgumentParser(description="Validate a skill's run_report.json (Item 13.3).")
    parser.add_argument("skill_dir", help="Path to the skill directory containing run_report.json")
    args = parser.parse_args()
    sys.exit(run_validation(args.skill_dir))


if __name__ == "__main__":
    main()
