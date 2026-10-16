import datetime
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from syndication.browser_uploader import BrowserUploader
from syndication.api_uploader import DirectSocialApiUploader
from syndication.daily_limiter import limiter


logger = logging.getLogger(__name__)

QUEUE_LOCK = threading.Lock()
SUPPORTED_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".jpg", ".jpeg", ".png", ".webp"
}


class SocialQueueManager:
    """
    Manages persistent storage and retries for social media content.
    If content fails to upload to Instagram, Facebook, or WhatsApp,
    it is stored in Story/pending/ and tracked in output/pending_social/queue.json.
    
    The scheduler checks this queue hourly to automatically retry only
    the platforms that failed, until all platforms succeed.
    """

    def __init__(self):
        self.queue_dir = config.OUTPUT_DIR / "pending_social"
        self.queue_file = self.queue_dir / "queue.json"
        
        self.story_dir = config.BASE_DIR / "Story"
        self.pending_dir = self.story_dir / "pending"
        self.completed_dir = self.story_dir / "completed"
        self.failed_dir = self.story_dir / "failed"

        for d in [self.queue_dir, self.story_dir, self.pending_dir, self.completed_dir, self.failed_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.api_uploader = DirectSocialApiUploader()

        if not self.queue_file.exists():
            self._save_raw([])

    def _save_raw(self, items: List[Dict[str, Any]]) -> None:
        temp_file = self.queue_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(items, indent=2), encoding="utf-8")
        temp_file.replace(self.queue_file)

    def load_queue(self) -> List[Dict[str, Any]]:
        """Loads all items from queue.json safely with thread lock."""
        with QUEUE_LOCK:
            if not self.queue_file.exists():
                return []
            try:
                return json.loads(self.queue_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Error loading social queue: {e}")
                return []

    def save_queue(self, items: List[Dict[str, Any]]) -> None:
        """Saves all items to queue.json safely with thread lock."""
        with QUEUE_LOCK:
            self._save_raw(items)

    def enqueue_failed(
        self,
        media_path: Path,
        caption: str,
        target_platforms: Optional[List[str]] = None,
        published_platforms: Optional[List[str]] = None,
        failed_platforms: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Stores failed/partial upload in Story/pending/ and records in queue.json.
        Preserves original caption and registers remaining pending platforms.
        """
        target_platforms = [p.lower() for p in (target_platforms or ["instagram", "facebook", "whatsapp"])]
        published_platforms = [p.lower() for p in (published_platforms or [])]
        failed_platforms = failed_platforms or {}

        pending_platforms = [p for p in target_platforms if p not in published_platforms]

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = f"social_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        # Move media file to Story/pending/
        dest_media_name = f"{timestamp}_{media_path.name}"
        dest_media_path = self.pending_dir / dest_media_name

        is_post_media = "post" in [p.lower() for p in media_path.parts]
        if media_path.exists():
            try:
                if is_post_media:
                    shutil.copy2(str(media_path), str(dest_media_path))
                    logger.info(f"🔒 [Social Queue] Preserved original '{media_path.name}' in {media_path.parent} (never deleted)!")
                else:
                    shutil.move(str(media_path), str(dest_media_path))
            except Exception:
                shutil.copy2(str(media_path), str(dest_media_path))
        else:
            # Check if file was already moved to completed directory by another worker
            completed_matches = list(self.completed_dir.glob(f"*_{media_path.name}"))
            if completed_matches:
                logger.info(f"✨ [Social Queue] '{media_path.name}' is already completed ({completed_matches[0].name}). Skipping duplicate enqueue.")
                return {"status": "COMPLETED", "pending_platforms": [], "published_platforms": target_platforms}
            if not self.pending_dir.joinpath(media_path.name).exists() and not media_path.exists():
                logger.warning(f"⚠️ [Social Queue] Cannot enqueue non-existent media: {media_path}")
                return {"status": "FAILED", "pending_platforms": [], "published_platforms": []}
            dest_media_path = media_path  # If already in pending

        # Save caption alongside media
        dest_caption_path = dest_media_path.with_suffix(".txt")
        dest_caption_path.write_text(caption, encoding="utf-8")

        queue_item = {
            "id": unique_id,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_attempt_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "media_path": str(dest_media_path.resolve()),
            "caption_path": str(dest_caption_path.resolve()),
            "caption": caption,
            "target_platforms": target_platforms,
            "published_platforms": published_platforms,
            "pending_platforms": pending_platforms,
            "retry_count": 0,
            "max_retries": 10,
            "status": "PENDING",
            "errors": failed_platforms,
            "metadata": metadata or {},
        }

        items = self.load_queue()
        items.append(queue_item)
        self.save_queue(items)

        logger.info(
            f"📦 [Social Queue] Stored '{dest_media_name}' for hourly retry. "
            f"Pending platforms: {', '.join(pending_platforms)} (Published: {', '.join(published_platforms) or 'None'})"
        )

        # Log storage without popping noisy desktop notifications
        return queue_item

    def get_pending_items(self) -> List[Dict[str, Any]]:
        """Returns all items currently awaiting retry (auto-archives items older than 24h)."""
        items = self.load_queue()
        pending = []
        needs_save = False
        now = datetime.datetime.now()
        for item in items:
            if item.get("status") == "PENDING" and item.get("pending_platforms"):
                mpath = Path(item.get("media_path", ""))
                created_str = item.get("created_at")
                is_stale = False
                if created_str:
                    try:
                        created_dt = datetime.datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S")
                        if (now - created_dt).total_seconds() > 86400:  # older than 24h
                            is_stale = True
                    except Exception:
                        pass

                if is_stale or not mpath.exists():
                    item["status"] = "ARCHIVED_STALE"
                    needs_save = True
                    continue

                pending.append(item)

        if needs_save:
            self.save_queue(items)
        return pending

    def recover_stranded_failed_files(self) -> int:
        """
        Scans Story/failed/ directory to automatically recover any previous
        failed media files and import them into the hourly retry queue.
        """
        recovered_count = 0
        items = self.load_queue()
        existing_paths = {Path(it.get("media_path", "")).name for it in items}

        for f in self.failed_dir.iterdir():
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                if f.name in existing_paths:
                    continue

                # Look for matching caption file
                cap_file = f.with_suffix(".txt")
                if cap_file.exists():
                    caption = cap_file.read_text(encoding="utf-8").strip()
                else:
                    caption = f"🔥 Royal Enfield Specialized Care\n\n#ChamundaAutomobile #RoyalEnfield #Bullet #Classic350"

                logger.info(f"🔄 [Social Queue] Recovering stranded failed file: {f.name}")
                self.enqueue_failed(
                    media_path=f,
                    caption=caption,
                    target_platforms=["instagram", "facebook", "whatsapp"],
                    published_platforms=[],
                    failed_platforms={"general": "Recovered from Story/failed"},
                    metadata={"source": "recovered_failed_dir"},
                )
                if cap_file.exists():
                    try:
                        cap_file.unlink()
                    except Exception:
                        pass
                recovered_count += 1

        return recovered_count

    def retry_item(
        self,
        item_id: str,
        uploader: Optional[BrowserUploader] = None,
        api_uploader: Optional[DirectSocialApiUploader] = None,
    ) -> Dict[str, Any]:
        """
        Retries uploading a specific queue item ONLY for the platforms that are still pending.
        Uses fast Direct API first, then falls back to Browser automation if API is unconfigured/failed.
        """
        items = self.load_queue()
        target_item = None
        for it in items:
            if it.get("id") == item_id:
                target_item = it
                break

        if not target_item:
            return {"status": "ERROR", "message": f"Item {item_id} not found in queue"}

        media_path = Path(target_item.get("media_path", ""))
        if not media_path.exists():
            target_item["status"] = "FILE_MISSING"
            self.save_queue(items)
            return {"status": "ERROR", "message": f"Media file {media_path} does not exist"}

        caption = target_item.get("caption", "")
        pending_platforms = list(target_item.get("pending_platforms", []))
        published_platforms = target_item.get("published_platforms", [])
        errors = target_item.get("errors", {})

        if not pending_platforms:
            target_item["status"] = "COMPLETED"
            self.save_queue(items)
            return {"status": "ALREADY_COMPLETED", "item": target_item}

        uploader = uploader or BrowserUploader()
        api_uploader = api_uploader or self.api_uploader

        logger.info(
            f"🔄 [Social Queue] Retrying {media_path.name} (Attempt #{target_item.get('retry_count', 0) + 1}). "
            f"Targeting: {', '.join(pending_platforms)}..."
        )

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target_item["last_attempt_at"] = now_str
        target_item["retry_count"] = target_item.get("retry_count", 0) + 1

        platforms_to_check = list(pending_platforms)
        for platform in platforms_to_check:
            p_lower = platform.lower()
            res = {}
            try:
                if p_lower == "instagram":
                    logger.info(f"📸 [Retry -> Instagram] Attempting Direct API first...")
                    res = api_uploader.post_instagram_direct(media_path, caption)
                    if res.get("status") != "PUBLISHED":
                        logger.info(f"📸 [Retry -> Instagram Browser Fallback] Posting {media_path.name}...")
                        res = uploader.post_instagram_reel(media_path, caption)
                elif p_lower == "facebook":
                    logger.info(f"📘 [Retry -> Facebook] Attempting Direct API first...")
                    res = api_uploader.post_facebook_direct(media_path, caption)
                    if res.get("status") != "PUBLISHED":
                        logger.info(f"📘 [Retry -> Facebook Browser Fallback] Posting {media_path.name}...")
                        res = uploader.post_facebook_story(media_path, caption)
                elif p_lower == "whatsapp":
                    logger.info(f"💬 [Retry -> WhatsApp] Attempting Direct API first...")
                    res = api_uploader.post_whatsapp_direct(media_path, caption)
                    if res.get("status") != "PUBLISHED":
                        logger.info(f"💬 [Retry -> WhatsApp Browser Fallback] Posting {media_path.name}...")
                        res = uploader.post_whatsapp_status(media_path, caption)
            except Exception as e:
                logger.warning(f"⚠️ [Retry -> {platform}] Exception during upload: {e}")
                res = {"status": "FAILED", "reason": str(e)}

            if res and res.get("status") == "PUBLISHED":
                logger.info(f"🎉 [Retry SUCCESS] Published to {platform.title()}!")
                if p_lower in pending_platforms:
                    pending_platforms.remove(p_lower)
                if p_lower not in published_platforms:
                    published_platforms.append(p_lower)
                errors.pop(p_lower, None)


            else:
                reason = res.get("reason") or res.get("message") or "Upload incomplete"
                errors[p_lower] = reason
                logger.warning(f"⚠️ [Retry FAILED] {platform.title()} could not publish: {reason}")

        target_item["pending_platforms"] = pending_platforms
        target_item["published_platforms"] = published_platforms
        target_item["errors"] = errors

        # Check if all platforms are now successfully published
        if not pending_platforms:
            target_item["status"] = "COMPLETED"
            # Move media to completed folder
            dest_completed = self.completed_dir / media_path.name
            try:
                shutil.move(str(media_path), str(dest_completed))
                target_item["media_path"] = str(dest_completed.resolve())
                cap_file = Path(target_item.get("caption_path", ""))
                if cap_file.exists():
                    shutil.move(str(cap_file), str(self.completed_dir / cap_file.name))
                    target_item["caption_path"] = str((self.completed_dir / cap_file.name).resolve())
            except Exception as e:
                logger.debug(f"Notice moving completed file: {e}")

            logger.info(f"🏆 [Social Queue] Item {item_id} fully published across all requested platforms!")

            # Record in daily limiter
            try:
                limiter.record_post(
                    source="social_queue",
                    media_names=[media_path.name],
                    platforms=published_platforms,
                    details={"queue_id": item_id}
                )
            except Exception as e:
                logger.debug(f"Limiter record notice: {e}")

            # Desktop notification for complete success
            try:
                from growth.notifier import notifier
                notifier.send(
                    "🎉 Stored Story Fully Published!",
                    f"'{media_path.name}' has now successfully posted to Instagram, Facebook & WhatsApp!",
                    urgency="normal"
                )
            except Exception:
                pass

        elif target_item["retry_count"] >= target_item.get("max_retries", 10):
            target_item["status"] = "EXHAUSTED"
            logger.info(f"ℹ️ [Social Queue] Item {item_id} ({media_path.name}) reached max retries ({target_item['max_retries']}). Marked EXHAUSTED.")

        self.save_queue(items)
        return {
            "status": target_item["status"],
            "published": published_platforms,
            "pending": pending_platforms,
            "errors": errors,
        }

    def retry_all_pending(self, force: bool = False) -> Dict[str, Any]:
        """
        Hourly pulse method:
        1. Recovers any stranded failed files from Story/failed/
        2. Inspects all pending items in the queue
        3. Retries uploading remaining pending platforms for existing queued stories
        """
        pending_items = self.get_pending_items()

        if not pending_items:
            return {
                "status": "OK",
                "retried_count": 0,
                "completed_count": 0,
                "remaining_pending": 0,
            }

        logger.info(f"📋 [Social Queue Pulse] Found {len(pending_items)} stored item(s) pending social upload.")

        uploader = BrowserUploader()
        completed_count = 0

        # Throttle to max 1 retry item per hourly pulse to prevent daemon stalls and resource exhaustion
        for item in pending_items[:1]:
            item_id = item["id"]
            media_name = Path(item["media_path"]).name
            logger.info(f"🚀 [Social Queue] Processing single throttled retry for: {media_name} ({item_id})...")
            res = self.retry_item(item_id, uploader=uploader, api_uploader=self.api_uploader)
            if res.get("status") == "COMPLETED":
                completed_count += 1
            break

        remaining = len(self.get_pending_items())
        logger.info(
            f"📊 [Social Queue Summary] Retried {min(len(pending_items), 1)} item(s). "
            f"Newly Completed: {completed_count} | Remaining Pending: {remaining}"
        )

        return {
            "status": "OK",
            "retried_count": min(len(pending_items), 1),
            "completed_count": completed_count,
            "remaining_pending": remaining,
        }

    def sweep_and_publish_all_leftover_stories(self, max_items: Optional[int] = 10) -> Dict[str, Any]:
        """
        Master Leftover Sweep for Social Media:
        Runs on laptop boot / startup to sweep all pending, queued, and stranded stories,
        uploading them to Instagram Stories, Facebook Stories, and WhatsApp Status.
        """
        # 0. Check Story/Post/ for any content needing upload
        try:
            from syndication.story_watcher import StoryWatcher
            watcher = StoryWatcher()
            post_media = watcher.get_post_media()
            if post_media:
                logger.info(f"📂 [Social Sweep] Checking {len(post_media)} media file(s) in Story/Post/...")
                watcher.upload_from_post_folder(force=False)
        except Exception as e:
            logger.debug(f"Notice during Story/Post check in sweep: {e}")

        # 1. Recover any files in Story/failed/
        self.recover_stranded_failed_files()

        # 2. Check Story/pending/ for any untracked media files
        items = self.load_queue()
        tracked_filenames = {Path(it.get("media_path", "")).name for it in items}
        for f in self.pending_dir.iterdir():
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                if f.name not in tracked_filenames:
                    cap_file = f.with_suffix(".txt")
                    caption = cap_file.read_text(encoding="utf-8").strip() if cap_file.exists() else "Royal Enfield Specialized Care #ChamundaAutomobile"
                    logger.info(f"📥 [Social Sweep] Enqueueing untracked pending file: {f.name}")
                    self.enqueue_failed(
                        media_path=f,
                        caption=caption,
                        target_platforms=["instagram", "facebook", "whatsapp"],
                        metadata={"source": "pending_sweep"},
                    )

        # 3. Re-activate stale items that still have pending platforms
        items = self.load_queue()
        needs_save = False
        for it in items:
            if it.get("status") == "ARCHIVED_STALE" and len(it.get("pending_platforms", [])) > 0:
                p = Path(it.get("media_path", ""))
                if p.exists():
                    it["status"] = "PENDING"
                    it["retry_count"] = min(it.get("retry_count", 0), 3)  # reset retry counter for fresh sweep
                    needs_save = True
        if needs_save:
            self.save_queue(items)

        pending_items = self.get_pending_items()
        if not pending_items:
            logger.info("✨ [Social Sweep] No leftover stories pending. Queue is completely clear!")
            return {"status": "OK", "processed_count": 0, "completed_count": 0, "published_count": 0}

        logger.info(f"🚀 [Social Sweep] Found {len(pending_items)} leftover story item(s) to publish across IG, FB & WA!")
        from growth.notifier import notifier
        notifier.send(
            "📱 Social Media Leftover Sweep",
            f"Found {len(pending_items)} leftover story items. Publishing to WhatsApp, Instagram & Facebook...",
            urgency="normal",
            timeout_ms=5000,
        )

        uploader = BrowserUploader()
        completed_count = 0
        processed_count = 0
        limit = max_items or len(pending_items)

        for item in pending_items[:limit]:
            item_id = item["id"]
            media_name = Path(item["media_path"]).name
            logger.info(f"📤 [Social Sweep] Publishing leftover item: {media_name} ({item['pending_platforms']})...")
            res = self.retry_item(item_id, uploader=uploader, api_uploader=self.api_uploader)
            processed_count += 1
            if res.get("status") == "COMPLETED":
                completed_count += 1

        remaining = len(self.get_pending_items())
        logger.info(f"📊 [Social Sweep Complete] Processed: {processed_count} | Completed: {completed_count} | Remaining: {remaining}")

        if completed_count > 0:
            notifier.send(
                "🎉 Leftover Stories Published!",
                f"Successfully uploaded {completed_count} stored story item(s) to Instagram, Facebook & WhatsApp!",
                urgency="normal",
                timeout_ms=7000,
            )

        return {
            "status": "OK",
            "processed_count": processed_count,
            "completed_count": completed_count,
            "published_count": completed_count,
            "remaining_pending": remaining,
        }



def get_social_queue_status() -> Dict[str, Any]:
    """Helper to query current queue statistics for Web Dashboard and CLI."""
    qm = SocialQueueManager()
    pending = qm.get_pending_items()
    items = qm.load_queue()
    return {
        "pending_count": len(pending),
        "total_tracked": len(items),
        "pending_items": [
            {
                "id": it.get("id"),
                "filename": Path(it.get("media_path", "")).name,
                "created_at": it.get("created_at"),
                "last_attempt_at": it.get("last_attempt_at"),
                "retry_count": it.get("retry_count"),
                "pending_platforms": it.get("pending_platforms", []),
                "published_platforms": it.get("published_platforms", []),
                "errors": it.get("errors", {}),
            }
            for it in pending
        ]
    }
