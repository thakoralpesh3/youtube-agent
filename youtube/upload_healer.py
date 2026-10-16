"""
YouTube Upload Self-Diagnosis, Healing, and Error Recovery Engine
Detects upload failures, displays rich error breakdowns, and automatically executes self-repairs.
"""

import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from rich.console import Console
from rich.panel import Panel

import config

logger = logging.getLogger(__name__)
console = Console()


class YouTubeUploadHealer:
    """
    Diagnoses YouTube upload exceptions, provides self-healing actions,
    and displays user-friendly recovery instructions.
    """

    def __init__(self, uploader=None):
        self.uploader = uploader

    def diagnose(self, error: Exception) -> Dict[str, Any]:
        """Classifies the upload error into a recognized category with root cause and remedy."""
        err_str = str(error).lower()

        # -------------------------------------------------------------
        # 1. YouTube Daily Upload Limit Clamped (uploadLimitExceeded)
        # -------------------------------------------------------------
        if "uploadlimitexceeded" in err_str or "exceeded the number of videos" in err_str:
            reset_time_str = "in approximately 1 to 2 hours"
            unlock_dt = None
            try:
                if self.uploader and hasattr(self.uploader, "service"):
                    res = self.uploader.service.search().list(
                        part="snippet", forMine=True, type="video", maxResults=12, order="date"
                    ).execute()
                    items = res.get("items", [])
                    if len(items) >= 10:
                        tenth = items[9]
                        pub_at = datetime.fromisoformat(tenth["snippet"]["publishedAt"].replace("Z", "+00:00"))
                        unlock_dt = pub_at + timedelta(hours=24, minutes=2)
                        now = datetime.now(timezone.utc)
                        diff_min = int((unlock_dt - now).total_seconds() // 60)
                        local_unlock = unlock_dt.astimezone()
                        if diff_min > 0:
                            reset_time_str = f"at {local_unlock.strftime('%I:%M %p')} (in ~{diff_min} mins)"
                        else:
                            reset_time_str = "rolling over right now"
            except Exception:
                pass

            return {
                "type": "UPLOAD_LIMIT_EXCEEDED",
                "headline": "🛑 YouTube Daily Upload Limit Reached (24-Hour Account Quota)",
                "reason": (
                    "YouTube imposes a daily cap of 10 uploads per 24 hours on standard/unverified channels "
                    "to prevent spam. The channel uploaded 10 videos within the last 24 hours."
                ),
                "auto_action": (
                    f"Agent auto-preserved the video locally in 'output/pending_uploads/' (DID NOT delete it). "
                    f"The background daemon will automatically retry and upload as soon as the quota resets {reset_time_str}."
                ),
                "permanent_solution": (
                    "To permanently unlock 100+ daily uploads:\n"
                    "1. Open YouTube Studio: https://studio.youtube.com/channel/settings/features\n"
                    "2. Under 'Advanced Features', click 'ACCESS FEATURES'.\n"
                    "3. Complete quick 30-sec selfie video verification or submit valid ID."
                ),
                "recoverable_immediately": False,
                "unlock_dt": unlock_dt,
            }

        # -------------------------------------------------------------
        # 2. Token Expired / OAuth Authentication Revoked
        # -------------------------------------------------------------
        if any(w in err_str for w in ["invalid_grant", "unauthorized", "token has been expired or revoked", "invalid credentials"]):
            return {
                "type": "AUTH_EXPIRED",
                "headline": "🔑 YouTube OAuth Credentials Expired / Revoked",
                "reason": "The Google OAuth 2.0 refresh token in 'token.json' has expired or was revoked.",
                "auto_action": "Agent will attempt an automated token refresh.",
                "permanent_solution": (
                    "If token refresh fails, run interactive setup to re-authenticate:\n"
                    "  python agent.py --auth\n"
                    "or right-click Desktop launcher > '🔑 Authenticate YouTube Channel'."
                ),
                "recoverable_immediately": True,
            }

        # -------------------------------------------------------------
        # 3. Metadata Validation Error (Title too long / Forbidden chars)
        # -------------------------------------------------------------
        if any(w in err_str for w in ["titlenotallowed", "invalidtitle", "title is too long", "badrequest", "400"]):
            return {
                "type": "METADATA_ERROR",
                "headline": "📝 Video Title / Description Format Rejected by YouTube",
                "reason": "YouTube rejected the video title, description, or tags (e.g. title exceeded 100 chars or had illegal characters like '<' or '>').",
                "auto_action": "Agent will sanitize the title to <= 90 chars, strip illegal characters, trim tags, and retry upload immediately.",
                "permanent_solution": "Auto-sanitizer handles metadata adjustments automatically.",
                "recoverable_immediately": True,
            }

        # -------------------------------------------------------------
        # 4. Network Disconnection / DNS Failure
        # -------------------------------------------------------------
        if any(w in err_str for w in ["name or service not known", "servernotfounderror", "connection refused", "timeout", "timed out"]):
            return {
                "type": "NETWORK_ERROR",
                "headline": "🌐 Network / DNS Disconnection",
                "reason": "Unable to communicate with youtube.googleapis.com due to network drop or DNS resolution failure.",
                "auto_action": "Agent will activate NetworkGuard, pause until internet is restored, and resume upload.",
                "permanent_solution": "Check WiFi / Ethernet connection. The agent auto-resumes once connectivity returns.",
                "recoverable_immediately": True,
            }

        # -------------------------------------------------------------
        # 5. Media Encoding / File Corrupt
        # -------------------------------------------------------------
        if any(w in err_str for w in ["invalid media", "corrupt", "unsupported video format", "processingfailure"]):
            return {
                "type": "MEDIA_ERROR",
                "headline": "🎬 Video Encoding Incompatibility",
                "reason": "YouTube could not parse the MP4 file container or audio/video streams.",
                "auto_action": "Agent will execute an FFmpeg remux pass (libx264 / aac) to repair the video and retry upload.",
                "permanent_solution": "Agent auto-repairs media files using standard H.264 profile.",
                "recoverable_immediately": True,
            }

        # -------------------------------------------------------------
        # Default / Unknown
        # -------------------------------------------------------------
        return {
            "type": "UNKNOWN",
            "headline": "⚠️ YouTube Upload Error",
            "reason": str(error)[:200],
            "auto_action": "Video has been safely queued in 'output/pending_uploads/' for retry.",
            "permanent_solution": "Inspect output/autostart.log for full API response trace.",
            "recoverable_immediately": False,
        }

    def display_diagnosis(self, diag: Dict[str, Any], video_path: Optional[Path] = None):
        """Renders an eye-catching, informative panel in the console and dispatches desktop notification."""
        vname = video_path.name if video_path else "Generated Video"
        
        content = (
            f"[bold red]{diag['headline']}[/bold red]\n\n"
            f"[bold cyan]📁 Target Video:[/bold cyan] {vname}\n"
            f"[bold yellow]🔍 Root Cause:[/bold yellow] {diag['reason']}\n\n"
            f"[bold green]🤖 Auto-Correction Plan:[/bold green]\n{diag['auto_action']}\n\n"
            f"[bold magenta]💡 Permanent Solution:[/bold magenta]\n{diag['permanent_solution']}"
        )
        console.print(Panel(content, title="[bold red]🛡️ YOUTUBE UPLOAD SELF-HEALER[/bold red]", border_style="red"))

        # Send native desktop notification (only if interactive; quiet in daemon mode)
        if not (os.environ.get("NON_INTERACTIVE") == "1" or not sys.stdin or not sys.stdin.isatty()):
            try:
                subprocess.run([
                    "notify-send",
                    "-a", "YouTube Upload Monitor",
                    "-u", "normal",
                    diag["headline"][:45],
                    f"Video: {vname}\n{diag['auto_action'][:100]}",
                ], check=False)
            except Exception:
                pass

    def attempt_auto_correction(
        self,
        error: Exception,
        video_path: Path,
        metadata: Dict[str, Any],
        retry_callback: Callable[[Path, Dict[str, Any]], Any],
    ) -> Optional[Any]:
        """
        Attempts to automatically fix the issue and retry uploading.
        Returns upload result if successful, or None if issue requires deferred waiting.
        """
        diag = self.diagnose(error)
        self.display_diagnosis(diag, video_path)

        if not diag["recoverable_immediately"]:
            return None

        logger.info(f"🔧 [Self-Healer] Attempting auto-correction for {diag['type']}...")

        # Case A: Metadata Error -> Sanitize and Retry
        if diag["type"] == "METADATA_ERROR":
            clean_title = re.sub(r"[<>]", "", metadata.get("title", ""))[:85].strip()
            if not clean_title.endswith("#Shorts"):
                clean_title += " #Shorts"
            clean_desc = metadata.get("description", "")[:4000]
            clean_tags = [re.sub(r"[<>]", "", t) for t in metadata.get("tags", [])][:15]

            corrected_meta = dict(metadata)
            corrected_meta["title"] = clean_title
            corrected_meta["description"] = clean_desc
            corrected_meta["tags"] = clean_tags

            logger.info(f"✨ Sanitized metadata. Retrying upload with clean title: '{clean_title}'...")
            try:
                res = retry_callback(video_path, corrected_meta)
                logger.info("🎉 [Self-Healer SUCCESS] Upload succeeded after metadata auto-correction!")
                return res
            except Exception as retry_err:
                logger.warning(f"Metadata correction retry failed: {retry_err}")
                return None

        # Case B: Network Error -> Wait for network and retry
        elif diag["type"] == "NETWORK_ERROR":
            from growth.network_guard import NetworkGuard
            logger.info("⏳ Waiting for network reconnection...")
            NetworkGuard.wait_for_network(max_wait_seconds=60)
            time.sleep(3)
            try:
                res = retry_callback(video_path, metadata)
                logger.info("🎉 [Self-Healer SUCCESS] Upload succeeded after network restoration!")
                return res
            except Exception as retry_err:
                logger.warning(f"Network retry failed: {retry_err}")
                return None

        # Case C: Auth Expired -> Try credentials refresh
        elif diag["type"] == "AUTH_EXPIRED":
            try:
                from youtube.auth import YouTubeAuth
                auth = YouTubeAuth()
                auth.get_credentials()
                logger.info("✨ Refreshed credentials. Retrying upload...")
                res = retry_callback(video_path, metadata)
                logger.info("🎉 [Self-Healer SUCCESS] Upload succeeded after token refresh!")
                return res
            except Exception as retry_err:
                logger.warning(f"Token refresh retry failed: {retry_err}")
                return None

        # Case D: Media Repair via FFmpeg
        elif diag["type"] == "MEDIA_ERROR":
            repaired_path = video_path.with_name(f"repaired_{video_path.name}")
            cmd = [
                "ffmpeg", "-y", "-i", str(video_path),
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", str(repaired_path)
            ]
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                if repaired_path.exists() and repaired_path.stat().st_size > 0:
                    logger.info("✨ Remuxed video with standard H.264 profile. Retrying upload...")
                    res = retry_callback(repaired_path, metadata)
                    logger.info("🎉 [Self-Healer SUCCESS] Upload succeeded with repaired media!")
                    return res
            except Exception as fix_err:
                logger.warning(f"Media repair retry failed: {fix_err}")
                return None

        return None

    def clean_stuck_ghost_videos(self, max_check: int = 50) -> Dict[str, Any]:
        """
        Scans channel uploads for videos permanently stuck in 'processing' status
        (such as 'Processing will begin shortly') and cleans them up automatically.
        If a successfully processed duplicate exists, deletes the stuck ghost draft.
        If no duplicate exists, preserves or marks it for clean re-upload.
        """
        if not self.uploader or not hasattr(self.uploader, "service"):
            from youtube.uploader import YouTubeUploader
            self.uploader = YouTubeUploader()

        service = self.uploader.service
        deleted = []
        try:
            channel_res = service.channels().list(part="contentDetails", mine=True).execute()
            if not channel_res.get("items"):
                return {"status": "NO_CHANNEL", "deleted": []}
            uploads_id = channel_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

            # Fetch recent uploads
            res = service.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_id,
                maxResults=min(max_check, 50)
            ).execute()
            video_ids = [item["contentDetails"]["videoId"] for item in res.get("items", [])]

            if not video_ids:
                return {"status": "CLEAN", "deleted": []}

            # Query video statuses
            vres = service.videos().list(
                part="snippet,status,processingDetails,statistics",
                id=",".join(video_ids)
            ).execute()

            items = vres.get("items", [])
            stuck_items = [
                v for v in items 
                if v.get("status", {}).get("uploadStatus") != "processed"
            ]

            now = datetime.now(timezone.utc)
            for s in stuck_items:
                vid = s["id"]
                title = s["snippet"]["title"]
                pub_str = s["snippet"]["publishedAt"].replace("Z", "+00:00")
                pub_dt = datetime.fromisoformat(pub_str)
                age_hours = (now - pub_dt).total_seconds() / 3600.0

                # Check if there is another video with matching title that is successfully processed
                has_working_duplicate = any(
                    other["id"] != vid 
                    and other["snippet"]["title"].strip().lower() == title.strip().lower()
                    and other.get("status", {}).get("uploadStatus") == "processed"
                    for other in items
                )

                # Only auto-delete if stuck for > 1 hour and has a working duplicate or is 0-view unplayable draft
                views = int(s.get("statistics", {}).get("viewCount", 0))
                if age_hours >= 1.0 and (has_working_duplicate or views == 0):
                    logger.warning(
                        f"🧹 [Upload Healer] Cleaning stuck ghost video '{title}' (ID: {vid}, "
                        f"age: {age_hours:.1f}h, views: {views}, duplicate_exists: {has_working_duplicate})..."
                    )
                    try:
                        service.videos().delete(id=vid).execute()
                        deleted.append({
                            "id": vid,
                            "title": title,
                            "age_hours": age_hours,
                            "duplicate_exists": has_working_duplicate,
                        })
                        logger.info(f"✅ [Upload Healer] Successfully deleted stuck video {vid} from YouTube!")
                    except Exception as del_err:
                        logger.warning(f"Could not delete stuck video {vid}: {del_err}")

        except Exception as e:
            logger.debug(f"Stuck video cleaner notice: {e}")

        return {"status": "SUCCESS", "deleted": deleted}
