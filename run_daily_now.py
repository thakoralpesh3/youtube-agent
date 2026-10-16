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
    args = parser.parse_args()

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    logger.info("=" * 70)
    logger.info(f"🚀 SEQUENTIAL DAILY CONTENT RUNNER ({today_str})")
    logger.info(f"   Mode: {'FORCE OVERRIDE' if args.force else 'Standard (1 run/day quota check)'}")
    logger.info("   Execution Order: [1] YouTube Agent ➔ [2] Social AI Agent ➔ [3] Cleaner ➔ [4] PublisheR AI")
    logger.info("=" * 70)

    from scheduler import run_daily_coordinator_worker
    run_daily_coordinator_worker(force=args.force)

if __name__ == "__main__":
    main()
