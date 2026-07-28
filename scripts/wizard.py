#!/usr/bin/env python3
"""Wizard — interactive guided workflow for sop-extractor.

Reduces CLI friction by guiding users through common workflows:
  1. Compilar um livro/PDF
  2. Ingerir um vídeo do YouTube
  3. Ensinar um skill existente
  4. Ver status de um projeto

Usage:
    python scripts/wizard.py              # interactive mode
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Color helpers (ANSI)
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

SCRIPTS_DIR = Path(__file__).parent


def colored(text: str, color: str) -> str:
    """Wrap text in ANSI color codes."""
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{RESET}"


def prompt_choice(question: str, options: list[str]) -> int:
    """Show numbered options and return 1-based index.

    Raises SystemExit on EOF/non-TTY (no infinite loop).
    """
    if not sys.stdin.isatty():
        print(f"{question} (non-interactive, using default: 1)", file=sys.stderr)
        return 1

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
            print(f"  {colored('Digite um numero de 1 a ' + str(len(options)), YELLOW)}")
        except ValueError:
            print(f"  {colored('Digite um numero de 1 a ' + str(len(options)), YELLOW)}")
        except EOFError:
            return 1  # non-interactive fallback
        # KeyboardInterrupt propagates naturally


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
    print(f"\n  {colored('OK', GREEN)} {message}")


def print_warning(message: str) -> None:
    print(f"\n  {colored('! ', YELLOW)} {message}")


def print_error(message: str) -> None:
    print(f"\n  {colored('ERRO', RED)} {message}")


# ---------------------------------------------------------------------------
# Subprocess runner (replaces os.system — no shell injection)
# ---------------------------------------------------------------------------

def run_script(script_name: str, args: list[str], step: str = "") -> int:
    """Run a script via subprocess (list args, no shell).

    Returns returncode. Raises on non-zero if check=True.
    """
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)] + args
    if step:
        print(f"\n{colored(step, CYAN)}")
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except FileNotFoundError:
        print_error(f"Script nao encontrado: {script_name}")
        return 1


# ---------------------------------------------------------------------------
# Workflow: Compilar fonte
# ---------------------------------------------------------------------------

def wizard_compile() -> int:
    """Guided workflow for compiling a source file.

    Returns 0 on success, 1 on error.
    """
    print_header("COMPILAR FONTE -> SKILL")

    # Step 1: Source file
    print_step(1, 2, "Selecione a fonte")
    source = prompt_text("Caminho do arquivo (PDF, EPUB, TXT, SRT):")
    if not source:
        print_error("Nenhum arquivo informado.")
        return 1

    path = Path(source)
    if not path.exists():
        print_error(f"Arquivo nao encontrado: {source}")
        return 1

    # Step 2: Confirm and run
    print_step(2, 2, "Confirmacao")
    print(f"\n  Arquivo: {colored(str(path.name), GREEN)}")
    print(f"  Tamanho: {path.stat().st_size / 1024:.1f} KB")

    confirm = prompt_text("Confirmar compilacao? (s/n)", "s")
    if confirm.lower() != "s":
        print_warning("Compilacao cancelada.")
        return 1

    # Run scan + compile
    rc1 = run_script("preflight_scan.py", [str(path)], "Pre-flight scan")
    if rc1 != 0:
        print_error(f"Pre-flight scan falhou (exit {rc1})")
        return 1

    rc2 = run_script("compile.py", [str(path), "--batch"], "Compilacao")
    if rc2 != 0:
        print_error(f"Compilacao falhou (exit {rc2})")
        return 1

    print_success("Skill compilada com sucesso!")
    print(f"\n  Proximo passo: {colored('sopx teach start output/', GREEN)}<skill_dir>")
    return 0


# ---------------------------------------------------------------------------
# Workflow: Ingerir video
# ---------------------------------------------------------------------------

def wizard_ingest() -> int:
    """Guided workflow for ingesting a YouTube video or playlist.

    Returns 0 on success, 1 on error.
    """
    print_header("INGERIR VIDEO -> TRANSCRICAO")

    # Step 1: Source type
    print_step(1, 4, "Tipo de fonte")
    source_type = prompt_choice("O que deseja ingerir?", [
        "Video unico (URL ou arquivo)",
        "Playlist / canal inteiro (URL)",
    ])

    # Step 2: URL or file
    print_step(2, 4, "Fonte")
    if source_type == 1:
        source = prompt_text("URL do YouTube ou caminho do arquivo de video:")
    else:
        source = prompt_text("URL da playlist ou canal do YouTube:")
    if not source:
        print_error("Nenhuma fonte informada.")
        return 1

    # Step 3: Options
    print_step(3, 4, "Opcoes")
    extra_args = []

    if source_type == 2:
        max_vids = prompt_text("Maximo de videos (deixe vazio para todos):", "")
        if max_vids and max_vids.isdigit():
            extra_args.extend(["--max", max_vids])

        compile_after = prompt_choice("Compilar automaticamente apos ingestao?", [
            "Nao (so transcricao)",
            "Sim (ingest + compile automatico)",
        ])
        if compile_after == 2:
            extra_args.append("--compile")
    else:
        rescue = prompt_choice("Extrair frames de referencia visual?", [
            "Nao (so transcricao)",
            "Sim (extrair frames)",
        ])
        if rescue == 2:
            extra_args.append("--rescue-frames")

    # Step 4: Run
    print_step(4, 4, "Ingestao")

    args = [source] + extra_args
    rc = run_script("ingest.py", args, "Ingestao")
    if rc != 0:
        print_error(f"Ingestao falhou (exit {rc})")
        return 1

    print_success("Ingestao concluida!")
    if "--compile" in extra_args:
        print("\n  Pipeline completo: ingest + compile")
        print(f"  Skill final em: {colored('output/', GREEN)}")
    else:
        print(f"\n  Proximo passo: {colored('sopx compile output/', GREEN)}<video_dir>")
    return 0


# ---------------------------------------------------------------------------
# Workflow: Ensinar skill
# ---------------------------------------------------------------------------

def wizard_teach() -> int:
    """Guided workflow for teaching a skill.

    Returns 0 on success, 1 on error.
    """
    print_header("ENSINAR SKILL -> METODO HEBRAICO")

    # Step 1: Skill directory
    print_step(1, 4, "Diretorio do skill")
    skill_dir = prompt_text("Caminho do skill directory:")
    if not skill_dir or not Path(skill_dir).is_dir():
        print_error(f"Diretorio nao encontrado: {skill_dir}")
        return 1

    # Step 2: Check existing progress
    print_step(2, 4, "Progresso")
    from teach.session_manager import get_status, start_session, complete_session
    status = get_status(skill_dir)

    if status["completed"] == 6:
        print_warning("Todas as 6 sessoes ja foram completadas!")
        return 0

    print(f"  Sessao atual: {colored(str(status['current_session']), GREEN)}/6")
    print(f"  Progresso: {colored(str(status['progress_pct']) + '%', GREEN)}")

    # Step 3: Sessao 1 — coletar objetivo
    print_step(3, 4, "Sessao 1: Pergunta")
    user_goal = prompt_text("O que voce quer entender nesta obra?")
    if not user_goal:
        print_error("Objetivo e obrigatorio para iniciar.")
        return 1

    # Create task_contract (fecha o ciclo)
    from teach.session_1_pergunta import create_task_contract
    create_task_contract(skill_dir, user_goal)
    complete_session(skill_dir, 1)
    print_success("task_contract.json criado. Sessao 1 completa.")

    # Step 4: Mostrar proxima sessao
    print_step(4, 4, "Proxima sessao")
    session_info = start_session(skill_dir)
    num = session_info["session_number"]
    name = session_info["name"]
    desc = session_info["description"]
    gate = session_info["gate"]

    session_num = str(num)
    print(f"\n  {colored('Sessao ' + session_num + ': ' + name, GREEN)}")
    print(f"  {desc}")
    print(f"  Gate: {gate}")

    print(f"\n  Proximo passo: {colored(f'sopx teach start {skill_dir}', GREEN)}")
    return 0


# ---------------------------------------------------------------------------
# Workflow: Ver status
# ---------------------------------------------------------------------------

def wizard_status() -> int:
    """Show status of the workspace.

    Returns 0 on success.
    """
    print_header("STATUS DO PROJETO")

    # Check output directory
    output_dir = Path("output")
    if not output_dir.exists():
        print_warning("Nenhum diretorio output/ encontrado.")
        return 0

    # Count compilations
    comp_dir = output_dir / "compilation"
    compilations = list(comp_dir.glob("*.json")) if comp_dir.exists() else []
    compilations = [f for f in compilations if not f.name.startswith("run") and "semantic_field" not in f.name]

    # Count semantic fields
    sfs = list(comp_dir.glob("*.semantic_field.json")) if comp_dir.exists() else []

    # Count transcripts
    transcripts = list(output_dir.rglob("*.srt"))

    print(f"  Compilacoes: {colored(str(len(compilations)), GREEN)}")
    print(f"  Semantic Fields: {colored(str(len(sfs)), GREEN)}")
    print(f"  Transcricoes: {colored(str(len(transcripts)), GREEN)}")

    # Check teach status
    teach_dirs = list(output_dir.rglob("progress.json"))
    if teach_dirs:
        print("\n  Teach Mode:")
        for td in teach_dirs:
            from teach.session_manager import get_status
            skill_dir = str(td.parent.parent)
            status = get_status(skill_dir)
            print(f"    {skill_dir}: {status['completed']}/6 sessoes ({status['progress_pct']}%)")

    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="sopx wizard — assistente interativo",
    )
    parser.add_argument("--auto", action="store_true",
                        help="Modo automatico (detectar de args)")

    args = parser.parse_args()

    if args.auto:
        print("Modo automatico nao implementado ainda.")
        print("Use: python scripts/wizard.py")
        sys.exit(1)

    print_header("SOP-EXTRACTOR — ASSISTENTE")
    print(f"\n  {colored('Bem-vindo ao assistente do sop-extractor.', BOLD)}")
    print("  Vou guia-lo pelo fluxo ideal para sua necessidade.\n")

    choice = prompt_choice("O que voce quer fazer?", [
        "Compilar um livro/PDF em skill",
        "Ingerir um video do YouTube",
        "Ensinar um skill existente (Metodo Hebraico)",
        "Ver status do projeto",
    ])

    rc = 0
    if choice == 1:
        rc = wizard_compile()
    elif choice == 2:
        rc = wizard_ingest()
    elif choice == 3:
        rc = wizard_teach()
    elif choice == 4:
        rc = wizard_status()

    print(f"\n{'='*50}\n")
    sys.exit(rc)


if __name__ == "__main__":
    main()
