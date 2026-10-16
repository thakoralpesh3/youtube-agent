import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from google import genai
from google.genai import types

import config
from growth.model_resolver import get_candidate_models
from youtube.auth import YouTubeAuth

logger = logging.getLogger(__name__)


class GrowthEngine:
    """
    Autonomous Channel Growth & Self-Evolution Engine.
    Analyzes uploaded YouTube Shorts analytics, extracts winning hook/retention formulas,
    and updates channel memory to compound viewer retention and subscriber growth.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.memory_file = config.OUTPUT_DIR / "channel_growth.json"
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    def load_growth_memory(self) -> dict:
        """Loads accumulated growth lessons and winning formulas."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read growth memory: {e}")

        # Default foundational baseline rules for adult motivation & health/fitness
        return {
            "total_videos_analyzed": 0,
            "best_performing_hook_styles": [
                "Counter-Intuitive Biological Truth (e.g., 'Doing the hard thing physically enlarges your brain')",
                "Micro-Friction vs Instant Gratification (e.g., 'The 5-second physiological rule of action')",
                "Direct Provocative Question (e.g., 'Why motivation is a neurological trap')",
            ],
            "peak_engagement_themes": [
                "Stoic unshakeable calm & self-mastery",
                "Neuroscience of willpower and deep focus",
                "Metabolic fat oxidation & recovery science",
            ],
            "key_retention_rules": [
                "Cut straight to the hook with zero intro fluff in the first 2.5 seconds.",
                "Use high-contrast dramatic visual pacing every 4 to 6 seconds.",
                "End with an open loop or high-stakes reflection question to spike comments.",
            ],
            "growth_score": 100,
        }

    def fetch_uploaded_video_analytics(self) -> List[dict]:
        """Scans local run history and queries YouTube API for live performance stats."""
        video_entries = []
        for summary_file in config.OUTPUT_DIR.glob("run_*/summary.json"):
            try:
                with open(summary_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    upload_res = data.get("upload_result")
                    if upload_res and "video_id" in upload_res:
                        video_entries.append({
                            "video_id": upload_res["video_id"],
                            "title": data.get("title", ""),
                            "timestamp": data.get("timestamp", ""),
                        })
            except Exception:
                pass

        if not video_entries:
            return []

        # Query YouTube API for live stats if token is available
        auth = YouTubeAuth()
        if not auth.is_token_valid():
            logger.debug("YouTube OAuth token not valid or expired. Skipping live analytics sync.")
            return []
        try:
            from googleapiclient.discovery import build
            creds = auth.get_credentials()
            youtube = build("youtube", "v3", credentials=creds)

            video_ids = [v["video_id"] for v in video_entries[-50:]]
            response = youtube.videos().list(
                part="snippet,statistics",
                id=",".join(video_ids),
            ).execute()

            enriched = []
            for item in response.get("items", []):
                stats = item.get("statistics", {})
                views = int(stats.get("viewCount", 0))
                likes = int(stats.get("likeCount", 0))
                comments = int(stats.get("commentCount", 0))
                enriched.append({
                    "video_id": item["id"],
                    "title": item["snippet"]["title"],
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "engagement_rate": round(((likes + comments) / max(views, 1)) * 100, 2),
                })
            return enriched
        except Exception as e:
            logger.debug(f"Could not query live YouTube stats (offline or not authenticated yet): {e}")
            return video_entries

    def evolve_channel_strategy(self) -> dict:
        """
        Analyzes recent video performance using Gemini to generate evolving growth rules.
        """
        memory = self.load_growth_memory()
        analytics = self.fetch_uploaded_video_analytics()

        if not analytics or len(analytics) < 2 or not self.client:
            logger.info("Using baseline high-performance growth strategy.")
            return memory

        logger.info(f"🧠 Analyzing performance across {len(analytics)} uploaded Shorts to evolve channel growth strategy...")
        
        prompt = f"""
You are an expert YouTube Shorts Channel Growth Strategist and Algorithm Specialist.
Analyze the following YouTube Shorts performance data for our Adult Motivation & Health/Fitness channel:

VIDEO PERFORMANCE DATA:
{json.dumps(analytics, indent=2)}

CURRENT STRATEGY MEMORY:
{json.dumps(memory, indent=2)}

Task:
Extract updated channel growth intelligence:
1. Top 3 hook structures that drove the highest engagement and views.
2. The most viral topic patterns.
3. Crucial retention rules for tomorrow's video.

Respond ONLY with valid JSON matching this schema:
{{
  "total_videos_analyzed": {len(analytics)},
  "best_performing_hook_styles": ["hook formula 1", "hook formula 2", "hook formula 3"],
  "peak_engagement_themes": ["theme 1", "theme 2", "theme 3"],
  "key_retention_rules": ["rule 1", "rule 2", "rule 3"],
  "growth_score": 120
}}
"""
        candidate_models = get_candidate_models()
        for model in candidate_models:
            try:
                res = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.4,
                    ),
                )
                updated_memory = json.loads(res.text)
                with open(self.memory_file, "w", encoding="utf-8") as f:
                    json.dump(updated_memory, f, indent=2)
                logger.info("🚀 Channel Growth Memory successfully updated with fresh winning formulas!")
                return updated_memory
            except Exception as e:
                logger.debug(f"Growth optimization model {model} failed: {e}")

        return memory

    def get_growth_prompt_context(self) -> str:
        """Formats learned growth insights for injection into Gemini script generation."""
        memory = self.load_growth_memory()
        hooks = "\n".join([f"  • {h}" for h in memory.get("best_performing_hook_styles", [])])
        rules = "\n".join([f"  • {r}" for r in memory.get("key_retention_rules", [])])
        
        return f"""
ALGORITHMIC CHANNEL GROWTH INTELLIGENCE (Learned Winning Formulas):
Top Hook Frameworks to emulate:
{hooks}

Audience Retention Rules to apply:
{rules}
"""
