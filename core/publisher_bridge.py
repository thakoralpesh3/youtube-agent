"""PublisheR AI Bridge for YouTube Agent Coordinator
Triggers PublisheR AI (Amazon KDP & Flipkart Publishing Agent) autonomously
as Step 4 in the sequential daily production pipeline.
"""

import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("PublisherBridge")

PUBLISHER_AGENT_DIR = Path("/home/alpesh/book-publishing-agent")
PUBLISHER_SCRIPT = PUBLISHER_AGENT_DIR / "run_background_publisher.sh"
PUBLISHER_TRACKER = PUBLISHER_AGENT_DIR / "output" / "publisher_daily_tracker.json"


def is_publisher_ready_to_run(force: bool = False) -> bool:
    """Checks if PublisheR AI is installed and if today's run is due."""
    if not PUBLISHER_SCRIPT.exists():
        logger.warning(f"PublisheR script not found at {PUBLISHER_SCRIPT}")
        return False
    
    if force:
        return True

    if PUBLISHER_TRACKER.exists():
        try:
            import datetime
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            data = json.loads(PUBLISHER_TRACKER.read_text(encoding="utf-8") or "{}")
            if data.get("last_run_date") == today_str and data.get("runs_today_count", 0) >= data.get("daily_limit", 1):
                logger.info(f"✨ PublisheR AI has already published today's book ({data.get('last_book_title', '')}).")
                return False
        except Exception as e:
            logger.debug(f"Tracker check notice: {e}")

    return True


def run_publisher_daily(force: bool = False) -> Dict[str, Any]:
    """
    Executes PublisheR AI autonomously in the background.
    Generates a daily trending book, interior PDF, full-wrap cover,
    Amazon KDP metadata, and Flipkart listing catalog.
    """
    if not PUBLISHER_SCRIPT.exists():
        logger.warning(f"PublisheR launcher not found: {PUBLISHER_SCRIPT}")
        return {"status": "skipped", "reason": "script_not_found"}

    if not is_publisher_ready_to_run(force=force):
        return {"status": "skipped", "reason": "already_ran_today"}

    logger.info("=" * 65)
    logger.info("📚 [Step 4/4: PublisheR AI] Launching background book publishing pipeline...")
    logger.info("=" * 65)

    cmd = ["bash", str(PUBLISHER_SCRIPT)]
    if force:
        cmd.append("--force")

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PUBLISHER_AGENT_DIR),
            capture_output=True,
            text=True,
            timeout=900  # 15 minutes max
        )

        if proc.returncode == 0:
            logger.info("✅ [Step 4/4: PublisheR AI] Book generation completed successfully!")
            return {"status": "completed", "output": proc.stdout[-500:] if proc.stdout else ""}
        else:
            logger.error(f"❌ [Step 4/4: PublisheR AI] Finished with exit code {proc.returncode}")
            if proc.stderr:
                logger.error(f"Stderr: {proc.stderr[-500:]}")
            return {"status": "failed", "code": proc.returncode, "error": proc.stderr[-500:] if proc.stderr else ""}

    except subprocess.TimeoutExpired:
        logger.error("⏱️ [Step 4/4: PublisheR AI] Timed out after 900 seconds.")
        return {"status": "timeout"}
    except Exception as e:
        logger.error(f"❌ [Step 4/4: PublisheR AI] Execution exception: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
