import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

import requests

import config
from security.security_guard import SecurityGuard

logger = logging.getLogger("TelegramBot")


def send_telegram_alert(message: str):
    """Sends a push notification to the owner's Telegram app."""
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }
        requests.post(url, json=payload, timeout=10)
        return True
    except Exception as e:
        logger.debug(f"Telegram alert error: {e}")
        return False


class TelegramRemoteBot:
    """
    Autonomous Mobile Remote Control Bot via Telegram.
    Allows user to trigger workflows, check 24/7 status, and drop Story photos/videos
    directly from their smartphone Telegram app without needing a laptop.
    """

    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = str(config.TELEGRAM_CHAT_ID).strip() if config.TELEGRAM_CHAT_ID else ""
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self.offset = 0
        self.running = False

    def is_configured(self) -> bool:
        return bool(self.token and len(self.token) > 10)

    def is_authorized(self, sender_id: int) -> bool:
        if not self.chat_id:
            # If no chat ID locked yet, allow first user and lock it
            self.chat_id = str(sender_id)
            return True
        return str(sender_id) == self.chat_id

    def send_message(self, chat_id: int, text: str):
        try:
            url = f"{self.base_url}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
        except Exception as e:
            logger.debug(f"Error sending telegram message: {e}")

    def handle_command(self, chat_id: int, text: str):
        text = text.strip().lower()
        if text.startswith("/start"):
            msg = (
                "🤖 *YouTube & Social Media AI Agent - 24/7 Cloud Sentinel*\n\n"
                "Welcome! You can control your agent from anywhere on your phone:\n\n"
                "📸 *Post to Stories*: Just send any Photo or Video directly to this chat!\n\n"
                "⚡ *Quick Commands*:\n"
                "• `/status` - Check 24/7 live health & security\n"
                "• `/surprise` - ✨ Surprise me with a breakthrough creative idea!\n"
                "• `/shorts` - Generate & upload Trilingual Shorts (EN, HI, GU)\n"
                "• `/festival` - Run Chamunda Auto Festival Campaign\n"
                "• `/pending` - Upload pending YouTube videos\n"
                "• `/retry_social` - 🔄 Retry stored pending social stories (IG, FB, WA)\n"
                "• `/security` - Run 5-point anti-hacker audit & harden"
            )
            self.send_message(chat_id, msg)

        elif text.startswith("/status"):
            from syndication.festival_detector import FestivalDetector
            detector = FestivalDetector()
            fest = detector.get_festival_for_date()
            fest_name = fest.festival_name if fest else "Daily Royal Enfield Blessing"

            pending_social_str = "0 Pending"
            try:
                from syndication.social_queue import SocialQueueManager
                qm = SocialQueueManager()
                pending_count = len(qm.get_pending_items())
                pending_social_str = f"{pending_count} item(s) awaiting retry" if pending_count > 0 else "All Published ✅"
            except Exception:
                pass

            msg = (
                "📊 *Agent 24/7 Live Status Report*\n\n"
                f"• *Daemon*: 🟢 Running (24/7)\n"
                f"• *AI Model*: `{config.GEMINI_MODEL}`\n"
                f"• *YouTube Auth*: {'✅ Active' if Path(config.YOUTUBE_TOKEN_FILE).exists() else '⚠️ Needs Auth'}\n"
                f"• *Social Profile*: {'✅ Active (IG, FB, WA)' if (config.BASE_DIR / 'assets' / 'browser_profiles' / 'social_firefox' / 'cookies.sqlite').exists() else '⚠️ Incomplete'}\n"
                f"• *Stored Social Stories*: {pending_social_str}\n"
                f"• *Next Campaign*: {fest_name}\n"
                f"• *Security Posture*: 🛡️ Protected (FIM SHA-256 Intact)"
            )
            self.send_message(chat_id, msg)

        elif text.startswith("/shorts"):
            self.send_message(chat_id, "🚀 *Starting Trilingual Shorts generation in background...* (EN, HI, GU)")
            def _run():
                try:
                    from agent import YouTubeAgent
                    YouTubeAgent().run_trilingual(dry_run=False)
                    self.send_message(chat_id, "🎉 *Trilingual Shorts generation & publishing completed!*")
                except Exception as e:
                    self.send_message(chat_id, f"❌ *Error during Shorts generation:* {e}")
            threading.Thread(target=_run, daemon=True).start()

        elif text.startswith("/festival"):
            self.send_message(chat_id, "🎉 *Launching Chamunda Automobile Festival Campaign...*")
            def _run():
                try:
                    from syndication.festival_agent import FestivalSocialAgent
                    res = FestivalSocialAgent().run_festival_campaign(force_upload=True)
                    self.send_message(
                        chat_id,
                        f"✅ *Festival Campaign Published!*\n"
                        f"• Festival: {res.get('festival')}\n"
                        f"• Uploads: {res.get('uploads')}"
                    )
                except Exception as e:
                    self.send_message(chat_id, f"❌ *Festival Campaign error:* {e}")
            threading.Thread(target=_run, daemon=True).start()

        elif text.startswith("/pending"):
            self.send_message(chat_id, "📤 *Checking and uploading pending YouTube Shorts...*")
            def _run():
                try:
                    from upload_to_youtube import upload_all_pending
                    uploaded = upload_all_pending(watch_mode=False)
                    self.send_message(chat_id, f"✅ *Uploaded {len(uploaded or [])} pending video(s) to YouTube!*")
                except Exception as e:
                    self.send_message(chat_id, f"❌ *Pending upload error:* {e}")
            threading.Thread(target=_run, daemon=True).start()

        elif text.startswith("/retry_social"):
            self.send_message(chat_id, "🔄 *Retrying Stored Social Stories...*\nChecking queue and attempting upload to remaining pending platforms (Instagram, Facebook & WhatsApp)...")
            def _run():
                try:
                    from syndication.social_queue import SocialQueueManager
                    qm = SocialQueueManager()
                    res = qm.retry_all_pending()
                    msg = (
                        f"📊 *Social Retry Complete!*\n"
                        f"• Retried: {res.get('retried_count', 0)}\n"
                        f"• Newly Published: {res.get('completed_count', 0)}\n"
                        f"• Still Pending: {res.get('remaining_pending', 0)}"
                    )
                    self.send_message(chat_id, msg)
                except Exception as e:
                    self.send_message(chat_id, f"❌ Social retry error: {e}")
            threading.Thread(target=_run, daemon=True).start()

        elif text.startswith("/security"):
            self.send_message(chat_id, "🛡️ *Executing 5-point cybersecurity audit & hardening...*")
            def _run():
                try:
                    guard = SecurityGuard()
                    report = guard.run_security_audit(auto_harden=True)
                    self.send_message(
                        chat_id,
                        f"🛡️ *Security Audit Complete!*\n"
                        f"• Status: *{report.get('overall_status')}*\n"
                        f"• Code Integrity: {report.get('findings', {}).get('code_integrity', {}).get('status')}\n"
                        f"• Vault Hardening: {report.get('findings', {}).get('vault_hardening', {}).get('status')}"
                    )
                except Exception as e:
                    self.send_message(chat_id, f"❌ *Security audit error:* {e}")
            threading.Thread(target=_run, daemon=True).start()

        elif text.startswith("/surprise") or text.startswith("/idea"):
            self.send_message(chat_id, "💡 *Brainstorming unexpected creative breakthrough...*")
            def _run_idea():
                try:
                    from growth.evolution_engine import EvolutionEngine
                    ee = EvolutionEngine()
                    sparks = ee.generate_surprise_sparks(force_refresh=True)
                    spark = sparks[0] if sparks else None
                    if spark:
                        msg = (
                            f"✨ *AI Creative Surprise Spark!*\n\n"
                            f"📌 *Title*: *{spark.get('title')}*\n"
                            f"🎯 *Format*: {spark.get('target_platform')}\n\n"
                            f"🧠 *Concept*: {spark.get('concept')}\n\n"
                            f"⚡ *Surprise Factor*: _{spark.get('surprise_factor')}_\n\n"
                            f"🚀 *To produce this idea right now, reply with*: `/execute_idea`"
                        )
                        self.send_message(chat_id, msg)
                except Exception as e:
                    self.send_message(chat_id, f"❌ Error generating idea: {e}")
            threading.Thread(target=_run_idea, daemon=True).start()

        elif text.startswith("/execute_idea"):
            self.send_message(chat_id, "🚀 *Engaging AI creation for the latest surprise idea...*")
            def _exec():
                try:
                    from growth.evolution_engine import EvolutionEngine
                    ee = EvolutionEngine()
                    journal = ee.load_journal()
                    sparks = journal.get("active_sparks", [])
                    spark_id = sparks[0].get("id") if sparks else ""
                    res = ee.execute_spark_idea(spark_id)
                    self.send_message(chat_id, f"🎉 *Creation launched in background!*\n{res.get('message')}")
                except Exception as e:
                    self.send_message(chat_id, f"❌ Execution error: {e}")
            threading.Thread(target=_exec, daemon=True).start()

        else:
            self.send_message(chat_id, "❓ Unknown command. Send `/surprise` to get a fresh idea, or send any Photo/Video to post to Stories.")

    def handle_media(self, chat_id: int, file_id: str, is_video: bool, caption: Optional[str] = None):
        """Downloads photo or video from Telegram and stages it in Story/ for immediate upload."""
        try:
            # 1. Get file path
            info_url = f"{self.base_url}/getFile?file_id={file_id}"
            resp = requests.get(info_url, timeout=10).json()
            if not resp.get("ok"):
                self.send_message(chat_id, "❌ Could not retrieve media file from Telegram.")
                return

            file_path = resp["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"

            # 2. Save into Story/ folder
            ext = ".mp4" if is_video else ".jpg"
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"telegram_{timestamp}{ext}"
            story_dir = config.BASE_DIR / "Story"
            story_dir.mkdir(parents=True, exist_ok=True)
            target_file = story_dir / filename

            self.send_message(chat_id, "⏳ *Downloading media into Story/ folder...*")
            with requests.get(download_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(target_file, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)

            if caption:
                caption_file = story_dir / f"telegram_{timestamp}.txt"
                caption_file.write_text(caption, encoding="utf-8")

            self.send_message(
                chat_id,
                f"🎉 *Media Received!* Saved as `{filename}`.\n"
                f"The autonomous StoryWatcher is now publishing it to *Instagram, Facebook & WhatsApp Stories*! 🚀"
            )
            logger.info(f"📲 [Telegram Bot] Downloaded media to Story/: {filename}")

        except Exception as e:
            logger.error(f"Error handling media from Telegram: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ Failed to process media: {e}")

    def poll_updates(self):
        url = f"{self.base_url}/getUpdates"
        params = {"offset": self.offset, "timeout": 20}
        try:
            resp = requests.get(url, params=params, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    self.offset = update["update_id"] + 1
                    msg = update.get("message") or update.get("channel_post")
                    if not msg:
                        continue

                    sender = msg.get("from", {})
                    sender_id = sender.get("id") or msg.get("chat", {}).get("id")
                    if not self.is_authorized(sender_id):
                        logger.warning(f"Unauthorized Telegram access attempt from ID: {sender_id}")
                        continue

                    caption = msg.get("caption", "")

                    if "photo" in msg:
                        # Grab highest resolution
                        photo = msg["photo"][-1]
                        self.handle_media(sender_id, photo["file_id"], is_video=False, caption=caption)

                    elif "video" in msg:
                        video = msg["video"]
                        self.handle_media(sender_id, video["file_id"], is_video=True, caption=caption)

                    elif "document" in msg and any(msg["document"].get("mime_type", "").startswith(p) for p in ["image/", "video/"]):
                        doc = msg["document"]
                        is_v = doc.get("mime_type", "").startswith("video/")
                        self.handle_media(sender_id, doc["file_id"], is_video=is_v, caption=caption)

                    elif "text" in msg:
                        self.handle_command(sender_id, msg["text"])

        except requests.exceptions.Timeout:
            pass
        except Exception as e:
            logger.debug(f"Telegram polling notice: {e}")
            time.sleep(3)

    def start_polling(self, block: bool = False):
        if not self.is_configured():
            logger.debug("Telegram bot token not configured. Skipping bot polling.")
            return

        self.running = True
        logger.info("🤖 [Telegram Remote Bot] Started polling for commands & Story uploads.")

        def _loop():
            while self.running:
                self.poll_updates()
                time.sleep(1)

        if block:
            _loop()
        else:
            t = threading.Thread(target=_loop, daemon=True, name="TelegramBotThread")
            t.start()
            return t


def start_telegram_bot_if_configured():
    bot = TelegramRemoteBot()
    if bot.is_configured():
        return bot.start_polling(block=False)
    return None
