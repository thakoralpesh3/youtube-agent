"""
Centralized Linux Desktop Notification Engine
=============================================
Provides guaranteed, resilient desktop notifications for YouTube Agent and Social Media Agent:
- Automatically detects and configures DISPLAY (:0), XAUTHORITY (~/.Xauthority), and DBUS_SESSION_BUS_ADDRESS.
- Gracefully handles boot-time delays (waits for desktop session/Cinnamon to become ready).
- Logs all dispatched notifications to output/notifications.log for full auditability.
- Provides milestone alerts: login banner, generation start, upload success, daily quota status, and retry queueing.
"""

import datetime
import json
import logging
import os
from pathlib import Path
import subprocess
import time
from typing import Dict, List, Optional

import config

logger = logging.getLogger("Notifier")


class DesktopNotifier:
    def __init__(self):
        self.app_name = "YouTube & Social AI"
        self.log_file = config.OUTPUT_DIR / "notifications.log"
        self.icon_path = config.BASE_DIR / "assets" / "youtube-creator.svg"

    def _get_desktop_env(self) -> Dict[str, str]:
        """Ensures DISPLAY, XAUTHORITY, and DBUS_SESSION_BUS_ADDRESS are populated."""
        env = os.environ.copy()

        # Guarantee DISPLAY
        if not env.get("DISPLAY"):
            env["DISPLAY"] = ":0"

        # Guarantee XAUTHORITY
        if not env.get("XAUTHORITY"):
            user_xauth = Path.home() / ".Xauthority"
            if user_xauth.exists():
                env["XAUTHORITY"] = str(user_xauth)

        # Guarantee DBUS_SESSION_BUS_ADDRESS for systemd user services
        if not env.get("DBUS_SESSION_BUS_ADDRESS"):
            uid = os.getuid()
            bus_path = Path(f"/run/user/{uid}/bus")
            if bus_path.exists():
                env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus_path}"

        return env

    def is_desktop_ready(self) -> bool:
        """Verifies if the graphical desktop session (D-Bus notification daemon) is available."""
        env = self._get_desktop_env()
        try:
            # Query org.freedesktop.Notifications owner on session bus
            res = subprocess.run(
                ["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
                 "--object-path", "/org/freedesktop/DBus",
                 "--method", "org.freedesktop.DBus.GetNameOwner", "org.freedesktop.Notifications"],
                env=env,
                capture_output=True,
                text=True,
                timeout=2,
            )
            return res.returncode == 0 and "org.freedesktop.Notifications" not in res.stderr
        except Exception:
            return False

    def wait_for_desktop_session(self, timeout_sec: int = 45) -> bool:
        """Waits during boot until the user logs into their desktop and notification server is active."""
        start = time.time()
        while time.time() - start < timeout_sec:
            if self.is_desktop_ready():
                return True
            time.sleep(2)
        return False

    def send(
        self,
        title: str,
        message: str,
        urgency: str = "normal",
        timeout_ms: int = 6000,
        custom_icon: Optional[str] = None,
        wait_if_booting: bool = False,
    ) -> bool:
        """
        Dispatches a desktop notification with audit logging.
        """
        if wait_if_booting and not self.is_desktop_ready():
            self.wait_for_desktop_session(timeout_sec=30)

        env = self._get_desktop_env()
        icon = custom_icon or str(self.icon_path)
        cmd = ["notify-send", "-a", self.app_name, "-u", urgency, "-t", str(timeout_ms), title, message]
        if Path(icon).exists():
            cmd.extend(["-i", icon])

        success = False
        try:
            res = subprocess.run(cmd, env=env, timeout=4, capture_output=True, text=True)
            success = (res.returncode == 0)
        except Exception as e:
            logger.debug(f"Notification dispatch error: {e}")

        # Audit log to output/notifications.log
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status_tag = "DELIVERED" if success else "FAILED"
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] [{status_tag}] {title} | {message.replace(chr(10), ' ')}\n")
        except Exception:
            pass

        return success

    def send_desktop_login_banner(self) -> bool:
        """
        Dispatched whenever the user logs into their desktop session.
        Gives full visual visibility into today's YouTube and Social agent status.
        """
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        yt_file = config.OUTPUT_DIR / "youtube_daily_tracker.json"
        soc_file = config.OUTPUT_DIR / "social_daily_tracker.json"

        yt_status = "Pending ⏳"
        yt_runs = 0
        if yt_file.exists():
            try:
                data = json.loads(yt_file.read_text(encoding="utf-8"))
                if data.get("last_run_date") == today_str and data.get("runs_today_count", 0) >= 1:
                    yt_runs = data.get("runs_today_count", 1)
                    yt_status = f"Completed ({yt_runs}/1) ✅"
            except Exception:
                pass

        soc_status = "Pending ⏳"
        if soc_file.exists():
            try:
                sdata = json.loads(soc_file.read_text(encoding="utf-8"))
                if sdata.get("last_post_date") == today_str and sdata.get("posts_today_count", 0) >= 1:
                    sposts = sdata.get("posts_today_count", 1)
                    soc_status = f"Posted ({sposts}/1) ✅"
                else:
                    soc_status = "Active & Monitoring 🟢"
            except Exception:
                pass

        title = "🤖 YouTube & Social Media AI Active"
        body = f"🎬 YouTube: {yt_status}\n📱 Social AI: {soc_status}\n⚙️ Background Daemon: Running"

        return self.send(title, body, urgency="normal", timeout_ms=8000)

    # -------------------------------------------------------------------------
    # Milestone Notification Helpers
    # -------------------------------------------------------------------------
    def notify_youtube_start(self, topic: Optional[str] = None):
        t_text = f"Topic: '{topic[:40]}...'" if topic else "Trilingual batch (EN, HI, GU)"
        self.send(
            "🎬 YouTube Agent Starting",
            f"Generating trilingual video package...\n{t_text}",
            urgency="normal",
            timeout_ms=5000,
        )

    def notify_youtube_success(self, count: int = 3, sample_url: Optional[str] = None):
        msg = f"Successfully generated & uploaded {count} Shorts (EN, HI, GU) to YouTube!"
        if sample_url:
            msg += f"\nLive URL: {sample_url}"
        self.send("🎉 YouTube Shorts Published Live!", msg, urgency="normal", timeout_ms=8000)

    def notify_youtube_quota_reached(self):
        self.send(
            "✨ YouTube Daily Quota Up To Date",
            "Today's YouTube Short (1/1) is already published. Background monitor active.",
            urgency="low",
            timeout_ms=5000,
        )

    def notify_social_start(self, campaign_name: str = "Royal Enfield Chamunda"):
        self.send(
            "📱 Social Media Agent Starting",
            f"Campaign: '{campaign_name}'\nPreparing Story & Status for WhatsApp, Instagram, Facebook...",
            urgency="normal",
            timeout_ms=5000,
        )

    def notify_social_success(self, campaign_name: str, platforms: List[str]):
        p_str = ", ".join([p.capitalize() for p in platforms]) or "Social Platforms"
        self.send(
            "🎉 Social Campaign Live!",
            f"'{campaign_name}' successfully published to {p_str}!",
            urgency="normal",
            timeout_ms=8000,
        )

    def notify_social_queued(self, item_name: str, platforms: List[str], reason: str = ""):
        p_str = ", ".join([p.capitalize() for p in platforms]) or "Social Platforms"
        r_text = f" ({reason[:40]})" if reason else ""
        self.send(
            "📦 Social Post Queued for Auto-Retry",
            f"Item: {item_name}\nSaved to hourly retry queue for {p_str}{r_text}.",
            urgency="normal",
            timeout_ms=6000,
        )

    def notify_social_quota_reached(self):
        self.send(
            "✨ Social Media Daily Quota Up To Date",
            "Today's daily social post (1/1) is already completed. Next scheduled run tomorrow.",
            urgency="low",
            timeout_ms=5000,
        )


notifier = DesktopNotifier()
