"""Smart routing for video ingestion — detects user intent and recommends best approach.

Flow:
1. Detect input type (single video, multiple URLs, playlist/channel)
2. Check local hardware capabilities
3. Recommend: local GPU/CPU or Colab GPU
4. Generate appropriate script/instructions
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def detect_input_type(source: str | None, playlist: str | None, urls: list[str] | None) -> str:
    """Detect what the user wants to process.

    Returns:
        "single" - Single video URL or file
        "multi" - Multiple separate URLs
        "playlist" - YouTube playlist or channel
    """
    if playlist:
        return "playlist"
    if urls and len(urls) > 1:
        return "multi"
    return "single"


def check_local_hardware() -> dict:
    """Check local hardware capabilities for transcription.

    Returns dict with:
        - tier: "low", "medium", "high"
        - has_gpu: bool
        - cpu_cores: int
        - ram_gb: float
        - can_handle_batch: bool (if local processing is practical)
    """
    from sopx.ingest.hardware import detect_hardware

    profile = detect_hardware()

    # Determine if local processing is practical
    # Low tier: >30min videos will be slow, recommend Colab
    # Medium tier: OK for most cases
    # High tier: fast local processing
    can_handle_batch = profile.tier in ("medium", "high")

    return {
        "tier": profile.tier,
        "has_gpu": profile.has_gpu,
        "cpu_cores": profile.cpu_physical,
        "ram_gb": profile.ram_gb,
        "can_handle_batch": can_handle_batch,
    }


def estimate_processing_time(duration_sec: float, hardware: dict) -> dict:
    """Estimate processing time for a video.

    Returns dict with:
        - local_time_sec: estimated time on local hardware
        - colab_time_sec: estimated time on Colab GPU
        - local_minutes: formatted local time
        - colab_minutes: formatted colab time
        - speedup: colab speedup factor
    """
    # Speed ratios by tier
    speeds = {
        "low": 1.67,
        "medium": 2.5,
        "high": 4.0,
    }
    colab_speed = 115  # T4 GPU batch=16

    local_speed = speeds.get(hardware["tier"], 1.67)
    local_time = duration_sec / local_speed
    colab_time = duration_sec / colab_speed

    def fmt(seconds):
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"

    return {
        "local_time_sec": local_time,
        "colab_time_sec": colab_time,
        "local_minutes": fmt(local_time),
        "colab_minutes": fmt(colab_time),
        "speedup": local_time / colab_time if colab_time > 0 else 0,
    }


def recommend_approach(input_type: str, hardware: dict, video_count: int = 1, total_duration: float = 0) -> dict:
    """Recommend the best approach based on input and hardware.

    Returns dict with:
        - approach: "local" or "colab"
        - reason: explanation string
        - urgency: "immediate" or "background"
        - action: what to do next
    """
    # Single short video (<5min): always local
    if input_type == "single" and total_duration < 300:
        return {
            "approach": "local",
            "reason": "Vídeo curto — processamento local rápido",
            "urgency": "immediate",
            "action": "execute",
        }

    # Single video with good hardware: local
    if input_type == "single" and hardware["tier"] in ("medium", "high"):
        return {
            "approach": "local",
            "reason": f"Hardware {hardware['tier']} — processamento local viável",
            "urgency": "immediate",
            "action": "execute",
        }

    # Single video with weak hardware: Colab
    if input_type == "single" and hardware["tier"] == "low":
        return {
            "approach": "colab",
            "reason": f"Hardware {hardware['tier']} ({hardware['cpu_cores']} cores) — Colab é {115/1.67:.0f}x mais rápido",
            "urgency": "background",
            "action": "generate_notebook",
        }

    # Multiple videos: always Colab
    if input_type == "multi":
        return {
            "approach": "colab",
            "reason": f"{video_count} vídeos — Colab processa em paralelo com GPU",
            "urgency": "background",
            "action": "generate_notebook",
        }

    # Playlist/channel: always Colab
    if input_type == "playlist":
        return {
            "approach": "colab",
            "reason": "Playlist/canal — Colab é essencial para lote grande",
            "urgency": "background",
            "action": "generate_notebook",
        }

    # Default: Colab for safety
    return {
        "approach": "colab",
        "reason": "Recomendação padrão — Colab para melhor performance",
        "urgency": "background",
        "action": "generate_notebook",
    }


def print_routing_decision(input_type: str, hardware: dict, recommendation: dict, estimates: dict | None = None):
    """Print the routing decision to stderr."""
    print(f"\n  {'='*60}", file=sys.stderr)
    print(f"  ANÁLISE INTELIGENTE DE ROTEAMENTO", file=sys.stderr)
    print(f"  {'='*60}", file=sys.stderr)

    # Input type
    type_names = {
        "single": "Vídeo único",
        "multi": "Múltiplos vídeos",
        "playlist": "Playlist/Canal",
    }
    print(f"\n  📁 Tipo de entrada:    {type_names.get(input_type, input_type)}", file=sys.stderr)

    # Hardware
    tier_names = {"low": "Baixo", "medium": "Médio", "high": "Alto"}
    print(f"  🖥️  Hardware local:     {tier_names.get(hardware['tier'], '?')} ({hardware['cpu_cores']} cores, {hardware['ram_gb']:.0f}GB)", file=sys.stderr)
    print(f"  🎮 GPU local:          {'Sim' if hardware['has_gpu'] else 'Não'}", file=sys.stderr)

    # Recommendation
    approach_names = {"local": "Local", "colab": "Colab GPU"}
    print(f"\n  💡 Recomendação:       {approach_names.get(recommendation['approach'], '?')}", file=sys.stderr)
    print(f"  📝 Motivo:             {recommendation['reason']}", file=sys.stderr)

    # Estimates if available
    if estimates:
        print(f"\n  ⏱️  Tempo estimado:", file=sys.stderr)
        print(f"     Local:  ~{estimates['local_minutes']}", file=sys.stderr)
        print(f"     Colab:  ~{estimates['colab_minutes']}", file=sys.stderr)
        print(f"     Speedup: {estimates['speedup']:.0f}x mais rápido no Colab", file=sys.stderr)

    # Action
    print(f"\n  🚀 Próxima ação:       {recommendation['action']}", file=sys.stderr)
    print(f"  {'='*60}\n", file=sys.stderr)
