import asyncio
import hashlib
import json
import logging
import os
import secrets
import sys
import threading
from pathlib import Path
from typing import Dict, Any

from aiohttp import web

import config
from security.security_guard import SecurityGuard

logger = logging.getLogger("WebServer")
TEMPLATES_DIR = config.BASE_DIR / "web" / "templates"
AUTH_TOKENS = set()


def get_expected_token() -> str:
    salt = "youtube_social_agent_2026"
    return hashlib.sha256(f"{config.DASHBOARD_PASSWORD}_{salt}".encode()).hexdigest()


def check_auth(request: web.Request) -> bool:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1].strip()
        expected = get_expected_token()
        if token == expected or token in AUTH_TOKENS:
            return True
    return False


# --------------------------------------------------------------------------
# Route Handlers
# --------------------------------------------------------------------------
async def index_handler(request: web.Request) -> web.Response:
    html_file = TEMPLATES_DIR / "index.html"
    if not html_file.exists():
        return web.Response(text="Control Center template not found", status=404)
    return web.Response(text=html_file.read_text(encoding="utf-8"), content_type="text/html")


async def login_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        password = data.get("password", "")
    except Exception:
        return web.json_response({"status": "ERROR", "message": "Invalid JSON"}, status=400)

    if password == config.DASHBOARD_PASSWORD:
        token = get_expected_token()
        AUTH_TOKENS.add(token)
        return web.json_response({"status": "OK", "token": token})

    return web.json_response({"status": "ERROR", "message": "Invalid password"}, status=401)


async def status_handler(request: web.Request) -> web.Response:
    if not check_auth(request):
        return web.json_response({"status": "UNAUTHORIZED"}, status=401)

    # 1. YouTube status
    yt_token = Path(config.YOUTUBE_TOKEN_FILE)
    youtube_status = {
        "authenticated": yt_token.exists(),
        "privacy": config.YOUTUBE_PRIVACY_STATUS,
        "token_file": str(yt_token),
    }

    # 2. Social Profiles status
    social_profile = config.BASE_DIR / "assets" / "browser_profiles" / "social_firefox"
    social_ready = (social_profile / "cookies.sqlite").exists()
    social_status = {
        "browser_session_ready": social_ready,
        "profile_dir": str(social_profile),
    }

    # 3. Security Status
    security_status = {"status": "SECURE"}
    audit_log = config.OUTPUT_DIR / "security_audit.log"
    recent_logs = []
    if audit_log.exists():
        try:
            lines = audit_log.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
            recent_logs = lines[-35:]
            for line in reversed(lines):
                if "Security Audit: Status=" in line:
                    stat = line.split("Status=")[1].strip()
                    security_status["status"] = stat
                    break
        except Exception:
            pass

    # 4. Festival Check
    festival_info = {"name": "Royal Enfield Daily Blessing", "date": "Everyday"}
    try:
        from syndication.festival_detector import FestivalDetector
        detector = FestivalDetector()
        upcoming = detector.get_upcoming_festivals(days=30)
        if upcoming:
            festival_info = {
                "name": upcoming[0].festival_name,
                "date": upcoming[0].date_str,
            }
    except Exception:
        pass

    # 5. Creative Evolution & Surprise Sparks
    evolution_info = {
        "level_name": "Level 2: Creative Explorer",
        "creative_score": 140,
        "sparks_count": 0,
        "sparks": [],
    }
    try:
        from growth.evolution_engine import EvolutionEngine
        ee = EvolutionEngine()
        journal = ee.load_journal()
        evolution_info = {
            "level_name": journal.get("level_name", "Level 2: Creative Explorer"),
            "creative_score": journal.get("creative_score", 140),
            "sparks_count": len(journal.get("active_sparks", [])),
            "sparks": journal.get("active_sparks", []),
        }
    except Exception:
        pass

    # 6. Stored Social Queue (Instagram, Facebook, WhatsApp)
    social_queue_info = {"pending_count": 0, "total_tracked": 0, "pending_items": []}
    try:
        from syndication.social_queue import get_social_queue_status
        social_queue_info = get_social_queue_status()
    except Exception:
        pass

    # 7. Daily 1-Click YouTube Stuck Cleaner Status
    cleaner_info = {"last_run_date": "Not yet today", "status": "Ready", "last_run_timestamp": None}
    cleaner_tracker = getattr(config, "YOUTUBE_CLEANER_TRACKER_FILE", config.OUTPUT_DIR / "youtube_cleaner_tracker.json")
    if cleaner_tracker.exists():
        try:
            cdata = json.loads(cleaner_tracker.read_text(encoding="utf-8"))
            cleaner_info = {
                "last_run_date": cdata.get("last_run_date", "Never"),
                "status": f"Clean ({cdata.get('deleted_count', 0)} purged)" if cdata.get("deleted_count", 0) > 0 else "All Healthy",
                "last_run_timestamp": cdata.get("last_run_timestamp"),
            }
        except Exception:
            pass

    return web.json_response({
        "status": "OK",
        "model": config.GEMINI_MODEL,
        "youtube": youtube_status,
        "social": social_status,
        "security": security_status,
        "festival": festival_info,
        "evolution": evolution_info,
        "social_queue": social_queue_info,
        "cleaner": cleaner_info,
        "logs": recent_logs,
    })


async def trigger_shorts_handler(request: web.Request) -> web.Response:
    if not check_auth(request):
        return web.json_response({"status": "UNAUTHORIZED"}, status=401)

    def _run():
        try:
            from agent import YouTubeAgent
            YouTubeAgent().run_trilingual(dry_run=False)
        except Exception as e:
            logger.error(f"Error in background Shorts generation: {e}", exc_info=True)

    threading.Thread(target=_run, daemon=True).start()
    return web.json_response({"status": "OK", "message": "Trilingual Shorts generation started in background!"})


async def trigger_festival_handler(request: web.Request) -> web.Response:
    if not check_auth(request):
        return web.json_response({"status": "UNAUTHORIZED"}, status=401)

    def _run():
        try:
            from syndication.festival_agent import FestivalSocialAgent
            FestivalSocialAgent().run_festival_campaign(force_upload=True)
        except Exception as e:
            logger.error(f"Error in background Festival campaign: {e}", exc_info=True)

    threading.Thread(target=_run, daemon=True).start()
    return web.json_response({"status": "OK", "message": "Chamunda Automobile Festival Campaign launched in background!"})


async def trigger_pending_handler(request: web.Request) -> web.Response:
    if not check_auth(request):
        return web.json_response({"status": "UNAUTHORIZED"}, status=401)

    def _run():
        try:
            from upload_to_youtube import upload_all_pending
            upload_all_pending(watch_mode=False)
        except Exception as e:
            logger.error(f"Error in pending YouTube uploader: {e}", exc_info=True)

    threading.Thread(target=_run, daemon=True).start()
    return web.json_response({"status": "OK", "message": "Pending YouTube upload check started!"})


async def trigger_social_retry_handler(request: web.Request) -> web.Response:
    if not check_auth(request):
        return web.json_response({"status": "UNAUTHORIZED"}, status=401)

    def _run():
        try:
            from syndication.social_queue import SocialQueueManager
            SocialQueueManager().retry_all_pending()
        except Exception as e:
            logger.error(f"Error in pending social retry: {e}", exc_info=True)

    threading.Thread(target=_run, daemon=True).start()
    return web.json_response({"status": "OK", "message": "Pending social story retry initiated in background!"})


async def trigger_security_handler(request: web.Request) -> web.Response:
    if not check_auth(request):
        return web.json_response({"status": "UNAUTHORIZED"}, status=401)

    guard = SecurityGuard()
    report = guard.run_security_audit(auto_harden=True, alert_on_threat=True)
    return web.json_response(report)


async def trigger_cleaner_handler(request: web.Request) -> web.Response:
    if not check_auth(request):
        return web.json_response({"status": "UNAUTHORIZED"}, status=401)

    def _run():
        try:
            from scheduler import run_daily_youtube_cleaner
            run_daily_youtube_cleaner(force=True)
        except Exception as e:
            logger.error(f"Error in 1-click cleaner: {e}", exc_info=True)

    threading.Thread(target=_run, daemon=True).start()
    return web.json_response({"status": "OK", "message": "1-Click YouTube Stuck Cleaner initiated in background!"})



async def upload_story_handler(request: web.Request) -> web.Response:
    """
    Accepts multipart upload from smartphone or remote browser and places it
    directly into the Story/ folder. The background StoryWatcher picks it up
    and immediately uploads to Instagram, Facebook, and WhatsApp!
    """
    if not check_auth(request):
        return web.json_response({"status": "UNAUTHORIZED"}, status=401)

    try:
        data = await request.post()
        file_field = data.get("media")
        caption_text = str(data.get("caption", "")).strip()

        if not file_field:
            return web.json_response({"status": "ERROR", "message": "No media file found in form data"}, status=400)

        story_dir = config.BASE_DIR / "Story"
        story_dir.mkdir(parents=True, exist_ok=True)

        raw_filename = getattr(file_field, "filename", None) or f"remote_upload_{secrets.token_hex(4)}.jpg"
        clean_filename = SecurityGuard.sanitize_file_path(raw_filename).name
        clean_filename = clean_filename.replace(" ", "_")

        target_path = story_dir / clean_filename
        if target_path.exists():
            stem = target_path.stem
            ext = target_path.suffix
            target_path = story_dir / f"{stem}_{secrets.token_hex(3)}{ext}"

        if hasattr(file_field, "file"):
            content = file_field.file.read()
        else:
            content = bytes(file_field)

        target_path.write_bytes(content)
        saved_filename = target_path.name

        # If caption is provided, save corresponding .txt file
        if caption_text:
            caption_file = story_dir / f"{Path(saved_filename).stem}.txt"
            caption_file.write_text(caption_text, encoding="utf-8")

        logger.info(f"📲 [Web Studio] Hot-Drop file saved: {saved_filename} (Caption: '{caption_text}')")
        return web.json_response({
            "status": "OK",
            "filename": saved_filename,
            "message": f"Successfully received {saved_filename}. StoryWatcher is now publishing to IG, FB & WA Stories!",
        })

    except Exception as e:
        logger.error(f"Error handling Story upload: {e}", exc_info=True)
        return web.json_response({"status": "ERROR", "message": str(e)}, status=500)


async def get_sparks_handler(request: web.Request) -> web.Response:
    if not check_auth(request):
        return web.json_response({"status": "UNAUTHORIZED"}, status=401)
    from growth.evolution_engine import EvolutionEngine
    ee = EvolutionEngine()
    sparks = ee.generate_surprise_sparks(force_refresh=False)
    journal = ee.load_journal()
    return web.json_response({
        "status": "OK",
        "level_name": journal.get("level_name"),
        "creative_score": journal.get("creative_score"),
        "sparks": sparks,
    })


async def surprise_sparks_handler(request: web.Request) -> web.Response:
    if not check_auth(request):
        return web.json_response({"status": "UNAUTHORIZED"}, status=401)
    from growth.evolution_engine import EvolutionEngine
    ee = EvolutionEngine()
    sparks = ee.generate_surprise_sparks(force_refresh=True)
    journal = ee.load_journal()
    return web.json_response({
        "status": "OK",
        "message": f"Formulated {len(sparks)} fresh surprise ideas!",
        "level_name": journal.get("level_name"),
        "creative_score": journal.get("creative_score"),
        "sparks": sparks,
    })


async def execute_spark_handler(request: web.Request) -> web.Response:
    if not check_auth(request):
        return web.json_response({"status": "UNAUTHORIZED"}, status=401)
    try:
        data = await request.json()
        spark_id = data.get("spark_id", "")
    except Exception:
        spark_id = ""

    from growth.evolution_engine import EvolutionEngine
    ee = EvolutionEngine()
    res = ee.execute_spark_idea(spark_id)
    return web.json_response(res)


# --------------------------------------------------------------------------
# App Factory & Runner
# --------------------------------------------------------------------------
def create_app() -> web.Application:
    app = web.Application(client_max_size=120 * 1024 * 1024)  # 120MB upload limit
    app.router.add_get("/", index_handler)
    app.router.add_post("/api/login", login_handler)
    app.router.add_get("/api/status", status_handler)
    app.router.add_post("/api/trigger/shorts", trigger_shorts_handler)
    app.router.add_post("/api/trigger/festival", trigger_festival_handler)
    app.router.add_post("/api/trigger/pending", trigger_pending_handler)
    app.router.add_post("/api/social/retry_pending", trigger_social_retry_handler)
    app.router.add_post("/api/trigger/security", trigger_security_handler)
    app.router.add_post("/api/trigger/cleaner", trigger_cleaner_handler)
    app.router.add_post("/api/upload/story", upload_story_handler)
    app.router.add_get("/api/evolution/sparks", get_sparks_handler)
    app.router.add_post("/api/evolution/surprise", surprise_sparks_handler)
    app.router.add_post("/api/evolution/execute", execute_spark_handler)
    return app


def start_web_server(host: str = None, port: int = None, block: bool = False):
    host = host or config.WEB_SERVER_HOST
    port = port or config.WEB_SERVER_PORT

    def _run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = create_app()
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, host, port)
        loop.run_until_complete(site.start())
        logger.info(f"🌐 [24/7 Web Control Center] Active and listening at http://{host}:{port}")
        loop.run_forever()

    if block:
        _run_server()
    else:
        server_thread = threading.Thread(target=_run_server, daemon=True, name="WebControlCenter")
        server_thread.start()
        return server_thread


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    print(f"Starting Web Control Center on port {config.WEB_SERVER_PORT}...")
    start_web_server(block=True)
