#!/usr/bin/env python3
"""
Autonomous 24/7 Cloud Scheduler & Watchdog Daemon for YouTube & Social Agents.
Runs continuously on GitHub Actions (and local environments) to ensure
zero missed uploads, automated channel health auditing, queue recovery,
and multi-agent synchronization around the clock.
"""

import argparse
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("CloudScheduler")

REPO_YOUTUBE = "thakoralpesh3/youtube-agent"
REPO_SOCIAL = "thakoralpesh3/social-media-agent"
WORKFLOW_YOUTUBE = "daily_youtube_agent.yml"
WORKFLOW_SOCIAL = "daily_social_agent.yml"


def get_ist_now() -> datetime.datetime:
    """Returns current datetime in Indian Standard Time (IST, UTC+5:30)."""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    ist_offset = datetime.timedelta(hours=5, minutes=30)
    return utc_now + ist_offset


def get_ist_date_str() -> str:
    """Returns current IST date as YYYY-MM-DD."""
    return get_ist_now().strftime("%Y-%m-%d")


def get_ist_time_str() -> str:
    """Returns current IST time as HH:MM."""
    return get_ist_now().strftime("%H:%M")


def run_gh_cmd(args: List[str], timeout: int = 45) -> Tuple[int, str, str]:
    """Runs a GitHub CLI command safely."""
    gh_path = shutil.which("gh")
    if not gh_path:
        return 1, "", "gh CLI not found in PATH"
    try:
        res = subprocess.run([gh_path] + args, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


class CloudScheduler:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.ist_now = get_ist_now()
        self.today_ist = get_ist_date_str()
        self.time_ist = get_ist_time_str()
        self.report: Dict[str, Any] = {
            "timestamp_ist": self.ist_now.strftime("%Y-%m-%d %H:%M:%S IST"),
            "today_ist": self.today_ist,
            "channel_health": {},
            "youtube_run_status": {},
            "social_run_status": {},
            "actions_taken": [],
            "alerts": [],
        }

    def audit_youtube_channel(self) -> Dict[str, Any]:
        """Audits YouTube OAuth token validity and retrieves channel telemetry."""
        health: Dict[str, Any] = {
            "status": "UNKNOWN",
            "token_valid": False,
            "channel_title": "N/A",
            "subscribers": 0,
            "videos": 0,
            "views": 0,
            "error": None,
        }
        try:
            from youtube.auth import YouTubeAuth
            auth = YouTubeAuth()
            if auth.is_token_valid():
                ch = auth.verify_channel()
                health["status"] = "CONNECTED"
                health["token_valid"] = True
                health["channel_title"] = ch.get("title", "Unknown")
                health["subscribers"] = ch.get("subscribers", 0)
                health["videos"] = ch.get("videos", 0)
                health["views"] = ch.get("views", 0)
                logger.info(
                    f"✅ [YouTube Health] Connected: '{health['channel_title']}' "
                    f"({health['subscribers']} subs, {health['videos']} videos)"
                )
            else:
                health["status"] = "TOKEN_INVALID"
                health["error"] = "OAuth token is expired or unauthorized"
                logger.warning("⚠️ [YouTube Health] OAuth token invalid or needs refresh.")
                self.report["alerts"].append("YouTube OAuth token is invalid or unauthorized.")
        except Exception as e:
            health["status"] = "ERROR"
            health["error"] = str(e)
            logger.error(f"❌ [YouTube Health] Failed to verify channel: {e}")
            self.report["alerts"].append(f"YouTube auth exception: {e}")

        self.report["channel_health"] = health
        return health

    def check_today_workflow_runs(self, workflow: str, repo: str) -> Dict[str, Any]:
        """Checks if a workflow has completed successfully today (IST)."""
        status_info = {
            "completed_today": False,
            "in_progress": False,
            "latest_run_id": None,
            "latest_status": None,
            "latest_conclusion": None,
            "created_at": None,
        }

        # Query recent workflow runs via gh CLI
        code, stdout, stderr = run_gh_cmd([
            "run", "list",
            "--repo", repo,
            "--workflow", workflow,
            "--limit", "10",
            "--json", "databaseId,status,conclusion,createdAt",
        ])

        if code != 0 or not stdout:
            logger.warning(f"Could not fetch runs for {workflow} on {repo}: {stderr}")
            return status_info

        try:
            runs = json.loads(stdout)
            for r in runs:
                created_utc_str = r.get("createdAt", "")
                if not created_utc_str:
                    continue
                # Convert UTC timestamp to IST date
                try:
                    dt_utc = datetime.datetime.fromisoformat(created_utc_str.replace("Z", "+00:00"))
                    dt_ist = dt_utc + datetime.timedelta(hours=5, minutes=30)
                    run_date_ist = dt_ist.strftime("%Y-%m-%d")
                except Exception:
                    run_date_ist = created_utc_str[:10]

                if run_date_ist == self.today_ist:
                    if r.get("status") == "in_progress":
                        status_info["in_progress"] = True
                    if r.get("conclusion") == "success":
                        status_info["completed_today"] = True
                        status_info["latest_run_id"] = r.get("databaseId")
                        status_info["latest_status"] = r.get("status")
                        status_info["latest_conclusion"] = r.get("conclusion")
                        status_info["created_at"] = created_utc_str
                        break

            # If no success today, record latest run anyway
            if not status_info["completed_today"] and runs:
                latest = runs[0]
                status_info["latest_run_id"] = latest.get("databaseId")
                status_info["latest_status"] = latest.get("status")
                status_info["latest_conclusion"] = latest.get("conclusion")
                status_info["created_at"] = latest.get("createdAt")
        except Exception as e:
            logger.warning(f"Failed parsing run list json for {workflow}: {e}")

        return status_info

    def dispatch_workflow(self, workflow: str, repo: str, inputs: Optional[Dict[str, str]] = None) -> bool:
        """Dispatches a workflow run via GitHub CLI."""
        if self.dry_run:
            logger.info(f"🔍 [Dry-Run] Would dispatch '{workflow}' on '{repo}'.")
            self.report["actions_taken"].append(f"[Dry-Run] Dispatch {workflow} on {repo}")
            return True

        args = ["workflow", "run", workflow, "-R", repo]
        if inputs:
            for k, v in inputs.items():
                args.extend(["-f", f"{k}={v}"])

        logger.info(f"🚀 [Cloud Dispatch] Triggering '{workflow}' on '{repo}'...")
        code, stdout, stderr = run_gh_cmd(args, timeout=30)
        if code == 0:
            logger.info(f"✅ [Cloud Dispatch] Successfully triggered '{workflow}' on '{repo}'!")
            self.report["actions_taken"].append(f"Dispatched {workflow} on {repo}")
            return True
        else:
            logger.error(f"❌ [Cloud Dispatch] Failed to trigger '{workflow}': {stderr}")
            self.report["alerts"].append(f"Failed to dispatch {workflow} on {repo}: {stderr}")
            return False

    def sweep_pending_youtube_uploads(self) -> int:
        """Finds any generated videos that failed or were interrupted during upload."""
        try:
            from upload_to_youtube import get_pending_videos
            pending = get_pending_videos()
            count = len(pending)
            if count > 0:
                logger.info(f"🧹 [Queue Recovery] Found {count} pending/un-uploaded video(s) in output directory.")
                if not self.dry_run:
                    logger.info("🚀 [Queue Recovery] Executing upload_to_youtube.py to sweep and publish leftovers...")
                    cmd = [sys.executable, "upload_to_youtube.py"]
                    env = os.environ.copy()
                    env["NON_INTERACTIVE"] = "1"
                    res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
                    if res.returncode == 0:
                        logger.info("✅ [Queue Recovery] Successfully published pending videos!")
                        self.report["actions_taken"].append(f"Swept & published {count} pending video(s)")
                    else:
                        logger.warning(f"⚠️ [Queue Recovery] Sweeper output: {res.stderr.strip()[:200]}")
                else:
                    logger.info(f"🔍 [Dry-Run] Would sweep {count} pending video(s).")
            return count
        except Exception as e:
            logger.warning(f"Notice during pending videos sweep: {e}")
            return 0

    def run_cleaner_and_audit(self) -> bool:
        """Audits YouTube channel videos and cleans stuck processing videos."""
        if self.dry_run:
            logger.info("🔍 [Dry-Run] Would run YouTube stuck video cleaner and auditor.")
            self.report["actions_taken"].append("[Dry-Run] YouTube channel audit & stuck video cleaner")
            return True

        logger.info("🧹 [Channel Auditor] Running YouTube stuck video cleaner & audit...")
        try:
            from youtube.cleaner import YouTubeCleaner
            cleaner = YouTubeCleaner()
            res = cleaner.run_cleaner(delete_failed=True, delete_processing_over_hours=4.0)
            logger.info(f"✅ [Channel Auditor] Completed. Cleaned: {res.get('deleted_count', 0)} videos.")
            self.report["actions_taken"].append(f"Cleaned {res.get('deleted_count', 0)} stuck video(s)")
            return True
        except Exception as e:
            logger.warning(f"Channel cleaner notice: {e}")
            return False

    def execute_heartbeat_cycle(self, force_yt: bool = False, force_soc: bool = False, clean_channel: bool = False):
        """
        Executes one full 24/7 autonomous watchdog cycle:
        1. Checks YouTube OAuth token & channel status.
        2. Evaluates current IST time and checks today's workflow runs.
        3. Recovers any interrupted or leftover video queues.
        4. Dispatches YouTube agent (target: >= 09:00 AM IST) if not completed today.
        5. Runs cleaner (target: >= 09:30 AM IST).
        6. Dispatches Social agent (target: >= 23:30 IST) if not completed today.
        7. Publishes GitHub Actions Step Summary.
        """
        logger.info("=" * 70)
        logger.info(f"🌐 [24/7 Cloud Scheduler Daemon] Starting Watchdog Cycle at {self.report['timestamp_ist']}")
        logger.info("=" * 70)

        # 1. Audit channel & credentials
        self.audit_youtube_channel()

        # 2. Check today's execution state for YouTube
        yt_status = self.check_today_workflow_runs(WORKFLOW_YOUTUBE, REPO_YOUTUBE)
        self.report["youtube_run_status"] = yt_status

        # 3. Check today's execution state for Social Media Agent
        soc_status = self.check_today_workflow_runs(WORKFLOW_SOCIAL, REPO_SOCIAL)
        self.report["social_run_status"] = soc_status

        # 4. Check & sweep pending queues
        self.sweep_pending_youtube_uploads()

        # Parse current IST hour and minute
        now_hour = self.ist_now.hour
        now_minute = self.ist_now.minute

        # 5. Evaluate YouTube Agent execution
        import config
        yt_upload_time = getattr(config, "DAILY_UPLOAD_TIME", "23:30")
        try:
            yt_hour, yt_min = map(int, yt_upload_time.split(":"))
        except Exception:
            yt_hour, yt_min = 23, 30

        is_yt_window = (now_hour > yt_hour) or (now_hour == yt_hour and now_minute >= yt_min)
        if force_yt or (is_yt_window and not yt_status["completed_today"] and not yt_status["in_progress"]):
            reason = "Force requested" if force_yt else f"Due at {yt_upload_time} IST (Current: {self.time_ist} IST, Not completed today)"
            logger.info(f"🚀 [YouTube Agent Decision] Triggering workflow. Reason: {reason}")
            self.dispatch_workflow(WORKFLOW_YOUTUBE, REPO_YOUTUBE)
        elif yt_status["completed_today"]:
            logger.info(f"✨ [YouTube Agent Decision] Today's run already completed (Run ID: {yt_status['latest_run_id']}).")
        elif yt_status["in_progress"]:
            logger.info("⏳ [YouTube Agent Decision] YouTube agent workflow is currently running. Standing by.")
        else:
            logger.info(f"⏳ [YouTube Agent Decision] Standing by until {yt_upload_time} IST (Current: {self.time_ist} IST).")

        # 6. Evaluate Channel Cleaner execution
        cleaner_time = getattr(config, "DAILY_CLEANER_TIME", "23:55")
        try:
            clean_hour, clean_min = map(int, cleaner_time.split(":"))
        except Exception:
            clean_hour, clean_min = 23, 55

        is_cleaner_window = (now_hour > clean_hour) or (now_hour == clean_hour and now_minute >= clean_min)
        if clean_channel or (is_cleaner_window and yt_status["completed_today"]):
            self.run_cleaner_and_audit()

        # 7. Evaluate Social Agent execution
        # Target: >= 11:30 PM IST (23:30)
        is_soc_window = (now_hour == 23 and now_minute >= 30)
        if force_soc or (is_soc_window and not soc_status["completed_today"] and not soc_status["in_progress"]):
            reason = "Force requested" if force_soc else f"Due at 11:30 PM IST (Current: {self.time_ist} IST, Not completed today)"
            logger.info(f"📱 [Social Agent Decision] Triggering workflow. Reason: {reason}")
            self.dispatch_workflow(WORKFLOW_SOCIAL, REPO_SOCIAL)
        elif soc_status["completed_today"]:
            logger.info(f"✨ [Social Agent Decision] Today's social publishing already completed.")
        elif soc_status["in_progress"]:
            logger.info("⏳ [Social Agent Decision] Social agent workflow is currently in progress.")
        else:
            logger.info(f"⏳ [Social Agent Decision] Standing by until 11:30 PM IST (Current: {self.time_ist} IST).")

        # 8. Write Markdown step summary
        self.write_github_step_summary()
        logger.info("🏁 [24/7 Cloud Scheduler Daemon] Watchdog cycle completed successfully.")

    def write_github_step_summary(self):
        """Generates a GitHub Actions Step Summary markdown dashboard."""
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if not summary_path:
            return

        ch = self.report.get("channel_health", {})
        yt = self.report.get("youtube_run_status", {})
        soc = self.report.get("social_run_status", {})
        actions = self.report.get("actions_taken", [])
        alerts = self.report.get("alerts", [])

        yt_badge = "🟢 Completed Today" if yt.get("completed_today") else ("🟡 In Progress" if yt.get("in_progress") else "⚪ Pending / Scheduled")
        soc_badge = "🟢 Completed Today" if soc.get("completed_today") else ("🟡 In Progress" if soc.get("in_progress") else "⚪ Pending / Scheduled")
        ch_badge = "🟢 Healthy & Connected" if ch.get("token_valid") else "🔴 Authentication Alert"

        md = []
        md.append("# 🌐 YouTube & Social Agent 24/7 Cloud Scheduler Dashboard")
        md.append(f"**Execution Timestamp:** `{self.report['timestamp_ist']}` | **Current IST Date:** `{self.today_ist}`\n")

        md.append("## 📊 Autonomous 24/7 Status Overview")
        md.append("| Agent / System | Target Schedule | Today's Status | Channel / Run Details |")
        md.append("| :--- | :--- | :--- | :--- |")
        md.append(f"| **🎬 Daily YouTube Agent** | 11:30 PM IST daily | {yt_badge} | Latest Run: `{yt.get('latest_run_id') or 'N/A'}` (`{yt.get('latest_conclusion') or yt.get('latest_status') or 'Pending'}`) |")
        md.append(f"| **📱 Daily Social Agent** | 11:30 PM IST daily | {soc_badge} | Latest Run: `{soc.get('latest_run_id') or 'N/A'}` (`{soc.get('latest_conclusion') or soc.get('latest_status') or 'Pending'}`) |")
        md.append(f"| **📺 YouTube Channel Health** | 24/7 Continuous | {ch_badge} | Channel: **{ch.get('channel_title', 'Unknown')}** (Subs: {ch.get('subscribers', 0)}, Videos: {ch.get('videos', 0)}) |")
        md.append("")

        if actions:
            md.append("### ⚡ Actions Executed in this Cycle")
            for a in actions:
                md.append(f"- ✅ {a}")
            md.append("")

        if alerts:
            md.append("### ⚠️ Active Alerts & Diagnostics")
            for alt in alerts:
                md.append(f"- ⚠️ {alt}")
            md.append("")

        md.append("### ⏰ Daily Autonomous Milestones")
        md.append("- **11:30 PM IST**: Trilingual Shorts (EN, HI, GU) & 16:9 Landscape Video Generation & Upload.")
        md.append("- **11:30 PM IST**: Social Story Publishing (WhatsApp Status, Instagram Story, Facebook Story).")
        md.append("- **23:55 PM IST**: 1-Click Stuck Video Cleaner & Channel Auditor.")
        md.append("- **Hourly (24/7)**: Cloud Watchdog heartbeat, queue recovery, and failure retry dispatch.")

        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write("\n".join(md) + "\n")
            logger.info("📝 [Step Summary] Successfully updated GITHUB_STEP_SUMMARY.")
        except Exception as e:
            logger.warning(f"Could not write step summary: {e}")


def main():
    parser = argparse.ArgumentParser(description="24/7 Cloud Scheduler for YouTube & Social Agents")
    parser.add_argument("--heartbeat", action="store_true", help="Run standard 24/7 watchdog cycle")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate state without dispatching actions")
    parser.add_argument("--force-youtube", action="store_true", help="Force immediate YouTube agent dispatch")
    parser.add_argument("--force-social", action="store_true", help="Force immediate Social agent dispatch")
    parser.add_argument("--clean-channel", action="store_true", help="Run YouTube stuck video cleaner and audit")
    args = parser.parse_args()

    scheduler = CloudScheduler(dry_run=args.dry_run)
    scheduler.execute_heartbeat_cycle(
        force_yt=args.force_youtube,
        force_soc=args.force_social,
        clean_channel=args.clean_channel,
    )


if __name__ == "__main__":
    main()
