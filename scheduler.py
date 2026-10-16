import datetime
import logging
import sys
import threading
import time
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
            notifier.send("⚠️ Social 11:30 PM Notice", f"Social publishing notice: {str(e)[:80]}", urgency="normal")
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
                notifier.send("⚠️ YouTube Agent Error", f"Daily run encountered notice: {str(e)[:80]}", urgency="normal")
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
                notifier.send("⚠️ Social Agent Notice", f"Daily social notice: {str(e)[:80]}", urgency="normal")
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


def job():
    logger.info(f"⏰ Daily trigger activated at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
            from youtube.auth import YouTubeAuth
            auth = YouTubeAuth()
            if auth.is_token_valid():
                # 1a. Upload any pending or leftover video files across output/
                try:
                    from upload_to_youtube import get_pending_videos, upload_all_pending
                    pending_vids = get_pending_videos()
                    if pending_vids:
                        logger.info(f"📋 [Hourly YouTube Pulse] Found {len(pending_vids)} unuploaded generated video(s). Attempting YouTube upload...")
                        uploaded = upload_all_pending(watch_mode=False)
                        if uploaded:
                            logger.info(f"🎉 [Hourly YouTube Pulse] Successfully uploaded {len(uploaded)} previously unuploaded video(s) to YouTube!")
                    else:
                        logger.info("✨ [Hourly YouTube Pulse] All generated videos are uploaded and up to date.")
                except Exception as up_err:
                    logger.warning(f"⚠️ [Hourly YouTube Pulse] Leftover video upload notice: {up_err}")

                # 1b. Check if any interrupted generation run exists and resume it to finish and upload
                try:
                    from agent import YouTubeAgent
                    agent = YouTubeAgent()
                    resumable = agent.find_latest_resumable_run(trilingual=True)
                    if resumable:
                        logger.info(f"🔄 [Hourly YouTube Pulse] Found incomplete generation run ({resumable.name}). Resuming to compile and upload...")
                        agent.run_trilingual(target_platform="youtube", dry_run=False, resume=True)
                except Exception as res_err:
                    logger.warning(f"⚠️ [Hourly YouTube Pulse] Incomplete run resumption notice: {res_err}")

            else:
                logger.info("ℹ️ [Hourly YouTube Pulse] YouTube OAuth token not valid or expired. Skipping hourly upload attempt.")
                try:
                    from growth.notifier import notifier
                    notifier.send(
                        "⚠️ YouTube Login Required",
                        "YouTube token expired. Please open a terminal and run: python3 upload_to_youtube.py",
                        urgency="normal",
                        timeout_ms=8000,
                    )
                except Exception:
                    pass
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

    # Schedule daily sequential execution: YouTube Agent (10:00 AM IST)
    schedule.every().day.at(upload_time).do(job)

    # Schedule daily sharp 11:30 PM Social Publishing (Instagram, Facebook & WhatsApp Stories)
    social_upload_time = getattr(config, "SOCIAL_DAILY_UPLOAD_TIME", "23:30")
    schedule.every().day.at(social_upload_time).do(
        lambda: threading.Thread(target=run_daily_social_worker, args=(False,), daemon=True, name="Daily1130PMSocialWorker").start()
    )
    logger.info(f"📱 [Daily Social Agent] Scheduled daily at sharp {social_upload_time} (WhatsApp, Instagram & Facebook Stories)")

    # Schedule daily 1-click YouTube stuck video cleaner (09:00 AM IST)
    cleaner_time = getattr(config, "DAILY_CLEANER_TIME", "09:00")
    schedule.every().day.at(cleaner_time).do(run_daily_youtube_cleaner)
    logger.info(f"🧹 [Daily Cleaner] Scheduled daily at {cleaner_time} (1-Click Stuck Video Cleaner & Channel Auditor)")

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
        yt_needed = youtube_limiter.can_run_today() or has_leftover_yt
        soc_needed = (social_limiter.can_post_today() or has_leftover_soc) and is_social_upload_window()

        if yt_needed:
            logger.info(
                f"🚀 [Startup Coordinator] Laptop started! YouTube action required (can_run: {youtube_limiter.can_run_today()}, "
                f"leftovers: {has_leftover_yt}). Launching sequential coordinator..."
            )
            run_daily_pipelines_if_needed(force=False, background=True)
        elif soc_needed:
            logger.info(
                f"🚀 [Startup Coordinator] Laptop started after 11:30 PM and social upload pending! "
                f"Launching sharp 11:30 PM social publishing worker..."
            )
            threading.Thread(target=run_daily_social_worker, args=(False,), daemon=True, name="StartupSocialWorker").start()
        else:
            logger.info("✅ [Startup Coordinator] Today's daily workflow is up to date and no leftovers pending. Daemon standing by in scheduled monitoring mode.")
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
