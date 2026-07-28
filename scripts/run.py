#!/usr/bin/env python3
"""run — one command, paste a link, system handles everything.

Auto-detects input type and runs the appropriate pipeline.

Supported:
    YouTube URLs (video, playlist, channel)
    Local video (.mp4, .mkv, .avi, .mov)
    Local audio (.mp3, .wav, .m4a, .ogg, .flac)
    Books (.pdf, .epub, .docx)
    Transcripts (.txt, .srt, .vtt, .md)

Usage:
    sopx run <URL_or_path>                  # auto-detect, ingest + compile
    sopx run <URL> --workers 4              # parallel ingest
    sopx run <URL> --max 10                 # limit videos
    sopx run <URL> --gpu                    # force Colab GPU
    sopx run ./book.pdf                     # compile directly
    sopx run ./audio.mp3                    # transcribe + compile
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma", ".opus"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}
COMPILABLE_EXTS = {".txt", ".srt", ".vtt", ".md", ".pdf", ".epub", ".docx", ".rst", ".html"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".svg"}

# ANSI colors
BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def _c(text: str, color: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{RESET}"


def _print_banner():
    print(f"""
{_c('═' * 50, CYAN)}
  {_c('sopx run', BOLD)}  — cola o link, eu resolvo
{_c('═' * 50, CYAN)}
""")


def _detect_source_type(source: str) -> str:
    """Detect if source is URL (video/playlist/channel) or local file."""
    if os.path.isfile(source):
        return "file"
    if "youtube.com" in source or "youtu.be" in source:
        if "playlist" in source or "channel" in source or "/c/" in source or "/@" in source:
            return "playlist"
        return "video_url"
    if source.startswith("http://") or source.startswith("https://"):
        return "url"
    return "unknown"


def _run_cmd(cmd: list[str], label: str = "") -> int:
    """Run a command, stream output, return exit code."""
    if label:
        print(f"  {_c(label, CYAN)}")
    result = subprocess.run(cmd)
    return result.returncode


def run_source(source: str, workers: int = 1, max_videos: int | None = None,
               gpu: bool = False, model: str | None = None) -> int:
    """Main entry: detect source and run appropriate pipeline."""
    _print_banner()

    source_type = _detect_source_type(source)

    if source_type == "file":
        return _run_file(source, model)

    if source_type == "playlist":
        return _run_playlist(source, workers=workers, max_videos=max_videos,
                             gpu=gpu, model=model)

    if source_type in ("video_url", "url"):
        return _run_single_video(source, gpu=gpu, model=model)

    print(f"  {_c('ERRO', RED)} Não consegui identificar a fonte: {source}")
    print(f"  {DIM}Aceita: URL do YouTube, playlist, ou arquivo local{RESET}")
    return 1


def _run_file(path: str, model: str | None = None) -> int:
    """Local file → route to correct pipeline."""
    p = Path(path)
    if not p.exists():
        print(f"  {_c('ERRO', RED)} Arquivo não encontrado: {path}")
        return 1

    ext = p.suffix.lower()

    # Compilable: books, transcripts, docs → compile directly
    if ext in COMPILABLE_EXTS:
        print(f"  📄 Arquivo compilável detectado: {_c(p.name, GREEN)}")
        print("  → Compilando diretamente\n")
        cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "compile.py"), str(p)]
        if model:
            cmd.extend(["--model", model])
        return _run_cmd(cmd)

    # Audio: needs transcription → ingest (whisper) + compile
    if ext in AUDIO_EXTS:
        print(f"  🔊 Áudio detectado: {_c(p.name, GREEN)}")
        print("  → Transcrevendo + compilando\n")
        cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "ingest.py"), str(p), "--compile"]
        if model:
            cmd.extend(["--model", model])
        return _run_cmd(cmd)

    # Video: needs download+transcription → ingest + compile
    if ext in VIDEO_EXTS:
        print(f"  🎬 Vídeo detectado: {_c(p.name, GREEN)}")
        print("  → Ingerindo + compilando\n")
        cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "ingest.py"), str(p), "--compile"]
        if model:
            cmd.extend(["--model", model])
        return _run_cmd(cmd)

    # Images: not supported yet (VLM not implemented)
    if ext in IMAGE_EXTS:
        print(f"  🖼️  Imagem detectada: {_c(p.name, YELLOW)}")
        print(f"  {_c('Não suportado', YELLOW)} — análise de imagem requer VLM (Fase 3)")
        print(f"  {DIM}Formatos suportados: PDF, EPUB, DOCX, TXT, SRT, MD, audio, video{RESET}")
        return 1

    # Unknown: try as text
    print(f"  ⚠ Formato desconhecido: {_c(ext or '(sem extensão)', YELLOW)}")
    print(f"  {DIM}Tentando como texto...{RESET}")
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "compile.py"), str(p)]
    if model:
        cmd.extend(["--model", model])
    return _run_cmd(cmd)


def _run_single_video(url: str, gpu: bool = False, model: str | None = None) -> int:
    """Single YouTube video → ingest + compile."""
    print("  🎬 Vídeo detectado")
    print("  → Ingerindo + compilando\n")
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "ingest.py"), url, "--compile"]
    if gpu:
        cmd.append("--gpu")
    if model:
        cmd.extend(["--model", model])
    return _run_cmd(cmd)


def _run_playlist(url: str, workers: int = 1, max_videos: int | None = None,
                  gpu: bool = False, model: str | None = None) -> int:
    """Playlist/channel → ingest batch + compile batch."""
    print("  📺 Playlist/canal detectado")
    if workers > 1:
        print(f"  ⚡ Workers: {workers}")
    if max_videos:
        print(f"  📊 Máximo: {max_videos} vídeos")
    print("  → Ingerindo + compilando\n")

    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "ingest.py"),
           "--playlist", url, "--compile"]
    if workers > 1:
        cmd.extend(["--workers", str(workers)])
    if max_videos:
        cmd.extend(["--max", str(max_videos)])
    if gpu:
        cmd.append("--gpu")
    if model:
        cmd.extend(["--model", model])
    return _run_cmd(cmd)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="Cola um link, eu resolvo — ingest + compile automático",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  sopx run https://youtube.com/watch?v=ABC123\n"
            "  sopx run https://youtube.com/playlist?list=XYZ\n"
            "  sopx run https://youtube.com/@channel\n"
            "  sopx run ./meu-video.mp4\n"
            "  sopx run ./audio.mp3              # transcreve + compila\n"
            "  sopx run ./livro.pdf              # compila direto\n"
            "  sopx run ./transcript.srt         # compila direto\n"
            "  sopx run URL --workers 4          # paralelo\n"
            "  sopx run URL --max 10 --gpu       # Colab GPU, 10 vídeos\n"
        ),
    )
    parser.add_argument("source", help="URL do YouTube ou caminho local")
    parser.add_argument("--workers", type=int, default=1,
                        help="Workers paralelos para playlist (default: 1)")
    parser.add_argument("--max", type=int, default=None,
                        help="Máximo de vídeos para playlist")
    parser.add_argument("--gpu", action="store_true",
                        help="Forçar Colab GPU")
    parser.add_argument("--model", default=None,
                        help="Modelo whisper (tiny/base/small/medium/large-v3)")

    args = parser.parse_args(argv)
    rc = run_source(args.source, workers=args.workers, max_videos=args.max,
                    gpu=args.gpu, model=args.model)
    sys.exit(rc)


if __name__ == "__main__":
    main()
