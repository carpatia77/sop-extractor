import os
import json
import tempfile
import pytest
from scripts.validate_evolution_audit import run_validation

def setup_mock_set(tmpdir):
    # Create skills
    skill1 = os.path.join(tmpdir, "mom")
    os.makedirs(skill1)
    with open(os.path.join(skill1, "first_principles.md"), "w", encoding="utf-8") as f:
        f.write("Range is 10 percent.\n")
        
    skill2 = os.path.join(tmpdir, "mip")
    os.makedirs(skill2)
    with open(os.path.join(skill2, "first_principles.md"), "w", encoding="utf-8") as f:
        f.write("Range is bounded by balance. It changes.\nExplicitly supersedes old range.\n")
        
    # Create manifest
    manifest = {
        "set_id": "test-set",
        "members": [
            {"source_id": "mom", "date": "1990-01-01", "role": "book", "skill_path": "mom"},
            {"source_id": "mip", "date": "2007-01-01", "role": "book", "skill_path": "mip"}
        ]
    }
    with open(os.path.join(tmpdir, "set_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)
        
    # Create valid current
    with open(os.path.join(tmpdir, "set_current.md"), "w", encoding="utf-8") as f:
        f.write("- **Range** — bounded. `[mip/2007-01-01]`\n")

def setup_mock_set_tied_dates(tmpdir, seq_a=None, seq_b=None):
    """Two sources sharing the same date (e.g. two 2025 courses), as
    exercised by the sequence tie-breaker tests."""
    skill_a = os.path.join(tmpdir, "course_a")
    os.makedirs(skill_a)
    with open(os.path.join(skill_a, "first_principles.md"), "w", encoding="utf-8") as f:
        f.write("Range is 10 percent.\n")

    skill_b = os.path.join(tmpdir, "course_b")
    os.makedirs(skill_b)
    with open(os.path.join(skill_b, "first_principles.md"), "w", encoding="utf-8") as f:
        f.write("Range is bounded by balance. It changes.\nExplicitly supersedes old range.\n")

    member_a = {"source_id": "course_a", "date": "2025-01-01", "role": "live_training", "skill_path": "course_a"}
    member_b = {"source_id": "course_b", "date": "2025-01-01", "role": "live_training", "skill_path": "course_b"}
    if seq_a is not None:
        member_a["sequence"] = seq_a
    if seq_b is not None:
        member_b["sequence"] = seq_b

    manifest = {"set_id": "test-set-tied", "members": [member_a, member_b]}
    with open(os.path.join(tmpdir, "set_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    with open(os.path.join(tmpdir, "set_current.md"), "w", encoding="utf-8") as f:
        f.write("- **Range** — bounded. `[course_b/2025-01-01]`\n")

def test_1_refined_valid_chronology():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set(tmpdir)
        with open(os.path.join(tmpdir, "set_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| mom | 1990-01-01 | book | introduced | Range is 10 percent |
| mip | 2007-01-01 | book | refined | Range is bounded by balance |
""")
        assert run_validation(tmpdir) == 0

def test_2_superseded_chronology_inversion():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set(tmpdir)
        with open(os.path.join(tmpdir, "set_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| mip | 2007-01-01 | book | introduced | Range is bounded by balance |
| mom | 1990-01-01 | book | superseded | Range is 10 percent |
""")
        # Hard fail because mom (1990) supersedes mip (2007)
        assert run_validation(tmpdir) == 1

def test_3_silence_gate():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set(tmpdir)
        with open(os.path.join(tmpdir, "set_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| mom | 1990-01-01 | book | introduced | Range is 10 percent |
| mip | 2007-01-01 | book | superseded | concept is missing |
""")
        # Hard fail because superseded by silence
        assert run_validation(tmpdir) == 1
        
def test_4_dropped_high_confidence():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set(tmpdir)
        with open(os.path.join(tmpdir, "set_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| mom | 1990-01-01 | book | introduced | Range is 10 percent |
| mip | 2007-01-01 | book | dropped? | High confidence that it was removed |
""")
        assert run_validation(tmpdir) == 1

def test_5_unverified_claim():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set(tmpdir)
        with open(os.path.join(tmpdir, "set_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| mom | 1990-01-01 | book | introduced | Range is 10 percent |
| mip | 2007-01-01 | book | refined | Completely fabricated claim not in source |
""")
        # >30% unverified
        assert run_validation(tmpdir) == 1

def test_6_reaffirmed_valid():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set(tmpdir)
        with open(os.path.join(tmpdir, "mip", "first_principles.md"), "a", encoding="utf-8") as f:
            f.write("Range is 10 percent.\n")
            
        with open(os.path.join(tmpdir, "set_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| mom | 1990-01-01 | book | introduced | Range is 10 percent |
| mip | 2007-01-01 | book | reaffirmed | Range is 10 percent |
""")
        assert run_validation(tmpdir) == 0

def test_7_current_md_missing_tag():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set(tmpdir)
        with open(os.path.join(tmpdir, "set_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| mom | 1990-01-01 | book | introduced | Range is 10 percent |
""")
        with open(os.path.join(tmpdir, "set_current.md"), "w", encoding="utf-8") as f:
            f.write("- **Range** — bounded. (no tag here)\n")
            
        assert run_validation(tmpdir) == 1

def test_8_import_reuse():
    import scripts.validate_evolution_audit as vea
    import scripts.validate_coherence_audit as vca
    assert vea.jaccard is vca.jaccard

def test_generic_author_name():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set(tmpdir)
        with open(os.path.join(tmpdir, "tversky_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| mom | 1990-01-01 | book | introduced | Range is 10 percent |
| mip | 2007-01-01 | book | refined | Range is bounded by balance |
""")
        with open(os.path.join(tmpdir, "tversky_current.md"), "w", encoding="utf-8") as f:
            f.write("- **Range** — bounded. `[mip/2007-01-01]`\n")
        
        # Remove set_current.md created by setup_mock_set
        os.remove(os.path.join(tmpdir, "set_current.md"))
        
        assert run_validation(tmpdir) == 0

def test_no_evolution_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set(tmpdir)
        assert run_validation(tmpdir) == 1

def test_multiple_evolution_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set(tmpdir)
        with open(os.path.join(tmpdir, "a_evolution.md"), "w") as f: f.write("")
        with open(os.path.join(tmpdir, "b_evolution.md"), "w") as f: f.write("")
        assert run_validation(tmpdir) == 1

def test_tied_dates_without_sequence_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set_tied_dates(tmpdir)  # no sequence on either
        with open(os.path.join(tmpdir, "set_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| course_a | 2025-01-01 | live_training | introduced | Range is 10 percent |
| course_b | 2025-01-01 | live_training | refined | Range is bounded by balance |
""")
        assert run_validation(tmpdir) == 1

def test_tied_dates_with_valid_sequence_passes():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set_tied_dates(tmpdir, seq_a=1, seq_b=2)
        with open(os.path.join(tmpdir, "set_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| course_a | 2025-01-01 | live_training | introduced | Range is 10 percent |
| course_b | 2025-01-01 | live_training | refined | Range is bounded by balance |
""")
        assert run_validation(tmpdir) == 0

def test_tied_dates_with_inverted_sequence_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set_tied_dates(tmpdir, seq_a=2, seq_b=1)  # course_b sequenced BEFORE course_a
        with open(os.path.join(tmpdir, "set_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| course_a | 2025-01-01 | live_training | introduced | Range is 10 percent |
| course_b | 2025-01-01 | live_training | refined | Range is bounded by balance |
""")
        assert run_validation(tmpdir) == 1

def test_tied_dates_with_sequence_on_only_one_side_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_mock_set_tied_dates(tmpdir, seq_a=1, seq_b=None)
        with open(os.path.join(tmpdir, "set_evolution.md"), "w", encoding="utf-8") as f:
            f.write("""
## Range
| Fonte | Data | Papel | Tratamento | O que mudou |
|---|---|---|---|---|
| course_a | 2025-01-01 | live_training | introduced | Range is 10 percent |
| course_b | 2025-01-01 | live_training | refined | Range is bounded by balance |
""")
        assert run_validation(tmpdir) == 1
