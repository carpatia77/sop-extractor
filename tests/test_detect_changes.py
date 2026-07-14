import json
from scripts.detect_changes import detect_changes

def test_detect_changes(tmp_path):
    set_dir = tmp_path / "setA"
    set_dir.mkdir()
    
    # 1. No run.json -> all new
    manifest = {
        "members": [
            {"source_id": "sk1", "skill_path": "sk1"},
            {"source_id": "sk2", "skill_path": "sk2"}
        ]
    }
    (set_dir / "set_manifest.json").write_text(json.dumps(manifest), encoding='utf-8')
    
    changes = detect_changes(str(set_dir))
    assert set(changes["new"]) == {"sk1", "sk2"}
    assert not changes["removed"]
    
    # 2. Unchanged
    # Setup mock skills
    sk1_dir = set_dir / "sk1"
    sk1_dir.mkdir()
    (sk1_dir / "first_principles.md").write_text("fp1", encoding='utf-8')
    (sk1_dir / "transcripts").mkdir()
    (sk1_dir / "transcripts" / "t.srt").write_text("src1", encoding='utf-8')
    
    from scripts.write_run_manifest import sha256_file, get_source_hash
    h_fp1 = sha256_file(str(sk1_dir / "first_principles.md"))
    h_src1 = get_source_hash(str(sk1_dir))
    
    run_record = {
        "sources": [
            {
                "source_id": "sk1", 
                "source_sha256": h_src1, 
                "artifacts_sha256": {"first_principles.md": h_fp1}
            },
            {
                "source_id": "sk_removed",
                "source_sha256": "old_hash",
                "artifacts_sha256": {}
            }
        ]
    }
    (set_dir / "run.json").write_text(json.dumps(run_record), encoding='utf-8')
    
    changes = detect_changes(str(set_dir))
    # sk1 should be unchanged, sk_removed should be removed, sk2 should be new
    assert "sk1" in changes["unchanged"]
    assert "sk2" in changes["new"]
    assert "sk_removed" in changes["removed"]
    
    # 3. Source changed (mutated transcript)
    (sk1_dir / "transcripts" / "t.srt").write_text("src1_mutated", encoding='utf-8')
    changes = detect_changes(str(set_dir))
    assert "sk1" in changes["source-changed"]
    
    # 4. Source hash present -> absent
    # Delete the transcripts folder
    import shutil
    shutil.rmtree(str(sk1_dir / "transcripts"))
    changes = detect_changes(str(set_dir))
    assert "sk1" in changes["source-changed"]
    
    # 5. Artifact changed
    # Re-create transcript with original content to fix source hash
    (sk1_dir / "transcripts").mkdir()
    (sk1_dir / "transcripts" / "t.srt").write_text("src1", encoding='utf-8')
    # Mutate artifact
    (sk1_dir / "first_principles.md").write_text("fp1_mutated", encoding='utf-8')
    changes = detect_changes(str(set_dir))
    assert "sk1" in changes["artifacts-changed"]
    
    # 6. Source hash absent -> present
    # Write a new run.json where sk1 has NO source_sha256
    run_record["sources"][0].pop("source_sha256")
    (set_dir / "run.json").write_text(json.dumps(run_record), encoding='utf-8')
    # Since sk1 still has a transcript on disk, it has a hash now, but didn't before
    changes = detect_changes(str(set_dir))
    assert "sk1" in changes["source-changed"]
