import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from render_skill_viewer import (
    markdown_lite_to_html,
    extract_headings,
    discover_skill_files,
    render_skill_viewer,
    write_skill_viewer,
    _slugify,
)


def _build_synthetic_skill(tmp_path):
    skill_dir = tmp_path / "asg"
    (skill_dir / "chapters").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# ASG Skill\n\n## First Principles\n- The market is driven by order flow.\n\n"
        "## SOPs\n- Watch the smart money region.\n", encoding="utf-8")
    (skill_dir / "chapters" / "mod01-intro.md").write_text(
        "## Module 1\nSome content here.\n", encoding="utf-8")
    (skill_dir / "asg_architecture.md").write_text(
        "---\nintent: reverse-engineering\n---\n\n## Frontend observations\n"
        "- [OBSERVED O1 src1/00:03:48] The panel shows two regions.\n"
        "- [INFERRED I1 ← O1] The engine likely clusters book depth.\n",
        encoding="utf-8")
    (skill_dir / "determinism_score.json").write_text(
        json.dumps({"book_determinism_pct": 0.333}), encoding="utf-8")
    return skill_dir


def test_markdown_lite_renders_headings_and_lists():
    text = "# Title\n\n## Sub\n- item one\n- item two\n"
    out = markdown_lite_to_html(text)
    assert '<h1 id="title">Title</h1>' in out
    assert '<h2 id="sub">Sub</h2>' in out
    assert "<li>item one</li>" in out
    assert "<li>item two</li>" in out


def test_markdown_lite_wraps_observed_and_inferred_seals():
    text = "- [OBSERVED O1 src1/00:01:00] Something shown on screen.\n"
    out = markdown_lite_to_html(text)
    assert 'class="badge badge-observed"' in out
    text2 = "- [INFERRED I1 ← O1] Something hypothesized.\n"
    out2 = markdown_lite_to_html(text2)
    assert 'class="badge badge-inferred"' in out2


def test_markdown_lite_wraps_generic_provenance_tag():
    text = "A claim here [src1/2020-01-01] with a citation.\n"
    out = markdown_lite_to_html(text)
    assert 'class="badge badge-prov"' in out


def test_markdown_lite_escapes_html_in_source():
    text = "This has a <script>alert(1)</script> tag.\n"
    out = markdown_lite_to_html(text)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_extract_headings_respects_max_level():
    text = "# H1\n## H2\n### H3 (excluded)\n"
    headings = extract_headings(text, max_level=2)
    titles = [t for _, t, _ in headings]
    assert "H1" in titles
    assert "H2" in titles
    assert "H3 (excluded)" not in titles


def test_discover_skill_files_finds_all_artifacts(tmp_path):
    skill_dir = _build_synthetic_skill(tmp_path)
    files = discover_skill_files(str(skill_dir))
    assert files["skill_md"] is not None
    assert len(files["chapters"]) == 1
    assert len(files["architecture"]) == 1
    assert files["determinism"]["book_determinism_pct"] == 0.333


def test_discover_skill_files_missing_optional_files_is_not_an_error(tmp_path):
    skill_dir = tmp_path / "minimal"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Minimal\n", encoding="utf-8")
    files = discover_skill_files(str(skill_dir))
    assert files["skill_md"] is not None
    assert files["chapters"] == []
    assert files["architecture"] == []
    assert files["determinism"] is None


def test_render_skill_viewer_includes_nav_and_both_badge_classes(tmp_path):
    skill_dir = _build_synthetic_skill(tmp_path)
    out = render_skill_viewer(str(skill_dir))
    assert "mod01-intro.md" in out
    assert "asg_architecture.md" in out
    assert "badge-observed" in out
    assert "badge-inferred" in out
    assert "33.3% SOP-backed" in out


def test_render_skill_viewer_without_architecture_doc_has_no_re_nav(tmp_path):
    skill_dir = tmp_path / "no_re"
    (skill_dir / "chapters").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Plain Skill\n", encoding="utf-8")
    out = render_skill_viewer(str(skill_dir))
    assert "Reverse-Engineering" not in out
    assert '<span class="badge badge-observed"' not in out


def test_write_skill_viewer_writes_single_html_file(tmp_path):
    skill_dir = _build_synthetic_skill(tmp_path)
    out_path = write_skill_viewer(str(skill_dir))
    assert os.path.isfile(out_path)
    with open(out_path, encoding="utf-8") as f:
        content = f.read()
    assert content.startswith("<!doctype html>")
    assert "badge-observed" in content


def test_slugify_produces_url_safe_ids():
    assert _slugify("First Principles!") == "first-principles"
    assert _slugify("Módulo 01") != ""
