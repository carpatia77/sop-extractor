import json

from scripts.domain_synonyms import load_domain_synonyms, normalize_text
from scripts.verify_concept_presence import score_principle
from scripts.validate_coherence_audit import verify_claim

def test_load_domain_synonyms(tmp_path, monkeypatch):
    # Mock __file__ inside load_domain_synonyms using monkeypatch on os.path
    import scripts.domain_synonyms as ds
    
    # We create a fake directory structure
    fake_repo_root = tmp_path
    domains_dir = fake_repo_root / "domains" / "test-domain"
    domains_dir.mkdir(parents=True)
    
    synonyms_json = {
        "domain_id": "test-domain",
        "groups": [
            {"canonical": "target", "synonyms": ["alvo", "objetivo"]},
            {"canonical": "trading range", "synonyms": ["faixa de negociação"]}
        ]
    }
    
    (domains_dir / "synonyms.json").write_text(json.dumps(synonyms_json), encoding='utf-8')
    
    # Monkeypatch the paths inside domain_synonyms
    monkeypatch.setattr(ds.os.path, 'abspath', lambda x: str(fake_repo_root / "scripts" / "domain_synonyms.py"))
    monkeypatch.setattr(ds.os.path, 'dirname', lambda x: str(fake_repo_root) if x.endswith("scripts") else str(fake_repo_root / "scripts"))
    
    syn_map = load_domain_synonyms("test-domain")
    
    assert syn_map["alvo"] == "target"
    assert syn_map["objetivo"] == "target"
    assert syn_map["faixa de negociação"] == "trading range"
    
    # Missing domain should return empty dict safely
    assert load_domain_synonyms("nonexistent-domain") == {}

def test_normalize_text():
    syn_map = {
        "banda de preço": "range",
        "range": "range", # Can be present
        "trading range": "consolidation",
        "alvo": "target"
    }
    
    # Test longer phrase takes precedence ("trading range" vs "range")
    # Actually wait, in this test dict, "trading range" has 13 chars, "banda de preço" has 14, "range" has 5.
    text1 = "We hit the trading range early."
    res1 = normalize_text(text1, syn_map)
    assert res1 == "We hit the consolidation early."
    
    text2 = "A banda de preço está clara."
    res2 = normalize_text(text2, syn_map)
    assert res2 == "A range está clara."
    
    # Word boundary test: "alvo" shouldn't match "salvo"
    text3 = "Eu fui salvo, esse não é o alvo."
    res3 = normalize_text(text3, syn_map)
    assert res3 == "Eu fui salvo, esse não é o target."
    
    # Empty inputs
    assert normalize_text("", syn_map) == ""
    assert normalize_text("text", {}) == "text"
    assert normalize_text("text", None) == "text"

def test_verify_concept_presence_with_synonyms():
    # Simulate a claim that uses "banda de preço" and a corpus that uses "range"
    claim = "O preço ficou na banda de preço"
    corpus = "the market entered a range and stayed there."
    
    # Without synonyms, the salient terms "banda", "preço" are absent in corpus.
    res_without = score_principle(claim, corpus)
    assert res_without["score"] < 1.0
    
    syn_map = {"banda de preço": "range"}
    # With synonyms, "banda de preço" -> "range", and "range" IS in corpus.
    # Wait, the corpus has "range", which is already canonical.
    res_with = score_principle(claim, corpus, synonym_map=syn_map)
    assert res_with["score"] > res_without["score"]

def test_validate_coherence_audit_with_synonyms():
    claim = "The participant showed directional conviction"
    source = "The participant showed initiative in the market."
    
    syn_map = {"directional conviction": "initiative"}
    res_with = verify_claim(claim, source, synonym_map=syn_map)

    # The synonym map should normalize the claim to "initiative", making it match the source exactly.
    assert res_with is True
