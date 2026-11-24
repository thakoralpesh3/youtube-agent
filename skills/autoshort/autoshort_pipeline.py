#!/usr/bin/env python3
"""
autoshort_pipeline.py - Autonomous CLI runner for creating high-retention faceless Shorts.

Usage:
    python3 autoshort_pipeline.py --topic "The Dopamine Reset Protocol"
    python3 autoshort_pipeline.py --topic "Stoic Mindset" --trilingual
    python3 autoshort_pipeline.py --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

# Setup root path to import core agent modules
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Switch to .venv python if running directly with system python
if sys.prefix == sys.base_prefix:
    _venv_py = REPO_ROOT / ".venv" / "bin" / "python3"
    if _venv_py.exists():
        os.execv(str(_venv_py), [str(_venv_py)] + sys.argv)

import config
from rich.console import Console
from rich.panel import Panel

console = Console()

def run_pipeline():
    parser = argparse.ArgumentParser(description="AutoShort Autonomous Video Creation Pipeline")
    parser.add_argument("--topic", type=str, default="", help="Custom topic or theme")
    parser.add_argument("--lang", type=str, choices=["en", "hi", "gu"], default="en", help="Language for single short")
    parser.add_argument("--trilingual", action="store_true", help="Generate 3 synchronized shorts in EN, HI, GU")
    parser.add_argument("--dry-run", action="store_true", help="Generate media locally without live publishing")
    parser.add_argument("--platform", type=str, choices=["youtube", "social", "all"], default="youtube", help="Target publishing platform")
    parser.add_argument("--content-type", type=str, choices=["shorts", "both", "videos"], default="shorts", help="Type of content to generate")
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]⚡ AUTOSHORT AUTONOMOUS PIPELINE[/bold cyan]\n"
        f"[dim]Topic: {args.topic or 'Autonomous Selection'} | Mode: {'Trilingual (EN, HI, GU)' if args.trilingual else args.lang.upper()} | Platform: {args.platform}[/dim]",
        border_style="cyan"
    ))

    from agent import YouTubeAgent
    agent = YouTubeAgent()

    if args.trilingual:
        console.print("\n[bold yellow]🚀 Initiating Trilingual Faceless Shorts Pipeline (EN, HI, GU)...[/bold yellow]")
        result = agent.run_trilingual(
            topic=args.topic if args.topic else None,
            dry_run=args.dry_run,
            target_platform=args.platform,
            content_type=args.content_type,
            force=True,
            resume=True
        )
    else:
        console.print(f"\n[bold yellow]🚀 Initiating Faceless Short Pipeline ({args.lang.upper()})...[/bold yellow]")
        result = agent.run(
            topic=args.topic if args.topic else None,
            dry_run=args.dry_run,
            content_type="shorts",
            resume=True
        )

    console.print("\n" + "=" * 65)
    status = result.get("status", "SUCCESS") if isinstance(result, dict) else "COMPLETE"
    console.print(f"🎉 [bold green]AUTOSHORT EXECUTION COMPLETE![/bold green] Status: [bold cyan]{status}[/bold cyan]")
    console.print("=" * 65)

if __name__ == "__main__":
    run_pipeline()
