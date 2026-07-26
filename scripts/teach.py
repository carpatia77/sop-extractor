#!/usr/bin/env python3
"""Teach CLI — sopx teach interface.

Commands:
    sopx teach start <skill_dir>              Start/resume teach session
    sopx teach status <skill_dir>             Show session status
    sopx teach session <skill_dir> --session N  Run specific session
    sopx teach close <skill_dir>              Complete current session
"""
from __future__ import annotations

import argparse
import sys

from teach.session_manager import (
    start_session,
    get_current_session,
    complete_session,
    print_status,
)
from teach.session_1_pergunta import generate_pergunta_prompt
from teach.session_2_contexto import generate_contexto_prompt
from teach.session_3_analise import generate_analise_prompt
from teach.session_4_sintese import generate_sintese_prompt
from teach.session_5_conclusoes import generate_conclusoes_prompt
from teach.session_6_aplicacao import generate_aplicacao_prompt


SESSION_PROMPTS = {
    1: generate_pergunta_prompt,
    2: generate_contexto_prompt,
    3: generate_analise_prompt,
    4: generate_sintese_prompt,
    5: generate_conclusoes_prompt,
    6: generate_aplicacao_prompt,
}


def cmd_start(args):
    """Start or resume teach session."""
    session_info = start_session(args.skill_dir, args.session)
    num = session_info["session_number"]
    print(f"\n{'='*50}")
    print(f"  SESSÃO {num}: {session_info['name']}")
    print(f"  {session_info['description']}")
    print(f"{'='*50}")
    print(f"  Input: {session_info['input']}")
    print(f"  Output: {session_info['output']}")
    print(f"  Gate: {session_info['gate']}")
    if session_info.get("is_resume"):
        print("  (retomando sessao anterior)")
    print()

    # Show prompt
    prompt_fn = SESSION_PROMPTS.get(num)
    if prompt_fn:
        print(prompt_fn(args.skill_dir))


def cmd_status(args):
    """Show teach status."""
    print_status(args.skill_dir)


def cmd_complete(args):
    """Complete current session."""
    current = get_current_session(args.skill_dir)
    if current == 0:
        print("Todas as sessoes ja foram completadas!")
        return
    try:
        next_session = complete_session(args.skill_dir, current)
        if next_session == 0:
            print(f"Sessao {current} completada! Todas as 6 sessoes finalizadas.")
        else:
            print(f"Sessao {current} completada. Proxima: sessao {next_session}")
    except ValueError as e:
        print(f"Erro: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="sopx teach — Ensino interativo Método Hebraico",
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando")

    # start
    start_parser = subparsers.add_parser("start", help="Iniciar sessao de ensino")
    start_parser.add_argument("skill_dir", help="Diretorio do skill")
    start_parser.add_argument("--session", type=int, default=None,
                              help="Sessao especifica (1-6)")

    # status
    status_parser = subparsers.add_parser("status", help="Ver status do ensino")
    status_parser.add_argument("skill_dir", help="Diretorio do skill")

    # complete
    complete_parser = subparsers.add_parser("complete", help="Completar sessao atual")
    complete_parser.add_argument("skill_dir", help="Diretorio do skill")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "start":
        cmd_start(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "complete":
        cmd_complete(args)


if __name__ == "__main__":
    main()
