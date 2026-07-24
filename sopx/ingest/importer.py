"""Import Colab output into the local pipeline.

Handles importing ZIP files or directories from Colab transcription
into the local cache and output structure.
"""
from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

from sopx.cache import CacheManager
from sopx.config import ensure_config, get


def validate_output_dir(video_dir: Path) -> dict | None:
    """Validate a video output directory has required files.

    Returns metadata dict if valid, None if invalid.
    """
    srt_file = video_dir / "transcript.srt"
    text_file = video_dir / "full_text.txt"
    meta_file = video_dir / "metadata.json"

    if not srt_file.exists():
        print(f"  ⚠ {video_dir.name}: transcript.srt não encontrado", file=sys.stderr)
        return None

    if not meta_file.exists():
        print(f"  ⚠ {video_dir.name}: metadata.json não encontrado", file=sys.stderr)
        return None

    try:
        metadata = json.loads(meta_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"  ⚠ {video_dir.name}: metadata.json inválido: {e}", file=sys.stderr)
        return None

    # Ensure required fields
    if "video_id" not in metadata:
        metadata["video_id"] = video_dir.name

    return metadata


def import_zip(zip_path: Path, output_base: Path | None = None) -> list[dict]:
    """Import a ZIP file from Colab.

    Args:
        zip_path: Path to the ZIP file.
        output_base: Base directory for outputs (default: output/).

    Returns:
        List of metadata dicts for imported videos.
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP não encontrado: {zip_path}")

    # Ensure output_base is a Path (CLI passes string)
    if output_base is None:
        config = ensure_config()
        output_base = Path(get(config, "output_dir", "output/"))
    else:
        output_base = Path(output_base)

    # Extract ZIP to temp directory (use mkdtemp for isolation)
    import tempfile
    temp_dir = Path(tempfile.mkdtemp(prefix="sopx_import_"))

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)

        # Find video directories
        imported = []
        for item in temp_dir.rglob("*"):
            if item.is_dir():
                metadata = validate_output_dir(item)
                if metadata:
                    imported.append((item, metadata))

        if not imported:
            print("  ⚠ Nenhum vídeo válido encontrado no ZIP", file=sys.stderr)
            return []

        # Copy to output directory and register in cache
        cache = CacheManager()
        results = []

        for video_dir, metadata in imported:
            video_id = metadata.get("video_id", video_dir.name)
            # Use consistent cache key with pipeline (sha256 hash)
            cache_key = CacheManager.key_for_url(video_id)
            dest = output_base / video_id
            dest.mkdir(parents=True, exist_ok=True)

            # Copy files
            for f in video_dir.glob("*"):
                if f.is_file():
                    shutil.copy2(f, dest / f.name)

            # Register in cache with consistent key
            cache.mark_done(
                key=cache_key,
                output_dir=str(dest),
                canonical_id=video_id,
                word_count=metadata.get("word_count", 0),
                title=metadata.get("title", ""),
            )

            print(f"  ✓ {video_id}: {metadata.get('word_count', 0)} palavras", file=sys.stderr)
            results.append(metadata)

        return results

    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


def import_directory(dir_path: Path, output_base: Path | None = None) -> list[dict]:
    """Import a directory from Colab.

    Args:
        dir_path: Path to the directory containing video outputs.
        output_base: Base directory for outputs (default: output/).

    Returns:
        List of metadata dicts for imported videos.
    """
    if not dir_path.exists():
        raise FileNotFoundError(f"Diretório não encontrado: {dir_path}")

    # Ensure output_base is a Path (CLI passes string)
    if output_base is None:
        config = ensure_config()
        output_base = Path(get(config, "output_dir", "output/"))
    else:
        output_base = Path(output_base)

    # Find video directories
    imported = []
    for item in dir_path.iterdir():
        if item.is_dir():
            metadata = validate_output_dir(item)
            if metadata:
                imported.append((item, metadata))

    # Also check if dir_path itself is a video directory
    if not imported:
        metadata = validate_output_dir(dir_path)
        if metadata:
            imported.append((dir_path, metadata))

    if not imported:
        print("  ⚠ Nenhum vídeo válido encontrado", file=sys.stderr)
        return []

    # Copy to output directory and register in cache
    cache = CacheManager()
    results = []

    for video_dir, metadata in imported:
        video_id = metadata.get("video_id", video_dir.name)
        # Use consistent cache key with pipeline (sha256 hash)
        cache_key = CacheManager.key_for_url(video_id)
        dest = output_base / video_id
        dest.mkdir(parents=True, exist_ok=True)

        # Copy files
        for f in video_dir.glob("*"):
            if f.is_file():
                shutil.copy2(f, dest / f.name)

        # Register in cache with consistent key
        cache.mark_done(
            key=cache_key,
            output_dir=str(dest),
            canonical_id=video_id,
            word_count=metadata.get("word_count", 0),
            title=metadata.get("title", ""),
        )

        print(f"  ✓ {video_id}: {metadata.get('word_count', 0)} palavras", file=sys.stderr)
        results.append(metadata)

    return results


def print_import_summary(results: list[dict]):
    """Print import summary."""
    if not results:
        print("\n  ⚠ Nenhum vídeo importado", file=sys.stderr)
        return

    total_words = sum(r.get("word_count", 0) for r in results)
    total_duration = sum(r.get("duration", 0) for r in results)

    print(f"\n  {'='*50}", file=sys.stderr)
    print(f"  IMPORTAÇÃO CONCLUÍDA", file=sys.stderr)
    print(f"  {'='*50}", file=sys.stderr)
    print(f"  Vídeos:    {len(results)}", file=sys.stderr)
    print(f"  Palavras:  {total_words}", file=sys.stderr)
    print(f"  Duração:   {total_duration/60:.1f} min", file=sys.stderr)
    print(f"  {'='*50}", file=sys.stderr)
    print(f"\n  Próximo passo:", file=sys.stderr)
    print(f"  sopx scan output/<video_id>/transcript.srt --emit-prompt", file=sys.stderr)
