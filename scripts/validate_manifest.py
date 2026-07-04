#!/usr/bin/env python3
"""Validates set_manifest.json (pure Python, no external dependencies).
Ensures structural integrity and cross-field rules (like date tie-breakers and dir existence).
"""

import os
import re
import json
import argparse
import sys
from collections import defaultdict

def validate_manifest(manifest_path: str) -> list:
    """Returns a list of error strings. Empty list means valid."""
    errors = []
    if not os.path.isfile(manifest_path):
        return [f"File not found: {manifest_path}"]
        
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]
        
    if not isinstance(data, dict):
        return ["Root must be a JSON object."]
        
    # Check set_id
    if "set_id" not in data or not isinstance(data["set_id"], str) or not data["set_id"].strip():
        errors.append("'set_id' is required and must be a non-empty string.")
        
    # Check members
    members = data.get("members")
    if not isinstance(members, list) or len(members) == 0:
        errors.append("'members' is required and must be a non-empty array.")
        return errors
        
    seen_sources = set()
    date_to_members = defaultdict(list)
    
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
    
    for i, m in enumerate(members):
        if not isinstance(m, dict):
            errors.append(f"Member at index {i} must be an object.")
            continue
            
        # source_id
        sid = m.get("source_id")
        if not isinstance(sid, str) or not re.match(r'^[a-z0-9][a-z0-9_-]*$', sid):
            errors.append(f"Member at index {i} has invalid 'source_id': '{sid}'. Must match ^[a-z0-9][a-z0-9_-]*$")
        else:
            if sid in seen_sources:
                errors.append(f"Duplicate 'source_id' found: '{sid}'")
            seen_sources.add(sid)
            
        # date
        date_val = m.get("date")
        if not isinstance(date_val, str) or not re.match(r'^\d{4}-\d{2}-\d{2}$', date_val):
            errors.append(f"Member '{sid or i}' has invalid 'date': '{date_val}'. Must be YYYY-MM-DD.")
        else:
            date_to_members[date_val].append(m)
            
        # role (optional)
        role = m.get("role")
        if role is not None and not isinstance(role, str):
            errors.append(f"Member '{sid or i}' has invalid 'role'. Must be a string.")
            
        # skill_path
        skill_path = m.get("skill_path")
        if not isinstance(skill_path, str) or not skill_path.strip():
            errors.append(f"Member '{sid or i}' is missing 'skill_path' string.")
        else:
            full_path = os.path.join(manifest_dir, skill_path)
            if not os.path.isdir(full_path):
                errors.append(f"Member '{sid or i}' specifies 'skill_path' '{skill_path}' which is not a valid directory relative to the manifest.")
                
        # sequence (optional)
        seq = m.get("sequence")
        if seq is not None and not isinstance(seq, int):
            errors.append(f"Member '{sid or i}' has invalid 'sequence'. Must be an integer.")

    # Cross-field: Check date tie-breakers
    for date_val, group in date_to_members.items():
        if len(group) > 1:
            missing_seq = [m.get("source_id", "unknown") for m in group if m.get("sequence") is None]
            if missing_seq:
                errors.append(f"Multiple members share date '{date_val}', but the following lack a 'sequence' tie-breaker: {missing_seq}")

    return errors

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate set_manifest.json")
    parser.add_argument("manifest_path", help="Path to set_manifest.json")
    args = parser.parse_args()
    
    errs = validate_manifest(args.manifest_path)
    if errs:
        print("Manifest validation failed:")
        for e in errs:
            print(f"- {e}")
        sys.exit(1)
    else:
        print("Manifest is valid.")
        sys.exit(0)
