"""
YouTube Daily Rate Limiter
Enforces the strict policy: run strictly 1 time in whole day for the YouTube Agent.
"""

import datetime
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import config

logger = logging.getLogger("YouTubeDailyLimiter")
_LIMITER_LOCK = threading.Lock()


class YouTubeDailyLimiter:
    """
    Manages and enforces the 1-run-per-day quota for the YouTube Agent.
    Guarantees that regardless of how many boots, reboots, wakeups, or background
    scheduler pulses occur, YouTube Shorts generation and uploads occur strictly
    once per calendar day.
    """

    _instance: Optional["YouTubeDailyLimiter"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with _LIMITER_LOCK:
                if cls._instance is None:
                    cls._instance = super(YouTubeDailyLimiter, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, tracker_file: Optional[Path] = None):
        if getattr(self, "_initialized", False):
            return
        self.tracker_file = tracker_file or config.YOUTUBE_TRACKER_FILE
        self.daily_limit = getattr(config, "YOUTUBE_DAILY_RUN_LIMIT", 1)
        self.state = self._load_state()
        self._initialized = True

    def _today_str(self) -> str:
        return datetime.date.today().strftime("%Y-%m-%d")

    def _load_state(self) -> Dict[str, Any]:
        with _LIMITER_LOCK:
            if self.tracker_file.exists():
                try:
                    data = json.loads(self.tracker_file.read_text(encoding="utf-8"))
                    today = self._today_str()
                    if data.get("last_run_date") != today:
                        data["runs_today_count"] = 0
                        data["current_date"] = today
                    return data
                except Exception as e:
                    logger.debug(f"Could not read YouTube tracker file, re-initializing: {e}")

            default_state = {
                "current_date": self._today_str(),
                "last_run_date": None,
                "runs_today_count": 0,
                "daily_limit": self.daily_limit,
                "last_run_timestamp": None,
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
            logger.warning(f"Failed to persist YouTube daily tracker: {e}")

    def can_run_today(self, force: bool = False) -> bool:
        """
        Returns True if the YouTube Agent is permitted to generate and upload today.
        Returns False if the daily quota (1 run/day) has already been fulfilled today.
        """
        if force:
            logger.info("⚡ [YouTube Daily Limiter] Force override active: bypassing daily run limit.")
            return True

        with _LIMITER_LOCK:
            today = self._today_str()
            # If tracking date has rolled over to a new calendar day, reset count
            if self.state.get("last_run_date") != today:
                self.state["runs_today_count"] = 0
                self.state["current_date"] = today

            count = self.state.get("runs_today_count", 0)
            if count >= self.daily_limit:
                logger.info(
                    f"⏸️ [YouTube Daily Limiter] Daily YouTube limit reached ({count}/{self.daily_limit} for {today}). "
                    f"Next YouTube run allowed tomorrow. Skipping."
                )
                return False

            return True

    def record_run(
        self,
        run_dir: Optional[Path] = None,
        topic: str = "",
        videos: Optional[Dict[str, str]] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """
        Records a completed YouTube pipeline run and updates the daily quota.
        """
        with _LIMITER_LOCK:
            today = self._today_str()
            now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if self.state.get("last_run_date") != today:
                self.state["runs_today_count"] = 0

            self.state["last_run_date"] = today
            self.state["runs_today_count"] = self.state.get("runs_today_count", 0) + 1
            self.state["last_run_timestamp"] = now_iso
            self.state["daily_limit"] = self.daily_limit

            entry = {
                "timestamp": now_iso,
                "date": today,
                "run_dir": str(run_dir) if run_dir else "",
                "topic": topic,
                "videos": videos or {},
                "details": details or kwargs
            }
            history = self.state.setdefault("history", [])
            history.append(entry)
            if len(history) > 30:
                self.state["history"] = history[-30:]

            self._save_state()

            logger.info(
                f"🎉 [YouTube Daily Limiter] Successfully recorded daily YouTube run "
                f"({self.state['runs_today_count']}/{self.daily_limit} for {today})! "
                f"Topic: '{topic}'. Next YouTube run scheduled for tomorrow."
            )

    def get_status(self) -> Dict[str, Any]:
        """Returns the current daily YouTube run status."""
        with _LIMITER_LOCK:
            today = self._today_str()
            count = self.state.get("runs_today_count", 0) if self.state.get("last_run_date") == today else 0
            return {
                "date": today,
                "runs_today": count,
                "daily_limit": self.daily_limit,
                "can_run": (count < self.daily_limit),
                "last_run_date": self.state.get("last_run_date"),
                "last_run_timestamp": self.state.get("last_run_timestamp")
            }


# Global singleton instance
youtube_limiter = YouTubeDailyLimiter()
