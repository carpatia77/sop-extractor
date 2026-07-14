import json
from scripts.write_run_manifest import sha256_file, get_source_hash, write_run_manifest

def test_sha256_file(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world", encoding='utf-8')
    h = sha256_file(str(test_file))
    assert h == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    
    assert sha256_file(str(tmp_path / "not_exist.txt")) is None

def test_get_source_hash_transcripts(tmp_path):
    skill_dir = tmp_path / "skill_a"
    transcripts_dir = skill_dir / "transcripts"
    transcripts_dir.mkdir(parents=True)
    
    (transcripts_dir / "part1.srt").write_text("hello", encoding='utf-8')
    (transcripts_dir / "part2.srt").write_text(" world", encoding='utf-8')
    
    h = get_source_hash(str(skill_dir))
    # sha256 of "hello world"
    assert h == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

def test_write_run_manifest(tmp_path):
    # Setup mock set
    manifest = {
        "set_id": "test-set",
        "members": [
            {"source_id": "src1", "date": "2026-01-01", "skill_path": "skill1"}
        ]
    }
    
    (tmp_path / "set_manifest.json").write_text(json.dumps(manifest), encoding='utf-8')
    
    skill_dir = tmp_path / "skill1"
    skill_dir.mkdir()
    (skill_dir / "first_principles.md").write_text("principles", encoding='utf-8')
    (skill_dir / "sops.md").write_text("sops", encoding='utf-8')
    
    (tmp_path / "test_evolution.md").write_text("evo", encoding='utf-8')
    # Call the writer
    success = write_run_manifest(str(tmp_path), model="claude-4-test", audit_model="gpt-4o")
    assert success
    
    # Read the run.json
    run_json = tmp_path / "run.json"
    assert run_json.exists()
    
    with open(run_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    assert data["generated_by_model"] == "claude-4-test"
    assert data["audit_model"] == "gpt-4o"
    assert "prompt_version" in data
    
    assert len(data["sources"]) == 1
    src1 = data["sources"][0]
    assert src1["source_id"] == "src1"
    assert "first_principles.md" in src1["artifacts_sha256"]
    assert "sops.md" in src1["artifacts_sha256"]
    assert "glossary.md" not in src1["artifacts_sha256"] # Doesn't exist
    assert "source_sha256" not in src1 # No transcript or source.txt
    
    assert "test_evolution.md" in data["set_artifacts_sha256"]
