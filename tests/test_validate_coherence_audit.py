import os
import tempfile
from scripts.validate_coherence_audit import normalize, jaccard, verify_claim, run_validation

def test_normalize():
    # Should lowercase, remove punctuation, remove stopwords
    text = "The quick, brown fox jumps over the lazy dog!"
    normalized = normalize(text)
    assert "the" not in normalized
    assert "quick" in normalized
    assert "fox" in normalized
    assert "jumps" in normalized
    assert "," not in normalized
    assert "!" not in normalized

def test_jaccard():
    a = "This is a simple test sentence."
    b = "This simple test is a sentence."
    # Both normalize to the exact same set
    assert jaccard(a, b) == 1.0
    
    c = "A completely different claim."
    assert jaccard(a, c) < 0.2

def test_verify_claim_valid_citation():
    source = "The system must prioritize latency over throughput in real-time scenarios."
    
    # Exact match
    assert verify_claim("The system must prioritize latency over throughput in real-time scenarios.", source) == True
    
    # Paraphrased / slightly different word order, but high overlap
    claim = "In real-time scenarios, prioritize latency over throughput."
    assert verify_claim(claim, source) == True

def test_verify_claim_subset_fallback():
    source = "When evaluating database performance, always measure the p99 latency rather than the average."
    
    # Missing words (summarized) but all words in the claim are in the source
    # sa - sb will be empty
    claim = "Measure p99 latency rather than average."
    assert verify_claim(claim, source) == True
    
    # Even with 1-2 hallucinated/different words, it should pass the fallback if len(sa - sb) <= 2
    claim = "Must measure p99 latency rather than average." # 'must' is not in source
    assert verify_claim(claim, source) == True

def test_verify_claim_fabricated():
    source = "The cache should be invalidated every 5 minutes."
    claim = "The database requires manual vacuuming every night."
    assert verify_claim(claim, source) == False

def test_run_validation_pass():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create mock source files
        with open(os.path.join(tmpdir, "first_principles.md"), "w") as f:
            f.write("- **Principle**: measure p99 latency.\n")
        
        with open(os.path.join(tmpdir, "sops.md"), "w") as f:
            f.write("Trigger: high CPU.\nSteps: restart service.\n")
            
        # Create mock audit file
        audit_path = os.path.join(tmpdir, "coherence_audit.md")
        with open(audit_path, "w") as f:
            f.write("""
## Flagged Tensions
### 1. Latency tension
- **Claim A** (Ch 1): "measure p99 latency"
- **Claim B** (Ch 2): "restart service"
            """)
            
        # Should pass (exit code 0)
        assert run_validation(audit_path, os.path.join(tmpdir, "first_principles.md"), os.path.join(tmpdir, "sops.md")) == 0

def test_run_validation_fail_fabricated():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "first_principles.md"), "w") as f:
            f.write("- **Principle**: measure p99 latency.\n")
            
        audit_path = os.path.join(tmpdir, "coherence_audit.md")
        with open(audit_path, "w") as f:
            f.write("""
## Flagged Tensions
### 1. Fabricated tension
- **Claim A** (Ch 1): "measure p99 latency"
- **Claim B** (Ch 2): "completely hallucinated claim that is long enough to fail subset"
- **Claim A** (Ch 1): "another completely hallucinated claim that fails subset"
            """)
            
        # >30% unverified, should fail (exit code 1)
        assert run_validation(audit_path, os.path.join(tmpdir, "first_principles.md"), "none.md") == 1
