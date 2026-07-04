#!/usr/bin/env python3
"""Writes a run.json to record the exact inputs and artifacts of a validation run.
"""

import os
import json
import hashlib
import subprocess
import glob
from datetime import datetime
from pathlib import Path

def sha256_file(path: str) -> str:
    """Returns the SHA-256 digest of a file, or None if it doesn't exist."""
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def get_source_hash(skill_dir: str) -> str:
    """Attempts to hash the raw source (transcripts or source.txt)."""
    transcripts = sorted(glob.glob(os.path.join(skill_dir, "transcripts", "*.srt")))
    if transcripts:
        h = hashlib.sha256()
        for t in transcripts:
            with open(t, 'rb') as f:
                while chunk := f.read(8192):
                    h.update(chunk)
        return h.hexdigest()
        
    src_txt = os.path.join(skill_dir, "source.txt")
    if os.path.isfile(src_txt):
        return sha256_file(src_txt)
        
    return None

def get_prompt_version(repo_root: str) -> str:
    """Captures the git blob hash of SKILL.md, or unversioned if not available."""
    try:
        # Check if SKILL.md exists in repo_root to ensure we can hash it
        skill_path = os.path.join(repo_root, "SKILL.md")
        if not os.path.isfile(skill_path):
            return "unversioned"
            
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD:SKILL.md"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True
        )
        return f"git:{result.stdout.strip()}"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unversioned"

def write_run_manifest(set_dir: str, model: str = "unspecified"):
    set_dir_path = Path(set_dir).resolve()
    manifest_path = set_dir_path / "set_manifest.json"
    
    if not manifest_path.exists():
        print(f"Error: set_manifest.json not found in {set_dir}")
        return False
        
    with open(manifest_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Assume the script is run from somewhere inside the git repo, we can find the repo root
    # by looking for .git or just use the current working directory as a fallback.
    # A robust way is to just use the parent of scripts/ directory.
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(scripts_dir)
    
    run_id = datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    
    run_record = {
        "run_id": run_id,
        "generated_by_model": model,
        "prompt_version": get_prompt_version(repo_root),
        "sources": [],
        "set_artifacts_sha256": {}
    }
    
    for member in data.get("members", []):
        sid = member["source_id"]
        skill_rel_path = member["skill_path"]
        skill_full_path = set_dir_path / skill_rel_path
        
        source_rec = {
            "source_id": sid,
            "skill_path": skill_rel_path,
            "artifacts_sha256": {}
        }
        
        # Source hash (optional)
        src_hash = get_source_hash(str(skill_full_path))
        if src_hash:
            source_rec["source_sha256"] = src_hash
            
        # Artifacts hashes
        for art in ["first_principles.md", "sops.md", "glossary.md"]:
            art_hash = sha256_file(str(skill_full_path / art))
            if art_hash:
                source_rec["artifacts_sha256"][art] = art_hash
                
        run_record["sources"].append(source_rec)
        
    # Set-level artifacts
    evo_files = glob.glob(os.path.join(set_dir, "*_evolution.md"))
    curr_files = glob.glob(os.path.join(set_dir, "*_current.md"))
    
    for f in evo_files + curr_files:
        h = sha256_file(f)
        if h:
            run_record["set_artifacts_sha256"][os.path.basename(f)] = h
            
    run_json_path = set_dir_path / "run.json"
    with open(run_json_path, 'w', encoding='utf-8') as f:
        json.dump(run_record, f, indent=2)
        
    print(f"✅ Stamped run record to {run_json_path.name} (run_id: {run_id})")
    return True

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Write a run.json to record validation inputs.")
    parser.add_argument("--set", required=True, help="Path to the set directory")
    parser.add_argument("--model", default="unspecified", help="Model used for extraction (e.g. claude-3-opus)")
    args = parser.parse_args()
    
    write_run_manifest(args.set, args.model)
