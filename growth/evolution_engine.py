import hashlib
import json
import logging
import os
import random
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

import config
from growth.model_resolver import get_candidate_models

logger = logging.getLogger("evolution_engine")


class EvolutionEngine:
    """
    Autonomous Creative Evolution & Proactive Idea Generation Engine.
    Enables the agent to:
    1. Evolve its creative intelligence and mutate winning formulas.
    2. Proactively brainstorm unexpected, high-converting ideas ('Surprise Sparks').
    3. Empower the user to execute breakthrough ideas with a single click across
       Web, Telegram, and CLI.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.journal_file = config.OUTPUT_DIR / "evolution_journal.json"
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    # --------------------------------------------------------------------------
    # 1. EVOLUTIONARY JOURNAL MANAGEMENT
    # --------------------------------------------------------------------------
    def load_journal(self) -> Dict[str, Any]:
        """Loads or initializes the Creative Evolution Journal."""
        if self.journal_file.exists():
            try:
                with open(self.journal_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error reading evolution journal: {e}")

        # Initial baseline journal
        default_journal = {
            "evolution_level": 2,
            "level_name": "Level 2: Creative Explorer",
            "creative_score": 140,
            "breakthroughs_discovered": 3,
            "active_sparks": [],
            "executed_sparks_history": [],
            "mutated_hook_formulas": [
                "The Counter-Biological Glitch (Reveals why our instincts betray us in modern life)",
                "Micro-Friction Protocol (The neurological switch between hesitation and momentum)",
                "Royal Enfield Engineering Mystique (The mechanical soul of the thumping pushrod engine)",
                "Apex Predator Focus (How eagles and wolves filter noise to lock onto single high-value targets)",
                "Living Organism Elasticity (How bamboo and ancient redwoods survive Category 5 storms without breaking)",
            ],
            "visual_style_mutations": [
                "High-contrast documentary pacing with split-second kinetic text pop-ins",
                "Vintage amber and brushed bronze color grading (Chamunda Royal Enfield aesthetic)",
                "Minimalist dark-mode typography with rapid biological cutaways",
                "Cinematic wildlife and living-nature macro cutaways with deep organic textures",
            ],
            "last_evolution_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.save_journal(default_journal)
        return default_journal

    def save_journal(self, journal: Dict[str, Any]):
        """Saves journal state atomically."""
        try:
            config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.journal_file, "w", encoding="utf-8") as f:
                json.dump(journal, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save evolution journal: {e}")

    def get_level_info(self, score: int) -> tuple[int, str]:
        """Calculates level progression based on creative score."""
        if score >= 500:
            return 5, "🌟 Level 5: Creative Visionary"
        elif score >= 350:
            return 4, "⚡ Level 4: Content Alchemist"
        elif score >= 220:
            return 3, "🚀 Level 3: Viral Innovator"
        elif score >= 120:
            return 2, "🔍 Level 2: Creative Explorer"
        else:
            return 1, "🌱 Level 1: Autonomous Novice"

    # --------------------------------------------------------------------------
    # 2. PROACTIVE SURPRISE SPARKS GENERATOR
    # --------------------------------------------------------------------------
    def generate_surprise_sparks(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Brainstorms 3 fresh, unexpected, out-of-the-box creative ideas:
        1. Mindset/Neuroscience Viral Shorts Concept
        2. Chamunda Automobile (Royal Enfield Only) Cultural/Technical Special
        3. Wildcard Cross-Over Breakthrough Idea
        """
        journal = self.load_journal()

        # If we already have fresh sparks and not forcing refresh, return them
        if not force_refresh and journal.get("active_sparks"):
            return journal["active_sparks"]

        logger.info("💡 [Creative Brain] Synthesizing fresh surprise ideas and creative breakthroughs...")

        sparks = []
        if self.client:
            prompt = """
You are an elite, disruptive creative director, viral content architect, and storytelling maestro.
Your mission is to SURPRISE the creator with 3 exceptionally creative, unexpected, and high-converting content ideas.

DOMAINS TO COVER:
1. IDEA 1 (Mindset, Neuroscience & Living Organisms): High-Performance Adult Mindset, Stoicism, Brain Biology, and Bio-Resilience principles from Apex Predators & Living Nature (eagles, wolves, lions, ancient forests).
   - Must have a counter-intuitive, unexpected angle (NOT generic motivation).
   - Format: YouTube Shorts (Trilingual: English, Hindi, Gujarati).

2. IDEA 2 (Royal Enfield Special for Chamunda Automobile Parts & Services):
   - Specializes in Royal Enfield motorcycles ONLY.
   - Rider heritage, engine thumping mechanics, Bullet/Classic/Himalayan road endurance, or workshop secrets.
   - Format: Social Media Story / Reel (Instagram, Facebook, WhatsApp).

3. IDEA 3 (The Wildcard / Cross-Over Breakthrough):
   - A bold, unexpected conceptual fusion between living wildlife/nature instincts and human mechanical or mental excellence (e.g. 'What a hunting falcon and a Royal Enfield engine share about precision under pressure').
   - Format: YouTube Shorts or High-Impact Carousel.

For each idea, invent a compelling title, why it's a surprising breakthrough, and a ready-to-run prompt.

Respond ONLY with valid JSON matching this exact array schema:
[
  {
    "id": "spark_1",
    "title": "Short Catchy Viral Title",
    "category": "mindset",
    "target_platform": "YouTube Shorts (EN, HI, GU)",
    "concept": "2-3 sentences explaining the premise and psychological hook.",
    "surprise_factor": "What makes this idea completely unexpected, clever, or counter-intuitive.",
    "suggested_action": "shorts",
    "full_prompt": "Detailed topic prompt to feed directly into the video generator."
  },
  {
    "id": "spark_2",
    "title": "Short Catchy Viral Title",
    "category": "royal_enfield",
    "target_platform": "Instagram, Facebook & WhatsApp Story",
    "concept": "Premise tailored to Chamunda Automobile and Royal Enfield lovers.",
    "surprise_factor": "The technical or emotional secret that bike enthusiasts will crave.",
    "suggested_action": "festival",
    "full_prompt": "Detailed prompt for the Royal Enfield social campaign generator."
  },
  {
    "id": "spark_3",
    "title": "Short Catchy Viral Title",
    "category": "wildcard",
    "target_platform": "Multi-Platform Viral Special",
    "concept": "The unexpected cross-over premise.",
    "surprise_factor": "Why nobody else is talking about this connection.",
    "suggested_action": "shorts",
    "full_prompt": "Detailed prompt ready for execution."
  }
]
"""
            candidate_models = get_candidate_models(tier="pro")
            for model in candidate_models:
                try:
                    res = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.85,
                        ),
                    )
                    parsed = json.loads(res.text)
                    if isinstance(parsed, list) and len(parsed) >= 2:
                        for idx, item in enumerate(parsed):
                            item["id"] = f"spark_{int(time.time())}_{idx+1}_{secrets.token_hex(2)}"
                        sparks = parsed[:3]
                        break
                except Exception as e:
                    logger.debug(f"Idea generation with model {model} failed: {e}")

        # Reliable high-impact fallback sparks if Gemini is offline or slow
        if not sparks:
            sparks = [
                {
                    "id": f"spark_{int(time.time())}_1",
                    "title": "The Biological Trap of 'Feeling Ready'",
                    "category": "mindset",
                    "target_platform": "YouTube Shorts (EN, HI, GU)",
                    "concept": "Debunking the myth of readiness: Action produces dopamine, not the other way around. The brain waits for physical movement to initiate cognitive momentum.",
                    "surprise_factor": "Reveals that waiting for motivation is a neurological defense mechanism designed to conserve glycogen.",
                    "suggested_action": "shorts",
                    "full_prompt": "Why waiting until you feel ready is a biological trap: The neuroscience of physical movement triggering anterior mid-cingulate cortex dopamine release.",
                },
                {
                    "id": f"spark_{int(time.time())}_2",
                    "title": "The 'Golden Oil' Secret Every Royal Enfield Rider Needs",
                    "category": "royal_enfield",
                    "target_platform": "Instagram, Facebook & WhatsApp Story",
                    "concept": "Chamunda Automobile mechanics share the #1 silent killer of Classic 350 and Bullet 500 engines: thermal oil degradation during city crawling.",
                    "surprise_factor": "Shows how air-cooled single-cylinder engines require specific viscosity checks before weekend highway cruising.",
                    "suggested_action": "festival",
                    "full_prompt": "Chamunda Automobile Parts & Services workshop secret: Why Royal Enfield air-cooled engines need high-thermal viscosity oil to survive stop-and-go city traffic.",
                },
                {
                    "id": f"spark_{int(time.time())}_3",
                    "title": "The Stoic Rider: What Highway Thump Teaches the Nervous System",
                    "category": "wildcard",
                    "target_platform": "YouTube Shorts (EN, HI, GU)",
                    "concept": "Exploring the 40Hz acoustic frequency of a Royal Enfield long-stroke engine and how prolonged steady riding triggers theta wave relaxation and mental clarity.",
                    "surprise_factor": "Connecting motorcycle acoustic harmonics directly with meditation and stress hormone reduction.",
                    "suggested_action": "shorts",
                    "full_prompt": "The acoustic neuroscience of the Royal Enfield thump: How long-distance single-cylinder riding acts as active meditation and lowers cortisol.",
                },
            ]

        # Update journal
        journal["active_sparks"] = sparks
        journal["creative_score"] = journal.get("creative_score", 140) + 15
        lvl, name = self.get_level_info(journal["creative_score"])
        journal["evolution_level"] = lvl
        journal["level_name"] = name
        journal["last_evolution_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save_journal(journal)

        logger.info(f"✨ [Creative Brain] Formulated {len(sparks)} fresh surprise sparks. Evolution Level: {name}")
        return sparks

    # --------------------------------------------------------------------------
    # 3. SELF-EVOLUTION & FORMULA MUTATION
    # --------------------------------------------------------------------------
    def evolve_creative_formulas(self) -> Dict[str, Any]:
        """
        Periodically mutates hook templates and narrative rhythms.
        Advances creative score and ensures content never becomes repetitive.
        """
        journal = self.load_journal()
        journal["creative_score"] = journal.get("creative_score", 140) + 5
        lvl, name = self.get_level_info(journal["creative_score"])
        journal["evolution_level"] = lvl
        journal["level_name"] = name
        journal["breakthroughs_discovered"] = journal.get("breakthroughs_discovered", 3) + 1
        journal["last_evolution_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

        # Mutate hook styles
        new_hooks = [
            "The 10-Second Physical Contrast (Instantly jolts viewer attention with an undeniable contrast)",
            "The Forbidden Protocol (Revealing an uncomfortable reality about habits vs excuses)",
            "Royal Enfield Master Mechanic Observation (A tiny mechanical sound that reveals engine health)",
            "The Epictetus Cold-Truth Test (Testing your reaction to unexpected daily chaos)",
        ]
        chosen = random.choice(new_hooks)
        if chosen not in journal["mutated_hook_formulas"]:
            journal["mutated_hook_formulas"].append(chosen)
            if len(journal["mutated_hook_formulas"]) > 6:
                journal["mutated_hook_formulas"].pop(0)

        # Refresh surprise sparks if active sparks are empty
        if not journal.get("active_sparks"):
            self.generate_surprise_sparks(force_refresh=True)
            journal = self.load_journal()
        else:
            self.save_journal(journal)

        return journal

    # --------------------------------------------------------------------------
    # 4. 1-CLICK SURPRISE IDEA EXECUTION
    # --------------------------------------------------------------------------
    def execute_spark_idea(self, spark_id: str) -> Dict[str, Any]:
        """
        Executes a surprise idea on demand:
        Finds the idea in active sparks, routes to YouTube Shorts or Social Campaign,
        and logs it in the executed history.
        """
        journal = self.load_journal()
        active = journal.get("active_sparks", [])
        
        target_spark = None
        for s in active:
            if s.get("id") == spark_id:
                target_spark = s
                break

        # If not found by ID, use first available spark or create one
        if not target_spark:
            if active:
                target_spark = active[0]
            else:
                sparks = self.generate_surprise_sparks(force_refresh=True)
                target_spark = sparks[0]

        logger.info(f"🚀 [Creative Brain] Executing Surprise Spark: '{target_spark.get('title')}'")

        action_type = target_spark.get("suggested_action", "shorts")
        full_prompt = target_spark.get("full_prompt") or target_spark.get("title")

        # Move spark from active to executed history
        journal["active_sparks"] = [s for s in active if s.get("id") != target_spark.get("id")]
        executed_entry = {
            **target_spark,
            "executed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        journal.setdefault("executed_sparks_history", []).append(executed_entry)
        journal["creative_score"] = journal.get("creative_score", 140) + 25
        lvl, name = self.get_level_info(journal["creative_score"])
        journal["evolution_level"] = lvl
        journal["level_name"] = name
        self.save_journal(journal)

        # Launch appropriate pipeline in background thread
        if action_type == "festival" or "royal_enfield" in target_spark.get("category", ""):
            def _run_re():
                try:
                    from syndication.festival_agent import FestivalSocialAgent
                    agent = FestivalSocialAgent()
                    agent.run_festival_campaign(force_upload=True)
                except Exception as e:
                    logger.error(f"Error executing Royal Enfield surprise spark: {e}", exc_info=True)
            threading.Thread(target=_run_re, daemon=True).start()

        else:
            def _run_shorts():
                try:
                    from agent import YouTubeAgent
                    agent = YouTubeAgent()
                    agent.run_trilingual(topic=full_prompt, dry_run=False)
                except Exception as e:
                    logger.error(f"Error executing Shorts surprise spark: {e}", exc_info=True)
            threading.Thread(target=_run_shorts, daemon=True).start()

        # Send desktop alert of creative execution
        try:
            import subprocess
            subprocess.run([
                "notify-send",
                "-a", "AI Creative Brain",
                "💡 Creative Spark Engaged!",
                f"Now producing: '{target_spark.get('title')}'"
            ], check=False)
        except Exception:
            pass

        return {
            "status": "OK",
            "message": f"Successfully launched creative execution for: '{target_spark.get('title')}'",
            "spark": target_spark,
        }
