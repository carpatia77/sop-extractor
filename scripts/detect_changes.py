import os
import json
from pathlib import Path
import sys

# Add the scripts directory to the path so we can import the other scripts
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_run_manifest import sha256_file, get_source_hash

def detect_changes(set_dir: str) -> dict:
    set_dir_path = Path(set_dir).resolve()
    manifest_path = set_dir_path / "set_manifest.json"
    run_json_path = set_dir_path / "run.json"
    
    res = {
        "new": [],
        "removed": [],
        "unchanged": [],
        "source-changed": [],
        "artifacts-changed": []
    }
    
    if not manifest_path.exists():
        return res
        
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest_data = json.load(f)
        
    current_members = {m["source_id"]: m for m in manifest_data.get("members", [])}
    
    if not run_json_path.exists():
        res["new"] = list(current_members.keys())
        return res
        
    with open(run_json_path, 'r', encoding='utf-8') as f:
        run_data = json.load(f)
        
    old_sources = {s["source_id"]: s for s in run_data.get("sources", [])}
    
    # Check removed
    for sid in old_sources:
        if sid not in current_members:
            res["removed"].append(sid)
            
    # Check others
    for sid, m in current_members.items():
        if sid not in old_sources:
            res["new"].append(sid)
            continue
            
        old_rec = old_sources[sid]
        old_src_hash = old_rec.get("source_sha256")
        old_artifacts = old_rec.get("artifacts_sha256", {})
        
        skill_full_path = set_dir_path / m["skill_path"]
        
        # current hashes
        curr_src_hash = get_source_hash(str(skill_full_path))
        
        if (old_src_hash is None and curr_src_hash is not None) or \
           (old_src_hash is not None and curr_src_hash is None) or \
           (old_src_hash != curr_src_hash):
            res["source-changed"].append(sid)
            continue
            
        # check artifacts
        artifacts_differ = False
        for art in ["first_principles.md", "sops.md", "glossary.md"]:
            curr_art_hash = sha256_file(str(skill_full_path / art))
            old_art_hash = old_artifacts.get(art)
            if curr_art_hash != old_art_hash:
                artifacts_differ = True
                break
                
        if artifacts_differ:
            res["artifacts-changed"].append(sid)
        else:
            res["unchanged"].append(sid)
            
    return res

def print_changes(changes: dict):
    print("\n=== Change Detection (Since Last Run) ===")
    has_changes = False
    
    for category in ["new", "removed", "source-changed", "artifacts-changed", "unchanged"]:
        items = changes.get(category, [])
        if items:
            if category != "unchanged":
                has_changes = True
            
            icon = {
                "new": "🟢",
                "removed": "🔴",
                "source-changed": "🟡",
                "artifacts-changed": "🔵",
                "unchanged": "⚪"
            }.get(category, "")
            
            print(f"{icon} {category.upper()}:")
            for item in sorted(items):
                print(f"    - {item}")
                
    if not has_changes and changes.get("unchanged"):
        print("✅ All sources and artifacts are unchanged.")
        
    print("=========================================\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", required=True, help="Set directory")
    args = parser.parse_args()
    
    changes = detect_changes(args.set)
    print_changes(changes)
