import json

from validate_run_report import check_run_report, run_validation, ALWAYS_REQUIRED_STEPS


def _complete_report(skip_step=None, skip_reason="valid reason"):
    steps = {}
    for step_id in ALWAYS_REQUIRED_STEPS:
        if step_id == skip_step:
            steps[step_id] = {"status": "skipped", "reason": skip_reason}
        else:
            steps[step_id] = {"status": "ran"}
    if skip_step == "7.5":
        steps["7.5"] = {"status": "skipped", "reason": skip_reason}
    return {"steps": steps}


def test_complete_report_passes():
    ok, errors = check_run_report(_complete_report())
    assert ok
    assert errors == []


def test_missing_step_fails():
    report = _complete_report()
    del report["steps"]["7"]
    ok, errors = check_run_report(report)
    assert not ok
    assert any("'7'" in e for e in errors)


def test_skipped_step_with_reason_passes():
    report = _complete_report(skip_step="7", skip_reason="video file not provided, per SKILL.md Step 7.5 precondition")
    ok, errors = check_run_report(report)
    assert ok


def test_skipped_step_without_reason_fails():
    """Regression test for the real incident: a step skipped citing a
    fabricated cost ('1.6GB') with no reason recorded is exactly what this
    gate exists to catch — an empty/missing reason must fail."""
    report = _complete_report(skip_step="7.5", skip_reason="")
    ok, errors = check_run_report(report)
    assert not ok
    assert any("7.5" in e and "reason" in e for e in errors)


def test_optional_step_7_5_not_required_when_absent():
    report = _complete_report()
    assert "7.5" not in report["steps"]
    ok, errors = check_run_report(report)
    assert ok  # 7.5 is optional, its absence is not an error


def test_invalid_status_value_fails():
    report = _complete_report()
    report["steps"]["3"] = {"status": "maybe"}
    ok, errors = check_run_report(report)
    assert not ok
    assert any("'3'" in e for e in errors)


def test_steps_not_a_dict_fails():
    ok, errors = check_run_report({"steps": "not a dict"})
    assert not ok


def test_missing_steps_key_fails():
    ok, errors = check_run_report({})
    assert not ok


def test_run_validation_missing_file(tmp_path):
    assert run_validation(str(tmp_path)) == 1


def test_run_validation_complete_report_passes(tmp_path):
    report = _complete_report()
    with open(tmp_path / "run_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f)
    assert run_validation(str(tmp_path)) == 0


def test_run_validation_incomplete_report_fails(tmp_path):
    report = _complete_report(skip_step="9", skip_reason="")
    with open(tmp_path / "run_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f)
    assert run_validation(str(tmp_path)) == 1


def test_run_validation_malformed_json_fails(tmp_path):
    with open(tmp_path / "run_report.json", "w", encoding="utf-8") as f:
        f.write("{not valid json")
    assert run_validation(str(tmp_path)) == 1
