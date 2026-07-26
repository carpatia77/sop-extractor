#!/usr/bin/env python3
"""Wizard — interactive guided workflow for sop-extractor.

Reduces CLI friction by guiding users through common workflows:
  1. Compilar um livro/PDF
  2. Ingerir um vídeo do YouTube
  3. Ensinar um skill existente
  4. Ver status de um projeto

Usage:
    python scripts/wizard.py              # interactive mode
    python scripts/wizard.py --auto       # auto-detect from args
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Color helpers (ANSI)
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def colored(text: str, color: str) -> str:
    """Wrap text in ANSI color codes."""
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{RESET}"


def prompt_choice(question: str, options: list[str]) -> int:
    """Show numbered options and return 1-based index."""
    print(f"\n{colored(question, BOLD)}")
    for i, opt in enumerate(options, 1):
        print(f"  {colored(str(i), CYAN)}) {opt}")
    print()

    while True:
        try:
            choice = input(f"  {colored('>', CYAN)} ").strip()
            idx = int(choice)
            if 1 <= idx <= len(options):
                return idx
        except (ValueError, EOFError):
            pass
        print(f"  {colored('Digite um número de 1 a ' + str(len(options)), YELLOW)}")


def prompt_text(question: str, default: str = "") -> str:
    """Show question and return text input."""
    suffix = f" [{default}]" if default else ""
    print(f"\n{colored(question + suffix, BOLD)}")
    try:
        answer = input(f"  {colored('>', CYAN)} ").strip()
        return answer or default
    except EOFError:
        return default


def print_header(title: str) -> None:
    """Print formatted header."""
    width = 50
    print(f"\n{'='*width}")
    print(f"  {colored(title, BOLD)}")
    print(f"{'='*width}")


def print_step(step: int, total: int, description: str) -> None:
    """Print step progress."""
    print(f"\n{colored(f'[{step}/{total}]', CYAN)} {description}")


def print_success(message: str) -> None:
    print(f"\n  {colored('✓', GREEN)} {message}")


def print_warning(message: str) -> None:
    print(f"\n  {colored('⚠', YELLOW)} {message}")


def print_error(message: str) -> None:
    print(f"\n  {colored('✗', RED)} {message}")


# ---------------------------------------------------------------------------
# Workflow: Compilar fonte
# ---------------------------------------------------------------------------

def wizard_compile():
    """Guided workflow for compiling a source file."""
    print_header("COMPILAR FONTE → SKILL")

    # Step 1: Source file
    print_step(1, 4, "Selecione a fonte")
    source = prompt_text("Caminho do arquivo (PDF, EPUB, TXT, SRT):")
    if not source or not os.path.exists(source):
        print_error(f"Arquivo não encontrado: {source}")
        return

    # Step 2: Content type
    print_step(2, 4, "Tipo de conteúdo")
    content_type = prompt_choice("Qual o tipo de conteúdo?", [
        "Técnico (decisões, procedimentos, regras)",
        "Literário (conceitos, ideias, argumentos)",
        "Misto (ambos)",
    ])
    type_map = {1: "technical", 2: "literary", 3: "mixed"}
    book_type = type_map[content_type]

    # Step 3: Depth
    print_step(3, 4, "Profundidade")
    depth = prompt_choice("Qual profundidade desejada?", [
        "Fundamentos (princípios, conceitos)",
        "Procedimentos (SOPs, passo-a-passo)",
        "Ambos (fundamentos + procedimentos)",
    ])
    depth_map = {1: "foundations", 2: "procedures", 3: "both"}
    depth_val = depth_map[depth]

    # Step 4: Confirm and run
    print_step(4, 4, "Confirmação")
    print(f"\n  Arquivo: {colored(source, GREEN)}")
    print(f"  Tipo: {colored(book_type, GREEN)}")
    print(f"  Profundidade: {colored(depth_val, GREEN)}")

    confirm = prompt_text("Confirmar compilação? (s/n)", "s")
    if confirm.lower() != "s":
        print_warning("Compilação cancelada.")
        return

    # Run
    print(f"\n{colored('Iniciando compilação...', CYAN)}")

    # Step 1: Scan
    print_step(1, 3, "Pre-flight scan")
    os.system(f"python3 scripts/preflight_scan.py '{source}'")

    # Step 2: Compile
    print_step(2, 3, "Compilação")
    os.system(f"python3 scripts/compile.py '{source}' --batch")

    # Step 3: Summary
    print_step(3, 3, "Concluído")
    print_success("Skill compilada com sucesso!")
    print(f"\n  Próximo passo: {colored('sopx teach start output/', GREEN)}<skill_dir>")


# ---------------------------------------------------------------------------
# Workflow: Ingerir vídeo
# ---------------------------------------------------------------------------

def wizard_ingest():
    """Guided workflow for ingesting a YouTube video."""
    print_header("INGERIR VÍDEO → TRANSCRIÇÃO")

    # Step 1: URL or file
    print_step(1, 3, "Fonte do vídeo")
    source = prompt_text("URL do YouTube ou caminho do arquivo de vídeo:")
    if not source:
        print_error("Nenhuma fonte informada.")
        return

    # Step 2: Options
    print_step(2, 3, "Opções")
    rescue = prompt_choice("Extrair frames de referência visual?", [
        "Não (só transcrição)",
        "Sim (extrair frames)",
    ])
    rescue_flag = "--rescue-frames" if rescue == 2 else ""

    # Step 3: Run
    print_step(3, 3, "Ingestão")
    print(f"\n{colored('Iniciando ingestão...', CYAN)}")

    cmd = f"python3 scripts/ingest.py '{source}' {rescue_flag}"
    os.system(cmd)

    print_success("Ingestão concluída!")
    print(f"\n  Próximo passo: {colored('sopx compile output/', GREEN)}<video_dir>")


# ---------------------------------------------------------------------------
# Workflow: Ensinar skill
# ---------------------------------------------------------------------------

def wizard_teach():
    """Guided workflow for teaching a skill."""
    print_header("ENSINAR SKILL → DEBATE SOCRATICO")

    # Step 1: Skill directory
    print_step(1, 3, "Diretório do skill")
    skill_dir = prompt_text("Caminho do skill directory:")
    if not skill_dir or not os.path.isdir(skill_dir):
        print_error(f"Diretório não encontrado: {skill_dir}")
        return

    # Step 2: Check existing progress
    print_step(2, 3, "Progresso")
    from teach.session_manager import get_status
    status = get_status(skill_dir)

    if status["completed"] == 6:
        print_warning("Todas as 6 sessões já foram completadas!")
        return

    print(f"  Sessão atual: {colored(str(status['current_session']), GREEN)}/6")
    print(f"  Progresso: {colored(str(status['progress_pct']) + '%', GREEN)}")

    # Step 3: Start session
    print_step(3, 3, "Iniciar sessão")
    from teach.session_manager import start_session
    session_info = start_session(skill_dir)
    num = session_info["session_number"]
    name = session_info["name"]
    desc = session_info["description"]
    gate = session_info["gate"]

    print(f"\n  {colored(f'Sessao {num}: {name}', GREEN)}")
    print(f"  {desc}")
    print(f"  Gate: {gate}")

    # Show prompt
    from teach.session_1_pergunta import generate_pergunta_prompt
    from teach.session_2_contexto import generate_contexto_prompt
    from teach.session_3_analise import generate_analise_prompt
    from teach.session_4_sintese import generate_sintese_prompt
    from teach.session_5_conclusoes import generate_conclusoes_prompt
    from teach.session_6_aplicacao import generate_aplicacao_prompt

    prompts = {
        1: generate_pergunta_prompt,
        2: generate_contexto_prompt,
        3: generate_analise_prompt,
        4: generate_sintese_prompt,
        5: generate_conclusoes_prompt,
        6: generate_aplicacao_prompt,
    }

    if num in prompts:
        print()
        print(prompts[num](skill_dir))

    print(f"\n  Próximo passo: {colored(f'sopx teach complete {skill_dir}', GREEN)}")


# ---------------------------------------------------------------------------
# Workflow: Ver status
# ---------------------------------------------------------------------------

def wizard_status():
    """Show status of the workspace."""
    print_header("STATUS DO PROJETO")

    # Check output directory
    output_dir = Path("output")
    if not output_dir.exists():
        print_warning("Nenhum diretório output/ encontrado.")
        return

    # Count compilations
    comp_dir = output_dir / "compilation"
    compilations = list(comp_dir.glob("*.json")) if comp_dir.exists() else []
    compilations = [f for f in compilations if not f.name.startswith("run") and "semantic_field" not in f.name]

    # Count semantic fields
    sfs = list(comp_dir.glob("*.semantic_field.json")) if comp_dir.exists() else []

    # Count transcripts
    transcripts = list(output_dir.rglob("*.srt"))

    print(f"  Compilações: {colored(str(len(compilations)), GREEN)}")
    print(f"  Semantic Fields: {colored(str(len(sfs)), GREEN)}")
    print(f"  Transcrições: {colored(str(transcripts.__len__()), GREEN)}")

    # Check teach status
    teach_dirs = list(output_dir.rglob("progress.json"))
    if teach_dirs:
        print("\n  Teach Mode:")
        for td in teach_dirs:
            from teach.session_manager import get_status
            skill_dir = str(td.parent.parent)
            status = get_status(skill_dir)
            print(f"    {skill_dir}: {status['completed']}/6 sessões ({status['progress_pct']}%)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="sopx wizard — assistente interativo",
    )
    parser.add_argument("--auto", action="store_true",
                        help="Modo automático (detectar de args)")

    args = parser.parse_args()

    if args.auto:
        print("Modo automático não implementado ainda.")
        print("Use: python scripts/wizard.py")
        sys.exit(1)

    print_header("SOP-EXTRACTOR — ASSISTENTE")
    print(f"\n  {colored('Bem-vindo ao assistente do sop-extractor.', BOLD)}")
    print("  Vou guia-lo pelo fluxo ideal para sua necessidade.\n")

    choice = prompt_choice("O que você quer fazer?", [
        "Compilar um livro/PDF em skill",
        "Ingerir um vídeo do YouTube",
        "Ensinar um skill existente (Debate Socratico)",
        "Ver status do projeto",
    ])

    if choice == 1:
        wizard_compile()
    elif choice == 2:
        wizard_ingest()
    elif choice == 3:
        wizard_teach()
    elif choice == 4:
        wizard_status()

    print(f"\n{'='*50}\n")


if __name__ == "__main__":
    main()
