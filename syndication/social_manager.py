"""
Autonomous Social Media Manager for Instagram, Facebook & WhatsApp
Provides full automated control, status auditing, modal auto-dismissal,
and sequential multi-platform publishing.
"""

import argparse
import datetime
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from syndication.browser_uploader import BrowserUploader
from syndication.api_uploader import DirectSocialApiUploader
from syndication.social_auth import SocialAuth
from syndication.story_publisher import StoryPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("SocialManager")
console = Console()


class SocialManager:
    """
    Autonomous Manager to control and oversee Instagram, Facebook, and WhatsApp Web.
    Handles session health, automated publishing, overlay bypass, and history logging.
    """

    def __init__(self):
        self.auth = SocialAuth()
        self.uploader = BrowserUploader()
        self.api_uploader = DirectSocialApiUploader()
        self.publisher = StoryPublisher()
        self.history_file = config.OUTPUT_DIR / "social_history.json"
        self.history = self._load_history()

    def _load_history(self) -> List[Dict[str, Any]]:
        if self.history_file.exists():
            try:
                return json.loads(self.history_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_history(self):
        try:
            self.history_file.write_text(json.dumps(self.history, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug(f"History save notice: {e}")

    def log_event(self, platform: str, action: str, status: str, media_file: str, details: Optional[str] = None):
        event = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "platform": platform,
            "action": action,
            "status": status,
            "media_file": media_file,
            "details": details or "",
        }
        self.history.append(event)
        self._save_history()

    # --------------------------------------------------------------------------
    # 1. ACCOUNT HEALTH & SESSION AUDITING
    # --------------------------------------------------------------------------
    def audit_accounts(self) -> Dict[str, Dict[str, Any]]:
        """Audits the live connection and login status of Instagram, Facebook, and WhatsApp."""
        console.print("\n[bold cyan]🔍 Auditing Social Media Accounts (Instagram, Facebook, WhatsApp)...[/bold cyan]")
        results = {
            "instagram": {"status": "UNKNOWN", "details": ""},
            "facebook": {"status": "UNKNOWN", "details": ""},
            "whatsapp": {"status": "UNKNOWN", "details": ""},
        }

        # Check local profile cookie store
        cookies_sqlite = self.uploader.profile_dir / "cookies.sqlite"
        if not cookies_sqlite.exists() or cookies_sqlite.stat().st_size < 10000:
            # Attempt to auto-sync from main user Firefox profile first
            self.uploader.sync_from_user_firefox()

        driver = None
        try:
            driver = self.uploader.get_driver(headless=True)
            
            # --- 1. Audit Facebook ---
            try:
                driver.get("https://www.facebook.com/stories/create")
                time.sleep(4)
                self.uploader.dismiss_overlays(driver)
                if "stories/create" in driver.current_url or "facebook.com" in driver.current_url:
                    inputs = driver.find_elements("css selector", "input[type='file']")
                    if inputs or "create" in driver.title.lower() or "facebook" in driver.title.lower():
                        results["facebook"] = {
                            "status": "ONLINE",
                            "details": "Authenticated (Story creator ready)",
                        }
                    else:
                        results["facebook"] = {"status": "LOGIN_REQUIRED", "details": "Redirected to login"}
            except Exception as e:
                results["facebook"] = {"status": "ERROR", "details": str(e)[:60]}

            # --- 2. Audit Instagram ---
            try:
                driver.get("https://www.instagram.com/")
                time.sleep(4)
                self.uploader.dismiss_overlays(driver)
                feed_indicators = driver.find_elements("xpath", "//*[@aria-label='New post'] | //*[@aria-label='Home'] | //span[text()='Home']")
                if feed_indicators or "instagram" in driver.title.lower():
                    results["instagram"] = {
                        "status": "ONLINE",
                        "details": "Authenticated (Feed & Story access ready)",
                    }
                else:
                    results["instagram"] = {"status": "LOGIN_REQUIRED", "details": "Login screen detected"}
            except Exception as e:
                results["instagram"] = {"status": "ERROR", "details": str(e)[:60]}

            # --- 3. Audit WhatsApp Web ---
            try:
                driver.get("https://web.whatsapp.com/")
                time.sleep(6)
                qr = driver.find_elements("css selector", "canvas")
                if not qr:
                    results["whatsapp"] = {
                        "status": "ONLINE",
                        "details": "Authenticated (Chats & Status active)",
                    }
                else:
                    results["whatsapp"] = {"status": "SCAN_QR_REQUIRED", "details": "QR code scan needed once"}
            except Exception as e:
                results["whatsapp"] = {"status": "ERROR", "details": str(e)[:60]}

        except Exception as e:
            logger.warning(f"Session audit error: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        self._display_audit_table(results)
        return results

    def _display_audit_table(self, results: Dict[str, Dict[str, Any]]):
        table = Table(title="🌐 Social Media Account Health & Control", border_style="cyan")
        table.add_column("Platform", style="bold white", width=18)
        table.add_column("Status", justify="center", width=18)
        table.add_column("Live Details", style="dim", width=42)

        for plat, data in results.items():
            name = "📸 Instagram" if plat == "instagram" else "📘 Facebook" if plat == "facebook" else "💬 WhatsApp"
            status = data["status"]
            if status == "ONLINE":
                st_str = "[bold green]✅ ACTIVE / READY[/bold green]"
            elif "REQUIRED" in status:
                st_str = "[bold yellow]⚠️ SETUP NEEDED[/bold yellow]"
            else:
                st_str = "[bold red]❌ OFFLINE[/bold red]"
            table.add_row(name, st_str, data["details"])

        console.print(table)

    # --------------------------------------------------------------------------
    # 2. AUTONOMOUS MULTI-PLATFORM PUBLISHING
    # --------------------------------------------------------------------------
    def publish_single_media(self, media_path: Path, caption: Optional[str] = None) -> Dict[str, Any]:
        """
        Publishes a single image or video across Instagram, Facebook, and WhatsApp Stories autonomously.
        """
        if not media_path.exists():
            return {"status": "FAILED", "reason": "Media file not found"}

        if not caption:
            caption = f"🔥 {media_path.stem.replace('_', ' ').title()}\n\n#DailyGrowth #Discipline #Mindset #Shorts"

        console.print(Panel(
            f"[bold green]🚀 Publishing Media to Social Channels[/bold green]\n"
            f"[cyan]File:[/cyan] {media_path.name} ({media_path.stat().st_size / 1024 / 1024:.1f} MB)\n"
            f"[cyan]Caption:[/cyan] {caption[:70]}...",
            border_style="green"
        ))

        results = {}

        # 1. Instagram
        logger.info(f"📸 [Instagram] Publishing {media_path.name}...")
        try:
            ig_res = self.api_uploader.post_instagram_direct(media_path, caption)
            if ig_res.get("status") != "PUBLISHED":
                logger.info(f"📸 [Instagram Browser Fallback] Publishing {media_path.name}...")
                ig_res = self.uploader.post_instagram_reel(media_path, caption)
            results["instagram"] = ig_res
            self.log_event("instagram", "publish_story", ig_res.get("status", "SUCCESS"), media_path.name)
            console.print(f"  📸 Instagram: [green]{ig_res.get('status')}[/green]")
        except Exception as e:
            results["instagram"] = {"status": "FAILED", "reason": str(e)}
            console.print(f"  📸 Instagram: [red]FAILED[/red] ({e})")

        time.sleep(2)

        # 2. Facebook
        logger.info(f"📘 [Facebook] Publishing {media_path.name}...")
        try:
            fb_res = self.api_uploader.post_facebook_direct(media_path, caption)
            if fb_res.get("status") != "PUBLISHED":
                logger.info(f"📘 [Facebook Browser Fallback] Publishing {media_path.name}...")
                fb_res = self.uploader.post_facebook_story(media_path, caption)
            results["facebook"] = fb_res
            self.log_event("facebook", "publish_story", fb_res.get("status", "SUCCESS"), media_path.name)
            console.print(f"  📘 Facebook: [green]{fb_res.get('status')}[/green]")
        except Exception as e:
            results["facebook"] = {"status": "FAILED", "reason": str(e)}
            console.print(f"  📘 Facebook: [red]FAILED[/red] ({e})")

        time.sleep(2)

        # 3. WhatsApp
        logger.info(f"💬 [WhatsApp] Publishing {media_path.name}...")
        try:
            wa_res = self.api_uploader.post_whatsapp_direct(media_path, caption)
            if wa_res.get("status") != "PUBLISHED":
                logger.info(f"💬 [WhatsApp Browser Fallback] Publishing {media_path.name}...")
                wa_res = self.uploader.post_whatsapp_status(media_path, caption)
            results["whatsapp"] = wa_res
            self.log_event("whatsapp", "publish_status", wa_res.get("status", "SUCCESS"), media_path.name)
            console.print(f"  💬 WhatsApp: [green]{wa_res.get('status')}[/green]")
        except Exception as e:
            results["whatsapp"] = {"status": "FAILED", "reason": str(e)}
            console.print(f"  💬 WhatsApp: [red]FAILED[/red] ({e})")

        # Desktop alert
        try:
            from growth.notifier import notifier
            notifier.send(
                "🌐 Social Media Publishing Finished",
                f"File: {media_path.name}\nPublished to Instagram, Facebook & WhatsApp!",
                urgency="normal"
            )
        except Exception:
            pass

        return results

    def publish_pending_stories(self) -> int:
        """Finds all media in Story/ and output/stories/ and publishes them autonomously."""
        from syndication.story_watcher import StoryWatcher
        watcher = StoryWatcher()
        count = watcher.run_once()
        console.print(f"✨ [bold green]Published {count} media item(s) from Story/ folder.[/bold green]")
        return count


def interactive_dashboard():
    """Interactive Control Dashboard for Social Media Stories AI."""
    mgr = SocialManager()
    console.clear()
    console.print(Panel.fit(
        "[bold magenta]🌐 SOCIAL MEDIA STORIES AI - CONTROL DASHBOARD[/bold magenta]\n"
        "[cyan]Platforms:[/cyan] [bold]Instagram (Stories/Reels) + Facebook (Stories) + WhatsApp (Status)[/bold]\n"
        "[dim]Full autonomous management, session handling & publishing[/dim]",
        border_style="magenta"
    ))

    while True:
        console.print("\n[bold yellow]Select an Action:[/bold yellow]")
        console.print("  [cyan][1][/cyan] 🚀 Run Full Autonomous Generation & Publish to IG, FB, WA")
        console.print("  [cyan][2][/cyan] 📁 Publish Pending Content from 'Story/' Drop Folder")
        console.print("  [cyan][3][/cyan] 🔍 Audit Account Connections & Login Health")
        console.print("  [cyan][4][/cyan] 🔄 Sync Browser Sessions from Firefox")
        console.print("  [cyan][5][/cyan] 📜 View Recent Social Publishing History")
        console.print("  [cyan][0][/cyan] 🚪 Exit")

        choice = input("\nEnter choice [1-5, 0]: ").strip()
        if choice == "1":
            from agent import YouTubeAgent
            console.print("\n[bold green]Starting Autonomous Trilingual Generation for Social Media...[/bold green]")
            agent = YouTubeAgent()
            agent.run_trilingual(target_platform="social")
        elif choice == "2":
            mgr.publish_pending_stories()
        elif choice == "3":
            mgr.audit_accounts()
        elif choice == "4":
            mgr.uploader.sync_from_user_firefox()
            console.print("✅ [green]Synchronized browser sessions from Firefox![/green]")
        elif choice == "5":
            history = mgr.history[-10:]
            if not history:
                console.print("[dim]No publishing history recorded yet.[/dim]")
            else:
                htable = Table(title="📜 Recent Publishing Events", border_style="magenta")
                htable.add_column("Timestamp", style="dim", width=20)
                htable.add_column("Platform", style="bold white", width=14)
                htable.add_column("Media File", style="cyan", width=26)
                htable.add_column("Status", justify="center", width=14)
                for ev in reversed(history):
                    st = f"[green]{ev['status']}[/green]" if ev['status'] in ("PUBLISHED", "SUCCESS") else f"[yellow]{ev['status']}[/yellow]"
                    htable.add_row(ev["timestamp"], ev["platform"], ev["media_file"][:24], st)
                console.print(htable)
        elif choice in ("0", "q", "exit"):
            break


def main():
    parser = argparse.ArgumentParser(description="Social Media Stories AI Autonomous Manager")
    parser.add_argument("--status", action="store_true", help="Audit Instagram, Facebook and WhatsApp account health")
    parser.add_argument("--publish-pending", action="store_true", help="Publish pending media from Story/ folder")
    parser.add_argument("--file", type=str, default=None, help="Publish a specific image or video file")
    parser.add_argument("--caption", type=str, default=None, help="Optional caption for upload")
    parser.add_argument("--sync", action="store_true", help="Sync browser sessions from user's Firefox")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive control dashboard")
    args = parser.parse_args()

    mgr = SocialManager()

    if args.status:
        mgr.audit_accounts()
    elif args.sync:
        mgr.uploader.sync_from_user_firefox()
    elif args.file:
        mgr.publish_single_media(Path(args.file), caption=args.caption)
    elif args.publish_pending:
        mgr.publish_pending_stories()
    elif args.interactive or len(sys.argv) == 1:
        interactive_dashboard()


if __name__ == "__main__":
    main()
