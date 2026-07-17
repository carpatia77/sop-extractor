import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from merge_architecture_audit import (
    split_into_sections,
    merge_front_matter,
    merge_architecture_files,
    write_merged_architecture,
)
from validate_architecture_audit import run_validation, split_front_matter

VID1 = """---
intent: reverse-engineering
approved_by: jaro
analyst_lens: quantitative-trading-systems-architect
system: SG (ASG)
---

## Frontend observations

- [OBSERVED O1 src1/00:03:48] The panel shows two regions.
- [OBSERVED O2 src1/00:09:56] Regions mark smart money levels.

## Inferred backend

- [INFERRED I1 ← O1, O2] The engine clusters book depth by level.

## Confidence & gaps

Nothing here reveals the exact formula.
"""

VID2 = """---
intent: reverse-engineering
approved_by: jaro
analyst_lens: trading-systems-architect
system: SG (ASG)
---

## Frontend observations

- [OBSERVED O1 src2/00:05:09] A market-makers signal is shown separately.
- [OBSERVED O2 src2/00:09:58] The book is processed 1600 times a second.

## Inferred backend

- [INFERRED I1 ← O1, O2] Market-makers signal derives from book-read speed.

## Confidence & gaps

The percentage formula stays a black box.
"""


def _write(tmp_path, name, content):
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return str(f)


def test_split_into_sections_groups_by_heading():
    sections = split_into_sections(
        "## A\nline1\nline2\n\n## B\nline3\n"
    )
    headings = [h for h, _ in sections]
    assert headings == ["A", "B"]
    assert sections[0][1] == ["line1", "line2", ""]


def test_merge_front_matter_keeps_first_lens_and_flags_variants():
    fm1 = {"intent": "reverse-engineering", "approved_by": "jaro", "analyst_lens": "lens-a", "system": "SG"}
    fm2 = {"intent": "reverse-engineering", "approved_by": "jaro", "analyst_lens": "lens-b", "system": "SG"}
    merged = merge_front_matter([fm1, fm2])
    assert merged["analyst_lens"] == "lens-a"
    assert merged["analyst_lens_variants"] == "lens-b"
    assert merged["system"] == "SG"
    assert "system_variants" not in merged


def test_merge_front_matter_unions_distinct_approvers():
    fm1 = {"intent": "reverse-engineering", "approved_by": "jaro", "analyst_lens": "x", "system": "SG"}
    fm2 = {"intent": "reverse-engineering", "approved_by": "another-op", "analyst_lens": "x", "system": "SG"}
    merged = merge_front_matter([fm1, fm2])
    assert merged["approved_by"] == "jaro; another-op"


def test_merge_architecture_files_renumbers_continuously(tmp_path):
    p1 = _write(tmp_path, "vid1_architecture.md", VID1)
    p2 = _write(tmp_path, "vid2_architecture.md", VID2)
    front, body = merge_architecture_files([p1, p2])

    # vid1's O1/O2 stay O1/O2; vid2's O1/O2 must become O3/O4 (continuous).
    assert "[OBSERVED O1 src1/00:03:48]" in body
    assert "[OBSERVED O2 src1/00:09:56]" in body
    assert "[OBSERVED O3 src2/00:05:09]" in body
    assert "[OBSERVED O4 src2/00:09:58]" in body

    # vid1's I1 stays I1; vid2's I1 becomes I2, citing the REWRITTEN O3/O4.
    assert "[INFERRED I1 ← O1, O2]" in body
    assert "[INFERRED I2 ← O3, O4]" in body


def test_merge_architecture_files_groups_sections_not_interleaved(tmp_path):
    p1 = _write(tmp_path, "vid1_architecture.md", VID1)
    p2 = _write(tmp_path, "vid2_architecture.md", VID2)
    _, body = merge_architecture_files([p1, p2])
    obs_idx = body.index("Frontend Observations")
    inf_idx = body.index("Inferred Backend")
    assert obs_idx < inf_idx
    # all four OBSERVED lines must appear before the Inferred Backend heading
    assert body.index("O4 src2") < inf_idx


def test_merge_architecture_files_preserves_per_source_prose(tmp_path):
    p1 = _write(tmp_path, "vid1_architecture.md", VID1)
    p2 = _write(tmp_path, "vid2_architecture.md", VID2)
    _, body = merge_architecture_files([p1, p2])
    assert "Nothing here reveals the exact formula." in body
    assert "black box" in body
    assert "vid1_architecture.md" in body
    assert "vid2_architecture.md" in body


def test_write_merged_architecture_passes_gates(tmp_path):
    p1 = _write(tmp_path, "vid1_architecture.md", VID1)
    p2 = _write(tmp_path, "vid2_architecture.md", VID2)
    out_path = str(tmp_path / "merged_architecture.md")
    code = write_merged_architecture([p1, p2], out_path)
    assert code == 0
    assert os.path.isfile(out_path)

    # The merged file must also pass the real validator standalone.
    assert run_validation(out_path) == 0


def test_write_merged_architecture_reports_lens_variant_warning(tmp_path, capsys):
    p1 = _write(tmp_path, "vid1_architecture.md", VID1)
    p2 = _write(tmp_path, "vid2_architecture.md", VID2)
    out_path = str(tmp_path / "merged_architecture.md")
    write_merged_architecture([p1, p2], out_path)
    out = capsys.readouterr().out
    assert "disagreed on analyst_lens" in out


def test_write_merged_architecture_fails_gate_on_dangling_reference(tmp_path):
    broken = VID2.replace("[INFERRED I1 ← O1, O2]", "[INFERRED I1 ← O99]")
    p1 = _write(tmp_path, "vid1_architecture.md", VID1)
    p2 = _write(tmp_path, "vid2_broken.md", broken)
    out_path = str(tmp_path / "merged.md")
    code = write_merged_architecture([p1, p2], out_path)
    assert code == 1


def test_merge_respects_approved_by_override(tmp_path):
    p1 = _write(tmp_path, "vid1_architecture.md", VID1)
    p2 = _write(tmp_path, "vid2_architecture.md", VID2)
    front, _ = merge_architecture_files([p1, p2], approved_by="reviewer-x")
    assert front["approved_by"] == "reviewer-x"


def test_split_front_matter_of_merged_output_is_well_formed(tmp_path):
    p1 = _write(tmp_path, "vid1_architecture.md", VID1)
    p2 = _write(tmp_path, "vid2_architecture.md", VID2)
    _, merged_text = merge_architecture_files([p1, p2])
    front, body = split_front_matter(merged_text)
    assert front["intent"] == "reverse-engineering"
    assert front["approved_by"] == "jaro"
