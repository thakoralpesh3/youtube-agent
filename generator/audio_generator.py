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


def compute_cadence_timings(words: List[str], total_duration: float) -> List[dict]:
    """
    Computes natural speech cadence timings when raw neural word boundaries are unavailable.
    Accounts for phoneme length (character count) and natural punctuation pauses (commas, periods, etc.)
    instead of dividing total duration uniformly.
    """
    if not words:
        return []

    weights = []
    pause_after = []
    total_pause = 0.0

    for w in words:
        clean_len = max(1, len(w.strip(".,!?;:\"'-–—।॥")))
        weight = max(1.5, float(clean_len))
        weights.append(weight)

        pause = 0.0
        if any(w.endswith(p) for p in (".", "!", "?", "।", "॥")):
            pause = 0.50
        elif any(w.endswith(p) for p in (",", ";", ":", "-", "–", "—")):
            pause = 0.28
        pause_after.append(pause)
        total_pause += pause

    max_allowable_pause = total_duration * 0.35
    if total_pause > max_allowable_pause:
        scale = max_allowable_pause / max(total_pause, 0.001)
        pause_after = [p * scale for p in pause_after]
        total_pause = max_allowable_pause

    speech_time = max(0.4, total_duration - total_pause)
    total_weight = sum(weights) or 1.0

    timings = []
    cur_time = 0.0
    for w, wt, p in zip(words, weights, pause_after):
        w_dur = (wt / total_weight) * speech_time
        start_s = cur_time
        end_s = start_s + w_dur
        timings.append({
            "word": w,
            "start_s": start_s,
            "end_s": end_s,
        })
        cur_time = end_s + p

    if timings and timings[-1]["end_s"] > 0:
        scale_factor = total_duration / timings[-1]["end_s"]
        for it in timings:
            it["start_s"] *= scale_factor
            it["end_s"] *= scale_factor

    return timings


def create_srt_from_boundaries(
    timings: List[dict],
    duration: float,
    output_srt: Path,
    chunk_size: int = 4,
) -> None:
    """
    Creates a clean, synchronized SRT subtitle file using word timing boundaries.
    """
    if not timings:
        output_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n...\n", encoding="utf-8")
        return

    def format_time(seconds: float) -> str:
        seconds = max(0.0, seconds)
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int(round((seconds - int(seconds)) * 1000))
        if ms >= 1000:
            ms = 999
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    total = len(timings)
    idx = 1
    for i in range(0, total, chunk_size):
        chunk = timings[i : i + chunk_size]
        start_sec = chunk[0]["start_s"]
        if i + chunk_size < total:
            end_sec = timings[i + chunk_size]["start_s"]
        else:
            end_sec = min(duration, chunk[-1]["end_s"])
        if end_sec <= start_sec:
            end_sec = start_sec + 0.4
        chunk_text = " ".join(item["word"] for item in chunk)
        lines.append(f"{idx}\n{format_time(start_sec)} --> {format_time(end_sec)}\n{chunk_text}\n")
        idx += 1

    output_srt.write_text("\n".join(lines), encoding="utf-8")


def create_srt_from_text(text: str, duration: float, output_srt: Path) -> None:
    """
    Creates a synchronized SRT file from text and audio duration,
    using natural cadence and punctuation pauses instead of naive division.
    """
    words = text.strip().split()
    if not words:
        output_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n...\n", encoding="utf-8")
        return
    timings = compute_cadence_timings(words, duration)
    create_srt_from_boundaries(timings, duration, output_srt, chunk_size=4)


def create_word_highlight_ass(
    text: str,
    duration: float,
    output_ass: Path,
    lang: str = "en",
    word_boundaries: Optional[List[dict]] = None,
    orientation: str = "portrait",
) -> None:
    """
    Generates dynamic word-by-word karaoke-style ASS subtitles (MrBeast / Alex Hormozi style)
    where the currently spoken word glows in bright yellow while other words remain white.
    Synchronizes using exact neural WordBoundary timestamps from Edge-TTS, or intelligent
    cadence timing on fallback. Supports both portrait (9:16 Shorts) and landscape (16:9) formats.
    """
    font_name = "Noto Sans Gujarati" if lang == "gu" else "Noto Sans Devanagari" if lang == "hi" else "Noto Sans"
    is_landscape = orientation.lower() in ("landscape", "16:9", "widescreen")

    if is_landscape:
        play_res_x = 1920
        play_res_y = 1080
        font_size = 44
        margin_v = 90
        outline = 4
        shadow = 2
        chunk_size = 5 if len(text.split()) > 10 else 4
    else:
        play_res_x = 1080
        play_res_y = 1920
        font_size = 62
        margin_v = 360
        outline = 6
        shadow = 3
        chunk_size = 3 if len(text.split()) > 6 else 2

    words_raw = text.strip().split()
    if not words_raw:
        words_raw = ["..."]

    # Use exact neural boundaries if available and valid
    if word_boundaries and len(word_boundaries) >= max(1, int(len(words_raw) * 0.5)):
        timings = []
        for wb in word_boundaries:
            w_text = wb.get("word", "").strip()
            if w_text:
                timings.append({
                    "word": w_text,
                    "start_s": float(wb.get("start_s", 0.0)),
                    "end_s": min(duration, float(wb.get("end_s", 0.0))),
                })
        if not timings:
            timings = compute_cadence_timings(words_raw, duration)
    else:
        timings = compute_cadence_timings(words_raw, duration)

    def fmt(sec: float) -> str:
        sec = max(0.0, sec)
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        cs = int(round((sec - int(sec)) * 100))
        if cs >= 100:
            cs = 99
        return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"

    events = []
    total_words = len(timings)

    for chunk_idx in range(0, total_words, chunk_size):
        chunk_items = timings[chunk_idx : chunk_idx + chunk_size]
        chunk_len = len(chunk_items)

        # Chunk stays until last word ends (or next chunk begins)
        if chunk_idx + chunk_size < total_words:
            next_start = timings[chunk_idx + chunk_size]["start_s"]
            chunk_end_s = min(duration, max(chunk_items[-1]["end_s"], next_start))
        else:
            chunk_end_s = min(duration, max(chunk_items[-1]["end_s"], duration))

        for w_idx_in_chunk, active_item in enumerate(chunk_items):
            w_start_s = active_item["start_s"]

            # Active word duration extends to next word start in chunk or chunk end
            if w_idx_in_chunk + 1 < chunk_len:
                w_end_s = min(chunk_end_s, chunk_items[w_idx_in_chunk + 1]["start_s"])
            else:
                w_end_s = chunk_end_s

            if w_end_s <= w_start_s:
                w_end_s = w_start_s + 0.15

            line_parts = []
            for j, itm in enumerate(chunk_items):
                w_str = itm["word"]
                clean_w = w_str.upper() if lang == "en" else w_str
                if j == w_idx_in_chunk:
                    line_parts.append(r"{\c&H0000FFFF&\fscx112\fscy112}" + clean_w + r"{\r}")
                else:
                    line_parts.append(r"{\c&H00FFFFFF&\fscx100\fscy100}" + clean_w + r"{\r}")

            line_str = " ".join(line_parts)
            events.append(f"Dialogue: 0,{fmt(w_start_s)},{fmt(w_end_s)},Default,,0,0,0,,{line_str}")

    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,{outline},{shadow},2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n"

    output_ass.write_text(ass_header, encoding="utf-8")


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

    async def _synthesize_edge_async(self, text: str, output_path: Path, subtitle_path: Path, voice: Optional[str] = None) -> List[dict]:
        selected_voice = voice or self.default_voice
        communicate = edge_tts.Communicate(text=text, voice=selected_voice, rate=self.rate, boundary="WordBoundary")
        word_boundaries: List[dict] = []

        with open(output_path, "wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start_s = chunk["offset"] / 10_000_000.0
                    dur_s = chunk["duration"] / 10_000_000.0
                    word_boundaries.append({
                        "word": chunk["text"],
                        "start_s": start_s,
                        "end_s": start_s + dur_s,
                    })

        with AudioFileClip(str(output_path)) as clip:
            duration = clip.duration

        if word_boundaries:
            create_srt_from_boundaries(word_boundaries, duration, subtitle_path, chunk_size=4)
        else:
            create_srt_from_text(text, duration, subtitle_path)

        return word_boundaries

    def _generate_edge_tts(self, text: str, output_path: Path, subtitle_path: Path, lang: str = "en") -> Tuple[bool, List[dict]]:
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            voice = self.get_voice_for_lang(lang, attempt=attempt)
            try:
                logger.info(f"Generating TTS audio via Edge-TTS ({voice} | lang={lang}) - attempt {attempt}...")
                word_boundaries = asyncio.run(self._synthesize_edge_async(text, output_path, subtitle_path, voice=voice))
                if output_path.exists() and output_path.stat().st_size > 100:
                    return True, word_boundaries
            except Exception as e:
                logger.warning(f"Edge-TTS attempt {attempt} failed: {e}")
                time.sleep(attempt * 1.5)
        return False, []

    def _generate_gtts(self, text: str, output_path: Path, subtitle_path: Path, lang: str = "en") -> Tuple[bool, List[dict]]:
        gtts_lang = "gu" if lang == "gu" else "hi" if lang == "hi" else "en"
        for attempt in range(1, 4):
            try:
                logger.info(f"Generating voiceover via gTTS engine (lang={gtts_lang}) - attempt {attempt}...")
                tts = gTTS(text=text, lang=gtts_lang, slow=False)
                tts.save(str(output_path))

                with AudioFileClip(str(output_path)) as clip:
                    duration = clip.duration

                words = text.strip().split()
                timings = compute_cadence_timings(words, duration)
                create_srt_from_boundaries(timings, duration, subtitle_path, chunk_size=4)
                return True, timings
            except Exception as e:
                logger.warning(f"gTTS attempt {attempt} failed: {e}")
                time.sleep(attempt * 2.0)
        return False, []

    def generate_audio(self, text: str, output_path: Path, subtitle_path: Path, lang: str = "en", callback=None) -> Tuple[Path, Path, List[dict]]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subtitle_path.parent.mkdir(parents=True, exist_ok=True)

        def _do_synth():
            # 1. Try Edge-TTS (with neural WordBoundary events)
            success, words = self._generate_edge_tts(text, output_path, subtitle_path, lang=lang)
            # 2. Fallback to gTTS (with cadence & pause distribution)
            if not success:
                success, words = self._generate_gtts(text, output_path, subtitle_path, lang=lang)
            if not success:
                raise ConnectionError(f"TTS network services temporarily unavailable for text: {text[:50]}...")
            return output_path, subtitle_path, words

        # Wrap in network guard for auto-resume if connection drops
        return NetworkGuard.resilient_call(_do_synth, callback=callback)

    def generate_scene_audios(
        self,
        scenes: List[dict],
        run_dir: Path,
        lang: str = "en",
        subfolder: Optional[str] = None,
        orientation: str = "portrait",
        callback=None,
    ) -> List[dict]:
        import json

        folder_name = subfolder if subfolder else (f"audio_{lang}" if lang != "en" else "audio")
        audio_dir = run_dir / folder_name
        audio_dir.mkdir(parents=True, exist_ok=True)

        scene_audio_results = []
        total_scenes = len(scenes)
        for idx, scene in enumerate(scenes):
            scene_num = scene.get("scene_number", idx + 1)
            text = scene.get("narration", "")

            audio_file = audio_dir / f"scene_{scene_num:02d}.mp3"
            srt_file = audio_dir / f"scene_{scene_num:02d}.srt"
            ass_file = audio_dir / f"scene_{scene_num:02d}.ass"
            meta_file = audio_dir / f"scene_{scene_num:02d}.meta.json"
            words_file = audio_dir / f"scene_{scene_num:02d}.words.json"

            # Checkpoint validation: verify cached files match CURRENT narration text exactly!
            reusable = False
            word_boundaries = []
            if audio_file.exists() and srt_file.exists() and ass_file.exists() and meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    if (
                        meta.get("text") == text.strip()
                        and meta.get("orientation") == orientation
                        and audio_file.stat().st_size > 100
                    ):
                        reusable = True
                        if words_file.exists():
                            word_boundaries = json.loads(words_file.read_text(encoding="utf-8"))
                except Exception:
                    reusable = False

            if reusable:
                logger.info(f"⚡ Checkpoint verified: Reusing matching voiceover for scene {scene_num} ({lang}, {folder_name})")
                if callback:
                    callback(idx + 1, total_scenes, f"Reused verified voice for scene {idx + 1}/{total_scenes} ({lang.upper()})")
                with AudioFileClip(str(audio_file)) as clip:
                    duration = clip.duration
            else:
                if callback:
                    callback(idx + 1, total_scenes, f"Synthesizing voice for scene {idx + 1}/{total_scenes} ({lang.upper()})")
                _, _, word_boundaries = self.generate_audio(text, audio_file, srt_file, lang=lang, callback=callback)
                time.sleep(0.3)

                with AudioFileClip(str(audio_file)) as clip:
                    duration = clip.duration

                # Persist words and metadata checkpoints to enforce 100% sync integrity
                try:
                    meta_data = {
                        "text": text.strip(),
                        "lang": lang,
                        "orientation": orientation,
                        "duration": duration,
                    }
                    meta_file.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8")
                    if word_boundaries:
                        words_file.write_text(json.dumps(word_boundaries, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception as e:
                    logger.debug(f"Could not write meta/words file for scene {scene_num}: {e}")

            # Always generate/refresh dynamic word-highlight ASS with verified orientation and word boundaries
            create_word_highlight_ass(
                text=text,
                duration=duration,
                output_ass=ass_file,
                lang=lang,
                word_boundaries=word_boundaries,
                orientation=orientation,
            )

            scene_audio_results.append({
                "scene_number": scene_num,
                "narration": text,
                "audio_path": audio_file,
                "subtitle_path": srt_file,
                "ass_path": ass_file,
                "duration": duration,
                "word_boundaries": word_boundaries,
                "speaker_entity": scene.get("speaker_entity", ""),
                "speaking_action": scene.get("speaking_action", ""),
                "proper_sign": scene.get("proper_sign", ""),
                "sign_badge": scene.get("sign_badge", ""),
            })

        return scene_audio_results
