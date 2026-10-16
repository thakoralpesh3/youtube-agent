"""
Autonomous Festival Social Agent for "Chamunda Automobile Parts & Services".
Specializes in Royal Enfield Only.

Orchestrates:
1. Autonomous festival detection for the current day.
2. Generating branded festive image (poster) and video (Reel/Story).
3. Auto-uploading to Instagram, Facebook, and WhatsApp Stories/Status.
4. Archiving and marking state to prevent duplicate daily runs.
"""

import datetime
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from syndication.browser_uploader import BrowserUploader
from syndication.festival_creator import ChamundaFestivalCreator
from syndication.festival_detector import FestivalDetector, FestivalInfo
from syndication.story_watcher import StoryWatcher
from syndication.daily_limiter import limiter, is_social_upload_window

logger = logging.getLogger("festival_agent")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class FestivalSocialAgent:
    """
    Autonomous Social Agent dedicated to Chamunda Automobile Parts & Services.
    Runs in background on festival days and publishes festive greetings to IG, FB & WA.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.model_name = model_name or config.GEMINI_MODEL
        self.detector = FestivalDetector(api_key=self.api_key, model_name=self.model_name)
        self.creator = ChamundaFestivalCreator(api_key=self.api_key, model_name=self.model_name)
        self.story_dir = config.BASE_DIR / "Story"
        self.story_dir.mkdir(parents=True, exist_ok=True)
        self.story_watcher = StoryWatcher(story_dir=self.story_dir)
        self.browser_uploader = BrowserUploader()

    def process_story_folder(self, dry_run: bool = False) -> List[Dict[str, Any]]:
        """
        Processes any custom content dropped by the user into the 'Story/' folder.
        Uploads each item to Instagram, Facebook, and WhatsApp Stories/Status,
        running alongside or independently of generated festival content.
        """
        pending_media = self.story_watcher.get_pending_media()
        if not pending_media:
            logger.info("📂 [Story Folder Check] No pending custom story media found in Story/.")
            return []

        logger.info("=" * 65)
        logger.info(f"📂 [Story Folder Upload] Found {len(pending_media)} custom item(s) in Story/ to publish alongside generated content!")
        logger.info("=" * 65)

        results = []
        for media_file in pending_media:
            logger.info(f"🚀 [Story Folder -> Social AI] Processing custom story: {media_file.name}")
            if not dry_run:
                try:
                    success = self.story_watcher.process_file(media_file)
                    results.append({"file": media_file.name, "status": "PUBLISHED" if success else "STORED_FOR_RETRY"})
                except Exception as e:
                    logger.warning(f"⚠️ Error uploading {media_file.name}: {e}")
                    results.append({"file": media_file.name, "status": "ERROR", "error": str(e)})
            else:
                logger.info(f"🧪 [Dry-Run] Would upload {media_file.name} to Instagram, Facebook, and WhatsApp.")
                results.append({"file": media_file.name, "status": "DRY_RUN"})

        return results

    def process_post_folder(self, dry_run: bool = False, force: bool = False) -> List[Dict[str, Any]]:
        """
        Uploads content from 'Story/Post/' to Instagram, Facebook, and WhatsApp.
        STRICT POLICY: NEVER delete or move content from the Post folder.
        """
        if dry_run:
            media = self.story_watcher.get_post_media()
            logger.info(f"🧪 [Dry-Run] Would upload {len(media)} item(s) from Story/Post/ (never deleted).")
            return [{"file": m.name, "status": "DRY_RUN"} for m in media]
        return self.story_watcher.upload_from_post_folder(force=force)

    def run_festival_campaign(
        self,
        target_festival: Optional[FestivalInfo] = None,
        dry_run: bool = False,
        lang: str = "hi",
        force_upload: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes complete festival campaign:
        1. Uploads any custom content from Story/ folder alongside generated media.
        2. Uploads content from Story/Post folder alongside generated media (never deletes Post content).
        3. Identifies festival (either passed or detected today).
        4. Generates branded Royal Enfield festive poster & video.
        5. Deploys to Instagram, Facebook, and WhatsApp.
        """
        today = datetime.date.today()
        today_str = today.strftime("%Y-%m-%d")

        # Check strict daily 1-post limit for generated content
        if not force_upload and not limiter.can_post_generated_today():
            logger.info(f"⏸️ [Festival Agent] Daily generated content already posted today ({today_str}). Skipping duplicate creation.")
            return {
                "status": "SKIPPED",
                "reason": "Daily generated post limit reached",
                "date": today_str
            }

        # 1. ALWAYS check and upload any waiting Story/ folder media ALONGSIDE generated content!
        story_uploads = self.process_story_folder(dry_run=dry_run)

        # 1b. ALWAYS upload from Story/Post folder ALONGSIDE generated content (never delete)!
        post_folder_uploads = self.process_post_folder(dry_run=dry_run, force=force_upload)

        # 2. Identify Festival
        festival = target_festival or self.detector.get_festival_for_date(today)
        if not festival or not festival.is_festival:
            logger.info(f"📅 [Festival Agent] No festival detected for today ({today_str}). Background check complete.")
            return {
                "status": "COMPLETED" if (story_uploads or post_folder_uploads) else "SKIPPED",
                "reason": "No festival today",
                "date": today_str,
                "story_folder_uploads": story_uploads,
                "post_folder_uploads": post_folder_uploads,
            }

        logger.info("=" * 65)
        logger.info(f"🎉 [FESTIVAL DETECTED] {festival.festival_name} on {festival.date_str}")
        logger.info(f"🏍️ Campaign: Chamunda Automobile Parts & Services (Royal Enfield Only)")
        logger.info("=" * 65)

        # 3. Check if already posted today
        if not force_upload and self.detector.is_campaign_posted(today_str, festival.festival_name):
            logger.info(f"⏩ [Festival Agent] Campaign for '{festival.festival_name}' was already published today. Skipping duplicate.")
            return {
                "status": "ALREADY_POSTED",
                "festival": festival.festival_name,
                "date": today_str,
                "story_folder_uploads": story_uploads,
            }

        # Check if an interrupted campaign checkpoint exists for today
        checkpoint_file = config.OUTPUT_DIR / "festival_checkpoint.json"
        poster_path = None
        video_path = None
        caption = None

        if checkpoint_file.exists():
            try:
                import json
                cp = json.loads(checkpoint_file.read_text(encoding="utf-8"))
                if cp.get("date") == today_str and cp.get("festival") == festival.festival_name:
                    p_candidate = Path(cp.get("poster_path", ""))
                    v_candidate = Path(cp.get("video_path", ""))
                    if p_candidate.exists() and v_candidate.exists():
                        logger.info(f"⚡ Checkpoint found: Reusing existing festive poster and video for {festival.festival_name}!")
                        poster_path = p_candidate
                        video_path = v_candidate
                        caption = cp.get("caption")
            except Exception:
                pass

        if not poster_path or not video_path:
            # 3. Generate Festive Poster (Image)
            logger.info(f"📸 Generating branded festive poster for {festival.festival_name}...")
            poster_path = self.creator.generate_poster(festival, lang=lang)

            # 4. Generate Festive Video (Reel/Story)
            logger.info(f"🎥 Generating branded festive video for {festival.festival_name}...")
            video_path = self.creator.generate_video(festival, poster_path, lang=lang)

            # 5. Generate Multi-Platform Caption
            caption = self.creator.generate_caption(festival, lang=lang)

            # Checkpoint progress to disk for fault-tolerant recovery
            try:
                import json
                checkpoint_file.write_text(json.dumps({
                    "date": today_str,
                    "festival": festival.festival_name,
                    "poster_path": str(poster_path.resolve()),
                    "video_path": str(video_path.resolve()),
                    "caption": caption,
                }, indent=2), encoding="utf-8")
            except Exception:
                pass

        # Save caption files
        poster_caption_file = poster_path.with_suffix(".txt")
        video_caption_file = video_path.with_suffix(".txt")
        poster_caption_file.write_text(caption, encoding="utf-8")
        video_caption_file.write_text(caption, encoding="utf-8")

        upload_results = {}

        if not dry_run:
            # 7. Publish to Social Media (Instagram, Facebook, WhatsApp)
            logger.info("🚀 [Auto-Publish] Initiating multi-platform story publishing...")

            vid_ok = False
            post_ok = False

            # Upload video to Story / Status (force=True to allow both video & greeting card in festival package)
            try:
                if video_path.exists():
                    vid_ok = self.story_watcher.process_file(video_path, force=True)
                    upload_results["video"] = "PUBLISHED" if vid_ok else "STORED_FOR_RETRY"
            except Exception as e:
                logger.warning(f"Video upload notice: {e}")
                upload_results["video"] = f"NOTICE: {e}"

            # Upload poster image to Story / Feed (force=True to allow both video & greeting card in festival package)
            try:
                if poster_path.exists():
                    post_ok = self.story_watcher.process_file(poster_path, force=True)
                    upload_results["poster"] = "PUBLISHED" if post_ok else "STORED_FOR_RETRY"
            except Exception as e:
                logger.warning(f"Poster upload notice: {e}")
                upload_results["poster"] = f"NOTICE: {e}"

            if vid_ok or post_ok:
                # 8. Mark Campaign as Posted in History only if at least one succeeded
                self.detector.mark_campaign_posted(
                    date_str=today_str,
                    festival_name=festival.festival_name,
                    media_paths=[str(poster_path), str(video_path)],
                )

                # Record in daily limiter
                try:
                    limiter.record_post(
                        source="festival_agent",
                        media_names=[poster_path.name, video_path.name],
                        platforms=["instagram", "facebook", "whatsapp"],
                        details={"festival": festival.festival_name}
                    )
                except Exception as e:
                    logger.debug(f"Limiter record notice: {e}")

                # 9. Send Linux Desktop Notification
                try:
                    from growth.notifier import notifier
                    notifier.notify_social_success(
                        festival.festival_name,
                        ["whatsapp", "instagram", "facebook"]
                    )
                except Exception:
                    pass
            else:
                logger.warning(f"⚠️ Neither video nor poster could be published for {festival.festival_name}.")
                try:
                    from growth.notifier import notifier
                    notifier.notify_social_queued(
                        festival.festival_name,
                        ["whatsapp", "instagram", "facebook"],
                        "Saved to retry queue"
                    )
                except Exception:
                    pass

        else:
            logger.info("🧪 [Dry-Run] Media generated successfully. Skipping live upload step.")
            upload_results = {"mode": "dry_run", "status": "GENERATED"}

        logger.info("=" * 65)
        logger.info(f"✨ [CAMPAIGN COMPLETE] {festival.festival_name} processed for Chamunda Automobile!")
        logger.info("=" * 65)

        return {
            "status": "COMPLETED",
            "festival": festival.festival_name,
            "poster": str(poster_path),
            "video": str(video_path),
            "uploads": upload_results,
            "caption": caption,
        }

    def run_daily_social_cycle(self, force: bool = False) -> Dict[str, Any]:
        """
        Executes the single daily social publishing cycle:
        1. Checks strict 1-post-per-day rate limiter.
        2. On festival days: generates and posts Chamunda Automobile Royal Enfield greeting card & video.
        3. On non-festival days: posts business content from Story/ or Story/Post/ (never deleted).
        4. Retries any stored pending queue items if available.
        Guarantees strictly 1 social post per calendar day.
        """
        today = datetime.date.today()
        today_str = today.strftime("%Y-%m-%d")

        # 0. Sweep all leftover pending stories across Instagram, Facebook, WhatsApp
        try:
            from syndication.social_queue import SocialQueueManager
            qm = SocialQueueManager()
            leftover_res = qm.sweep_and_publish_all_leftover_stories(max_items=10)
            if leftover_res.get("published_count", 0) > 0:
                logger.info(f"✨ [Daily Social Agent] Leftover sweep published {leftover_res['published_count']} story items.")
        except Exception as e:
            logger.debug(f"Leftover sweep notice: {e}")

    def _get_daily_re_showcase_info(self, today: datetime.date) -> FestivalInfo:
        """Produces daily Royal Enfield showcase & maintenance theme for non-festival days."""
        day_name = today.strftime("%A")
        date_str = today.strftime("%Y-%m-%d")
        daily_themes = {
            "Monday": ("Mahadev Blessings & Machine Power", "Lord Shiva blessing the Royal Enfield machine, unshakeable strength on every ride"),
            "Tuesday": ("Hanuman Ji Strength & Safety Shield", "Bajrangbali blessing riders with courage, road discipline, and zero breakdown confidence"),
            "Wednesday": ("Genuine Spare Parts & Performance Care", "Chamunda Automobile genuine Royal Enfield spare parts, authentic filters, and factory precision"),
            "Thursday": ("Guru & Highway Touring Wisdom", "Long-haul highway cruising mastery, engine temperature care, and open-road discipline"),
            "Friday": ("Classic 350 & Bullet 350 Heritage Glory", "Timeless heavy flywheel thump, gold hand-painted pinstripes, and authentic Royal Enfield pride"),
            "Saturday": ("Weekend Expedition & Mountain Machine Care", "Himalayan 450 expedition spirit, suspension tuning, and high-altitude touring readiness"),
            "Sunday": ("Weekend Rider Brotherhood & Community Pride", "Riding brotherhood, group tour safety, and complete Sunday machine inspection"),
        }
        theme_title, theme_desc = daily_themes.get(day_name, ("Royal Enfield Daily Ride & Genuine Care", "Daily Royal Enfield maintenance and pure riding passion"))
        return FestivalInfo(
            is_festival=True,
            festival_name=f"Chamunda Royal Enfield {day_name} Special",
            date_str=date_str,
            significance=theme_desc,
            motorcycle_theme=theme_title,
            greeting_headline=f"Royal Enfield {day_name} Special - Chamunda Automobile",
            blessing_message_hi="चामुंडा ऑटोमोबाइल कलोल - रॉयल एनफील्ड के साथ आपकी हर यात्रा सुरक्षित, सशक्त और गौरवमयी रहे।",
            blessing_message_gu="ચામુંડા ઓટોમોબાઇલ કલોલ - રોયલ એન્ફિલ્ડ સાથે તમારી દરેક સવારી મંગલમય, સુરક્ષિત અને અડીખમ રહે.",
            blessing_message_en="Ride pure, ride proud with Chamunda Automobile Parts & Services (Royal Enfield Only). Safe journeys always!",
        )

    def run_daily_social_cycle(self, force: bool = False) -> Dict[str, Any]:
        """
        Executes the single daily social publishing cycle:
        1. Checks strict 1-post-per-day rate limiter and sharp 11:30 PM window.
        2. On festival days: generates and posts Chamunda Automobile Royal Enfield greeting card & video.
        3. On non-festival days: generates daily Royal Enfield showcase & maintenance video/poster.
        4. Uploads all media from Story/Post/ (never deleted).
        5. Retries any stored pending queue items if available.
        """
        today = datetime.date.today()
        today_str = today.strftime("%Y-%m-%d")

        # 0. Sweep all leftover pending stories across Instagram, Facebook, WhatsApp
        try:
            from syndication.social_queue import SocialQueueManager
            qm = SocialQueueManager()
            leftover_res = qm.sweep_and_publish_all_leftover_stories(max_items=10)
            if leftover_res.get("published_count", 0) > 0:
                logger.info(f"✨ [Daily Social Agent] Leftover sweep published {leftover_res['published_count']} story items.")
        except Exception as e:
            logger.debug(f"Leftover sweep notice: {e}")

        if not force:
            if not is_social_upload_window():
                logger.info(
                    f"⏳ [Daily Social Agent] Social story uploads are strictly scheduled for sharp 11:30 PM (23:30). "
                    f"Standing by for {today_str}."
                )
                return {"status": "SCHEDULED", "reason": "Awaiting sharp 11:30 PM upload window", "date": today_str}
            if not limiter.can_post_generated_today():
                logger.info(f"⏸️ [Daily Social Agent] Daily generated content already published today ({today_str}). Skipping duplicate creation.")
                return {"status": "SKIPPED", "reason": "Daily generated limit reached", "date": today_str}

        logger.info("=" * 65)
        logger.info(f"📱 [Daily Social Agent] Running Daily Social Publishing Workflow for {today_str}...")
        logger.info("=" * 65)

        # 1. Festival Check (Highest priority on festival days)
        festival = self.detector.get_festival_for_date(today)
        if festival and festival.is_festival:
            if force or not self.detector.is_campaign_posted(today_str, festival.festival_name):
                logger.info(f"🌟 [Daily Social Agent] Today is {festival.festival_name}! Launching Chamunda Automobile festival campaign...")
                return self.run_festival_campaign(target_festival=festival, dry_run=False, force_upload=force)
            else:
                logger.info(f"⏩ [Daily Social Agent] Festival campaign for '{festival.festival_name}' already posted today.")
        else:
            # Daily Royal Enfield Showcase / Care Campaign on non-festival days
            daily_theme = self._get_daily_re_showcase_info(today)
            if force or not self.detector.is_campaign_posted(today_str, daily_theme.festival_name):
                logger.info(f"🌟 [Daily Social Agent] Launching Chamunda Royal Enfield daily showcase ({daily_theme.festival_name})...")
                return self.run_festival_campaign(target_festival=daily_theme, dry_run=False, force_upload=force)
            else:
                logger.info(f"⏩ [Daily Social Agent] Daily showcase for '{daily_theme.festival_name}' already posted today.")

        # 2. Check Custom Drops in Story/ folder
        if self.story_watcher.get_pending_media():
            logger.info("📂 [Daily Social Agent] Processing custom media dropped in Story/...")
            res = self.process_story_folder(dry_run=False)
            if res:
                return {"status": "COMPLETED", "source": "story_folder", "results": res}

        # 3. Check Business Post in Story/Post/ folder (Chamunda Automobile Royal Enfield)
        if self.story_watcher.get_post_media():
            logger.info("📂 [Daily Social Agent] Publishing Royal Enfield business post from Story/Post/...")
            res = self.process_post_folder(dry_run=False, force=force)
            if res:
                return {"status": "COMPLETED", "source": "post_folder", "results": res}

        # 4. Check Stored Pending Queue for Retries
        try:
            from syndication.social_queue import SocialQueueManager
            qm = SocialQueueManager()
            qres = qm.retry_all_pending()
            if qres.get("completed_count", 0) > 0:
                return {"status": "COMPLETED", "source": "queue_retry", "results": qres}
        except Exception as e:
            logger.debug(f"Queue retry notice: {e}")

        logger.info("✨ [Daily Social Agent] Social workflow check complete.")
        return {"status": "IDLE", "reason": "No pending content or festival today", "date": today_str}

    def check_and_run_background(self, force: bool = False) -> None:
        """
        Non-blocking invocation for scheduler / background pulse.
        Executes daily social publishing in a daemon thread.
        Strictly respects 1-post-per-day rate limiting.
        """
        if not force and not limiter.can_post_today():
            logger.debug("⏸️ [Festival Background Agent] Daily social post limit reached (1/1). Skipping background pulse.")
            return

        def _task():
            try:
                self.run_daily_social_cycle(force=force)
            except Exception as e:
                logger.error(f"Error in background social execution: {e}", exc_info=True)

        thread = threading.Thread(target=_task, daemon=True, name="DailySocialBackgroundAgent")
        thread.start()


# Global helper
_festival_agent = FestivalSocialAgent()


def trigger_festival_check(force: bool = False) -> None:
    _festival_agent.check_and_run_background(force=force)


def run_daily_social_agent(force: bool = False) -> Dict[str, Any]:
    return _festival_agent.run_daily_social_cycle(force=force)

