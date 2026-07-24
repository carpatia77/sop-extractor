#!/usr/bin/env python3
"""Build set_manifest.json from ingested metadata.

Closes the provenance loop: output/<id>/metadata.json captures upload_date
from ingestion, and this script feeds it into set_manifest.json as a
labeled, confirmable proposal — never silently authoritative.

Usage:
    sopx set-build <set_dir> --source output/<id1> --source output/<id2> ...
    sopx set-build <set_dir> --from-outputs output/ --skills-root ./skills
    sopx set-build <set_dir> --dry-run
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def source_id_from_metadata(meta: dict) -> str:
    """Convert canonical_id to valid source_id for manifest.

    Rules:
    - Lowercase
    - Replace invalid chars with '-'
    - Must match ^[a-z0-9][a-z0-9_-]*$
    - Falls back to slugified title/filename if no canonical_id
    """
    raw = meta.get("canonical_id") or meta.get("title") or "unknown"
    # Lowercase and replace invalid chars
    slug = re.sub(r"[^a-z0-9_-]", "-", raw.lower())
    # Ensure starts with alphanumeric
    slug = re.sub(r"^[^a-z0-9]+", "", slug)
    # Ensure not empty
    if not slug:
        slug = "unknown"
    # Ensure matches pattern
    assert re.match(r"^[a-z0-9][a-z0-9_-]*$", slug), f"Invalid source_id: {slug}"
    return slug


def date_from_metadata(meta: dict) -> str | None:
    """Extract upload_date from metadata.

    Returns YYYY-MM-DD string or None. NEVER fabricates dates.
    None means the source needs a manual date entry.
    """
    date = meta.get("upload_date")
    if date and re.match(r"^\d{4}-\d{2}-\d{2}$", str(date)):
        return str(date)
    return None


def infer_sequence(members: list[dict]) -> list[dict]:
    """Sort members by date and assign sequence numbers.

    Members with dates come first (sorted chronologically).
    Members without dates get sequence None (human must fill).
    """
    # Separate into dated and undated
    dated = [m for m in members if m.get("date")]
    undated = [m for m in members if not m.get("date")]

    # Sort dated by date
    dated.sort(key=lambda m: m["date"])

    # Assign sequence to dated members
    for i, m in enumerate(dated, 1):
        m["sequence"] = i

    # Undated members get no sequence (human must fill)
    for m in undated:
        m["sequence"] = None

    return dated + undated


def build_manifest(
    set_id: str,
    entries: list[dict],
    skills_root: str | Path | None = None,
    existing_manifest: dict | None = None,
) -> dict:
    """Build set_manifest.json from ingestion entries.

    Args:
        set_id: Set identifier (e.g., "fullcycle")
        entries: List of dicts with 'output_dir' and optional 'skill_path'
        skills_root: Root directory for skills (for relative paths)
        existing_manifest: Existing manifest to merge with (for idempotent updates)

    Returns:
        Complete manifest dict ready to write
    """
    members = []

    # Load existing manifest for merge
    existing_by_sid = {}
    if existing_manifest:
        for m in existing_manifest.get("members", []):
            sid = m.get("source_id")
            if sid:
                existing_by_sid[sid] = m

    for entry in entries:
        output_dir = Path(entry["output_dir"])

        # Load metadata
        meta_path = output_dir / "metadata.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        else:
            meta = {}

        # Build member
        sid = source_id_from_metadata(meta)
        date = date_from_metadata(meta)

        member = {
            "source_id": sid,
            "date": date or "",
            "role": meta.get("role", "practitioner_book"),
        }

        # Skill path
        if "skill_path" in entry:
            member["skill_path"] = entry["skill_path"]
        elif skills_root:
            # Try to find skill directory
            skill_dir = Path(skills_root) / sid
            if skill_dir.exists():
                member["skill_path"] = str(skill_dir.relative_to(output_dir.parent))
            else:
                member["skill_path"] = f"../skills/{sid}"
        else:
            member["skill_path"] = f"../skills/{sid}"

        # Merge with existing (preserve manual overrides)
        if sid in existing_by_sid:
            existing = existing_by_sid[sid]
            # Preserve manual date overrides
            if existing.get("date_source") == "manual" and existing.get("date"):
                member["date"] = existing["date"]
                member["date_source"] = "manual"
            else:
                member["date_source"] = "ingested" if date else "needs_date"
        else:
            member["date_source"] = "ingested" if date else "needs_date"

        # Mark needs_date flag for members without dates
        if not member["date"]:
            member["needs_date"] = True

        members.append(member)

    # Infer sequence numbers
    members = infer_sequence(members)

    # Build manifest
    manifest = {
        "set_id": set_id,
        "members": members,
    }

    return manifest


def validate_manifest_data(manifest: dict) -> list[str]:
    """Validate manifest data structure (same rules as validate_manifest.py).

    Returns list of error strings. Empty list means valid.
    """
    errors = []

    if not isinstance(manifest, dict):
        return ["Root must be a JSON object."]

    # Check set_id
    if "set_id" not in manifest or not isinstance(manifest["set_id"], str):
        errors.append("'set_id' is required and must be a string.")

    # Check members
    members = manifest.get("members")
    if not isinstance(members, list) or len(members) == 0:
        errors.append("'members' is required and must be a non-empty array.")
        return errors

    seen_sources = set()
    for i, m in enumerate(members):
        if not isinstance(m, dict):
            errors.append(f"Member at index {i} must be an object.")
            continue

        # source_id
        sid = m.get("source_id")
        if not isinstance(sid, str) or not re.match(r"^[a-z0-9][a-z0-9_-]*$", sid):
            errors.append(
                f"Member at index {i} has invalid 'source_id': '{sid}'. "
                f"Must match ^[a-z0-9][a-z0-9_-]*$"
            )
        else:
            if sid in seen_sources:
                errors.append(f"Duplicate 'source_id' found: '{sid}'")
            seen_sources.add(sid)

        # date (must be valid format if present)
        date_val = m.get("date")
        if date_val and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date_val)):
            errors.append(
                f"Member '{sid or i}' has invalid 'date': '{date_val}'. "
                f"Must be YYYY-MM-DD."
            )

        # skill_path
        skill_path = m.get("skill_path")
        if not isinstance(skill_path, str) or not skill_path.strip():
            errors.append(f"Member '{sid or i}' is missing 'skill_path' string.")

    return errors


def print_summary(manifest: dict):
    """Print human-readable summary of manifest."""
    set_id = manifest.get("set_id", "unknown")
    members = manifest.get("members", [])

    print(f"\n  Set: {set_id}  ({len(members)} membros)")
    print(f"  {'─' * 50}")

    for m in members:
        sid = m.get("source_id", "?")
        date = m.get("date", "")
        seq = m.get("sequence", "?")
        source = m.get("date_source", "unknown")
        needs_date = m.get("needs_date", False)

        if needs_date or not date:
            print(f"  ⚠ src {sid:<25} {'<SEM DATA>':<12} seq {seq or '?':<4} [needs_date]")
        else:
            print(f"  ✓ src {sid:<25} {date:<12} seq {seq or '?':<4} [{source}]")

    print(f"  {'─' * 50}")


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Build set_manifest.json from ingested metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  sopx set-build ./my-set --source output/vid1 --source output/vid2\n"
            "  sopx set-build ./my-set --from-outputs output/ --skills-root ./skills\n"
            "  sopx set-build ./my-set --dry-run\n"
        ),
    )
    parser.add_argument("set_dir", help="Directory for the set")
    parser.add_argument(
        "--source", action="append", default=[],
        help="Source output directory (can be repeated)"
    )
    parser.add_argument(
        "--from-outputs", default=None,
        help="Scan directory for output subdirectories"
    )
    parser.add_argument(
        "--skills-root", default=None,
        help="Root directory for skills"
    )
    parser.add_argument(
        "--set-id", default=None,
        help="Set ID (default: directory name)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show manifest without writing"
    )

    args = parser.parse_args(argv)

    set_dir = Path(args.set_dir)
    set_id = args.set_id or set_dir.name

    # Collect entries
    entries = []

    if args.source:
        for src in args.source:
            entries.append({"output_dir": src})

    if args.from_outputs:
        outputs_dir = Path(args.from_outputs)
        if outputs_dir.exists():
            for item in outputs_dir.iterdir():
                if item.is_dir() and (item / "metadata.json").exists():
                    entries.append({"output_dir": str(item)})

    if not entries:
        print("  Erro: nenhuma fonte especificada", file=sys.stderr)
        print("  Use --source <dir> ou --from-outputs <dir>", file=sys.stderr)
        return 1

    # Load existing manifest if present
    manifest_path = set_dir / "set_manifest.json"
    existing_manifest = None
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            existing_manifest = json.load(f)

    # Build manifest
    manifest = build_manifest(
        set_id=set_id,
        entries=entries,
        skills_root=args.skills_root,
        existing_manifest=existing_manifest,
    )

    # Validate
    errors = validate_manifest_data(manifest)
    if errors:
        print("  Erros de validação:", file=sys.stderr)
        for e in errors:
            print(f"    - {e}", file=sys.stderr)
        return 1

    # Print summary
    print_summary(manifest)

    if args.dry_run:
        print("\n  [dry-run] Manifest não foi gravado.")
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0

    # Write manifest
    set_dir.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n  Manifest gravado: {manifest_path}")
    print(f"  → Próximo: sopx validate {set_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
