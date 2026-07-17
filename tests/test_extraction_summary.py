import os

from extraction_summary import compute_summary, _course_stats


def _build_course(base, name, srt_text, md_text):
    course_dir = base / name
    (course_dir / "transcripts").mkdir(parents=True)
    (course_dir / "transcripts" / "part1.srt").write_text(srt_text, encoding="utf-8")
    (course_dir / "SKILL.md").write_text(md_text, encoding="utf-8")
    return course_dir


SRT_SAMPLE = (
    "1\n00:00:00,000 --> 00:00:02,000\nHello world this is a test\n\n"
    "2\n00:01:30,000 --> 00:01:32,000\nSecond line of dialogue here\n"
)


def test_course_stats_returns_none_without_transcripts(tmp_path):
    course_dir = tmp_path / "no_transcripts"
    course_dir.mkdir()
    assert _course_stats(str(course_dir)) is None


def test_course_stats_computes_duration_from_last_timestamp(tmp_path):
    course_dir = _build_course(tmp_path, "course1", SRT_SAMPLE, "# Skill\nsome content here\n")
    stats = _course_stats(str(course_dir))
    assert stats is not None
    # The regex matches the first timestamp on the last matching line, i.e. the
    # *start* of the last cue (00:01:30) -> 90 seconds -> 0.025 hours.
    assert abs(stats["hours"] - (90 / 3600)) < 1e-9
    assert stats["course_name"] == "course1"


def test_course_stats_counts_input_and_output_words(tmp_path):
    course_dir = _build_course(tmp_path, "course1", SRT_SAMPLE, "one two three four five\n")
    stats = _course_stats(str(course_dir))
    assert stats["output_words"] == 5
    assert stats["input_words"] > 0
    assert stats["input_tokens"] == int(stats["input_words"] * 1.33)


def test_course_stats_includes_chapters_and_all_known_md_files(tmp_path):
    course_dir = _build_course(tmp_path, "course1", SRT_SAMPLE, "skill words here\n")
    (course_dir / "chapters").mkdir()
    (course_dir / "chapters" / "ch01.md").write_text("chapter one two three\n", encoding="utf-8")
    (course_dir / "sops.md").write_text("sop one two\n", encoding="utf-8")
    stats = _course_stats(str(course_dir))
    # skill(3) + chapter(4) + sops(3) = 10 words
    assert stats["output_words"] == 10


def test_compute_summary_aggregates_multiple_courses(tmp_path):
    _build_course(tmp_path, "course1", SRT_SAMPLE, "alpha beta gamma\n")
    _build_course(tmp_path, "course2", SRT_SAMPLE, "delta epsilon\n")
    summary = compute_summary(os.path.join(str(tmp_path), "*/"))
    assert len(summary["courses"]) == 2
    names = {c["course_name"] for c in summary["courses"]}
    assert names == {"course1", "course2"}
    assert summary["total_output_words"] == 3 + 2
    assert summary["grand_total_tokens"] > 0


def test_compute_summary_skips_directories_without_transcripts(tmp_path):
    _build_course(tmp_path, "course1", SRT_SAMPLE, "alpha\n")
    (tmp_path / "not_a_course").mkdir()
    summary = compute_summary(os.path.join(str(tmp_path), "*/"))
    assert len(summary["courses"]) == 1
    assert summary["courses"][0]["course_name"] == "course1"


def test_compute_summary_empty_glob_returns_zero_totals(tmp_path):
    summary = compute_summary(os.path.join(str(tmp_path), "*/"))
    assert summary["courses"] == []
    assert summary["total_hours"] == 0
    assert summary["grand_total_tokens"] == 0
