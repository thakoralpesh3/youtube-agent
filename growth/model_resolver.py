"""
Dynamic Gemini Model Resolver, Tier Router, and Autonomous Auto-Failover Engine.

Prioritizes:
1. User Requirement: Explicitly chosen model via CLI (--model), UI selector, or .env.
2. Agent Requirement: Tier-optimized candidate chain (flash, pro, fast, vision).
3. Autonomous Failover: Automatically switches to next viable model on 503 (high demand) or 429 (quota).
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("model_resolver")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_FILE = BASE_DIR / "output" / ".model_cache.json"
ENV_FILE = BASE_DIR / ".env"

# Active robust fallback chains excluding deprecated 404 models
DEPRECATED_MODELS = {
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-1.0-pro",
    "gemini-pro",
}
DEFAULT_TIER_FALLBACKS = {
    "argon": [
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-4-argon",
        "gemini-3.1-pro-preview",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
    ],
    "flash": [
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-flash-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-4-argon",
    ],
    "pro": [
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.1-pro-preview",
        "gemini-pro-latest",
        "gemini-4-argon",
        "gemini-3.8-flash",
    ],
    "fast": [
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest",
        "gemini-3.8-flash",
    ],
    "vision": [
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.8-flash",
        "gemini-4-argon",
    ],
}

DEFAULT_FALLBACK_CANDIDATES = DEFAULT_TIER_FALLBACKS["argon"]

# Global runtime user override
_RUNTIME_MODEL_OVERRIDE: Optional[str] = None


def set_runtime_model(model_name: Optional[str]) -> None:
    """Sets a global runtime model override requested by user or CLI flag."""
    global _RUNTIME_MODEL_OVERRIDE
    if model_name:
        _RUNTIME_MODEL_OVERRIDE = model_name.replace("models/", "").strip()
        logger.info(f"🎯 [Model Priority] Active runtime model set to: {_RUNTIME_MODEL_OVERRIDE}")
    else:
        _RUNTIME_MODEL_OVERRIDE = None


def get_runtime_model() -> Optional[str]:
    """Returns the current runtime model override if set."""
    return _RUNTIME_MODEL_OVERRIDE


class ModelResolver:
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_path: Optional[Path] = None,
        ttl_hours: float = 6.0,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.cache_path = cache_path or CACHE_FILE
        self.ttl_seconds = ttl_hours * 3600.0

    @staticmethod
    def parse_model_info(model_name: str) -> Optional[Tuple[Tuple[int, ...], bool, str, bool]]:
        """
        Parses version and capabilities from model name.
        Returns:
            ((major, minor, ...), is_stable, tier ('argon'|'flash'|'pro'), is_lite) or None
        """
        clean_name = model_name.replace("models/", "").strip()

        # Reject known deprecated models that return 404 to new users
        if clean_name.startswith("gemini-2.5-flash") or clean_name.startswith("gemini-1.") or clean_name.startswith("gemini-2.0"):
            return None

        match = re.match(r"^gemini-(\d+(?:\.\d+)*)-(argon|flash|pro)(?:-(lite))?(?:-(preview))?$", clean_name, re.IGNORECASE)
        if not match:
            return None

        ver_str = match.group(1)
        tier = match.group(2).lower()
        is_lite = bool(match.group(3))
        is_preview = bool(match.group(4))
        is_stable = not is_preview

        try:
            ver_tuple = tuple(int(part) for part in ver_str.split("."))
            return (ver_tuple, is_stable, tier, is_lite)
        except Exception:
            return None

    def _read_cache(self) -> Optional[Dict[str, Any]]:
        """Reads cached model data if present and still valid."""
        try:
            if not self.cache_path.exists():
                return None
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_at = data.get("cached_at", 0)
            if (time.time() - cached_at) < self.ttl_seconds:
                return data
        except Exception as e:
            logger.debug(f"Failed to read model cache: {e}")
        return None

    def _write_cache(self, latest_model: str, candidates: Dict[str, List[str]]) -> None:
        """Saves discovered models to disk cache."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "cached_at": time.time(),
                "latest_model": latest_model,
                "tier_candidates": candidates,
            }
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not write model cache to {self.cache_path}: {e}")

    def _update_env_file(self, new_model: str) -> None:
        """Updates GEMINI_MODEL in .env so environment stays up-to-date."""
        try:
            if not ENV_FILE.exists():
                return

            with open(ENV_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()

            model_line_found = False
            updated_lines = []
            for line in lines:
                if line.strip().startswith("GEMINI_MODEL="):
                    old_model = line.strip().split("=", 1)[1]
                    if old_model != new_model:
                        logger.info(
                            f"🚀 [MODEL AUTO-UPGRADE] Updating .env: GEMINI_MODEL={new_model} (was: {old_model})"
                        )
                        updated_lines.append(f"GEMINI_MODEL={new_model}\n")
                    else:
                        updated_lines.append(line)
                    model_line_found = True
                else:
                    updated_lines.append(line)

            if not model_line_found:
                updated_lines.append(f"\nGEMINI_MODEL={new_model}\n")

            with open(ENV_FILE, "w", encoding="utf-8") as f:
                f.writelines(updated_lines)

        except Exception as e:
            logger.warning(f"Failed to auto-update .env with latest model: {e}")

    def discover_models(self, force_refresh: bool = False) -> Tuple[str, Dict[str, List[str]]]:
        """
        Discovers models via Gemini API, sorts by semantic version,
        and returns (latest_model_name, tier_candidate_map).
        """
        if not force_refresh:
            cached = self._read_cache()
            if cached and cached.get("latest_model") and cached.get("tier_candidates"):
                return cached["latest_model"], cached["tier_candidates"]

        if not self.api_key:
            logger.warning("No GEMINI_API_KEY found, using default candidate fallback list.")
            return DEFAULT_FALLBACK_CANDIDATES[0], DEFAULT_TIER_FALLBACKS

        try:
            from google import genai

            client = genai.Client(api_key=self.api_key)
            all_models = list(client.models.list())

            argon_models: List[Tuple[Tuple[int, ...], bool, str]] = []
            flash_models: List[Tuple[Tuple[int, ...], bool, str]] = []
            pro_models: List[Tuple[Tuple[int, ...], bool, str]] = []
            lite_models: List[Tuple[Tuple[int, ...], bool, str]] = []

            for m in all_models:
                m_name = getattr(m, "name", "")
                if not m_name:
                    continue

                clean_name = m_name.replace("models/", "").strip()
                if clean_name in DEPRECATED_MODELS or any(d in clean_name for d in ["2.5-pro", "2.5-flash", "1.5-pro", "1.5-flash", "1.0-pro"]):
                    continue

                actions = getattr(m, "supported_actions", []) or []

                if actions and "generateContent" not in actions:
                    continue

                parsed = self.parse_model_info(clean_name)
                if parsed:
                    ver_tuple, is_stable, tier, is_lite = parsed
                    if tier == "argon":
                        argon_models.append((ver_tuple, is_stable, clean_name))
                    elif is_lite:
                        lite_models.append((ver_tuple, is_stable, clean_name))
                    elif tier == "pro":
                        pro_models.append((ver_tuple, is_stable, clean_name))
                    else:
                        flash_models.append((ver_tuple, is_stable, clean_name))

            # Sort descending: newest semantic version first, then stable over preview
            argon_models.sort(key=lambda x: (x[0], x[1]), reverse=True)
            flash_models.sort(key=lambda x: (x[0], x[1]), reverse=True)
            pro_models.sort(key=lambda x: (x[0], x[1]), reverse=True)
            lite_models.sort(key=lambda x: (x[0], x[1]), reverse=True)

            sorted_argon = [m[2] for m in argon_models]
            sorted_flash = [m[2] for m in flash_models]
            sorted_pro = [m[2] for m in pro_models]
            sorted_lite = [m[2] for m in lite_models]

            if not sorted_argon and "gemini-4-argon" in [getattr(m, "name", "").replace("models/", "").strip() for m in all_models]:
                sorted_argon = ["gemini-4-argon"]

            tier_candidates: Dict[str, List[str]] = {
                "argon": sorted_argon + sorted_pro + sorted_flash,
                "flash": sorted_argon + sorted_flash + sorted_lite + ["gemini-flash-latest"],
                "pro": sorted_argon + sorted_pro + sorted_flash[:2],
                "fast": sorted_lite + sorted_flash + sorted_argon,
                "vision": [m for m in (sorted_argon + sorted_flash) if "tts" not in m and "transcribe" not in m],
            }

            for k in tier_candidates:
                deduped = list(dict.fromkeys(tier_candidates[k]))
                for fb in DEFAULT_TIER_FALLBACKS.get(k, []):
                    if fb not in deduped:
                        deduped.append(fb)
                tier_candidates[k] = deduped

            latest_model = (
                tier_candidates["argon"][0]
                if tier_candidates.get("argon")
                else (tier_candidates["flash"][0] if tier_candidates.get("flash") else DEFAULT_FALLBACK_CANDIDATES[0])
            )

            current_env_model = os.getenv("GEMINI_MODEL", "")
            if current_env_model and current_env_model != latest_model:
                curr_parsed = self.parse_model_info(current_env_model)
                new_parsed = self.parse_model_info(latest_model)
                if curr_parsed and new_parsed and new_parsed[0] > curr_parsed[0]:
                    logger.info(
                        f"🌟 [AUTO-UPGRADE DETECTED] New Gemini generation model available: {latest_model} "
                        f"(current: {current_env_model}). Auto-upgrading agent engine!"
                    )
                    self._update_env_file(latest_model)
                elif not curr_parsed and new_parsed:
                    self._update_env_file(latest_model)

            self._write_cache(latest_model, tier_candidates)
            return latest_model, tier_candidates

        except Exception as e:
            logger.warning(f"Error querying Gemini models list ({e}). Using cached or fallback candidate list.")
            cached = self._read_cache()
            if cached and cached.get("latest_model"):
                return cached["latest_model"], cached.get("tier_candidates", DEFAULT_TIER_FALLBACKS)
            return DEFAULT_FALLBACK_CANDIDATES[0], DEFAULT_TIER_FALLBACKS


_resolver = ModelResolver()


def get_latest_gemini_model(fallback: str = "gemini-4-argon", force_refresh: bool = False) -> str:
    """
    Returns the latest available Gemini model string (default: 'gemini-4-argon').
    Respects runtime user override if set.
    """
    runtime_override = get_runtime_model()
    if runtime_override:
        return runtime_override

    try:
        latest, _ = _resolver.discover_models(force_refresh=force_refresh)
        return latest or fallback
    except Exception:
        return fallback


def get_candidate_models(
    preferred: Optional[str] = None,
    tier: str = "argon",
) -> List[str]:
    """
    Returns an ordered list of candidate models from newest/best to fallback.
    User priority:
    1. Runtime user override (via CLI --model or UI menu)
    2. Preferred model passed as argument
    3. Tier-based candidates sorted by semantic version
    """
    tier_key = tier.lower() if tier.lower() in DEFAULT_TIER_FALLBACKS else "argon"
    try:
        _, tier_map = _resolver.discover_models()
        candidates = list(tier_map.get(tier_key, DEFAULT_TIER_FALLBACKS[tier_key]))
    except Exception:
        candidates = list(DEFAULT_TIER_FALLBACKS.get(tier_key, DEFAULT_FALLBACK_CANDIDATES))

    user_override = get_runtime_model()
    chosen_pref = user_override or preferred

    if chosen_pref:
        clean_pref = chosen_pref.replace("models/", "").strip()
        if clean_pref in candidates:
            candidates.remove(clean_pref)
        candidates.insert(0, clean_pref)

    return list(dict.fromkeys(candidates))


def call_gemini_resilient(
    client: Any,
    contents: Any,
    config: Optional[Any] = None,
    preferred_model: Optional[str] = None,
    tier: str = "argon",
    task_name: str = "Gemini Operation",
) -> Tuple[Any, str]:
    """
    Executes a Gemini generate_content call with bulletproof candidate failover.
    Automatically handles 503 (high demand), 429 (rate limits), and 404 (deprecated models)
    by seamlessly promoting the next model in the candidate chain.
    """
    candidates = get_candidate_models(preferred=preferred_model, tier=tier)
    last_exception = None

    for idx, model in enumerate(candidates):
        try:
            logger.info(f"🤖 [{task_name}] Invoking Gemini model: {model} (candidate {idx + 1}/{len(candidates)})")
            kwargs: Dict[str, Any] = {"model": model, "contents": contents}
            if config is not None:
                kwargs["config"] = config

            response = client.models.generate_content(**kwargs)
            logger.info(f"✨ [{task_name}] Successfully completed using {model}")
            return response, model

        except Exception as err:
            err_str = str(err)
            last_exception = err
            is_demand_spike = "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str
            is_quota_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
            is_not_found = "404" in err_str or "NOT_FOUND" in err_str

            if is_demand_spike:
                logger.warning(f"⚠️ [{task_name}] Model {model} is experiencing high demand (503). Auto-failing over to next model...")
            elif is_quota_limit:
                logger.warning(f"⚠️ [{task_name}] Model {model} hit rate limit (429). Auto-failing over to next model...")
            elif is_not_found:
                logger.warning(f"⚠️ [{task_name}] Model {model} is deprecated/not found (404). Auto-failing over to next model...")
            else:
                logger.warning(f"⚠️ [{task_name}] Model {model} encountered error: {err}. Trying next candidate...")

            continue

    raise RuntimeError(
        f"All candidate Gemini models failed for '{task_name}'. Last error: {last_exception}"
    )
