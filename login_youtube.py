#!/usr/bin/env python3
"""
Dedicated YouTube Google OAuth 2.0 Login & Verification Wizard
=============================================================
1-Click interactive authorization tool that:
1. Opens Google OAuth in your default browser.
2. Explains the Google verification bypass ('Advanced' -> 'Go to YouTube Agent').
3. Saves fresh token.json permanently (with offline refresh token).
4. Synchronizes credentials to GitHub Actions Secrets.
5. Sweeps and uploads all 5 pending videos waiting in output/.
"""

import os
import sys
import time
from pathlib import Path

# Auto-switch to virtual environment if running with system Python
REPO_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python3"
if VENV_PYTHON.exists() and sys.executable != str(VENV_PYTHON.resolve()):
    os.execv(str(VENV_PYTHON.resolve()), [str(VENV_PYTHON.resolve())] + sys.argv)

sys.path.insert(0, str(REPO_ROOT))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def main():
    console.print(Panel.fit(
        "[bold cyan]🔑 YOUTUBE CHANNEL OAUTH 2.0 LOGIN & RUNNER[/bold cyan]\n"
        "[dim]Authenticates YouTube Data API v3 and publishes all queued videos.[/dim]",
        border_style="cyan"
    ))

    from youtube.auth import YouTubeAuth
    auth = YouTubeAuth()

    if not auth.client_secret_file.exists():
        console.print(f"❌ [bold red]Missing client_secret.json at:[/bold red] {auth.client_secret_file.resolve()}")
        console.print("Please place your downloaded Google Cloud OAuth Client ID JSON file at client_secret.json.")
        sys.exit(1)

    console.print("\n[bold yellow]Step 1: Authenticating with Google...[/bold yellow]")
    console.print("👉 A browser window will open to authenticate.")
    console.print("ℹ️  [dim]If Google shows 'Google hasn't verified this app':[/dim]")
    console.print("   [dim]1. Click 'Advanced' (bottom left)[/dim]")
    console.print("   [dim]2. Click 'Go to YouTube Agent (unsafe)'[/dim]")
    console.print("   [dim]3. Click 'Continue' to approve access.[/dim]\n")

    try:
        from youtube.uploader import YouTubeUploader
        uploader = YouTubeUploader(auth=auth)
        # Accessing service triggers fresh login flow if expired
        ch = uploader.service.channels().list(part="snippet,statistics", mine=True).execute()

        item = ch["items"][0]
        title = item["snippet"]["title"]
        chid = item["id"]
        subs = item["statistics"].get("subscriberCount", 0)
        vids = item["statistics"].get("videoCount", 0)

        console.print(f"\n🎉 [bold green]SUCCESSFULLY CONNECTED TO YOUTUBE![/bold green]")
        console.print(f"   • Channel Title: [bold cyan]{title}[/bold cyan]")
        console.print(f"   • Channel ID:    [dim]{chid}[/dim]")
        console.print(f"   • Videos:        [white]{vids}[/white] | Subscribers: [white]{subs}[/white]")

        # Step 2: Sync to GitHub Actions Secrets
        console.print("\n[bold yellow]Step 2: Syncing credentials to GitHub repository secrets...[/bold yellow]")
        try:
            from core.github_sync import sync_secrets_to_github
            sec_res = sync_secrets_to_github()
            if sec_res.get("status") == "SUCCESS":
                console.print("✅ [bold green]GitHub Actions Secrets updated successfully![/bold green]")
            else:
                console.print(f"ℹ️ [dim]GitHub secrets notice: {sec_res.get('status')}[/dim]")
        except Exception as se:
            console.print(f"ℹ️ [dim]Could not sync to GitHub secrets ({se}). Continuing...[/dim]")

        # Step 3: Sweep & Upload all pending videos
        console.print("\n" + "=" * 65)
        console.print("🚀 [bold cyan]STEP 3: UPLOADING ALL PENDING VIDEOS TO YOUTUBE[/bold cyan]")
        console.print("=" * 65)
        from upload_to_youtube import get_pending_videos, upload_all_pending
        pending = get_pending_videos()
        if pending:
            console.print(f"📋 Found [bold yellow]{len(pending)}[/bold yellow] pending video(s) ready for upload.")
            uploaded = upload_all_pending(watch_mode=False)
            if uploaded:
                console.print(f"\n🎉 [bold green]Uploaded {len(uploaded)} video(s) successfully to YouTube![/bold green]")
                for up in uploaded:
                    console.print(f"   • [cyan]{up.get('title')}[/cyan] ➔ {up.get('video_url')}")
        else:
            console.print("✨ [bold green]All generated videos are already uploaded and up to date![/bold green]")

        console.print("\n" + "=" * 65)
        console.print("🎯 [bold green]YOUTUBE AUTHENTICATION & UPLOAD COMPLETE![/bold green]")
        console.print("=" * 65 + "\n")

    except Exception as e:
        console.print(f"\n❌ [bold red]YouTube Login Failed:[/bold red] {e}")
        console.print("\n💡 [bold yellow]Troubleshooting Tips:[/bold yellow]")
        console.print("1. If Google displayed 'Access blocked: Error 403 access_denied':")
        console.print("   Open https://console.cloud.google.com/apis/credentials/consent")
        console.print("   Under 'Test users', add your Google email address, or click 'PUBLISH APP'.")
        console.print("2. If the browser did not open, copy the URL displayed above and open it in Firefox or Chrome.")
        sys.exit(1)


if __name__ == "__main__":
    main()
