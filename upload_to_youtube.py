#!/usr/bin/env python3
"""
Dedicated YouTube Content Uploader & Leftover Sweeper
====================================================
Uploads all pending / leftover video content to YouTube channel with auto-retry.
Deep scans all run directories (single and trilingual), handles interrupted runs,
and maintains an upload cache to eliminate duplicate uploads.
"""

import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import config
from youtube.uploader import YouTubeUploader
from growth.self_healer import SelfHealer
from growth.notifier import notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("YouTubeUploaderTool")

CACHE_FILE = config.OUTPUT_DIR / "youtube_uploaded_cache.json"


def _load_uploaded_cache() -> Dict[str, Any]:
    """Loads cache of verified uploaded video paths and IDs."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug(f"Could not read upload cache: {e}")
    return {"uploaded_files": {}, "uploaded_ids": []}


def _save_uploaded_cache(cache: Dict[str, Any]) -> None:
    """Safely saves upload cache to disk."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        tmp.replace(CACHE_FILE)
    except Exception as e:
        logger.debug(f"Could not save upload cache: {e}")


def _get_video_file_hash(video_path: Path) -> str:
    """Computes quick SHA256 of first 64KB + file size for fast duplicate recognition."""
    try:
        size = video_path.stat().st_size
        h = hashlib.sha256()
        h.update(str(size).encode())
        with open(video_path, "rb") as f:
            chunk = f.read(65536)
            h.update(chunk)
        return h.hexdigest()
    except Exception:
        return str(video_path.name)


def _extract_metadata_for_video(video_path: Path, run_dir: Path) -> Dict[str, Any]:
    """Extracts title, description, and tags from summary.json, package.json, or script.json."""
    title = None
    desc = None
    tags = ["shorts", "dailygrowth", "mindset", "success"]

    is_standard = video_path.name.startswith("final_video") and not video_path.name.startswith("final_short")
    thumb_path = run_dir / "thumbnail.jpg"
    thumbnail_path = str(thumb_path.resolve()) if (thumb_path.exists() and thumb_path.stat().st_size > 1000) else None

    # 1. Try summary.json
    sum_file = run_dir / "summary.json"
    if sum_file.exists():
        try:
            sdata = json.loads(sum_file.read_text(encoding="utf-8"))
            if is_standard and "youtube_video" in sdata and isinstance(sdata["youtube_video"], dict):
                yv = sdata["youtube_video"]
                return {
                    "title": yv.get("title"),
                    "description": yv.get("description"),
                    "tags": yv.get("tags", ["masterclass", "dailygrowth", "mindset", "success", "habits"]),
                    "thumbnail_path": yv.get("thumbnail_path") or thumbnail_path,
                    "is_standard": True,
                }
            topic = sdata.get("topic", "")
            if "_hi" in video_path.stem:
                title = sdata.get("details", {}).get("titles", {}).get("hi") or sdata.get("title")
            elif "_gu" in video_path.stem:
                title = sdata.get("details", {}).get("titles", {}).get("gu") or sdata.get("title")
            else:
                title = sdata.get("details", {}).get("titles", {}).get("en") or sdata.get("title")
            if not desc and topic:
                desc = f"{topic}\n\nMaster your habits and mindset with Daily Growth. #Shorts #DailyGrowth"
        except Exception:
            pass

    # 1.5 Try long_video_script.json for standard video
    long_script = run_dir / "long_video_script.json"
    if is_standard and long_script.exists():
        try:
            ldata = json.loads(long_script.read_text(encoding="utf-8"))
            return {
                "title": ldata.get("title"),
                "description": ldata.get("description"),
                "tags": ldata.get("tags", ["masterclass", "dailygrowth", "mindset", "success"]),
                "thumbnail_path": thumbnail_path,
                "pinned_comment": ldata.get("pinned_comment"),
                "category_id": ldata.get("category_id", "27"),
                "is_standard": True,
            }
        except Exception:
            pass

    # 2. Try package.json (trilingual runs)
    pkg_file = run_dir / "package.json"
    if not title and pkg_file.exists():
        try:
            pdata = json.loads(pkg_file.read_text(encoding="utf-8"))
            topic = pdata.get("topic", "")
            if "_hi" in video_path.stem and "hindi" in pdata:
                title = pdata["hindi"].get("title")
                desc = pdata["hindi"].get("description")
                tags = pdata["hindi"].get("tags", tags)
            elif "_gu" in video_path.stem and "gujarati" in pdata:
                title = pdata["gujarati"].get("title")
                desc = pdata["gujarati"].get("description")
                tags = pdata["gujarati"].get("tags", tags)
            elif "english" in pdata:
                title = pdata["english"].get("title")
                desc = pdata["english"].get("description")
                tags = pdata["english"].get("tags", tags)
        except Exception:
            pass

    # 3. Try script.json (single runs)
    script_file = run_dir / "script.json"
    if not title and script_file.exists():
        try:
            scdata = json.loads(script_file.read_text(encoding="utf-8"))
            title = scdata.get("title")
            desc = scdata.get("description")
            tags = scdata.get("tags", tags)
        except Exception:
            pass

    # 4. Fallback: Generate clean SEO title
    if not title:
        if is_standard:
            title = "The Stoic Resilience Glitch: Masterclass Guide"
            desc = f"{title}\n\nMaster your discipline, focus, and mindset daily. In-depth masterclass breakdown.\n\nSubscribe for daily growth! #DailyGrowth #Stoicism"
            tags = ["stoicism", "dailygrowth", "mindset", "focus", "discipline"]
        else:
            clean_name = run_dir.name.replace("run_trilingual_", "").replace("run_", "")
            lang_tag = "Hindi" if "_hi" in video_path.stem else ("Gujarati" if "_gu" in video_path.stem else "English")
            title = f"The Stoic Resilience Glitch {lang_tag} #Shorts"
    if not desc:
        desc = f"{title}\n\nMaster your discipline, focus, and mindset daily. Subscribe for daily growth shorts! #Shorts #DailyGrowth"

    return {
        "title": title,
        "description": desc,
        "tags": tags,
        "thumbnail_path": thumbnail_path,
        "is_standard": is_standard,
    }


def get_pending_videos() -> List[Dict[str, Any]]:
    """
    Deep scans all output directories to gather all available generated videos
    that have NOT yet been uploaded to YouTube.
    """
    pending = []
    seen_paths = set()
    cache = _load_uploaded_cache()
    uploaded_files_cache = cache.get("uploaded_files", {})

    # 1. Check pending_uploads directory
    queue_dir = config.OUTPUT_DIR / "pending_uploads"
    if queue_dir.exists():
        for qf in sorted(queue_dir.glob("*.json")):
            try:
                data = json.loads(qf.read_text(encoding="utf-8"))
                vpath = Path(data.get("video_path", ""))
                if vpath.exists() and vpath not in seen_paths:
                    seen_paths.add(vpath)
                    sdata = data.get("script_data", {})
                    lang_code = sdata.get("language") or ("hi" if "_hi" in vpath.stem else ("gu" if "_gu" in vpath.stem else "en"))
                    pending.append({
                        "video_path": vpath,
                        "script": sdata,
                        "source_json": qf,
                        "run_dir": vpath.parent,
                        "lang": lang_code,
                    })
            except Exception as e:
                logger.debug(f"Error reading queue file {qf.name}: {e}")

    # 2. Deep scan all run directories (run_* and run_trilingual_*)
    run_dirs = sorted(list(config.OUTPUT_DIR.glob("run_*")), reverse=True)
    for run_dir in run_dirs:
        if not run_dir.is_dir():
            continue

        # Look for summary.json
        summary_file = run_dir / "summary.json"
        summary_yt = {}
        if summary_file.exists():
            try:
                sdata = json.loads(summary_file.read_text(encoding="utf-8"))
                yt_info = sdata.get("youtube", {})
                if isinstance(yt_info, dict):
                    summary_yt = yt_info
            except Exception:
                pass

        # Scan all completed mp4 files in this run directory
        # Include Shorts (final_short*.mp4) AND Standard Landscape Videos (final_video*.mp4)
        video_candidates = list(run_dir.glob("final_short*.mp4")) + list(run_dir.glob("final_video*.mp4"))
        if not video_candidates:
            # Check for any root .mp4 files inside the run
            video_candidates = [f for f in run_dir.glob("*.mp4") if not f.name.startswith("temp_") and "raw_" not in f.name]

        for vpath in video_candidates:
            if vpath in seen_paths or not vpath.exists() or vpath.stat().st_size < 10000:
                continue

            is_standard = vpath.name.startswith("final_video") and not vpath.name.startswith("final_short")
            lang_code = "en"
            if not is_standard:
                if "_hi" in vpath.stem:
                    lang_code = "hi"
                elif "_gu" in vpath.stem:
                    lang_code = "gu"

            # Check if recorded in summary.json
            if is_standard:
                std_record = sdata.get("youtube_video", {}).get("upload_result", {}) if isinstance(sdata, dict) else {}
                if std_record.get("video_id") or std_record.get("video_url"):
                    continue  # Already uploaded!
            else:
                lang_record = summary_yt.get(lang_code, {}) if isinstance(summary_yt, dict) else {}
                if lang_record.get("video_id") or lang_record.get("video_url"):
                    continue  # Already uploaded!

            # Check if recorded in uploaded_cache
            v_hash = _get_video_file_hash(vpath)
            if v_hash in uploaded_files_cache:
                continue  # Already uploaded in earlier session!

            # Video is genuine leftover needing upload!
            meta = _extract_metadata_for_video(vpath, run_dir)
            seen_paths.add(vpath)
            pending.append({
                "video_path": vpath,
                "script": meta,
                "source_json": None,
                "run_dir": run_dir,
                "lang": lang_code,
                "is_standard": is_standard,
            })

    return pending


def check_youtube_quota_status(uploader: YouTubeUploader):
    """Inspects recent channel upload history to calculate when YouTube's 24h rolling limit resets."""
    try:
        res = uploader.service.search().list(
            part="snippet", forMine=True, type="video", maxResults=15, order="date"
        ).execute()
        items = res.get("items", [])
        if not items:
            return None

        # Parse published timestamps
        timestamps = []
        for it in items:
            dt = datetime.fromisoformat(it["snippet"]["publishedAt"].replace("Z", "+00:00"))
            timestamps.append((dt, it["snippet"]["title"]))

        timestamps.sort(key=lambda x: x[0], reverse=True)
        return timestamps
    except Exception as e:
        logger.warning(f"Could not fetch channel history: {e}")
        return None


def upload_all_pending(watch_mode: bool = False, max_uploads: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Uploads all pending and leftover videos to YouTube.
    Guarantees no duplicate uploads and updates both summary.json and the persistent cache.
    """
    uploader = YouTubeUploader()

    # In unattended/daemon mode, do not fail or prompt if token is expired
    if not uploader.auth.is_token_valid() and (os.environ.get("NON_INTERACTIVE") == "1" or not sys.stdin or not sys.stdin.isatty()):
        logger.info("ℹ️ YouTube OAuth token is unauthenticated or expired. Videos safely preserved in output/. Run 'python3 upload_to_youtube.py' in a terminal to authenticate.")
        return []

    # Verify authentication
    try:
        ch = uploader.service.channels().list(part="snippet,statistics", mine=True).execute()
        ch_item = ch["items"][0]
        logger.info(f"✅ Authenticated Channel: '{ch_item['snippet']['title']}' (ID: {ch_item['id']})")
    except Exception as e:
        logger.warning(f"⚠️ YouTube authentication notice: {e}")
        return []

    # Clean any stuck ghost drafts on channel before processing
    try:
        from youtube.upload_healer import YouTubeUploadHealer
        healer = YouTubeUploadHealer(uploader=uploader)
        clean_res = healer.clean_stuck_ghost_videos()
        if clean_res.get("deleted"):
            logger.info(f"🧹 [Auto-Cleaner] Purged {len(clean_res['deleted'])} stuck ghost draft(s) from YouTube channel!")
    except Exception as e:
        logger.debug(f"Stuck video check notice: {e}")

    uploaded_results = []
    cache = _load_uploaded_cache()

    while True:
        pending = get_pending_videos()
        logger.info(f"📋 Found {len(pending)} pending / leftover video(s) to upload on YouTube.")
        
        if not pending:
            logger.info("✨ No pending videos to upload. All content is up to date!")
            return uploaded_results

        all_uploaded = True
        limit_hit = False

        for item in pending:
            if max_uploads and len(uploaded_results) >= max_uploads:
                logger.info(f"Reached batch limit of {max_uploads} uploads.")
                return uploaded_results

            vpath = item["video_path"]
            script = item["script"]
            is_standard = item.get("is_standard") or script.get("is_standard") or (vpath.name.startswith("final_video") and not vpath.name.startswith("final_short"))
            title = script.get("title", "Daily Growth Masterclass" if is_standard else "Daily Growth #Shorts")
            desc = script.get("description", title)
            tags = script.get("tags", ["masterclass", "dailygrowth", "mindset"] if is_standard else ["shorts", "dailygrowth"])
            cat_id = script.get("category_id", "27")
            pinned = script.get("pinned_comment")

            thumb_path = script.get("thumbnail_path")
            if not thumb_path:
                candidate_thumb = vpath.parent / "thumbnail.jpg"
                if candidate_thumb.exists() and candidate_thumb.stat().st_size > 1000:
                    thumb_path = candidate_thumb
            else:
                thumb_path = Path(thumb_path)
                if not (thumb_path.exists() and thumb_path.stat().st_size > 1000):
                    thumb_path = None

            video_type_str = "Standard 16:9 Video" if is_standard else "Short"
            logger.info(f"🚀 [Leftover Upload] Attempting YouTube upload ({video_type_str}): '{title}' ({vpath.name}, {vpath.stat().st_size / 1024 / 1024:.1f} MB)...")
            try:
                res = uploader.upload_video(
                    video_path=vpath,
                    title=title,
                    description=desc,
                    tags=tags,
                    category_id=cat_id,
                    pinned_comment=pinned,
                    thumbnail_path=thumb_path,
                )
                logger.info(f"🎉 SUCCESS! Uploaded to YouTube: {res.get('video_url')}")
                uploaded_results.append(res)

                # Update summary.json in the run directory
                try:
                    sum_file = vpath.parent / "summary.json"
                    sdata = {}
                    if sum_file.exists():
                        sdata = json.loads(sum_file.read_text(encoding="utf-8"))
                    else:
                        sdata = {
                            "timestamp": vpath.parent.name.replace("run_trilingual_", "").replace("run_", ""),
                            "title": title,
                            "video_path": str(vpath),
                        }
                    if is_standard:
                        if "youtube_video" not in sdata or not isinstance(sdata["youtube_video"], dict):
                            sdata["youtube_video"] = {}
                        sdata["youtube_video"]["upload_result"] = res
                        sdata["youtube_video"]["title"] = title
                        sdata["youtube_video"]["video_path"] = str(vpath.resolve())
                        if thumb_path:
                            sdata["youtube_video"]["thumbnail_path"] = str(thumb_path.resolve())
                    else:
                        if "youtube" not in sdata or not isinstance(sdata["youtube"], dict):
                            sdata["youtube"] = {}
                        lang = item.get("lang") or ("hi" if "_hi" in vpath.stem else ("gu" if "_gu" in vpath.stem else "en"))
                        sdata["youtube"][lang] = res
                    sum_file.write_text(json.dumps(sdata, indent=2), encoding="utf-8")
                except Exception as sum_err:
                    logger.debug(f"Notice updating summary.json: {sum_err}")

                # Update uploaded cache to guarantee no duplicates
                v_hash = _get_video_file_hash(vpath)
                cache["uploaded_files"][v_hash] = {
                    "path": str(vpath),
                    "video_id": res.get("video_id"),
                    "video_url": res.get("video_url"),
                    "title": title,
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                }
                if res.get("video_id"):
                    cache["uploaded_ids"].append(res.get("video_id"))
                _save_uploaded_cache(cache)

                # Send Native Desktop Notification
                try:
                    notifier.send(
                        "🎉 YouTube Video Uploaded!",
                        f"Title: {title[:50]}\nLive: {res.get('video_url')}",
                        urgency="normal",
                        timeout_ms=7000,
                    )
                except Exception:
                    pass

                if item["source_json"] and item["source_json"].exists():
                    item["source_json"].unlink()
            except Exception as e:
                err_str = str(e)
                if "uploadLimitExceeded" in err_str:
                    logger.warning("⚠️ YouTube Daily Upload Limit reached on this channel account.")
                    try:
                        notifier.notify_agent_failure(
                            agent_name="YouTube Agent",
                            failure_step="YouTube Upload Limit Exceeded",
                            error_message="Channel daily upload limit reached (uploadLimitExceeded).",
                            details={"video": title, "path": str(vpath.name)},
                        )
                    except Exception:
                        pass
                    limit_hit = True
                    all_uploaded = False
                    break
                elif "quotaExceeded" in err_str:
                    logger.warning("⚠️ YouTube API Quota Exceeded.")
                    try:
                        notifier.notify_agent_failure(
                            agent_name="YouTube Agent",
                            failure_step="YouTube API Quota Exceeded",
                            error_message="Daily YouTube API v3 quota (10,000 units) exhausted.",
                            details={"video": title, "path": str(vpath.name)},
                        )
                    except Exception:
                        pass
                    limit_hit = True
                    all_uploaded = False
                    break
                else:
                    logger.error(f"❌ Upload error for {vpath.name}: {e}")
                    try:
                        notifier.notify_agent_failure(
                            agent_name="YouTube Agent",
                            failure_step="YouTube Video Upload",
                            error_message=str(e),
                            details={"video": title, "path": str(vpath.name)},
                        )
                    except Exception:
                        pass
                    all_uploaded = False

        if not watch_mode or all_uploaded:
            break

        if limit_hit:
            history = check_youtube_quota_status(uploader)
            now = datetime.now(timezone.utc)
            wait_seconds = 300
            
            if history and len(history) >= 10:
                tenth_latest = history[9][0]
                reset_time = tenth_latest + timedelta(hours=24, minutes=2)
                diff = (reset_time - now).total_seconds()
                if diff > 0:
                    wait_seconds = int(diff)
                    logger.info(f"⏳ YouTube 24-hour limit will begin unlocking at {reset_time.strftime('%H:%M:%S UTC')} (in {wait_seconds // 60} minutes).")
                else:
                    logger.info("⏳ Limit window rolling over now. Waiting 2 minutes for YouTube propagation...")
                    wait_seconds = 120

            logger.info(f"😴 Waiting {wait_seconds} seconds before retrying YouTube upload...")
            time.sleep(min(wait_seconds, 600))

    return uploaded_results


def sweep_and_upload_all_leftovers() -> int:
    """Convenience entry point for startup / boot sweeps."""
    results = upload_all_pending(watch_mode=False)
    return len(results)


if __name__ == "__main__":
    watch = "--watch" in sys.argv
    upload_all_pending(watch_mode=watch)
