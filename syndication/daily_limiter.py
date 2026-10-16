"""
Social Media Daily Rate Limiter
Enforces the strict policy: "post one time in day only" for the Social AI Agent
across Instagram, Facebook, and WhatsApp.
"""

import datetime
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import config

logger = logging.getLogger("SocialDailyLimiter")
_LIMITER_LOCK = threading.Lock()


class SocialDailyLimiter:
    """
    Manages and enforces the 1-post-per-day quota for the Social AI Agent.
    Guarantees that regardless of how many triggers, drops, or background pulses occur,
    content is only published to Instagram, Facebook, and WhatsApp once per calendar day.
    """

    _instance: Optional["SocialDailyLimiter"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with _LIMITER_LOCK:
                if cls._instance is None:
                    cls._instance = super(SocialDailyLimiter, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, tracker_file: Optional[Path] = None):
        if getattr(self, "_initialized", False):
            return
        self.tracker_file = tracker_file or config.SOCIAL_TRACKER_FILE
        self.daily_limit = getattr(config, "SOCIAL_DAILY_POST_LIMIT", 1)
        self.state = self._load_state()
        self._initialized = True

    def _today_str(self) -> str:
        return datetime.date.today().strftime("%Y-%m-%d")

    def _load_state(self) -> Dict[str, Any]:
        with _LIMITER_LOCK:
            if self.tracker_file.exists():
                try:
                    data = json.loads(self.tracker_file.read_text(encoding="utf-8"))
                    # If date is from a previous day, auto-reset count
                    if data.get("last_post_date") != self._today_str():
                        data["posts_today_count"] = 0
                        data["current_date"] = self._today_str()
                    return data
                except Exception as e:
                    logger.debug(f"Could not read tracker file, re-initializing: {e}")

            default_state = {
                "current_date": self._today_str(),
                "last_post_date": None,
                "posts_today_count": 0,
                "daily_limit": self.daily_limit,
                "last_post_timestamp": None,
                "history": []
            }
            return default_state

    def _save_state(self) -> None:
        try:
            self.tracker_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.tracker_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
            tmp.replace(self.tracker_file)
        except Exception as e:
            logger.warning(f"Failed to persist social daily tracker: {e}")

    def can_post_generated_today(self, force: bool = False) -> bool:
        """Returns True if today's daily generated festival/promotional content has not been posted yet."""
        if force:
            return True
        with _LIMITER_LOCK:
            today = self._today_str()
            if self.state.get("last_post_date") != today:
                return True
            return not self.state.get("generated_posted_today", False)

    def can_post_post_folder_today(self, force: bool = False) -> bool:
        """Returns True if today's Story/Post/ folder batch has not been posted yet."""
        if force:
            return True
        with _LIMITER_LOCK:
            today = self._today_str()
            if self.state.get("last_post_date") != today:
                return True
            return not self.state.get("post_folder_posted_today", False)

    def is_cycle_completed_today(self) -> bool:
        """Returns True if today's sharp 11:30 PM social cycle has fully completed."""
        with _LIMITER_LOCK:
            today = self._today_str()
            return self.state.get("daily_cycle_completed_date") == today

    def can_post_today(self, force: bool = False, source: Optional[str] = None) -> bool:
        """
        Returns True if the Social Agent is permitted to publish today.
        Supports per-source querying (generated vs post_folder).
        """
        if force:
            logger.info("⚡ [Daily Limiter] Force override active: bypassing daily post limit.")
            return True

        with _LIMITER_LOCK:
            today = self._today_str()
            # If tracking date has rolled over to a new calendar day, reset counts & flags
            if self.state.get("last_post_date") != today:
                self.state["posts_today_count"] = 0
                self.state["current_date"] = today
                self.state["generated_posted_today"] = False
                self.state["post_folder_posted_today"] = False

            if source in ("post_folder", "story_watcher_post"):
                return not self.state.get("post_folder_posted_today", False)
            elif source in ("festival_agent", "generated"):
                return not self.state.get("generated_posted_today", False)

            if self.state.get("daily_cycle_completed_date") == today:
                return False

            gen_done = self.state.get("generated_posted_today", False)
            post_done = self.state.get("post_folder_posted_today", False)
            if gen_done and post_done:
                return False

            return True

    def mark_post_folder_posted(
        self,
        media_names: List[str],
        platforms: List[str],
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Records completion of Story/Post/ folder batch for today."""
        with _LIMITER_LOCK:
            today = self._today_str()
            now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.state["last_post_date"] = today
            self.state["post_folder_posted_today"] = True
            self.state["posts_today_count"] = self.state.get("posts_today_count", 0) + 1
            self.state["last_post_timestamp"] = now_iso

            entry = {
                "timestamp": now_iso,
                "date": today,
                "source": "story_watcher_post",
                "media_files": media_names,
                "platforms": platforms,
                "details": details or {"is_post_folder": True}
            }
            history = self.state.setdefault("history", [])
            history.append(entry)
            if len(history) > 30:
                self.state["history"] = history[-30:]
            self._save_state()
            logger.info(f"📂 [Daily Limiter] Marked Story/Post/ content batch as posted for {today}.")

    def mark_cycle_completed(self) -> None:
        """Marks the entire sharp 11:30 PM daily social publishing cycle completed for today."""
        with _LIMITER_LOCK:
            today = self._today_str()
            self.state["daily_cycle_completed_date"] = today
            self.state["last_post_date"] = today
            self.state["generated_posted_today"] = True
            self.state["post_folder_posted_today"] = True
            self._save_state()
            logger.info(f"🏁 [Daily Limiter] Daily 11:30 PM social cycle marked 100% complete for {today}.")

    def record_post(
        self,
        source: str,
        media_names: List[str],
        platforms: List[str],
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Records a completed social publishing event and updates the daily quota.
        """
        with _LIMITER_LOCK:
            today = self._today_str()
            now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if self.state.get("last_post_date") != today:
                self.state["posts_today_count"] = 0
                self.state["generated_posted_today"] = False
                self.state["post_folder_posted_today"] = False

            self.state["last_post_date"] = today
            self.state["posts_today_count"] = self.state.get("posts_today_count", 0) + 1
            self.state["last_post_timestamp"] = now_iso
            self.state["daily_limit"] = self.daily_limit

            details_dict = details or {}
            if source == "festival_agent" or details_dict.get("is_generated"):
                self.state["generated_posted_today"] = True
            if details_dict.get("is_post_folder") or source in ("post_folder", "story_watcher_post"):
                self.state["post_folder_posted_today"] = True

            entry = {
                "timestamp": now_iso,
                "date": today,
                "source": source,
                "media_files": media_names,
                "platforms": platforms,
                "details": details_dict
            }
            history = self.state.setdefault("history", [])
            history.append(entry)
            # Keep only last 30 entries
            if len(history) > 30:
                self.state["history"] = history[-30:]

            self._save_state()

            logger.info(
                f"🎉 [Daily Limiter] Successfully recorded daily social post "
                f"({self.state['posts_today_count']}/{self.daily_limit} for {today})! "
                f"Platforms: {', '.join(platforms)}. Next post scheduled for tomorrow."
            )

    def get_status(self) -> Dict[str, Any]:
        """Returns the current daily posting status."""
        with _LIMITER_LOCK:
            today = self._today_str()
            count = self.state.get("posts_today_count", 0) if self.state.get("last_post_date") == today else 0
            return {
                "date": today,
                "posts_today": count,
                "daily_limit": self.daily_limit,
                "can_post": self.can_post_today(),
                "generated_posted": self.state.get("generated_posted_today", False),
                "post_folder_posted": self.state.get("post_folder_posted_today", False),
                "cycle_completed": (self.state.get("daily_cycle_completed_date") == today),
                "last_post_date": self.state.get("last_post_date"),
                "last_post_timestamp": self.state.get("last_post_timestamp")
            }


# Global singleton instance
limiter = SocialDailyLimiter()


def is_social_upload_window(target_time: Optional[str] = None, now_dt: Optional[datetime.datetime] = None) -> bool:
    """
    Returns True if current local time is at or past the scheduled daily social upload time
    (default 23:30 / sharp 11:30 PM) on the current calendar day.
    Between 00:00 and 23:29, returns False (preventing premature daytime uploads).
    From 23:30 to 23:59, returns True.
    """
    time_str = target_time or getattr(config, "SOCIAL_DAILY_UPLOAD_TIME", "23:30")
    try:
        parts = time_str.split(":")
        target_hour = int(parts[0])
        target_minute = int(parts[1])
        now = now_dt or datetime.datetime.now()
        target_dt = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        return now >= target_dt
    except Exception:
        return False

