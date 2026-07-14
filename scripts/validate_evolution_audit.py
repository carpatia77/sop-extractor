import os
import re
import json
import sys
import argparse
import glob
from datetime import datetime
from typing import NamedTuple

class EvolutionResult(NamedTuple):
    exit_code: int
    unverified_pct: float = 0.0

# Re-use from validate_coherence_audit
try:
    # normalize/jaccard are intentionally re-exported for reuse (see test_8_import_reuse)
    from scripts.validate_coherence_audit import normalize, jaccard, verify_claim  # noqa: F401
except ImportError:
    from validate_coherence_audit import normalize, jaccard, verify_claim  # noqa: F401

def load_manifest(dir_path: str) -> dict:
    manifest_path = os.path.join(dir_path, "set_manifest.json")
    if not os.path.exists(manifest_path):
        print(f"Error: set_manifest.json not found in {dir_path}")
        sys.exit(1)

    with open(manifest_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return {
        member["source_id"]: {"date": member["date"], "sequence": member.get("sequence")}
        for member in data.get("members", [])
    }

def load_skill_source_text(dir_path: str, source_id: str) -> str:
    manifest_path = os.path.join(dir_path, "set_manifest.json")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    skill_path = None
    for m in data.get("members", []):
        if m["source_id"] == source_id:
            skill_path = os.path.join(dir_path, m["skill_path"])
            break
            
    if not skill_path or not os.path.exists(skill_path):
        return ""
        
    text = ""
    fp_path = os.path.join(skill_path, "first_principles.md")
    sops_path = os.path.join(skill_path, "sops.md")
    glossary_path = os.path.join(skill_path, "glossary.md")
    if os.path.exists(fp_path):
        with open(fp_path, 'r', encoding='utf-8') as f:
            text += f.read() + "\n"
    if os.path.exists(sops_path):
        with open(sops_path, 'r', encoding='utf-8') as f:
            text += f.read() + "\n"
    if os.path.exists(glossary_path):
        with open(glossary_path, 'r', encoding='utf-8') as f:
            text += f.read() + "\n"
            
    return text

def parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return datetime.min

def _discover(dir_path: str, suffix: str):
    matches = sorted(glob.glob(os.path.join(dir_path, f"*_{suffix}.md")))
    if len(matches) == 0:
        print(f"Error: no *_{suffix}.md file found in {dir_path}")
        return None
    if len(matches) > 1:
        names = [os.path.basename(m) for m in matches]
        print(f"Error: multiple *_{suffix}.md files in {dir_path}: {names}. Expected exactly one.")
        return None
    return matches[0]

def run_validation(dir_path: str) -> EvolutionResult:
    manifest = load_manifest(dir_path)
    
    evo_path = _discover(dir_path, "evolution")
    if evo_path is None:
        return EvolutionResult(1)
        
    with open(evo_path, 'r', encoding='utf-8') as f:
        evo_content = f.read()
        
    current_path = _discover(dir_path, "current")
    if current_path is None:
        return EvolutionResult(1)
        
    # 1. Validate current state format and Provenance Integrity
    with open(current_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            tag_match = re.search(r'\[(.*?)\]', line)
            if not tag_match:
                print(f"Error in {os.path.basename(current_path)} line {line_num}: Missing provenance tag [source_id/date]")
                print(f"Line: {line}")
                return EvolutionResult(1)
                
            tag_content = tag_match.group(1)
            pairs = re.findall(r'([\w-]+)/(\d{4}(?:-\d{2}-\d{2})?)', tag_content)
            
            if not pairs:
                print(f"Error in {os.path.basename(current_path)} line {line_num}: Missing provenance tag [source_id/date]")
                print(f"Line: {line}")
                return EvolutionResult(1)
                
            for sid, date_str in pairs:
                if sid not in manifest:
                    print(f"Provenance Integrity FAILED in {os.path.basename(current_path)} line {line_num}:")
                    print(f"Provenance tag cites unknown source '{sid}'.")
                    return EvolutionResult(1)
                    
                manifest_date = manifest[sid]["date"]
                if date_str != manifest_date:
                    print(f"Provenance Integrity FAILED in {os.path.basename(current_path)} line {line_num}:")
                    print(f"Tag date '{date_str}' for source '{sid}' contradicts manifest date '{manifest_date}'.")
                    return EvolutionResult(1)

    # 2. Parse evolution matrix
    sections = re.split(r'\n##\s+', evo_content)
    if len(sections) > 1:
        sections = sections[1:] 
    else:
        sections = []
        
    total_claims = 0
    unverified_claims = []
    
    for section in sections:
        lines = section.strip().split('\n')
        concept_name = lines[0].strip()
        
        previous_date = None
        previous_seq = None
        previous_source = None

        for line in lines:
            line = line.strip()
            if line.startswith('|') and not 'Fonte' in line and not '---' in line:
                parts = [p.strip() for p in line.split('|')[1:-1]]
                if len(parts) >= 5:
                    source_id = parts[0]
                    category = parts[3].lower()
                    description = parts[4]

                    if source_id not in manifest:
                        continue

                    current_date = parse_date(manifest[source_id]["date"])
                    current_seq = manifest[source_id]["sequence"]

                    # Chronology Gate for reaffirmed, refined, superseded.
                    # Two sources dated identically (e.g. same year, exact
                    # date unknown) require an explicit 'sequence' tie-breaker
                    # in set_manifest.json — never inferred from manifest
                    # order or file order, same anti-guessing discipline as
                    # everywhere else in this gate.
                    if category in ['reaffirmed', 'refined', 'superseded'] and previous_date is not None:
                        if current_date < previous_date:
                            print(f"Chronology Gate FAILED for concept '{concept_name}':")
                            print(f"Source '{source_id}' claims to {category} '{previous_source}', but is not chronologically later.")
                            return EvolutionResult(1)
                        if current_date == previous_date:
                            if current_seq is None or previous_seq is None:
                                print(f"Chronology Gate FAILED for concept '{concept_name}':")
                                print(f"Source '{source_id}' and '{previous_source}' share the same date ({manifest[source_id]['date']}); "
                                      f"add an explicit integer 'sequence' field to both members in set_manifest.json to establish order.")
                                return EvolutionResult(1)
                            if current_seq <= previous_seq:
                                print(f"Chronology Gate FAILED for concept '{concept_name}':")
                                print(f"Source '{source_id}' (sequence {current_seq}) claims to {category} '{previous_source}' (sequence {previous_seq}), but is not sequenced later.")
                                return EvolutionResult(1)

                    # Silence Gate
                    if category == 'superseded' and ('absence' in description.lower() or 'missing' in description.lower() or 'not mentioned' in description.lower() or 'silence' in description.lower()):
                        print(f"Silence Gate FAILED for concept '{concept_name}':")
                        print("Cannot infer 'superseded' from silence. Must downgrade to 'dropped?'.")
                        return EvolutionResult(1)
                        
                    # Dropped Confidence check
                    if 'dropped?' in category or category == 'dropped':
                        desc_lower = description.lower()
                        if 'high' in desc_lower or 'alta' in desc_lower:
                            print(f"Confidence Gate FAILED for concept '{concept_name}': dropped? must be low confidence.")
                            return EvolutionResult(1)
                            
                    if category not in ['introduced', 'dropped?', 'dropped']:
                        total_claims += 1
                        source_text = load_skill_source_text(dir_path, source_id)
                        if not verify_claim(description, source_text):
                            unverified_claims.append(description)
                            
                    previous_date = current_date
                    previous_seq = current_seq
                    previous_source = source_id

    if total_claims == 0:
        print("Warning: No transitions found to validate.")
        return EvolutionResult(0)
        
    unverified_pct = len(unverified_claims) / total_claims
    
    print(f"Validation summary: {total_claims - len(unverified_claims)}/{total_claims} claims verified.")
    if unverified_claims:
        print("\nUnverified claims:")
        for c in unverified_claims:
            print(f"- {c}")
            
    if unverified_pct > 0.3:
        print(f"\nFAILURE: Unverified claims ({unverified_pct*100:.1f}%) exceed the 30% threshold.")
        return EvolutionResult(1, unverified_pct)
        
    print("\nSUCCESS: Temporal evolution audit passed validation.")
    return EvolutionResult(0, unverified_pct)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate temporal evolution audit output.")
    parser.add_argument("--dir", default=".", help="Directory containing set_manifest.json and audit files")
    args = parser.parse_args()
    sys.exit(run_validation(args.dir).exit_code)
