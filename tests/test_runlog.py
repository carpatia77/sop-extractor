import json
import pytest
from scripts._runlog import append_run, tail_log

def test_append_run(tmp_path):
    log_path = tmp_path / "runs.jsonl"
    record1 = {"ts": "2026-07-04T12:00:00Z", "set": "set-1", "evolution": "pass"}
    record2 = {"ts": "2026-07-04T13:00:00Z", "set": "set-2", "evolution": "fail"}
    
    append_run(record1, str(log_path))
    append_run(record2, str(log_path))
    
    lines = log_path.read_text('utf-8').strip().split('\n')
    assert len(lines) == 2
    
    data1 = json.loads(lines[0])
    assert data1["set"] == "set-1"
    assert data1["evolution"] == "pass"

def test_tail_log_no_alerts(tmp_path, capsys):
    log_path = tmp_path / "runs.jsonl"
    
    # Run 1: det 0.5, unv 0.1
    r1 = {
        "ts": "t1", "set": "setA", "unverified_claims_pct": 0.1,
        "per_skill": {"sk1": {"determinism_pct": 0.5}}
    }
    # Run 2: det 0.5, unv 0.1 (stable)
    r2 = {
        "ts": "t2", "set": "setA", "unverified_claims_pct": 0.1,
        "per_skill": {"sk1": {"determinism_pct": 0.5}}
    }
    append_run(r1, str(log_path))
    append_run(r2, str(log_path))
    
    tail_log(str(log_path), 10)
    captured = capsys.readouterr().out
    assert "✅ No regressions detected" in captured
    assert "⚠️  ALERT" not in captured

def test_tail_log_with_alerts(tmp_path, capsys):
    log_path = tmp_path / "runs.jsonl"
    
    # Run 1: det 0.9, unv 0.05
    r1 = {
        "ts": "t1", "set": "setA", "unverified_claims_pct": 0.05,
        "per_skill": {"sk1": {"determinism_pct": 0.9}}
    }
    # Run 2: det 0.5 (dropped >0.1), unv 0.20 (rose >0.1)
    r2 = {
        "ts": "t2", "set": "setA", "unverified_claims_pct": 0.20,
        "per_skill": {"sk1": {"determinism_pct": 0.5}}
    }
    append_run(r1, str(log_path))
    append_run(r2, str(log_path))
    
    tail_log(str(log_path), 10)
    captured = capsys.readouterr().out
    
    assert "⚠️  ALERT: setA evolution unverified claims rose by >10% (5.0% -> 20.0%)" in captured
    assert "⚠️  ALERT: Skill sk1 in setA determinism dropped by >10% (90.0% -> 50.0%)" in captured
    assert "✅ No regressions detected" not in captured
