#!/usr/bin/env python3
"""Unified validation harness for SOP Extractor skills.
Runs determinism, concept presence, coherence, and evolution validations.
"""

import argparse
import sys
import os
from pathlib import Path

# Add the scripts directory to the path so we can import the other scripts
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from determinism_score import score_skill
from verify_concept_presence import verify_source
from validate_coherence_audit import run_validation as run_coherence
from validate_evolution_audit import run_validation as run_evolution
from validate_manifest import validate_manifest

def validate_skill(skill_dir: str, since_last: bool = False) -> int:
    dir_path = Path(skill_dir)
    if not dir_path.is_dir():
        print(f"Error: Directory {skill_dir} not found.")
        return 1
        
    if since_last:
        try:
            from detect_changes import detect_changes, print_changes
            changes = detect_changes(skill_dir)
            print_changes(changes)
        except Exception as e:
            print(f"Warning: could not detect changes: {e}")

    print(f"=== Validating Set/Skill: {skill_dir} ===")
    
    # 0. Set Manifest Validation (Fail-Fast)
    manifest_path = dir_path / "set_manifest.json"
    if manifest_path.exists():
        errs = validate_manifest(str(manifest_path))
        if errs:
            print("\n❌ Manifest validation failed. Aborting.")
            for e in errs:
                print(f"  - {e}")
            return 1
    
    overall_status = 0
    
    # 1. Determinism Score
    chapters_dir = dir_path / "chapters"
    if chapters_dir.is_dir():
        print("\n--- 1. Determinism Score ---")
        try:
            score_res = score_skill(chapters_dir)
            cov = score_res.get('coverage_pct')
            if cov is not None:
                print(f"Procedural signal coverage: {cov*100:.1f}% ({score_res['chapters_with_procedural_signal']}/{score_res['chapters_total']} chapters)")
            det = score_res.get('book_determinism_pct')
            if det is not None:
                print(f"Overall Determinism: {det*100:.1f}%")
        except Exception as e:
            print(f"Error computing determinism: {e}")
            overall_status = 1
    
    # 2. Concept Presence (Jaccard Triage)
    print("\n--- 2. Concept Presence Triage ---")
    try:
        triage_res = verify_source(str(dir_path))
        if "error" in triage_res:
            print(f"Skipped: {triage_res['error']}")
        else:
            flags = len(triage_res.get('review_flags', []))
            print(f"Analyzed {triage_res.get('n_principles', 0)} principles.")
            if flags > 0:
                print(f"🔎 {flags} principles flagged for review (low source overlap).")
            else:
                print("✅ No principles flagged for missing terms.")
    except Exception as e:
        print(f"Error verifying concept presence: {e}")
        overall_status = 1

    # 3. Coherence Audit
    audit_path = dir_path / "coherence_audit.md"
    if audit_path.exists():
        print("\n--- 3. Coherence Audit ---")
        fp_path = dir_path / "first_principles.md"
        sops_path = dir_path / "sops.md"
        try:
            coherence_res = run_coherence(str(audit_path), str(fp_path), str(sops_path))
            if coherence_res == 0:
                print("✅ Coherence validation passed.")
            else:
                print("❌ Coherence validation failed.")
                overall_status = 1
        except Exception as e:
            print(f"Error in Coherence Audit: {e}")
            overall_status = 1

    # 4. Evolution Audit
    unverified_pct = None
    manifest_path = dir_path / "set_manifest.json"
    if manifest_path.exists():
        print("\n--- 4. Evolution Audit ---")
        try:
            res = run_evolution(str(dir_path))
            if res.exit_code == 0:
                print("✅ Evolution validation passed.")
            else:
                print("❌ Evolution validation failed.")
                overall_status = 1
            unverified_pct = res.unverified_pct
        except Exception as e:
            print(f"Error in Evolution Audit: {e}")
            overall_status = 1

    print("\n=============================================")
    if overall_status == 0:
        print("✅ ALL DISCOVERED VALIDATIONS PASSED.")
    else:
        print("❌ ONE OR MORE VALIDATIONS FAILED.")
        
    try:
        from _runlog import append_run
        from datetime import datetime, timezone
        
        # Build per_skill stats
        # Currently we run triage and coherence on the dir_path directly.
        skill_id = dir_path.name
        skill_stats = {}
        
        if 'det' in locals() and det is not None:
            skill_stats['determinism_pct'] = det
        if 'flags' in locals():
            skill_stats['concept_flags'] = flags
        if 'coherence_res' in locals() and 'coherence_audit.md' in str(audit_path):
            skill_stats['coherence'] = "pass" if coherence_res == 0 else "fail"
            
        record = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "set": dir_path.name,
            "evolution": "pass" if (manifest_path.exists() and unverified_pct is not None and overall_status == 0) else "fail",
            "per_skill": {skill_id: skill_stats} if skill_stats else {}
        }
        if unverified_pct is not None:
            record["unverified_claims_pct"] = unverified_pct
            
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_path = os.path.join(repo_root, "runs.jsonl")
        append_run(record, log_path)
    except Exception as e:
        print(f"Warning: could not write to run log: {e}")
        
    return overall_status

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified validation harness.")
    parser.add_argument("skill_dir", help="Path to the set/skill directory")
    parser.add_argument("--write-run", action="store_true", help="Stamp a run.json record upon successful validation")
    parser.add_argument("--model", default="unspecified", help="Model used, to stamp into run.json (e.g. claude-3-opus)")
    parser.add_argument("--since-last", action="store_true", help="Print structural changes since last run")
    args = parser.parse_args()
    
    status = validate_skill(args.skill_dir, since_last=args.since_last)
    
    if status == 0 and args.write_run:
        from write_run_manifest import write_run_manifest
        print("\n--- Stamping Reproducibility Record ---")
        write_run_manifest(args.skill_dir, model=args.model)
        
    sys.exit(status)
