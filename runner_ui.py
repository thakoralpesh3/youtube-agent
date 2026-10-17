#!/usr/bin/env python3
"""
Interactive UI Runner with Live Progress & User Control Center for YouTube Automation Agent.
Launched directly from Desktop / Taskbar shortcuts or terminal.
"""

import argparse
import select
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.prompt import Prompt

import config
from agent import YouTubeAgent
from generator.script_generator import EXPANDED_GROWTH_THEMES
from growth.growth_engine import GrowthEngine
from growth.self_healer import SelfHealer
from youtube.auth import YouTubeAuth

console = Console()

STEPS = [
    ("Step 1", "📝 Script & Viral Hook Generation"),
    ("Step 2", "🎙️ Neural Voice Synthesis & Word Sync"),
    ("Step 3", "🎨 Visual Scenes Generation (9:16 & 16:9)"),
    ("Step 4", "🎬 Video Assembly & Captions Burn-in"),
    ("Step 5", "📤 YouTube Shorts Upload & Publishing"),
    ("Step 6", "🌟 16:9 Standard Video & Custom Thumbnail"),
]


def render_ui(current_step: int, overall_pct: int, status_message: str, step_details: dict) -> Panel:
    table = Table(show_header=True, header_style="bold cyan", expand=True, box=None)
    table.add_column("Step", width=10)
    table.add_column("Pipeline Stage", width=38)
    table.add_column("Status", width=22)

    for idx, (s_name, s_title) in enumerate(STEPS, 1):
        if idx < current_step:
            status = "[bold green]✓ COMPLETED[/bold green]"
            stage_style = "[white]" + s_title + "[/white]"
        elif idx == current_step:
            status = f"[bold yellow]▶ IN PROGRESS ({overall_pct}%)[/bold yellow]"
            stage_style = "[bold yellow]" + s_title + "[/bold yellow]"
        else:
            status = "[dim]• PENDING[/dim]"
            stage_style = "[dim]" + s_title + "[/dim]"

        table.add_row(f"[cyan]{s_name}[/cyan]", stage_style, status)

    bar_width = 38
    filled = int(bar_width * (overall_pct / 100))
    bar_str = "█" * filled + "░" * (bar_width - filled)
    progress_bar = f"[bold cyan][{bar_str}] {overall_pct}%[/bold cyan]"

    content = Table.grid(padding=(0, 1))
    content.add_row(table)
    content.add_row(Text(""))
    content.add_row(Text.from_markup(f"[bold white]Overall Progress:[/bold white] {progress_bar}"))
    content.add_row(Text.from_markup(f"[bold magenta]Current Activity:[/bold magenta] [white]{status_message}[/white]"))

    return Panel(
        content,
        title="[bold red]▶ YouTube Creator Agent - Live Progress[/bold red]",
        border_style="bright_blue",
        padding=(1, 2),
    )


def handle_model_selection():
    console.clear()
    current_model = config.GEMINI_MODEL
    console.print(
        Panel.fit(
            "[bold cyan]🤖 AI MODEL SELECTION & TIER CONFIGURATION[/bold cyan]\n"
            f"[yellow]Current Active Model:[/yellow] [bold white]{current_model}[/bold white]\n"
            "[dim]Prioritizes your selected model for YouTube Shorts and Social Media Stories creation.[/dim]",
            border_style="cyan",
        )
    )
    console.print("  [bold cyan][1][/bold cyan] 🌟 [bold green]Auto-Latest[/bold green] (Dynamically query and select latest Gemini model)")
    console.print("  [bold cyan][2][/bold cyan] 🚀 [bold magenta]Gemini 4 Argon[/bold magenta] (gemini-4-argon) [Google Flagship Reasoning Engine]")
    console.print("  [bold cyan][3][/bold cyan] ⚡ [bold white]Gemini 3.8 Flash[/bold white] (gemini-3.8-flash)")
    console.print("  [bold cyan][4][/bold cyan] ⚡ [bold white]Gemini 3.7 Flash[/bold white] (gemini-3.7-flash)")
    console.print("  [bold cyan][5][/bold cyan] ⚡ [bold white]Gemini 3.6 Flash[/bold white] (gemini-3.6-flash)")
    console.print("  [bold cyan][6][/bold cyan] ⚡ [bold white]Gemini 3.5 Flash[/bold white] (gemini-3.5-flash)")
    console.print("  [bold cyan][7][/bold cyan] 🧠 [bold white]Gemini 3.1 Pro Preview[/bold white] (gemini-3.1-pro-preview)")
    console.print("  [bold cyan][8][/bold cyan] ✍️  [bold white]Enter Custom Model Name[/bold white]\n")

    m_choice = Prompt.ask("👉 Select model option", default="1")
    model_map = {
        "1": None,
        "2": "gemini-4-argon",
        "3": "gemini-3.8-flash",
        "4": "gemini-3.7-flash",
        "5": "gemini-3.6-flash",
        "6": "gemini-3.5-flash",
        "7": "gemini-3.1-pro-preview",
    }
    if m_choice in model_map:
        selected = model_map[m_choice]
    elif m_choice == "8":
        selected = Prompt.ask("Enter custom model name (e.g. gemini-4-argon, gemini-3.8-flash)")
    else:
        selected = None

    if selected:
        config.set_active_model(selected)
        console.print(f"\n[bold green]✅ Model switched successfully to:[/bold green] [bold cyan]{selected}[/bold cyan]")
    else:
        from growth.model_resolver import get_latest_gemini_model, set_runtime_model
        set_runtime_model(None)
        latest = get_latest_gemini_model(force_refresh=True)
        config.set_active_model(latest)
        console.print(f"\n[bold green]✅ Reset to Auto-Latest model:[/bold green] [bold cyan]{latest}[/bold cyan]")

    Prompt.ask("\nPress Enter to return")


def interactive_menu() -> tuple[str, Optional[str], Optional[str], bool, str]:
    """Displays the interactive menu and returns (action, topic, niche, dry_run, target_platform)."""
    while True:
        console.clear()
        console.print(
            Panel.fit(
                "[bold red]🎬 YOUTUBE CREATOR AI - INTERACTIVE CONTROL CENTER[/bold red]\n"
                f"[cyan]Channel Niche:[/cyan] {config.DEFAULT_NICHE}\n"
                f"[cyan]Active AI Model:[/cyan] [bold yellow]{config.GEMINI_MODEL}[/bold yellow] | "
                f"[cyan]Target:[/cyan] [bold green]{config.YOUTUBE_PRIVACY_STATUS.upper()}[/bold green]\n"
                f"[cyan]Category ID:[/cyan] {config.DEFAULT_CATEGORY_ID} (Education/Self-Improvement)",
                border_style="red",
            )
        )

        console.print("[bold yellow]Choose an option:[/bold yellow]\n")
        console.print("  [bold cyan][1][/bold cyan] 🔴 [bold white]YouTube Creation[/bold white] (Shorts [EN, HI, GU] + Standard 16:9 Video & Thumbnail)")
        console.print("  [bold cyan][2][/bold cyan] 🌐 [bold white]Social Media Stories Only[/bold white] (Upload to Instagram, Facebook & WhatsApp)")
        console.print("  [bold cyan][3][/bold cyan] 🚀 [bold white]All-in-One Multi-Platform[/bold white] (YouTube Shorts & Videos + IG + FB + WA)")
        console.print("  [bold cyan][4][/bold cyan] ✍️  [bold white]Enter Custom Topic[/bold white] (Generates Shorts + 16:9 Video)")
        console.print("  [bold cyan][5][/bold cyan] 🎭 [bold white]Choose Content Pillar[/bold white] (Pick from high-performance growth themes)")
        console.print("  [bold cyan][6][/bold cyan] 🧪 [bold white]Test Run (Dry Run)[/bold white] (Generates local videos without uploading)")
        console.print("  [bold cyan][V][/bold cyan] 🎬 [bold yellow]Standard YouTube Video Only[/bold yellow] (16:9 Landscape Video + Custom Thumbnail)")
        console.print("  [bold cyan][7][/bold cyan] 🔑 [bold white]Connect Accounts[/bold white] (YouTube, Instagram, Facebook & WhatsApp)")
        console.print("  [bold cyan][8][/bold cyan] 🛡️  [bold white]Self-Diagnose & Auto-Repair[/bold white] (Audit APIs, tokens & media engines)")
        console.print("  [bold cyan][9][/bold cyan] 📈 [bold white]Channel Growth Intelligence[/bold white] (Inspect winning hooks & memory)")
        console.print("  [bold cyan][M][/bold cyan] 🤖 [bold yellow]Switch / Configure AI Model[/bold yellow] (Current: " + config.GEMINI_MODEL + ")")
        console.print("  [bold cyan][F][/bold cyan] 🎉 [bold yellow]Chamunda Automobile Festival Campaign[/bold yellow] (Royal Enfield Stories on IG, FB & WA)")
        console.print("  [bold cyan][S][/bold cyan] 🛡️  [bold white]Cybersecurity Sentinel & Anti-Hacker Shield[/bold white] (Audit & Harden)")
        console.print("  [bold cyan][E][/bold cyan] 💡 [bold white]AI Creative Evolution & Surprise Ideas[/bold white] (Brainstorm Breakthroughs)")
        console.print("  [bold cyan][R][/bold cyan] 🔄 [bold yellow]Retry Stored Social Stories[/bold yellow] (Auto-Retry Pending IG, FB & WA Stories)")
        console.print("  [bold cyan][G][/bold cyan] 🌐 [bold yellow]Sync Codebase to GitHub[/bold yellow] (Auto-Commit & Push All Antigravity Updates)")
        console.print("  [bold cyan][0][/bold cyan] 🚪 [bold dim]Exit[/bold dim]\n")

        choice = Prompt.ask("👉 Enter choice", default="1")

        if choice.strip().upper() == "M":
            handle_model_selection()
            continue
        if choice.strip().upper() == "V":
            return "video_only", None, None, False, "youtube"
        if choice.strip().upper() == "F":
            return "festival", None, None, False, "social"
        if choice.strip().upper() == "S":
            return "security", None, None, False, "all"
        if choice.strip().upper() == "E":
            return "evolution", None, None, False, "all"
        if choice.strip().upper() == "R":
            return "retry_social", None, None, False, "social"
        if choice.strip().upper() == "G":
            return "sync_github", None, None, False, "all"

    if choice == "1":
        return "trilingual", None, None, False, "youtube"
    elif choice == "2":
        return "trilingual", None, None, False, "social"
    elif choice == "3":
        return "trilingual", None, None, False, "all"
    elif choice == "4":
        custom_topic = Prompt.ask("\n💡 [bold green]Enter your custom video topic[/bold green]")
        return "trilingual", custom_topic, None, False, "all"
    elif choice == "5":
        console.print("\n[bold yellow]Available Theme Pillars:[/bold yellow]")
        for i, theme in enumerate(EXPANDED_GROWTH_THEMES, 1):
            console.print(f"  [cyan]{i:2d}[/cyan]. {theme}")
        idx_str = Prompt.ask("\n👉 Select pillar number", default="1")
        try:
            chosen_pillar = EXPANDED_GROWTH_THEMES[int(idx_str) - 1]
            return "trilingual", chosen_pillar, None, False, "all"
        except Exception:
            return "trilingual", None, None, False, "all"
    elif choice == "6":
        return "trilingual", None, None, True, "all"
    elif choice == "7":
        return "auth", None, None, False, "all"
    elif choice == "8":
        return "heal", None, None, False, "all"
    elif choice == "9":
        return "growth", None, None, False, "all"
    elif choice == "0":
        sys.exit(0)
    else:
        return "trilingual", None, None, False, "all"


def handle_festival_campaign(dry_run: bool = False):
    console.clear()
    console.print(
        Panel.fit(
            "[bold yellow]🎉 CHAMUNDA AUTOMOBILE - AUTONOMOUS FESTIVAL CAMPAIGN[/bold yellow]\n"
            "[bold white]Specializes in Royal Enfield Only[/bold white]\n"
            "[cyan]Target Platforms:[/cyan] Instagram (Stories & Reels), Facebook (Stories), WhatsApp (Status)\n"
            "[cyan]Outputs:[/cyan] High-Res 9:16 Festive Poster + Synchronized Video (Edge-TTS + Ducked Music)",
            border_style="yellow",
        )
    )
    from syndication.festival_agent import FestivalSocialAgent
    from syndication.festival_detector import FestivalDetector
    detector = FestivalDetector(model_name=config.GEMINI_MODEL)
    today_fest = detector.get_festival_for_date()

    target_fest = today_fest
    if not target_fest:
        console.print("\n[yellow]No pre-scheduled festival detected for today.[/yellow]")
        console.print("Upcoming Festivals in next 60 days:")
        upcoming = detector.get_upcoming_festivals(days=60)
        for idx, u in enumerate(upcoming, 1):
            console.print(f"  [cyan][{idx}][/cyan] {u.date_str}: {u.festival_name}")
        console.print(f"  [cyan][0][/cyan] Generate general Royal Enfield Blessing Campaign for Today")
        sel = Prompt.ask("\n👉 Select festival to run/preview", default="1" if upcoming else "0")
        if sel != "0" and int(sel) <= len(upcoming):
            target_fest = upcoming[int(sel) - 1]

    agent = FestivalSocialAgent(model_name=config.GEMINI_MODEL)
    with console.status("[bold green]Generating and uploading Chamunda Automobile Festival Campaign..."):
        res = agent.run_festival_campaign(target_festival=target_fest, dry_run=dry_run, force_upload=True)

    console.print(f"\n[bold green]✅ Campaign {res.get('status')}![/bold green]")
    console.print(f"  • Festival: [bold yellow]{res.get('festival')}[/bold yellow]")
    console.print(f"  • Poster:   [cyan]{res.get('poster')}[/cyan]")
    console.print(f"  • Video:    [cyan]{res.get('video')}[/cyan]")
    console.print(f"  • Uploads:  [bold white]{res.get('uploads')}[/bold white]")
    input("\nPress Enter to exit...")


def handle_security_audit(auto_harden: bool = True):
    console.clear()
    console.print(
        Panel.fit(
            "[bold red]🛡️  CYBERSECURITY SENTINEL & ANTI-HACKER SHIELD[/bold red]\n"
            "[bold white]Autonomous Code Integrity, Credential Defense & Threat Hunting Engine[/bold white]\n"
            "[cyan]Vault Protections:[/cyan] Credential Permissions (0600/0700) • Git Leak Shield • FIM Code Integrity (SHA-256)\n"
            "[cyan]Threat Scanners:[/cyan] Reverse Shell & Backdoor Scanner • Network Port Exposure Audit • Dynamic Sanitization",
            border_style="red",
        )
    )
    from security.security_guard import SecurityGuard
    guard = SecurityGuard()

    with console.status("[bold green]Executing comprehensive 5-point cybersecurity audit..."):
        report = guard.run_security_audit(auto_harden=auto_harden)

    status = report.get("overall_status", "UNKNOWN")
    findings = report.get("findings", {})

    status_color = "green" if status == "SECURE" else ("yellow" if status == "WARNING" else "red")
    console.print(f"\n[bold {status_color}]Overall Security Posture: {status}[/bold {status_color}] (Audit Log: output/security_audit.log)\n")

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Security Pillar", width=32)
    table.add_column("Status", width=22)
    table.add_column("Details & Telemetry", width=46)

    # 1. Vault Hardening
    vh = findings.get("vault_hardening", {})
    vh_stat = vh.get("status", "SKIPPED")
    vh_style = "[bold green]HARDENED (0600/0700)[/bold green]" if vh_stat == "HARDENED" else f"[dim]{vh_stat}[/dim]"
    table.add_row(
        "1. Credential Vault Permissions",
        vh_style,
        f"Protected {vh.get('files_hardened', 0)} secrets & {vh.get('dirs_hardened', 0)} profile dirs",
    )

    # 2. Git Shield
    gs = findings.get("git_shield", {})
    gs_stat = gs.get("status", "OK")
    gs_style = "[bold green]PROTECTED[/bold green]" if gs_stat == "PROTECTED" else f"[bold yellow]{gs_stat}[/bold yellow]"
    table.add_row(
        "2. Git Secret Leak Shield",
        gs_style,
        "Credentials, tokens & browser databases blocked in .gitignore",
    )

    # 3. File Integrity (FIM)
    ci = findings.get("code_integrity", {})
    ci_stat = ci.get("status", "OK")
    if ci_stat == "VERIFIED":
        ci_style = "[bold green]VERIFIED (SHA-256)[/bold green]"
        ci_msg = ci.get("message", "All codebase hashes verified intact")
    elif ci_stat == "BASELINE_CREATED":
        ci_style = "[bold cyan]BASELINE SEALED[/bold cyan]"
        ci_msg = ci.get("message", "Cryptographic baseline sealed")
    else:
        ci_style = "[bold red]COMPROMISED[/bold red]"
        ci_msg = f"Mod: {ci.get('modified', [])}, Added: {ci.get('added', [])}"
    table.add_row("3. Cryptographic Code Integrity", ci_style, ci_msg)

    # 4. Malware & Backdoor Signatures
    ms = findings.get("malware_scan", {})
    ms_stat = ms.get("status", "CLEAN")
    if ms_stat == "CLEAN":
        ms_style = "[bold green]CLEAN (0 Threats)[/bold green]"
        ms_msg = f"Scanned {ms.get('scanned_files', 0)} files for reverse shells & backdoors"
    else:
        ms_style = "[bold red]THREAT DETECTED[/bold red]"
        ms_msg = f"Detections: {len(ms.get('detections', []))} malicious signatures"
    table.add_row("4. Malicious Signature Scan", ms_style, ms_msg)

    # 5. Network Port Exposure
    ns = findings.get("network_scan", {})
    ns_stat = ns.get("status", "SECURE")
    if ns_stat == "SECURE":
        ns_style = "[bold green]SECURE[/bold green]"
        ns_msg = ns.get("message", "All listening sockets bound safely")
    else:
        ns_style = "[bold yellow]WARNING[/bold yellow]"
        ns_msg = f"Public listeners detected: {len(ns.get('public_listeners', []))}"
    table.add_row("5. Network Surface & Ports", ns_style, ns_msg)

    console.print(table)

    console.print("\n[bold cyan]🔧 Autonomous Defensive Capabilities Active:[/bold cyan]")
    console.print("  • Hourly background audits running via [bold white]scheduler.py[/bold white]")
    console.print("  • System boot pre-flight hardening active in [bold white]autostart.sh[/bold white]")
    console.print("  • Critical desktop alerts via [bold white]notify-send[/bold white] upon threat detection")

    input("\nPress Enter to exit...")


def handle_evolution_center():
    console.clear()
    from growth.evolution_engine import EvolutionEngine
    ee = EvolutionEngine()
    journal = ee.load_journal()
    level_name = journal.get("level_name", "Level 2: Creative Explorer")
    score = journal.get("creative_score", 140)

    console.print(
        Panel.fit(
            "[bold magenta]💡 AI CREATIVE EVOLUTION & SURPRISE BRAIN[/bold magenta]\n"
            f"[cyan]Evolutionary Status:[/cyan] [bold yellow]{level_name}[/bold yellow] | [cyan]Creative Score:[/cyan] [bold green]{score}[/bold green]\n"
            "[bold white]Autonomous Breakthrough Ideation & Winning Formula Discovery[/bold white]\n"
            "[dim]The AI continuously evolves beyond static routines to surprise you with high-potential viral concepts.[/dim]",
            border_style="magenta",
        )
    )

    with console.status("[bold cyan]Querying Creative Brain for surprise sparks..."):
        sparks = ee.generate_surprise_sparks(force_refresh=False)

    console.print("\n[bold yellow]✨ Current Surprise Ideas Formulated by AI:[/bold yellow]\n")
    for idx, spark in enumerate(sparks, 1):
        cat = spark.get("category", "idea").upper()
        title = spark.get("title", "Untitled Idea")
        platform = spark.get("target_platform", "Multi-Platform")
        concept = spark.get("concept", "")
        surprise = spark.get("surprise_factor", "")

        spark_grid = Table.grid(padding=(0, 1))
        spark_grid.add_row("[bold cyan]Target:[/bold cyan]", f"[bold white]{platform}[/bold white]")
        spark_grid.add_row("[bold cyan]Premise:[/bold cyan]", f"[white]{concept}[/white]")
        spark_grid.add_row("[bold magenta]✨ Surprise Twist:[/bold magenta]", f"[italic yellow]{surprise}[/italic yellow]")

        console.print(
            Panel(
                spark_grid,
                title=f"[bold green][{idx}] {title} ({cat})[/bold green]",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    console.print("\n[bold cyan]Action Options:[/bold cyan]")
    console.print("  [bold green][1-3][/bold green] 🚀 Bring selected idea to life immediately (Generate & Upload)")
    console.print("  [bold yellow][R][/bold yellow]   ✨ Force Brainstorm New Surprises (Query Gemini)")
    console.print("  [bold dim][0][/bold dim]   🚪 Return to Main Menu\n")

    sel = Prompt.ask("👉 Select action", default="1")
    if sel.strip().upper() == "R":
        with console.status("[bold yellow]Synthesizing fresh creative sparks..."):
            ee.generate_surprise_sparks(force_refresh=True)
        handle_evolution_center()
        return
    elif sel.strip() in ["1", "2", "3"]:
        idx = int(sel.strip()) - 1
        if idx < len(sparks):
            target_spark = sparks[idx]
            console.print(f"\n[bold green]🚀 Launching immediate production for: '{target_spark.get('title')}'...[/bold green]")
            res = ee.execute_spark_idea(target_spark.get("id"))
            console.print(f"[bold cyan]Status:[/bold cyan] {res.get('message')}")
            input("\nPress Enter to return...")
            return
    elif sel.strip() == "0":
        return


def handle_social_retry():
    console.clear()
    from syndication.social_queue import SocialQueueManager
    qm = SocialQueueManager()
    qm.recover_stranded_failed_files()
    pending = qm.get_pending_items()

    console.print(
        Panel.fit(
            "[bold cyan]🔄 STORED SOCIAL STORIES - RETRY MANAGER[/bold cyan]\n"
            f"[yellow]Pending Queue Count:[/yellow] [bold white]{len(pending)} item(s)[/bold white]\n"
            "[dim]Retries stored media specifically on failed platforms (Instagram, Facebook & WhatsApp).[/dim]",
            border_style="cyan",
        )
    )

    if not pending:
        console.print("\n[bold green]✨ All platforms are up to date! No pending social stories found in queue.[/bold green]")
        input("\nPress Enter to return...")
        return

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("ID", width=22)
    table.add_column("Media File", width=28)
    table.add_column("Pending Platforms", width=24)
    table.add_column("Retries", width=10)

    for it in pending:
        table.add_row(
            it.get("id", ""),
            Path(it.get("media_path", "")).name[:28],
            ", ".join([p.title() for p in it.get("pending_platforms", [])]),
            str(it.get("retry_count", 0)),
        )
    console.print(table)

    confirm = Prompt.ask("\n🚀 Start uploading pending stories now?", choices=["y", "n"], default="y")
    if confirm == "y":
        with console.status("[bold cyan]Retrying pending social story uploads..."):
            res = qm.retry_all_pending()
        console.print(f"\n[bold green]✅ Retry process complete![/bold green] Newly completed: {res.get('completed_count', 0)}, Remaining pending: {res.get('remaining_pending', 0)}")
    input("\nPress Enter to continue...")


def run_pipeline():
    parser = argparse.ArgumentParser(description="YouTube Agent Runner UI")
    parser.add_argument("--platform", choices=["all", "youtube", "social"], default="all", help="Target platform: 'youtube' (YouTube only), 'social' (IG, FB, WA only), or 'all'")
    parser.add_argument("--dry-run", action="store_true", help="Generate video without uploading to YouTube")
    parser.add_argument("--topic", type=str, default=None, help="Specific topic for video")
    parser.add_argument("--niche", type=str, default=None, help="Custom niche")
    parser.add_argument("--interactive", action="store_true", help="Force interactive menu on startup")
    parser.add_argument("--no-resume", action="store_true", help="Force new run without resuming checkpoints")
    parser.add_argument("--trilingual", action="store_true", help="Generate 3 videos (English, Hindi, Gujarati) in 1 prompt and upload all 3")
    parser.add_argument("--festival", action="store_true", help="Run Chamunda Automobile Festival Campaign (Royal Enfield Stories & Status)")
    parser.add_argument("--security-audit", action="store_true", help="Run master 5-point cybersecurity audit & report")
    parser.add_argument("--security-harden", action="store_true", help="Harden file permissions & tighten secret shield")
    parser.add_argument("--surprise", action="store_true", help="Brainstorm fresh surprise ideas and execute from CLI")
    parser.add_argument("--evolution", action="store_true", help="Open AI Creative Evolution & Surprise Center")
    parser.add_argument("--retry-social", action="store_true", help="Retry all stored pending social stories on Instagram, Facebook & WhatsApp")
    parser.add_argument("--model", type=str, default=None, help="Explicitly specify or prioritize Gemini AI model (e.g. 'gemini-4-argon', 'gemini-3.8-flash')")
    args = parser.parse_args()

    if args.model:
        config.set_active_model(args.model)

    if args.retry_social:
        handle_social_retry()
        return

    if args.surprise or args.evolution:
        handle_evolution_center()
        return

    if args.security_audit or args.security_harden:
        handle_security_audit(auto_harden=True)
        return

    if args.festival:
        handle_festival_campaign(dry_run=args.dry_run)
        return

    topic = args.topic
    niche = args.niche
    dry_run = args.dry_run
    target_platform = args.platform
    is_trilingual = True

    # If no explicit action CLI flags provided, show a brief auto-start prompt where user can press any key for menu
    if not args.dry_run and not args.topic and not args.niche and not args.no_resume and not args.festival and not args.security_audit and not args.security_harden and not args.surprise and not args.evolution:
        target_label = "YouTube Shorts Only (EN + HI + GU)" if target_platform == "youtube" else "Social Media Stories Only (IG, FB, WA)" if target_platform == "social" else "All Platforms (YouTube + Social)"
        console.clear()
        console.print(
            Panel.fit(
                "[bold red]🎬 AUTONOMOUS CONTENT CREATOR AGENT[/bold red]\n"
                f"[cyan]Niche:[/cyan] {config.DEFAULT_NICHE}\n"
                f"[cyan]Target Platform:[/cyan] [bold green]{target_label}[/bold green]\n"
                f"[cyan]YouTube Target:[/cyan] [bold green]{config.YOUTUBE_PRIVACY_STATUS.upper()}[/bold green] | "
                f"[cyan]Category ID:[/cyan] {config.DEFAULT_CATEGORY_ID} (Education/Self-Improvement)\n"
                f"[magenta]🌐 Mode:[/magenta] [bold yellow]TRILINGUAL (English + Hindi + Gujarati)[/bold yellow]\n"
                f"[magenta]🧠 Self-Growth:[/magenta] [green]ACTIVE[/green] | "
                f"[magenta]🛡️ Self-Healing:[/magenta] [green]ACTIVE[/green] | "
                f"[magenta]🌐 Network Guard:[/magenta] [green]AUTO-RESUME READY[/green]",
                border_style="red",
            )
        )
        console.print(f"[cyan]🤖 Starting Autonomous Generation for [{target_label}] in 3 seconds...[/cyan]")
        console.print("[dim]Press [bold yellow][Enter][/bold yellow] or any key now for Interactive Control Menu...[/dim]\n")
        
        # Check for user input within 3 seconds
        rlist, _, _ = select.select([sys.stdin], [], [], 3.0)
        if rlist:
            sys.stdin.readline()
            action, topic, niche, dry_run, target_platform = interactive_menu()
            if action == "auth":
                console.print("\n[bold yellow]Select Account to Connect:[/bold yellow]")
                console.print("  [cyan][1][/cyan] 🔴 YouTube Channel (OAuth 2.0 Credentials)")
                console.print("  [cyan][2][/cyan] 🌐 Instagram, Facebook & WhatsApp (Open Firefox to Log In Once)")
                console.print("  [cyan][3][/cyan] ⚙️  Meta / WhatsApp API Keys (Configure in .env)")
                auth_choice = Prompt.ask("\n👉 Select", default="2")

                if auth_choice == "1":
                    auth = YouTubeAuth()
                    try:
                        auth.get_credentials()
                        console.print("[bold green]✅ YouTube authentication successful![/bold green]")
                        try:
                            from core.github_sync import sync_secrets_to_github
                            sec_res = sync_secrets_to_github()
                            if sec_res.get("status") == "SUCCESS":
                                console.print("[bold green]🔐 GitHub Actions Secrets synced automatically![/bold green]")
                        except Exception:
                            pass
                    except Exception as e:
                        console.print(f"[bold red]❌ YouTube Auth error:[/bold red] {e}")
                elif auth_choice == "2":
                    from syndication.browser_uploader import BrowserUploader
                    bu = BrowserUploader()
                    console.print("[bold cyan]🚀 Launching Firefox with persistent Social Profile...[/bold cyan]")
                    console.print("[dim]Log into your Instagram, Facebook, and WhatsApp Web accounts. Once logged in, close Firefox and your sessions will be saved permanently.[/dim]\n")
                    bu.launch_login_wizard()
                elif auth_choice == "3":
                    from syndication.social_auth import SocialAuth
                    sa = SocialAuth()
                    console.print("\n[bold cyan]🔑 Enter Meta / WhatsApp Credentials (Saved permanently in social_credentials.json):[/bold cyan]")
                    meta_tok = Prompt.ask("Meta Graph API Access Token (leave blank to keep existing)", default="")
                    ig_id = Prompt.ask("Instagram Business Account ID (leave blank to keep existing)", default="")
                    fb_id = Prompt.ask("Facebook Page ID (leave blank to keep existing)", default="")
                    wa_tok = Prompt.ask("WhatsApp Cloud API Token (optional)", default="")
                    wa_pid = Prompt.ask("WhatsApp Phone Number ID (optional)", default="")

                    sa.remember_tokens(
                        meta_token=meta_tok if meta_tok else None,
                        ig_account_id=ig_id if ig_id else None,
                        fb_page_id=fb_id if fb_id else None,
                        wa_token=wa_tok if wa_tok else None,
                        wa_phone_id=wa_pid if wa_pid else None,
                    )
                    console.print("\n[bold green]✅ Social credentials saved permanently! The agent will remember them and never ask again.[/bold green]")

                input("\nPress Enter to return...")
                return
            elif action == "heal":
                healer = SelfHealer()
                rep = healer.run_health_audit()
                console.print("\n[bold yellow]🛡️ Health Diagnostics:[/bold yellow]")
                for k, v in rep.items():
                    console.print(f"  • [cyan]{k:14s}[/cyan]: {v.get('message')}")
                healer.auto_repair()
                input("\nPress Enter to exit...")
                return
            elif action == "growth":
                growth = GrowthEngine()
                mem = growth.evolve_channel_strategy()
                console.print("\n[bold green]📈 Learned Channel Growth Patterns:[/bold green]")
                for h in mem.get("best_performing_hook_styles", []):
                    console.print(f"  • {h}")
                input("\nPress Enter to exit...")
                return
            elif action == "festival":
                handle_festival_campaign(dry_run=dry_run)
                return
            elif action == "security":
                handle_security_audit(auto_harden=True)
                return
            elif action == "evolution":
                handle_evolution_center()
                return
            elif action == "retry_social":
                handle_social_retry()
                return
            elif action == "sync_github":
                from core.github_sync import sync_to_github, get_remote_info
                console.clear()
                console.print(
                    Panel.fit(
                        "[bold cyan]🌐 ANTIGRAVITY TO GITHUB SYNCHRONIZATION[/bold cyan]\n"
                        "[dim]Commits and pushes all code modifications to your GitHub repository.[/dim]",
                        border_style="cyan",
                    )
                )
                remotes = get_remote_info()
                if not remotes:
                    console.print("[yellow]ℹ️ No remote repository URL configured yet.[/yellow]")
                    new_remote = Prompt.ask("👉 Enter GitHub Repo URL (e.g. https://github.com/username/youtube-agent.git)", default="")
                    if new_remote.strip():
                        from core.github_sync import set_remote_url
                        set_remote_url(new_remote.strip())
                custom_msg = Prompt.ask("👉 Enter commit message (leave blank for auto-generated summary)", default="")
                res = sync_to_github(message=custom_msg if custom_msg.strip() else None)
                console.print(f"\n[bold green]Sync Result:[/bold green] [bold white]{res.get('status')}[/bold white]")
                if res.get("message"):
                    console.print(f"[cyan]Commit Message:[/cyan] {res.get('message')}")
                if res.get("error"):
                    console.print(f"[bold red]Notice:[/bold red] {res.get('error')}")
                Prompt.ask("\nPress Enter to return")
                return
            elif action == "trilingual":
                is_trilingual = True

    console.clear()
    console.print(
        Panel.fit(
            "[bold red]🎬 AUTONOMOUS YOUTUBE CREATOR AGENT[/bold red]\n"
            f"[cyan]Mode:[/cyan] {'🌐 TRILINGUAL (English + Hindi + Gujarati)' if is_trilingual else 'Standard Short'}\n"
            f"[cyan]YouTube Target:[/cyan] [bold green]{config.YOUTUBE_PRIVACY_STATUS.upper()}[/bold green] | "
            f"[cyan]Category ID:[/cyan] {config.DEFAULT_CATEGORY_ID} (Education/Self-Improvement)\n"
            f"[magenta]🧠 Self-Growth:[/magenta] [green]ACTIVE[/green] | "
            f"[magenta]🛡️ Self-Healing:[/magenta] [green]ACTIVE[/green] | "
            f"[magenta]🌐 Network Guard:[/magenta] [green]AUTO-RESUME READY[/green]",
            border_style="red",
        )
    )

    mode_text = f"Trilingual (EN, HI, GU): {topic or 'Auto-selected Pillar'}" if is_trilingual else (f"Custom Topic: {topic}" if topic else "Autonomous Unique Topic Selection with Checkpoint Recovery")
    console.print(f"[cyan]🤖 Running:[/cyan] [white]{mode_text}...[/white]\n")

    state = {
        "current_step": 1,
        "overall_pct": 0,
        "status_message": "Initializing autonomous generation pipeline...",
        "step_details": {},
    }

    def progress_callback(pct: int, msg: str, step: int):
        state["overall_pct"] = min(pct, 100)
        state["status_message"] = msg
        state["current_step"] = step
        state["step_details"][step] = msg

    agent = YouTubeAgent(model=config.GEMINI_MODEL)

    with Live(render_ui(1, 0, "Starting...", {}), refresh_per_second=4, console=console) as live:
        def live_cb(pct: int, msg: str, step: int):
            progress_callback(pct, msg, step)
            live.update(
                render_ui(
                    state["current_step"],
                    state["overall_pct"],
                    state["status_message"],
                    state["step_details"],
                )
            )

        max_recovery_attempts = 10
        recovery_attempts = 0
        summary = None

        while recovery_attempts < max_recovery_attempts:
            try:
                if action == "video_only":
                    summary = agent.run_trilingual(
                        topic=topic,
                        dry_run=dry_run,
                        progress_callback=live_cb,
                        target_platform="youtube",
                        content_type="videos",
                    )
                elif is_trilingual:
                    summary = agent.run_trilingual(
                        topic=topic,
                        dry_run=dry_run,
                        progress_callback=live_cb,
                        target_platform=target_platform,
                        content_type="both",
                    )
                else:
                    summary = agent.run(
                        niche=niche,
                        topic=topic,
                        dry_run=dry_run,
                        content_type="both",
                        resume=not args.no_resume,
                        progress_callback=live_cb,
                    )
                state["current_step"] = 6
                state["overall_pct"] = 100
                state["status_message"] = "Pipeline execution finished successfully!"
                live.update(
                    render_ui(
                        6,
                        100,
                        state["status_message"],
                        state["step_details"],
                    )
                )
                break
            except Exception as e:
                # Do not loop endlessly on user configuration / missing file errors
                if isinstance(e, FileNotFoundError) or "client_secret" in str(e).lower():
                    live.stop()
                    console.print(f"\n[bold red]❌ Configuration Notice:[/bold red] {e}")
                    break

                recovery_attempts += 1
                if recovery_attempts >= max_recovery_attempts:
                    live.stop()
                    console.print(f"\n[bold red]❌ Execution Error (Exceeded max recovery attempts):[/bold red] {e}")
                    console.print("[dim]Check output logs for details.[/dim]")
                    input("\nPress Enter to exit...")
                    sys.exit(1)

                wait_secs = min(4 * recovery_attempts, 25)
                for s in range(wait_secs, 0, -1):
                    live_cb(
                        state["overall_pct"],
                        f"⚠️ Interruption detected ({type(e).__name__}). Auto-repairing & resuming in {s}s (Recovery #{recovery_attempts})...",
                        state["current_step"],
                    )
                    time.sleep(1)

                try:
                    agent.self_healer.auto_repair()
                except Exception:
                    pass

    console.print("")
    
    if not summary:
        console.print("[yellow]Pipeline finished without summary.[/yellow]")
        input("\nPress [Enter] to exit...")
        return

    # Final Result Card
    result_grid = Table.grid(padding=(0, 1))
    
    if is_trilingual:
        result_grid.add_row("[bold cyan]Focus Pillar:[/bold cyan]", f"[bold white]{summary.get('topic')}[/bold white]")
        videos = summary.get("videos", {})
        upload_results = summary.get("upload_results", {})
        for lang_code in ["en", "hi", "gu"]:
            flag = "🇺🇸 EN" if lang_code == "en" else "🇮🇳 HI" if lang_code == "hi" else "🇮🇳 GU"
            vpath = videos.get(lang_code, "N/A")
            ures = upload_results.get(lang_code, {})
            result_grid.add_row(f"[bold cyan]{flag} Video:[/bold cyan]", f"[green]{vpath}[/green]")
            if ures.get("video_url"):
                result_grid.add_row(f"[bold cyan]{flag} YouTube:[/bold cyan]", f"[bold yellow underline]{ures['video_url']}[/bold yellow underline]")
            else:
                result_grid.add_row(f"[bold cyan]{flag} Upload:[/bold cyan]", f"[yellow]{ures.get('status', 'Saved Locally')}[/yellow]")
        
        story_res = summary.get("story_syndication", {})
        if story_res:
            result_grid.add_row("", "")
            result_grid.add_row("[bold magenta]📲 Story Syndication:[/bold magenta]", "[bold green]Instagram, Facebook & WhatsApp Stories Ready[/bold green]")
            result_grid.add_row("[bold cyan]📸 Instagram Stories:[/bold cyan]", f"[dim]{config.OUTPUT_DIR}/stories/instagram[/dim]")
            result_grid.add_row("[bold cyan]📘 Facebook Stories:[/bold cyan]", f"[dim]{config.OUTPUT_DIR}/stories/facebook[/dim]")
            result_grid.add_row("[bold cyan]💬 WhatsApp Status:[/bold cyan]", f"[dim]{config.OUTPUT_DIR}/stories/whatsapp[/dim]")
    else:
        upload_res = summary.get("upload_result") or {}
        result_grid.add_row("[bold cyan]Video Title:[/bold cyan]", f"[bold white]{summary.get('title')}[/bold white]")
        result_grid.add_row("[bold cyan]Video File:[/bold cyan]", f"[green]{summary.get('video_path')}[/green]")
        
        if upload_res.get("video_url"):
            result_grid.add_row("[bold cyan]YouTube URL:[/bold cyan]", f"[bold yellow underline]{upload_res['video_url']}[/bold yellow underline]")
            result_grid.add_row("[bold cyan]Upload Status:[/bold cyan]", f"[bold green]PUBLIC (Uploaded to Channel)[/bold green]")
        elif upload_res.get("status") == "SAVED_LOCALLY_NEEDS_AUTH":
            result_grid.add_row("[bold cyan]Upload Status:[/bold cyan]", "[bold yellow]Saved Locally (YouTube Login Needed)[/bold yellow]")
        else:
            result_grid.add_row("[bold cyan]Upload Status:[/bold cyan]", "[yellow]Dry Run (Saved Locally)[/yellow]")

    std_vid = summary.get("youtube_video")
    if std_vid and isinstance(std_vid, dict):
        result_grid.add_row("", "")
        result_grid.add_row("[bold magenta]🎬 Standard 16:9 Video:[/bold magenta]", f"[bold white]{std_vid.get('title', 'Masterclass Video')}[/bold white]")
        result_grid.add_row("[bold cyan]📹 Video File (1080p):[/bold cyan]", f"[green]{std_vid.get('video_path', 'N/A')}[/green]")
        if std_vid.get("thumbnail_path"):
            result_grid.add_row("[bold cyan]🖼️ Custom Thumbnail:[/bold cyan]", f"[cyan]{std_vid.get('thumbnail_path')}[/cyan]")
        up_res = std_vid.get("upload_result") or {}
        if isinstance(up_res, dict) and up_res.get("video_url"):
            result_grid.add_row("[bold cyan]🌐 Video YouTube URL:[/bold cyan]", f"[bold yellow underline]{up_res['video_url']}[/bold yellow underline]")
        elif isinstance(up_res, dict) and up_res.get("status"):
            result_grid.add_row("[bold cyan]🌐 Video Status:[/bold cyan]", f"[yellow]{up_res.get('status')}[/yellow]")

    console.print(
        Panel(
            result_grid,
            title="[bold green]🎉 SUCCESSFUL RUN SUMMARY[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )

    # If YouTube OAuth is needed, display a dedicated helper card
    if not Path(config.YOUTUBE_TOKEN_FILE).exists():
        console.print(
            Panel(
                "[bold yellow]ℹ️ TO ENABLE 1-CLICK UPLOADS DIRECTLY TO YOUTUBE:[/bold yellow]\n\n"
                "1. Open [bold cyan]https://console.cloud.google.com/[/bold cyan]\n"
                "2. Enable [bold white]YouTube Data API v3[/bold white] & create an [bold white]OAuth Client ID (Desktop App)[/bold white]\n"
                f"3. Save the downloaded JSON file as:\n"
                f"   [bold green]/home/alpesh/youtube-agent/client_secret.json[/bold green]\n"
                "4. Run: [bold cyan]python agent.py --auth[/bold cyan] (or option [4] in interactive menu)",
                title="[bold cyan]🔑 YouTube Channel Authentication Setup[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    console.print("\n[bold green]✨ All done! Your Short has been generated and processed.[/bold green]")
    console.print("[cyan]🕒 Window will auto-close in 5 seconds (or press any key to close immediately)...[/cyan]\n")
    for remaining in range(5, 0, -1):
        sys.stdout.write(f"\r  Auto-closing in {remaining}s... ")
        sys.stdout.flush()
        rlist, _, _ = select.select([sys.stdin], [], [], 1.0)
        if rlist:
            sys.stdin.readline()
            break
    print("\n👋 Process complete. Closing window now...")
    sys.exit(0)


if __name__ == "__main__":
    run_pipeline()
