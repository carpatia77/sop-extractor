"""Hardware detection for optimal transcription settings.

Detects CPU cores, RAM, and GPU availability to determine the optimal
transcription configuration (batch_size, segment length, speed estimates).
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class HardwareProfile:
    """Detected hardware capabilities."""
    cpu_count: int          # Logical cores
    cpu_physical: int       # Physical cores
    cpu_freq_mhz: float     # Max frequency in MHz
    ram_gb: float           # Total RAM in GB
    has_gpu: bool           # CUDA/Metal available
    tier: str               # "low", "medium", "high"

    def __str__(self) -> str:
        tier_names = {
            "low": "Baixo (CPU simples)",
            "medium": "Médio (CPU moderno)",
            "high": "Alto (GPU/multi-core)",
        }
        return (
            f"{self.cpu_physical} cores, {self.ram_gb:.1f}GB RAM"
            f" — Tier: {tier_names.get(self.tier, self.tier)}"
        )


def _get_cpu_info() -> tuple[int, int, float]:
    """Get CPU core count and frequency.

    Returns (logical_cores, physical_cores, max_freq_mhz).
    """
    logical = os.cpu_count() or 2
    physical = logical
    freq = 2000.0  # default 2GHz

    try:
        # Try /proc/cpuinfo (Linux)
        with open("/proc/cpuinfo", "r") as f:
            content = f.read()

        # Count unique physical ids + cores
        phys_ids = set()
        core_count = 0
        for line in content.splitlines():
            if line.startswith("physical id"):
                phys_ids.add(line.split(":")[1].strip())
            if line.startswith("cpu cores"):
                core_count = int(line.split(":")[1].strip())
            if line.startswith("cpu MHz"):
                try:
                    freq = float(line.split(":")[1].strip())
                except ValueError:
                    pass

        if core_count > 0:
            physical = len(phys_ids) * core_count
            if physical == 0:
                physical = core_count
    except FileNotFoundError:
        pass

    # Fallback: assume physical = logical / 2 (hyperthreading)
    if physical <= 0:
        physical = max(1, logical // 2)

    return logical, physical, freq


def _get_ram_gb() -> float:
    """Get total RAM in GB."""
    try:
        # Linux: /proc/meminfo
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    return kb / (1024 * 1024)
    except (FileNotFoundError, ValueError):
        pass

    # Fallback: assume 4GB
    return 4.0


def _detect_gpu() -> bool:
    """Check if CUDA GPU is available."""
    # Check nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Check CUDA_VISIBLE_DEVICES env
    if os.environ.get("CUDA_VISIBLE_DEVICES"):
        return True

    # Check if torch with CUDA is available
    try:
        import torch
        if torch.cuda.is_available():
            return True
    except (ImportError, AttributeError):
        pass

    return False


def _classify_tier(cpu_physical: int, ram_gb: float, has_gpu: bool, cpu_freq_mhz: float) -> str:
    """Classify hardware into a performance tier.

    Tiers:
    - low: 1-3 physical cores, or <4GB RAM, or <2GHz
    - medium: 4-7 physical cores, 4-15GB RAM, no GPU
    - high: 8+ cores, or 16GB+ RAM, or GPU available
    """
    if has_gpu:
        return "high"

    if cpu_physical >= 8 or ram_gb >= 16:
        return "high"

    if cpu_physical >= 4 and ram_gb >= 4 and cpu_freq_mhz >= 2000:
        return "medium"

    return "low"


def detect_hardware() -> HardwareProfile:
    """Detect system hardware and return profile.

    This is cached after first call for performance.
    """
    if hasattr(detect_hardware, "_cache"):
        return detect_hardware._cache

    logical, physical, freq = _get_cpu_info()
    ram = _get_ram_gb()
    gpu = _detect_gpu()
    tier = _classify_tier(physical, ram, gpu, freq)

    profile = HardwareProfile(
        cpu_count=logical,
        cpu_physical=physical,
        cpu_freq_mhz=freq,
        ram_gb=ram,
        has_gpu=gpu,
        tier=tier,
    )
    detect_hardware._cache = profile
    return profile


# ---------------------------------------------------------------------------
# Optimal settings per tier
# ---------------------------------------------------------------------------

# Speed ratios by hardware tier (seconds of audio per second of processing)
# Measured on real hardware:
#   low:    Pentium 5405U 2-core 2.3GHz — 49min in 29:19 = 1.67x
#   medium: estimated based on ~1.5x improvement over low
#   high:   estimated based on GPU or 8+ core CPU
_SPEED_BY_TIER = {
    "tiny":    {"low": 7.0,  "medium": 10.0, "high": 15.0},
    "base":    {"low": 1.67, "medium": 2.5,  "high": 4.0},
    "small":   {"low": 0.9,  "medium": 1.4,  "high": 2.2},
    "medium":  {"low": 0.45, "medium": 0.7,  "high": 1.1},
    "large-v3": {"low": 0.2, "medium": 0.35, "high": 0.6},
}

# Default batch_size by tier
_BATCH_SIZE = {"low": 2, "medium": 4, "high": 8}

# Beam size by tier (lower = faster, slight quality tradeoff on low-end)
_BEAM_SIZE = {"low": 3, "medium": 5, "high": 5}

# Max segment length (seconds) for audio splitting
_MAX_SEGMENT = {"low": 300, "medium": 600, "high": 900}


def get_optimal_settings(profile: HardwareProfile, video_duration_sec: float) -> dict:
    """Return optimal transcription settings for this hardware and video.

    Args:
        profile: Detected hardware profile.
        video_duration_sec: Duration of the video in seconds.

    Returns:
        dict with keys: batch_size, compute_type, beam_size,
                        split_audio, max_segment_sec.
    """
    tier = profile.tier
    split = video_duration_sec > 1800  # >30min

    return {
        "batch_size": _BATCH_SIZE[tier],
        "compute_type": "int8",
        "beam_size": _BEAM_SIZE[tier],
        "split_audio": split,
        "max_segment_sec": _MAX_SEGMENT[tier],
    }


def get_speed_ratio(model: str, tier: str) -> float:
    """Get the measured speed ratio for a model on a given tier."""
    model_speeds = _SPEED_BY_TIER.get(model, _SPEED_BY_TIER["base"])
    return model_speeds.get(tier, 1.67)


def estimate_transcription_time(duration_sec: float, model: str, profile: HardwareProfile) -> float:
    """Estimate transcription time in seconds."""
    speed = get_speed_ratio(model, profile.tier)
    return duration_sec / speed


def print_hardware_summary(profile: HardwareProfile, file=sys.stderr):
    """Print detected hardware info."""
    tier_names = {
        "low": "Baixo (CPU simples)",
        "medium": "Médio (CPU moderno)",
        "high": "Alto (GPU/multi-core)",
    }
    gpu_str = " + GPU" if profile.has_gpu else ""
    print(
        f"  Hardware detectado: {profile.cpu_physical} cores, "
        f"{profile.ram_gb:.1f}GB RAM{gpu_str}",
        file=file,
    )
    print(f"  Tier: {tier_names.get(profile.tier, profile.tier)}", file=file)
