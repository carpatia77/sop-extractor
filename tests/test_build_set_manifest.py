"""Tests for build_set_manifest.py — provenance loop."""
import json


from scripts.build_set_manifest import (
    build_manifest,
    date_from_metadata,
    infer_sequence,
    source_id_from_metadata,
    validate_manifest_data,
)


class TestSourceIdFromMetadata:
    def test_canonical_id_basic(self):
        meta = {"canonical_id": "mYDSSRS-B5U"}
        assert source_id_from_metadata(meta) == "mydssrs-b5u"

    def test_canonical_id_uppercase(self):
        meta = {"canonical_id": "ABC123"}
        assert source_id_from_metadata(meta) == "abc123"

    def test_canonical_id_with_underscores(self):
        meta = {"canonical_id": "vid_123_test"}
        assert source_id_from_metadata(meta) == "vid_123_test"

    def test_canonical_id_with_dashes(self):
        meta = {"canonical_id": "vid-123-test"}
        assert source_id_from_metadata(meta) == "vid-123-test"

    def test_canonical_id_special_chars(self):
        meta = {"canonical_id": "vid@123#test!"}
        assert source_id_from_metadata(meta) == "vid-123-test-"

    def test_fallback_to_title(self):
        meta = {"title": "My Video Title"}
        sid = source_id_from_metadata(meta)
        assert re.match(r"^[a-z0-9][a-z0-9_-]*$", sid)

    def test_fallback_to_unknown(self):
        meta = {}
        assert source_id_from_metadata(meta) == "unknown"

    def test_starts_with_alphanumeric(self):
        meta = {"canonical_id": "123abc"}
        assert source_id_from_metadata(meta) == "123abc"

    def test_no_leading_special_chars(self):
        meta = {"canonical_id": "-abc123"}
        sid = source_id_from_metadata(meta)
        assert sid.startswith("abc")


class TestDateFromMetadata:
    def test_valid_date(self):
        meta = {"upload_date": "2024-01-15"}
        assert date_from_metadata(meta) == "2024-01-15"

    def test_none_when_missing(self):
        meta = {}
        assert date_from_metadata(meta) is None

    def test_none_when_invalid_format(self):
        meta = {"upload_date": "15-01-2024"}
        assert date_from_metadata(meta) is None

    def test_none_when_partial(self):
        meta = {"upload_date": "2024-01"}
        assert date_from_metadata(meta) is None


class TestInferSequence:
    def test_chronological_order(self):
        members = [
            {"source_id": "b", "date": "2024-03-01"},
            {"source_id": "a", "date": "2024-01-01"},
        ]
        result = infer_sequence(members)
        assert result[0]["source_id"] == "a"
        assert result[0]["sequence"] == 1
        assert result[1]["source_id"] == "b"
        assert result[1]["sequence"] == 2

    def test_undated_get_no_sequence(self):
        members = [
            {"source_id": "a", "date": "2024-01-01"},
            {"source_id": "b"},  # no date
        ]
        result = infer_sequence(members)
        assert result[0]["sequence"] == 1
        assert result[1]["sequence"] is None

    def test_same_date_distinct_sequences(self):
        members = [
            {"source_id": "a", "date": "2024-01-01"},
            {"source_id": "b", "date": "2024-01-01"},
        ]
        result = infer_sequence(members)
        assert result[0]["sequence"] == 1
        assert result[1]["sequence"] == 2


class TestBuildManifest:
    def test_basic_build(self, tmp_path):
        # Create output dirs with metadata
        out1 = tmp_path / "vid1"
        out1.mkdir()
        (out1 / "metadata.json").write_text(json.dumps({
            "canonical_id": "VID001",
            "upload_date": "2024-01-15",
        }))

        out2 = tmp_path / "vid2"
        out2.mkdir()
        (out2 / "metadata.json").write_text(json.dumps({
            "canonical_id": "VID002",
            "upload_date": "2024-03-20",
        }))

        manifest = build_manifest(
            set_id="test-set",
            entries=[
                {"output_dir": str(out1)},
                {"output_dir": str(out2)},
            ],
        )

        assert manifest["set_id"] == "test-set"
        assert len(manifest["members"]) == 2
        assert manifest["members"][0]["source_id"] == "vid001"
        assert manifest["members"][0]["date"] == "2024-01-15"
        assert manifest["members"][0]["date_source"] == "ingested"
        assert manifest["members"][0]["sequence"] == 1

    def test_member_without_date(self, tmp_path):
        out1 = tmp_path / "book"
        out1.mkdir()
        (out1 / "metadata.json").write_text(json.dumps({
            "title": "My Book",
        }))

        manifest = build_manifest(
            set_id="test-set",
            entries=[{"output_dir": str(out1)}],
        )

        member = manifest["members"][0]
        assert member["date"] == ""
        assert member["date_source"] == "needs_date"
        assert member["needs_date"] is True

    def test_needs_date_fails_validation(self, tmp_path):
        out1 = tmp_path / "book"
        out1.mkdir()
        (out1 / "metadata.json").write_text(json.dumps({
            "title": "My Book",
        }))

        manifest = build_manifest(
            set_id="test-set",
            entries=[{"output_dir": str(out1)}],
        )

        # Real validator rejects empty dates — fail-fast as per plan
        errors = validate_manifest_data(manifest)
        assert len(errors) > 0
        assert any("date" in e.lower() for e in errors)

    def test_merge_preserves_manual_dates(self, tmp_path):
        out1 = tmp_path / "vid1"
        out1.mkdir()
        (out1 / "metadata.json").write_text(json.dumps({
            "canonical_id": "VID001",
            "upload_date": "2024-01-15",
        }))

        existing = {
            "set_id": "test-set",
            "members": [
                {
                    "source_id": "vid001",
                    "date": "2024-06-01",  # manually corrected
                    "date_source": "manual",
                    "skill_path": "../skills/vid001",
                }
            ],
        }

        manifest = build_manifest(
            set_id="test-set",
            entries=[{"output_dir": str(out1)}],
            existing_manifest=existing,
        )

        # Manual date should be preserved
        assert manifest["members"][0]["date"] == "2024-06-01"
        assert manifest["members"][0]["date_source"] == "manual"

    def test_idempotent_rerun(self, tmp_path):
        out1 = tmp_path / "vid1"
        out1.mkdir()
        (out1 / "metadata.json").write_text(json.dumps({
            "canonical_id": "VID001",
            "upload_date": "2024-01-15",
        }))

        # First build
        manifest1 = build_manifest(
            set_id="test-set",
            entries=[{"output_dir": str(out1)}],
        )

        # Simulate manual correction
        manifest1["members"][0]["date"] = "2024-06-01"
        manifest1["members"][0]["date_source"] = "manual"

        # Second build with existing manifest
        manifest2 = build_manifest(
            set_id="test-set",
            entries=[{"output_dir": str(out1)}],
            existing_manifest=manifest1,
        )

        # Manual date should be preserved
        assert manifest2["members"][0]["date"] == "2024-06-01"
        assert manifest2["members"][0]["date_source"] == "manual"


class TestValidateManifestData:
    def test_valid_manifest(self, tmp_path):
        # Create skill directory for validation
        skill_dir = tmp_path / "skills" / "vid001"
        skill_dir.mkdir(parents=True)

        manifest = {
            "set_id": "test",
            "members": [
                {
                    "source_id": "vid001",
                    "date": "2024-01-15",
                    "skill_path": "skills/vid001",  # relative to manifest dir
                }
            ],
        }
        # Write manifest to tmp_path so relative paths resolve correctly
        manifest_path = tmp_path / "set_manifest.json"
        errors = validate_manifest_data(manifest, manifest_path)
        assert errors == []

    def test_invalid_source_id(self):
        manifest = {
            "set_id": "test",
            "members": [
                {
                    "source_id": "VID001",  # uppercase invalid
                    "date": "2024-01-15",
                    "skill_path": "../skills/vid001",
                }
            ],
        }
        errors = validate_manifest_data(manifest)
        assert len(errors) > 0
        assert any("source_id" in e for e in errors)

    def test_invalid_date_format(self):
        manifest = {
            "set_id": "test",
            "members": [
                {
                    "source_id": "vid001",
                    "date": "15-01-2024",  # wrong format
                    "skill_path": "../skills/vid001",
                }
            ],
        }
        errors = validate_manifest_data(manifest)
        assert len(errors) > 0
        assert any("date" in e for e in errors)

    def test_duplicate_source_id(self):
        manifest = {
            "set_id": "test",
            "members": [
                {"source_id": "vid001", "date": "2024-01-15", "skill_path": "../skills/vid001"},
                {"source_id": "vid001", "date": "2024-03-20", "skill_path": "../skills/vid001"},
            ],
        }
        errors = validate_manifest_data(manifest)
        assert len(errors) > 0
        assert any("Duplicate" in e for e in errors)

    def test_missing_skill_path(self):
        manifest = {
            "set_id": "test",
            "members": [
                {"source_id": "vid001", "date": "2024-01-15"},
            ],
        }
        errors = validate_manifest_data(manifest)
        assert len(errors) > 0
        assert any("skill_path" in e for e in errors)

    def test_empty_date_rejected_by_real_validator(self):
        """Empty date is rejected by real validator — fail-fast as per plan."""
        manifest = {
            "set_id": "test",
            "members": [
                {
                    "source_id": "vid001",
                    "date": "",
                    "skill_path": "../skills/vid001",
                }
            ],
        }
        # Real validator rejects empty dates — this is the fail-fast behavior
        errors = validate_manifest_data(manifest)
        assert len(errors) > 0
        assert any("date" in e.lower() for e in errors)


# Need re for some tests
import re
