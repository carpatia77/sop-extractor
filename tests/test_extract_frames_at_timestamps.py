import pytest
from scripts.extract_frames_at_timestamps import (
    parse_timestamp,
    find_gap_timestamps,
    dedupe_timestamps,
    build_ffmpeg_command,
    extract_frames,
    merge_manifest,
    DEFAULT_MARKERS,
)

def test_parse_timestamp_hms_comma():
    assert parse_timestamp("00:01:23,456") == pytest.approx(83.456)

def test_parse_timestamp_hms_dot():
    assert parse_timestamp("01:02:03.500") == pytest.approx(3723.5)

def test_parse_timestamp_ms_only():
    assert parse_timestamp("02:30") == pytest.approx(150.0)

def test_find_gap_timestamps_srt_arrow():
    transcript = """1
00:00:10,000 --> 00:00:13,000
So the value area builds up here.

2
00:00:15,000 --> 00:00:18,000
Look at this — see how the b-formation forms right there.

3
00:00:20,000 --> 00:00:23,000
Nothing visual to flag in this line.
"""
    hits = find_gap_timestamps(transcript)
    assert len(hits) == 1
    assert hits[0]["timestamp_seconds"] == pytest.approx(15.0)
    assert "look at this" in hits[0]["matched_markers"]

def test_find_gap_timestamps_bracket_format():
    transcript = """[00:05:00] The range extends beyond the initial balance.
[00:05:20] Olha aqui, vê como o perfil forma esse b.
[00:05:40] Regular commentary continues.
"""
    hits = find_gap_timestamps(transcript)
    assert len(hits) == 1
    assert hits[0]["timestamp_seconds"] == pytest.approx(320.0)

def test_find_gap_timestamps_custom_markers():
    transcript = "[00:01:00] This is a custom trigger phrase in the text.\n"
    hits = find_gap_timestamps(transcript, markers=["custom trigger phrase"])
    assert len(hits) == 1
    hits_none = find_gap_timestamps(transcript, markers=["not present"])
    assert len(hits_none) == 0

def test_find_gap_timestamps_no_timestamp_before_match_is_skipped():
    transcript = "Look at this before any timestamp appears.\n[00:00:05] plain line\n"
    hits = find_gap_timestamps(transcript)
    assert hits == []

def test_dedupe_timestamps_merges_close_hits():
    hits = [
        {"timestamp_seconds": 10.0, "matched_markers": ["a"], "context": "x"},
        {"timestamp_seconds": 11.0, "matched_markers": ["b"], "context": "y"},
        {"timestamp_seconds": 20.0, "matched_markers": ["c"], "context": "z"},
    ]
    deduped = dedupe_timestamps(hits, min_gap_seconds=3.0)
    assert [h["timestamp_seconds"] for h in deduped] == [10.0, 20.0]

def test_dedupe_timestamps_keeps_far_apart_hits():
    hits = [
        {"timestamp_seconds": 0.0, "matched_markers": [], "context": ""},
        {"timestamp_seconds": 5.0, "matched_markers": [], "context": ""},
    ]
    deduped = dedupe_timestamps(hits, min_gap_seconds=3.0)
    assert len(deduped) == 2

def test_dedupe_timestamps_empty():
    assert dedupe_timestamps([]) == []

def test_build_ffmpeg_command_is_pure_and_correct():
    cmd = build_ffmpeg_command("course.mp4", 83.456, "out/frame.jpg", width=512)
    assert cmd[0] == "ffmpeg"
    assert "-ss" in cmd and cmd[cmd.index("-ss") + 1] == "83.456"
    assert "-i" in cmd and cmd[cmd.index("-i") + 1] == "course.mp4"
    assert "out/frame.jpg" in cmd
    assert "scale=512:-1" in cmd

def test_extract_frames_dry_run_does_not_call_subprocess(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("subprocess.run should not be called in dry_run mode")
    monkeypatch.setattr("scripts.extract_frames_at_timestamps.subprocess.run", _boom)

    hits = [{"timestamp_seconds": 12.5, "matched_markers": ["look at this"], "context": "look at this"}]
    manifest = extract_frames("course.mp4", hits, "frames", dry_run=True)
    assert len(manifest) == 1
    assert manifest[0]["timestamp_seconds"] == 12.5
    assert "frame_00h00m12.50s.jpg" in manifest[0]["output_path"]

def test_extract_frames_invokes_ffmpeg_per_hit(monkeypatch, tmp_path):
    calls = []
    def _fake_run(cmd, check, capture_output):
        calls.append(cmd)
    monkeypatch.setattr("scripts.extract_frames_at_timestamps.subprocess.run", _fake_run)

    hits = [
        {"timestamp_seconds": 10.0, "matched_markers": ["olha aqui"], "context": "olha aqui"},
        {"timestamp_seconds": 90.0, "matched_markers": ["see this"], "context": "see this"},
    ]
    manifest = extract_frames("course.mp4", hits, str(tmp_path), dry_run=False)
    assert len(calls) == 2
    assert len(manifest) == 2

def test_default_markers_cover_both_languages():
    assert any("look" in m for m in DEFAULT_MARKERS)
    assert any("olha" in m for m in DEFAULT_MARKERS)

def test_extract_frames_with_part_id_prefixes_filename(monkeypatch):
    monkeypatch.setattr("scripts.extract_frames_at_timestamps.subprocess.run", lambda *a, **kw: None)
    hits = [{"timestamp_seconds": 12.5, "matched_markers": ["look at this"], "context": "x"}]
    manifest = extract_frames("course_part1.mp4", hits, "frames", dry_run=False, part_id="part1")
    assert "frame_part1_00h00m12.50s.jpg" in manifest[0]["output_path"]
    assert manifest[0]["part_id"] == "part1"

def test_extract_frames_same_timestamp_different_parts_do_not_collide(monkeypatch):
    monkeypatch.setattr("scripts.extract_frames_at_timestamps.subprocess.run", lambda *a, **kw: None)
    hit = [{"timestamp_seconds": 300.0, "matched_markers": ["olha aqui"], "context": "x"}]
    manifest_1 = extract_frames("p1.mp4", hit, "frames", dry_run=False, part_id="part1")
    manifest_3 = extract_frames("p3.mp4", hit, "frames", dry_run=False, part_id="part3")
    assert manifest_1[0]["output_path"] != manifest_3[0]["output_path"]

def test_merge_manifest_accumulates_across_parts():
    part1_entries = [{"part_id": "part1", "timestamp_seconds": 10.0}]
    part2_entries = [{"part_id": "part2", "timestamp_seconds": 20.0}]
    merged_after_part1 = merge_manifest([], part1_entries, "part1")
    merged_after_part2 = merge_manifest(merged_after_part1, part2_entries, "part2")
    assert len(merged_after_part2) == 2
    assert {e["part_id"] for e in merged_after_part2} == {"part1", "part2"}

def test_merge_manifest_rerun_replaces_same_part_only():
    existing = [
        {"part_id": "part1", "timestamp_seconds": 10.0},
        {"part_id": "part2", "timestamp_seconds": 20.0},
    ]
    new_part1_entries = [{"part_id": "part1", "timestamp_seconds": 11.0}]
    merged = merge_manifest(existing, new_part1_entries, "part1")
    assert len(merged) == 2
    part1 = [e for e in merged if e["part_id"] == "part1"]
    assert len(part1) == 1 and part1[0]["timestamp_seconds"] == 11.0
    part2 = [e for e in merged if e["part_id"] == "part2"]
    assert len(part2) == 1 and part2[0]["timestamp_seconds"] == 20.0

def test_merge_manifest_no_part_id_behaves_like_single_course():
    existing = [{"part_id": None, "timestamp_seconds": 5.0}]
    new_entries = [{"part_id": None, "timestamp_seconds": 6.0}]
    merged = merge_manifest(existing, new_entries, part_id="")
    assert len(merged) == 1
    assert merged[0]["timestamp_seconds"] == 6.0
