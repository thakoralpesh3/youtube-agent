import json
import logging
import os
import shutil
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import requests

import config
from syndication.browser_uploader import BrowserUploader
from syndication.social_auth import SocialAuth
from syndication.daily_limiter import limiter

logger = logging.getLogger(__name__)


class StoryPublisher:
    """
    Step-by-Step Multi-Platform Publisher for:
    1. Instagram (Stories & Reels)
    2. Facebook (Stories & Reels)
    3. WhatsApp (Status / Stories)

    Remembers credentials and sessions permanently - asks only ONCE.
    """

    def __init__(self):
        self.stories_dir = config.OUTPUT_DIR / "stories"
        self.ig_dir = self.stories_dir / "instagram"
        self.fb_dir = self.stories_dir / "facebook"
        self.wa_dir = self.stories_dir / "whatsapp"

        for d in [self.stories_dir, self.ig_dir, self.fb_dir, self.wa_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.auth = SocialAuth()
        self.browser_uploader = BrowserUploader()

        # Load remembered credentials from SocialAuth / env
        creds = self.auth.get_meta_credentials()
        self.meta_access_token = creds["meta_access_token"]
        self.ig_account_id = creds["ig_account_id"]
        self.fb_page_id = creds["fb_page_id"]
        self.wa_token = creds["wa_token"]
        self.wa_phone_id = creds["wa_phone_id"]
        self.wa_target_phone = creds["wa_target_phone"]

    # --------------------------------------------------------------------------
    # 1. INSTAGRAM SEQUENTIAL UPLOADER
    # --------------------------------------------------------------------------
    def upload_instagram_sequential(
        self,
        videos: Dict[str, Path],
        package_data: Dict[str, Any],
        dry_run: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Uploads videos sequentially to Instagram (English -> Hindi -> Gujarati).
        """
        results = {}
        lang_order = [("en", "English", "🇺🇸"), ("hi", "Hindi", "🇮🇳"), ("gu", "Gujarati", "🇮🇳")]

        logger.info("📸 [Step 5.2] Sequential Instagram Upload (English -> Hindi -> Gujarati)...")

        for idx, (lang_code, lang_name, flag) in enumerate(lang_order, 1):
            vid_path = videos.get(lang_code)
            if not vid_path or not vid_path.exists():
                continue

            lang_pkg = package_data.get(lang_code, {})
            title = lang_pkg.get("title", "Daily Growth #Shorts")
            description = lang_pkg.get("description", "")
            hashtags = lang_pkg.get("hashtags", "#motivation #health #DailyGrowth #reels")
            caption = f"{title}\n\n{description}\n\n{hashtags}"

            # Save local Instagram Story package
            ig_file = self.ig_dir / f"instagram_{lang_code}_{vid_path.name}"
            shutil.copyfile(vid_path, ig_file)
            (self.ig_dir / f"instagram_{lang_code}_caption.txt").write_text(caption, encoding="utf-8")

            if progress_callback:
                progress_callback(f"[{idx}/3] Uploading {flag} {lang_name} to Instagram...")

            logger.info(f"📸 [{idx}/3] Uploading {flag} {lang_name} to Instagram: '{title}'...")

            if dry_run:
                results[lang_code] = {"status": "DRY_RUN", "file": str(ig_file.resolve())}
            elif self.meta_access_token and self.ig_account_id:
                # Direct Meta Graph API Upload
                res = self._post_to_instagram_graph_api(ig_file, caption)
                results[lang_code] = res
                logger.info(f"🎉 [INSTAGRAM {lang_name.upper()}] Status: {res.get('status')}")
                if idx < len(lang_order):
                    time.sleep(4)
            else:
                # Direct Browser Automation Upload
                logger.info(f"🌐 [Instagram] Attempting automated browser upload for {flag} {lang_name}...")
                b_res = self.browser_uploader.post_instagram_reel(ig_file, caption)
                results[lang_code] = b_res
                logger.info(f"🎉 [INSTAGRAM {lang_name.upper()}] Browser Status: {b_res.get('status')}")

        return results

    def _post_to_instagram_graph_api(self, video_path: Path, caption: str) -> Dict[str, Any]:
        """Directly publishes video to Instagram Reels/Stories using Meta Graph API."""
        try:
            # 1. Initialize video container
            init_url = f"https://graph.facebook.com/v19.0/{self.ig_account_id}/media"
            params = {
                "media_type": "REELS",
                "caption": caption,
                "access_token": self.meta_access_token,
                "upload_type": "resumable",
            }
            init_res = requests.post(init_url, params=params, timeout=15)
            if init_res.status_code != 200:
                return {"status": "FAILED", "error": init_res.text}

            container_id = init_res.json().get("id")
            upload_url = init_res.json().get("uri")

            # 2. Upload video binary
            if upload_url:
                with open(video_path, "rb") as f:
                    headers = {
                        "Authorization": f"OAuth {self.meta_access_token}",
                        "offset": "0",
                        "file_size": str(video_path.stat().st_size),
                    }
                    requests.post(upload_url, data=f, headers=headers, timeout=60)

            # 3. Publish container
            time.sleep(3)
            pub_url = f"https://graph.facebook.com/v19.0/{self.ig_account_id}/media_publish"
            pub_res = requests.post(pub_url, params={"creation_id": container_id, "access_token": self.meta_access_token}, timeout=15)
            
            if pub_res.status_code == 200:
                media_id = pub_res.json().get("id")
                return {"status": "PUBLISHED", "media_id": media_id, "url": f"https://instagram.com/p/{media_id}"}
            else:
                return {"status": "CONTAINER_CREATED", "container_id": container_id, "details": pub_res.text}

        except Exception as e:
            logger.warning(f"Instagram Graph API upload notice: {e}")
            return {"status": "SAVED_LOCALLY", "reason": str(e)}

    # --------------------------------------------------------------------------
    # 2. FACEBOOK SEQUENTIAL UPLOADER
    # --------------------------------------------------------------------------
    def upload_facebook_sequential(
        self,
        videos: Dict[str, Path],
        package_data: Dict[str, Any],
        dry_run: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Uploads videos sequentially to Facebook Page / Stories (English -> Hindi -> Gujarati).
        """
        results = {}
        lang_order = [("en", "English", "🇺🇸"), ("hi", "Hindi", "🇮🇳"), ("gu", "Gujarati", "🇮🇳")]

        logger.info("📘 [Step 5.3] Sequential Facebook Upload (English -> Hindi -> Gujarati)...")

        for idx, (lang_code, lang_name, flag) in enumerate(lang_order, 1):
            vid_path = videos.get(lang_code)
            if not vid_path or not vid_path.exists():
                continue

            lang_pkg = package_data.get(lang_code, {})
            title = lang_pkg.get("title", "Daily Growth #Shorts")
            description = lang_pkg.get("description", "")
            hashtags = lang_pkg.get("hashtags", "#motivation #health #DailyGrowth #facebookreels")
            caption = f"{title}\n\n{description}\n\n{hashtags}"

            # Save local Facebook Story package
            fb_file = self.fb_dir / f"facebook_{lang_code}_{vid_path.name}"
            shutil.copyfile(vid_path, fb_file)
            (self.fb_dir / f"facebook_{lang_code}_caption.txt").write_text(caption, encoding="utf-8")

            if progress_callback:
                progress_callback(f"[{idx}/3] Uploading {flag} {lang_name} to Facebook...")

            logger.info(f"📘 [{idx}/3] Uploading {flag} {lang_name} to Facebook: '{title}'...")

            if dry_run:
                results[lang_code] = {"status": "DRY_RUN", "file": str(fb_file.resolve())}
            elif self.meta_access_token and self.fb_page_id:
                res = self._post_to_facebook_graph_api(fb_file, title, caption)
                results[lang_code] = res
                logger.info(f"🎉 [FACEBOOK {lang_name.upper()}] Status: {res.get('status')}")
                if idx < len(lang_order):
                    time.sleep(4)
            else:
                # Direct Browser Automation Upload
                logger.info(f"🌐 [Facebook] Attempting automated browser story upload for {flag} {lang_name}...")
                b_res = self.browser_uploader.post_facebook_story(fb_file, caption)
                results[lang_code] = b_res
                logger.info(f"🎉 [FACEBOOK {lang_name.upper()}] Browser Status: {b_res.get('status')}")

        return results

    def _post_to_facebook_graph_api(self, video_path: Path, title: str, description: str) -> Dict[str, Any]:
        """Directly uploads video to Facebook Page Videos/Reels using Graph API."""
        try:
            url = f"https://graph.facebook.com/v19.0/{self.fb_page_id}/videos"
            with open(video_path, "rb") as f:
                files = {"source": f}
                data = {
                    "title": title,
                    "description": description,
                    "access_token": self.meta_access_token,
                }
                res = requests.post(url, data=data, files=files, timeout=60)
                if res.status_code == 200:
                    vid_id = res.json().get("id")
                    return {"status": "PUBLISHED", "video_id": vid_id, "url": f"https://facebook.com/{vid_id}"}
                else:
                    return {"status": "FAILED", "error": res.text}
        except Exception as e:
            logger.warning(f"Facebook Graph API upload notice: {e}")
            return {"status": "SAVED_LOCALLY", "reason": str(e)}

    # --------------------------------------------------------------------------
    # 3. WHATSAPP STORY / STATUS SEQUENTIAL UPLOADER
    # --------------------------------------------------------------------------
    def upload_whatsapp_sequential(
        self,
        videos: Dict[str, Path],
        package_data: Dict[str, Any],
        dry_run: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Uploads and prepares videos for WhatsApp Status / Stories (English -> Hindi -> Gujarati).
        Generates 1-Click Status share launchers and sends via WhatsApp Cloud API if configured.
        """
        results = {}
        lang_order = [("en", "English", "🇺🇸"), ("hi", "Hindi", "🇮🇳"), ("gu", "Gujarati", "🇮🇳")]

        logger.info("💬 [Step 5.4] Sequential WhatsApp Status Preparation & Dispatch...")

        for idx, (lang_code, lang_name, flag) in enumerate(lang_order, 1):
            vid_path = videos.get(lang_code)
            if not vid_path or not vid_path.exists():
                continue

            lang_pkg = package_data.get(lang_code, {})
            title = lang_pkg.get("title", "Daily Growth #Shorts")
            hashtags = lang_pkg.get("hashtags", "#DailyGrowth #Motivation")
            caption = f"🔥 {title}\n\n{hashtags}"

            # Save local WhatsApp Status video
            wa_file = self.wa_dir / f"whatsapp_status_{lang_code}_{vid_path.name}"
            shutil.copyfile(vid_path, wa_file)
            (self.wa_dir / f"whatsapp_{lang_code}_caption.txt").write_text(caption, encoding="utf-8")

            # 1-Click WhatsApp Status Web URL
            encoded_caption = urllib.parse.quote(caption)
            share_url = f"https://api.whatsapp.com/send?text={encoded_caption}"

            # Generate interactive HTML status launcher
            html_launcher = self.wa_dir / f"post_status_{lang_code}.html"
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Post {lang_name} WhatsApp Status</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: system-ui, sans-serif; background: #0b141a; color: #e9edef; padding: 30px; text-align: center; }}
        .card {{ background: #111b21; max-width: 500px; margin: 0 auto; padding: 25px; border-radius: 12px; border: 1px solid #202c33; }}
        .btn {{ display: inline-block; background: #00a884; color: #fff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: bold; margin-top: 20px; }}
        .btn:hover {{ background: #008f6f; }}
        video {{ width: 100%; max-height: 400px; border-radius: 8px; margin: 15px 0; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>{flag} {lang_name} WhatsApp Story</h2>
        <p><strong>{title}</strong></p>
        <video controls src="{wa_file.name}"></video>
        <p><a href="{share_url}" target="_blank" class="btn">🚀 Share to WhatsApp Status</a></p>
    </div>
</body>
</html>"""
            html_launcher.write_text(html_content, encoding="utf-8")

            if progress_callback:
                progress_callback(f"[{idx}/3] Prepared {flag} {lang_name} WhatsApp Status...")

            logger.info(f"💬 [{idx}/3] WhatsApp Status {flag} {lang_name} ready: {html_launcher.name}")

            if dry_run:
                results[lang_code] = {"status": "DRY_RUN", "file": str(wa_file.resolve())}
            elif self.wa_token and self.wa_phone_id and self.wa_target_phone:
                cloud_status = "READY_FOR_STATUS"
                try:
                    cloud_url = f"https://graph.facebook.com/v19.0/{self.wa_phone_id}/messages"
                    headers = {"Authorization": f"Bearer {self.wa_token}", "Content-Type": "application/json"}
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": self.wa_target_phone,
                        "type": "text",
                        "text": {"body": f"🎬 New {lang_name} Short Ready:\n{caption}\n\nVideo: {wa_file.resolve()}"},
                    }
                    w_res = requests.post(cloud_url, headers=headers, json=payload, timeout=10)
                    if w_res.status_code == 200:
                        cloud_status = "SENT_TO_WHATSAPP"
                except Exception as e:
                    logger.debug(f"WhatsApp Cloud notice: {e}")
                results[lang_code] = {
                    "status": cloud_status,
                    "file": str(wa_file.resolve()),
                    "launcher_html": str(html_launcher.resolve()),
                    "share_url": share_url,
                    "caption": caption,
                }
            else:
                # Direct WhatsApp Web automated status upload
                logger.info(f"🌐 [WhatsApp] Attempting automated WhatsApp Status upload for {flag} {lang_name}...")
                b_res = self.browser_uploader.post_whatsapp_status(wa_file, caption)
                b_res["launcher_html"] = str(html_launcher.resolve())
                b_res["share_url"] = share_url
                results[lang_code] = b_res
                logger.info(f"🎉 [WHATSAPP {lang_name.upper()}] Browser Status: {b_res.get('status')}")

        return results

    # --------------------------------------------------------------------------
    # FULL STEP-BY-STEP ORCHESTRATOR
    # --------------------------------------------------------------------------
    def publish_all_platforms_step_by_step(
        self,
        videos: Dict[str, Path],
        package_data: Dict[str, Any],
        dry_run: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes sequential publishing across Instagram, Facebook, and WhatsApp.
        Strictly enforces 1-post-per-day rate limiting.
        """
        if not dry_run and not force and not limiter.can_post_today():
            logger.info("⏸️ [Story Publisher] Daily social post limit reached (1/1). Skipping social syndication until tomorrow.")
            return {
                "status": "SKIPPED_DAILY_LIMIT",
                "instagram": {},
                "facebook": {},
                "whatsapp": {},
            }

        ig_results = self.upload_instagram_sequential(
            videos=videos,
            package_data=package_data,
            dry_run=dry_run,
            progress_callback=progress_callback,
        )

        fb_results = self.upload_facebook_sequential(
            videos=videos,
            package_data=package_data,
            dry_run=dry_run,
            progress_callback=progress_callback,
        )

        wa_results = self.upload_whatsapp_sequential(
            videos=videos,
            package_data=package_data,
            dry_run=dry_run,
            progress_callback=progress_callback,
        )

        if not dry_run:
            try:
                limiter.record_post(
                    source="trilingual_daily_pipeline",
                    media_names=[v.name for v in videos.values() if v and v.exists()],
                    platforms=["instagram", "facebook", "whatsapp"]
                )
            except Exception as e:
                logger.debug(f"Limiter record notice: {e}")

        return {
            "instagram": ig_results,
            "facebook": fb_results,
            "whatsapp": wa_results,
        }
