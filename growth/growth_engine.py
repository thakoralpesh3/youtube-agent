import datetime
import json
import logging
import re
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

import config
from growth.model_resolver import call_gemini_resilient
from youtube.auth import YouTubeAuth

logger = logging.getLogger(__name__)


def _parse_iso_duration_sec(duration_str: str) -> int:
    """Converts YouTube ISO-8601 duration (e.g., PT1M23S) into integer seconds."""
    if not duration_str:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", str(duration_str))
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(m.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def _detect_lang_code(title: str, lang_hint: Optional[str] = None) -> str:
    """Detects 'hi', 'gu', or 'en' from script unicode range or metadata hint."""
    if title:
        if re.search(r"[\u0A80-\u0AFF]", title):
            return "gu"
        if re.search(r"[\u0900-\u097F]", title):
            return "hi"
    if lang_hint and str(lang_hint).lower().startswith("gu"):
        return "gu"
    if lang_hint and str(lang_hint).lower().startswith("hi"):
        return "hi"
    return "en"


class GrowthEngine:
    """
    Autonomous Channel Growth, Watch-Hours & Self-Evolution Engine.
    Analyzes live YouTube channel performance (Data API v3 + YouTube Analytics v2 when authorized),
    links runs to scripts/hooks, diagnoses what drives views, likes & watch time vs zero-view flops,
    and feeds concrete data-backed rules back into content generation.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.memory_file = config.OUTPUT_DIR / "channel_growth.json"
        self.last_channel_overview: Dict[str, Any] = {}
        self.last_analytics_source: str = "baseline"
        self.client = (
            genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=20000.0,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            if self.api_key
            else None
        )

    def load_growth_memory(self) -> dict:
        """Loads accumulated growth lessons and winning formulas."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception as e:
                logger.warning(f"Failed to read growth memory: {e}")

        # Default foundational baseline rules for adult motivation & health/fitness
        return {
            "total_videos_analyzed": 0,
            "analytics_source": "baseline",
            "best_performing_hook_styles": [
                "Plain-Spoken Relatable Paradox (e.g., 'Stop letting small things steal your peace')",
                "Concrete 1-Number Curiosity Gap (e.g., 'The 1 habit keeping you exhausted all day')",
                "High-Stakes Actionable Contrast (e.g., 'Why forcing motivation fails within 72 hours')",
            ],
            "peak_engagement_themes": [
                "Stoic calm under daily stress and emotional control",
                "Clear, relatable hydration, sleep, and morning focus science",
                "Practical financial self-control and apex focus habits",
            ],
            "key_retention_rules": [
                "Open in the first 2.5 seconds with 'you' and concrete personal stakes — zero abstract jargon.",
                "Use 5-6 rapid visual scene cuts (3.0-4.5s each) matching spoken beats.",
                "End on a loop connector so the final line flows back into the opening hook (>100% APV).",
            ],
            "long_form_watch_hour_rules": [
                "Write specific curiosity-driven titles (<60 chars, no generic 'Masterclass Guide' repetition).",
                "Open with immediate stakes in seconds 0-15 before introducing any framework.",
                "Insert a curiosity re-hook every chapter ('But here is the trap 90% miss...') to hold watch time.",
            ],
            "winning_title_patterns": [
                "Short emotional truth + #Shorts (<45 chars)",
                "Specific single number hook (e.g. '1 Habit', '72-Hour Rule')",
            ],
            "underperforming_patterns_to_avoid": [
                "Never repeat previously uploaded or fallback titles.",
                "Avoid overly academic 'Glitch' buzzword titles that feel clinical or repetitive.",
            ],
            "saturated_titles": [],
            "optimal_shorts_duration_sec": "28-42",
            "growth_score": 100,
        }

    def _collect_local_run_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Maps uploaded YouTube video_ids to local script/package metadata across all runs."""
        id_map: Dict[str, Dict[str, Any]] = {}
        for summary_file in sorted(config.OUTPUT_DIR.glob("run_*/summary.json"), reverse=True):
            run_dir = summary_file.parent
            try:
                data = json.loads(summary_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            pkg_data: Dict[str, Any] = {}
            for cand_name in ("package.json", "script.json", "long_video_script.json"):
                cand_path = run_dir / cand_name
                if cand_path.exists():
                    try:
                        pkg_data = json.loads(cand_path.read_text(encoding="utf-8"))
                        break
                    except Exception:
                        pass

            base_topic = data.get("topic") or pkg_data.get("topic") or ""
            theme_cat = data.get("theme_category") or pkg_data.get("theme_category") or ""

            # 1. Legacy single Short summary
            upload_res = data.get("upload_result")
            if isinstance(upload_res, dict) and upload_res.get("video_id"):
                scenes = pkg_data.get("scenes", []) if isinstance(pkg_data, dict) else []
                hook_line = scenes[0].get("narration", "") if scenes else ""
                id_map[upload_res["video_id"]] = {
                    "topic": base_topic or data.get("title", ""),
                    "theme_category": theme_cat,
                    "lang": "en",
                    "format": "short",
                    "hook_line": hook_line,
                    "scene_count": len(scenes),
                }

            # 2. Trilingual Shorts (EN, HI, GU)
            yt_dict = data.get("youtube")
            if isinstance(yt_dict, dict):
                lang_key_map = {"en": "english", "hi": "hindi", "gu": "gujarati"}
                for lc, res in yt_dict.items():
                    if isinstance(res, dict) and res.get("video_id"):
                        l_pkg = pkg_data.get(lang_key_map.get(lc, ""), {}) if isinstance(pkg_data, dict) else {}
                        scenes = l_pkg.get("scenes", []) if isinstance(l_pkg, dict) else []
                        hook_line = scenes[0].get("narration", "") if scenes else ""
                        id_map[res["video_id"]] = {
                            "topic": base_topic,
                            "theme_category": theme_cat,
                            "lang": lc,
                            "format": "short",
                            "hook_line": hook_line,
                            "scene_count": len(scenes),
                        }

            # 3. Standard 16:9 Landscape Video
            yt_vid = data.get("youtube_video")
            if isinstance(yt_vid, dict):
                v_up = yt_vid.get("upload_result", {})
                if isinstance(v_up, dict) and v_up.get("video_id"):
                    id_map[v_up["video_id"]] = {
                        "topic": base_topic or yt_vid.get("title", ""),
                        "theme_category": theme_cat or "long_form",
                        "lang": "en",
                        "format": "long",
                        "hook_line": "",
                        "scene_count": 0,
                    }

        return id_map

    def _fetch_youtube_analytics_v2(self, creds: Any) -> Dict[str, Dict[str, Any]]:
        """
        Queries YouTube Analytics API v2 for true watch-time and retention metrics
        if the current OAuth token includes 'yt-analytics.readonly'.
        """
        scopes = set(getattr(creds, "scopes", None) or [])
        if "https://www.googleapis.com/auth/yt-analytics.readonly" not in scopes:
            return {}

        try:
            from googleapiclient.discovery import build

            yta = build("youtubeAnalytics", "v2", credentials=creds)
            end_date = datetime.date.today().strftime("%Y-%m-%d")
            start_date = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
            res = yta.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,subscribersGained",
                dimensions="video",
                maxResults=200,
                sort="-estimatedMinutesWatched",
            ).execute()

            per_video: Dict[str, Dict[str, Any]] = {}
            for row in res.get("rows", []):
                # [video_id, views, est_min_watched, avg_view_dur, avg_view_pct, likes, subs_gained]
                if len(row) >= 7:
                    per_video[str(row[0])] = {
                        "analytics_views": int(row[1] or 0),
                        "watch_minutes": round(float(row[2] or 0.0), 2),
                        "avg_view_duration_sec": round(float(row[3] or 0.0), 1),
                        "avg_view_percentage": round(float(row[4] or 0.0), 1),
                        "subscribers_gained": int(row[6] or 0),
                    }
            return per_video
        except Exception as e:
            logger.debug(f"YouTube Analytics v2 query skipped: {e}")
            return {}

    def fetch_uploaded_video_analytics(self, max_channel_videos: int = 200) -> List[dict]:
        """Scans local runs AND channel uploads playlist for live stats and watch-time signals."""
        local_meta = self._collect_local_run_metadata()

        auth = YouTubeAuth()
        if not auth.is_token_valid():
            logger.debug("YouTube OAuth token not valid or expired. Skipping live analytics sync.")
            self.last_analytics_source = "local_only"
            return [
                {
                    "video_id": vid,
                    "title": meta.get("topic", ""),
                    "views": 0,
                    "likes": 0,
                    "comments": 0,
                    **meta,
                }
                for vid, meta in local_meta.items()
            ]

        try:
            from googleapiclient.discovery import build

            creds = auth.get_credentials()
            youtube = build("youtube", "v3", credentials=creds)

            ch_res = youtube.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
            ch_items = ch_res.get("items", [])
            channel_video_ids: List[str] = []
            if ch_items:
                ch = ch_items[0]
                ch_stats = ch.get("statistics", {})
                self.last_channel_overview = {
                    "channel_title": ch.get("snippet", {}).get("title", ""),
                    "subscribers": int(ch_stats.get("subscriberCount", 0)),
                    "total_channel_views": int(ch_stats.get("viewCount", 0)),
                    "total_channel_videos": int(ch_stats.get("videoCount", 0)),
                }
                uploads_pl = ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
                if uploads_pl:
                    page_token = None
                    while len(channel_video_ids) < max_channel_videos:
                        pl_res = youtube.playlistItems().list(
                            part="contentDetails",
                            playlistId=uploads_pl,
                            maxResults=50,
                            pageToken=page_token,
                        ).execute()
                        for item in pl_res.get("items", []):
                            vid = item.get("contentDetails", {}).get("videoId")
                            if vid and vid not in channel_video_ids:
                                channel_video_ids.append(vid)
                        page_token = pl_res.get("nextPageToken")
                        if not page_token:
                            break

            # Include any local run IDs not already in the recent uploads slice
            for vid in local_meta:
                if vid not in channel_video_ids:
                    channel_video_ids.append(vid)

            if not channel_video_ids:
                return []

            analytics_v2 = self._fetch_youtube_analytics_v2(creds)
            self.last_analytics_source = "youtube_analytics_v2" if analytics_v2 else "youtube_data_api_v3"

            enriched: List[dict] = []
            for i in range(0, len(channel_video_ids), 50):
                batch = channel_video_ids[i : i + 50]
                v_res = youtube.videos().list(
                    part="snippet,statistics,contentDetails,status",
                    id=",".join(batch),
                ).execute()
                for item in v_res.get("items", []):
                    vid = item["id"]
                    snip = item.get("snippet", {})
                    stats = item.get("statistics", {})
                    cd = item.get("contentDetails", {})
                    status = item.get("status", {})
                    meta = local_meta.get(vid, {})

                    title = snip.get("title", "")
                    duration_sec = _parse_iso_duration_sec(cd.get("duration", ""))
                    views = int(stats.get("viewCount", 0))
                    likes = int(stats.get("likeCount", 0))
                    comments = int(stats.get("commentCount", 0))
                    fmt = meta.get("format") or ("short" if 0 < duration_sec <= 65 else "long")
                    lang = meta.get("lang") or _detect_lang_code(title, snip.get("defaultAudioLanguage"))
                    engagement_rate = round(((likes + comments) / max(views, 1)) * 100, 2)

                    # True Studio watch metrics if authorized; otherwise duration-weighted conservative estimate
                    yta_row = analytics_v2.get(vid, {})
                    if yta_row:
                        watch_minutes = yta_row["watch_minutes"]
                        avg_view_pct = yta_row["avg_view_percentage"]
                        avg_view_dur = yta_row["avg_view_duration_sec"]
                        subs_gained = yta_row["subscribers_gained"]
                    else:
                        est_retention = 0.65 if fmt == "short" else 0.30
                        watch_minutes = round((views * duration_sec * est_retention) / 60.0, 2) if duration_sec else 0.0
                        avg_view_pct = None
                        avg_view_dur = None
                        subs_gained = 0

                    enriched.append({
                        "video_id": vid,
                        "title": title,
                        "published_at": snip.get("publishedAt", ""),
                        "privacy": status.get("privacyStatus", "public"),
                        "format": fmt,
                        "lang": lang,
                        "duration_sec": duration_sec,
                        "views": views,
                        "likes": likes,
                        "comments": comments,
                        "engagement_rate": engagement_rate,
                        "watch_minutes": watch_minutes,
                        "avg_view_percentage": avg_view_pct,
                        "avg_view_duration_sec": avg_view_dur,
                        "subscribers_gained": subs_gained,
                        "topic": meta.get("topic", ""),
                        "hook_line": meta.get("hook_line", ""),
                    })

            return enriched
        except Exception as e:
            logger.debug(f"Could not query live YouTube stats (offline or unauthenticated): {e}")
            self.last_analytics_source = "local_fallback"
            return [
                {"video_id": vid, "title": meta.get("topic", ""), "views": 0, "likes": 0, "comments": 0, **meta}
                for vid, meta in local_meta.items()
            ]

    def _summarize_analytics(self, analytics: List[dict]) -> Dict[str, Any]:
        """Aggregates deterministic channel metrics, language winners, format ROI, and duplicate saturation."""
        total = len(analytics)
        total_views = sum(v.get("views", 0) for v in analytics)
        total_likes = sum(v.get("likes", 0) for v in analytics)
        total_comments = sum(v.get("comments", 0) for v in analytics)
        total_watch_hours = round(sum(v.get("watch_minutes", 0.0) for v in analytics) / 60.0, 2)
        zero_views = sum(1 for v in analytics if v.get("views", 0) == 0)

        shorts = [v for v in analytics if v.get("format") == "short"]
        longs = [v for v in analytics if v.get("format") == "long"]

        # Language performance breakdown
        lang_perf: Dict[str, Dict[str, Any]] = {}
        for lc in ("en", "hi", "gu"):
            subset = [v for v in shorts if v.get("lang") == lc]
            sv = sum(x.get("views", 0) for x in subset)
            sl = sum(x.get("likes", 0) for x in subset)
            lang_perf[lc] = {
                "count": len(subset),
                "total_views": sv,
                "avg_views": round(sv / max(len(subset), 1), 2),
                "total_likes": sl,
            }

        # Shorts duration sweet spot
        buckets = {"under_30s": [], "30_to_45s": [], "46_to_65s": []}
        for s in shorts:
            d = s.get("duration_sec", 0)
            if 0 < d < 30:
                buckets["under_30s"].append(s.get("views", 0))
            elif 30 <= d <= 45:
                buckets["30_to_45s"].append(s.get("views", 0))
            elif d > 45:
                buckets["46_to_65s"].append(s.get("views", 0))

        bucket_avgs = {
            k: round(sum(vals) / len(vals), 2) if vals else 0.0
            for k, vals in buckets.items()
        }
        best_bucket = max(bucket_avgs, key=lambda k: bucket_avgs[k]) if any(bucket_avgs.values()) else "30_to_45s"
        dur_map = {"under_30s": "20-29", "30_to_45s": "30-42", "46_to_65s": "45-55"}

        # Detect duplicate/saturated titles uploaded repeatedly
        title_counts = Counter(v.get("title", "").strip() for v in analytics if v.get("title", "").strip())
        saturated_titles = [t for t, c in title_counts.most_common(25) if c >= 2]
        duplicate_extra_uploads = sum(c - 1 for c in title_counts.values() if c >= 2)

        # Rank top performers by weighted impact (views + likes + comments + watch time)
        scored = sorted(
            analytics,
            key=lambda v: (
                v.get("views", 0)
                + v.get("likes", 0) * 15
                + v.get("comments", 0) * 25
                + v.get("watch_minutes", 0.0) * 3
            ),
            reverse=True,
        )
        top_performers = [
            {
                "title": v.get("title", ""),
                "format": v.get("format", "short"),
                "lang": v.get("lang", "en"),
                "duration_sec": v.get("duration_sec", 0),
                "views": v.get("views", 0),
                "likes": v.get("likes", 0),
                "comments": v.get("comments", 0),
                "watch_minutes": v.get("watch_minutes", 0.0),
            }
            for v in scored[:12]
            if v.get("views", 0) > 0
        ]

        # Sample unique recent underperformers (0-view / low-traction patterns to diagnose)
        seen_flop_titles = set()
        underperformers = []
        for v in reversed(scored):
            t = v.get("title", "").strip()
            if t and t not in seen_flop_titles and v.get("views", 0) <= 1:
                seen_flop_titles.add(t)
                underperformers.append({
                    "title": t,
                    "format": v.get("format", "short"),
                    "duration_sec": v.get("duration_sec", 0),
                    "views": v.get("views", 0),
                })
            if len(underperformers) >= 10:
                break

        short_views = sum(v.get("views", 0) for v in shorts)
        long_views = sum(v.get("views", 0) for v in longs)

        return {
            "channel_stats": {
                "total_videos_analyzed": total,
                "total_views": total_views,
                "total_likes": total_likes,
                "total_comments": total_comments,
                "estimated_watch_hours": total_watch_hours,
                "zero_view_count": zero_views,
                "zero_view_rate_pct": round((zero_views / max(total, 1)) * 100, 1),
                "duplicate_title_uploads": duplicate_extra_uploads,
                "shorts_count": len(shorts),
                "shorts_avg_views": round(short_views / max(len(shorts), 1), 2),
                "long_count": len(longs),
                "long_avg_views": round(long_views / max(len(longs), 1), 2),
                "subscribers": self.last_channel_overview.get("subscribers", 0),
                "channel_total_views": self.last_channel_overview.get("total_channel_views", total_views),
                "channel_total_videos": self.last_channel_overview.get("total_channel_videos", total),
            },
            "language_performance": lang_perf,
            "duration_buckets_avg_views": bucket_avgs,
            "optimal_shorts_duration_sec": dur_map.get(best_bucket, "30-42"),
            "saturated_titles": saturated_titles,
            "top_performers": top_performers,
            "underperformers": underperformers,
        }

    def evolve_channel_strategy(self, force: bool = False, cache_hours: float = 4.0) -> dict:
        """
        Analyzes live YouTube channel performance across all uploaded videos & watch hours,
        extracts winning patterns and failure traps via Gemini, and persists evolved rules.
        """
        memory = self.load_growth_memory()
        last_ts = float(memory.get("last_analyzed_ts", 0) or 0)
        if (
            not force
            and last_ts > 0
            and (time.time() - last_ts) < cache_hours * 3600
            and memory.get("channel_stats")
        ):
            logger.debug("Using fresh cached channel growth strategy (<4h old).")
            return memory

        analytics = self.fetch_uploaded_video_analytics()
        if not analytics or len(analytics) < 2:
            logger.info("Using baseline high-performance growth strategy.")
            return memory

        digest = self._summarize_analytics(analytics)
        stats = digest["channel_stats"]
        objective_score = min(
            999,
            100
            + (stats["total_views"] // 20)
            + (stats["total_likes"] * 3)
            + (stats["total_comments"] * 5)
            + int(stats["estimated_watch_hours"] * 5),
        )

        logger.info(
            f"🧠 Analyzing {len(analytics)} YouTube videos "
            f"(Views: {stats['total_views']}, Likes: {stats['total_likes']}, "
            f"Est. Watch Hours: {stats['estimated_watch_hours']}h, Source: {self.last_analytics_source})..."
        )

        evolved_insights: Optional[dict] = None
        if self.client:
            prompt = f"""
You are a senior YouTube Algorithm, Retention & Packaging Strategist.
Analyze real channel telemetry from '{self.last_channel_overview.get("channel_title", "our YouTube channel")}':

CHANNEL METRICS DIGEST:
{json.dumps(stats, indent=2)}

LANGUAGE PERFORMANCE (Shorts avg views by language):
{json.dumps(digest["language_performance"], indent=2)}

SHORTS DURATION BUCKETS (Avg views by length):
{json.dumps(digest["duration_buckets_avg_views"], indent=2)}

TOP PERFORMING VIDEOS (Winners in views/likes/watch-time):
{json.dumps(digest["top_performers"], indent=2, ensure_ascii=False)}

LOW / ZERO-VIEW SAMPLE (Diagnose why these got ignored):
{json.dumps(digest["underperformers"][:8], indent=2, ensure_ascii=False)}

DUPLICATED / SATURATED TITLES TO STRICTLY BAN:
{json.dumps(digest["saturated_titles"][:12], indent=2, ensure_ascii=False)}

PREVIOUS STRATEGY MEMORY:
{json.dumps({k: memory.get(k) for k in ("best_performing_hook_styles", "peak_engagement_themes", "key_retention_rules", "underperforming_patterns_to_avoid")}, indent=2, ensure_ascii=False)}

Objective: Maximize TOTAL WATCH HOURS, VIEWS, LIKES, and SUBSCRIBERS on the next Shorts (EN, HI, GU) AND 16:9 Landscape videos.
Look closely at why top performers won (plain relatable hooks, clear human benefit, punchy Hindi/English curiosity) vs why many videos got 0 views (repetitive generic 'Masterclass Guide' or abstract 'Glitch' buzzwords and duplicate uploads).

Respond ONLY with valid JSON matching this schema:
{{
  "best_performing_hook_styles": ["3 concrete winning opening hook formulas"],
  "peak_engagement_themes": ["3 highest-upside topic angles based on top winners"],
  "key_retention_rules": ["3 specific Shorts retention rules for >100% APV and likes"],
  "long_form_watch_hour_rules": ["3 specific 16:9 video rules for higher CTR and multi-minute watch hours"],
  "winning_title_patterns": ["3 specific high-CTR title templates (<55 chars, zero fluff)"],
  "underperforming_patterns_to_avoid": ["3 concrete mistakes/words/topics to STOP using immediately"],
  "recommended_next_topics": ["3 fresh, specific, unrepeated video topic ideas ready for next upload"]
}}
"""
            try:
                res, used_model = call_gemini_resilient(
                    client=self.client,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.35,
                    ),
                    tier="argon",
                    task_name="YouTube Growth Strategy Evolution",
                )
                parsed = json.loads(res.text)
                if isinstance(parsed, dict) and parsed.get("best_performing_hook_styles"):
                    evolved_insights = parsed
                    logger.info(f"🚀 Channel Growth Memory updated via {used_model}!")
            except Exception as e:
                logger.info(f"ℹ️ Gemini growth synthesis fallback ({e}); persisting statistical telemetry directly.")

        updated_memory = {
            **memory,
            **(evolved_insights or {}),
            "total_videos_analyzed": stats["total_videos_analyzed"],
            "analytics_source": self.last_analytics_source,
            "channel_stats": stats,
            "language_performance": digest["language_performance"],
            "duration_buckets_avg_views": digest["duration_buckets_avg_views"],
            "optimal_shorts_duration_sec": digest["optimal_shorts_duration_sec"],
            "top_performers": digest["top_performers"][:8],
            "saturated_titles": digest["saturated_titles"],
            "growth_score": objective_score,
            "last_analyzed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_analyzed_ts": time.time(),
        }

        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.memory_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(updated_memory, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.memory_file)
        except Exception as e:
            logger.warning(f"Failed to persist channel growth memory: {e}")

        return updated_memory

    def get_saturated_titles(self) -> List[str]:
        """Returns normalized list of duplicated/previously saturated channel titles to block reuse."""
        memory = self.load_growth_memory()
        return list(memory.get("saturated_titles", []))

    def get_growth_prompt_context(self, content_format: str = "shorts") -> str:
        """Formats live learned YouTube insights into concise actionable rules for ScriptGenerator."""
        memory = self.load_growth_memory()
        stats = memory.get("channel_stats", {})
        hooks = "\n".join([f"  • {h}" for h in memory.get("best_performing_hook_styles", [])[:4]])
        themes = "\n".join([f"  • {t}" for t in memory.get("peak_engagement_themes", [])[:4]])
        rules_key = "long_form_watch_hour_rules" if content_format == "long" else "key_retention_rules"
        rules_list = memory.get(rules_key) or memory.get("key_retention_rules", [])
        rules = "\n".join([f"  • {r}" for r in rules_list[:4]])
        avoid = "\n".join([f"  ✗ {a}" for a in memory.get("underperforming_patterns_to_avoid", [])[:4]])
        top_wins = "\n".join(
            [f"  ★ \"{p.get('title')}\" ({p.get('views', 0)} views, {p.get('likes', 0)} likes)"
             for p in memory.get("top_performers", [])[:4]]
        )
        saturated = "\n".join([f"  - {t}" for t in memory.get("saturated_titles", [])[:10]])

        telemetry_line = (
            f"Analyzed {stats.get('total_videos_analyzed', 0)} videos | "
            f"Avg Views: Shorts={stats.get('shorts_avg_views', 0)}, Long={stats.get('long_avg_views', 0)} | "
            f"Est. Watch Hours={stats.get('estimated_watch_hours', 0)}h | "
            f"Target Shorts Length={memory.get('optimal_shorts_duration_sec', '30-42')}s"
            if stats
            else "Using baseline channel optimization rules"
        )

        sections = [
            f"ALGORITHMIC CHANNEL PERFORMANCE INTELLIGENCE ({telemetry_line}):",
        ]
        if top_wins:
            sections.append(f"Proven Top Channel Performers (learn their plain relatable pull):\n{top_wins}")
        if hooks:
            sections.append(f"Top Hook Frameworks to apply:\n{hooks}")
        if themes:
            sections.append(f"Peak Engagement Themes:\n{themes}")
        if rules:
            label = "Watch-Hours & CTR Rules (16:9)" if content_format == "long" else "Retention & Likes Rules (Shorts)"
            sections.append(f"{label}:\n{rules}")
        if avoid:
            sections.append(f"STRICTLY AVOID (What caused 0-view flops):\n{avoid}")
        if saturated:
            sections.append(f"BANNED SATURATED TITLES (NEVER repeat or closely paraphrase):\n{saturated}")

        return "\n\n".join(sections)
