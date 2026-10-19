import argparse
import datetime
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any

import subprocess
import config
from generator.script_generator import ScriptGenerator, LongVideoScript
from generator.audio_generator import AudioGenerator
from generator.image_generator import ImageGenerator
from generator.thumbnail_generator import ThumbnailGenerator
from generator.video_assembler import VideoAssembler
from growth.growth_engine import GrowthEngine
from growth.self_healer import SelfHealer
from syndication.story_publisher import StoryPublisher
from growth.youtube_daily_limiter import youtube_limiter
from youtube.auth import YouTubeAuth
from youtube.uploader import YouTubeUploader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("YouTubeAgent")


def send_desktop_notification(title: str, message: str, icon_path: Optional[str] = None) -> None:
    """Dispatches a non-intrusive Linux desktop notification."""
    try:
        from growth.notifier import notifier
        notifier.send(title, message, urgency="normal", custom_icon=icon_path)
    except Exception as e:
        logger.debug(f"Desktop notification notice: {e}")



class YouTubeAgent:
    def __init__(self, model: Optional[str] = None):
        self.model_name = model or config.GEMINI_MODEL
        if model:
            config.set_active_model(model)
        self.script_gen = ScriptGenerator(model_name=self.model_name)
        self.audio_gen = AudioGenerator()
        self.image_gen = ImageGenerator()
        self.thumbnail_gen = ThumbnailGenerator(api_key=self.script_gen.api_key)
        self.video_assembler = VideoAssembler()
        self.uploader = YouTubeUploader()
        self.growth_engine = GrowthEngine()
        self.self_healer = SelfHealer()
        self.story_publisher = StoryPublisher()

    def find_latest_resumable_run(self, trilingual: bool = False) -> Optional[Path]:
        """Finds the most recent incomplete run directory to resume within the last 48 hours."""
        pattern = "run_trilingual_*" if trilingual else "run_*"
        runs = sorted(list(config.OUTPUT_DIR.glob(pattern)), reverse=True)
        now = time.time()
        for r in runs:
            if not r.is_dir():
                continue
            # Skip runs older than 48 hours to avoid picking up outdated or corrupted historical runs
            try:
                if (now - r.stat().st_mtime) > (48 * 3600):
                    continue
            except Exception:
                continue
            if (r / ".unresumable").exists() or (r / ".corrupt").exists():
                continue

            if trilingual:
                pkg_file = r / "package.json"
                sum_file = r / "summary.json"
                if pkg_file.exists():
                    if not sum_file.exists():
                        return r
                    try:
                        sdata = json.loads(sum_file.read_text(encoding="utf-8"))
                        yt = sdata.get("youtube", {})
                        shorts_done = bool(yt.get("en", {}).get("video_id") and yt.get("hi", {}).get("video_id") and yt.get("gu", {}).get("video_id"))
                        video_done = bool(sdata.get("youtube_video", {}).get("upload_result", {}).get("video_url") or sdata.get("youtube_video", {}).get("upload_result", {}).get("video_id"))
                        if not (shorts_done and video_done):
                            return r
                    except Exception:
                        return r
            else:
                if "run_trilingual_" in r.name:
                    continue
                script_file = r / "script.json"
                summary_file = r / "summary.json"
                if script_file.exists():
                    if not summary_file.exists():
                        return r
                    try:
                        sdata = json.loads(summary_file.read_text(encoding="utf-8"))
                        short_done = bool(sdata.get("upload_result", {}).get("video_url"))
                        video_done = bool(sdata.get("youtube_video", {}).get("upload_result", {}).get("video_url"))
                        if not (short_done and video_done):
                            return r
                    except Exception:
                        return r
        return None

    def generate_standard_video(
        self,
        topic: Optional[str] = None,
        run_dir: Optional[Path] = None,
        dry_run: bool = False,
        progress_callback: Optional[Callable[[int, str, int], None]] = None,
    ) -> dict:
        """
        Generates and uploads a complete Standard YouTube Landscape Video (16:9, 1080p)
        including multi-scene chapters, voiceover, 16:9 visuals, custom thumbnail,
        description with timestamps, and tags.
        """
        def report(pct: int, msg: str, step: int = 6):
            if progress_callback:
                progress_callback(pct, msg, step)

        if not run_dir:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = config.OUTPUT_DIR / f"run_video_{timestamp}"
            run_dir.mkdir(parents=True, exist_ok=True)

        logger.info("=" * 65)
        logger.info("🎬 [Standard YouTube Video] Starting 16:9 Landscape Video Production...")
        logger.info(f"   Directory: {run_dir.name} | Topic: {topic or 'Auto-Theme'}")
        logger.info("=" * 65)

        # 1. Script & Metadata
        script_file = run_dir / "long_video_script.json"
        if script_file.exists():
            logger.info("⚡ Checkpoint found: Loading existing long_video_script.json...")
            with open(script_file, "r", encoding="utf-8") as f:
                script = LongVideoScript(**json.load(f))
            report(10, f"Resumed standard video script: '{script.title[:40]}...'", 6)
        else:
            report(5, "Generating 16:9 masterclass video script with Gemini 4 Argon...", 6)
            script = self.script_gen.generate_long_video_script(topic=topic, callback=lambda m: report(5, m, 6))
            with open(script_file, "w", encoding="utf-8") as f:
                json.dump(script.model_dump(), f, indent=2)
            report(15, f"Standard video script generated: '{script.title[:40]}...'", 6)

        logger.info(f"✨ Standard Video Title: {script.title}")
        logger.info(f"📜 Total Chapters/Scenes: {len(script.scenes)}")

        # 2. Synthesize Audio for all scenes (isolated in audio_long)
        report(20, "Synthesizing voiceover narration for all chapters (Edge-TTS)...", 6)
        scene_dicts = [s.model_dump() for s in script.scenes]
        audios = self.audio_gen.generate_scene_audios(
            scene_dicts,
            run_dir,
            lang="en",
            subfolder="audio_long",
            orientation="landscape",
        )
        report(40, f"Voiceover synthesized for {len(audios)} chapters", 6)

        # 3. Generate 16:9 Landscape Visuals
        report(45, "Generating 16:9 cinematic widescreen visual scenes...", 6)
        image_paths = self.image_gen.generate_all_scenes(
            scenes=scene_dicts,
            run_dir=run_dir,
            aspect_ratio="16:9",
            width=1920,
            height=1080,
            callback=lambda c, t, m: report(45 + int((c / t) * 20), m, 6),
        )
        for i, sc in enumerate(audios):
            sc["image_path"] = image_paths[i]
        report(65, "All 16:9 visual scenes ready", 6)

        # 4. Generate High-Converting 16:9 Custom Thumbnail
        report(68, "Generating high-CTR 16:9 custom thumbnail...", 6)
        thumbnail_path = run_dir / "thumbnail.jpg"
        if thumbnail_path.exists() and thumbnail_path.stat().st_size > 5000:
            logger.info("⚡ Checkpoint found: Reusing existing thumbnail.jpg")
        else:
            self.thumbnail_gen.generate_thumbnail(
                headline=script.thumbnail_headline,
                visual_prompt=script.thumbnail_visual_prompt,
                output_path=thumbnail_path,
            )
        report(75, f"Custom thumbnail ready: {thumbnail_path.name}", 6)

        # 5. Assemble 1080p Landscape Video with FFmpeg
        final_video_path = run_dir / "final_video.mp4"
        if final_video_path.exists() and final_video_path.stat().st_size > 100000:
            logger.info(f"⚡ Checkpoint found: Reusing existing final_video.mp4")
            report(88, "Reused existing assembled 16:9 video!", 6)
        else:
            report(78, "Assembling 16:9 widescreen video with dynamic captions...", 6)
            music_files = list(config.MUSIC_DIR.glob("*.mp3")) + list(config.MUSIC_DIR.glob("*.wav"))
            bg_music = music_files[0] if music_files else None
            self.video_assembler.assemble_video(
                scene_data=audios,
                output_video_path=final_video_path,
                background_music_path=bg_music,
                lang="en",
                orientation="landscape",
                callback=lambda c, t, m: report(78 + int((c / t) * 10), m, 6),
            )
            report(88, "16:9 widescreen video assembled successfully!", 6)

        # 6. Upload to YouTube with Custom Thumbnail & Chapters
        upload_result = None
        has_valid_auth = not dry_run and self.uploader.auth.is_token_valid()

        if has_valid_auth:
            report(90, "Uploading standard 16:9 video + custom thumbnail to YouTube...", 6)
            logger.info(f"📤 Uploading standard video to YouTube: '{script.title}'...")
            try:
                upload_result = self.uploader.upload_video(
                    video_path=final_video_path,
                    title=script.title,
                    description=script.description,
                    tags=script.tags,
                    category_id=script.category_id,
                    pinned_comment=script.pinned_comment,
                    thumbnail_path=thumbnail_path,
                )
                logger.info(f"🎉 Standard Video Live on YouTube: {upload_result['video_url']}")
                report(100, f"Standard Video Uploaded! URL: {upload_result['video_url']}", 6)
            except Exception as e:
                logger.warning(f"⚠️ Standard video upload deferred: {e}")
                self.self_healer.queue_for_later(final_video_path, script.model_dump())
                upload_result = {
                    "status": "QUEUED_LOCALLY",
                    "error": str(e),
                    "video_path": str(final_video_path.resolve()),
                    "thumbnail_path": str(thumbnail_path.resolve()),
                }
                report(100, f"Standard video saved locally (upload deferred)", 6)
        elif not dry_run:
            logger.info("ℹ️ YouTube OAuth token unauthenticated or expired. Saving video & thumbnail locally.")
            self.self_healer.queue_for_later(final_video_path, script.model_dump())
            upload_result = {
                "status": "SAVED_LOCALLY_NEEDS_AUTH",
                "video_path": str(final_video_path.resolve()),
                "thumbnail_path": str(thumbnail_path.resolve()),
            }
            report(100, f"Saved locally: {final_video_path.name} (OAuth needed)", 6)
        else:
            upload_result = {
                "status": "DRY_RUN",
                "video_path": str(final_video_path.resolve()),
                "thumbnail_path": str(thumbnail_path.resolve()),
            }
            report(100, f"Dry run complete! Video saved: {final_video_path.name}", 6)

        # Save / update summary.json
        sum_file = run_dir / "summary.json"
        sdata = {}
        if sum_file.exists():
            try:
                sdata = json.loads(sum_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        sdata["youtube_video"] = {
            "title": script.title,
            "description": script.description,
            "tags": script.tags,
            "video_path": str(final_video_path.resolve()),
            "thumbnail_path": str(thumbnail_path.resolve()),
            "upload_result": upload_result,
        }
        sum_file.write_text(json.dumps(sdata, indent=2), encoding="utf-8")

        # Desktop notification
        send_desktop_notification(
            title="🎬 Standard YouTube Video Ready!",
            message=f"{script.title}\nThumbnail: {thumbnail_path.name}",
        )

        return sdata["youtube_video"]


    def run(
        self,
        niche: Optional[str] = None,
        topic: Optional[str] = None,
        dry_run: bool = False,
        content_type: str = "both",
        resume: bool = True,
        progress_callback: Optional[Callable[[int, str, int], None]] = None,
    ) -> dict:
        def report(pct: int, msg: str, step: int):
            if progress_callback:
                progress_callback(pct, msg, step)

        # -------------------------------------------------------------
        # STEP 0: Autonomous Self-Healing Pre-flight & Growth Sync
        # -------------------------------------------------------------
        report(2, "Self-Healing audit: checking tokens, permissions & directories...", 1)
        self.self_healer.auto_repair()
        self.growth_engine.evolve_channel_strategy()

        # Check for resumable incomplete run
        resumable_run = self.find_latest_resumable_run() if (resume and not topic) else None
        if resumable_run:
            run_dir = resumable_run
            timestamp = run_dir.name.replace("run_", "")
            logger.info(f"🔄 RESUMING INCOMPLETE PIPELINE from checkpoint: {run_dir.name}")
            report(3, f"Resuming pipeline from checkpoint: {run_dir.name}...", 1)
        else:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = config.OUTPUT_DIR / f"run_{timestamp}"
            run_dir.mkdir(parents=True, exist_ok=True)

        # Bypass straight to standard 16:9 video if video-only requested
        if content_type in ("videos", "video"):
            logger.info("=" * 60)
            logger.info("🎬 [Mode: Standard Video Only] Generating 16:9 Landscape Video...")
            logger.info("=" * 60)
            report(10, "Generating Standard YouTube Landscape Video (16:9)...", 6)
            video_result = self.generate_standard_video(
                topic=topic,
                run_dir=run_dir,
                dry_run=dry_run,
                progress_callback=progress_callback,
            )
            summary = {
                "timestamp": timestamp,
                "topic": topic,
                "youtube_video": video_result,
                "dry_run": dry_run,
            }
            with open(run_dir / "summary.json", "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
            report(100, "Standard YouTube Video Completed!", 6)
            return summary

        logger.info("=" * 60)
        logger.info(f"🚀 STARTING YOUTUBE AUTOMATION PIPELINE (Run: {timestamp})")
        logger.info(f"🎯 Niche: {niche or config.DEFAULT_NICHE}")
        if topic:
            logger.info(f"💡 Specific Topic: {topic}")
        logger.info(f"🧪 Dry Run Mode: {dry_run}")
        logger.info(f"📺 Content Format: {content_type.upper()}")
        logger.info("=" * 60)

        # -------------------------------------------------------------
        # STEP 1: Generate or Resume Script & Metadata
        # -------------------------------------------------------------
        script_file = run_dir / "script.json"
        from generator.script_generator import ShortsScript
        if script_file.exists():
            logger.info("⚡ Checkpoint found: Loading existing script.json...")
            with open(script_file, "r", encoding="utf-8") as f:
                script = ShortsScript(**json.load(f))
            report(20, f"Resumed script: '{script.title[:40]}...'", 1)
        else:
            report(5, "Generating viral script, SEO metadata & scene prompts...", 1)
            logger.info("📝 [Step 1/5] Generating script, metadata, and scene prompts with Gemini...")
            script = self.script_gen.generate_script(niche=niche, specific_topic=topic, callback=lambda m: report(5, m, 1))
            
            with open(script_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(script.model_dump(), indent=2))
            report(20, f"Script generated: '{script.title[:40]}...'", 1)

        logger.info(f"✨ Title: {script.title}")
        logger.info(f"📜 Scenes to generate: {len(script.scenes)}")

        # -------------------------------------------------------------
        # STEP 2: Generate Audio & Subtitles
        # -------------------------------------------------------------
        report(22, "Synthesizing voiceover & word timestamps (Edge-TTS)...", 2)
        logger.info("🎙️ [Step 2/5] Synthesizing voiceover and word timestamps...")
        scene_dicts = [s.model_dump() for s in script.scenes]
        
        def audio_sub_cb(curr: int, tot: int, msg: str):
            pct = 20 + int((curr / tot) * 20)
            report(pct, msg, 2)

        scene_audios = self.audio_gen.generate_scene_audios(
            scene_dicts,
            run_dir,
            lang="en",
            subfolder="audio",
            orientation="portrait",
            callback=audio_sub_cb,
        )
        report(40, f"Voiceover ready for all {len(scene_dicts)} scenes", 2)

        # -------------------------------------------------------------
        # STEP 3: Generate AI Visuals
        # -------------------------------------------------------------
        report(42, "Generating 9:16 vertical AI visual scenes...", 3)
        logger.info("🎨 [Step 3/5] Generating 9:16 vertical AI visual scenes...")

        def image_sub_cb(curr: int, tot: int, msg: str):
            pct = 40 + int((curr / tot) * 25)
            report(pct, msg, 3)

        image_paths = self.image_gen.generate_all_scenes(scene_dicts, run_dir, callback=image_sub_cb)

        # Combine audio & image info for each scene
        for i, scene in enumerate(scene_audios):
            scene["image_path"] = image_paths[i]
        report(65, f"All {len(image_paths)} visual scenes rendered", 3)

        # -------------------------------------------------------------
        # STEP 4: Assemble & Render Video
        # -------------------------------------------------------------
        report(68, "Composing vertical video with animated captions...", 4)
        logger.info("🎬 [Step 4/5] Composing video with animated subtitles & zoom effects...")
        final_video_path = run_dir / "final_short.mp4"
        
        if final_video_path.exists() and final_video_path.stat().st_size > 100000:
            logger.info(f"⚡ Checkpoint found: Reusing existing rendered video ({final_video_path.name})")
            report(85, "Reused existing assembled video!", 4)
        else:
            music_files = list(config.MUSIC_DIR.glob("*.mp3")) + list(config.MUSIC_DIR.glob("*.wav"))
            bg_music = music_files[0] if music_files else None
            if bg_music:
                logger.info(f"🎵 Adding background music: {bg_music.name}")

            def video_sub_cb(curr: int, tot: int, msg: str):
                pct = 65 + int((curr / tot) * 20)
                report(pct, msg, 4)

            self.video_assembler.assemble_video(
                scene_data=scene_audios,
                output_video_path=final_video_path,
                background_music_path=bg_music,
                callback=video_sub_cb,
            )
            report(85, "Video assembly complete!", 4)

        # -------------------------------------------------------------
        # STEP 5: Upload to YouTube or Save Locally
        # -------------------------------------------------------------
        upload_result = None
        if not dry_run and self.uploader.auth.is_token_valid():
            report(88, "Uploading video directly to YouTube channel...", 5)
            logger.info("📤 [Step 5/5] Uploading video to YouTube channel...")
            try:
                upload_result = self.uploader.upload_video(
                    video_path=final_video_path,
                    title=script.title,
                    description=script.description,
                    tags=script.tags,
                    category_id=script.category_id,
                    pinned_comment=script.pinned_comment,
                )
                logger.info(f"🎉 Video live at: {upload_result['video_url']}")
                report(100, f"Uploaded! URL: {upload_result['video_url']}", 5)
                # Cleanup local media files on successful upload to save disk space
                self.self_healer.cleanup_media(run_dir, final_video_path)
            except Exception as upload_err:
                logger.warning(f"⚠️ YouTube upload deferred: {upload_err}")
                from youtube.upload_healer import YouTubeUploadHealer
                diag = YouTubeUploadHealer(self.uploader).diagnose(upload_err)
                YouTubeUploadHealer(self.uploader).display_diagnosis(diag, final_video_path)
                self.self_healer.queue_for_later(final_video_path, script.model_dump())
                upload_result = {
                    "status": "QUEUED_LOCALLY",
                    "reason": diag["headline"],
                    "auto_action": diag["auto_action"],
                    "solution": diag["permanent_solution"],
                    "video_path": str(final_video_path.resolve()),
                }
                report(100, f"Saved locally: {diag['headline']}", 5)
        elif not dry_run and not self.uploader.auth.is_token_valid():
            logger.info("ℹ️ YouTube OAuth token is currently unauthenticated or expired.")
            logger.info(f"💾 Video successfully generated and saved locally: file://{final_video_path.resolve()}")
            self.self_healer.queue_for_later(final_video_path, script.model_dump())
            upload_result = {
                "status": "SAVED_LOCALLY_NEEDS_AUTH",
                "message": "Video saved locally. Run 'python3 upload_to_youtube.py' in terminal to authenticate.",
                "video_path": str(final_video_path.resolve()),
            }
            report(100, f"Saved locally: {final_video_path.name} (OAuth login needed)", 5)
        else:
            logger.info("🧪 Dry run enabled: Skipped YouTube upload. Video generated at:")
            logger.info(f"   file://{final_video_path.resolve()}")
            report(100, f"Dry run complete! Video saved: {final_video_path.name}", 5)

        # -------------------------------------------------------------
        # STEP 6: Accompanying Standard YouTube Video (16:9 Landscape)
        # -------------------------------------------------------------
        video_result = None
        if content_type in ("both", "videos", "all", "video"):
            logger.info("=" * 60)
            logger.info("🎬 Generating accompanying Standard YouTube Landscape Video (16:9)...")
            logger.info("=" * 60)
            report(90, "Generating accompanying Standard YouTube Landscape Video (16:9)...", 6)
            try:
                video_result = self.generate_standard_video(
                    topic=script.title if hasattr(script, "title") else topic,
                    run_dir=run_dir,
                    dry_run=dry_run,
                    progress_callback=progress_callback,
                )
            except Exception as vid_err:
                logger.error(f"⚠️ Error generating standard YouTube video: {vid_err}", exc_info=True)
                video_result = {"status": "FAILED", "error": str(vid_err)}

        # Record summary
        summary = {
            "timestamp": timestamp,
            "title": script.title,
            "description": script.description,
            "tags": script.tags,
            "video_path": str(final_video_path.resolve()),
            "dry_run": dry_run,
            "upload_result": upload_result,
            "youtube_video": video_result,
            "community_poll": script.community_poll.model_dump() if script.community_poll else None,
        }

        with open(run_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        # Dispatch Desktop Notification
        status_txt = "Uploaded to YouTube" if (upload_result and upload_result.get("video_url")) else "Saved to Disk"
        send_desktop_notification(
            title="🎬 YouTube Short Ready!",
            message=f"{script.title}\nStatus: {status_txt}",
        )

        logger.info("=" * 60)
        logger.info("✅ PIPELINE EXECUTION FINISHED SUCCESSFULLY!")
        logger.info("=" * 60)

        return summary

    def run_trilingual(
        self,
        topic: Optional[str] = None,
        dry_run: bool = False,
        progress_callback: Optional[Callable[[int, str, int], None]] = None,
        target_platform: str = "all",
        content_type: str = "both",
        force: bool = False,
        resume: bool = True,
    ) -> dict:
        """
        Executes single-prompt generation for English, Hindi, and Gujarati,
        synthesizes 3 native voice tracks, compiles 3 videos, and uploads all 3 to YouTube.
        Guarantees strictly 1 run per calendar day unless force=True.
        Supports full fault-tolerant checkpoint resumption across all steps.
        """
        # Check for resumable incomplete run FIRST before daily quota check
        resumable_run = self.find_latest_resumable_run(trilingual=True) if (resume and not topic) else None

        # Strict Daily 1-Run Quota Check for YouTube (only prevents creating a 2nd fresh run)
        if not resumable_run and target_platform in ("all", "youtube") and not force and not dry_run:
            if not youtube_limiter.can_run_today():
                today_str = datetime.date.today().strftime("%Y-%m-%d")
                logger.info(f"⏸️ [YouTube Agent] Daily YouTube content generation already completed for today ({today_str}). Skipping fresh run (1 run/day policy).")
                return {
                    "status": "SKIPPED",
                    "reason": "Daily YouTube run limit reached (1/1)",
                    "date": today_str
                }

        def report(pct: int, msg: str, step: int):
            if progress_callback:
                progress_callback(pct, msg, step)
        if resumable_run:
            run_dir = resumable_run
            timestamp = run_dir.name.replace("run_trilingual_", "")
            logger.info(f"🔄 RESUMING INCOMPLETE TRILINGUAL PIPELINE from checkpoint: {run_dir.name}")
            report(3, f"Resuming trilingual pipeline from checkpoint: {run_dir.name}...", 1)
        else:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = config.OUTPUT_DIR / f"run_trilingual_{timestamp}"
            run_dir.mkdir(parents=True, exist_ok=True)

        # Bypass straight to standard 16:9 video if video-only requested
        if content_type in ("videos", "video"):
            logger.info("=" * 60)
            logger.info("🎬 [Mode: Standard Video Only] Generating 16:9 Landscape Video...")
            logger.info("=" * 60)
            report(10, "Generating Standard YouTube Landscape Video (16:9)...", 6)
            video_result = self.generate_standard_video(
                topic=topic,
                run_dir=run_dir,
                dry_run=dry_run,
                progress_callback=progress_callback,
            )
            summary = {
                "timestamp": timestamp,
                "topic": topic,
                "youtube_video": video_result,
                "dry_run": dry_run,
            }
            with open(run_dir / "summary.json", "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
            report(100, "Standard YouTube Video Completed!", 6)
            return summary

        # STEP 0: Pre-flight audit
        report(2, "Self-Healing audit & diagnostics...", 1)
        self.self_healer.auto_repair()
        self.growth_engine.evolve_channel_strategy()

        logger.info("=" * 60)
        logger.info(f"🌐 STARTING TRILINGUAL PIPELINE (EN, HI, GU) (Run: {timestamp})")
        if topic:
            logger.info(f"💡 Target Pillar: {topic}")
        logger.info(f"🧪 Dry Run Mode: {dry_run}")
        logger.info(f"📺 Content Format: {content_type.upper()}")
        logger.info("=" * 60)

        # STEP 1: Generate or Resume Trilingual package
        pkg_file = run_dir / "package.json"
        if pkg_file.exists():
            logger.info("⚡ Checkpoint found: Loading existing package.json...")
            from generator.script_generator import TrilingualShortsPackage
            with open(pkg_file, "r", encoding="utf-8") as f:
                package = TrilingualShortsPackage(**json.load(f))
            report(20, "Resumed scripts: EN, HI (Devanagari), GU (Gujarati)", 1)
        else:
            report(5, "Generating Trilingual package (EN, HI, GU) in 1 prompt with Gemini...", 1)
            logger.info("📝 [Step 1/5] Generating synchronized English, Hindi & Gujarati scripts in 1 prompt...")
            package = self.script_gen.generate_trilingual_script(specific_topic=topic, callback=lambda m: report(5, m, 1))
            with open(pkg_file, "w", encoding="utf-8") as f:
                json.dump(package.model_dump(), f, indent=2)
            report(20, f"Scripts generated: EN, HI (Devanagari), GU (Gujarati)", 1)

        logger.info(f"✨ Topic: {package.topic}")
        logger.info(f"🇺🇸 EN Title: {package.english.title}")
        logger.info(f"🇮🇳 HI Title: {package.hindi.title}")
        logger.info(f"🇮🇳 GU Title: {package.gujarati.title}")

        # STEP 2: Synthesize Audios for all 3 languages (with scene checkpointing)
        report(25, "Synthesizing voiceovers (English, Hindi, Gujarati)...", 2)
        logger.info("🎙️ [Step 2/5] Synthesizing multilingual neural voiceovers...")
        audios = {}
        for lang_code, lang_obj in [("en", package.english), ("hi", package.hindi), ("gu", package.gujarati)]:
            scenes_dict = [s.model_dump() for s in lang_obj.scenes]
            folder = f"audio_{lang_code}" if lang_code != "en" else "audio"
            audios[lang_code] = self.audio_gen.generate_scene_audios(
                scenes_dict,
                run_dir,
                lang=lang_code,
                subfolder=folder,
                orientation="portrait",
            )
        report(45, "Voiceovers synthesized for all 3 languages", 2)

        # STEP 3: Generate 9:16 Visuals (with scene checkpointing)
        report(48, "Generating shared 9:16 vertical AI visual scenes...", 3)
        logger.info("🎨 [Step 3/5] Generating shared 9:16 vertical visual scenes...")
        scenes_for_visuals = [s.model_dump() for s in package.english.scenes]
        image_paths = self.image_gen.generate_all_scenes(scenes_for_visuals, run_dir)
        report(65, f"All {len(image_paths)} visual scenes rendered", 3)

        # STEP 4: Assemble 3 Videos with localized fonts (with clip & video checkpointing)
        report(68, "Assembling 3 localized vertical videos with animated captions...", 4)
        logger.info("🎬 [Step 4/5] Assembling 3 localized vertical video versions...")
        final_videos = {}
        music_files = list(config.MUSIC_DIR.glob("*.mp3")) + list(config.MUSIC_DIR.glob("*.wav"))
        bg_music = music_files[0] if music_files else None

        for lang_code in ["en", "hi", "gu"]:
            for i, sc in enumerate(audios[lang_code]):
                sc["image_path"] = image_paths[i]
            out_video = run_dir / f"final_short_{lang_code}.mp4"
            if out_video.exists() and out_video.stat().st_size > 50000:
                logger.info(f"⚡ Checkpoint found: Reusing assembled video {out_video.name}")
                final_videos[lang_code] = out_video
            else:
                self.video_assembler.assemble_video(
                    scene_data=audios[lang_code],
                    output_video_path=out_video,
                    background_music_path=bg_music,
                    lang=lang_code,
                )
                final_videos[lang_code] = out_video

        report(85, "All 3 video language versions assembled!", 4)

        pkg_dict = {
            "en": package.english.model_dump(),
            "hi": package.hindi.model_dump(),
            "gu": package.gujarati.model_dump(),
        }

        # -------------------------------------------------------------
        # STEP 5.1: YouTube Sequential Upload (EN -> HI -> GU)
        # -------------------------------------------------------------
        upload_results = {}
        sum_file = run_dir / "summary.json"
        if sum_file.exists():
            try:
                sdata = json.loads(sum_file.read_text(encoding="utf-8"))
                if isinstance(sdata.get("youtube"), dict):
                    upload_results = sdata["youtube"].copy()
            except Exception:
                pass

        if target_platform in ("all", "youtube"):
            logger.info("=" * 60)
            logger.info("📤 [Step 5.1] 🔴 YouTube Sequential Upload (English -> Hindi -> Gujarati)...")
            logger.info("=" * 60)

            # Pre-flight token check: avoid repeated upload failure exceptions and desktop popups
            has_valid_auth = not dry_run and self.uploader.auth.is_token_valid()
            if not dry_run and not has_valid_auth:
                logger.info("ℹ️ [YouTube Agent] YouTube OAuth token is currently unauthenticated or expired.")
                logger.info(f"💾 [YouTube Agent] All 3 localized Shorts are safely preserved in {run_dir.name}.")
                logger.info("🔑 To publish to YouTube channel, authenticate once in terminal: python3 upload_to_youtube.py")

            lang_packages = [
                ("en", "English", "🇺🇸", package.english),
                ("hi", "Hindi", "🇮🇳", package.hindi),
                ("gu", "Gujarati", "🇮🇳", package.gujarati),
            ]
            total_langs = len(lang_packages)

            for idx, (lang_code, lang_name, flag, lang_pkg) in enumerate(lang_packages, 1):
                vid_path = final_videos[lang_code]
                pct = 85 + int((idx / total_langs) * 5)

                # Checkpoint check: if already uploaded to YouTube, skip!
                if upload_results.get(lang_code, {}).get("video_url"):
                    logger.info(f"⚡ Checkpoint found: {flag} {lang_name} already uploaded live: {upload_results[lang_code]['video_url']}")
                    report(pct, f"✓ YouTube {lang_name} (Checkpoint): {upload_results[lang_code]['video_url']}", 5)
                    continue

                report(pct, f"[{idx}/3] Uploading {flag} {lang_name} Short to YouTube channel...", 5)
                logger.info(f"🔴 [{idx}/3] Uploading {flag} {lang_name} to YouTube: '{lang_pkg.title}'...")

                if has_valid_auth:
                    try:
                        res = self.uploader.upload_video(
                            video_path=vid_path,
                            title=lang_pkg.title,
                            description=lang_pkg.description + f"\n\n{lang_pkg.hashtags}",
                            tags=lang_pkg.tags,
                            category_id=config.DEFAULT_CATEGORY_ID,
                        )
                        upload_results[lang_code] = res
                        logger.info(f"🎉 [YOUTUBE {lang_name.upper()} LIVE]: {res['video_url']}")
                        report(pct, f"✓ YouTube {lang_name}: {res['video_url']}", 5)

                        # Immediately checkpoint summary.json after each language upload
                        try:
                            sdata = {
                                "timestamp": timestamp,
                                "topic": package.topic,
                                "title": package.english.title,
                                "videos": {k: str(v.resolve()) for k, v in final_videos.items()},
                                "youtube": upload_results,
                                "dry_run": dry_run,
                            }
                            sum_file.write_text(json.dumps(sdata, indent=2), encoding="utf-8")
                        except Exception:
                            pass

                        if idx < total_langs:
                            time.sleep(4)

                    except Exception as e:
                        logger.warning(f"⚠️ [{lang_name}] YouTube upload deferred: {e}")
                        from youtube.upload_healer import YouTubeUploadHealer
                        diag = YouTubeUploadHealer(self.uploader).diagnose(e)
                        YouTubeUploadHealer(self.uploader).display_diagnosis(diag, vid_path)
                        self.self_healer.queue_for_later(vid_path, lang_pkg.model_dump())
                        upload_results[lang_code] = {
                            "status": "QUEUED_LOCALLY",
                            "reason": diag["headline"],
                            "auto_action": diag["auto_action"],
                            "solution": diag["permanent_solution"],
                            "video_path": str(vid_path.resolve()),
                        }
                        report(pct, f"⚠️ YouTube {lang_name} deferred: {diag['headline'][:40]}", 5)
                elif not dry_run:
                    self.self_healer.queue_for_later(vid_path, lang_pkg.model_dump())
                    upload_results[lang_code] = {
                        "status": "SAVED_LOCALLY_NEEDS_AUTH",
                        "video_path": str(vid_path.resolve()),
                    }
                else:
                    upload_results[lang_code] = {
                        "status": "DRY_RUN",
                        "video_path": str(vid_path.resolve()),
                    }

        else:
            logger.info("⏩ [Step 5.1] Skipping YouTube upload (Target: Social only)")

        # -------------------------------------------------------------
        # STEP 5.1.5: Standard YouTube Landscape Video (16:9, 1080p)
        # -------------------------------------------------------------
        video_result = None
        if target_platform in ("all", "youtube") and content_type in ("both", "videos", "all", "video"):
            logger.info("=" * 60)
            logger.info("🎬 [Step 5.1.5] Generating Standard YouTube Landscape Video (16:9)...")
            logger.info("=" * 60)
            report(88, "Generating Standard YouTube Landscape Video (16:9)...", 6)
            try:
                video_result = self.generate_standard_video(
                    topic=package.topic,
                    run_dir=run_dir,
                    dry_run=dry_run,
                    progress_callback=progress_callback,
                )
            except Exception as vid_err:
                logger.error(f"⚠️ Error generating standard YouTube video: {vid_err}", exc_info=True)
                video_result = {"status": "FAILED", "error": str(vid_err)}

        # -------------------------------------------------------------
        # STEP 5.2 - 5.4: Social Media Sequential Uploads (IG, FB, WA)
        # -------------------------------------------------------------
        ig_results = {}
        fb_results = {}
        wa_results = {}

        if target_platform in ("all", "social"):
            logger.info("=" * 60)
            logger.info("📤 [Step 5.2] 📸 Instagram Sequential Upload (Stories & Reels)...")
            logger.info("=" * 60)
            report(92, "Publishing to Instagram (Stories & Reels)...", 5)
            ig_results = self.story_publisher.upload_instagram_sequential(
                videos=final_videos,
                package_data=pkg_dict,
                dry_run=dry_run,
                progress_callback=lambda msg: report(93, msg, 5),
            )

            logger.info("=" * 60)
            logger.info("📤 [Step 5.3] 📘 Facebook Sequential Upload (Stories & Page Videos)...")
            logger.info("=" * 60)
            report(95, "Publishing to Facebook Page & Stories...", 5)
            fb_results = self.story_publisher.upload_facebook_sequential(
                videos=final_videos,
                package_data=pkg_dict,
                dry_run=dry_run,
                progress_callback=lambda msg: report(96, msg, 5),
            )

            logger.info("=" * 60)
            logger.info("📤 [Step 5.4] 💬 WhatsApp Status & Story Publishing...")
            logger.info("=" * 60)
            report(98, "Dispatching WhatsApp Status & Stories...", 5)
            wa_results = self.story_publisher.upload_whatsapp_sequential(
                videos=final_videos,
                package_data=pkg_dict,
                dry_run=dry_run,
                progress_callback=lambda msg: report(99, msg, 5),
            )
        else:
            logger.info("⏩ [Step 5.2-5.4] Skipping Social uploads (Target: YouTube only)")

        # Keep final generated videos safely preserved in run_dir for archival and pending retries
        has_std_vid = bool(video_result and video_result.get("status") != "FAILED")
        finished_msg = (
            "YouTube Shorts & Standard 16:9 Video Published!"
            if (target_platform == "youtube" and has_std_vid)
            else "YouTube Shorts Published!"
            if target_platform == "youtube"
            else "Social Stories Published (IG, FB, WA)!"
            if target_platform == "social"
            else "All Platforms Published (YouTube Shorts + 16:9 Video + Social Stories)!"
        )
        report(100, finished_msg, 5)

        summary = {
            "timestamp": timestamp,
            "topic": package.topic,
            "theme_category": package.theme_category,
            "title": package.english.title,
            "videos": {k: str(v.resolve()) for k, v in final_videos.items()},
            "youtube": upload_results,
            "youtube_video": video_result,
            "instagram": ig_results,
            "facebook": fb_results,
            "whatsapp": wa_results,
            "dry_run": dry_run,
            "community_poll": package.community_poll.model_dump() if package.community_poll else None,
        }

        with open(run_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        # Record successful daily run in YouTubeDailyLimiter
        if target_platform in ("all", "youtube") and not dry_run:
            try:
                youtube_limiter.record_run(
                    run_dir=run_dir,
                    topic=package.topic,
                    videos={k: str(v.resolve()) for k, v in final_videos.items()},
                    details={
                        "theme_category": package.theme_category,
                        "titles": {
                            "en": package.english.title,
                            "hi": package.hindi.title,
                            "gu": package.gujarati.title
                        }
                    }
                )
            except Exception as e:
                logger.debug(f"Could not record YouTube daily run: {e}")

        # Dispatch Desktop Notification for Trilingual Batch
        send_desktop_notification(
            title="🌐 Multi-Platform Broadcast Complete!",
            message=f"Topic: {package.topic}\nYouTube + Instagram + Facebook + WhatsApp Ready!",
        )

        logger.info("=" * 60)
        logger.info("✅ MULTI-PLATFORM STEP-BY-STEP PUBLISHING FINISHED!")
        logger.info("=" * 60)

        return summary


def main():
    parser = argparse.ArgumentParser(description="Automated YouTube Content Creator Agent")
    parser.add_argument("--run-now", action="store_true", help="Execute the complete pipeline immediately")
    parser.add_argument("--dry-run", action="store_true", help="Generate video without uploading to YouTube")
    parser.add_argument("--trilingual", action="store_true", help="Generate 3 videos (English, Hindi, Gujarati) in 1 prompt and upload all 3")
    parser.add_argument("--platform", choices=["all", "youtube", "social"], default="all", help="Target: 'youtube' (YouTube only), 'social' (IG, FB, WA only), or 'all'")
    parser.add_argument("--topic", type=str, default=None, help="Specify a custom video topic")
    parser.add_argument("--niche", type=str, default=None, help="Specify a custom channel niche")
    parser.add_argument("--auth", action="store_true", help="Authenticate YouTube OAuth2 credentials")
    parser.add_argument("--schedule", action="store_true", help="Run the automated daily scheduler daemon")
    parser.add_argument("--self-heal", action="store_true", help="Run full self-diagnostics and auto-repair")
    parser.add_argument("--growth", action="store_true", help="Display evolving channel growth analytics and memory")
    parser.add_argument("--no-resume", action="store_true", help="Force new run without resuming incomplete checkpoints")
    parser.add_argument("--force", action="store_true", help="Bypass the 1-run-per-day rate limiter")
    parser.add_argument("--model", type=str, default=None, help="Explicitly specify or prioritize Gemini AI model (e.g. 'gemini-4-argon', 'gemini-3.8-flash')")
    parser.add_argument("--content-type", choices=["both", "shorts", "videos"], default="both", help="Content format: 'both' (Shorts + Standard 16:9 Video), 'shorts' (Shorts only), 'videos' (Standard 16:9 Video only)")
    parser.add_argument("--shorts-only", action="store_true", help="Generate and upload YouTube Shorts only (skip standard video)")
    parser.add_argument("--video-only", action="store_true", help="Generate and upload Standard 16:9 YouTube Video only (skip shorts)")

    args = parser.parse_args()

    if args.model:
        config.set_active_model(args.model)

    if args.self_heal:
        healer = SelfHealer()
        print("\n" + "=" * 65)
        print("🛡️  RUNNING AUTONOMOUS SELF-DIAGNOSTICS & REPAIR")
        print("=" * 65)
        report = healer.run_health_audit()
        for k, v in report.items():
            status_icon = "✅" if v.get("status") == "HEALTHY" else "⚠️" if v.get("status") == "WARNING" else "ℹ️"
            print(f"{status_icon} [{k.upper():14s}] : {v.get('message')}")
        
        repairs = healer.auto_repair()
        print("\n🔧 Auto-Repair Actions:")
        if repairs:
            for r in repairs:
                print(f"  • {r}")
        else:
            print("  • All system components, permissions, and directories are in peak state.")
        print("=" * 65 + "\n")
        return

    if args.growth:
        growth = GrowthEngine()
        mem = growth.evolve_channel_strategy()
        print("\n" + "=" * 65)
        print("📈 AUTONOMOUS CHANNEL GROWTH INTELLIGENCE MEMORY")
        print("=" * 65)
        print("🎯 Best Performing Hook Styles:")
        for h in mem.get("best_performing_hook_styles", []):
            print(f"  • {h}")
        print("\n🔥 Peak Engagement Themes:")
        for t in mem.get("peak_engagement_themes", []):
            print(f"  • {t}")
        print("\n⏱️ Key Retention Rules:")
        for r in mem.get("key_retention_rules", []):
            print(f"  • {r}")
        print("=" * 65 + "\n")
        return

    if args.auth:
        auth = YouTubeAuth()
        try:
            ch_info = auth.verify_channel()
            print("\n" + "=" * 60)
            print("🎉 YOUTUBE OAUTH 2.0 AUTHENTICATION SUCCESSFUL!")
            print("=" * 60)
            print(f"📺 Channel Title : {ch_info['title']}")
            print(f"🔗 Channel URL   : https://youtube.com/{ch_info.get('custom_url', '')}")
            print(f"👥 Subscribers   : {ch_info['subscribers']}")
            print(f"🎬 Total Videos  : {ch_info['videos']}")
            print(f"🔑 Token Cached  : {config.YOUTUBE_TOKEN_FILE}")
            print("=" * 60)
            print("✨ The agent is now authorized for autonomous public uploads!\n")
        except Exception as e:
            print(f"✅ Authentication completed, but channel info query had notice: {e}")
            print(f"Token saved to: {config.YOUTUBE_TOKEN_FILE}")
        return

    if args.schedule:
        from scheduler import run_daily_scheduler
        run_daily_scheduler()
        return

    content_type = "both"
    if args.shorts_only:
        content_type = "shorts"
    elif args.video_only:
        content_type = "videos"
    elif args.content_type:
        content_type = args.content_type

    agent = YouTubeAgent(model=args.model)

    if args.run_now and not args.trilingual:
        agent.run(
            topic=args.topic,
            niche=args.niche,
            dry_run=args.dry_run,
            content_type=content_type,
            resume=not args.no_resume,
        )
    else:
        # Run trilingual with specified target platform and content type
        agent.run_trilingual(
            topic=args.topic,
            dry_run=args.dry_run,
            target_platform=args.platform,
            content_type=content_type,
            force=args.force,
            resume=not args.no_resume,
        )


if __name__ == "__main__":
    main()
