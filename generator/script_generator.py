import importlib.util
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

import config
from growth.model_resolver import call_gemini_resilient, get_candidate_models, mark_model_successful

logger = logging.getLogger(__name__)

import re

# Strict All-Ages / Zero-Tolerance Patterns (No 18+, No Nude, No Porn, No Sexy Content)
PROHIBITED_18_PLUS_PATTERNS = [
    # 18+, Adult, Pornography, Erotica
    r"18\+",
    r"adult[\s_-]+(only|content|material|film|video|theme)",
    r"nsfw",
    r"porn\w*",
    r"sex\b",
    r"sexual\w*",
    r"sexy\w*",
    r"sensual\w*",
    r"erotic\w*",
    r"fetish\w*",
    r"bdsm",
    r"kinky\w*",
    r"xxx",
    # Nude, Naked, Revealing & Provocative Attire
    r"nud\w*",
    r"naked\w*",
    r"shirtless\w*",
    r"topless\w*",
    r"bottomless\w*",
    r"bare[\s_-]*chest\w*",
    r"bare[\s_-]*skin",
    r"cleavag\w*",
    r"bikini\w*",
    r"swimsuit\w*",
    r"swimwear\w*",
    r"lingerie\w*",
    r"underwear\w*",
    r"panties\w*",
    r"bra\b",
    r"brassiere\w*",
    r"thong\w*",
    r"provocative\w*",
    r"seducti\w*",
    r"horny\w*",
    r"lust\w*",
    r"strip\b",
    r"stripper\w*",
    r"striptease\w*",
    r"escort\w*",
    r"hookup\w*",
    r"onlyfans",
    r"camgirl\w*",
    # Anatomy Slang
    r"boobs\w*",
    r"breasts?\b",
    r"buttocks?\b",
    r"penis\w*",
    r"vagina\w*",
    r"pussy\w*",
    # Drugs, Alcohol & Tobacco
    r"drugs?\b",
    r"cocaine",
    r"heroin",
    r"meth\b",
    r"weed\b",
    r"marijuana",
    r"vaping",
    r"vape\b",
    r"tobacco",
    r"cigarette\w*",
    r"alcohol\w*",
    r"liquor\w*",
    r"whiskey",
    r"vodka",
    r"drunk\w*",
    r"hangover\w*",
    # Gambling
    r"casino\w*",
    r"gambling\w*",
    r"betting\w*",
    # Extreme Violence & Weapons
    r"suicide\w*",
    r"murder\w*",
    r"gore\b",
    r"bloodshed\w*",
    r"massacre\w*",
    r"weapons?\b",
    r"gunshot\w*",
]

# Legacy terms list for backwards compatibility
PROHIBITED_18_PLUS_TERMS = [
    "18+", "adult content", "porn", "sex", "sexy", "nude", "nudity", "bikini", "cleavage", "shirtless"
]


def validate_family_safe(text: str) -> bool:
    """Validates that text strictly complies with the all-ages / zero 18+ / zero sexy policy."""
    lower = text.lower()
    for pat in PROHIBITED_18_PLUS_PATTERNS:
        full_pat = r"(?:^|\W)" + pat + r"(?:$|\W)"
        m = re.search(full_pat, lower)
        if m:
            matched_term = m.group(0).strip()
            raise ValueError(
                f"Content safety violation: Prohibited term detected: '{matched_term}'. Content must be strictly all-ages safe (zero 18+, zero sexy, zero nude)."
            )
    return True


EXPANDED_GROWTH_THEMES = [
    "Neuroscience of Willpower & Brain Friction (Anterior Mid-Cingulate Cortex expansion)",
    "Stoic Mental Fortitude & Emotional Resilience (Marcus Aurelius & Epictetus rules for calm under pressure)",
    "The Eagle's Law: How Apex Predators Filter Out Distraction and Lock on High-Value Targets",
    "The Deep Work Fortress: Mastering Elite Focus and Distraction-Free Execution",
    "The Wolfpack Mental Model: Savage Endurance, Quiet Strength, and Relentless Loyalty to Standards",
    "The 20-Second Rule: Eliminating Habit Friction for Automatic Daily Discipline",
    "Antifragility in Living Nature: How Ancient Trees and Wild Organisms Thrive Under Harsh Stress",
    "Circadian Biology, Deep Sleep Architecture & Hormonal Reset",
    "The Lion Mindset: Silent Authority, Predatory Focus, and Calm Decisive Power",
    "Dopamine Detox, Focus Optimization & Eliminating Brain Fog",
    "Bamboo Resilience: Why Bending in the Storm Beats Rigid Resistance (Natural Elasticity)",
    "Hormesis & Longevity Protocols (Cold Exposure, Natural Thermal Adaptation, Autophagy)",
    "High-Performance Daily Routine & 4-Hour Deep Work Mastery",
    "The Psychology of Discipline vs Motivation: Why Motivation is a Trap",
    "Overcoming Procrastination & The Friction Principle of Action",
    "Mental Toughness & Breaking Past the 40% Perceived Barrier",
    "Delayed Gratification & The Compound Effect of Micro-Habits",
    "Managing Cortisol, Chronic Stress & Restoring Peak Energy",
    "The Ancient Stoic Armor: Unshakeable Inner Equanimity Under External Chaos",
    "The Stoic Art of Unshakeable Confidence and Detachment from Validation",
]

# Backwards compatibility alias
EXPANDED_ADULT_THEMES = EXPANDED_GROWTH_THEMES


def get_topic_history() -> List[str]:
    """Retrieves recent topics and titles to avoid repeating content."""
    history = []
    history_file = config.OUTPUT_DIR / "topic_history.json"
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    # Also check past run directory scripts
    for script_file in sorted(config.OUTPUT_DIR.glob("run_*/script.json"), reverse=True)[:30]:
        try:
            with open(script_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                title = data.get("title", "")
                topic = data.get("topic", "")
                entry = f"{title} (Topic: {topic})"
                if entry and entry not in history:
                    history.append(entry)
        except Exception:
            pass

    return history[-30:]


def record_topic_history(topic: str, title: str):
    """Saves newly generated topic to history to ensure future uniqueness."""
    history_file = config.OUTPUT_DIR / "topic_history.json"
    history = []
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    entry = f"{title} (Topic: {topic})"
    if entry not in history:
        history.append(entry)

    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save topic history: {e}")


class Scene(BaseModel):
    scene_number: int = Field(description="Sequential scene number starting from 1")
    narration: str = Field(
        description="The exact spoken voiceover text for this scene. Punchy, authoritative, and engaging."
    )
    speaker_entity: str = Field(
        default="Disciplined Stoic Mentor",
        description="The person or personified entity actively talking in this scene (e.g. 'Disciplined Stoic Mentor in dark coat', 'Living Marble Statue of Marcus Aurelius', 'Futuristic Cybernetic Life Coach', 'Wise Veteran Scholar')."
    )
    speaking_action: str = Field(
        default="Speaking directly into the camera with mouth open in mid-speech delivery",
        description="The specific speaking action and facial expression showing active talking and passionate oratory delivery."
    )
    proper_sign: str = Field(
        default="Raising hand in an authoritative STOP sign gesture",
        description="The clear physical sign or gesture made by the speaker (e.g., 'Raising palm in a firm STOP sign 🛑', 'Index finger raised making Rule #1 point ☝️', 'Pointing directly into the lens at the viewer 👉', 'Pointing down to comments and subscribe 👇')."
    )
    sign_badge: str = Field(
        default="⚠️ RULE #1",
        description="Short punchy 2-4 word text for the on-screen graphic signboard badge in the language of this script (e.g. '🛑 STOP THIS', '🧠 RULE #1', '🎯 100% FOCUS', '👇 ACT NOW')."
    )
    visual_prompt: str = Field(
        description="Detailed prompt for AI image generator. Must specify the speaking person/thing actively talking with mouth open in mid-speech, making the proper sign/gesture, shot on ARRI Alexa LF, 35mm anamorphic prime lens, T1.5 shallow depth of field, authentic natural lighting, lifelike human skin pores and micro-expressions, authentic material physics, 9:16 vertical composition, 8k resolution, documentary cinematography realism, photorealistic, hyper-detailed, no text overlay."
    )
    estimated_duration_sec: float = Field(
        default=5.0, description="Estimated duration of narration in seconds"
    )


class CommunityPoll(BaseModel):
    question: str = Field(
        description="A thought-provoking, debate-igniting YouTube Community Poll question relating directly to the Short's theme"
    )
    options: List[str] = Field(
        description="4 high-impact multiple choice options for viewers to vote on"
    )
    post_text: str = Field(
        description="Short 1-2 sentence context text accompanying the poll with relevant hashtags"
    )


class ShortsScript(BaseModel):
    topic: str = Field(description="The core topic, stoic lesson, or health/fitness principle explored in the video")
    title: str = Field(
        description="Viral, high-converting YouTube Shorts title (< 70 chars) with strong curiosity or emotional hook, ending with #Shorts"
    )
    description: str = Field(
        description="SEO-optimized description including summary, key takeaways, and 5-8 relevant hashtags like #Motivation #Fitness #SelfImprovement #Discipline #Shorts"
    )
    tags: List[str] = Field(
        description="10-15 comma-separated YouTube keyword tags for motivation, health, fitness, discipline, and psychology"
    )
    category_id: str = Field(
        default=config.DEFAULT_CATEGORY_ID,
        description="YouTube category ID: 27=Education, 26=Howto & Style, 22=People & Blogs",
    )
    pinned_comment: str = Field(
        description="An engaging, thought-provoking question or discussion starter for the audience to pin in the comments section"
    )
    scenes: List[Scene] = Field(
        description="A sequence of 4-6 scenes making up a 35 to 55 second high-retention vertical Short"
    )
    community_poll: Optional[CommunityPoll] = Field(
        default=None,
        description="Matching YouTube Community Poll to ignite organic reach and subscriber debate"
    )


class LanguageScript(BaseModel):
    language: str = Field(description="Language code: en, hi, or gu")
    title: str = Field(
        description=(
            "Catchy, viral, click-compelling title under 60 characters ending with #Shorts. "
            "CRITICAL: The title MUST be written in the authentic native script of this language! "
            "For 'en': Catchy English title ending with #Shorts. "
            "For 'hi': Authentic, natural Hindi title written in Devanagari script ending with #Shorts (DO NOT use English letters). "
            "For 'gu': Authentic, natural Gujarati title written in Gujarati script ending with #Shorts (DO NOT use English letters)."
        )
    )
    description: str = Field(
        description="Two sentences explaining the video's value, ending with a call to action to subscribe."
    )
    hashtags: str = Field(
        description="A single string of 5 highly relevant hashtags (e.g., '#motivation #health #DailyGrowth #Shorts')"
    )
    tags: List[str] = Field(
        default=["Daily Growth", "Motivation", "Self Improvement", "Health", "Shorts"],
        description="List of 8-12 YouTube search keyword tags"
    )
    voiceover_script: str = Field(
        description="The exact spoken text for 45-60 second video (roughly 120-140 words) with a strong hook in first 3 seconds."
    )
    scenes: List[Scene] = Field(
        description="Sequence of 4-5 timed scenes with narration and 9:16 visual prompts for video subtitle sync"
    )


class TrilingualShortsPackage(BaseModel):
    topic: str = Field(
        description="The chosen topic: one of 'stoic mental resilience', 'practical daily health habits', or 'realistic financial discipline'"
    )
    theme_category: str = Field(
        description="Category: 'stoic_resilience', 'health_habits', or 'financial_discipline'"
    )
    visual_prompt: str = Field(
        description="A highly detailed descriptive prompt for AI image/video generator for background footage (shot on ARRI Alexa LF, 35mm anamorphic prime lens, 9:16 vertical, cinematic lighting, photorealistic documentary realism)"
    )
    english: LanguageScript = Field(description="Complete English Short package")
    hindi: LanguageScript = Field(description="Complete Hindi Short package in Devanagari script")
    gujarati: LanguageScript = Field(description="Complete Gujarati Short package in Gujarati script")
    community_poll: Optional[CommunityPoll] = Field(
        default=None,
        description="Matching YouTube Community Poll to ignite organic reach and subscriber debate"
    )


class LongVideoScene(BaseModel):
    scene_number: int = Field(description="Sequential scene number starting from 1")
    chapter_title: str = Field(description="Short chapter title for YouTube timestamps (e.g. '01: The Hidden Mechanism', '02: Dopamine Detox Protocol')")
    narration: str = Field(description="The spoken voiceover narration text for this chapter/scene (~40-70 words)")
    visual_prompt: str = Field(
        description="Detailed prompt for AI image generator for a 16:9 widescreen landscape cinema still shot on ARRI Alexa LF, 35mm anamorphic prime lens, T1.5 shallow depth of field, authentic natural lighting, lifelike human skin pores and micro-expressions, authentic material physics, 16:9 horizontal composition, 8k resolution, documentary cinematography realism, photorealistic, hyper-detailed, no text overlay."
    )
    estimated_duration_sec: float = Field(default=18.0, description="Estimated duration in seconds")


class LongVideoScript(BaseModel):
    topic: str = Field(description="The core topic or masterclass theme explored in this full-length video")
    title: str = Field(
        description="High-converting, curiosity-driven YouTube video title under 80 characters (NO #Shorts tag), with an irresistible promise or deep psychological hook"
    )
    description: str = Field(
        description="Full SEO description for YouTube including summary, formatted chapters/timestamps (00:00 - Introduction, ...), key takeaways, subscribe call to action, and 5-8 relevant hashtags"
    )
    tags: List[str] = Field(
        description="15-20 high-volume YouTube search keyword tags for mindset, discipline, science, and self-improvement"
    )
    category_id: str = Field(
        default=config.DEFAULT_CATEGORY_ID,
        description="YouTube category ID: 27=Education, 26=Howto & Style, 22=People & Blogs"
    )
    thumbnail_headline: str = Field(
        description="Short, punchy 2-3 word high-contrast text to display boldly on the 16:9 thumbnail (MUST NOT repeat words from the title, e.g., 'FIX THIS NOW', 'STOP WAITING', 'BRAIN TRAP')"
    )
    thumbnail_accent: Optional[str] = Field(
        default=None,
        description="Short 3-5 word curiosity kicker shown below the thumbnail headline specific to this topic (e.g., '3 BIOLOGY SHIFTS EXPLAINED', 'NO WILLPOWER NEEDED')"
    )
    thumbnail_visual_prompt: str = Field(
        description="Detailed prompt for 16:9 widescreen thumbnail artwork featuring intense emotional focus, high contrast, cinematic ARRI Alexa lighting, clean negative space for headline text"
    )
    scenes: List[LongVideoScene] = Field(
        description="Sequence of 6 to 10 sequential chapters/scenes making up a 2 to 4 minute deep-dive educational video"
    )
    pinned_comment: str = Field(
        description="Thought-provoking question or discussion starter for the audience to pin at the top of comments"
    )


from growth.growth_engine import GrowthEngine
from growth.network_guard import NetworkGuard

_SKILL_MODULE_CACHE: Dict[str, Any] = {}


def _load_skill_module(rel_path: str) -> Any:
    """Loads a local skill scorer script once cleanly without altering sys.path."""
    if rel_path in _SKILL_MODULE_CACHE:
        return _SKILL_MODULE_CACHE[rel_path]
    full_path = config.BASE_DIR / rel_path
    if not full_path.exists():
        _SKILL_MODULE_CACHE[rel_path] = None
        return None
    try:
        spec = importlib.util.spec_from_file_location(f"skill_{full_path.stem}", str(full_path))
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        _SKILL_MODULE_CACHE[rel_path] = mod
        return mod
    except Exception as e:
        logger.debug(f"Could not load skill scorer {rel_path}: {e}")
        _SKILL_MODULE_CACHE[rel_path] = None
        return None


def _normalize_title_tokens(title: str) -> set:
    """Extracts meaningful lowercase title tokens excluding #Shorts boilerplate."""
    cleaned = re.sub(r"#shorts\b", "", (title or "").lower())
    return {w for w in re.findall(r"[a-z0-9\u0900-\u097f\u0a80-\u0aff]+", cleaned) if len(w) > 2}


def is_repetitive_title(title: str, avoid_titles: List[str]) -> bool:
    """Returns True if title matches or closely overlaps (>=80%) any previously uploaded/saturated title."""
    cand_norm = re.sub(r"\s+", " ", re.sub(r"#shorts\b", "", (title or "").lower())).strip()
    cand_toks = _normalize_title_tokens(title)
    if not cand_norm:
        return True
    for old in avoid_titles:
        old_clean = re.sub(r"\(Topic:.*", "", old, flags=re.IGNORECASE).strip()
        old_norm = re.sub(r"\s+", " ", re.sub(r"#shorts\b", "", old_clean.lower())).strip()
        if not old_norm:
            continue
        if cand_norm == old_norm:
            return True
        old_toks = _normalize_title_tokens(old_clean)
        if cand_toks and old_toks and len(cand_toks) >= 3:
            overlap = len(cand_toks & old_toks) / max(len(cand_toks | old_toks), 1)
            if overlap >= 0.80:
                return True
    return False


class ScriptGenerator:
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_keys = [api_key] if api_key else (getattr(config, "GEMINI_API_KEYS", None) or [config.GEMINI_API_KEY])
        self.api_keys = [k for k in self.api_keys if k]
        self.current_key_idx = 0
        self.api_key = self.api_keys[0] if self.api_keys else ""
        self.model_name = model_name or config.GEMINI_MODEL

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please set it in .env or pass it to ScriptGenerator."
            )

        self.client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=60000.0))
        self.growth_engine = GrowthEngine(api_key=self.api_key)

    def rotate_api_key(self) -> bool:
        """Rotates to next available GEMINI_API_KEY if multiple are provided."""
        if len(self.api_keys) > 1:
            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            self.api_key = self.api_keys[self.current_key_idx]
            self.client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=60000.0))
            logger.info(f"🔄 Rotated Gemini API key to key #{self.current_key_idx + 1} of {len(self.api_keys)}")
            return True
        return False

    def _ensure_native_title(self, title: str, lang: str, english_title: str) -> str:
        """
        Validates that the title is truly written in the target native script.
        If missing native characters (e.g. Gemini returned an English title),
        localizes the English title via Gemini into authentic Hindi or Gujarati.
        """
        has_native = False
        if lang == "hi" and re.search(r"[\u0900-\u097F]", title):
            has_native = True
        elif lang == "gu" and re.search(r"[\u0A80-\u0AFF]", title):
            has_native = True

        if has_native and title.strip() != english_title.strip():
            return title

        logger.info(f"🌐 [Title Localizer] Localizing title to authentic {lang.upper()} script...")
        lang_name = "Hindi in Devanagari script" if lang == "hi" else "Gujarati in Gujarati script"
        prompt = (
            f"Translate and localize this YouTube Shorts title into viral, natural, catchy {lang_name}. "
            f"Keep it under 60 characters and end strictly with #Shorts. "
            f"Do NOT return any English letters, explanation, or quotes. Only return the localized title:\n"
            f"'{english_title}'"
        )
        models_to_try = get_candidate_models(preferred=self.model_name, tier="argon")
        for model in models_to_try:
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                raw_text = resp.text.strip()
                clean_title = None
                for line in raw_text.splitlines():
                    cleaned_line = line.strip().strip('*').strip('"').strip("'").strip()
                    if re.search(r'#Shorts', cleaned_line, re.IGNORECASE):
                        clean_title = cleaned_line
                        break
                if not clean_title:
                    first_line = raw_text.splitlines()[0].strip().strip('*').strip('"').strip("'").strip()
                    clean_title = f"{first_line} #Shorts" if not first_line.endswith("#Shorts") else first_line

                logger.info(f"✨ [Title Localizer] Successfully localized {lang.upper()} title using {model}: '{clean_title}'")
                return clean_title
            except Exception as e:
                logger.debug(f"Candidate {model} failed for title localization: {e}. Trying next model...")

        logger.warning(f"⚠️ Could not auto-localize {lang} title across candidate models.")
        return title

    def _get_avoid_titles(self) -> List[str]:
        """Combines local topic history and channel-wide saturated titles from GrowthEngine."""
        combined = list(get_topic_history())
        try:
            for t in self.growth_engine.get_saturated_titles():
                if t and t not in combined:
                    combined.append(t)
        except Exception:
            pass
        return combined

    def _audit_short_quality(self, lang_pkg: Any, avoid_titles: List[str]) -> Dict[str, Any]:
        """Scores a Shorts script using repo skill linters (faceless_rules, hookscore, title)."""
        issues: List[str] = []
        title = getattr(lang_pkg, "title", "")
        scenes = getattr(lang_pkg, "scenes", []) or []
        first_hook = scenes[0].narration if scenes else ""

        if is_repetitive_title(title, avoid_titles):
            issues.append(f"Title '{title}' duplicates or closely overlaps a saturated channel title.")

        faceless_mod = _load_skill_module("skills/faceless-shorts/faceless_rules.py")
        fl_score = 100
        if faceless_mod and hasattr(faceless_mod, "lint_faceless_script"):
            res = faceless_mod.lint_faceless_script(lang_pkg.model_dump())
            fl_score = res.get("score", 100)
            for _, msg in res.get("issues", []):
                issues.append(msg)

        hook_verdict = 75
        hook_mod = _load_skill_module("skills/yt-script/hookscore.py")
        if hook_mod and hasattr(hook_mod, "score") and first_hook:
            _, hook_verdict, _, _ = hook_mod.score(first_hook)
            if hook_verdict < 62:
                issues.append(f"Opening hook scored {hook_verdict}/100: needs direct 'you' address + concrete stakes/curiosity gap.")

        title_score = 80
        title_mod = _load_skill_module("skills/yt-package/title.py")
        if title_mod and hasattr(title_mod, "check") and title:
            tr = title_mod.check(re.sub(r"#shorts\b", "", title, flags=re.I).strip())
            title_score = tr.get("score", 80)

        return {
            "faceless_score": fl_score,
            "hook_score": hook_verdict,
            "title_score": title_score,
            "issues": issues,
            "needs_polish": bool(issues and (fl_score < 78 or hook_verdict < 62 or any("duplicates" in i for i in issues))),
        }

    def _polish_trilingual_package(self, package: TrilingualShortsPackage, avoid_titles: List[str]) -> TrilingualShortsPackage:
        """Runs 1 targeted quality-polish pass if pre-publish scoring flags weak hooks/pacing/duplicates."""
        audit = self._audit_short_quality(package.english, avoid_titles)
        logger.info(
            f"📊 [Pre-Publish Quality Audit] Faceless={audit['faceless_score']}/100 | "
            f"Hook={audit['hook_score']}/100 | Title={audit['title_score']}/100"
        )
        if not audit["needs_polish"]:
            return package

        if self.client:
            polish_prompt = f"""
Improve this Trilingual Shorts package to maximize WATCH TIME, RETENTION (>100% loop APV), VIEWS, and LIKES.
Fix ONLY these diagnosed weaknesses across English, Hindi (Devanagari), and Gujarati:
{chr(10).join('- ' + i for i in audit['issues'])}

REQUIREMENTS:
1. Plain, concrete, relatable Title under 52 chars ending with #Shorts (NO banned jargon like 'Glitch', NO duplicate titles).
2. Scene 1 hook MUST directly address 'you' with immediate stakes in <=18 words.
3. Break narration into 5 to 6 scenes, each 3.0 to 4.5 seconds estimated_duration_sec.
4. End the final scene with a seamless loop connector phrase ('And that is why...', 'Remember this rule...', 'Because...').
5. Preserve all family-safe standards and accurate Hindi/Gujarati localization.

CURRENT PACKAGE JSON:
{json.dumps(package.model_dump(), ensure_ascii=False)}
"""
            try:
                res, used_model = call_gemini_resilient(
                    client=self.client,
                    contents=polish_prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=TrilingualShortsPackage,
                        temperature=0.5,
                    ),
                    preferred_model=self.model_name,
                    tier="argon",
                    task_name="Pre-Publish Shorts Quality Polish",
                )
                improved = TrilingualShortsPackage(**json.loads(res.text))
                improved.hindi.title = self._ensure_native_title(improved.hindi.title, "hi", improved.english.title)
                improved.gujarati.title = self._ensure_native_title(improved.gujarati.title, "gu", improved.english.title)
                validate_family_safe(f"{improved.topic} {improved.english.title} {improved.english.voiceover_script}")
                logger.info(f"✨ [Quality Polish] Upgraded trilingual script via {used_model}")
                return improved
            except Exception as e:
                logger.debug(f"Pre-publish polish skipped cleanly: {e}")

        # Deterministic safety clamp so scene durations stay snappy
        for lang_obj in (package.english, package.hindi, package.gujarati):
            for sc in lang_obj.scenes:
                if sc.estimated_duration_sec > 5.0:
                    sc.estimated_duration_sec = 4.2
        return package

    def _polish_long_script(self, script: LongVideoScript, avoid_titles: List[str]) -> LongVideoScript:
        """Audits 16:9 long video CTR packaging & opening 15s hook for watch hours."""
        issues: List[str] = []
        if is_repetitive_title(script.title, avoid_titles) or "masterclass guide" in script.title.lower():
            issues.append(f"Title '{script.title}' sounds generic/repetitive. Rewrite with specific concrete number/curiosity (<58 chars).")

        title_mod = _load_skill_module("skills/yt-package/title.py")
        if title_mod and hasattr(title_mod, "check"):
            tr = title_mod.check(script.title, script.thumbnail_headline)
            for k, msg in tr.get("issues", []):
                if k in ("duplicate", "thumb-length", "vague", "length"):
                    issues.append(msg)

        hook_mod = _load_skill_module("skills/yt-script/hookscore.py")
        if hook_mod and hasattr(hook_mod, "score") and script.scenes:
            _, hv, _, _ = hook_mod.score(script.scenes[0].narration[:220])
            if hv < 60:
                issues.append(f"First 15s hook scored {hv}/100: cut abstract intro and start with direct stakes for 'you'.")

        if not issues or not self.client:
            return script

        polish_prompt = f"""
Upgrade this 16:9 YouTube video script for higher CTR and Multi-Minute WATCH HOURS.
Fix ONLY these packaging & retention issues:
{chr(10).join('- ' + i for i in issues)}

RULES:
- Title: under 58 chars, concrete curiosity + number/stakes, NO 'Masterclass Guide', NO repetitive buzzwords.
- thumbnail_headline: max 3 bold words using DIFFERENT words than the title.
- thumbnail_accent: 3-4 concrete kicker words (never 'WATCH BEFORE IT IS TOO LATE').
- Scene 1 narration: open cold with 'you' and undeniable personal stakes in the first sentence.
- Each chapter should end with an open loop pulling the viewer into the next chapter.

CURRENT SCRIPT JSON:
{json.dumps(script.model_dump(), ensure_ascii=False)}
"""
        try:
            res, used_model = call_gemini_resilient(
                client=self.client,
                contents=polish_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=LongVideoScript,
                    temperature=0.5,
                ),
                preferred_model=self.model_name,
                tier="argon",
                task_name="Pre-Publish Long Video Polish",
            )
            improved = LongVideoScript(**json.loads(res.text))
            validate_family_safe(f"{improved.topic} {improved.title} {improved.thumbnail_headline} " + " ".join(s.narration for s in improved.scenes))
            logger.info(f"✨ [Quality Polish] Upgraded 16:9 watch-hours script via {used_model}")
            return improved
        except Exception as e:
            logger.debug(f"Long script polish skipped cleanly: {e}")
            return script

    def generate_trilingual_script(self, specific_topic: Optional[str] = None, callback: Optional[Callable] = None) -> TrilingualShortsPackage:
        """
        Generates a synchronized 3-language video package (English, Hindi, Gujarati)
        in a SINGLE prompt call, focused on stoic resilience, daily health, or financial discipline.
        """
        NetworkGuard.wait_for_network(callback=callback)
        avoid_titles = self._get_avoid_titles()
        growth_intelligence = self.growth_engine.get_growth_prompt_context(content_format="shorts")

        # Target Pillars
        trilingual_pillars = [
            "stoic mental resilience, unshakeable inner peace, and nature's living endurance under pressure",
            "practical daily health habits, biological energy optimization, and natural vitality",
            "realistic financial discipline, compounding micro-money rules, and sustainable growth",
            "lessons from apex predators and wild living creatures: focus, grit, and survival mastery",
        ]
        chosen_pillar = specific_topic or random.choice(trilingual_pillars)

        history_instruction = ""
        if avoid_titles:
            formatted_history = "\n".join([f"- {t}" for t in avoid_titles[-20:]])
            history_instruction = f"""
CRITICAL UNIQUENESS REQUIREMENT:
Ensure this topic and title are 100% unique and NEVER repeat or paraphrase:
{formatted_history}
"""

        system_instruction = (
            "You are Gemini 4 Argon, Google's flagship reasoning engine, acting as an elite YouTube Shorts producer.\n"
            "Your task is to leverage advanced reasoning to generate an exceptional, viral-ready, trilingual short video package focused on one of these pillars: "
            "stoic mental resilience, practical daily health habits, realistic financial discipline, or powerful survival/focus principles drawn from living nature and wildlife. "
            "Pick only one topic per generation. The tone must be clean, inspiring, authoritative, and deeply actionable.\n\n"
            f"{config.SAFETY_GUARDRAILS}\n\n"
            "STRICT AGE-APPROPRIATE & ZERO-TOLERANCE POLICY (NO 18+, NO NUDE, NO PORN, NO SEXY CONTENT):\n"
            "- All content (titles, descriptions, voiceover narration, and visual prompts) MUST be 100% clean, wholesome, and suitable for all ages (G/PG rating).\n"
            "- Strictly NEVER generate any 18+ adult content, sexual references, nudity, sexy/provocative clothing, revealing cleavage, bare chest, shirtless figures, coarse language, profanity, vulgarity, violence, gore, weapons, alcohol, tobacco, drugs, or mature/illicit topics.\n\n"
            "GEMINI 4 ARGON DEEP REASONING & NARRATIVE ARCHITECTURE:\n"
            "Apply multi-step reasoning to construct a compelling psychological progression across all 4-5 scenes:\n"
            "1. Scene 1 (The Cognitive Paradox / Pattern Interrupt Hook): Shatter viewer scrolling autopilot in the first 2-3 seconds with an inescapable truth or counter-intuitive psychological insight. Do NOT start with cliché greetings.\n"
            "2. Scene 2 (The Hidden Trap / Behavioral Glitch): Unmask the subtle evolutionary or cognitive mistake that keeps 99% of people trapped in complacency.\n"
            "3. Scene 3 (Rule #1 / The Sovereign Mechanism): Reveal the actionable, high-leverage principle or mental model that immediately shifts trajectory.\n"
            "4. Scene 4/5 (Transformative Climax & Empowering Call to Action): Deliver the final decisive paradigm shift with commanding clarity and an empowering directive.\n\n"
            "Generate synchronized scripts across 3 languages:\n"
            "1. ENGLISH (Language: 'en')\n"
            "2. HINDI (Language: 'hi' - Written in authentic, natural Devanagari script)\n"
            "3. GUJARATI (Language: 'gu' - Written in authentic, natural Gujarati script)\n\n"
            "Rules for EACH language package:\n"
            "- Title: MUST be translated and written in the native script of that specific language! Under 60 characters ending with #Shorts:\n"
            "  * English ('en'): Catchy English title ending with #Shorts.\n"
            "  * Hindi ('hi'): Authentic Hindi title written strictly in Devanagari script ending with #Shorts (NEVER use English letters or English words in Hindi title).\n"
            "  * Gujarati ('gu'): Authentic Gujarati title written strictly in Gujarati script ending with #Shorts (NEVER use English letters or English words in Gujarati title).\n"
            "- Description: Two sentences explaining the video's value, ending with a call to action to subscribe, in the native language/script.\n"
            "- Hashtags: A single string of 5 highly relevant hashtags (e.g., '#motivation #health #DailyGrowth #Shorts').\n"
            "- Voiceover_Script: The exact spoken text for a 40-50 second video (~115-140 words total) with a strong hook in the first 3 seconds, ending on an infinite loop connector phrase that flows seamlessly back into the opening hook line.\n"
            "- Scenes: 5 to 6 rapid, timed scenes (each strictly 3.0 to 4.5 seconds for high visual dopamine and retention) breaking down the voiceover script with matching cinematic 9:16 visual prompts.\n"
            "- CRITICAL REQUIREMENT: PEOPLE OR THINGS MUST TALK & GIVE PROPER SIGNS:\n"
            "  Every single scene prompt MUST prominently feature a PERSON OR PERSONIFIED THING actively TALKING directly to the camera and giving a PROPER SIGN:\n"
            "  * TALKING SUBJECT (PERSON OR THING): Mentor in warm coat, stoic coach, ancient philosopher, or personified living entity (e.g. animated marble statue of Marcus Aurelius coming alive to speak, wise grandfather, focused scholar, or high-tech android mentor) ACTIVELY SPEAKING directly to the camera with mouth visibly open in dynamic speech delivery, intense eye contact, passionate oratory expression.\n"
            "  * PROPER PHYSICAL SIGNS & GESTURES: The talking speaker MUST make a clear, authoritative sign/gesture in every scene:\n"
            "    - Scene 1 (The Hook): Authoritative STOP sign 🛑 (palm held up firmly towards the camera, or finger pointing directly at the viewer 👉).\n"
            "    - Scene 2 (The Trap / Problem): Warning or comparison sign (pointing to a ticking clock, gesturing between two contrasting paths, holding up a caution gesture).\n"
            "    - Scene 3 (The Core Principle): Rule #1 sign ☝️ (index finger raised upright delivering the key lesson, or tapping temple for mental focus).\n"
            "    - Scene 4 / Final (Call to Action): Empowering sign (pointing down to comments/subscribe 👇, firm thumbs-up 👍, or clenched fist of resolve ✊).\n"
            "  * PROPER SIGNBOARD BADGE (sign_badge): A short, punchy 2-4 word localized graphic sign badge for each scene:\n"
            "    - English: '🛑 STOP THIS', '🧠 RULE #1', '⚡ THE GLITCH', '🎯 100% FOCUS', '👇 ACT NOW'.\n"
            "    - Hindi (Devanagari): '🛑 रुकिए', '🧠 नियम #1', '⚡ असली सच', '🎯 100% फोकस', '👇 सब्सक्राइब करें'.\n"
            "    - Gujarati (Gujarati script): '🛑 ઊભા રહો', '🧠 નિયમ #1', '⚡ સાચો રસ્તો', '🎯 100% ધ્યાન', '👇 સબ્સ્ક્રાઇબ કરો'.\n"
            "  * Visual Realism & Style: 9:16 vertical framing, ultra-photorealistic cinema still shot on ARRI Alexa LF, 35mm anamorphic prime lens, T1.5 shallow depth of field with organic background bokeh, natural directional lighting (key light and subtle rim light), authentic skin micro-textures, pores, and realistic expressions, genuine physical material physics (wool, leather, polished metal, natural foliage), documentary cinematography realism (National Geographic / BBC style), strictly modest fully clothed attire, 100% family-friendly, zero nudity, zero sexy elements, zero shirtless figures, zero violence, zero weapons, NO on-screen text in the image itself."
        )

        prompt = f"""
Generate a complete Trilingual YouTube Shorts package (English, Hindi, Gujarati) powered by Gemini 4 Argon reasoning.

Target Focus Pillar: {chosen_pillar}
{growth_intelligence}
{history_instruction}

Ensure Hindi is written in genuine Devanagari script and Gujarati is written in genuine Gujarati script with punchy, native cadence.
Enforce strict all-ages / family-friendly standards (zero 18+ content).
"""
        candidate_models = get_candidate_models(preferred=self.model_name, tier="argon")

        for model in candidate_models:
            for key_attempt in range(len(self.api_keys)):
                try:
                    logger.info(f"Generating Trilingual Shorts package using Gemini model: {model} (key #{self.current_key_idx + 1})")
                    response = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            response_mime_type="application/json",
                            response_schema=TrilingualShortsPackage,
                            temperature=0.75,
                        ),
                    )
                    package_data = json.loads(response.text)
                    package = TrilingualShortsPackage(**package_data)

                    # Ensure Hindi and Gujarati titles are in native scripts (Devanagari and Gujarati)
                    package.hindi.title = self._ensure_native_title(package.hindi.title, "hi", package.english.title)
                    package.gujarati.title = self._ensure_native_title(package.gujarati.title, "gu", package.english.title)

                    # Validate strict all-ages compliance
                    validate_family_safe(f"{package.topic} {package.english.title} {package.english.voiceover_script} {package.visual_prompt}")

                    # Pre-publish quality scoring & targeted optimization for higher watch time/views/likes
                    mark_model_successful(model)
                    package = self._polish_trilingual_package(package, avoid_titles)

                    # Record topic history
                    record_topic_history(package.topic, package.english.title)
                    return package
                except Exception as e:
                    logger.warning(f"Model {model} failed for trilingual package: {e}.")
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        if self.rotate_api_key():
                            continue
                    break

        logger.warning("⚠️ All Gemini candidate models and API keys encountered rate limits (429/503). Activating autonomous high-retention Trilingual Shorts generator...")
        package = self._create_fallback_trilingual_package(chosen_pillar or specific_topic or "stoic mental resilience", avoid_titles=avoid_titles)
        record_topic_history(package.topic, package.english.title)
        return package

    def generate_script(self, niche: Optional[str] = None, specific_topic: Optional[str] = None, callback: Optional[Callable] = None) -> ShortsScript:
        # Pre-check network connectivity
        NetworkGuard.wait_for_network(callback=callback)
        niche = niche or config.DEFAULT_NICHE
        avoid_titles = self._get_avoid_titles()
        growth_intelligence = self.growth_engine.get_growth_prompt_context(content_format="shorts")
        
        history_instruction = ""
        if avoid_titles:
            formatted_history = "\n".join([f"- {t}" for t in avoid_titles[-20:]])
            history_instruction = f"""
CRITICAL UNIQUENESS REQUIREMENT:
You MUST generate a completely unique and novel topic that has NEVER been covered before.
DO NOT repeat or closely duplicate any of these recently generated or saturated videos:
{formatted_history}
"""

        # Intelligently select theme or topic
        chosen_topic = specific_topic or random.choice(EXPANDED_GROWTH_THEMES)
        chosen_topic_prompt = ""
        if specific_topic:
            chosen_topic_prompt = f"Specific Topic Requested: {specific_topic}"
        else:
            chosen_topic_prompt = (
                f"Theme Pillar: {chosen_topic}\n"
                "Create a fresh, mind-shifting, highly specific viral angle within this theme that immediately commands attention."
            )

        system_instruction = (
            "You are Gemini 4 Argon, Google's flagship reasoning engine, acting as an elite YouTube Shorts creator and scriptwriter specializing in high-performing, "
            "strictly all-ages, family-friendly content: "
            "Motivation, Discipline, Health & Fitness Science, Stoic Philosophy, and High-Performance Habits.\n\n"
            "Your tone is mature, authoritative, deeply inspiring, and grounded in real cognitive psychology, human physiology, and evolutionary biology. "
            "Deliver perspective-shifting truths, cognitive pattern interrupts, and actionable insights safe for viewers of all ages.\n\n"
            "STRICT CONTENT SAFETY RULES (ZERO 18+ / ZERO NUDE / ZERO SEXY TOLERANCE):\n"
            "1. NEVER generate content above 18+ age. Absolutely NO nude, porn, sexy, erotic, sensual, provocative, seductive, or revealing content under any circumstances.\n"
            "2. All content must be 100% wholesome, clean, and suitable for all audiences (strictly family-friendly, G/PG rating).\n"
            "3. GEMINI 4 ARGON HOOK & NARRATIVE REASONING:\n"
            "   - Scene 1 MUST be an irresistible 3-second psychological pattern-interrupt hook that halts scrolling instantly by challenging a widespread cognitive illusion.\n"
            "   - Scene 2 exposes the biological or behavioral trap.\n"
            "   - Scene 3 delivers the foundational 'Rule #1' law with undeniable clarity.\n"
            "   - Scene 4/5 provides the transformative execution step and compelling synthesis.\n"
            "4. Keep narration concise, punchy, conversational, and rhythmically paced (~110-140 words total across 4-6 scenes).\n"
            "5. Visual prompts MUST feature PEOPLE OR THINGS ACTIVELY TALKING & GIVING PROPER SIGNS:\n"
            "   - Every scene must prominently feature a person or personified entity (mentor, stoic coach, ancient philosopher, or living statue/artifact) actively speaking directly to the camera with mouth open in mid-speech, engaging vocal facial animation, and dynamic eye contact.\n"
            "   - Every scene must make a clear authoritative physical sign/gesture (e.g. Scene 1: STOP hand sign 🛑 or pointing at viewer 👉; Scene 2: warning sign pointing to clock/flaw; Scene 3: Rule #1 finger up ☝️; Scene 4: pointing down to subscribe 👇).\n"
            "   - Every scene must define a short punchy on-screen signboard badge text ('sign_badge', e.g. '🛑 STOP THIS', '🧠 RULE #1', '🎯 100% FOCUS', '👇 ACT NOW').\n"
            "   - Style: 9:16 vertical, ultra-photorealistic cinema still shot on ARRI Alexa LF, 35mm anamorphic prime lens, T1.5 shallow depth of field, authentic natural skin pores, realistic eye moisture, subtle rim lighting, strictly modest fully clothed attire, zero nudity, zero sexy elements, NO text drawn inside the image.\n"
            "6. NEVER include on-screen text instructions inside the visual prompt.\n"
            "7. The final scene must provide a powerful takeaway and seamlessly loop back to the start or ask a compelling question."
        )

        prompt = f"""
Generate an exceptional and 100% UNIQUE YouTube Short script powered by Gemini 4 Argon reasoning.

Target Audience: All Ages & High-Performers (Motivation, Fitness, Health, Stoicism, Discipline - Strictly Family-Friendly & Clean).
Niche/Theme: {niche}
{chosen_topic_prompt}
{growth_intelligence}
{history_instruction}

STRICT REQUIREMENT: Absolutely NO 18+ or adult content. 100% safe, clean, and family-friendly.

Requirements:
- 4 to 6 scenes total.
- Total narration word count ~100-140 words (35-50 second pace).
- Title must be punchy (< 70 chars) with strong curiosity/mindset hook + ends with #Shorts.
- Description includes 2 short paragraphs + top hashtags (#Motivation, #Fitness, #Discipline, #Mindset, #Shorts).
- 10-15 high-ranking YouTube keyword tags.
- Category ID default: "{config.DEFAULT_CATEGORY_ID}" (Education/Self-Improvement).
- Pinned comment to ignite debate/discussion.
"""

        candidate_models = get_candidate_models(preferred=self.model_name, tier="argon")

        last_error = None
        for model in candidate_models:
            for key_attempt in range(len(self.api_keys)):
                try:
                    logger.info(f"Generating YouTube Shorts script using Gemini model: {model} (key #{self.current_key_idx + 1})")
                    response = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            response_mime_type="application/json",
                            response_schema=ShortsScript,
                            temperature=0.8,
                        ),
                    )
                    raw_text = response.text
                    script_data = json.loads(raw_text)
                    script = ShortsScript(**script_data)

                    # Validate strict all-ages compliance
                    full_text = f"{script.topic} {script.title} {script.description} " + " ".join(s.narration + " " + s.visual_prompt for s in script.scenes)
                    validate_family_safe(full_text)
                    mark_model_successful(model)

                    audit = self._audit_short_quality(script, avoid_titles)
                    logger.info(f"📊 [Short Quality Audit] Faceless={audit['faceless_score']}/100 | Hook={audit['hook_score']}/100")

                    # Record to history for future uniqueness
                    record_topic_history(script.topic, script.title)
                    return script
                except Exception as e:
                    logger.warning(f"Model {model} failed with: {e}.")
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        if self.rotate_api_key():
                            continue
                    last_error = e
                    break

        logger.warning(f"⚠️ All Gemini models and API keys encountered rate limits (429/503): {last_error}. Activating autonomous high-retention Shorts script generator...")
        script = self._create_fallback_shorts_script(chosen_topic, avoid_titles=avoid_titles)
        record_topic_history(script.topic, script.title)
        return script

    def generate_long_video_script(
        self,
        topic: Optional[str] = None,
        seed_topic: Optional[str] = None,
        callback: Optional[Callable] = None,
    ) -> LongVideoScript:
        """
        Generates a comprehensive standard YouTube video script (16:9 widescreen, 2-4 minutes)
        with multi-scene sequential chapters, timestamps, custom thumbnail specifications,
        and high-converting SEO metadata powered by Gemini 4 Argon deep reasoning.
        """
        NetworkGuard.wait_for_network(callback=callback)
        avoid_titles = self._get_avoid_titles()
        growth_intelligence = self.growth_engine.get_growth_prompt_context(content_format="long")

        chosen_topic = topic or seed_topic or random.choice(EXPANDED_GROWTH_THEMES)

        history_instruction = ""
        if avoid_titles and not topic:
            formatted_history = "\n".join([f"- {t}" for t in avoid_titles[-20:]])
            history_instruction = f"""
CRITICAL UNIQUENESS REQUIREMENT:
Ensure this topic and title are 100% unique and fresh. NEVER repeat generic 'Masterclass Guide' titles or any of these:
{formatted_history}
"""

        system_instruction = (
            "You are Gemini 4 Argon, Google's flagship reasoning engine, acting as an elite YouTube retention & packaging producer.\n"
            "Your task is to generate a complete, high-CTR STANDARD YouTube landscape video script (16:9 widescreen, 2 to 4 minutes total duration) engineered to maximize WATCH HOURS, CTR, and LIKES.\n"
            "Focus on: High-Performance Growth Mindset, Stoic Philosophy, Health & Fitness Science, Mental Resilience, and Peak Daily Discipline.\n"
            "The tone must be clean, authoritative, grounded in real physiology/psychology, and suitable for all ages.\n\n"
            f"{config.SAFETY_GUARDRAILS}\n\n"
            "STRICT AGE-APPROPRIATE & ZERO-TOLERANCE POLICY (NO 18+, NO NUDE, NO PORN, NO SEXY CONTENT):\n"
            "- All content (title, description, timestamps, narration, thumbnail prompt, and scene prompts) MUST be 100% clean and suitable for all ages (G/PG rating).\n"
            "- Strictly NO adult references, nudity, sexy/provocative clothing, revealing cleavage, bare chest, shirtless figures, profanity, vulgarity, violence, weapons, alcohol, or illicit topics.\n\n"
            "WATCH-HOURS & CHAPTER RETENTION ARCHITECTURE:\n"
            "Construct a coherent, high-retention 6 to 9 scene progression:\n"
            "1. Scene 1 (Cold-Open Hook 00:00): Start in seconds 0-10 addressing 'you' directly with undeniable stakes or a sharp cognitive paradox (NEVER start with 'Most people believe' or 'In this video').\n"
            "2. Scene 2 (The Hidden Biological Trap): Unmask what silently drains energy/focus, ending with an open loop into the next chapter.\n"
            "3. Scene 3 (The Real Cost): Concrete cost of staying stuck, keeping viewers hooked.\n"
            "4. Scene 4 (The Core Shift / Rule #1): Deliver the surprising scientific mechanism.\n"
            "5. Scene 5 & 6 (Step-by-Step Protocol): 2-3 immediate actions viewers can apply today.\n"
            "6. Scene 7+ (Payoff & Final Question): Synthesize + invite comments to boost algorithm signals.\n\n"
            "PACKAGING & THUMBNAIL RULES (TITLE + THUMBNAIL = 1 UNIT):\n"
            "- Title: Under 58 characters, concrete curiosity/number/stakes, NO generic 'Masterclass Guide' or vague 'Definitive' fluff (NO #Shorts tag).\n"
            "- Thumbnail_Headline: MAX 3 bold words using COMPLETELY DIFFERENT words from the title (e.g. Title='3 Habits Destroying Your Focus' -> Thumb='FIX THIS NOW').\n"
            "- Thumbnail_Accent: Short 3-4 word secondary kicker below headline specific to this topic (e.g. 'SCIENCE EXPLAINED', 'NO WILLPOWER NEEDED').\n"
            "- Thumbnail_Visual_Prompt: Detailed prompt for a 16:9 cinematic landscape thumbnail visual with clear dark negative space on the left third for text overlay.\n"
            "- Scenes: 6 to 9 scenes, each with ~40-65 words of spoken narration, and a photorealistic 16:9 widescreen cinematic visual prompt shot on ARRI Alexa LF, 35mm anamorphic prime lens, 16:9 horizontal framing, natural cinematic lighting, strictly family-friendly attire, NO text inside images."
        )

        prompt = f"""
Generate a complete, high-impact Standard YouTube Landscape Video script (16:9 format).

Core Topic: {chosen_topic}
{growth_intelligence}
{history_instruction}

Ensure complete chapter breakdown with timestamps in description.
Enforce strict all-ages / family-friendly standards (zero 18+ content).
"""
        candidate_models = get_candidate_models(preferred=self.model_name, tier="argon")

        last_error = None
        for model in candidate_models:
            for key_attempt in range(len(self.api_keys)):
                try:
                    logger.info(f"Generating Standard YouTube Video script using Gemini model: {model} (key #{self.current_key_idx + 1})")
                    response = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            response_mime_type="application/json",
                            response_schema=LongVideoScript,
                            temperature=0.75,
                        ),
                    )
                    raw_text = response.text
                    script_data = json.loads(raw_text)
                    script = LongVideoScript(**script_data)

                    # Validate strict all-ages compliance
                    full_text = f"{script.topic} {script.title} {script.description} {script.thumbnail_headline} " + " ".join(s.narration + " " + s.visual_prompt for s in script.scenes)
                    validate_family_safe(full_text)
                    mark_model_successful(model)
                    script = self._polish_long_script(script, avoid_titles)

                    record_topic_history(script.topic, script.title)
                    return script
                except Exception as e:
                    logger.warning(f"Model {model} failed for long video script: {e}.")
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        if self.rotate_api_key():
                            continue
                    last_error = e
                    break

        logger.warning(f"⚠️ All Gemini models and API keys encountered rate limits or errors: {last_error}. Activating autonomous high-quality standard video script generator...")
        script = self._create_fallback_long_video_script(chosen_topic, avoid_titles=avoid_titles)
        record_topic_history(script.topic, script.title)
        return script

    def _create_fallback_long_video_script(self, topic: str, avoid_titles: Optional[List[str]] = None) -> LongVideoScript:
        """
        Constructs a unique, high-CTR, family-safe LongVideoScript when Gemini API quota
        is temporarily exceeded, varying title & framing to avoid duplicate uploads.
        """
        avoid = avoid_titles or self._get_avoid_titles()
        raw_clean = re.sub(r"[^a-zA-Z0-9\s,&:-]", "", (topic or "Unshakeable Daily Focus")).strip()
        short_focus = " ".join(raw_clean.split()[:5]).title() or "Deep Focus"

        title_candidates = [
            (f"Why Your Brain Loses {short_focus} (And 3 Fixes)", "STOP LOSING TIME", "3 BIOLOGY SHIFTS"),
            (f"The 3 Habits Silently Killing Your {short_focus}", "SILENT DRAIN", "FIX IT IN 7 DAYS"),
            (f"How High Performers Build {short_focus} Daily", "BRAIN RESET", "ZERO EXCUSES"),
            (f"5 Minutes to Rewire {short_focus} Forever", "5 MIN RULE", "PROVEN HABIT LOOP"),
            (f"Why Willpower Fails on {short_focus} - Science", "NOT LAZINESS", "DOPAMINE TRUTH"),
        ]
        chosen_title, headline, accent = title_candidates[0]
        for cand_title, cand_hl, cand_acc in title_candidates:
            if not is_repetitive_title(cand_title, avoid):
                chosen_title, headline, accent = cand_title, cand_hl, cand_acc
                break
        if is_repetitive_title(chosen_title, avoid):
            chosen_title = f"{short_focus}: 3 Habits That Work ({time.strftime('%b %d')})"[:58]

        description = f"""{chosen_title}

You are not lazy - your environment drains your focus before work even begins. Here is the exact 3-step science breakdown for mastering {short_focus} and keeping steady clarity all day.

CHAPTER TIMESTAMPS:
00:00 - Why You Lose Energy Before Noon
00:25 - The Hidden Dopamine Drain
00:55 - Why Forcing Willpower Backfires
01:30 - The 3-Step Daily Protocol
02:10 - How Consistency Compounds in 30 Days

Subscribe to Daily Growth for practical breakdowns in focus, health, and stoic discipline!

#SelfImprovement #Focus #Discipline #Psychology #DailyGrowth #Habits"""

        tags = [
            "self improvement", "focus habits", "discipline", "dopamine detox",
            "stoic mindset", "daily growth", "mental clarity", "productivity science",
            "morning routine", "high performance", "how to focus",
        ]

        scenes = [
            LongVideoScene(
                scene_number=1,
                chapter_title="00:00 - Why You Lose Energy Before Noon",
                narration=(
                    f"If you wake up already behind and lose your focus by afternoon, it is not a lack of willpower. "
                    f"Every micro-distraction steals cognitive bandwidth before you ever start your real work on {short_focus}. "
                    f"Stay with me for two minutes, because fixing step one changes your entire day."
                ),
                visual_prompt=(
                    "Cinematic 16:9 widescreen shot of a focused mentor in dark wool coat at a clean sunlit desk, "
                    "intense eye contact directly toward viewer, warm dramatic morning shadows, ARRI Alexa LF, 35mm anamorphic lens, 8k, no text"
                ),
                estimated_duration_sec=16.0,
            ),
            LongVideoScene(
                scene_number=2,
                chapter_title="00:25 - The Hidden Dopamine Drain",
                narration=(
                    "Here is the trap 90% of people miss: checking fast feeds or constant alerts floods your brain with cheap stimulation. "
                    "Once your baseline spikes early, deep work feels physically painful. "
                    "Your brain is not broken - it is simply chasing the easiest stimulus in the room."
                ),
                visual_prompt=(
                    "Cinematic 16:9 landscape view of dramatic storm clouds parting over calm pine mountains at dawn, "
                    "sharp crisp shadows, golden hour rim lighting, ARRI Alexa LF, 35mm lens, documentary realism, 8k, no text"
                ),
                estimated_duration_sec=17.0,
            ),
            LongVideoScene(
                scene_number=3,
                chapter_title="00:55 - Why Willpower Backfires",
                narration=(
                    "Trying to brute-force discipline against a noisy environment burns willpower in under two hours. "
                    "Even the ancient Stoics knew calm control comes from designing friction away from bad habits, not relying on mood."
                ),
                visual_prompt=(
                    "Cinematic 16:9 widescreen shot of ancient stone columns bathed in crisp golden morning sunbeams, "
                    "quiet classical strength and architectural symmetry, ARRI Alexa LF, 35mm anamorphic lens, 8k, no text"
                ),
                estimated_duration_sec=16.0,
            ),
            LongVideoScene(
                scene_number=4,
                chapter_title="01:30 - The 3-Step Daily Protocol",
                narration=(
                    "First: delay all screens for 30 minutes after waking and hydrate with sunlight in your eyes. "
                    "Second: reduce friction so your most important task starts in 20 seconds flat. "
                    "Third: protect one 60-minute deep block daily before replying to anyone else's agenda."
                ),
                visual_prompt=(
                    "Cinematic 16:9 widescreen shot of a neat walnut study desk with an open journal, brass pen, and morning sunlight, "
                    "calm purposeful atmosphere, ARRI Alexa LF, 35mm anamorphic prime lens, 8k, no text"
                ),
                estimated_duration_sec=18.0,
            ),
            LongVideoScene(
                scene_number=5,
                chapter_title="02:10 - 30-Day Compounding",
                narration=(
                    f"Small daily wins in {short_focus} seem invisible on day one, then undeniable by day thirty. "
                    "Tell me in the comments which of those three steps you are locking in first today, "
                    "and subscribe for tomorrow's breakdown."
                ),
                visual_prompt=(
                    "Cinematic 16:9 wide shot of a hiker in modest jacket standing on a crisp granite ridge overlooking glowing sunrise valley, "
                    "epic hopeful horizon, ARRI Alexa LF, 35mm lens, 8k, no text"
                ),
                estimated_duration_sec=15.0,
            ),
        ]

        return LongVideoScript(
            topic=short_focus,
            title=chosen_title[:80],
            description=description,
            tags=tags,
            category_id=config.DEFAULT_CATEGORY_ID,
            thumbnail_headline=headline,
            thumbnail_accent=accent,
            thumbnail_visual_prompt=(
                "High-contrast 16:9 landscape thumbnail artwork of a determined mentor silhouetted with intense golden rim lighting "
                "on right half, deep dark clean negative space on left third for bold text, ARRI Alexa LF, 35mm lens, 8k, no text"
            ),
            scenes=scenes,
            pinned_comment=f"Which of the 3 steps for {short_focus} will you try tomorrow morning? Comment 1, 2, or 3 below!",
        )

    def _create_fallback_trilingual_package(self, topic: str) -> TrilingualShortsPackage:
        """
        Constructs a fresh, fast-paced, non-duplicate TrilingualShortsPackage
        across English, Hindi (Devanagari), and Gujarati when Gemini API quota
        is exhausted, selecting from a rotating multi-topic pool and filtering
        out saturated/recently uploaded titles.
        """
        avoid_titles = self._get_avoid_titles()
        presets = [
            {
                "keywords": ["sleep", "morning", "health", "energy", "vitality"],
                "theme_cat": "health_habits",
                "pillar": "Practical Daily Health Habits",
                "en_title": "Why 90% Wake Up Exhausted After 8 Hours #Shorts",
                "hi_title": "8 घंटे सोने के बाद भी थकान क्यों रहती है #Shorts",
                "gu_title": "8 કલાક ઊંઘ્યા પછી પણ થાક કેમ લાગે છે #Shorts",
                "en_s": [
                    "You slept eight full hours, yet your brain feels completely foggy.",
                    "A hidden 90-minute sleep cycle alarm just went off too late.",
                    "Waking mid-deep-sleep floods your prefrontal cortex with sleep inertia.",
                    "Set a 45-minute pre-bed screen curfew and cool room temperature tonight.",
                    "Follow that one clock tonight, and that is the exact reason...",
                ],
                "hi_s": [
                    "आठ घंटे सोने के बाद भी आपका दिमाग भारी और थका हुआ क्यों लगता है?",
                    "क्योंकि आप अपनी 90 मिनट की गहरी नींद के बीच में उठ रहे हैं।",
                    "अधूरी साइकिल में जागने से पूरा दिन आलस्य और थकान हावी रहती है।",
                    "आज रात सोने से 45 मिनट पहले फोन बंद करें और कमरा ठंडा रखें।",
                    "सही समय पर उठने की यह घड़ी समझ ली, तो यही असली कारण है कि...",
                ],
                "gu_s": [
                    "આઠ કલાકની પૂરી ઊંઘ પછી પણ સવારે મગજ ભારે કેમ લાગે છે?",
                    "કારણ કે તમે તમારી 90 મિનિટની ઊંડી ઊંઘની વચ્ચે જાગી જાઓ છો.",
                    "અધૂરી સાયકલમાં ઉઠવાથી આખો દિવસ સુસ્તી અને થાક લાગ્યા કરે છે.",
                    "આજે રાત્રે સૂવાના 45 મિનિટ પહેલાં ફોન બંધ કરી રૂમ ઠંડો રાખો.",
                    "જો આ ઊંઘનું ચક્ર સમજી લેશો, તો એ જ સાચું કારણ છે કે...",
                ],
                "poll_q": "What ruins your morning energy most often?",
                "poll_opts": ["Late phone scrolling", "Irregular wake time", "Heavy late dinner", "Waking mid-cycle"],
            },
            {
                "keywords": ["money", "financ", "wealth", "rich", "spend"],
                "theme_cat": "financial_discipline",
                "pillar": "Realistic Financial Discipline",
                "en_title": "The 72-Hour Rule Quiet Millionaires Swear By #Shorts",
                "hi_title": "पैसा बचाने का 72 घंटे वाला गुप्त नियम #Shorts",
                "gu_title": "પૈસા બચાવવાનો 72 કલાકનો અનોખો નિયમ #Shorts",
                "en_s": [
                    "Most paychecks vanish on things you barely remember three days later.",
                    "Impulse buying hijacks dopamine right before your logic wakes up.",
                    "Wait 72 hours before pressing buy on any want over fifty dollars.",
                    "Nine times out of ten, the urge drops to zero while your savings grow.",
                    "Try this quiet pause for thirty days, and notice how fast...",
                ],
                "hi_s": [
                    "ज्यादातर कमाई ऐसी चीजों में चली जाती है जिन्हें आप तीन दिन बाद भूल जाते हैं।",
                    "जल्दबाजी की खरीदारी दिमाग को भ्रम में डालकर जेब खाली कर देती है।",
                    "किसी भी गैर-जरूरी खरीद से पहले पूरे 72 घंटे का इंतजार करना शुरू करें।",
                    "नब्बे प्रतिशत मामलों में इच्छा खत्म हो जाती है और बचत बढ़ने लगती है।",
                    "तीस दिन इस शांत नियम को आजमाएं, फिर खुद देखें कि कैसे...",
                ],
                "gu_s": [
                    "મોટાભાગની કમાણી એવી વસ્તુઓમાં વપરાઈ જાય છે જે ત્રણ દિવસમાં ભૂલાઈ જાય છે.",
                    "ઉતાવળી ખરીદી મગજના આવેગનો ફાયદો ઉઠાવી ખિસ્સું ખાલી કરી દે છે.",
                    "કોઈ પણ બિનજરૂરી વસ્તુ ખરીદતા પહેલા પૂરા 72 કલાક રાહ જોવાની ટેવ પાડો.",
                    "નવ્વાણું ટકા કિસ્સામાં ખરીદવાની ઈચ્છા ઓગળી જશે અને બચત વધશે.",
                    "ત્રીસ દિવસ આ શાંત નિયમ અપનાવો, અને જુઓ કે કેવી રીતે...",
                ],
                "poll_q": "Which money habit helps you save the most?",
                "poll_opts": ["72-hour wait rule", "Auto-transfer on payday", "Cash-only weekends", "Tracking subscriptions"],
            },
            {
                "keywords": ["focus", "dopamine", "phone", "procrastin", "productiv"],
                "theme_cat": "focus_psychology",
                "pillar": "Deep Focus & Attention Mastery",
                "en_title": "Why 5 Minutes Of Boredom Fixes Broken Focus #Shorts",
                "hi_title": "5 मिनट बोर होने से दिमाग तेज कैसे होता है #Shorts",
                "gu_title": "5 મિનિટ શાંત બેસવાથી ફોકસ કેમ બમણું થાય છે #Shorts",
                "en_s": [
                    "You stare at work for an hour yet finish almost nothing meaningful.",
                    "Constant micro-scrolls keep your brain starved for cheap novelty.",
                    "Sit in silence for five plain minutes before opening your hardest task.",
                    "When stimulation drops, deep work suddenly feels effortless and clear.",
                    "Give your mind five empty minutes tomorrow morning, and see why...",
                ],
                "hi_s": [
                    "आप एक घंटे काम के सामने बैठते हैं, फिर भी काम पूरा क्यों नहीं होता?",
                    "बार-बार फोन देखने की आदत दिमाग की गहराई से सोचने की क्षमता घटाती है।",
                    "सबसे कठिन काम शुरू करने से पहले बस 5 मिनट बिना फोन चुपचाप बैठें।",
                    "जैसे ही शोर शांत होता है, दिमाग अपने आप एकाग्र होकर काम में लग जाता है।",
                    "कल सुबह अपने दिमाग को पांच शांत मिनट देकर देखें, और समझें कि...",
                ],
                "gu_s": [
                    "એક કલાક કામ સામે બેઠા પછી પણ અગત્યનું કામ કેમ પૂરું નથી થતું?",
                    "વારંવાર ફોન ચેક કરવાની ટેવ મગજની એકાગ્રતાને નબળી પાડી દે છે.",
                    "સૌથી અઘરું કામ શરૂ કરતા પહેલા માત્ર 5 મિનિટ ફોન વિના શાંત બેસો.",
                    "જ્યારે બાહ્ય શોર બંધ થાય છે, ત્યારે ઊંડું ધ્યાન આપમેળે લાગી જાય છે.",
                    "કાલે સવારે મગજને ફક્ત પાંચ ખાલી મિનિટ આપો, અને જુઓ કે...",
                ],
                "poll_q": "What kills your deep work streak fastest?",
                "poll_opts": ["Phone notifications", "Tab switching", "Unclear first step", "Mental fatigue"],
            },
            {
                "keywords": ["stoic", "calm", "anger", "mind", "stress", "resilien"],
                "theme_cat": "stoic_resilience",
                "pillar": "Stoic Mental Resilience",
                "en_title": "The 3-Second Stoic Trick That Disarms Any Insult #Shorts",
                "hi_title": "गुस्सा और अपमान शांत करने की 3-सेकंड की ट्रिक #Shorts",
                "gu_title": "ગુસ્સો અને અપમાન શાંત કરવાની 3-સેकન્ડની રીત #Shorts",
                "en_s": [
                    "One rude comment can hijack your mood for the entire afternoon.",
                    "Most people react instantly because ego hates leaving a word unanswered.",
                    "Look calmly at the person for three silent seconds before saying a word.",
                    "That pause shifts tension back onto them while your composure stays untouched.",
                    "Use silence before speaking next time, and that is exactly why...",
                ],
                "hi_s": [
                    "किसी की एक कड़वी बात आपका पूरा दिन बर्बाद कर सकती है।",
                    "अहंकार हर बात का तुरंत जवाब चाहता है और हम जाल में फंस जाते हैं।",
                    "जवाब देने से पहले बस तीन सेकंड शांत रहकर सामने वाले को देखें।",
                    "यह छोटा ठहराव सामने वाले की बेचैनी बढ़ाता है और आपकी शांति बचाता है।",
                    "अगली बार बोलने से पहले तीन सेकंड रुकें, और यही कारण है कि...",
                ],
                "gu_s": [
                    "કોઈની એક કડવી વાત તમારો આખો દિવસ બગાડી શકે છે.",
                    "આપણો અહંકાર તરત જવાબ આપવા દોડે છે અને આપણે જાળમાં ફસાઈએ છીએ.",
                    "જવાબ આપતા પહેલા માત્ર ત્રણ સેકન્ડ શાંત રહીને સામે જુઓ.",
                    "આ નાનો વિરામ તમારી શાંતિ જાળવી રાખે છે અને પરિસ્થિતિ સંભાળી લે છે.",
                    "આવતી વખતે બોલતા પહેલા ત્રણ સેકન્ડ થોભી જુઓ, એટલે સમજાશે કે...",
                ],
                "poll_q": "How do you stay calm during unfair criticism?",
                "poll_opts": ["Pause 3 seconds", "Ask a calm question", "Walk away briefly", "Reframe objectively"],
            },
            {
                "keywords": ["respect", "charisma", "speak", "social", "confiden"],
                "theme_cat": "communication_charisma",
                "pillar": "Respect & Communication Mastery",
                "en_title": "One Vocal Shift That Commands Instant Respect #Shorts",
                "hi_title": "बोलने का यह छोटा बदलाव तुरंत सम्मान दिलाता है #Shorts",
                "gu_title": "બોલવાનો આ નાનો ફેરફાર તરત માન અપાવે છે #Shorts",
                "en_s": [
                    "Talking faster makes smart ideas sound nervous and easily ignored.",
                    "High-status communicators let the end of each sentence land downward cleanly.",
                    "Drop upward inflection on statements and hold eye contact half a beat longer.",
                    "People instinctively trust voices that sound unhurried under pressure.",
                    "Slow your last three words today, and remember why...",
                ],
                "hi_s": [
                    "तेज गति से बोलने पर सही बात भी घबराई हुई और कमजोर लगती है।",
                    "प्रभावशाली लोग हर वाक्य के अंत में आवाज को स्थिर और स्पष्ट रखते हैं।",
                    "बात खत्म करते समय जल्दबाजी छोड़ें और एक सेकंड शांत नजर मिलाएं।",
                    "इंसानी दिमाग हमेशा शांत और सधे हुए स्वर पर तुरंत भरोसा करता है।",
                    "आज अपने वाक्य के आखिरी तीन शब्द धीरे बोलें, और याद रखें कि...",
                ],
                "gu_s": [
                    "ઝડપથી બોલવાથી સાચી વાત પણ ગભરાયેલી અને નબળી લાગે છે.",
                    "પ્રભાવશાળી લોકો દરેક વાક્યના અંતે અવાજને સ્થિર અને સ્પષ્ટ રાખે છે.",
                    "વાત પૂરી કરતી વખતે ઉતાવળ છોડો અને એક ક્ષણ શાંત નજર મિલાવો.",
                    "દરેક વ્યક્તિ શાંત અને ધીરજવાળા અવાજ પર તરત જ વિશ્વાસ મૂકે છે.",
                    "આજે તમારા વાક્યના છેલ્લા ત્રણ શબ્દો ધીમે બોલો, અને જુઓ કે...",
                ],
                "poll_q": "Which communication skill do you want to master next?",
                "poll_opts": ["Slower vocal pacing", "Holding eye contact", "Saying no politely", "Storytelling clarity"],
            },
            {
                "keywords": ["habit", "discipline", "gym", "consisten", "routine"],
                "theme_cat": "habit_architecture",
                "pillar": "Habit & Identity Architecture",
                "en_title": "The Two-Day Rule That Never Breaks A Habit Streak #Shorts",
                "hi_title": "आदत न टूटने देने का अचूक 2-दिन वाला नियम #Shorts",
                "gu_title": "સારી ટેવ ક્યારેય ન તૂટે તેનો 2-દિવસનો નિયમ #Shorts",
                "en_s": [
                    "One missed workout quietly turns into quitting for three whole months.",
                    "Perfectionism fools you into thinking a bad day means starting over.",
                    "Never miss twice: do a five-minute minimum version on tough days.",
                    "Showing up briefly keeps the neural habit wire alive all year.",
                    "Protect day two at all costs, and you will see why...",
                ],
                "hi_s": [
                    "एक दिन की छुट्टी धीरे-धीरे तीन महीने के आलस्य में बदल जाती है।",
                    "परफेक्शन की सोच हमें छोटे प्रयास करने से रोकती है।",
                    "कभी लगातार दो दिन मत छोड़िए: व्यस्त दिन भी पांच मिनट जरूर करें।",
                    "छोटा सा प्रयास पूरे साल आपकी आदत की डोर को टूटने नहीं देता।",
                    "दूसरे दिन को किसी भी कीमत पर बचा लें, फिर देखिए कि कैसे...",
                ],
                "gu_s": [
                    "એક દિવસની છૂટછાટ ધીમે ધીમે ત્રણ મહિનાની આળસમાં ફેરવાઈ જાય છે.",
                    "બધું પરફેક્ટ કરવાની જીદ આપણને નાના પ્રયાસોથી પણ દૂર રાખે છે.",
                    "ક્યારેય સતત બે દિવસ ન ચૂકો: વ્યસ્ત દિવસે પણ પાંચ મિનિટ જરૂર કરો.",
                    "નાનકડું સાતત્ય આખું વર્ષ તમારી સારી ટેવને જીવંત રાખે છે.",
                    "બીજા દિવસને કોઈ પણ ભોગે જાળવી રાખો, અને પછી જુઓ કે...",
                ],
                "poll_q": "How do you recover after missing a habit day?",
                "poll_opts": ["Never miss twice rule", "5-minute minimum", "Lower daily friction", "Restart next morning"],
            },
        ]

        topic_lower = (topic or "").lower()
        fresh_presets = [
            p for p in presets
            if not is_repetitive_title(p["en_title"], avoid_titles)
        ] or presets

        matched = [
            p for p in fresh_presets
            if any(k in topic_lower for k in p["keywords"])
        ]
        if matched:
            chosen = matched[int(time.time()) % len(matched)]
        else:
            chosen = fresh_presets[int(time.time() // 60) % len(fresh_presets)]

        theme_cat = chosen["theme_cat"]
        pillar_name = chosen["pillar"]
        base_prompt = (
            "Cinematic 9:16 vertical editorial film frame, natural warm key lighting, "
            "shallow depth of field, 35mm documentary realism, 8k detail, strictly all-ages safe, no text overlay"
        )
        scene_styles = [
            "disciplined person pausing with intense realization near sunlit desk, looking toward camera",
            "close-up macro atmospheric shot of glowing mechanical clockwork gears and hourglass sand",
            "clean minimalist study table with notebook, pen, and dramatic shadow geometry",
            "calm silhouette standing by tall window overlooking sunrise city skyline",
            "confident composed mentor walking forward with warm golden rim light",
        ]
        badges_map = {
            "en": ["🛑 WAIT", "🧠 THE TRAP", "⚡ SHIFT", "✅ DO THIS", "🔁 LOOP"],
            "hi": ["🛑 ध्यान दें", "🧠 असली सच", "⚡ नियम", "✅ आज करें", "🔁 याद रखें"],
            "gu": ["🛑 સાવધાન", "🧠 સાચું કારણ", "⚡ નિયમ", "✅ આ કરો", "🔁 યાદ રાખો"],
        }

        def _make_lang_scenes(lines: List[str], lang_code: str) -> List[Scene]:
            durations = [3.8, 3.8, 4.0, 4.0, 3.6]
            badges = badges_map[lang_code]
            return [
                Scene(
                    scene_number=idx + 1,
                    narration=lines[idx],
                    speaker_entity="Disciplined Mentor",
                    speaking_action="Delivering concise point directly with expressive posture",
                    proper_sign=f"Visual emphasis cue #{idx + 1}",
                    sign_badge=badges[idx],
                    visual_prompt=f"{base_prompt}, {scene_styles[idx]}",
                    estimated_duration_sec=durations[idx],
                )
                for idx in range(5)
            ]

        en_vo = " ".join(chosen["en_s"])
        hi_vo = " ".join(chosen["hi_s"])
        gu_vo = " ".join(chosen["gu_s"])

        poll = CommunityPoll(
            question=chosen["poll_q"],
            options=chosen["poll_opts"],
            post_text=f"{chosen['poll_q']} Share your pick below! #DailyGrowth #Mindset",
        )

        english_pkg = LanguageScript(
            language="en",
            title=chosen["en_title"],
            description=f"{chosen['en_s'][0]} {chosen['en_s'][2]} Subscribe to Daily Growth for practical daily psychology.",
            hashtags="#mindset #discipline #DailyGrowth #psychology #Shorts",
            tags=["Daily Growth", pillar_name, "Self Improvement", "Psychology", "Shorts"],
            voiceover_script=en_vo,
            scenes=_make_lang_scenes(chosen["en_s"], "en"),
        )
        hindi_pkg = LanguageScript(
            language="hi",
            title=chosen["hi_title"],
            description=f"{chosen['hi_s'][0]} {chosen['hi_s'][2]} डेली ग्रोथ को सब्सक्राइब करें।",
            hashtags="#motivation #mindset #DailyGrowth #hindi #Shorts",
            tags=["डेली ग्रोथ", "आत्म विकास", "मानसिक मजबूती", "प्रेरणा", "शॉर्ट्स"],
            voiceover_script=hi_vo,
            scenes=_make_lang_scenes(chosen["hi_s"], "hi"),
        )
        gujarati_pkg = LanguageScript(
            language="gu",
            title=chosen["gu_title"],
            description=f"{chosen['gu_s'][0]} {chosen['gu_s'][2]} ડેઇલી ગ્રોથને સબ્સ્ક્રાઇબ કરો.",
            hashtags="#gujarati #motivation #DailyGrowth #mindset #Shorts",
            tags=["ડેઇલી ગ્રોથ", "પ્રેરણા", "માનસિક શાંતિ", "આત્મવિશ્વાસ", "શોર્ટસ"],
            voiceover_script=gu_vo,
            scenes=_make_lang_scenes(chosen["gu_s"], "gu"),
        )

        return TrilingualShortsPackage(
            topic=pillar_name,
            theme_category=theme_cat,
            visual_prompt=base_prompt,
            english=english_pkg,
            hindi=hindi_pkg,
            gujarati=gujarati_pkg,
            community_poll=poll,
        )

    def _create_fallback_shorts_script(self, topic: str) -> ShortsScript:
        """
        Constructs an elite single ShortsScript when Gemini API quota is reached.
        """
        trilingual_fallback = self._create_fallback_trilingual_package(topic)
        en = trilingual_fallback.english
        return ShortsScript(
            topic=trilingual_fallback.topic,
            title=en.title,
            description=en.description,
            tags=en.tags,
            category_id=config.DEFAULT_CATEGORY_ID,
            pinned_comment="Which rule are you testing today? Comment below!",
            scenes=en.scenes,
            community_poll=trilingual_fallback.community_poll,
        )
