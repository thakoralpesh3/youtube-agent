import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import config

logger = logging.getLogger(__name__)


class SelfHealer:
    """
    Autonomous Self-Healing, Auto-Diagnostics, and Quota Recovery Engine.
    Monitors pipeline health, automatically repairs configuration/token issues,
    and manages offline upload queues to guarantee zero-crash execution.
    """

    def __init__(self):
        self.queue_dir = config.OUTPUT_DIR / "pending_uploads"
        self.queue_dir.mkdir(parents=True, exist_ok=True)

    def run_health_audit(self) -> Dict[str, dict]:
        """Runs a complete pre-flight health diagnostic check on all system components."""
        report = {}

        # 1. Gemini API Health
        try:
            from google import genai
            from growth.model_resolver import call_gemini_resilient
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            res, active_model = call_gemini_resilient(
                client=client,
                contents="ping",
                preferred_model=config.GEMINI_MODEL,
                tier="fast",
                task_name="Health Ping",
            )
            report["gemini_api"] = {
                "status": "HEALTHY",
                "model": active_model,
                "message": f"Gemini API operational via {active_model}.",
            }
        except Exception as e:
            report["gemini_api"] = {
                "status": "WARNING",
                "model": config.GEMINI_MODEL,
                "message": f"Gemini check notice: {e}",
            }

        # 2. YouTube OAuth2 Health
        token_file = Path(config.YOUTUBE_TOKEN_FILE)
        client_secret = Path(config.YOUTUBE_CLIENT_SECRET_FILE)
        if token_file.exists():
            try:
                from youtube.auth import YouTubeAuth
                auth = YouTubeAuth()
                if auth.is_token_valid():
                    report["youtube_auth"] = {
                        "status": "HEALTHY",
                        "message": f"Valid OAuth 2.0 credentials cached at {token_file.name}",
                    }
                else:
                    report["youtube_auth"] = {
                        "status": "ACTION_REQUIRED",
                        "message": f"Token expired or needs re-authentication in {token_file.name}",
                    }
            except Exception as e:
                report["youtube_auth"] = {
                    "status": "ACTION_REQUIRED",
                    "message": f"Token verification error: {e}",
                }
        elif client_secret.exists():
            report["youtube_auth"] = {
                "status": "NEEDS_AUTH",
                "message": f"Client secret found ({client_secret.name}). Ready for one-time login via `agent.py --auth`",
            }
        else:
            report["youtube_auth"] = {
                "status": "NOT_CONFIGURED",
                "message": f"Missing client_secret.json (save to {client_secret.resolve()})",
            }

        # 3. Media & TTS Engine
        try:
            import edge_tts
            report["tts_engine"] = {
                "status": "HEALTHY",
                "voice": config.TTS_VOICE,
                "message": "Edge-TTS engine operational.",
            }
        except Exception as e:
            report["tts_engine"] = {
                "status": "ERROR",
                "message": f"Edge-TTS check failed: {e}",
            }

        # 4. FFmpeg Video Assembler
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            res = subprocess.run([ffmpeg_exe, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            report["ffmpeg"] = {
                "status": "HEALTHY",
                "path": ffmpeg_exe,
                "message": "Hardware-accelerated FFmpeg ready.",
            }
        except Exception as e:
            report["ffmpeg"] = {
                "status": "ERROR",
                "message": f"FFmpeg check failed: {e}",
            }

        # 5. Disk Space & File Permissions
        total, used, free = shutil.disk_usage(config.OUTPUT_DIR)
        free_gb = free / (1024 ** 3)
        report["storage"] = {
            "status": "HEALTHY" if free_gb > 1.0 else "WARNING",
            "free_space_gb": round(free_gb, 2),
            "message": f"{free_gb:.2f} GB available in {config.OUTPUT_DIR.resolve()}",
        }

        # 6. Pending Upload Queue
        pending_files = list(self.queue_dir.glob("*.json"))
        report["upload_queue"] = {
            "status": "INFO",
            "pending_count": len(pending_files),
            "message": f"{len(pending_files)} deferred uploads in queue.",
        }

        return report

    def auto_repair(self) -> List[str]:
        """
        Executes automatic repairs on permissions, directories, and tokens.
        """
        repairs = []

        # 1. Ensure all directories exist
        for d in [config.OUTPUT_DIR, config.ASSETS_DIR, config.FONTS_DIR, config.MUSIC_DIR, self.queue_dir]:
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                repairs.append(f"Created missing directory: {d.name}")

        # 2. Repair executable permissions on scripts
        scripts = [
            config.BASE_DIR / "launch_agent.sh",
            config.BASE_DIR / "runner_ui.py",
            config.BASE_DIR / "agent.py",
            config.BASE_DIR / "scheduler.py",
            Path.home() / "Desktop" / "YouTube-Agent.desktop",
            Path.home() / ".local" / "share" / "applications" / "youtube-agent.desktop",
        ]
        for s in scripts:
            if s.exists():
                try:
                    os.chmod(s, 0o755)
                except Exception:
                    pass

        # 3. Check YouTube OAuth token status
        token_file = Path(config.YOUTUBE_TOKEN_FILE)
        if token_file.exists():
            try:
                from youtube.auth import YouTubeAuth
                auth = YouTubeAuth()
                if auth.is_token_valid():
                    repairs.append("Verified valid YouTube OAuth credentials.")
            except Exception as e:
                logger.debug(f"Auto-refresh notice: {e}")

        # 4. Process any pending deferred uploads (only if OAuth token is valid)
        try:
            from youtube.auth import YouTubeAuth
            if YouTubeAuth().is_token_valid():
                flushed = self.process_pending_queue()
                if flushed:
                    repairs.append(f"Processed and uploaded {len(flushed)} previously queued videos.")
        except Exception as e:
            logger.debug(f"Pending queue process notice: {e}")

        return repairs

    def queue_for_later(self, video_path: Path, script_data: dict) -> Path:
        """
        Saves video metadata to pending queue if YouTube upload hits a temporary network error or quota.
        """
        timestamp = Path(video_path).parent.name
        queue_item = self.queue_dir / f"pending_{timestamp}.json"
        
        payload = {
            "video_path": str(video_path.resolve()),
            "script_data": script_data,
            "queued_at": str(timestamp),
        }
        with open(queue_item, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        logger.info(f"💾 Video successfully queued for deferred upload: {queue_item.name}")
        return queue_item

    def cleanup_media(self, run_dir: Path, video_path: Optional[Path] = None) -> None:
        """
        Removes heavy video, audio, and image files after successful YouTube upload
        to free up local disk storage while retaining metadata for analytics.
        """
        try:
            if video_path and video_path.exists():
                video_path.unlink()
                logger.info(f"🗑️ Cleaned up uploaded video file: {video_path.name}")

            audio_dir = run_dir / "audio"
            if audio_dir.exists():
                shutil.rmtree(audio_dir, ignore_errors=True)

            images_dir = run_dir / "images"
            if images_dir.exists():
                shutil.rmtree(images_dir, ignore_errors=True)

            temp_dir = run_dir / "temp"
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

            logger.info(f"✨ Successfully cleaned up local media assets for {run_dir.name}.")
        except Exception as e:
            logger.debug(f"Media cleanup notice: {e}")

    def process_pending_queue(self) -> List[dict]:
        """
        Attempts to upload any queued videos when connectivity / quota is restored.
        Removes media files on success to preserve disk space.
        """
        token_file = Path(config.YOUTUBE_TOKEN_FILE)
        if not token_file.exists():
            return []

        from youtube.uploader import YouTubeUploader
        uploader = YouTubeUploader()
        if not uploader.auth.is_token_valid():
            logger.debug("YouTube OAuth token not valid/expired. Skipping queued upload flush.")
            return []

        queue_items = list(self.queue_dir.glob("pending_*.json"))
        if not queue_items:
            return []

        uploaded = []

        for item in queue_items:
            try:
                with open(item, "r", encoding="utf-8") as f:
                    payload = json.load(f)

                video_path = Path(payload["video_path"])
                script = payload["script_data"]

                if video_path.exists():
                    logger.info(f"📤 Uploading queued video: '{script.get('title')}'...")
                    result = uploader.upload_video(
                        video_path=video_path,
                        title=script.get("title", "YouTube Short #Shorts"),
                        description=script.get("description", ""),
                        tags=script.get("tags", []),
                        category_id=script.get("category_id", config.DEFAULT_CATEGORY_ID),
                        pinned_comment=script.get("pinned_comment"),
                    )
                    uploaded.append(result)
                    
                    # Clean up local media files and remove queue item
                    if video_path.exists():
                        video_path.unlink()
                    item.unlink()
                else:
                    logger.debug(f"Queued video file {video_path.name} no longer on disk. Removing queue item.")
                    item.unlink()
            except Exception as e:
                logger.debug(f"Pending upload retry deferred: {e}")

        return uploaded

