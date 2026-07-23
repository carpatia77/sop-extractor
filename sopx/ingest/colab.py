"""Colab GPU integration — generates notebooks for cloud transcription.

When the user doesn't have a local GPU, this module generates a Colab
notebook with the provided URLs and opens it in the browser.
"""
from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path


def _create_notebook_cell(cell_type: str, source: list[str]) -> dict:
    """Create a notebook cell."""
    return {
        "cell_type": cell_type,
        "metadata": {},
        "source": source,
        "outputs": [],
        "execution_count": None,
    }


def generate_colab_notebook(urls: list[str], model: str = "base") -> Path:
    """Generate a Colab notebook for GPU transcription.

    Args:
        urls: List of YouTube URLs to transcribe.
        model: Whisper model size (tiny/base/small/medium/large-v3).

    Returns:
        Path to the generated notebook file.
    """
    # Build video list for the notebook
    video_lines = []
    for url in urls:
        # Extract video ID from URL
        video_id = _extract_video_id(url)
        if video_id:
            video_lines.append(f'    "{video_id}",')

    videos_str = "\n".join(video_lines)

    cells = []

    # Cell 1: Title
    cells.append(_create_notebook_cell("markdown", [
        "# Transcrição GPU — sop-extractor\n",
        "\n",
        "Execute todas as células para transcrever os vídeos.\n",
        "\n",
        "**IMPORTANTE:** Runtime → Change runtime type → **T4 GPU**"
    ]))

    # Cell 2: Install dependencies
    cells.append(_create_notebook_cell("code", [
        "# 1. Instalar dependências\n",
        "!pip install -q faster-whisper yt-dlp\n",
        "\n",
        "import time, json, os\n",
        "from pathlib import Path\n",
        "from faster_whisper import WhisperModel, BatchedInferencePipeline\n",
        "\n",
        "print('✓ Dependências instaladas!')"
    ]))

    # Cell 3: Load model
    cells.append(_create_notebook_cell("code", [
        f"# 2. Carregar modelo {model} na GPU\n",
        "model = WhisperModel('" + model + "', device='cuda', compute_type='int8')\n",
        "batched_model = BatchedInferencePipeline(model=model)\n",
        "print('✓ Modelo carregado na GPU!')"
    ]))

    # Cell 4: Video list
    cells.append(_create_notebook_cell("code", [
        "# 3. Vídeos para processar\n",
        "VIDEO_IDS = [\n",
        videos_str,
        "]\n",
        "\n",
        "print(f'{len(VIDEO_IDS)} vídeos para transcrever')"
    ]))

    # Cell 5: Transcription function
    cells.append(_create_notebook_cell("code", [
        "# 4. Função de transcrição\n",
        "def transcribe(video_id):\n",
        "    url = f'https://www.youtube.com/watch?v={video_id}'\n",
        "    out = Path(f'output/{video_id}')\n",
        "    out.mkdir(parents=True, exist_ok=True)\n",
        "    \n",
        "    # Download\n",
        "    print(f'\\n📥 Download: {video_id}')\n",
        "    t0 = time.time()\n",
        "    os.system(f'yt-dlp -x --audio-format mp3 -o temp_audio.%(ext)s {url} 2>/dev/null')\n",
        "    \n",
        "    audio = next(Path('.').glob('temp_audio.*'), None)\n",
        "    if not audio:\n",
        "        print('  ❌ Erro no download')\n",
        "        return None\n",
        "    \n",
        "    # Transcrever\n",
        "    print(f'⚡ Transcrevendo com GPU...')\n",
        "    t1 = time.time()\n",
        "    segments, info = batched_model.transcribe(str(audio), batch_size=16, beam_size=5)\n",
        "    segs = list(segments)\n",
        "    elapsed = time.time() - t1\n",
        "    \n",
        "    # Salvar SRT\n",
        "    def ts(s):\n",
        "        h, m, sec = int(s//3600), int((s%3600)//60), int(s%60)\n",
        "        ms = round((s-int(s))*1000)\n",
        "        return f'{h:02d}:{m:02d}:{sec:02d},{ms:03d}'\n",
        "    \n",
        "    srt_lines = []\n",
        "    for i, seg in enumerate(segs, 1):\n",
        "        srt_lines.append(str(i))\n",
        "        srt_lines.append(f'{ts(seg.start)} --> {ts(seg.end)}')\n",
        "        srt_lines.append(seg.text.strip())\n",
        "        srt_lines.append('')\n",
        "    srt = '\\n'.join(srt_lines)\n",
        "    (out / 'transcript.srt').write_text(srt, encoding='utf-8')\n",
        "    \n",
        "    text = '\\n'.join(s.text.strip() for s in segs)\n",
        "    (out / 'full_text.txt').write_text(text, encoding='utf-8')\n",
        "    \n",
        "    # Metadata\n",
        "    meta = {\n",
        "        'video_id': video_id,\n",
        "        'language': info.language,\n",
        "        'duration': info.duration,\n",
        "        'word_count': len(text.split()),\n",
        "        'segments': len(segs),\n",
        "        'gpu_time': elapsed,\n",
        "    }\n",
        "    (out / 'metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')\n",
        "    \n",
        "    audio.unlink(missing_ok=True)\n",
        "    speedup = info.duration / elapsed if elapsed > 0 else 0\n",
        "    print(f'  ✅ {len(text.split())} palavras em {elapsed:.1f}s ({speedup:.0f}x)')\n",
        "    return meta\n",
        "\n",
        "print('✓ Função definida!')"
    ]))

    # Cell 6: Run all
    cells.append(_create_notebook_cell("code", [
        "# 5. Processar todos os vídeos\n",
        "results = []\n",
        "t_start = time.time()\n",
        "\n",
        "for i, vid in enumerate(VIDEO_IDS, 1):\n",
        "    print(f'\\n{\"=\"*50}')\n",
        "    print(f'VÍDEO {i}/{len(VIDEO_IDS)}')\n",
        "    print(f'{\"=\"*50}')\n",
        "    r = transcribe(vid)\n",
        "    if r:\n",
        "        results.append(r)\n",
        "\n",
        "total = time.time() - t_start"
    ]))

    # Cell 7: Report
    cells.append(_create_notebook_cell("code", [
        "# 6. Relatório\n",
        "print(f'\\n{\"=\"*60}')\n",
        "print('RELATÓRIO DE TRANSCRIÇÃO')\n",
        "print(f'{\"=\"*60}')\n",
        "print(f'\\nVídeos: {len(results)}/{len(VIDEO_IDS)}')\n",
        "print(f'Tempo total GPU: {total:.1f}s')\n",
        "print(f'\\n{\"Vídeo\":<15} {\"Duração\":>10} {\"Palavras\":>10} {\"Speed\":>8}')\n",
        "print('-'*45)\n",
        "for r in results:\n",
        "    d = r['duration']/60\n",
        "    print(f'{r[\"video_id\"]:<15} {d:>9.1f}m {r[\"word_count\"]:>10} {r[\"speedup\"]:>8}')\n",
        "print('-'*45)\n",
        "total_dur = sum(r['duration'] for r in results)/60\n",
        "total_words = sum(r['word_count'] for r in results)\n",
        "print(f'{\"TOTAL\":<15} {total_dur:>9.1f}m {total_words:>10}')"
    ]))

    # Cell 8: Download
    cells.append(_create_notebook_cell("code", [
        "# 7. Download dos resultados\n",
        "import shutil\n",
        "from google.colab import files\n",
        "from pathlib import Path\n",
        "\n",
        "# Verificar se há resultados\n",
        "output_dir = Path('output')\n",
        "if not output_dir.exists() or not any(output_dir.iterdir()):\n",
        "    print('⚠ Nenhum resultado encontrado. Execute as células anteriores primeiro!')\n",
        "else:\n",
        "    # Listar arquivos\n",
        "    print('📁 Arquivos gerados:')\n",
        "    for f in output_dir.rglob('*'):\n",
        "        if f.is_file():\n",
        "            print(f'   {f}')\n",
        "    \n",
        "    # Criar ZIP\n",
        "    shutil.make_archive('transcriptions', 'zip', 'output')\n",
        "    zip_path = Path('transcriptions.zip')\n",
        "    print(f'\\n📦 ZIP criado: {zip_path.stat().st_size / 1024:.1f} KB')\n",
        "    \n",
        "    # Baixar\n",
        "    files.download('transcriptions.zip')"
    ]))

    # Build notebook
    notebook = {
        "cells": cells,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"provenance": [], "gpuType": "T4"},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10.0"},
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }

    # Save notebook
    output_path = Path("/tmp/sopx_gpu_transcribe.ipynb")
    output_path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")

    return output_path


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    import re

    # Standard: youtube.com/watch?v=XXX
    m = re.search(r"watch\?v=([a-zA-Z0-9_-]{11})", url)
    if m:
        return m.group(1)

    # Short: youtu.be/XXX
    m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url)
    if m:
        return m.group(1)

    # Direct ID: 11 chars
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
        return url

    return None


def open_in_colab(notebook_path: Path) -> bool:
    """Open a notebook in Google Colab.

    Returns True if browser was opened successfully.
    """
    # Upload URL for local files
    colab_url = "https://colab.research.google.com/"

    print(f"\n  📓 Notebook gerado: {notebook_path}", file=sys.stderr)
    print(f"\n  Para usar no Colab:", file=sys.stderr)
    print(f"  1. Abra: {colab_url}", file=sys.stderr)
    print(f"  2. Arquivo → Abrir → Upload → selecione o notebook", file=sys.stderr)
    print(f"  3. Runtime → Change runtime type → T4 GPU", file=sys.stderr)
    print(f"  4. Runtime → Run all", file=sys.stderr)

    try:
        webbrowser.open(colab_url)
        print(f"\n  🌐 Colab aberto no navegador!", file=sys.stderr)
        return True
    except Exception:
        print(f"\n  ⚠ Não foi possível abrir o navegador automaticamente", file=sys.stderr)
        return False
