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


def generate_smart_script(urls: list[str], recommendation: dict, model: str = "base") -> str:
    """Generate a custom script/instructions based on recommendation.

    Returns formatted instructions for the user.
    """
    if recommendation["approach"] == "local":
        return _generate_local_script(urls, model)
    else:
        return _generate_colab_script(urls, model)


def _generate_local_script(urls: list[str], model: str) -> str:
    """Generate local execution script."""
    lines = [
        "# Script de Transcrição Local",
        "# " + "=" * 50,
        "",
        "# Execute no terminal:",
        "",
    ]

    for url in urls:
        lines.append(f"sopx ingest \"{url}\" --model {model}")

    lines.extend([
        "",
        "# Ou para todos de uma vez:",
        "",
    ])

    urls_str = " ".join(f'"{u}"' for u in urls)
    lines.append(f"# sopx ingest {urls_str[0:50]}... --model {model}")

    return "\n".join(lines)


def _generate_colab_script(urls: list[str], model: str) -> str:
    """Generate Colab instructions."""
    video_ids = []
    for url in urls:
        vid = _extract_video_id(url)
        if vid:
            video_ids.append(vid)

    lines = [
        "# " + "=" * 60,
        "# INSTRUÇÕES PARA GOOGLE COLAB",
        "# " + "=" * 60,
        "",
        "## Passo 1: Abrir o Colab",
        "Acesse: https://colab.research.google.com/",
        "",
        "## Passo 2: Criar novo notebook",
        "Arquivo → Novo notebook",
        "",
        "## Passo 3: Ativar GPU (OBRIGATÓRIO)",
        "Runtime → Change runtime type → T4 GPU → Save",
        "",
        "## Passo 4: Copiar e rodar o código abaixo",
        "",
        "```python",
        "# Instalar dependências",
        "!pip install -q faster-whisper yt-dlp",
        "",
        "import time, json, os",
        "from pathlib import Path",
        "from faster_whisper import WhisperModel, BatchedInferencePipeline",
        "",
        "# Carregar modelo na GPU",
        f"model = WhisperModel('{model}', device='cuda', compute_type='int8')",
        "batched_model = BatchedInferencePipeline(model=model)",
        "",
        f"# Vídeos ({len(video_ids)} total)",
        "VIDEO_IDS = [",
    ]

    for vid in video_ids:
        lines.append(f'    "{vid}",')

    lines.extend([
        "]",
        "",
        "# Função de transcrição",
        "def transcribe(video_id):",
        "    url = f'https://www.youtube.com/watch?v={video_id}'",
        "    out = Path(f'output/{video_id}')",
        "    out.mkdir(parents=True, exist_ok=True)",
        "    ",
        "    # Download",
        "    print(f'📥 Download: {video_id}')",
        "    os.system(f'yt-dlp -x --audio-format mp3 -o temp_audio.%(ext)s {url} 2>/dev/null')",
        "    audio = next(Path('.').glob('temp_audio.*'), None)",
        "    if not audio:",
        "        print('❌ Erro no download')",
        "        return None",
        "    ",
        "    # Transcrever",
        "    print(f'⚡ Transcrevendo com GPU...')",
        "    t1 = time.time()",
        "    segments, info = batched_model.transcribe(str(audio), batch_size=16, beam_size=5)",
        "    segs = list(segments)",
        "    elapsed = time.time() - t1",
        "    ",
        "    # Salvar SRT",
        "    def ts(s):",
        "        h, m, sec = int(s//3600), int((s%3600)//60), int(s%60)",
        "        ms = round((s-int(s))*1000)",
        "        return f'{h:02d}:{m:02d}:{sec:02d},{ms:03d}'",
        "    ",
        "    srt = '\\n'.join(f'{i}\\n{ts(s.start)} --> {ts(s.end)}\\n{s.text.strip()}\\n' for i, s in enumerate(segs, 1))",
        "    (out / 'transcript.srt').write_text(srt, encoding='utf-8')",
        "    ",
        "    text = '\\n'.join(s.text.strip() for s in segs)",
        "    (out / 'full_text.txt').write_text(text, encoding='utf-8')",
        "    ",
        "    meta = {'video_id': video_id, 'word_count': len(text.split()), 'gpu_time': elapsed}",
        "    (out / 'metadata.json').write_text(json.dumps(meta, indent=2))",
        "    ",
        "    audio.unlink(missing_ok=True)",
        "    speedup = info.duration / elapsed if elapsed > 0 else 0",
        "    print(f'✅ {meta[\"word_count\"]} palavras em {elapsed:.1f}s ({speedup:.0f}x)')",
        "    return meta",
        "",
        "# Processar todos",
        "results = []",
        "for vid in VIDEO_IDS:",
        "    r = transcribe(vid)",
        "    if r: results.append(r)",
        "",
        "print(f'\\n🎉 Concluído: {len(results)} vídeos processados')",
        "```",
        "",
        "## Passo 5: Download dos resultados",
        "Descomente na última célula para baixar um ZIP com todos os arquivos.",
        "",
        "# " + "=" * 60,
    ])

    return "\n".join(lines)


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    import re

    m = re.search(r"watch\?v=([a-zA-Z0-9_-]{11})", url)
    if m:
        return m.group(1)

    m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url)
    if m:
        return m.group(1)

    if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
        return url

    return None


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
