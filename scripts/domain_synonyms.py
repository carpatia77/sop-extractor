import os
import json
import re

def load_domain_synonyms(domain_id: str) -> dict[str, str]:
    """Loads domains/<domain_id>/synonyms.json and returns a flat {synonym: canonical} lookup."""
    if not domain_id:
        return {}
        
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(scripts_dir)
    synonyms_path = os.path.join(repo_root, "domains", domain_id, "synonyms.json")
    
    if not os.path.isfile(synonyms_path):
        return {}
        
    try:
        with open(synonyms_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        synonym_map = {}
        for group in data.get("groups", []):
            canonical = group.get("canonical", "").lower()
            if not canonical:
                continue
            for syn in group.get("synonyms", []):
                synonym_map[syn.lower()] = canonical
                
        return synonym_map
    except Exception as e:
        print(f"Warning: could not load synonyms for domain {domain_id}: {e}")
        return {}

def normalize_text(text: str, synonym_map: dict) -> str:
    """Substitutes synonyms for canonical terms in text using word boundaries and length-descending order."""
    if not synonym_map or not text:
        return text
        
    # Sort synonyms by length descending to match longest phrases first
    sorted_synonyms = sorted(synonym_map.keys(), key=len, reverse=True)
    
    # Escape synonyms for regex
    escaped_syns = [re.escape(syn) for syn in sorted_synonyms]
    # Wrap in word boundaries \b to avoid substring matching inside other words
    pattern = r'\b(' + '|'.join(escaped_syns) + r')\b'
    
    # Compile regex case-insensitively
    regex = re.compile(pattern, flags=re.IGNORECASE)
    
    # Replacement function
    def replacer(match):
        matched_str = match.group(1).lower()
        return synonym_map.get(matched_str, match.group(0))
        
    return regex.sub(replacer, text)
