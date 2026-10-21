import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Load .env file
load_dotenv(BASE_DIR / ".env")

# API Keys & Secrets (Supports multiple fallback keys for high-availability quota failover)
raw_gemini_keys = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
GEMINI_API_KEYS = [k.strip() for k in raw_gemini_keys.split(",") if k.strip()]
for idx in range(1, 10):
    extra_k = os.getenv(f"GEMINI_API_KEY_{idx}", "").strip()
    if extra_k and extra_k not in GEMINI_API_KEYS:
        GEMINI_API_KEYS.append(extra_k)

GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""

# Autonomous Dynamic Model Resolver (Auto-upgrades to latest Gemini model, e.g. Gemini 4 Argon, and respects user overrides)
try:
    from growth.model_resolver import (
        get_latest_gemini_model,
        get_candidate_models,
        set_runtime_model,
        get_runtime_model,
        call_gemini_resilient,
    )
    GEMINI_MODEL = get_latest_gemini_model(fallback=os.getenv("GEMINI_MODEL", "gemini-4-argon"))
except Exception:
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-4-argon")


def set_active_model(model_name: str) -> None:
    """Sets the active model dynamically for user override across both agents."""
    global GEMINI_MODEL
    GEMINI_MODEL = model_name
    try:
        from growth.model_resolver import set_runtime_model
        set_runtime_model(model_name)
    except Exception:
        pass

GEMINI_IMAGEN_MODEL = os.getenv("GEMINI_IMAGEN_MODEL", "imagen-3.0-generate-002")

# YouTube API Configuration
YOUTUBE_CLIENT_SECRET_FILE = os.getenv(
    "YOUTUBE_CLIENT_SECRET_FILE", str(BASE_DIR / "client_secret.json")
)
YOUTUBE_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", str(BASE_DIR / "token.json"))
YOUTUBE_PRIVACY_STATUS = os.getenv("YOUTUBE_PRIVACY_STATUS", "unlisted")  # public, private, unlisted

# Content Niche / Channel Strategy
DEFAULT_NICHE = os.getenv(
    "DEFAULT_NICHE",
    "High-Performance Growth Mindset, Stoicism, Health & Fitness Science, Mental Resilience, and Peak Daily Discipline (Strictly All-Ages & Family-Friendly)",
)
DEFAULT_CATEGORY_ID = os.getenv("YOUTUBE_CATEGORY_ID", "27")  # 27: Education, 26: Howto/Fitness, 22: People & Blogs
DAILY_UPLOAD_TIME = os.getenv("DAILY_UPLOAD_TIME", "09:00")  # HH:MM format for YouTube (Sharp 09:00 AM IST)
SOCIAL_DAILY_UPLOAD_TIME = os.getenv("SOCIAL_DAILY_UPLOAD_TIME", "23:30")  # Sharp 11:30 PM format for Social Stories (IG, FB, WA)
DAILY_CLEANER_TIME = os.getenv("DAILY_CLEANER_TIME", "09:30")  # HH:MM format for daily stuck video cleaner
SOCIAL_DAILY_POST_LIMIT = int(os.getenv("SOCIAL_DAILY_POST_LIMIT", "1"))  # Maximum 1 social post per day
YOUTUBE_DAILY_RUN_LIMIT = int(os.getenv("YOUTUBE_DAILY_RUN_LIMIT", "1"))  # Maximum 1 YouTube run per day

# GitHub Actions Cloud Dispatch Configuration (Zero-delay sharp dispatch)
DISPATCH_TO_GITHUB_ACTIONS = os.getenv("DISPATCH_TO_GITHUB_ACTIONS", "true").lower() in ("1", "true", "yes")
GITHUB_REPO = os.getenv("GITHUB_REPO", "thakoralpesh3/youtube-agent")
GITHUB_YOUTUBE_WORKFLOW = os.getenv("GITHUB_YOUTUBE_WORKFLOW", "daily_youtube_agent.yml")
GITHUB_SOCIAL_WORKFLOW = os.getenv("GITHUB_SOCIAL_WORKFLOW", "daily_social_agent.yml")

# Strict Content Safety & Age Appropriateness Policy (Under-18 Safe / All-Ages Family Friendly)
STRICT_NO_18_PLUS = True
MAX_AGE_RATING = "ALL_AGES"
PROHIBIT_SEXY_CONTENT = True
PROHIBIT_NUDE_CONTENT = True
PROHIBIT_PORN_CONTENT = True
PROHIBIT_18_PLUS_CONTENT = True
ENFORCE_MODEST_CLOTHING = True

SAFETY_GUARDRAILS = (
    "CRITICAL ZERO-TOLERANCE SAFETY POLICY (NO 18+, NO NUDE, NO PORN, NO SEXY CONTENT):\n"
    "- STRICTLY FORBIDDEN: Any nude, naked, semi-nude, topless, or bottomless imagery.\n"
    "- STRICTLY FORBIDDEN: Any porn, pornography, erotica, xxx, nsfw, or sexually suggestive themes.\n"
    "- STRICTLY FORBIDDEN: Any sexy, sensual, provocative, seductive, or erotic content, poses, or attire.\n"
    "- STRICTLY FORBIDDEN: Any swimwear, bikini, lingerie, underwear, revealing cleavage, bare chest, or shirtless human figures.\n"
    "- MANDATORY: All human figures must be fully clothed in modest attire (running jackets, tracksuits, modest sportswear with NO exposed skin/torso).\n"
    "- MANDATORY: Prefer majestic wildlife (eagles, lions, wolves, horses, falcons) and powerful living nature (mountains, redwood forests, oceans).\n"
    "- STRICTLY FORBIDDEN: Any violence, gore, weapons, alcohol, tobacco, vaping, drugs, gambling, or adult language.\n"
    "- MANDATORY: All content (topics, scripts, visual prompts, narrations, captions, and hashtags) MUST be 100% wholesome, inspiring, educational, clean, and safe for all viewers of all ages (G/PG rating)."
)

# Curated High-Performance Content Pillars (Discipline, Fitness, Mindset, Health, Living Organisms & Nature's Laws)
DEFAULT_CONTENT_PILLARS = [
    "Why discipline always beats motivation: The neuroscience of willpower",
    "How to rebuild your dopamine receptors and eliminate chronic brain fog",
    "The Eagle's Vision: How apex predators lock onto goals and ignore storm clouds",
    "The 3 non-negotiable morning habits of elite high performers",
    "The Wolfpack Discipline: Relentless endurance and loyalty to personal standards",
    "The brutal truth about fat loss and muscle hypertrophy science",
    "Stoic psychological rules for staying unshakeable under pressure",
    "Bamboo Resilience: Why bending in the storm beats rigid resistance (Antifragility in Nature)",
    "The sleep and circadian rhythm protocol for 2x energy and recovery",
    "How the 1% rule and micro-habits compound into unstoppable momentum",
    "Cortisol, stress, and chronic fatigue: How modern life drains your energy",
    "The Lion's Presence: Silent authority, calm power, and predatory focus",
    "The biological benefits of cold exposure, heat shock proteins, and fasting",
    "How to master deep work and get 8 hours of productive output in 3 hours",
    "Deep Roots of the Ancient Oak: Building unshakeable character in chaotic environments",
]

# Voice / TTS Settings
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-ChristopherNeural")  # high quality Edge-TTS neural voice
TTS_RATE = os.getenv("TTS_RATE", "+0%")

# Video Assembly Specs
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30

# Directories
OUTPUT_DIR = BASE_DIR / "output"
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
MUSIC_DIR = ASSETS_DIR / "music"
SOCIAL_TRACKER_FILE = OUTPUT_DIR / "social_daily_tracker.json"
YOUTUBE_TRACKER_FILE = OUTPUT_DIR / "youtube_daily_tracker.json"
YOUTUBE_CLEANER_TRACKER_FILE = OUTPUT_DIR / "youtube_cleaner_tracker.json"

# Default font path
DEFAULT_FONT_PATH = FONTS_DIR / "Montserrat-Variable.ttf"
if not DEFAULT_FONT_PATH.exists():
    # Fallback to LiberationSans if custom font not found
    DEFAULT_FONT_PATH = Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")

# Ensure required directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# Online Web Control Center & Remote Access
WEB_SERVER_HOST = os.getenv("WEB_SERVER_HOST", "0.0.0.0")
WEB_SERVER_PORT = int(os.getenv("WEB_SERVER_PORT", "8085"))
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "chamunda2026")

# Optional Telegram Remote Control Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

