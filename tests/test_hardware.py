"""Tests for hardware detection module."""

import pytest

from sopx.ingest.hardware import (
    HardwareProfile,
    _classify_tier,
    _get_cpu_info,
    _get_ram_gb,
    detect_hardware,
    estimate_transcription_time,
    get_optimal_settings,
    get_speed_ratio,
)


class TestGetCpuInfo:
    """Tests for _get_cpu_info()."""

    def test_returns_tuple_of_three(self):
        logical, physical, freq = _get_cpu_info()
        assert isinstance(logical, int)
        assert isinstance(physical, int)
        assert isinstance(freq, float)
        assert logical >= 1
        assert physical >= 1
        assert freq > 0

    def test_physical_not_greater_than_logical(self):
        logical, physical, _ = _get_cpu_info()
        assert physical <= logical


class TestGetRamGb:
    """Tests for _get_ram_gb()."""

    def test_returns_positive_float(self):
        ram = _get_ram_gb()
        assert isinstance(ram, float)
        assert ram > 0

    def test_reasonable_range(self):
        ram = _get_ram_gb()
        assert 0.5 <= ram <= 1024  # 512MB to 1TB


class TestClassifyTier:
    """Tests for _classify_tier()."""

    def test_low_tier_small_cpu(self):
        assert _classify_tier(cpu_physical=2, ram_gb=4.0, has_gpu=False, cpu_freq_mhz=2000) == "low"

    def test_medium_tier(self):
        assert _classify_tier(cpu_physical=4, ram_gb=8.0, has_gpu=False, cpu_freq_mhz=2500) == "medium"

    def test_high_tier_gpu(self):
        assert _classify_tier(cpu_physical=2, ram_gb=4.0, has_gpu=True, cpu_freq_mhz=2000) == "high"

    def test_high_tier_many_cores(self):
        assert _classify_tier(cpu_physical=8, ram_gb=8.0, has_gpu=False, cpu_freq_mhz=2000) == "high"

    def test_high_tier_large_ram(self):
        assert _classify_tier(cpu_physical=4, ram_gb=16.0, has_gpu=False, cpu_freq_mhz=2000) == "high"

    def test_low_tier_slow_cpu(self):
        assert _classify_tier(cpu_physical=4, ram_gb=4.0, has_gpu=False, cpu_freq_mhz=1500) == "low"


class TestDetectHardware:
    """Tests for detect_hardware()."""

    def test_returns_hardware_profile(self):
        # Reset cache
        if hasattr(detect_hardware, "_cache"):
            del detect_hardware._cache

        profile = detect_hardware()
        assert isinstance(profile, HardwareProfile)
        assert profile.tier in ("low", "medium", "high")

    def test_caches_result(self):
        if hasattr(detect_hardware, "_cache"):
            del detect_hardware._cache

        profile1 = detect_hardware()
        profile2 = detect_hardware()
        assert profile1 is profile2


class TestGetOptimalSettings:
    """Tests for get_optimal_settings()."""

    def test_settings_keys(self):
        profile = HardwareProfile(
            cpu_count=4, cpu_physical=2, cpu_freq_mhz=2500,
            ram_gb=8.0, has_gpu=False, tier="medium",
        )
        settings = get_optimal_settings(profile, video_duration_sec=600)
        assert "batch_size" in settings
        assert "compute_type" in settings
        assert "beam_size" in settings
        assert "split_audio" in settings
        assert "max_segment_sec" in settings

    def test_short_video_no_split(self):
        profile = HardwareProfile(
            cpu_count=4, cpu_physical=2, cpu_freq_mhz=2500,
            ram_gb=8.0, has_gpu=False, tier="medium",
        )
        settings = get_optimal_settings(profile, video_duration_sec=600)  # 10min
        assert settings["split_audio"] is False

    def test_long_video_split(self):
        profile = HardwareProfile(
            cpu_count=4, cpu_physical=2, cpu_freq_mhz=2500,
            ram_gb=8.0, has_gpu=False, tier="medium",
        )
        settings = get_optimal_settings(profile, video_duration_sec=2400)  # 40min
        assert settings["split_audio"] is True

    def test_low_tier_smaller_batch(self):
        profile = HardwareProfile(
            cpu_count=2, cpu_physical=1, cpu_freq_mhz=2000,
            ram_gb=4.0, has_gpu=False, tier="low",
        )
        settings = get_optimal_settings(profile, video_duration_sec=600)
        assert settings["batch_size"] == 2

    def test_high_tier_larger_batch(self):
        profile = HardwareProfile(
            cpu_count=16, cpu_physical=8, cpu_freq_mhz=3500,
            ram_gb=32.0, has_gpu=True, tier="high",
        )
        settings = get_optimal_settings(profile, video_duration_sec=600)
        assert settings["batch_size"] == 8


class TestGetSpeedRatio:
    """Tests for get_speed_ratio()."""

    def test_base_low(self):
        speed = get_speed_ratio("base", "low")
        assert speed == pytest.approx(1.67, abs=0.01)

    def test_base_medium(self):
        speed = get_speed_ratio("base", "medium")
        assert speed == pytest.approx(2.5, abs=0.1)

    def test_base_high(self):
        speed = get_speed_ratio("base", "high")
        assert speed == pytest.approx(4.0, abs=0.1)

    def test_tiny_faster_than_base(self):
        assert get_speed_ratio("tiny", "low") > get_speed_ratio("base", "low")

    def test_large_slower_than_base(self):
        assert get_speed_ratio("large-v3", "low") < get_speed_ratio("base", "low")


class TestEstimateTranscriptionTime:
    """Tests for estimate_transcription_time()."""

    def test_returns_float(self):
        profile = HardwareProfile(
            cpu_count=2, cpu_physical=1, cpu_freq_mhz=2000,
            ram_gb=4.0, has_gpu=False, tier="low",
        )
        result = estimate_transcription_time(600, "base", profile)
        assert isinstance(result, float)
        assert result > 0

    def test_longer_video_takes_more_time(self):
        profile = HardwareProfile(
            cpu_count=2, cpu_physical=1, cpu_freq_mhz=2000,
            ram_gb=4.0, has_gpu=False, tier="low",
        )
        t_short = estimate_transcription_time(600, "base", profile)
        t_long = estimate_transcription_time(1200, "base", profile)
        assert t_long > t_short

    def test_higher_tier_faster(self):
        profile_low = HardwareProfile(
            cpu_count=2, cpu_physical=1, cpu_freq_mhz=2000,
            ram_gb=4.0, has_gpu=False, tier="low",
        )
        profile_high = HardwareProfile(
            cpu_count=16, cpu_physical=8, cpu_freq_mhz=3500,
            ram_gb=32.0, has_gpu=True, tier="high",
        )
        t_low = estimate_transcription_time(1200, "base", profile_low)
        t_high = estimate_transcription_time(1200, "base", profile_high)
        assert t_high < t_low
