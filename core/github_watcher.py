#!/usr/bin/env python3
"""
Antigravity to GitHub Real-Time Auto-Sync Watcher Daemon
======================================================
Monitors repository for changes made by Antigravity or local edits.
Debounces multi-file edits, automatically commits with descriptive messages,
and pushes directly to GitHub (origin/main).

Can be run:
1. As a background daemon thread in scheduler.py / autostart.sh
2. Standalone via CLI: python3 core/github_watcher.py
3. Via sync CLI: python3 core/github_sync.py --watch
"""

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.github_sync import get_git_status, sync_to_github
from growth.notifier import notifier

logger = logging.getLogger("GitHubWatcher")


class GitHubAutoSyncWatcher:
    """
    Watches git status for any changes introduced by Antigravity or developers.
    Waits for a debounce window after the last file modification to allow multi-file
    operations to finish, then automatically stages, commits, and pushes to GitHub.
    """

    def __init__(self, debounce_seconds: int = 15, poll_interval: int = 5):
        self.debounce_seconds = debounce_seconds
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_change_time: Optional[float] = None
        self._pending_changes = False

    def start(self, daemon: bool = True) -> threading.Thread:
        """Starts the auto-sync watcher in a background thread."""
        if self._thread and self._thread.is_alive():
            return self._thread
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=daemon,
            name="GitHubAutoSyncWatcher"
        )
        self._thread.start()
        logger.info(
            f"👀 [GitHub Auto-Sync Watcher] Active in background "
            f"(poll: {self.poll_interval}s, debounce: {self.debounce_seconds}s)..."
        )
        return self._thread

    def stop(self) -> None:
        """Stops the auto-sync watcher."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("🛑 [GitHub Auto-Sync Watcher] Stopped.")

    def is_running(self) -> bool:
        """Checks if watcher thread is active."""
        return bool(self._thread and self._thread.is_alive())

    def trigger_immediate_sync(self, message: Optional[str] = None) -> dict:
        """Bypasses debounce and triggers an immediate sync."""
        logger.info("⚡ [GitHub Auto-Sync] Immediate sync requested...")
        res = sync_to_github(message=message, push=True)
        self._pending_changes = False
        self._last_change_time = None
        return res

    def _run_loop(self) -> None:
        """Continuous polling and debounce loop."""
        while not self._stop_event.is_set():
            try:
                status = get_git_status()
                total = (
                    len(status["modified"])
                    + len(status["added"])
                    + len(status["deleted"])
                    + len(status["untracked"])
                )

                now = time.time()
                if total > 0:
                    if not self._pending_changes:
                        files_preview = ", ".join(
                            (status["modified"] + status["added"] + status["untracked"])[:3]
                        )
                        logger.info(
                            f"📝 [GitHub Auto-Sync] Detected {total} changed file(s) [{files_preview}...]. "
                            f"Debouncing {self.debounce_seconds}s for Antigravity edits to settle..."
                        )
                        self._pending_changes = True
                    self._last_change_time = now

                elif self._pending_changes and total == 0:
                    # Cleaned or committed externally
                    self._pending_changes = False
                    self._last_change_time = None

                # Check if debounce window expired
                if self._pending_changes and self._last_change_time:
                    elapsed = now - self._last_change_time
                    if elapsed >= self.debounce_seconds:
                        logger.info(
                            f"🚀 [GitHub Auto-Sync] Debounce window elapsed ({int(elapsed)}s). "
                            f"Synchronizing Antigravity changes to GitHub..."
                        )
                        res = sync_to_github(push=True)
                        self._pending_changes = False
                        self._last_change_time = None

                        if res.get("status") == "PUSHED":
                            commit_title = res.get("message", "Antigravity updates")
                            logger.info(f"🎉 [GitHub Auto-Sync] Successfully pushed to origin/main: '{commit_title}'")
                            try:
                                notifier.send(
                                    "🚀 GitHub Auto-Sync Complete",
                                    f"Antigravity changes committed & pushed to GitHub main!\nCommit: {commit_title[:65]}",
                                    urgency="low",
                                    timeout_ms=5000,
                                )
                            except Exception:
                                pass
            except Exception as e:
                logger.debug(f"[GitHub Auto-Sync Watcher] Poll cycle notice: {e}")

            self._stop_event.wait(timeout=self.poll_interval)


# Global singleton instance
watcher = GitHubAutoSyncWatcher(debounce_seconds=15, poll_interval=5)


def start_watcher_background() -> threading.Thread:
    """Helper to start the global watcher in background daemon mode."""
    return watcher.start(daemon=True)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    print("=" * 65)
    print("🤖 ANTIGRAVITY TO GITHUB REAL-TIME AUTO-SYNC WATCHER")
    print("=" * 65)
    print("Watching repository for Antigravity changes...")
    print("Press Ctrl+C to stop.\n")

    w = GitHubAutoSyncWatcher(debounce_seconds=10, poll_interval=3)
    t = w.start(daemon=False)
    try:
        while t.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping auto-sync watcher...")
        w.stop()
        print("Goodbye!")
