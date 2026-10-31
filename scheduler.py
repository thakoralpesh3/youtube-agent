import datetime
import logging
import sys
import threading
import time
from typing import Optional, Dict, Any, List
import schedule

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("DailyScheduler")


_DAILY_RUN_LOCK = threading.Lock()
_YOUTUBE_RUN_LOCK = threading.Lock()
_SOCIAL_RUN_LOCK = threading.Lock()


def dispatch_github_workflow(
    workflow_name: str = "daily_youtube_agent.yml",
    repo: str = None,
    inputs: dict = None,
) -> bool:
    """
    Directly dispatches a GitHub Actions workflow via the GitHub CLI ('gh').
    Triggers immediate cloud execution (~10-30s start time), bypassing
    the multi-hour delays caused by GitHub Actions free-tier cron queuing.
    """
    import shutil
    import subprocess

    target_repo = repo or getattr(config, "GITHUB_REPO", "thakoralpesh3/youtube-agent")
    gh_path = shutil.which("gh")
    if not gh_path:
        logger.warning("⚠️ [GitHub Cloud Dispatch] GitHub CLI ('gh') not found in PATH.")
        return False

    cmd = [gh_path, "workflow", "run", workflow_name, "-R", target_repo]
    if inputs:
        for k, v in inputs.items():
            cmd.extend(["-f", f"{k}={v}"])

    try:
        logger.info(f"🚀 [GitHub Cloud Dispatch] Dispatching workflow '{workflow_name}' on '{target_repo}'...")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            logger.info(f"✅ [GitHub Cloud Dispatch] Successfully dispatched '{workflow_name}' on GitHub Actions!")
            try:
                from growth.notifier import notifier
                notifier.send(
                    "🚀 Cloud Agent Dispatched",
                    f"Workflow '{workflow_name}' triggered on GitHub Actions without cron delay!",
                    urgency="normal",
                )
            except Exception:
                pass
            return True
        else:
            logger.error(f"❌ [GitHub Cloud Dispatch] Failed to dispatch workflow '{workflow_name}': {res.stderr.strip()}")
            return False
    except Exception as e:
        logger.error(f"❌ [GitHub Cloud Dispatch] Error executing gh workflow run: {e}")
        return False


def run_daily_social_worker(force: bool = False):
    """
    Sharp 11:30 PM Social Media Daily Publishing Worker:
    Uploads BOTH:
      1. Daily generated contents (festive/promotional campaign video & poster)
      2. Contents from Story/Post folder (Story/Post/) (never deletes original media)
      3. Any leftover pending stories stored in the social queue
    Target features: WhatsApp Status, Instagram Story, and Facebook Story.
    Strictly fires at sharp 11:30 PM (23:30) once per calendar day.
    """
    if not _SOCIAL_RUN_LOCK.acquire(blocking=False):
        logger.info("⏳ [11:30 PM Social Worker] Social daily upload is already in progress. Skipping concurrent run.")
        return

    try:
        from syndication.daily_limiter import limiter as social_limiter, is_social_upload_window
        if not force and not is_social_upload_window():
            logger.info("⏳ [11:30 PM Social Worker] Outside the sharp 11:30 PM upload window. Standing by.")
            return

        today_str = datetime.date.today().strftime("%Y-%m-%d")
        if not force and social_limiter.is_cycle_completed_today():
            logger.info(f"✨ [11:30 PM Social Worker] Today's social upload cycle already completed for {today_str}. Standing by for tomorrow.")
            return

        logger.info("=" * 70)
        logger.info(f"📱 [11:30 PM Social Worker] Starting sharp 11:30 PM daily story publishing for {today_str}...")
        logger.info("   Target Features: WhatsApp Status | Instagram Story | Facebook Story")
        logger.info("=" * 70)

        # 1. Sweep and publish all leftover stories across Instagram, Facebook, and WhatsApp
        try:
            from syndication.social_queue import SocialQueueManager
            qm = SocialQueueManager()
            leftover_soc = qm.sweep_and_publish_all_leftover_stories(max_items=10)
            if leftover_soc.get("published_count", 0) > 0:
                logger.info(f"🎉 [11:30 PM Social Worker] Leftover sweep published {leftover_soc['published_count']} story item(s)!")
        except Exception as e:
            logger.debug(f"Leftover social sweep notice: {e}")

        # 2. Upload contents from Post folder (Story/Post/) to WhatsApp, Instagram & Facebook stories
        try:
            from syndication.story_watcher import StoryWatcher
            watcher = StoryWatcher()
            post_res = watcher.upload_from_post_folder(force=force)
            uploaded_post = len([r for r in post_res if r.get("status") == "PUBLISHED"])
            if uploaded_post > 0:
                logger.info(f"🎉 [11:30 PM Social Worker] Successfully published {uploaded_post} media item(s) from Post folder to stories!")
        except Exception as e:
            logger.warning(f"⚠️ [11:30 PM Social Worker] Post folder upload notice: {e}")

        # 3. Generate & upload daily festive / promotional campaign content (video & poster)
        try:
            from syndication.festival_agent import run_daily_social_agent
            from growth.notifier import notifier
            notifier.notify_social_start("Royal Enfield Chamunda Automobile")
            sres = run_daily_social_agent(force=force)
            logger.info(f"✅ [11:30 PM Social Worker] Daily generated story workflow finished with status: {sres.get('status', 'COMPLETED')}")
        except Exception as e:
            logger.error(f"❌ [11:30 PM Social Worker] Generated content publishing error: {e}", exc_info=True)

        # 4. Mark today's sharp 11:30 PM cycle complete
        social_limiter.mark_cycle_completed()

        logger.info("=" * 70)
        logger.info(f"🏁 [11:30 PM Social Worker] Completed sharp 11:30 PM social publishing cycle for {today_str}!")
        logger.info("=" * 70)
    except Exception as e:
        logger.error(f"❌ [11:30 PM Social Worker] Error during 11:30 PM social publishing: {e}", exc_info=True)
        try:
            from growth.notifier import notifier
            notifier.notify_agent_failure(
                agent_name="Social Media Agent",
                failure_step="11:30 PM Daily Social Publishing",
                error_message=str(e),
                details={"date": today_str},
            )
        except Exception:
            pass
    finally:
        _SOCIAL_RUN_LOCK.release()


def run_daily_coordinator_worker(force: bool = False):
    """
    Strict Sequential Daily Coordinator Worker:
    Ensures YouTube Agent, Social Agent, Cleaner, and PublisheR AI run strictly 1 time per calendar day.
    Execution is strictly sequential:
      Step 1: YouTube Agent runs to 100% completion (generates EN, HI, GU Shorts & publishes/archives).
      Step 2: Social AI Agent runs to 100% completion (Royal Enfield Chamunda Auto / Festival).
      Step 3: 1-Click YouTube Stuck Video Cleaner runs.
      Step 4: PublisheR AI runs to 100% completion (Amazon KDP & Flipkart book generation).
    """
    if not _DAILY_RUN_LOCK.acquire(blocking=False):
        logger.info("⏳ [Autonomous Daily Coordinator] Sequential daily run is already in progress. Skipping concurrent trigger.")
        return

    try:
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        logger.info("=" * 70)
        logger.info(f"🔄 [Autonomous Daily Coordinator] Starting Sequential Daily Run for {today_str}")
        logger.info("   Policy: Strictly 1 run per day | Order: [1] YouTube Agent ➔ [2] Social AI Agent ➔ [3] Cleaner ➔ [4] PublisheR AI")
        logger.info("=" * 70)

        # -------------------------------------------------------------
        # STEP 1: YouTube Daily Pipeline (STRICTLY FIRST)
        # -------------------------------------------------------------
        try:
            _YOUTUBE_RUN_LOCK.acquire()
            try:
                # 1a: Sweep and upload any leftover unuploaded videos across all run dirs first!
                try:
                    from upload_to_youtube import sweep_and_upload_all_leftovers
                    yt_leftovers_count = sweep_and_upload_all_leftovers()
                    if yt_leftovers_count > 0:
                        logger.info(f"🎉 [Step 1/4: YouTube Agent] Swept & uploaded {yt_leftovers_count} leftover video(s) to YouTube!")
                except Exception as e:
                    logger.debug(f"Leftover YouTube upload notice: {e}")

                from growth.youtube_daily_limiter import youtube_limiter
                from growth.notifier import notifier
                from agent import YouTubeAgent
                agent = YouTubeAgent()
                resumable_yt = agent.find_latest_resumable_run(trilingual=True)
                can_run_yt = force or youtube_limiter.can_run_today() or (resumable_yt is not None)
                if can_run_yt:
                    logger.info("=" * 65)
                    action_desc = f"Resuming incomplete trilingual run ({resumable_yt.name})" if resumable_yt else f"Starting daily trilingual run for {today_str}"
                    logger.info(f"🎬 [Step 1/4: YouTube Agent] {action_desc}...")
                    logger.info("=" * 65)
                    notifier.notify_youtube_start()
                    agent.run_trilingual(target_platform="youtube", dry_run=False, force=force or (resumable_yt is not None), resume=True)
                    logger.info("✅ [Step 1/4: YouTube Agent] Completed 100% successfully!")
                else:
                    logger.info(f"✨ [Step 1/4: YouTube Agent] YouTube Agent already ran today ({today_str}). Proceeding to Social Agent.")
                    notifier.notify_youtube_quota_reached()
            finally:
                _YOUTUBE_RUN_LOCK.release()
        except Exception as e:
            logger.error(f"❌ [Step 1/4: YouTube Agent] Error in daily YouTube pipeline: {e}", exc_info=True)
            try:
                from growth.notifier import notifier
                notifier.notify_agent_failure(
                    agent_name="YouTube Agent",
                    failure_step="Daily YouTube Pipeline (Step 1/4)",
                    error_message=str(e),
                    details={"date": today_str},
                )
            except Exception:
                pass

        # -------------------------------------------------------------
        # STEP 2: Social AI Agent Daily Pipeline (Scheduled for sharp 11:30 PM)
        # -------------------------------------------------------------
        try:
            from syndication.daily_limiter import limiter as social_limiter, is_social_upload_window
            social_time = getattr(config, "SOCIAL_DAILY_UPLOAD_TIME", "23:30")
            if force or is_social_upload_window():
                logger.info("=" * 65)
                logger.info(f"📱 [Step 2/4: Social AI Agent] Executing 11:30 PM social publishing for {today_str}...")
                logger.info("=" * 65)
                run_daily_social_worker(force=force)
            else:
                logger.info(
                    f"⏳ [Step 2/4: Social AI Agent] Social story uploads are strictly scheduled for sharp 11:30 PM ({social_time}). "
                    f"Generated & Story/Post/ content safely staged and standing by."
                )
        except Exception as e:
            logger.error(f"❌ [Step 2/4: Social AI Agent] Error in daily Social step: {e}", exc_info=True)
            try:
                from growth.notifier import notifier
                notifier.notify_agent_failure(
                    agent_name="Social Media Agent",
                    failure_step="Daily Social Step (Step 2/4)",
                    error_message=str(e),
                    details={"date": today_str},
                )
            except Exception:
                pass


        # -------------------------------------------------------------
        # STEP 3: 1-Click YouTube Stuck Video Cleaner
        # -------------------------------------------------------------
        try:
            logger.info("=" * 65)
            logger.info(f"🧹 [Step 3/4: Daily Cleaner] Running 1-Click YouTube Stuck Video Cleaner check...")
            logger.info("=" * 65)
            run_daily_youtube_cleaner(force=force)
            logger.info("✅ [Step 3/4: Daily Cleaner] Check completed.")
        except Exception as e:
            logger.debug(f"Daily cleaner notice: {e}")

        # -------------------------------------------------------------
        # STEP 4: PublisheR AI (Amazon KDP & Flipkart Publishing Agent)
        # -------------------------------------------------------------
        try:
            from core.publisher_bridge import run_publisher_daily
            logger.info("=" * 65)
            logger.info(f"📚 [Step 4/4: PublisheR AI] Running Autonomous Book Publishing Pipeline...")
            logger.info("=" * 65)
            pres = run_publisher_daily(force=force)
            logger.info(f"✅ [Step 4/4: PublisheR AI] Finished with status: {pres.get('status')}")
        except Exception as e:
            logger.error(f"❌ [Step 4/4: PublisheR AI] Error triggering publisher pipeline: {e}", exc_info=True)

        logger.info("=" * 70)
        logger.info(f"🏁 [Autonomous Daily Coordinator] All daily tasks finished for {today_str}!")
        logger.info("=" * 70)

    finally:
        _DAILY_RUN_LOCK.release()


def run_daily_pipelines_if_needed(force: bool = False, background: bool = True):
    """
    Entrypoint called on daemon startup, daily schedule, or hourly pulse.
    If background=True, runs the sequential coordinator worker in a dedicated daemon thread.
    """
    if background:
        threading.Thread(
            target=run_daily_coordinator_worker,
            args=(force,),
            daemon=True,
            name="DailySequentialCoordinator",
        ).start()
    else:
        run_daily_coordinator_worker(force=force)


def is_youtube_upload_window(target_time: Optional[str] = None, now_dt: Optional[datetime.datetime] = None) -> bool:
    """
    Returns True if current local time is at or past the scheduled daily YouTube upload time
    (default 23:30 / sharp 11:30 PM) on the current calendar day.
    """
    time_str = target_time or getattr(config, "DAILY_UPLOAD_TIME", "23:30")
    try:
        parts = time_str.split(":")
        target_hour = int(parts[0])
        target_minute = int(parts[1])
        now = now_dt or datetime.datetime.now()
        target_dt = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        return now >= target_dt
    except Exception:
        return False


def job():
    upload_time = getattr(config, "DAILY_UPLOAD_TIME", "23:30")
    logger.info(f"⏰ Daily trigger activated at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Scheduled: {upload_time} IST)")

    # Zero-delay GitHub Actions Cloud Dispatch (if configured)
    cloud_dispatch = getattr(config, "DISPATCH_TO_GITHUB_ACTIONS", False)
    if cloud_dispatch:
        try:
            from growth.youtube_daily_limiter import youtube_limiter
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            if not youtube_limiter.can_run_today():
                logger.info(f"✨ [11:30 PM Trigger] YouTube Agent already ran today ({today_str}). Standing by for tomorrow.")
                return

            workflow = getattr(config, "GITHUB_YOUTUBE_WORKFLOW", "daily_youtube_agent.yml")
            repo = getattr(config, "GITHUB_REPO", "thakoralpesh3/youtube-agent")
            logger.info("=" * 65)
            logger.info(f"🚀 [11:30 PM Sharp Trigger] Dispatching YouTube Agent to GitHub Actions ({workflow})...")
            logger.info("   Zero delay: Starts immediately on GitHub cloud runner without cron queue wait!")
            logger.info("=" * 65)
            success = dispatch_github_workflow(workflow_name=workflow, repo=repo)
            if success:
                youtube_limiter.record_run(topic="github_actions_cloud_dispatch", run_id="cloud_dispatch")
                logger.info("✅ [11:30 PM Sharp Trigger] Cloud run dispatched. Daily YouTube limit recorded.")
                return
            else:
                logger.warning("⚠️ [11:30 PM Sharp Trigger] GitHub Actions dispatch failed. Falling back to local execution...")
        except Exception as err:
            logger.warning(f"⚠️ [11:30 PM Sharp Trigger] Notice during cloud dispatch: {err}")

    run_daily_pipelines_if_needed(force=False, background=True)


def run_daily_youtube_cleaner(force: bool = False) -> bool:
    """
    Executes the 1-Click YouTube Stuck Video Cleaner once per calendar day.
    Saves the execution date in output/youtube_cleaner_tracker.json to guarantee
    it runs strictly once daily, conserving YouTube API quota.
    """
    tracker_file = getattr(config, "YOUTUBE_CLEANER_TRACKER_FILE", config.OUTPUT_DIR / "youtube_cleaner_tracker.json")
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    if not force and tracker_file.exists():
        try:
            import json
            data = json.loads(tracker_file.read_text(encoding="utf-8"))
            if data.get("last_run_date") == today_str:
                logger.info(f"✨ [Daily Cleaner] 1-Click Cleaner already ran today ({today_str}). Next run tomorrow.")
                return False
        except Exception as e:
            logger.debug(f"Could not read cleaner tracker file: {e}")

    logger.info("=" * 60)
    logger.info(f"🧹 [Daily Cleaner] Running 1-Click YouTube Stuck Video Cleaner at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")
    logger.info("=" * 60)

    try:
        from youtube.auth import YouTubeAuth
        if not YouTubeAuth().is_token_valid():
            logger.info("ℹ️ [Daily Cleaner] YouTube OAuth token not valid or expired. Skipping cleaner check until authenticated.")
            return False

        from youtube.upload_healer import YouTubeUploadHealer
        healer = YouTubeUploadHealer()
        res = healer.clean_stuck_ghost_videos(max_check=50)
        deleted = res.get("deleted", [])
        if deleted:
            logger.info(f"🎉 [Daily Cleaner] Cleaned {len(deleted)} stuck ghost video(s) from YouTube:")
            for d in deleted:
                logger.info(f"   • Removed: '{d['title']}' (ID: {d['id']}, age: {d.get('age_hours', 0):.1f}h)")
        else:
            logger.info("✨ [Daily Cleaner] All YouTube uploads are healthy. No stuck processing drafts found.")

        # Record successful completion date
        import json
        tracker_file.parent.mkdir(parents=True, exist_ok=True)
        tracker_file.write_text(json.dumps({
            "last_run_date": today_str,
            "last_run_timestamp": datetime.datetime.now().isoformat(),
            "deleted_count": len(deleted),
            "status": res.get("status", "SUCCESS"),
        }, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"⚠️ [Daily Cleaner] Notice during daily YouTube stuck cleaner: {e}")
        return False



_ALERT_COOLDOWN_FILE = config.OUTPUT_DIR / ".youtube_login_alert_cooldown"


def _should_notify_login_required(cooldown_hours: int = 12) -> bool:
    """Enforces cooldown on YouTube login desktop notifications to prevent alert fatigue."""
    try:
        if _ALERT_COOLDOWN_FILE.exists():
            last_ts = float(_ALERT_COOLDOWN_FILE.read_text(encoding="utf-8").strip())
            if time.time() - last_ts < cooldown_hours * 3600:
                return False
        _ALERT_COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ALERT_COOLDOWN_FILE.write_text(str(time.time()), encoding="utf-8")
        return True
    except Exception:
        return True


def hourly_cycle():
    """
    Runs every 1 hour automatically:
    1. Checks if there is pending video content for YouTube and uploads it automatically.
    2. Runs a quick Story drop-folder check.
    3. Executes self-healing health check and token validation.
    """
    logger.info("=" * 60)
    logger.info(f"⏱️ [Hourly Auto-Run] Pulse active at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 1. Hourly YouTube Sweep & Auto-Upload Engine
    # Checks if any generated contents were unable to upload on YouTube, and uploads them!
    if _YOUTUBE_RUN_LOCK.acquire(blocking=False):
        try:
            # First: check if there are any pending videos or resumable runs that actually need uploading
            pending_vids = []
            try:
                from upload_to_youtube import get_pending_videos
                pending_vids = get_pending_videos()
            except Exception as pe:
                logger.debug(f"Error checking pending videos: {pe}")

            resumable = None
            agent = None
            try:
                from agent import YouTubeAgent
                agent = YouTubeAgent()
                resumable = agent.find_latest_resumable_run(trilingual=True)
            except Exception as re:
                logger.debug(f"Error checking resumable run: {re}")

            if not pending_vids and not resumable:
                logger.info("✨ [Hourly YouTube Pulse] All generated videos are uploaded and up to date.")
            else:
                # There is actual content waiting to be uploaded!
                from youtube.auth import YouTubeAuth
                auth = YouTubeAuth()
                if auth.is_token_valid():
                    if pending_vids:
                        logger.info(f"📋 [Hourly YouTube Pulse] Found {len(pending_vids)} unuploaded generated video(s). Attempting YouTube upload...")
                        from upload_to_youtube import upload_all_pending
                        uploaded = upload_all_pending(watch_mode=False)
                        if uploaded:
                            logger.info(f"🎉 [Hourly YouTube Pulse] Successfully uploaded {len(uploaded)} previously unuploaded video(s) to YouTube!")
                    if resumable and agent:
                        logger.info(f"🔄 [Hourly YouTube Pulse] Found incomplete generation run ({resumable.name}). Resuming to compile and upload...")
                        agent.run_trilingual(target_platform="youtube", dry_run=False, resume=True)
                else:
                    if auth.is_permanently_revoked():
                        logger.warning("⚠️ [Hourly YouTube Pulse] YouTube OAuth token permanently revoked or invalid.")
                        if _should_notify_login_required(cooldown_hours=12):
                            try:
                                from growth.notifier import notifier
                                notifier.send(
                                    "⚠️ YouTube Login Required",
                                    "YouTube OAuth token expired. Please open a terminal and run: python3 upload_to_youtube.py",
                                    urgency="normal",
                                    timeout_ms=10000,
                                )
                            except Exception:
                                pass
                    else:
                        logger.info("ℹ️ [Hourly YouTube Pulse] YouTube upload deferred: token refresh temporarily unavailable (network offline). Will retry on next hourly cycle.")
        except Exception as yt_err:
            logger.warning(f"⚠️ [Hourly YouTube Pulse] Notice during hourly YouTube check: {yt_err}")
        finally:
            _YOUTUBE_RUN_LOCK.release()
    else:
        logger.info("⏳ [Hourly YouTube Pulse] YouTube worker currently in progress. Skipping concurrent check.")

    # 2. Check Social Daily Limiter & Sharp 11:30 PM Window (Strictly 11:30 PM only)
    try:
        from syndication.daily_limiter import limiter as social_limiter, is_social_upload_window
        if is_social_upload_window():
            if social_limiter.can_post_today():
                logger.info("📱 [Hourly Auto-Run] Active 11:30 PM window detected! Triggering daily social story publishing...")
                run_daily_social_worker(force=False)
            else:
                try:
                    from syndication.social_queue import SocialQueueManager
                    qm = SocialQueueManager()
                    res = qm.sweep_and_publish_all_leftover_stories(max_items=3)
                    pub_count = res.get("completed_count", 0) or res.get("published_count", 0)
                    if pub_count > 0:
                        logger.info(f"🎉 [Hourly Auto-Run] Successfully published {pub_count} stored social item(s) across all platforms!")
                except Exception as e:
                    logger.debug(f"Pending social retry notice: {e}")
        else:
            logger.debug("⏳ [Hourly Auto-Run] Social story publishing safely standing by for sharp 11:30 PM (23:30) window.")
    except Exception as e:
        logger.debug(f"Social hourly check notice: {e}")

    # 4. Quick self-healing auto-repair
    try:
        from growth.self_healer import SelfHealer
        SelfHealer().auto_repair()
    except Exception as e:
        logger.debug(f"Self-healer notice: {e}")

    # 6. Autonomous Cybersecurity Sentinel & Anti-Hacker Shield
    try:
        from security.security_guard import SecurityGuard
        guard = SecurityGuard()
        guard.run_security_audit(auto_harden=True, alert_on_threat=True)
    except Exception as e:
        logger.debug(f"Cybersecurity audit notice: {e}")

    # 7. Autonomous Creative Evolution & Surprise Brainstorming Pulse
    try:
        from growth.evolution_engine import EvolutionEngine
        EvolutionEngine().evolve_creative_formulas()
    except Exception as e:
        logger.debug(f"Creative evolution pulse notice: {e}")

    # 8. Automated Daily 1-Click YouTube Stuck Video Cleaner (Runs strictly 1 time per day)
    try:
        run_daily_youtube_cleaner(force=False)
    except Exception as e:
        logger.debug(f"Daily cleaner check notice: {e}")

    # 9. Autonomous GitHub Auto-Sync Sweep (Ensures any Antigravity updates reach origin/main)
    try:
        from core.github_sync import sync_to_github
        res = sync_to_github(push=True)
        if res.get("status") == "PUSHED":
            logger.info(f"🎉 [Hourly Auto-Run] Pushed Antigravity modifications to GitHub: '{res.get('message')}'")
    except Exception as e:
        logger.debug(f"Hourly GitHub auto-sync sweep notice: {e}")


def run_daily_scheduler():
    upload_time = config.DAILY_UPLOAD_TIME
    logger.info("=" * 60)
    logger.info("🤖 YOUTUBE & SOCIAL AUTOMATION SCHEDULER STARTED")
    logger.info(f"📅 Daily Run Scheduled at: {upload_time}")
    logger.info("⏱️ Hourly Self-Run & Pending Uploader: ACTIVE (Runs every 1 hour for YouTube & Social Stories)")
    logger.info(f"🛡️ Cybersecurity Sentinel & Anti-Hacker Shield: ACTIVE (Hourly Audit & FIM)")
    logger.info(f"💡 AI Creative Evolution & Surprise Brain: ACTIVE (Continuous Ideation)")
    logger.info(f"🎯 Default Niche: {config.DEFAULT_NICHE}")
    logger.info("=" * 60)

    # Start Story folder auto-uploader in background thread
    try:
        from syndication.story_watcher import StoryWatcher
        watcher = StoryWatcher()
        watcher_thread = threading.Thread(target=watcher.watch_forever, daemon=True)
        watcher_thread.start()
        logger.info("👀 [Story Watcher] Active in background (Monitors 'Story/' for IG, FB & WA Stories)")
    except Exception as e:
        logger.warning(f"Could not start Story watcher thread: {e}")

    # Start 24/7 Online Web Control Center in background thread
    try:
        from web.server import start_web_server
        start_web_server(host=config.WEB_SERVER_HOST, port=config.WEB_SERVER_PORT, block=False)
        logger.info(f"🌐 [Web Control Center] Active at http://{config.WEB_SERVER_HOST}:{config.WEB_SERVER_PORT}")
    except Exception as e:
        logger.warning(f"Could not start Web Control Center: {e}")

    # Start Mobile Telegram Remote Bot (if configured)
    try:
        from syndication.telegram_bot import start_telegram_bot_if_configured
        start_telegram_bot_if_configured()
    except Exception as e:
        logger.debug(f"Telegram bot start notice: {e}")

    # Start Real-Time GitHub Auto-Sync Watcher in background daemon thread
    try:
        from core.github_watcher import start_watcher_background
        start_watcher_background()
        logger.info("🚀 [GitHub Auto-Sync Watcher] Active in background (Monitors & syncs Antigravity changes to GitHub)")
    except Exception as e:
        logger.warning(f"Could not start GitHub auto-sync watcher thread: {e}")

    # Schedule daily sharp 11:30 PM YouTube execution
    schedule.every().day.at(upload_time).do(job)
    logger.info(f"🎬 [Daily YouTube Agent] Scheduled daily at sharp {upload_time} IST (Trilingual Shorts & Masterclass Video)")

    # Schedule daily sharp 11:30 PM Social Publishing (Instagram, Facebook & WhatsApp Stories)
    social_upload_time = getattr(config, "SOCIAL_DAILY_UPLOAD_TIME", "23:30")
    schedule.every().day.at(social_upload_time).do(
        lambda: threading.Thread(target=run_daily_social_worker, args=(False,), daemon=True, name="Daily1130PMSocialWorker").start()
    )
    logger.info(f"📱 [Daily Social Agent] Scheduled daily at sharp {social_upload_time} IST (WhatsApp, Instagram & Facebook Stories)")

    # Schedule daily 1-click YouTube stuck video cleaner (23:55 PM IST)
    cleaner_time = getattr(config, "DAILY_CLEANER_TIME", "23:55")
    schedule.every().day.at(cleaner_time).do(run_daily_youtube_cleaner)
    logger.info(f"🧹 [Daily Cleaner] Scheduled daily at {cleaner_time} IST (1-Click Stuck Video Cleaner & Channel Auditor)")

    # Schedule hourly self-run (checks pending uploads & system health every 1 hour)
    schedule.every(1).hours.do(hourly_cycle)

    # Check on startup (e.g. laptop turned on): if today's sequential workflow is pending OR leftovers exist, run immediately!
    # Order: [1] YouTube Agent & Leftovers strictly first -> [2] Social AI Agent at 11:30 PM -> [3] Cleaner
    try:
        from growth.youtube_daily_limiter import youtube_limiter
        from syndication.daily_limiter import limiter as social_limiter, is_social_upload_window
        from upload_to_youtube import get_pending_videos
        from syndication.social_queue import SocialQueueManager

        has_leftover_yt = len(get_pending_videos()) > 0
        has_leftover_soc = len(SocialQueueManager().get_pending_items()) > 0
        yt_needed = (youtube_limiter.can_run_today() and is_youtube_upload_window()) or has_leftover_yt
        soc_needed = (social_limiter.can_post_today() or has_leftover_soc) and is_social_upload_window()

        if yt_needed:
            logger.info(
                f"🚀 [Startup Coordinator] Laptop started after 11:30 PM with pending YouTube tasks (can_run: {youtube_limiter.can_run_today()}, "
                f"leftovers: {has_leftover_yt}). Coordinating daily execution..."
            )
            cloud_dispatch = getattr(config, "DISPATCH_TO_GITHUB_ACTIONS", False)
            if cloud_dispatch and youtube_limiter.can_run_today():
                workflow = getattr(config, "GITHUB_YOUTUBE_WORKFLOW", "daily_youtube_agent.yml")
                repo = getattr(config, "GITHUB_REPO", "thakoralpesh3/youtube-agent")
                logger.info(f"🚀 [Startup Coordinator] Dispatching '{workflow}' to GitHub Actions...")
                if dispatch_github_workflow(workflow_name=workflow, repo=repo):
                    youtube_limiter.record_run(topic="github_actions_cloud_dispatch", run_id="startup_cloud_dispatch")
                else:
                    run_daily_pipelines_if_needed(force=False, background=True)
            else:
                run_daily_pipelines_if_needed(force=False, background=True)
        elif soc_needed:
            logger.info(
                f"🚀 [Startup Coordinator] Laptop started after 11:30 PM and social upload pending! "
                f"Launching sharp 11:30 PM social publishing worker..."
            )
            threading.Thread(target=run_daily_social_worker, args=(False,), daemon=True, name="StartupSocialWorker").start()
        else:
            logger.info(f"✅ [Startup Coordinator] Today's daily workflow is standing by for sharp 11:30 PM IST (Scheduled: {upload_time} IST).")
    except Exception as e:
        logger.warning(f"Startup coordinator check notice: {e}")

    # Run hourly cycle on startup in a separate background thread (checks pending uploads, story folder, security audit)
    threading.Thread(target=hourly_cycle, daemon=True, name="StartupHourlyCycle").start()

    while True:
        try:
            schedule.run_pending()
        except Exception as loop_err:
            logger.error(f"❌ Error during scheduled task pulse: {loop_err}", exc_info=True)
        time.sleep(10)


if __name__ == "__main__":
    run_daily_scheduler()
