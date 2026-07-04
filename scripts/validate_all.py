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

def validate_skill(skill_dir: str) -> int:
    dir_path = Path(skill_dir)
    if not dir_path.is_dir():
        print(f"Error: Directory {skill_dir} not found.")
        return 1

    print(f"=== Validating Skill: {skill_dir} ===")
    
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
            res = run_coherence(str(audit_path), str(fp_path), str(sops_path))
            if res == 0:
                print("✅ Coherence validation passed.")
            else:
                print("❌ Coherence validation failed.")
                overall_status = 1
        except Exception as e:
            print(f"Error in Coherence Audit: {e}")
            overall_status = 1

    # 4. Evolution Audit
    manifest_path = dir_path / "set_manifest.json"
    if manifest_path.exists():
        print("\n--- 4. Evolution Audit ---")
        try:
            res = run_evolution(str(dir_path))
            if res == 0:
                print("✅ Evolution validation passed.")
            else:
                print("❌ Evolution validation failed.")
                overall_status = 1
        except Exception as e:
            print(f"Error in Evolution Audit: {e}")
            overall_status = 1

    print("\n=============================================")
    if overall_status == 0:
        print("✅ ALL DISCOVERED VALIDATIONS PASSED.")
    else:
        print("❌ ONE OR MORE VALIDATIONS FAILED.")
        
    return overall_status

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified validation harness.")
    parser.add_argument("skill_dir", help="Path to the skill directory")
    args = parser.parse_args()
    
    sys.exit(validate_skill(args.skill_dir))
