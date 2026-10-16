import asyncio
import logging
import math
import time
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Callable
import edge_tts
from gtts import gTTS
from moviepy.editor import AudioFileClip

import config
from growth.network_guard import NetworkGuard

logger = logging.getLogger(__name__)


def create_word_highlight_ass(text: str, duration: float, output_ass: Path, lang: str = "en") -> None:
    """
    Generates dynamic word-by-word karaoke-style ASS subtitles (MrBeast / Alex Hormozi style)
    where the currently spoken word glows in bright yellow while other words remain white.
    """
    font_name = "Noto Sans Gujarati" if lang == "gu" else "Noto Sans Devanagari" if lang == "hi" else "Noto Sans"
    words = text.strip().split()
    if not words:
        words = ["..."]

    word_dur = duration / max(len(words), 1)
    chunk_size = 3 if len(words) > 6 else 2
    events = []

    for chunk_idx in range(0, len(words), chunk_size):
        chunk_words = words[chunk_idx : chunk_idx + chunk_size]
        for w_idx_in_chunk, active_w in enumerate(chunk_words):
            global_w_idx = chunk_idx + w_idx_in_chunk
            start_s = global_w_idx * word_dur
            end_s = min(duration, (global_w_idx + 1) * word_dur)

            line_parts = []
            for j, w in enumerate(chunk_words):
                clean_w = w.upper() if lang == "en" else w
                if j == w_idx_in_chunk:
                    # Active word in glowing yellow with subtle pop scale
                    line_parts.append(r"{\c&H0000FFFF&\fscx112\fscy112}" + clean_w + r"{\r}")
                else:
                    # Surrounding words in clean white
                    line_parts.append(r"{\c&H00FFFFFF&\fscx100\fscy100}" + clean_w + r"{\r}")

            line_str = " ".join(line_parts)

            def fmt(sec: float) -> str:
                h = int(sec // 3600)
                m = int((sec % 3600) // 60)
                s = int(sec % 60)
                cs = int((sec - int(sec)) * 100)
                return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"

            events.append(f"Dialogue: 0,{fmt(start_s)},{fmt(end_s)},Default,,0,0,0,,{line_str}")

    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.VIDEO_WIDTH}
PlayResY: {config.VIDEO_HEIGHT}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},62,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,6,3,2,40,40,340,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n"

    output_ass.write_text(ass_header, encoding="utf-8")


def create_srt_from_text(text: str, duration: float, output_srt: Path) -> None:
    """
    Creates an evenly timed synchronized SRT file from text and audio duration.
    """
    words = text.strip().split()
    if not words:
        output_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n...\n", encoding="utf-8")
        return

    # Group into 3-4 word phrases for high-retention Shorts style
    chunks = []
    chunk_size = 4
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i : i + chunk_size]))

    chunk_duration = duration / max(len(chunks), 1)

    def format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for idx, chunk in enumerate(chunks, 1):
        start_sec = (idx - 1) * chunk_duration
        end_sec = min(duration, idx * chunk_duration)
        lines.append(f"{idx}\n{format_time(start_sec)} --> {format_time(end_sec)}\n{chunk}\n")

    output_srt.write_text("\n".join(lines), encoding="utf-8")


VOICE_MAP = {
    "en": "en-US-ChristopherNeural",
    "hi": "hi-IN-MadhurNeural",
    "gu": "gu-IN-NiranjanNeural",
}

FALLBACK_VOICE_MAP = {
    "en": "en-US-GuyNeural",
    "hi": "hi-IN-SwaraNeural",
    "gu": "gu-IN-DhwaniNeural",
}

class AudioGenerator:
    def __init__(self, voice: str = config.TTS_VOICE, rate: str = config.TTS_RATE):
        self.default_voice = voice
        self.rate = rate

    def get_voice_for_lang(self, lang: str, attempt: int = 1) -> str:
        lang_lower = lang.lower()
        if attempt > 1 and lang_lower in FALLBACK_VOICE_MAP:
            return FALLBACK_VOICE_MAP[lang_lower]
        return VOICE_MAP.get(lang_lower, self.default_voice)

    async def _synthesize_edge_async(self, text: str, output_path: Path, subtitle_path: Path, voice: Optional[str] = None) -> None:
        selected_voice = voice or self.default_voice
        communicate = edge_tts.Communicate(text=text, voice=selected_voice, rate=self.rate)
        submaker = edge_tts.SubMaker()

        with open(output_path, "wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    submaker.feed(chunk)

        srt_content = submaker.get_srt()
        if srt_content and len(srt_content.strip()) > 10:
            with open(subtitle_path, "w", encoding="utf-8") as sub_file:
                sub_file.write(srt_content)
        else:
            # Fallback to calculated SRT timing based on duration
            with AudioFileClip(str(output_path)) as clip:
                duration = clip.duration
            create_srt_from_text(text, duration, subtitle_path)

    def _generate_edge_tts(self, text: str, output_path: Path, subtitle_path: Path, lang: str = "en") -> bool:
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            voice = self.get_voice_for_lang(lang, attempt=attempt)
            try:
                logger.info(f"Generating TTS audio via Edge-TTS ({voice} | lang={lang}) - attempt {attempt}...")
                asyncio.run(self._synthesize_edge_async(text, output_path, subtitle_path, voice=voice))
                if output_path.exists() and output_path.stat().st_size > 100:
                    return True
            except Exception as e:
                logger.warning(f"Edge-TTS attempt {attempt} failed: {e}")
                time.sleep(attempt * 1.5)
        return False

    def _generate_gtts(self, text: str, output_path: Path, subtitle_path: Path, lang: str = "en") -> bool:
        gtts_lang = "gu" if lang == "gu" else "hi" if lang == "hi" else "en"
        for attempt in range(1, 4):
            try:
                logger.info(f"Generating voiceover via gTTS engine (lang={gtts_lang}) - attempt {attempt}...")
                tts = gTTS(text=text, lang=gtts_lang, slow=False)
                tts.save(str(output_path))

                with AudioFileClip(str(output_path)) as clip:
                    duration = clip.duration

                create_srt_from_text(text, duration, subtitle_path)
                return True
            except Exception as e:
                logger.warning(f"gTTS attempt {attempt} failed: {e}")
                time.sleep(attempt * 2.0)
        return False

    def generate_audio(self, text: str, output_path: Path, subtitle_path: Path, lang: str = "en", callback=None) -> Tuple[Path, Path]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subtitle_path.parent.mkdir(parents=True, exist_ok=True)

        def _do_synth():
            # 1. Try Edge-TTS
            success = self._generate_edge_tts(text, output_path, subtitle_path, lang=lang)
            # 2. Fallback to gTTS
            if not success:
                success = self._generate_gtts(text, output_path, subtitle_path, lang=lang)
            if not success:
                raise ConnectionError(f"TTS network services temporarily unavailable for text: {text[:50]}...")
            return output_path, subtitle_path

        # Wrap in network guard for auto-resume if connection drops
        return NetworkGuard.resilient_call(_do_synth, callback=callback)

    def generate_scene_audios(self, scenes: List[dict], run_dir: Path, lang: str = "en", callback=None) -> List[dict]:
        audio_dir = run_dir / (f"audio_{lang}" if lang != "en" else "audio")
        audio_dir.mkdir(parents=True, exist_ok=True)

        scene_audio_results = []
        total_scenes = len(scenes)
        for idx, scene in enumerate(scenes):
            scene_num = scene.get("scene_number", idx + 1)
            text = scene.get("narration", "")

            audio_file = audio_dir / f"scene_{scene_num:02d}.mp3"
            srt_file = audio_dir / f"scene_{scene_num:02d}.srt"
            ass_file = audio_dir / f"scene_{scene_num:02d}.ass"

            # Checkpoint check: if audio & subtitle already exist and are valid, reuse directly
            if audio_file.exists() and srt_file.exists() and audio_file.stat().st_size > 100 and srt_file.stat().st_size > 5:
                logger.info(f"⚡ Checkpoint found: Reusing existing voiceover for scene {scene_num} ({lang})")
                if callback:
                    callback(idx + 1, total_scenes, f"Reused existing voice for scene {idx + 1}/{total_scenes} ({lang.upper()})")
            else:
                if callback:
                    callback(idx + 1, total_scenes, f"Synthesizing voice for scene {idx + 1}/{total_scenes} ({lang.upper()})")
                self.generate_audio(text, audio_file, srt_file, lang=lang, callback=callback)
                time.sleep(0.5)

            with AudioFileClip(str(audio_file)) as clip:
                duration = clip.duration

            # Always ensure dynamic word-highlight ASS is generated
            create_word_highlight_ass(text, duration, ass_file, lang=lang)

            scene_audio_results.append({
                "scene_number": scene_num,
                "narration": text,
                "audio_path": audio_file,
                "subtitle_path": srt_file,
                "ass_path": ass_file,
                "duration": duration,
                "speaker_entity": scene.get("speaker_entity", ""),
                "speaking_action": scene.get("speaking_action", ""),
                "proper_sign": scene.get("proper_sign", ""),
                "sign_badge": scene.get("sign_badge", ""),
            })

        return scene_audio_results
