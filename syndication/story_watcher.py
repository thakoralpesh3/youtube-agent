import datetime
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

import config
from syndication.browser_uploader import BrowserUploader
from syndication.story_publisher import StoryPublisher
from syndication.social_queue import SocialQueueManager
from syndication.api_uploader import DirectSocialApiUploader
from syndication.daily_limiter import limiter, is_social_upload_window
from generator.script_generator import validate_family_safe
from generator.image_generator import ImageSafetyScanner

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".jpg", ".jpeg", ".png", ".webp"
}

_WATCHER_LOCK = threading.Lock()
_ACTIVE_FILES = set()


class StoryWatcher:
    """
    Monitors the 'Story' folder for new images or videos.
    Automatically publishes them to Instagram, Facebook, and WhatsApp Stories only.
    Prioritizes fast, headless Direct API uploads with browser automation fallback.
    """

    def __init__(self, story_dir: Optional[Path] = None):
        self.story_dir = story_dir or (config.BASE_DIR / "Story")
        self.completed_dir = self.story_dir / "completed"
        self.pending_dir = self.story_dir / "pending"
        self.failed_dir = self.story_dir / "failed"
        self.post_dir = (self.story_dir / "Post") if (self.story_dir / "Post").exists() else (self.story_dir / "post")

        for d in [self.story_dir, self.completed_dir, self.pending_dir, self.failed_dir, self.post_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.publisher = StoryPublisher()
        self.browser_uploader = BrowserUploader()
        self.queue_manager = SocialQueueManager()
        self.api_uploader = DirectSocialApiUploader()

    def get_pending_media(self) -> List[Path]:
        """Finds all media files in Story/ that are ready for upload."""
        pending = []
        for file in self.story_dir.iterdir():
            if file.is_file() and file.suffix.lower() in SUPPORTED_EXTENSIONS:
                if file.name.startswith(".") or file.name.startswith("test"):
                    continue
                # Skip 0-byte files
                try:
                    s1 = file.stat().st_size
                    if s1 == 0:
                        continue
                    # Make sure file has finished copying (size stable over 1s)
                    time.sleep(1.0)
                    s2 = file.stat().st_size
                    if s1 == s2 and s1 > 0:
                        pending.append(file)
                except Exception:
                    continue
        return pending

    def process_file(self, media_path: Path, custom_caption: Optional[str] = None, preserve_original: bool = False, force: bool = False) -> bool:
        """
        Uploads a single image or video to Instagram Story, Facebook Story, and WhatsApp Status only.
        If preserve_original=True (or file is in Story/Post/), the file is NEVER deleted or moved.
        Enforces strict 1-post-per-day limit across social platforms.
        """
        if not media_path.exists():
            return False

        if not force:
            if not is_social_upload_window():
                logger.info(
                    f"⏳ [Social AI] Daily story uploads strictly scheduled for sharp 11:30 PM (23:30). "
                    f"'{media_path.name}' remains safely staged for 11:30 PM."
                )
                return False
            if not limiter.can_post_today():
                logger.info(f"⏸️ [Social AI] Daily post limit reached (1 post/day). '{media_path.name}' will remain ready for tomorrow.")
                return False

        with _WATCHER_LOCK:
            if media_path.name in _ACTIVE_FILES:
                logger.debug(f"⏳ [Story Watcher] '{media_path.name}' is already being processed. Skipping duplicate trigger.")
                return False
            _ACTIVE_FILES.add(media_path.name)

        try:
            logger.info(f"🚀 [Story Folder] Detected new media: {media_path.name}")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            caption_file = media_path.with_suffix(".txt")
            if custom_caption:
                caption = custom_caption
            elif caption_file.exists():
                caption = caption_file.read_text(encoding="utf-8").strip()
            else:
                lower_name = media_path.name.lower()
                if any(k in lower_name for k in ["banking", "csc", "hdfc", "service", "digital"]):
                    caption = (
                        "🏛️ Digital India & Banking Services\n\n"
                        "સરળતાથી બેંકિંગ સેવાઓ અને સરકારી યોજનાઓનો લાભ મેળવો.\n"
                        "★ એકાઉન્ટ સેવાઓ • સ્ટેટમેન્ટ • લોન સહાય • ડિજિટલ સેવાઓ\n\n"
                        "#DigitalIndia #CSC #BankingServices #CitizenServices #Story"
                    )
                elif any(k in lower_name for k in ["chamunda", "enfield", "royal", "bullet", "bike", "gemini"]):
                    caption = (
                        "🏍️ Chamunda Automobile Parts & Services | Royal Enfield Specialist\n\n"
                        "★ Genuine Spare Parts, Accessories & Expert Service\n"
                        "★ Bullet 350 • Classic 350 • Hunter • Meteor • Himalayan • 650 Twins\n\n"
                        "📍 4, Sanidhya Arcade, Opp. Sindbad Hotel, Kalol - 382721\n"
                        "📞 Contact: Hitesh (8490001582) | Arjun (9054810022) | Alpesh (7874719139)\n\n"
                        "#ChamundaAutomobile #RoyalEnfield #Bullet350 #Classic350 #Kalol #GujaratBikers #PureMotorcycling #Story"
                    )
                else:
                    clean_title = media_path.stem.replace("_", " ").replace("-", " ").title()
                    caption = (
                        f"🔥 {clean_title}\n\n"
                        f"🏍️ Chamunda Automobile Parts & Services | Royal Enfield Specialist\n"
                        f"📍 4, Sanidhya Arcade, Opp. Sindbad Hotel, Kalol - 382721\n"
                        f"📞 Hitesh: 8490001582 | Alpesh: 7874719139\n\n"
                        f"#ChamundaAutomobile #RoyalEnfield #Story"
                    )

            # Enforce strict all-ages family-friendly caption safety
            try:
                validate_family_safe(caption)
            except ValueError as ve:
                logger.warning(f"⚠️ Inappropriate term detected in caption ({ve}). Sanitizing to clean default.")
                caption = (
                    "🏍️ Chamunda Automobile Parts & Services | Royal Enfield Specialist\n\n"
                    "★ Genuine Spare Parts, Accessories & Expert Service\n"
                    "★ Bullet 350 • Classic 350 • Hunter • Meteor • Himalayan • 650 Twins\n\n"
                    "📍 4, Sanidhya Arcade, Opp. Sindbad Hotel, Kalol - 382721\n"
                    "📞 Contact: Hitesh (8490001582) | Alpesh (7874719139)\n\n"
                    "#ChamundaAutomobile #RoyalEnfield #Bullet350 #Classic350 #Kalol #PureMotorcycling"
                )

            logger.info(f"📝 Caption: {caption[:60]}...")

            # Pre-flight AI Multimodal Vision Audit for image files
            if media_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                if not ImageSafetyScanner.audit_image(media_path):
                    logger.warning(
                        f"🚨 [Story Watcher] Media file '{media_path.name}' failed multimodal safety audit "
                        "(detected possible nude/sexy/18+ content). Upload rejected."
                    )
                    return False

            # -------------------------------------------------------------
            # 1. Instagram Story / Reel Upload (Direct API -> Browser Fallback)
            # -------------------------------------------------------------
            if not media_path.exists():
                return False
            logger.info(f"📸 [Story Auto-Upload] Posting to Instagram: {media_path.name}...")
            res_ig = self.api_uploader.post_instagram_direct(media_path, caption)
            if res_ig.get("status") != "PUBLISHED":
                try:
                    res_ig = self.browser_uploader.post_instagram_reel(media_path, caption)
                    logger.info(f"✅ Instagram Browser Status: {res_ig.get('status')}")
                except Exception as e:
                    logger.warning(f"⚠️ Instagram notice: {e}")
                    res_ig = {"status": "FAILED", "reason": str(e)}

            # -------------------------------------------------------------
            # 2. Facebook Story Upload (Direct Graph API -> Browser Fallback)
            # -------------------------------------------------------------
            if not media_path.exists():
                return False
            logger.info(f"📘 [Story Auto-Upload] Posting to Facebook Story: {media_path.name}...")
            res_fb = self.api_uploader.post_facebook_direct(media_path, caption)
            if res_fb.get("status") != "PUBLISHED":
                try:
                    res_fb = self.browser_uploader.post_facebook_story(media_path, caption)
                    logger.info(f"✅ Facebook Browser Status: {res_fb.get('status')}")
                except Exception as e:
                    logger.warning(f"⚠️ Facebook Story notice: {e}")
                    res_fb = {"status": "FAILED", "reason": str(e)}

            # -------------------------------------------------------------
            # 3. WhatsApp Status Upload (Direct Cloud API -> Browser Fallback)
            # -------------------------------------------------------------
            if not media_path.exists():
                return False
            logger.info(f"💬 [Story Auto-Upload] Posting to WhatsApp Status: {media_path.name}...")
            res_wa = self.api_uploader.post_whatsapp_direct(media_path, caption)
            if res_wa.get("status") != "PUBLISHED":
                try:
                    res_wa = self.browser_uploader.post_whatsapp_status(media_path, caption)
                    logger.info(f"✅ WhatsApp Browser Status: {res_wa.get('status')}")
                except Exception as e:
                    logger.warning(f"⚠️ WhatsApp Status notice: {e}")
                    res_wa = {"status": "FAILED", "reason": str(e)}

            # Determine which platforms genuinely published
            published_platforms = []
            failed_platforms = {}
            for plat_name, res in [("Instagram", res_ig), ("Facebook", res_fb), ("WhatsApp", res_wa)]:
                if res and res.get("status") == "PUBLISHED":
                    published_platforms.append(plat_name)
                else:
                    failed_platforms[plat_name] = res.get("reason") or res.get("message", "Upload incomplete")

            is_post_folder = preserve_original or (media_path.parent == self.post_dir) or (media_path.parent.name.lower() == "post")

            # CASE 1: All 3 platforms succeeded!
            if len(published_platforms) == 3:
                dest_file = self.completed_dir / f"{timestamp}_{media_path.name}"
                if media_path.exists():
                    if is_post_folder:
                        try:
                            shutil.copy2(str(media_path), str(dest_file))
                        except Exception:
                            pass
                        logger.info(f"💾 [Post Folder] Preserved original '{media_path.name}' in {media_path.parent} (never deleted)!")
                    else:
                        shutil.move(str(media_path), str(dest_file))

                if caption_file.exists():
                    if is_post_folder:
                        try:
                            shutil.copy2(str(caption_file), str(self.completed_dir / f"{timestamp}_{caption_file.name}"))
                        except Exception:
                            pass
                    else:
                        shutil.move(str(caption_file), str(self.completed_dir / f"{timestamp}_{caption_file.name}"))

                published_str = ", ".join(published_platforms)
                logger.info(f"🎉 [Story Folder] Successfully published {media_path.name} to all platforms: {published_str}!")
                try:
                    limiter.record_post(
                        source="story_watcher",
                        media_names=[media_path.name],
                        platforms=published_platforms,
                        details={"is_post_folder": is_post_folder}
                    )
                except Exception as e:
                    logger.debug(f"Limiter record notice: {e}")
                try:
                    subprocess.run([
                        "notify-send",
                        "-a", "Story Auto-Uploader",
                        "-u", "normal",
                        "📸 Published on All Platforms!",
                        f"'{media_path.name}' published to {published_str}!"
                    ], check=False)
                except Exception:
                    pass
                return True

            # CASE 2: Partial or Total Failure -> Store in Pending Queue for Hourly Auto-Retry!
            else:
                target_plats = ["instagram", "facebook", "whatsapp"]
                pub_lower = [p.lower() for p in published_platforms]
                fail_lower = {k.lower(): v for k, v in failed_platforms.items()}

                queue_item = self.queue_manager.enqueue_failed(
                    media_path=media_path,
                    caption=caption,
                    target_platforms=target_plats,
                    published_platforms=pub_lower,
                    failed_platforms=fail_lower,
                    metadata={"source": "story_watcher", "is_post_folder": is_post_folder}
                )
                if caption_file.exists() and not is_post_folder:
                    try:
                        caption_file.unlink()
                    except Exception:
                        pass

                pending_str = ", ".join([p.title() for p in queue_item.get("pending_platforms", [])])
                if published_platforms:
                    logger.info(
                        f"⚠️ [Story Folder] Partial upload for {media_path.name}. "
                        f"Published: {', '.join(published_platforms)} | Stored for hourly retry: {pending_str}"
                    )
                else:
                    logger.warning(
                        f"📦 [Story Folder] Initial upload failed for {media_path.name}. "
                        f"Stored in pending queue. Hourly scheduler will retry on: {pending_str}"
                    )

                return bool(published_platforms)
        finally:
            with _WATCHER_LOCK:
                _ACTIVE_FILES.discard(media_path.name)

    def get_post_media(self) -> List[Path]:
        """Finds all media files in Story/Post/ (never deletes them)."""
        post_dir = (self.story_dir / "Post") if (self.story_dir / "Post").exists() else (self.story_dir / "post")
        if not post_dir.exists() or not post_dir.is_dir():
            return []

        media_files = []
        for file in sorted(post_dir.iterdir()):
            if file.is_file() and file.suffix.lower() in SUPPORTED_EXTENSIONS:
                if file.name.startswith(".") or file.name.startswith("test"):
                    continue
                try:
                    if file.stat().st_size > 0:
                        media_files.append(file)
                except Exception:
                    continue
        return media_files

    def upload_from_post_folder(self, force: bool = False) -> List[Dict[str, Any]]:
        """
        Uploads all content from Story/Post/ to Instagram, Facebook, and WhatsApp.
        STRICT POLICY: NEVER delete or move content from the Post folder.
        Enforces 1-post-per-day rule: only uploads once per calendar day at sharp 11:30 PM.
        """
        if not force:
            if not is_social_upload_window():
                logger.debug("⏳ [Post Folder] Scheduled for sharp 11:30 PM (23:30). Story/Post/ content safely staged.")
                return []
            if not limiter.can_post_post_folder_today():
                logger.info("⏸️ [Post Folder] Daily social post for Story/Post/ already completed today. Skipping.")
                return []

        media_files = self.get_post_media()
        if not media_files:
            logger.info("📂 [Post Folder Check] No media found in Story/Post/.")
            return []

        logger.info("=" * 65)
        logger.info(f"📂 [Post Folder Upload] Found {len(media_files)} item(s) in Story/Post/ to publish!")
        logger.info("🔒 Policy: NEVER DELETE CONTENT FROM POST FOLDER.")
        logger.info("=" * 65)

        results = []
        uploaded_names = []
        for media_file in media_files:
            logger.info(f"🚀 [Post Folder -> Social AI] Uploading from Story/Post/: {media_file.name}")
            try:
                success = self.process_file(media_file, preserve_original=True, force=True)
                if success:
                    uploaded_names.append(media_file.name)
                results.append({
                    "file": media_file.name,
                    "status": "PUBLISHED" if success else "FAILED",
                    "preserved_in_post_folder": True
                })
            except Exception as e:
                logger.warning(f"⚠️ Error uploading {media_file.name} from Post folder: {e}")
                results.append({
                    "file": media_file.name,
                    "status": "ERROR",
                    "error": str(e),
                    "preserved_in_post_folder": True
                })

        if uploaded_names:
            try:
                limiter.mark_post_folder_posted(
                    media_names=uploaded_names,
                    platforms=["Instagram", "Facebook", "WhatsApp"],
                    details={"is_post_folder": True, "count": len(uploaded_names)}
                )
            except Exception as e:
                logger.debug(f"Limiter notice for post folder: {e}")

        return results

    def run_once(self, force: bool = False) -> int:
        """Processes all currently available media in Story/ and Story/Post/ at 11:30 PM."""
        if not force and not is_social_upload_window():
            logger.debug("⏸️ [Story Watcher] Scheduled for sharp 11:30 PM (23:30). Standing by.")
            return 0

        if not force and not limiter.can_post_today():
            logger.debug("⏸️ [Story Watcher] Daily social post limit reached. Skipping run_once().")
            return 0

        files = self.get_pending_media()
        count = 0
        for f in files:
            if not force and not limiter.can_post_today():
                break
            if self.process_file(f, force=force):
                count += 1

        # Unconditionally check and upload content from Story/Post/ (never deletes post content)
        try:
            post_results = self.upload_from_post_folder(force=force)
            if post_results:
                count += len([r for r in post_results if r.get("status") == "PUBLISHED"])
        except Exception as e:
            logger.warning(f"⚠️ Notice during Story/Post folder upload in run_once: {e}")

        return count

    def watch_forever(self, interval_seconds: int = 10):
        """Continuously watches the Story folder in the background (uploads at 11:30 PM)."""
        logger.info(f"👀 [Story Watcher] Monitoring folder '{self.story_dir}' for images & videos (Publish time: 11:30 PM)...")
        while True:
            try:
                self.run_once()
            except Exception as e:
                logger.debug(f"Story watcher cycle error: {e}")
            sleep_time = 60 if not limiter.can_post_today() else interval_seconds
            time.sleep(sleep_time)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    watcher = StoryWatcher()
    watcher.watch_forever()
