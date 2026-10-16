#!/usr/bin/env python3
"""
1-Click Account Connection & Verification Manager
Checks, connects, and verifies all required credentials, files, and assets for:
  1. YouTube Data API (Google OAuth 2.0)
  2. Instagram (royal_chamunda_auto)
  3. Facebook (Chamunda Automobile)
  4. WhatsApp Web (Status & Stories)
  5. Google Gemini AI Engine
  6. FFmpeg, Fonts & Media Assets
"""

import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config

console = Console()


def check_gemini() -> bool:
    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key:
        console.print("❌ [bold red]Gemini API Key:[/bold red] Missing in .env")
        return False
    try:
        from google import genai
        from growth.model_resolver import get_candidate_models
        client = genai.Client(api_key=api_key)
        candidates = get_candidate_models(preferred=getattr(config, "GEMINI_MODEL", "gemini-3.6-flash"))
        for model in candidates:
            try:
                res = client.models.generate_content(
                    model=model,
                    contents="ping",
                )
                if res and res.text:
                    console.print(f"✅ [bold green]Google Gemini AI:[/bold green] Connected & Operational (Model: [bold cyan]{model}[/bold cyan])")
                    return True
            except Exception:
                continue

        console.print("⚠️ [bold yellow]Google Gemini AI:[/bold yellow] All candidate models busy or unavailable.")
        return False
    except Exception as e:
        console.print(f"⚠️ [bold yellow]Google Gemini AI:[/bold yellow] Error: {e}")
        return False


def check_youtube() -> bool:
    try:
        from youtube.auth import YouTubeAuth
        from youtube.uploader import YouTubeUploader

        auth = YouTubeAuth()
        if not auth.is_token_valid():
            console.print("⚠️ [bold yellow]YouTube OAuth:[/bold yellow] Token is unauthenticated or expired.")
            console.print("🔑 Opening browser for 1-time Google OAuth authorization...")
            # Interactive authentication
            uploader = YouTubeUploader(auth=auth)
            # Accessing uploader.service triggers get_credentials()
            ch = uploader.service.channels().list(part="snippet,statistics", mine=True).execute()
        else:
            uploader = YouTubeUploader(auth=auth)
            ch = uploader.service.channels().list(part="snippet,statistics", mine=True).execute()

        item = ch["items"][0]
        title = item["snippet"]["title"]
        chid = item["id"]
        subs = item["statistics"].get("subscriberCount", 0)
        vids = item["statistics"].get("videoCount", 0)
        console.print(f"✅ [bold green]YouTube Channel:[/bold green] Connected as [bold cyan]{title}[/bold cyan] (ID: {chid}, Videos: {vids}, Subs: {subs})")
        return True
    except Exception as e:
        console.print(f"❌ [bold red]YouTube Channel:[/bold red] Error: {e}")
        return False


def check_whatsapp() -> bool:
    try:
        from syndication.browser_uploader import BrowserUploader
        bu = BrowserUploader()
        if bu.is_whatsapp_session_valid():
            console.print("✅ [bold green]WhatsApp Web:[/bold green] Paired & Connected (Active session found)")
            return True
        else:
            console.print("⚠️ [bold yellow]WhatsApp Web:[/bold yellow] No active paired session detected.")
            console.print("📱 To pair WhatsApp: Run './login_whatsapp.py' and scan QR code.")
            return False
    except Exception as e:
        console.print(f"❌ [bold red]WhatsApp Web:[/bold red] Error: {e}")
        return False


def check_instagram_and_facebook() -> bool:
    try:
        from syndication.browser_uploader import BrowserUploader
        bu = BrowserUploader()
        bu.sync_from_user_firefox(force=False)

        # Check cookies
        import sqlite3
        cpath = bu.profile_dir / "cookies.sqlite"
        has_ig = False
        has_fb = False
        if cpath.exists():
            conn = sqlite3.connect(f"file:{cpath}?immutable=1", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT name FROM moz_cookies WHERE host LIKE '%instagram%' AND name = 'sessionid'")
            if cur.fetchone():
                has_ig = True
            cur.execute("SELECT name FROM moz_cookies WHERE host LIKE '%facebook%' AND name IN ('c_user', 'xs')")
            if cur.fetchone():
                has_fb = True
            conn.close()

        ig_status = "✅ Connected" if has_ig else "⚠️ Login Needed"
        fb_status = "✅ Connected" if has_fb else "⚠️ Login Needed"
        console.print(f"{'✅' if has_ig else '⚠️'} [bold {'green' if has_ig else 'yellow'}]Instagram (royal_chamunda_auto):[/bold {'green' if has_ig else 'yellow'}] {ig_status}")
        console.print(f"{'✅' if has_fb else '⚠️'} [bold {'green' if has_fb else 'yellow'}]Facebook (Chamunda Auto):[/bold {'green' if has_fb else 'yellow'}] {fb_status}")

        if not has_ig or not has_fb:
            console.print("💡 Tip: To log in with 1-click in Firefox, run: [bold cyan]python3 connect_accounts.py --login-browser[/bold cyan]")
        return has_ig and has_fb
    except Exception as e:
        console.print(f"❌ [bold red]Social Accounts:[/bold red] Error: {e}")
        return False


def check_assets() -> bool:
    all_ok = True
    assets = [
        ("Montserrat Font", config.FONTS_DIR / "Montserrat-Variable.ttf"),
        ("Stoic Background Music", config.MUSIC_DIR / "stoic_ambient_focus.mp3"),
        ("Chamunda Visiting Card", config.ASSETS_DIR / "chamunda_visiting_card.jpg"),
    ]
    for label, path in assets:
        if path.exists() and path.stat().st_size > 1000:
            console.print(f"✅ [bold green]{label}:[/bold green] Present ({path.name}, {path.stat().st_size // 1024} KB)")
        else:
            console.print(f"❌ [bold red]{label}:[/bold red] Missing at {path}")
            all_ok = False
    return all_ok


def upload_waiting_content():
    console.print("\n" + "=" * 65)
    console.print("🚀 [bold cyan]STEP 1: SWEEPING & UPLOADING PENDING GENERATED VIDEOS[/bold cyan]")
    console.print("=" * 65)
    try:
        from upload_to_youtube import get_pending_videos, upload_all_pending
        pending = get_pending_videos()
        if pending:
            console.print(f"📋 Found [bold yellow]{len(pending)}[/bold yellow] unuploaded generated video(s) across output directories.")
            console.print("🚀 Uploading unuploaded videos to YouTube now...")
            uploaded = upload_all_pending(watch_mode=False)
            if uploaded:
                console.print(f"🎉 [bold green]Successfully uploaded {len(uploaded)} video(s) to YouTube![/bold green]")
                for up in uploaded:
                    console.print(f"   • [cyan]{up.get('title')}[/cyan] ➔ {up.get('video_url')}")
            else:
                console.print("ℹ️ Upload check completed. Videos remain safely preserved in output/.")
        else:
            console.print("✨ [bold green]All generated videos are already uploaded and up to date![/bold green]")
    except Exception as e:
        console.print(f"⚠️ Notice during upload: {e}")


def resume_incomplete_youtube_runs():
    try:
        from agent import YouTubeAgent
        agent = YouTubeAgent()
        resumable = agent.find_latest_resumable_run(trilingual=True)
        if resumable:
            console.print("\n" + "=" * 65)
            console.print(f"🔄 [bold yellow]STEP 2: RESUMING INCOMPLETE GENERATION RUN ({resumable.name})[/bold yellow]")
            console.print("=" * 65)
            console.print("🎬 Compiling video & publishing remaining languages to YouTube...")
            agent.run_trilingual(target_platform="youtube", dry_run=False, resume=True)
            console.print("✅ [bold green]Incomplete run resumed and finished successfully![/bold green]")
        else:
            console.print("\n✨ [bold green]No incomplete runs found. All video packages are 100% compiled.[/bold green]")
    except Exception as e:
        console.print(f"⚠️ Notice during run resumption: {e}")


def manual_run_youtube_prompt():
    console.print("\n" + "=" * 65)
    console.print("🎬 [bold cyan]STEP 3: MANUAL RUN YOUTUBE AGENT[/bold cyan]")
    console.print("=" * 65)
    from growth.youtube_daily_limiter import youtube_limiter
    can_run = youtube_limiter.can_run_today()
    force_run = False

    if "--run-now" in sys.argv:
        should_run = True
        force_run = True
    else:
        if not can_run:
            console.print("ℹ️ Today's daily YouTube quota run has already completed (1/1).")
            prompt_text = "Would you like to force a manual run of the YouTube Agent now? [y/N]: "
        else:
            console.print("✨ Today's daily YouTube Short is pending.")
            prompt_text = "Would you like to manually run the YouTube Agent now to generate & upload? [Y/n]: "

        try:
            import select
            console.print(f"👉 {prompt_text}", end="")
            sys.stdout.flush()
            rlist, _, _ = select.select([sys.stdin], [], [], 10)
            if rlist:
                user_input = sys.stdin.readline().strip().lower()
            else:
                user_input = "y" if can_run else "n"
                console.print(f" (Auto-selected: '{user_input}')")
        except Exception:
            user_input = "y" if can_run else "n"

        should_run = (user_input in ("y", "yes")) if not can_run else (user_input not in ("n", "no"))
        force_run = not can_run

    if should_run:
        console.print("\n🚀 [bold green]Starting manual YouTube Agent trilingual run (EN, HI, GU)...[/bold green]")
        try:
            from agent import YouTubeAgent
            agent = YouTubeAgent()
            agent.run_trilingual(target_platform="youtube", dry_run=False, force=force_run, resume=True)
            console.print("🎉 [bold green]Manual YouTube Agent run completed successfully![/bold green]")
        except Exception as e:
            console.print(f"❌ Error during manual YouTube Agent run: {e}")
    else:
        console.print("⏩ Skipping manual YouTube Agent generation. Background daemon will continue monitoring.")


def main():
    console.print(Panel.fit(
        "[bold cyan]🤖 YOUTUBE & SOCIAL AI AGENT — ACCOUNT & FILE CONNECTION MANAGER[/bold cyan]\n"
        "[dim]Inspects and links all required credentials, tokens, browsers, and media assets.[/dim]",
        border_style="cyan"
    ))

    if "--login-youtube" in sys.argv:
        console.print("\n🔑 [bold cyan]Initiating 1-Click YouTube Google OAuth Login & Runner...[/bold cyan]")
        yt_ok = check_youtube()
        if yt_ok:
            upload_waiting_content()
            resume_incomplete_youtube_runs()
            manual_run_youtube_prompt()
        console.print("\n" + "=" * 65)
        console.print("🎯 [bold green]YOUTUBE 1-CLICK OPERATION COMPLETE![/bold green]")
        console.print("=" * 65 + "\n")
        return

    if "--login-browser" in sys.argv:
        from syndication.browser_uploader import BrowserUploader
        console.print("\n🌐 Launching Firefox session wizard for Instagram, Facebook & WhatsApp...")
        console.print("👉 Please log in to your accounts in the browser window, then close it when done.")
        bu = BrowserUploader()
        bu.launch_login_wizard(block=True)
        console.print("✅ Browser session saved permanently!\n")

    console.print("\n[bold]1. AI Engine & Infrastructure[/bold]")
    check_gemini()

    console.print("\n[bold]2. Media Assets & Fonts[/bold]")
    check_assets()

    console.print("\n[bold]3. YouTube Channel Connection[/bold]")
    yt_ok = check_youtube()

    console.print("\n[bold]4. Social Media Connections[/bold]")
    check_whatsapp()
    check_instagram_and_facebook()

    if yt_ok and "--upload" in sys.argv:
        upload_waiting_content()

    console.print("\n" + "=" * 65)
    console.print("🎯 [bold green]CONNECTION CHECK COMPLETE![/bold green]")
    console.print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
