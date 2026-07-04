import os
import re
import sys
import argparse

try:
    from scripts.domain_synonyms import load_domain_synonyms, normalize_text
except ImportError:
    from domain_synonyms import load_domain_synonyms, normalize_text

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as", "at", 
    "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't", "cannot", "could", 
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "few", "for", 
    "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", 
    "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", 
    "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", 
    "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", 
    "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", 
    "so", "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there", 
    "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too", 
    "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what", 
    "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with", 
    "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves",
    # Portuguese common stopwords
    "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "por", "para", "com", "sem", "que", "se", "como", "mas", "ou", "e", "é"
}

def normalize(s: str) -> set:
    s = s.lower()
    s = re.sub(r'[^\w\s]', '', s)
    tokens = s.split()
    return set(tokens) - STOPWORDS

def jaccard(a: str, b: str) -> float:
    sa, sb = normalize(a), normalize(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

def verify_claim(claim: str, source_text: str, synonym_map: dict = None) -> bool:
    if synonym_map:
        claim = normalize_text(claim, synonym_map)
        source_text = normalize_text(source_text, synonym_map)
        
    sa = normalize(claim)
    if not sa:
        return False
    
    # Split source into roughly sentence-sized chunks
    sentences = re.split(r'[\n\.]', source_text)
    
    for sentence in sentences:
        sb = normalize(sentence)
        if not sb:
            continue
        
        score = jaccard(claim, sentence)
        if score >= 0.4:
            return True
            
        # Subset fallback
        if len(sa - sb) <= 2 and len(sa) > 0:
            return True
            
    return False

def run_validation(audit_path: str, first_principles_path: str, sops_path: str, synonym_map: dict = None) -> int:
    if not os.path.exists(audit_path):
        print(f"Error: Audit file not found: {audit_path}")
        return 1

    try:
        with open(audit_path, 'r', encoding='utf-8') as f:
            audit_text = f.read()
            
        source_text = ""
        if os.path.exists(first_principles_path):
            with open(first_principles_path, 'r', encoding='utf-8') as f:
                source_text += f.read() + "\n"
        if os.path.exists(sops_path):
            with open(sops_path, 'r', encoding='utf-8') as f:
                source_text += f.read() + "\n"
                
        if not source_text:
            print("Error: Could not find first_principles.md or sops.md to validate against.")
            return 1
            
        # Regex to find Claim A and Claim B
        claims = re.findall(r'-\s*\*\*Claim [A-B]\*\*(?:[^:]*):\s*"([^"]+)"', audit_text)
        
        if not claims:
            claims = re.findall(r'Claim [A-B].*?:\s*"([^"]+)"', audit_text, re.IGNORECASE)
            
        if not claims:
            print("Warning: No claims found to validate in the audit file. Empty or invalid format.")
            return 0
            
        total_claims = len(claims)
        unverified_claims = []
        
        for claim in claims:
            if not verify_claim(claim, source_text, synonym_map):
                unverified_claims.append(claim)
                
        unverified_pct = len(unverified_claims) / total_claims
        
        print(f"Validation summary: {total_claims - len(unverified_claims)}/{total_claims} claims verified.")
        
        if unverified_claims:
            print("\nUnverified claims:")
            for c in unverified_claims:
                print(f"- {c}")
                
        if unverified_pct > 0.3:
            print(f"\nFAILURE: Unverified claims ({unverified_pct*100:.1f}%) exceed the 30% threshold.")
            print("The audit generated by the LLM appears to contain hallucinated citations.")
            return 1
            
        print("\nSUCCESS: Coherence audit passed validation.")
        return 0
        
    except Exception as e:
        print(f"Error validating audit: {e}")
        return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate coherence audit output against sources.")
    parser.add_argument("audit_file", help="Path to coherence_audit.md")
    parser.add_argument("--dir", default=".", help="Directory containing first_principles.md and sops.md")
    parser.add_argument("--domain", default=None, help="Domain ID to load synonyms for (e.g. market-structure)")
    
    args = parser.parse_args()
    
    synonym_map = load_domain_synonyms(args.domain) if args.domain else None
    
    fp_path = os.path.join(args.dir, "first_principles.md")
    sops_path = os.path.join(args.dir, "sops.md")
    
    sys.exit(run_validation(args.audit_file, fp_path, sops_path, synonym_map))
