#!/usr/bin/env python3
"""Unified CLI dispatcher (Item 12 / Item 13.1): `sopx`.

A thin dispatcher over the scripts that already exist in this folder — it
contains no new domain logic. Each capability shells out to the same script
a user would invoke by hand (`python scripts/<file>.py <args>`), so headless
use (`python scripts/menu.py scan path.pdf`) is byte-identical to typing the
underlying command directly.

After `pip install -e .`, this is also available as the `sopx` console
command from anywhere (`sopx scan path.pdf --emit-prompt`) — `scripts/` is
packaged into the wheel alongside `book_to_skill`, and `sopx` is a
`[project.scripts]` entry point pointing at `scripts.menu:main`. Running it
as `python scripts/menu.py` from a checkout still works identically; both
paths dispatch to the exact same sibling scripts.
"""

import os
import shutil
import subprocess
import sys
from collections import namedtuple

Capability = namedtuple(
    "Capability",
    ["key", "verb", "label", "script", "arg_hint", "coming_soon", "info_only", "info_text"],
)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Item 12's menu map, flattened
CAPABILITIES = [
    Capability("1", "scan", "Scan a source (pre-flight)", "preflight_scan.py",
               "<path> [--emit-prompt]", False, False, None),
    Capability("2", "extract", "Extract a skill (hand-off to your agent)", None,
               None, False, True,
               "Extraction itself runs SKILL.md Steps 0-9 via your agent (Copilot CLI / "
               "Claude / Amp), not this menu — the menu never pretends to run the LLM pass. "
               "Use option 1 first to get an approved prompt, then hand it to your agent."),
    Capability("3", "validate", "Validate a skill (all checks)", "validate_all.py",
               "<skill_dir>", False, False, None),
    Capability("4", "coherence", "Coherence audit (single source)", "validate_coherence_audit.py",
               "<audit_file> --dir <skill_dir>", False, False, None),
    Capability("5", "evolution", "Evolution audit (a Set)", "validate_evolution_audit.py",
               "--dir <set_dir>", False, False, None),
    Capability("6", "blackhat", "Blackhat / reverse-engineering audit", "validate_architecture_audit.py",
               "<architecture.md> [--skill-dir <dir>]", False, False, None),
    Capability("7", "merge-arch", "Merge multi-part Blackhat architecture docs", "merge_architecture_audit.py",
               "<part1_architecture.md> <part2_architecture.md> ... --out <merged.md>", False, False, None),
    Capability("8", "determinism", "Determinism score", "determinism_score.py",
               "<skill_dir>", False, False, None),
    Capability("9", "view", "View a skill (renders one HTML page)", "render_skill_viewer.py",
               "<skill_dir> [--out <path>]", False, False, None),
    Capability("10", "summary", "Summary / run log", "extraction_summary.py",
               "<path>", False, False, None),
    Capability("11", "ingest", "Ingest video/URL → transcript + text", "ingest.py",
               "<URL_or_path> [--rescue-frames] [--model base]", False, False, None),
]


def find_capability(key_or_verb: str, capabilities=None):
    """Looks up a capability by its menu key ('1') or verb ('scan')."""
    capabilities = capabilities if capabilities is not None else CAPABILITIES
    for cap in capabilities:
        if key_or_verb == cap.key or key_or_verb == cap.verb:
            return cap
    return None


def is_available(cap: Capability, scripts_dir: str = SCRIPTS_DIR):
    """Returns (available: bool, reason: str). Checks:
    - coming_soon flag
    - backing script existence
    - required binaries for ingest capability"""
    if cap.coming_soon:
        return False, "coming soon — not yet implemented"
    if cap.info_only:
        return True, ""
    script_path = os.path.join(scripts_dir, cap.script)
    if not os.path.isfile(script_path):
        return False, f"backing script not found: {cap.script}"
    # Check binaries for ingest capability
    if cap.verb == "ingest":
        for binary in ["yt-dlp", "ffmpeg"]:
            if not shutil.which(binary):
                return False, f"{binary} não encontrado"
    return True, ""


def build_command(cap: Capability, args: list, scripts_dir: str = SCRIPTS_DIR,
                   python_bin: str = None) -> list:
    """Pure function: builds the exact subprocess command line."""
    python_bin = python_bin or sys.executable or "python3"
    script_path = os.path.join(scripts_dir, cap.script)
    return [python_bin, script_path] + list(args)


def format_menu(capabilities=None, scripts_dir: str = SCRIPTS_DIR) -> str:
    """Renders the interactive menu text."""
    capabilities = capabilities if capabilities is not None else CAPABILITIES
    lines = ["  sopx · sop-extractor unified CLI", "  " + "─" * 46]
    for cap in capabilities:
        available, reason = is_available(cap, scripts_dir)
        if available:
            lines.append(f"  {cap.key}) {cap.label}")
        else:
            lines.append(f"  {cap.key}) {cap.label}  [unavailable: {reason}]")
    lines.append("  " + "─" * 46)
    lines.append("  q) quit")
    return "\n".join(lines)


def dispatch(cap: Capability, args: list, scripts_dir: str = SCRIPTS_DIR) -> int:
    """Runs a capability's backing script as a subprocess."""
    available, reason = is_available(cap, scripts_dir)
    if not available:
        print(f"'{cap.label}' is unavailable: {reason}")
        return 1
    if cap.info_only:
        print(cap.info_text)
        return 0
    cmd = build_command(cap, args, scripts_dir)
    result = subprocess.run(cmd)
    return result.returncode


def run_interactive(capabilities=None, scripts_dir: str = SCRIPTS_DIR, input_fn=input):
    """The interactive loop."""
    capabilities = capabilities if capabilities is not None else CAPABILITIES
    banner_path = os.path.join(scripts_dir, "banner.txt")
    if os.path.isfile(banner_path):
        try:
            with open(banner_path, "r", encoding="utf-8") as f:
                print(f.read())
        except OSError:
            pass

    while True:
        print(format_menu(capabilities, scripts_dir))
        choice = input_fn("\n> ").strip()
        if choice.lower() in ("q", "quit", "exit"):
            return 0
        cap = find_capability(choice, capabilities)
        if cap is None:
            print(f"Unknown option: {choice!r}")
            continue
        raw_args = input_fn(f"Args for '{cap.label}' ({cap.arg_hint or 'no args'}): ").strip()
        args = raw_args.split() if raw_args else []
        dispatch(cap, args, scripts_dir)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv

    if not argv:
        return run_interactive()

    verb, rest = argv[0], argv[1:]
    if verb in ("-h", "--help"):
        print(format_menu())
        return 0

    cap = find_capability(verb)
    if cap is None:
        print(f"Unknown verb: {verb!r}. Run with no arguments to see the menu.", file=sys.stderr)
        return 1
    return dispatch(cap, rest)


if __name__ == "__main__":
    sys.exit(main())
