import json
import logging
import random
from pathlib import Path
from typing import List, Optional, Callable
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

import config
from growth.model_resolver import get_candidate_models

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
        description="Short, punchy 3-5 word high-contrast text to display boldly on the 16:9 thumbnail (e.g., 'THE DOPAMINE GLITCH', 'NEVER BE LAZY AGAIN', 'RULE #1 OF WILLPOWER')"
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

        self.client = genai.Client(api_key=self.api_key)
        self.growth_engine = GrowthEngine(api_key=self.api_key)

    def rotate_api_key(self) -> bool:
        """Rotates to next available GEMINI_API_KEY if multiple are provided."""
        if len(self.api_keys) > 1:
            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            self.api_key = self.api_keys[self.current_key_idx]
            self.client = genai.Client(api_key=self.api_key)
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

    def generate_trilingual_script(self, specific_topic: Optional[str] = None, callback: Optional[Callable] = None) -> TrilingualShortsPackage:
        """
        Generates a synchronized 3-language video package (English, Hindi, Gujarati)
        in a SINGLE prompt call, focused on stoic resilience, daily health, or financial discipline.
        """
        NetworkGuard.wait_for_network(callback=callback)
        past_topics = get_topic_history()
        growth_intelligence = self.growth_engine.get_growth_prompt_context()

        # Target Pillars
        trilingual_pillars = [
            "stoic mental resilience, unshakeable inner peace, and nature's living endurance under pressure",
            "practical daily health habits, biological energy optimization, and natural vitality",
            "realistic financial discipline, compounding micro-money rules, and sustainable growth",
            "lessons from apex predators and wild living creatures: focus, grit, and survival mastery",
        ]
        chosen_pillar = specific_topic or random.choice(trilingual_pillars)

        history_instruction = ""
        if past_topics:
            formatted_history = "\n".join([f"- {t}" for t in past_topics[-15:]])
            history_instruction = f"""
CRITICAL UNIQUENESS REQUIREMENT:
Ensure this topic is 100% unique and does not repeat:
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
            "- Voiceover_Script: The exact spoken text for a 45-60 second video (~120-140 words total) with a strong hook in the first 3 seconds.\n"
            "- Scenes: 4 to 5 timed scenes breaking down the voiceover script with matching cinematic 9:16 visual prompts.\n"
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
        package = self._create_fallback_trilingual_package(chosen_pillar or specific_topic or "stoic mental resilience")
        record_topic_history(package.topic, package.english.title)
        return package

    def generate_script(self, niche: Optional[str] = None, specific_topic: Optional[str] = None, callback: Optional[Callable] = None) -> ShortsScript:
        # Pre-check network connectivity
        NetworkGuard.wait_for_network(callback=callback)
        niche = niche or config.DEFAULT_NICHE
        past_topics = get_topic_history()
        growth_intelligence = self.growth_engine.get_growth_prompt_context()
        
        history_instruction = ""
        if past_topics:
            formatted_history = "\n".join([f"- {t}" for t in past_topics[-15:]])
            history_instruction = f"""
CRITICAL UNIQUENESS REQUIREMENT:
You MUST generate a completely unique and novel topic that has NEVER been covered before.
DO NOT repeat or closely duplicate any of these recently generated videos:
{formatted_history}
"""

        # Intelligently select theme or topic
        chosen_topic_prompt = ""
        if specific_topic:
            chosen_topic_prompt = f"Specific Topic Requested: {specific_topic}"
        else:
            selected_theme = random.choice(EXPANDED_GROWTH_THEMES)
            chosen_topic_prompt = (
                f"Theme Pillar: {selected_theme}\n"
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
        script = self._create_fallback_shorts_script(chosen_topic)
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
        past_topics = get_topic_history()
        growth_intelligence = self.growth_engine.get_growth_prompt_context()

        chosen_topic = topic or seed_topic or random.choice(EXPANDED_GROWTH_THEMES)

        history_instruction = ""
        if past_topics and not topic:
            formatted_history = "\n".join([f"- {t}" for t in past_topics[-15:]])
            history_instruction = f"""
CRITICAL UNIQUENESS REQUIREMENT:
Ensure this topic is 100% unique and fresh. Do not duplicate recent concepts:
{formatted_history}
"""

        system_instruction = (
            "You are Gemini 4 Argon, Google's flagship reasoning engine, acting as a masterclass YouTube producer.\n"
            "Your task is to generate a complete, viral-ready STANDARD YouTube landscape video script (16:9 widescreen, 2 to 4 minutes total duration).\n"
            "Focus on: High-Performance Growth Mindset, Stoic Philosophy, Health & Fitness Science, Mental Resilience, and Peak Daily Discipline.\n"
            "The tone must be clean, authoritative, intellectually deep, grounded in real physiology/psychology, and suitable for all ages.\n\n"
            f"{config.SAFETY_GUARDRAILS}\n\n"
            "STRICT AGE-APPROPRIATE & ZERO-TOLERANCE POLICY (NO 18+, NO NUDE, NO PORN, NO SEXY CONTENT):\n"
            "- All content (title, description, timestamps, narration, thumbnail prompt, and scene prompts) MUST be 100% clean and suitable for all ages (G/PG rating).\n"
            "- Strictly NO adult references, nudity, sexy/provocative clothing, revealing cleavage, bare chest, shirtless figures, profanity, vulgarity, violence, weapons, alcohol, or illicit topics.\n\n"
            "GEMINI 4 ARGON DEEP REASONING & CHAPTER NARRATIVE STRUCTURE:\n"
            "Construct a coherent, high-retention 6 to 10 scene progression:\n"
            "1. Scene 1 (The Hook & Provocative Premise): 00:00 - Introduction. Arrest viewer attention with an inescapable cognitive paradox or counter-intuitive reality.\n"
            "2. Scene 2 (The Evolutionary / Neurological Flaw): Unmask the biological trap or common misconception that sabotages most people.\n"
            "3. Scene 3 (The Cost of Inaction): Illustrate the compounding negative trajectory of continuing down the default path.\n"
            "4. Scene 4 (The Sovereign Principle / Rule #1): Reveal the foundational paradigm shift or scientific law.\n"
            "5. Scene 5 & 6 (The Tactical Step-by-Step Protocol): Concrete, daily actionable micro-habits that viewers can execute immediately.\n"
            "6. Scene 7+ (The Compounding Payoff & Lifelong Mastery): Deliver the inspiring climax, synthesis, and an empowering call to action.\n\n"
            "METADATA & THUMBNAIL REQUIREMENTS:\n"
            "- Title: High-converting, curiosity-driven YouTube video title under 80 characters (NO #Shorts tag).\n"
            "- Description: Structured YouTube long-form description with:\n"
            "  * 2-3 sentence overview of the video's core value.\n"
            "  * Formatted timestamps and chapter breakdown (e.g. '00:00 - Introduction\\n00:30 - The Invisible Trap\\n01:15 - Rule #1 of Discipline\\n...').\n"
            "  * Key Takeaways bullet points.\n"
            "  * Call to action to subscribe and comment.\n"
            "  * 5-8 relevant hashtags (#SelfImprovement #Mindset #Discipline #Psychology #Education).\n"
            "- Tags: 15-20 high-value YouTube search keyword tags.\n"
            "- Thumbnail_Headline: 3-5 bold, punchy words for the 16:9 thumbnail text overlay (e.g. 'THE DOPAMINE TRAP', 'RULE #1 OF WILLPOWER', 'STOP WASTING YEARS').\n"
            "- Thumbnail_Visual_Prompt: Detailed prompt for a 16:9 cinematic landscape thumbnail visual with clear negative space for text overlay.\n"
            "- Scenes: 6 to 10 scenes, each with ~40-70 words of spoken narration, and a photorealistic 16:9 widescreen cinematic visual prompt shot on ARRI Alexa LF, 35mm anamorphic prime lens, 16:9 horizontal framing, natural cinematic lighting, authentic skin textures and material physics, strictly family-friendly attire, NO text drawn inside the image itself."
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
        script = self._create_fallback_long_video_script(chosen_topic)
        record_topic_history(script.topic, script.title)
        return script

    def _create_fallback_long_video_script(self, topic: str) -> LongVideoScript:
        """
        Constructs an elite, 100% all-ages, family-safe LongVideoScript when Gemini API
        quota (429 RESOURCE_EXHAUSTED) is temporarily exceeded.
        """
        clean_topic = topic.strip().title() if topic else "Stoic Resilience & Unshakeable Focus"
        title = f"{clean_topic}: The Definitive Masterclass Guide"
        headline = "UNBREAKABLE MIND"
        if "focus" in clean_topic.lower() or "dopamine" in clean_topic.lower():
            headline = "PEAK FOCUS PROTOCOL"
        elif "habit" in clean_topic.lower() or "discipline" in clean_topic.lower():
            headline = "RULE #1 DISCIPLINE"

        description = f"""{title}

Master your habits, focus, and mindset with this comprehensive deep-dive. We explore the cognitive science, biological patterns, and practical daily protocols required to build unshakeable discipline.

CHAPTER TIMESTAMPS:
00:00 - Introduction & The Core Premise
00:25 - The Neurological Trap of Distraction
00:55 - The Sovereign Principle of Focus
01:30 - The 3-Step Daily Execution Protocol
02:10 - Lifelong Compounding & Final Synthesis

KEY TAKEAWAYS:
• Willpower is a biological resource that must be engineered through friction control.
• Clarity precedes action: reduce decision fatigue to execute without resistance.
• Consistency compounds exponentially over 90-day cycles.

Subscribe to Daily Growth for daily masterclasses in self-improvement and high performance!

#SelfImprovement #Mindset #Discipline #Productivity #Psychology #Stoicism #Education"""

        tags = [
            "self improvement", "productivity", "focus", "discipline",
            "stoicism", "daily growth", "motivation", "habits",
            "psychology", "mental resilience", "mindset mastery",
            "high performance", "deep work", "success habits"
        ]

        scenes = [
            LongVideoScene(
                scene_number=1,
                chapter_title="00:00 - Introduction & The Core Premise",
                narration=(
                    f"Most people believe success is a question of talent or luck. "
                    f"In reality, the secret lies in one foundational truth: your attention is your greatest currency. "
                    f"When you master {clean_topic}, external chaos loses its power over your direction."
                ),
                visual_prompt=(
                    "Cinematic 16:9 widescreen shot of a modern stoic mentor standing in a minimalist architecture library, "
                    "looking directly forward with focused clarity, warm afternoon sunlight casting dramatic soft shadows, "
                    "ARRI Alexa LF, 35mm anamorphic prime lens, T1.5 shallow depth of field, strictly fully clothed in tailored jacket, "
                    "photorealistic documentary cinematography, 8k resolution, no text"
                ),
                estimated_duration_sec=16.0,
            ),
            LongVideoScene(
                scene_number=2,
                chapter_title="00:25 - The Neurological Trap",
                narration=(
                    "The modern world is engineered to fragment your cognitive focus. "
                    "Every notification triggers a micro-release of dopamine, conditioning your brain to crave constant novelty. "
                    "This creates a state of perpetual shallow reaction rather than deliberate mastery."
                ),
                visual_prompt=(
                    "Cinematic 16:9 landscape view of an ancient marble sundial on a stone terrace overlooking misty mountains, "
                    "dramatic moody atmospheric fog, golden hour rim lighting, photorealistic material textures, "
                    "ARRI Alexa LF, 35mm lens, documentary realism, 8k, no text"
                ),
                estimated_duration_sec=18.0,
            ),
            LongVideoScene(
                scene_number=3,
                chapter_title="00:55 - The Sovereign Principle",
                narration=(
                    "The ancient Stoics discovered a timeless law: you cannot control external events, "
                    "but you have absolute sovereignty over your own response. "
                    "By detaching from immediate impulse and grounding yourself in deliberate daily execution, "
                    "you transform pressure into your greatest competitive advantage."
                ),
                visual_prompt=(
                    "Cinematic 16:9 widescreen composition, an ancient scholar walking along a majestic classical stone colonnade, "
                    "shafts of golden morning sunlight piercing through pillars, dramatic high contrast, "
                    "ARRI Alexa LF, 35mm anamorphic prime lens, cinematic realism, strictly clothed, 8k, no text"
                ),
                estimated_duration_sec=20.0,
            ),
            LongVideoScene(
                scene_number=4,
                chapter_title="01:30 - The Daily Protocol",
                narration=(
                    "Begin each day with sixty minutes of non-negotiable deep focus before checking any screen. "
                    "Protect your peak cognitive window fiercely. "
                    "Small, focused actions repeated with relentless consistency produce outcomes that look like magic to observers."
                ),
                visual_prompt=(
                    "Cinematic 16:9 widescreen still of a beautifully organized mahogany desk with a fountain pen and notebook, "
                    "warm glowing desk lamp, steam rising gently from a ceramic mug, serene early morning ambiance, "
                    "ARRI Alexa LF, 35mm anamorphic lens, 8k resolution, photorealistic, no text"
                ),
                estimated_duration_sec=18.0,
            ),
            LongVideoScene(
                scene_number=5,
                chapter_title="02:10 - Lifelong Compounding",
                narration=(
                    f"Mastery is not a finish line; it is a daily standard. "
                    f"Commit to the process of {clean_topic} today. "
                    f"Subscribe to Daily Growth, take control of your time, and build a life of quiet excellence."
                ),
                visual_prompt=(
                    "Cinematic 16:9 wide vista of a solitary figure standing atop a mountain ridge at sunrise, "
                    "golden light spreading across endless green valleys, inspiring horizon, "
                    "ARRI Alexa LF, 35mm anamorphic lens, epic cinematic documentary realism, 8k, strictly clothed, no text"
                ),
                estimated_duration_sec=16.0,
            ),
        ]

        return LongVideoScript(
            topic=clean_topic,
            title=title,
            description=description,
            tags=tags,
            category_id=config.DEFAULT_CATEGORY_ID,
            thumbnail_headline=headline,
            thumbnail_visual_prompt=(
                f"High-contrast 16:9 landscape thumbnail artwork, powerful portrait of a stoic thinker in intense focus, "
                f"dramatic golden rim lighting against deep dark background, clean negative space on the left third for headline text, "
                f"ARRI Alexa LF, 35mm anamorphic lens, cinematic realism, 8k, strictly clothed, no text"
            ),
            scenes=scenes,
            pinned_comment=f"What is the single biggest habit you are working to master this week? Share your thoughts below!",
        )

    def _create_fallback_trilingual_package(self, topic: str) -> TrilingualShortsPackage:
        """
        Constructs an authentic, high-converting TrilingualShortsPackage across English,
        Hindi (genuine Devanagari script), and Gujarati (genuine Gujarati script)
        when Gemini API daily free-tier quota (429 RESOURCE_EXHAUSTED) is reached.
        Guarantees that daily uploads NEVER fail even under API downtime.
        """
        topic_lower = (topic or "").lower()
        if "health" in topic_lower or "sleep" in topic_lower or "vitality" in topic_lower:
            theme_cat = "health_habits"
            pillar_name = "Practical Daily Health Habits"
            en_title = "The Morning Habit Draining Your Brain #Shorts"
            hi_title = "सुबह की यह गलत आदत तुरंत बदलो #Shorts"
            gu_title = "સવારની આ ખરાબ આદત તરત જ બદલો #Shorts"

            en_vo = "Checking your phone the instant you wake up is sabotaging your mental energy. You flood your half-asleep brain with cortisol and dopamine spikes, guaranteeing brain fog for the rest of the day. Rule number one: keep screens away for the first thirty minutes. Get direct sunlight in your eyes and drink a large glass of water. Subscribe to Daily Growth and master your daily vitality."
            hi_vo = "सुबह आँख खुलते ही फोन देखना आपकी ऊर्जा को बर्बाद कर रहा है। ऐसा करने से दिमाग में तनाव और बेचैनी बढ़ती है, जिससे पूरा दिन थकान महसूस होती है। नियम नंबर एक याद रखिए: उठने के बाद पहले तीस मिनट तक स्क्रीन से दूर रहिए। ताजी हवा और धूप लीजिए और पानी पीजिए। अपनी सेहत सुधारने के लिए डेली ग्रोथ को सब्सक्राइब करें।"
            gu_vo = "સવારે આંખ ખુલતાની સાથે જ મોબાઈલ જોવો એ તમારા દિવસની સૌથી મોટી ભૂલ છે. આમ કરવાથી મગજ પર સીધો તણાવ વધે છે અને આખો દિવસ આળસ રહે છે. નિયમ નંબર એક: સવારે ઉઠ્યા પછી પેહલી ત્રીસ મિનિટ સ્ક્રીનથી દૂર રહો. સૂર્યપ્રકાશ લો અને પાણી પીઓ. ઉત્તમ સ્વાસ્થ્ય માટે ડેઇલી ગ્રોથને સબ્સ્ક્રાઇબ કરો."

            en_s1, hi_s1, gu_s1 = "Checking your phone the instant you wake up is sabotaging your mental energy.", "सुबह आँख खुलते ही फोन देखना आपकी ऊर्जा को बर्बाद कर रहा है।", "સવારે આંખ ખુલતાની સાથે જ મોબાઈલ જોવો એ તમારા દિવસની સૌથી મોટી ભૂલ છે."
            en_s2, hi_s2, gu_s2 = "You flood your half-asleep brain with stress hormones, guaranteeing brain fog all day.", "ऐसा करने से दिमाग में तनाव और बेचैनी बढ़ती है, जिससे पूरा दिन थकान महसूस होती है।", "આમ કરવાથી મગજ પર સીધો તણાવ વધે છે અને આખો દિવસ આળસ અને થાક રહે છે."
            en_s3, hi_s3, gu_s3 = "Rule number one: zero screens for thirty minutes. Get sunlight and drink water.", "नियम नंबर एक: उठने के बाद पहले तीस मिनट स्क्रीन से दूर रहिए और धूप लीजिए।", "નિયમ નંબર એક: સવારે ઉઠ્યા પછી પેહલી ત્રીસ મિનિટ સ્ક્રીનથી દૂર રહો અને તાજી હવા લો."
            en_s4, hi_s4, gu_s4 = "Protect your morning. Subscribe to Daily Growth and master your daily vitality.", "अपनी सुबह की रक्षा करें। ऊर्जावान जीवन के लिए डेली ग्रोथ को सब्सक्राइब करें।", "તમારી સવારને સુધારો. ઉત્તમ સ્વાસ્થ્ય માટે ડેઇલી ગ્રોથને સબ્સ્ક્રાઇબ કરો."
        elif "financ" in topic_lower or "money" in topic_lower or "wealth" in topic_lower:
            theme_cat = "financial_discipline"
            pillar_name = "Realistic Financial Discipline"
            en_title = "Stop Buying Fake Wealth #Shorts"
            hi_title = "दिखावे का खर्च तुरंत बंद करो #Shorts"
            gu_title = "દેખાડો કરવાનું તરત જ બંધ કરો #Shorts"

            en_vo = "Spending money to impress people who do not care about you is keeping you broke. Real wealth is what you do not see: the investments growing silently and the freedom to walk away. Rule number one: delay every non-essential purchase by twenty-four hours. If you still want it tomorrow, evaluate your priorities. Subscribe to Daily Growth and build unbreakable financial discipline."
            hi_vo = "दूसरों को प्रभावित करने के लिए फिजूलखर्च करना आपको हमेशा गरीब बनाए रखेगा। सच्ची दौलત वह है जो दिखाई नहीं देती: आपकी बचत और आपकी आजादी। नियम नंबर एक: किसी भी गैर-जरूरी खरीदारी को चौबीસ घंटे के लिए टाल दीजिए। अगर कल भी उसकी जरूरत लगे, तभी विचार करें। आर्थिक रूप से मजबूत बनने के लिए डेली ग्रोथ को सब्सक्राइब करें।"
            gu_vo = "બીજાને પ્રભાવિત કરવા માટે પૈસા બગાડવા એ ગરીબીની સૌથી મોટી નિશાની છે. ખરી સંપત્તિ એ છે જે દેખાતી નથી: તમારી બચત અને તમારી સ્વતંત્રતા. નિયમ નંબર એક: કોઈપણ બિનજરૂરી ખરીદીને ચોવીસ કલાક માટે ટાળો. જો કાલે પણ જરૂર લાગે તો જ વિચારો. આર્થિક મજબૂતી માટે ડેઇલી ગ્રોથને સબ્સ્ક્રાઇબ કરો."

            en_s1, hi_s1, gu_s1 = "Spending money to impress people who do not care about you is keeping you broke.", "दूसरों को प्रभावित करने के लिए फिजूलखर्च करना आपको हमेशा गरीब बनाए रखेगा।", "બીજાને પ્રભાવિત કરવા માટે પૈસા બગાડવા એ ગરીબીની સૌથી મોટી નિશાની છે."
            en_s2, hi_s2, gu_s2 = "Real wealth is what you do not see: quiet investments and genuine freedom.", "सच्ची दौलत वह है जो दिखाई नहीं देती: आपकी बचत और आपकी मानसिक आजादी।", "ખરી સંપત્તિ એ છે જે દેખાતી નથી: તમારી બચત અને તમારી સાચી સ્વતંત્રતા."
            en_s3, hi_s3, gu_s3 = "Rule number one: delay every impulse purchase by twenty-four hours.", "नियम नंबर एक: किसी भी गैर-जरूरी खरीदारी को चौबीस घंटे के लिए टाल दीजिए।", "નિયમ નંબર એક: કોઈપણ બિનજરૂરી ખરીદીને ચોવીસ કલાક માટે ટાળી દો."
            en_s4, hi_s4, gu_s4 = "Invest in freedom, not temporary status. Subscribe to Daily Growth today.", "दिखावे में नहीं, स्वतंत्रता में निवेश करें। डेली ग्रोथ को सब्सक्राइब करें।", "દેખાડામાં નહિ, સાચી આઝાદીમાં રોકાણ કરો. ડેઇલી ગ્રોથને સબ્સ્ક્રાઇબ કરો."
        else:
            theme_cat = "stoic_resilience"
            pillar_name = "Stoic Mental Resilience"
            en_title = "Stop Letting Small Things Break You #Shorts"
            hi_title = "हर छोटी बात पर परेशान होना बंद करो #Shorts"
            gu_title = "દરેક નાની વાત પર ગુસ્સે થવાનું બંધ કરો #Shorts"

            en_vo = "Stop reacting to every tiny irritation in your day. When you let an insult or delay ruin your mood, you hand your power to strangers. The Stoics lived by one rule: you cannot control what happens, but you have 100% control over how you react. Breathe. Pause for three seconds. Choose calm over chaos. Subscribe to Daily Growth and master your mind."
            hi_vo = "हर छोटी बात पर अपनी शांति खोना बंद कीजिए। जब आप किसी की बात या देरी से परेशान होते हैं, तो आप अपनी ताकत दूसरों को दे देते हैं। जीवन का सबसे बड़ा नियम यही है: हालात आपके वश में नहीं हैं, लेकिन आपकी प्रतिक्रिया पूरी तरह आपके नियंत्रण में है। तीन सेकंड रुकिए। गुस्से के बदले शांति चुनिए। डेली ग्रोथ को सब्सक्राइब करें और खुद पर विजय पाएं।"
            gu_vo = "દરેક નાની વાત પર મન અશાંત કરવાનું બંધ કરો. જ્યારે તમે બીજાના શબ્દોથી ગુસ્સે થાઓ છો, ત્યારે તમે તમારી શક્તિ બીજાના હાથમાં સોંપી દો છો. જીવનનો સૌથી મોટો નિયમ છે: પરિસ્થિતિ તમારા હાથમાં નથી, પણ તમારી પ્રતિક્રિયા સો ટકા તમારા હાથમાં છે. ત્રણ સેકન્ડ ઊંડો શ્વાસ લો. ક્રોધની જગ્યાએ સંયમ પસંદ કરો. ડેઇલી ગ્રોથને સબ્સ્ક્રાઇબ કરો અને સફળ બનો."

            en_s1, hi_s1, gu_s1 = "Stop reacting to every tiny irritation in your day. Never hand your power to strangers.", "हर छोटी बात पर अपनी शांति खोना बंद कीजिए। कभी अपनी ताकत दूसरों को मत सौंपिए।", "દરેક નાની વાત પર મન અશાંત કરવાનું બંધ કરો. ક્યારેય તમારી શક્તિ બીજાને ન સોંપો."
            en_s2, hi_s2, gu_s2 = "The world wants you anxious and distracted, reacting blindly to every external impulse.", "यह दुनिया आपको हमेशा परेशान देखना चाहती है, ताकि आप अपने लक्ष्य से भटक जाएं।", "આ દુનિયા તમને હંમેશા ચિંતિત રાખવા માંગે છે, જેથી તમે તમારા ધ્યેયથી ભટકી જાઓ."
            en_s3, hi_s3, gu_s3 = "Rule number one: you cannot control events, but you control your response.", "नियम नंबर एक: हालात आपके वश में नहीं हैं, लेकिन आपकी प्रतिक्रिया आपके हाथ में है।", "નિયમ નંબર એક: પરિસ્થિતિ તમારા હાથમાં નથી, પણ પ્રતિક્રિયા તમારા હાથમાં છે."
            en_s4, hi_s4, gu_s4 = "Breathe. Choose calm over chaos. Subscribe to Daily Growth and master your mind.", "तीन सेकंड रुकिए। शांति चुनिए। खुद पर विजय पाने के लिए डेली ग्रोथ को सब्सक्राइब करें।", "ઊંડો શ્વાસ લો. સંયમ પસંદ કરો. પોતાના પર વિજય મેળવવા ડેઇલી ગ્રોથને સબ્સ્ક્રાઇબ કરો."

        base_prompt = "Cinematic 9:16 vertical cinema shot of a disciplined mentor in a dark tailored coat, ARRI Alexa LF, 35mm anamorphic lens, authentic natural lighting, 8k resolution, documentary realism, strictly fully clothed, no text overlay"

        def _make_lang_scenes(s1, s2, s3, s4, b1, b2, b3, b4):
            return [
                Scene(
                    scene_number=1,
                    narration=s1,
                    speaker_entity="Disciplined Stoic Mentor in dark coat",
                    speaking_action="Speaking directly into the camera with mouth open in mid-speech delivery",
                    proper_sign="Raising hand in an authoritative STOP sign gesture 🛑",
                    sign_badge=b1,
                    visual_prompt=f"{base_prompt}, looking firmly into camera with mouth open speaking, holding palm up in firm STOP gesture",
                    estimated_duration_sec=11.5,
                ),
                Scene(
                    scene_number=2,
                    narration=s2,
                    speaker_entity="Disciplined Stoic Mentor in dark coat",
                    speaking_action="Speaking with intense clarity gesturing to caution against traps",
                    proper_sign="Holding up an antique pocket watch pointing to passing seconds ⏳",
                    sign_badge=b2,
                    visual_prompt=f"{base_prompt}, holding up an antique pocket watch pointing to time passing, intense focused eye contact",
                    estimated_duration_sec=11.0,
                ),
                Scene(
                    scene_number=3,
                    narration=s3,
                    speaker_entity="Disciplined Stoic Mentor in dark coat",
                    speaking_action="Speaking with calm authority with index finger raised firmly",
                    proper_sign="Raising index finger upright delivering Rule #1 point ☝️",
                    sign_badge=b3,
                    visual_prompt=f"{base_prompt}, index finger raised upright delivering Rule #1 lesson, warm golden rim lighting",
                    estimated_duration_sec=12.0,
                ),
                Scene(
                    scene_number=4,
                    narration=s4,
                    speaker_entity="Disciplined Stoic Mentor in dark coat",
                    speaking_action="Speaking with warm resolute conviction gesturing down to subscribe",
                    proper_sign="Pointing down towards comments and subscribe button 👇",
                    sign_badge=b4,
                    visual_prompt=f"{base_prompt}, pointing down towards bottom frame with confident nod, inspiring sunrise background",
                    estimated_duration_sec=11.0,
                ),
            ]

        en_scenes = _make_lang_scenes(en_s1, en_s2, en_s3, en_s4, "🛑 STOP THIS", "⚡ THE TRAP", "🧠 RULE #1", "👇 SUBSCRIBE")
        hi_scenes = _make_lang_scenes(hi_s1, hi_s2, hi_s3, hi_s4, "🛑 रुकिए", "⚡ असली सच", "🧠 नियम #1", "👇 सब्सक्राइब करें")
        gu_scenes = _make_lang_scenes(gu_s1, gu_s2, gu_s3, gu_s4, "🛑 ઊભા રહો", "⚡ સાચો રસ્તો", "🧠 નિયમ #1", "👇 સબ્સ્ક્રાઇબ કરો")

        poll = CommunityPoll(
            question=f"What is your biggest daily focus challenge in {pillar_name}?",
            options=["Consistent Execution", "Digital Distractions", "Emotional Reactions", "Lack of Energy"],
            post_text=f"How do you stay disciplined under pressure? Cast your vote below! #DailyGrowth #Mindset",
        )

        english_pkg = LanguageScript(
            language="en",
            title=en_title,
            description="Master your habits, emotions, and discipline with timeless daily wisdom. Subscribe to Daily Growth for daily masterclasses.",
            hashtags="#mindset #discipline #DailyGrowth #motivation #Shorts",
            tags=["Daily Growth", "Motivation", "Self Improvement", "Discipline", "Shorts"],
            voiceover_script=en_vo,
            scenes=en_scenes,
        )

        hindi_pkg = LanguageScript(
            language="hi",
            title=hi_title,
            description="अपनी भावनाओं, आदतों और विचारों पर नियंत्रण पाएं। मानसिक मजबूती के लिए डेली ग्रोथ को सब्सक्राइब करें।",
            hashtags="#motivation #mindset #DailyGrowth #hindi #Shorts",
            tags=["डेली ग्रोथ", "आत्म विकास", "मानसिक मजबूती", "प्रेरणा", "शॉर्ट्स"],
            voiceover_script=hi_vo,
            scenes=hi_scenes,
        )

        gujarati_pkg = LanguageScript(
            language="gu",
            title=gu_title,
            description="તમારા મન, આદતો અને વિચારો પર કાબૂ મેળવો. જીવનમાં આગળ વધવા માટે ડેઇલી ગ્રોથને સબ્સ્ક્રાઇબ કરો.",
            hashtags="#gujarati #motivation #DailyGrowth #mindset #Shorts",
            tags=["ડેઇલી ગ્રોથ", "પ્રેરણા", "માનસિક શાંતિ", "આત્મવિશ્વાસ", "શોર્ટસ"],
            voiceover_script=gu_vo,
            scenes=gu_scenes,
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
            pinned_comment=f"What is the single biggest habit you are working on today? Share your thoughts below!",
            scenes=en.scenes,
            community_poll=trilingual_fallback.community_poll,
        )




