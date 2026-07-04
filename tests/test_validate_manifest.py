import os
import json
import pytest
from scripts.validate_manifest import validate_manifest

def create_manifest(tmp_path, data):
    manifest_path = tmp_path / "set_manifest.json"
    manifest_path.write_text(json.dumps(data), encoding='utf-8')
    return str(manifest_path)

def test_valid_manifest(tmp_path):
    (tmp_path / "skill1").mkdir()
    (tmp_path / "skill2").mkdir()
    
    data = {
        "set_id": "test-set",
        "members": [
            {
                "source_id": "src1",
                "date": "2026-01-01",
                "skill_path": "skill1"
            },
            {
                "source_id": "src2",
                "date": "2026-02-01",
                "skill_path": "skill2"
            }
        ]
    }
    manifest_path = create_manifest(tmp_path, data)
    errs = validate_manifest(manifest_path)
    assert not errs, f"Expected valid manifest, got errors: {errs}"

def test_duplicate_source_id(tmp_path):
    (tmp_path / "skill1").mkdir()
    data = {
        "set_id": "test-set",
        "members": [
            {"source_id": "dup", "date": "2026-01-01", "skill_path": "skill1"},
            {"source_id": "dup", "date": "2026-02-01", "skill_path": "skill1"}
        ]
    }
    manifest_path = create_manifest(tmp_path, data)
    errs = validate_manifest(manifest_path)
    assert any("Duplicate 'source_id' found" in e for e in errs)

def test_invalid_date(tmp_path):
    (tmp_path / "skill1").mkdir()
    data = {
        "set_id": "test-set",
        "members": [
            {"source_id": "src1", "date": "01-01-2026", "skill_path": "skill1"}
        ]
    }
    manifest_path = create_manifest(tmp_path, data)
    errs = validate_manifest(manifest_path)
    assert any("invalid 'date'" in e for e in errs)

def test_tied_dates_without_sequence(tmp_path):
    (tmp_path / "skill1").mkdir()
    data = {
        "set_id": "test-set",
        "members": [
            {"source_id": "src1", "date": "2026-01-01", "skill_path": "skill1"},
            {"source_id": "src2", "date": "2026-01-01", "skill_path": "skill1"}
        ]
    }
    manifest_path = create_manifest(tmp_path, data)
    errs = validate_manifest(manifest_path)
    assert any("share date '2026-01-01'" in e for e in errs)
    assert any("lack a 'sequence'" in e for e in errs)

def test_tied_dates_with_sequence(tmp_path):
    (tmp_path / "skill1").mkdir()
    data = {
        "set_id": "test-set",
        "members": [
            {"source_id": "src1", "date": "2026-01-01", "skill_path": "skill1", "sequence": 1},
            {"source_id": "src2", "date": "2026-01-01", "skill_path": "skill1", "sequence": 2}
        ]
    }
    manifest_path = create_manifest(tmp_path, data)
    errs = validate_manifest(manifest_path)
    assert not errs, f"Expected valid manifest with sequences, got errors: {errs}"

def test_missing_skill_path_dir(tmp_path):
    data = {
        "set_id": "test-set",
        "members": [
            {"source_id": "src1", "date": "2026-01-01", "skill_path": "doesnt_exist"}
        ]
    }
    manifest_path = create_manifest(tmp_path, data)
    errs = validate_manifest(manifest_path)
    assert any("not a valid directory relative to the manifest" in e for e in errs)
