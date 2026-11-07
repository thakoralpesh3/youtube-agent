#!/usr/bin/env python3
"""
Sequential Daily Content Runner (On-Demand & Boot Trigger)
Order of execution:
  [1] YouTube Agent runs to 100% completion (generates EN, HI, GU Shorts & publishes/archives).
  [2] Social AI Agent runs to 100% completion (Royal Enfield Chamunda Auto / Festival).
  [3] 1-Click YouTube Stuck Video Cleaner runs.
  [4] PublisheR AI runs to 100% completion (Amazon KDP & Flipkart book generation).
Usage:
  python3 run_daily_now.py          # Runs if today's quota is not yet fulfilled
  python3 run_daily_now.py --force  # Forces immediate execution regardless of quota
"""

import argparse
import datetime
import logging
import sys
from pathlib import Path

# Set up logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("SequentialDailyRunner")

def main():
    parser = argparse.ArgumentParser(description="Run YouTube, Social Media, and PublisheR AI agents in strict sequential order.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force execution even if today's daily limit has already been reached.",
    )
    parser.add_argument(
        "--social",
        action="store_true",
        help="Run only the Social Media Agent (Royal Enfield Chamunda Auto / Festival stories).",
    )
    parser.add_argument(
        "--youtube",
        action="store_true",
        help="Run only the YouTube Agent (Trilingual Shorts & 16:9 Masterclass).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Run only the 1-Click YouTube Stuck Ghost Video Cleaner.",
    )
    parser.add_argument(
        "--stories",
        action="store_true",
        help="Upload pending media directly from Story/Post/ to Instagram, Facebook & WhatsApp.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Run autonomous GitHub synchronization to push all local changes.",
    )
    args = parser.parse_args()

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    logger.info("=" * 70)
    logger.info(f"🚀 DAILY CONTENT RUNNER ({today_str})")
    logger.info(f"   Mode: {'FORCE OVERRIDE' if args.force else 'Standard (1 run/day quota check)'}")
    logger.info("=" * 70)

    if args.social:
        from scheduler import run_daily_social_worker
        logger.info("📱 Launching Social Media Agent...")
        run_daily_social_worker(force=args.force)
    elif args.youtube:
        from agent import YouTubeAgent
        logger.info("🎬 Launching YouTube Agent...")
        YouTubeAgent().run_trilingual(force=args.force)
    elif args.clean:
        from scheduler import run_daily_youtube_cleaner
        logger.info("🧹 Launching YouTube Stuck Ghost Cleaner...")
        run_daily_youtube_cleaner(force=True)
    elif args.stories:
        from syndication.story_watcher import StoryWatcher
        logger.info("📲 Uploading stories from Story/Post/...")
        watcher = StoryWatcher()
        res = watcher.upload_from_post_folder(force=True)
        logger.info(f"✨ Processed {len(res)} story item(s).")
    elif args.sync:
        from core.github_sync import sync_to_github
        logger.info("🌐 Running GitHub Auto-Sync...")
        sync_to_github(push=True)
    else:
        logger.info("   Execution Order: [1] YouTube Agent ➔ [2] Social AI Agent ➔ [3] Cleaner ➔ [4] PublisheR AI")
        from scheduler import run_daily_coordinator_worker
        run_daily_coordinator_worker(force=args.force)

if __name__ == "__main__":
    main()
