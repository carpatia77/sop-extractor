#!/usr/bin/env python3
"""Extracts still frames from a video at timestamps where the transcript
contains a deictic reference ("look at this", "olha aqui") without enough
verbal content to stand alone. Targeted, not frame-by-frame — the transcript
already carries the SOP substance; this only fills visual gaps."""

import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_MARKERS = [
    # English
    "look at this", "look here", "look at that", "see how", "see this",
    "watch this", "right here", "you can see", "as you can see", "this here",
    # Portuguese
    "olha aqui", "olha isso", "olha só", "vê como", "vê aqui", "vê isso",
    "esse formato", "aqui ó", "repara", "repare",
]

# SRT/VTT arrow line: "00:01:23,456 --> 00:01:26,000" or with '.' instead of ','
_ARROW_RE = re.compile(
    r'(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2})\s*-->'
)
# Bracketed/parenthesized timestamp: "[00:12:34]", "(1:23)"
_BRACKET_RE = re.compile(r'[\[(](\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?)[\])]')


def parse_timestamp(raw: str) -> float:
    """Parses 'HH:MM:SS[.,mmm]' or 'MM:SS[.,mmm]' into seconds."""
    raw = raw.replace(",", ".")
    parts = raw.split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", parts[0], parts[1]
    else:
        raise ValueError(f"Unrecognized timestamp format: {raw!r}")
    return int(h) * 3600 + int(m) * 60 + float(s)


def find_gap_timestamps(transcript_text: str, markers=None) -> list:
    """Scans a transcript for lines matching `markers`, returning the
    timestamp most recently seen before each match. Supports SRT/VTT arrow
    lines and bracketed/parenthesized inline timestamps."""
    markers = [m.lower() for m in (markers or DEFAULT_MARKERS)]
    current_ts = None
    hits = []
    for line in transcript_text.splitlines():
        arrow_match = _ARROW_RE.search(line)
        bracket_match = _BRACKET_RE.search(line)
        if arrow_match:
            current_ts = parse_timestamp(arrow_match.group(1))
            continue
        if bracket_match:
            current_ts = parse_timestamp(bracket_match.group(1))
        stripped = line.strip()
        if not stripped or current_ts is None:
            continue
        lowered = stripped.lower()
        matched = [m for m in markers if m in lowered]
        if matched:
            hits.append({
                "timestamp_seconds": current_ts,
                "matched_markers": matched,
                "context": stripped,
            })
    return hits


def dedupe_timestamps(hits: list, min_gap_seconds: float = 3.0) -> list:
    """Merges hits closer than `min_gap_seconds` together, keeping the
    first of each cluster (avoids extracting near-identical frames for
    consecutive gap mentions in the same moment)."""
    if not hits:
        return []
    ordered = sorted(hits, key=lambda h: h["timestamp_seconds"])
    deduped = [ordered[0]]
    for hit in ordered[1:]:
        if hit["timestamp_seconds"] - deduped[-1]["timestamp_seconds"] >= min_gap_seconds:
            deduped.append(hit)
    return deduped


def build_ffmpeg_command(video_path: str, timestamp_seconds: float, output_path: str, width: int = 512) -> list:
    """Builds the ffmpeg argv for a single-frame extraction. Uses fast
    (input-side) seek: approximate by design — this locates a moment for
    visual reference, not a frame-accurate cut."""
    return [
        "ffmpeg", "-y",
        "-ss", f"{timestamp_seconds:.3f}",
        "-i", video_path,
        "-frames:v", "1",
        "-vf", f"scale={width}:-1",
        output_path,
    ]


def _safe_filename(timestamp_seconds: float, part_id: str = "") -> str:
    h = int(timestamp_seconds // 3600)
    m = int((timestamp_seconds % 3600) // 60)
    s = timestamp_seconds % 60
    prefix = f"{part_id}_" if part_id else ""
    return f"frame_{prefix}{h:02d}h{m:02d}m{s:05.2f}s.jpg"


def extract_frames(video_path: str, hits: list, output_dir: str, width: int = 512, dry_run: bool = False, part_id: str = "") -> list:
    """Runs ffmpeg for each hit. In dry-run mode, builds commands without
    executing them (for tuning markers/timestamps before spending time).
    `part_id` disambiguates frames across multi-part courses (same rough
    timestamp can recur in different videos) — pass e.g. 'part1'."""
    if not dry_run:
        os.makedirs(output_dir, exist_ok=True)
    manifest = []
    for hit in hits:
        filename = _safe_filename(hit["timestamp_seconds"], part_id=part_id)
        output_path = os.path.join(output_dir, filename)
        cmd = build_ffmpeg_command(video_path, hit["timestamp_seconds"], output_path, width=width)
        if not dry_run:
            subprocess.run(cmd, check=True, capture_output=True)
        manifest.append({
            "part_id": part_id or None,
            "timestamp_seconds": hit["timestamp_seconds"],
            "output_path": output_path,
            "matched_markers": hit["matched_markers"],
            "context": hit["context"],
        })
    return manifest


def _load_existing_manifest(manifest_path: str) -> list:
    if not os.path.exists(manifest_path):
        return []
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_manifest(existing: list, new_entries: list, part_id: str) -> list:
    """Merges new_entries into existing, replacing any prior entries for the
    same part_id (re-running one part, e.g. after tuning --min-gap, updates
    that part's frames without duplicating or touching other parts')."""
    kept = [e for e in existing if e.get("part_id") != (part_id or None)]
    return kept + new_entries


def main():
    parser = argparse.ArgumentParser(
        description="Extract frames at transcript timestamps flagged as visual-reference gaps."
    )
    parser.add_argument("transcript", help="Path to transcript file (SRT/VTT or bracketed-timestamp text)")
    parser.add_argument("--video", help="Path to the video file (required unless --dry-run)")
    parser.add_argument("--output-dir", default="frames", help="Directory to write extracted frames (default: ./frames)")
    parser.add_argument("--markers", help="Comma-separated custom marker list (overrides defaults)")
    parser.add_argument("--min-gap", type=float, default=3.0, help="Minimum seconds between extracted frames (default: 3.0)")
    parser.add_argument("--width", type=int, default=512, help="Output frame width in pixels (default: 512)")
    parser.add_argument("--part-id", default="", help="Identifier for multi-part courses (e.g. 'part1') — disambiguates frame filenames and manifest entries across parts sharing one --output-dir")
    parser.add_argument("--dry-run", action="store_true", help="List detected timestamps without running ffmpeg")
    args = parser.parse_args()

    if not args.dry_run and not args.video:
        print("Error: --video is required unless --dry-run is set")
        sys.exit(1)

    with open(args.transcript, "r", encoding="utf-8") as f:
        transcript_text = f.read()

    markers = args.markers.split(",") if args.markers else None
    hits = find_gap_timestamps(transcript_text, markers=markers)
    hits = dedupe_timestamps(hits, min_gap_seconds=args.min_gap)

    if args.dry_run:
        label = f" [{args.part_id}]" if args.part_id else ""
        print(f"{len(hits)} gap timestamp(s) detected{label}:")
        for hit in hits:
            print(f"  {hit['timestamp_seconds']:.1f}s — {hit['matched_markers']} — {hit['context'][:80]}")
        sys.exit(0)

    new_entries = extract_frames(args.video, hits, args.output_dir, width=args.width, dry_run=False, part_id=args.part_id)
    manifest_path = os.path.join(args.output_dir, "frames_manifest.json")
    manifest = merge_manifest(_load_existing_manifest(manifest_path), new_entries, args.part_id)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Extracted {len(new_entries)} frame(s) to {args.output_dir}/ (manifest now has {len(manifest)} total)")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
