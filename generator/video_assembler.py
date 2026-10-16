import logging
import math
import os
import subprocess
from pathlib import Path
from typing import List, Optional
import imageio_ffmpeg

import config

logger = logging.getLogger(__name__)


def render_sign_badge(
    text: str,
    proper_sign: str = "",
    lang: str = "en",
    output_path: Optional[Path] = None,
) -> Optional[Path]:
    """
    Renders an authoritative, high-contrast signboard graphic badge (PNG with transparency)
    to be overlaid on the upper third of the video.
    """
    if not text or not text.strip():
        return None

    try:
        from PIL import Image, ImageDraw, ImageFont

        badge_text = text.strip()
        if badge_text.startswith("[") and badge_text.endswith("]"):
            badge_text = badge_text[1:-1].strip()

        # Strip emoji symbols to prevent tofu box glyphs in standard text fonts
        import re
        badge_text = re.sub(r"[\U00010000-\U0010ffff]", "", badge_text)
        badge_text = re.sub(r"[\u2600-\u27bf]", "", badge_text).strip()

        if not badge_text:
            return None

        # Determine font based on language
        font_paths = {
            "gu": [
                "/usr/share/fonts/truetype/noto/NotoSansGujarati-Bold.ttf",
                "/usr/share/fonts/truetype/noto/NotoSansGujarati-Regular.ttf",
            ],
            "hi": [
                "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
                "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
            ],
            "en": [
                "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ],
        }
        candidates = font_paths.get(lang.lower(), font_paths["en"])
        font = None
        for p in candidates:
            if os.path.exists(p):
                try:
                    font = ImageFont.truetype(p, 46)
                    break
                except Exception:
                    pass
        if font is None:
            font = ImageFont.load_default()

        # Measure text dimensions
        dummy_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy_img)
        bbox = draw.textbbox((0, 0), badge_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad_x = 44
        pad_y = 26
        badge_w = min(960, max(400, text_w + pad_x * 2))
        badge_h = max(110, text_h + pad_y * 2)

        img = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Border color matching sign urgency/theme
        combined_meta = f"{badge_text} {proper_sign}".lower()
        if any(w in combined_meta for w in ["stop", "🛑", "danger", "don't", "dont", "રુક", "રોકો"]):
            border_color = (255, 59, 48, 255)      # Red
        elif any(w in combined_meta for w in ["rule", "1", "☝", "નિયમ", "નંબર"]):
            border_color = (255, 215, 0, 255)     # Gold / Amber
        elif any(w in combined_meta for w in ["focus", "target", "🎯", "ધ્યાન", "લક્ષ્ય"]):
            border_color = (57, 255, 20, 255)     # Neon Green
        else:
            border_color = (0, 229, 255, 255)     # Cyan

        bg_color = (12, 18, 28, 235)              # Deep navy translucent
        text_color = (255, 255, 255, 255)

        # Draw rounded rectangle
        draw.rounded_rectangle(
            [(3, 3), (badge_w - 3, badge_h - 3)],
            radius=22,
            fill=bg_color,
            outline=border_color,
            width=4,
        )

        # Draw centered text
        tx = (badge_w - text_w) / 2
        ty = (badge_h - text_h) / 2 - bbox[1]
        draw.text((tx, ty), badge_text, font=font, fill=text_color)

        if output_path is None:
            output_path = Path(f"/tmp/badge_{abs(hash(badge_text))}.png")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")
        return output_path
    except Exception as e:
        logger.warning(f"Could not render sign badge: {e}")
        return None


def get_ffmpeg_binary() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


class VideoAssembler:
    def __init__(self, font_path: Optional[Path] = None):
        self.ffmpeg_bin = get_ffmpeg_binary()
        self.font_path = font_path or config.DEFAULT_FONT_PATH

    def render_scene_ffmpeg(
        self,
        image_path: Path,
        audio_path: Path,
        srt_path: Path,
        output_scene_mp4: Path,
        lang: str = "en",
        ass_path: Optional[Path] = None,
        sign_badge_path: Optional[Path] = None,
        duration: Optional[float] = None,
        scene_idx: int = 0,
        orientation: str = "portrait",
    ) -> Path:
        """
        Renders a single scene using direct FFmpeg hardware-accelerated processing.
        Applies alternating cinematic Ken Burns camera trajectories, super-resolution pre-scaling
        (to eliminate pixel jitter), filmic color grading, optical lens vignette, 35mm organic film grain,
        authoritative signboard badge overlay, and dynamic word-by-word highlighted captions.
        Supports both portrait 9:16 (Shorts) and landscape 16:9 (Standard Videos).
        """
        output_scene_mp4.parent.mkdir(parents=True, exist_ok=True)

        is_landscape = (orientation == "landscape")
        target_w = 1920 if is_landscape else config.VIDEO_WIDTH
        target_h = 1080 if is_landscape else config.VIDEO_HEIGHT
        pre_scale = "3840:2160" if is_landscape else "2160:3840"
        sub_margin_v = 80 if is_landscape else 200

        if duration is None or duration <= 0:
            try:
                from moviepy.editor import AudioFileClip
                with AudioFileClip(str(audio_path)) as clip:
                    duration = clip.duration
            except Exception:
                duration = 5.0

        d_frames = max(30, int((duration + 0.5) * 30))

        # 4 alternating camera trajectories per scene:
        # Move 0: Smooth Cinematic Push-In (direct focal engagement)
        # Move 1: Subtle Horizontal Dolly Pan (left-to-right cinematic slider)
        # Move 2: Smooth Slow Pull-Back / Reveal (expansive breathing space)
        # Move 3: Subtle Diagonal Drift (dynamic rising camera)
        camera_pattern = scene_idx % 4
        if camera_pattern == 0:
            zoom_expr = f"z='min(zoom+0.0008,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        elif camera_pattern == 1:
            zoom_expr = f"z='1.08':x='(iw-iw/zoom)*(on/{d_frames})':y='ih/2-(ih/zoom/2)'"
        elif camera_pattern == 2:
            zoom_expr = f"z='if(eq(on,1),1.10,max(zoom-0.0008,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        else:
            zoom_expr = f"z='min(zoom+0.0007,1.10)':x='(iw/2-(iw/zoom/2))+(iw*0.02)*(on/{d_frames})':y='(ih/2-(ih/zoom/2))-(ih*0.03)*(on/{d_frames})'"

        zoom_filter = (
            f"scale={pre_scale},"
            f"zoompan={zoom_expr}:d={d_frames}:s={target_w}x{target_h}:fps=30,"
            f"eq=contrast=1.06:brightness=0.01:saturation=1.08,"
            f"vignette=PI/5:mode=backward,"
            f"noise=c1s=3:c0f=u+t"
        )

        has_badge = sign_badge_path and sign_badge_path.exists()
        working_dir = ass_path.parent if (ass_path and ass_path.exists()) else srt_path.parent

        if has_badge:
            filter_complex = f"[0:v]{zoom_filter}[zoomed];[zoomed][2:v]overlay=(W-w)/2:150[badged];"
            if ass_path and ass_path.exists():
                filter_complex += f"[badged]ass='{ass_path.name}'[v]"
            else:
                font_name = "Noto Sans Gujarati" if lang == "gu" else "Noto Sans Devanagari" if lang == "hi" else "Noto Sans"
                filter_complex += (
                    f"[badged]subtitles='{srt_path.name}':force_style='FontName={font_name},FontSize=24,"
                    f"PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=2,Alignment=2,MarginV={sub_margin_v},Bold=1'[v]"
                )
        else:
            filter_complex = f"[0:v]{zoom_filter}[zoomed];"
            if ass_path and ass_path.exists():
                filter_complex += f"[zoomed]ass='{ass_path.name}'[v]"
            else:
                font_name = "Noto Sans Gujarati" if lang == "gu" else "Noto Sans Devanagari" if lang == "hi" else "Noto Sans"
                filter_complex += (
                    f"[zoomed]subtitles='{srt_path.name}':force_style='FontName={font_name},FontSize=24,"
                    f"PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=2,Alignment=2,MarginV={sub_margin_v},Bold=1'[v]"
                )

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-loop", "1",
            "-i", str(image_path.resolve()),
            "-i", str(audio_path.resolve()),
        ]
        if has_badge:
            cmd.extend(["-i", str(sign_badge_path.resolve())])

        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(output_scene_mp4.resolve()),
        ])

        logger.info(f"Rendering scene clip -> {output_scene_mp4.name} ({orientation.upper()} {target_w}x{target_h})")
        result = subprocess.run(
            cmd,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            logger.warning(f"Kinetic render fallback for {output_scene_mp4.name}: {result.stderr[-200:]}")
            # Fallback without zoompan/badge if error occurs
            cmd_fallback = [
                self.ffmpeg_bin,
                "-y",
                "-loop", "1",
                "-i", str(image_path.resolve()),
                "-i", str(audio_path.resolve()),
                "-vf", f"scale={target_w}:{target_h}",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-shortest",
                str(output_scene_mp4.resolve()),
            ]
            subprocess.run(
                cmd_fallback,
                cwd=working_dir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        return output_scene_mp4

    def assemble_video(
        self,
        scene_data: List[dict],
        output_video_path: Path,
        background_music_path: Optional[Path] = None,
        lang: str = "en",
        orientation: str = "portrait",
        callback=None,
    ) -> Path:
        """
        Blazing-fast FFmpeg video compilation with Speaking Push-in Zoom, Sign Badges, Sidechain Audio Ducking & Word Highlight Subtitles.
        Supports both portrait (9:16 Shorts) and landscape (16:9 Standard Videos).
        """
        output_video_path.parent.mkdir(parents=True, exist_ok=True)
        subprefix = f"temp_scenes_{orientation}_{lang}" if lang != "en" else f"temp_scenes_{orientation}"
        temp_dir = output_video_path.parent / subprefix
        temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"⚡ Assembling {len(scene_data)} scenes using direct FFmpeg engine ({orientation.upper()}, lang={lang})...")

        scene_mp4_files = []
        total_scenes = len(scene_data)
        for i, scene in enumerate(scene_data):
            img_path = scene["image_path"]
            aud_path = scene["audio_path"]
            srt_path = scene["subtitle_path"]
            ass_path = scene.get("ass_path")
            duration = scene.get("duration")
            sign_badge_text = scene.get("sign_badge") or ""
            proper_sign = scene.get("proper_sign") or ""

            out_mp4 = temp_dir / f"scene_{i + 1:02d}.mp4"
            if out_mp4.exists() and out_mp4.stat().st_size > 10000:
                logger.info(f"⚡ Checkpoint found: Reusing rendered clip {out_mp4.name}")
                if callback:
                    callback(i + 1, total_scenes, f"Reused rendered clip {i + 1}/{total_scenes}")
                scene_mp4_files.append(out_mp4)
                continue

            if callback:
                callback(i + 1, total_scenes, f"Rendering video scene {i + 1}/{total_scenes} ({orientation.upper()}, {lang.upper()})")

            badge_png = None
            if sign_badge_text and orientation == "portrait":
                badge_file = temp_dir / f"badge_{i + 1:02d}.png"
                badge_png = render_sign_badge(
                    text=sign_badge_text,
                    proper_sign=proper_sign,
                    lang=lang,
                    output_path=badge_file,
                )

            self.render_scene_ffmpeg(
                image_path=img_path,
                audio_path=aud_path,
                srt_path=srt_path,
                output_scene_mp4=out_mp4,
                lang=lang,
                ass_path=ass_path,
                sign_badge_path=badge_png,
                duration=duration,
                scene_idx=i,
                orientation=orientation,
            )
            scene_mp4_files.append(out_mp4)

        # Create concat list
        concat_list_file = temp_dir / "concat_list.txt"
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for mp4 in scene_mp4_files:
                f.write(f"file '{mp4.resolve()}'\n")

        # Concat video clips
        raw_concat_mp4 = temp_dir / "raw_concat.mp4"
        concat_cmd = [
            self.ffmpeg_bin,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_file),
            "-c", "copy",
            str(raw_concat_mp4),
        ]
        subprocess.run(concat_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Select background music (prefer custom or default stoic ambient track)
        bgm_path = background_music_path
        if not bgm_path or not bgm_path.exists():
            default_bgm = config.MUSIC_DIR / "stoic_ambient_focus.mp3"
            if default_bgm.exists():
                bgm_path = default_bgm

        # Mix background music with Sidechain Audio Ducking if available
        if bgm_path and bgm_path.exists():
            try:
                logger.info(f"🎵 Applying Sidechain Audio Ducking with {bgm_path.name}...")
                ducking_filter = (
                    "[1:a]volume=0.22[bgm];"
                    "[0:a]asplit[speech_main][speech_sc];"
                    "[bgm][speech_sc]sidechaincompress=threshold=0.03:ratio=5:attack=20:release=400[ducked_bgm];"
                    "[speech_main][ducked_bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                )
                mix_cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-i", str(raw_concat_mp4),
                    "-stream_loop", "-1",
                    "-i", str(bgm_path),
                    "-filter_complex", ducking_filter,
                    "-map", "0:v",
                    "-map", "[aout]",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    str(output_video_path),
                ]
                subprocess.run(mix_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logger.info("✨ Cinematic auto-ducked audio mix complete.")
            except Exception as e:
                logger.warning(f"Could not apply auto-ducking ({e}). Using raw video.")
                import shutil
                shutil.copyfile(raw_concat_mp4, output_video_path)
        else:
            import shutil
            shutil.copyfile(raw_concat_mp4, output_video_path)

        # Cleanup temp directory
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        file_size_mb = output_video_path.stat().st_size / (1024 * 1024) if output_video_path.exists() else 0
        logger.info(f"🎉 Final video created successfully! Path: {output_video_path} (Size: {file_size_mb:.2f} MB)")
        return output_video_path
