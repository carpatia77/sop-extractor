from sopx.cache import CacheManager


def test_key_for_url_is_stable_and_hex(tmp_path):
    cache = CacheManager(tmp_path / "cache")
    k1 = cache.key_for_url("ABC123")
    k2 = cache.key_for_url("ABC123")
    assert k1 == k2
    assert len(k1) == 16


def test_key_for_url_differs_for_different_ids(tmp_path):
    cache = CacheManager(tmp_path / "cache")
    assert cache.key_for_url("ABC123") != cache.key_for_url("XYZ789")


def test_key_for_file_depends_on_path_size_and_mtime(tmp_path):
    cache = CacheManager(tmp_path / "cache")
    f = tmp_path / "video.mp4"
    f.write_bytes(b"hello")
    k1 = cache.key_for_file(f)
    f.write_bytes(b"hello!!")  # size changes
    k2 = cache.key_for_file(f)
    assert k1 != k2


def test_stage_not_done_until_sentinel_written(tmp_path):
    cache = CacheManager(tmp_path / "cache")
    key = "somekey"
    stage_dir = cache.stage_path(key, "audio")
    # Simulate a crash mid-write: a partial artifact exists but no sentinel.
    (stage_dir / "audio.mp3").write_bytes(b"partial-garbage")
    assert cache.is_stage_done(key, "audio") is False


def test_stage_done_after_mark_stage_done(tmp_path):
    cache = CacheManager(tmp_path / "cache")
    key = "somekey"
    cache.stage_path(key, "audio")
    cache.mark_stage_done(key, "audio")
    assert cache.is_stage_done(key, "audio") is True


def test_is_done_false_when_output_dir_was_deleted(tmp_path):
    cache = CacheManager(tmp_path / "cache")
    output_dir = tmp_path / "output" / "key1"
    output_dir.mkdir(parents=True)
    cache.mark_done("key1", str(output_dir))
    assert cache.is_done("key1") is True

    output_dir.rmdir()
    assert cache.is_done("key1") is False


def test_mark_done_and_get_output_dir_persist_across_instances(tmp_path):
    cache_dir = tmp_path / "cache"
    output_dir = tmp_path / "output" / "key1"
    output_dir.mkdir(parents=True)

    cache1 = CacheManager(cache_dir)
    cache1.mark_done("key1", str(output_dir))

    cache2 = CacheManager(cache_dir)
    assert cache2.get_output_dir("key1") == str(output_dir)
    assert cache2.is_done("key1") is True


def test_entries_lists_all_cache_rows(tmp_path):
    cache = CacheManager(tmp_path / "cache")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    cache.mark_done("k1", str(output_dir), canonical_id="ABC")
    entries = cache.entries()
    assert len(entries) == 1
    assert entries[0]["key"] == "k1"
    assert entries[0]["canonical_id"] == "ABC"


def test_clear_empties_index(tmp_path):
    cache = CacheManager(tmp_path / "cache")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    cache.mark_done("k1", str(output_dir))
    removed = cache.clear()
    assert removed == 1
    assert cache.entries() == []
