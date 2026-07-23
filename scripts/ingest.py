#!/usr/bin/env python3
"""Ingest command — download/transcribe video → SRT + text.

Usage:
    sopx ingest <URL_or_path> [--rescue-frames] [--output-dir <dir>]
                              [--model <whisper_model>] [--no-cache]
                              [--gpu] [--gpu-urls URL...]
                              [--status] [--check]
"""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def check_deps():
    """Print dependency status."""
    from sopx.ingest.pipeline import check_dependencies
    deps = check_dependencies()
    print("  Dependências de ingestão:")
    all_ok = True
    for name, available in deps.items():
        status = "✓" if available else "✗ não encontrado"
        print(f"    {name}: {status}")
        if not available:
            all_ok = False
    return all_ok


def show_status():
    """Show cache of processed sources."""
    from sopx.cache import CacheManager
    cache = CacheManager()
    entries = cache.entries()
    if not entries:
        print("  Nenhum vídeo processado ainda.")
        return
    print(f"  {len(entries)} vídeo(s) processado(s):\n")
    for e in entries:
        source = e.get("canonical_id", e.get("key", "?"))
        title = e.get("title", "")
        words = e.get("word_count", "?")
        ts = e.get("processed_at", "?")
        print(f"    {source}")
        if title:
            print(f"      título:   {title}")
        print(f"      palavras: {words}  |  processado: {ts}")
        print(f"      output:   {e.get('output_dir', '?')}")
        print()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Ingerir vídeo/URL → transcript + metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  sopx ingest https://youtube.com/watch?v=ABC123\n"
            "  sopx ingest ./meu-video.mp4\n"
            "  sopx ingest ./video.mp4 --rescue-frames\n"
            "  sopx ingest --playlist https://youtube.com/playlist?list=XYZ --max 10\n"
            "  sopx ingest https://youtube.com/watch?v=ABC --gpu  # gera notebook Colab\n"
            "  sopx ingest --status\n"
            "  sopx ingest --check\n"
        ),
    )
    parser.add_argument("source", nargs="?", help="URL ou caminho do vídeo")
    parser.add_argument("--output-dir", default=None, help="Diretório de saída (default: output/)")
    parser.add_argument("--model", default=None, help="Modelo whisper (tiny/base/small/medium/large-v3)")
    parser.add_argument("--rescue-frames", action="store_true",
                        help="Extrair frames em timestamps deictic (rescue direcionado)")
    parser.add_argument("--no-cache", action="store_true", help="Ignorar cache e reprocessar")
    parser.add_argument("--status", action="store_true", help="Mostrar cache de processados")
    parser.add_argument("--check", action="store_true", help="Verificar dependências instaladas")
    parser.add_argument("--playlist", default=None, help="URL de playlist/canal para processar em lote")
    parser.add_argument("--max", type=int, default=None, help="Máximo de vídeos no batch (default: todos)")
    parser.add_argument("--gpu", action="store_true",
                        help="Forçar geração de notebook Colab (pula roteamento)")
    parser.add_argument("--local", action="store_true",
                        help="Forçar execução local (pula roteamento)")
    parser.add_argument("--gpu-urls", nargs="+", default=None,
                        help="URLs extras para incluir no notebook GPU")

    args = parser.parse_args(argv)

    if args.check:
        ok = check_deps()
        return 0 if ok else 1

    if args.status:
        show_status()
        return 0

    # GPU mode: generate Colab notebook
    if args.gpu:
        from sopx.ingest.colab import generate_colab_notebook, open_in_colab

        urls = []
        if args.source:
            urls.append(args.source)
        if args.gpu_urls:
            urls.extend(args.gpu_urls)
        if args.playlist:
            # Extract video IDs from playlist
            print("  Buscando vídeos do playlist...", file=sys.stderr)
            import subprocess
            cmd = ["yt-dlp", "--flat-playlist", "--dump-json", "--no-download", args.playlist]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        import json
                        info = json.loads(line)
                        vid = info.get("id", "")
                        if vid:
                            urls.append(f"https://www.youtube.com/watch?v={vid}")
            if args.max:
                urls = urls[:args.max]

        if not urls:
            print("  Erro: forneça pelo menos uma URL com --gpu", file=sys.stderr)
            return 1

        model = args.model or "base"
        notebook_path = generate_colab_notebook(urls, model=model)
        open_in_colab(notebook_path)
        return 0

    if not args.source and not args.playlist:
        parser.print_help()
        return 1

    # --- Smart routing (unless --gpu or --local forced) ---
    if not args.gpu and not getattr(args, 'local', False):
        from sopx.ingest.router import (
            detect_input_type, check_local_hardware, recommend_approach,
            estimate_processing_time, print_routing_decision,
        )
        from sopx.ingest.colab import generate_colab_notebook, open_in_colab

        # Collect URLs
        urls = []
        if args.source:
            urls.append(args.source)
        if args.gpu_urls:
            urls.extend(args.gpu_urls)

        # Detect input type
        input_type = detect_input_type(args.source, args.playlist, urls if len(urls) > 1 else None)

        # Check hardware
        hardware = check_local_hardware()

        # Get video count and duration for estimates
        video_count = len(urls) if urls else 1
        total_duration = 0
        if urls:
            # Quick metadata fetch for duration estimate
            try:
                from sopx.ingest.adapters import YtDlpAdapter
                ytdlp = YtDlpAdapter()
                for url in urls[:5]:  # Sample first 5
                    try:
                        info = ytdlp.get_info(url)
                        total_duration += info.get("duration", 0)
                    except Exception:
                        pass
            except Exception:
                pass

        # Get recommendation
        recommendation = recommend_approach(input_type, hardware, video_count, total_duration)

        # Get time estimates
        estimates = None
        if total_duration > 0:
            estimates = estimate_processing_time(total_duration, hardware)

        # Print routing decision
        print_routing_decision(input_type, hardware, recommendation, estimates)

        # If Colab recommended, generate notebook
        if recommendation["approach"] == "colab":
            # Collect all URLs for notebook
            all_urls = list(urls)
            if args.playlist:
                print("  Buscando vídeos do playlist...", file=sys.stderr)
                import subprocess
                cmd = ["yt-dlp", "--flat-playlist", "--dump-json", "--no-download", args.playlist]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if line:
                            info = json.loads(line)
                            vid = info.get("id", "")
                            if vid:
                                all_urls.append(f"https://www.youtube.com/watch?v={vid}")
                if args.max:
                    all_urls = all_urls[:args.max]

            if all_urls:
                model = args.model or "base"
                notebook_path = generate_colab_notebook(all_urls, model=model)
                open_in_colab(notebook_path)
                return 0
            else:
                print("  ⚠ Nenhuma URL válida encontrada", file=sys.stderr)
                return 1

        # If local recommended, continue to local execution
        print("  ▶ Executando localmente...\n", file=sys.stderr)

    from sopx.config import ensure_config, get
    from sopx.cache import CacheManager
    from sopx.ingest.pipeline import IngestPipeline

    config = ensure_config()
    if args.model:
        config.setdefault("whisper", {})["model_size"] = args.model
    if args.no_cache:
        config["cache_enabled"] = False

    cache = CacheManager()
    pipeline = IngestPipeline(config=config, cache=cache)

    # Batch playlist mode
    if args.playlist:
        try:
            results = pipeline.ingest_playlist(
                args.playlist,
                output_base=args.output_dir,
                max_videos=args.max,
            )
            print(f"\n  Batch concluído: {len(results)} vídeos processados")
        except FileNotFoundError as e:
            print(f"Erro: {e}", file=sys.stderr)
            return 1
        except RuntimeError as e:
            print(f"Erro na ingestão: {e}", file=sys.stderr)
            return 1
        return 0

    try:
        result = pipeline.ingest(
            source=args.source,
            output_base=args.output_dir,
            rescue_frames=args.rescue_frames,
        )
    except FileNotFoundError as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"Dependência faltando: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"Erro na ingestão: {e}", file=sys.stderr)
        return 1

    if result.cached:
        print(f"  Cache hit — reutilizando output anterior")
    else:
        print(f"  Ingestão concluída!")

    print(f"    output:    {result.output_dir}")
    print(f"    SRT:       {result.srt}")
    print(f"    texto:     {result.text}")

    # Post-ingestion prompt
    print(f"\n  O que deseja fazer agora?\n")
    print(f"    [1] Extrair SOPs e Princípios Fundamentais")
    print(f"    [2] Gerar Mapa Semântico")
    print(f"    [3] Gerar Concept Graph do conhecimento")
    print(f"    [4] Manter apenas transcrições (fim)\n")

    try:
        choice = input("  Escolha (1-4): ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "4"

    if choice == "1":
        print(f"\n  → sopx scan {result.srt} --emit-prompt\n")
    elif choice == "2":
        print(f"\n  → Mapa Semântico: funcionalidade em desenvolvimento (Fase 1)")
        print(f"    Transcrição disponível em: {result.text}\n")
    elif choice == "3":
        print(f"\n  → Concept Graph: funcionalidade em desenvolvimento (Fase 1)")
        print(f"    Transcrição disponível em: {result.text}\n")
    else:
        print(f"\n  Transcrições salvas em: {result.output_dir}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
