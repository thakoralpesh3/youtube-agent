import datetime
import json
import logging
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from google import genai
from google.genai import types

import config
from growth.model_resolver import call_gemini_resilient
from syndication.api_uploader import DirectSocialApiUploader
from syndication.social_auth import SocialAuth

logger = logging.getLogger(__name__)


class SocialGrowthEngine:
    """
    Autonomous Social Media Analytics & Content Evolution Engine (Instagram, Facebook, WhatsApp).
    Fetches live Reels/Feed/Page engagement telemetry and local publishing history,
    identifies what drives views, likes, shares & watch completion, and evolves
    prompts, captions, visuals, and hashtags for Chamunda Automobile.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.memory_file = config.OUTPUT_DIR / "social_growth.json"
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

    def load_social_memory(self) -> Dict[str, Any]:
        """Loads accumulated social growth intelligence or clean domain defaults."""
        if self.memory_file.exists():
            try:
                data = json.loads(self.memory_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception as e:
                logger.warning(f"Failed to read social growth memory: {e}")

        return {
            "total_posts_analyzed": 0,
            "analytics_sources": [],
            "winning_content_angles": [
                "Practical Royal Enfield service & mechanical care in Kalol (e.g., oil viscosity, one-way clutch, tappet tuning)",
                "Devotional Indian cultural blessings blended cleanly with Royal Enfield highway pride",
                "Specific model showcase (Classic 350, Bullet 350, Himalayan 450, 650 Twins) solving rider pain points",
            ],
            "winning_hook_formulas": [
                "Open immediately with a specific rider pain point or workshop insight in the first 2 seconds",
                "Pair regional Gujarati/Hindi warmth with concrete Royal Enfield model or service details",
            ],
            "top_hashtags": [
                "#RoyalEnfield", "#ChamundaAutomobile", "#Classic350", "#Bullet350",
                "#Kalol", "#GujaratBikers", "#PureMotorcycling", "#RE350", "#ReelsIndia",
            ],
            "caption_rules": [
                "Put a punchy 1-line hook or service tip at the very top before the contact block.",
                "Always include Chamunda Automobile Kalol location and Hitesh/Alpesh contact numbers cleanly.",
            ],
            "visual_and_pacing_rules": [
                "Prefer Reels with 3-4 distinct dynamic visual cuts (3-5s each) over single static poster loops.",
                "Always feature sharp mechanical details, genuine spare parts, or festive decorated motorcycles.",
            ],
            "avoid_patterns": [
                "Avoid posting static feed photos or blank-caption clips with zero searchable keywords.",
                "Avoid repeating identical weekday greeting templates verbatim.",
            ],
            "recommended_daily_angles": [
                "Classic 350 & Bullet 350 Tappet & Engine Oil Secret — Why Kalol Heat Requires Timely Viscosity Change",
                "Royal Enfield One-Way Bearing & Chain Sprocket Inspection Before Highway Touring",
                "Himalayan 450 & Meteor 350 Genuine Spare Parts vs Local Duplicate Warning",
            ],
            "social_growth_score": 100,
        }

    def _fetch_instagram_metrics(self, max_items: int = 20) -> Dict[str, Any]:
        """Queries Instagram profile and recent Reels/Feed media via DirectSocialApiUploader."""
        result: Dict[str, Any] = {"connected": False, "account": {}, "posts": []}
        try:
            uploader = DirectSocialApiUploader()
            cl = uploader.get_instagram_client()
            if not cl or not getattr(cl, "user_id", None):
                return result

            uid = cl.user_id
            info = cl.user_info(uid)
            followers = int(getattr(info, "follower_count", 0) or 0)
            media_count = int(getattr(info, "media_count", 0) or 0)

            result["connected"] = True
            result["account"] = {
                "username": getattr(info, "username", ""),
                "followers": followers,
                "media_count": media_count,
                "is_business": bool(getattr(info, "is_business", False)),
            }

            try:
                medias = cl.user_medias_v1(uid, amount=max_items)
            except Exception:
                medias = cl.user_medias(uid, amount=max_items)

            posts = []
            for m in medias:
                caption = (getattr(m, "caption_text", "") or "").strip()
                views = int(getattr(m, "view_count", 0) or getattr(m, "play_count", 0) or 0)
                likes = int(getattr(m, "like_count", 0) or 0)
                comments = int(getattr(m, "comment_count", 0) or 0)
                dur = round(float(getattr(m, "video_duration", 0.0) or 0.0), 1)
                prod = str(getattr(m, "product_type", "") or ("clips" if getattr(m, "media_type", 1) == 2 else "feed"))
                hashtags = re.findall(r"#\w+", caption.lower())
                denom = max(views, followers, 1)
                taken_at = getattr(m, "taken_at", None)
                posts.append({
                    "platform": "instagram",
                    "id": str(getattr(m, "pk", "")),
                    "product_type": prod,
                    "media_type": int(getattr(m, "media_type", 1) or 1),
                    "duration_sec": dur,
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "engagement_rate": round(((likes + comments) / denom) * 100, 2),
                    "caption_snippet": caption.replace("\n", " ")[:120],
                    "has_caption": bool(caption),
                    "hashtags": hashtags[:12],
                    "posted_at": taken_at.strftime("%Y-%m-%d %H:%M") if taken_at else "",
                })

            result["posts"] = posts
        except Exception as e:
            logger.debug(f"Instagram analytics fetch notice: {e}")

        return result

    def _fetch_facebook_metrics(self, limit: int = 15) -> Dict[str, Any]:
        """Queries Facebook Page posts engagement if Meta Graph API token is configured."""
        result: Dict[str, Any] = {"connected": False, "posts": []}
        try:
            creds = SocialAuth().get_meta_credentials()
            token = creds.get("fb_page_token")
            page_id = creds.get("fb_page_id")
            if not token or not page_id:
                return result

            url = f"https://graph.facebook.com/v21.0/{page_id}/posts"
            params = {
                "fields": "id,message,created_time,shares,likes.summary(true),comments.summary(true)",
                "limit": limit,
                "access_token": token,
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return result

            result["connected"] = True
            for item in resp.json().get("data", []):
                msg = (item.get("message") or "").strip()
                likes = int(item.get("likes", {}).get("summary", {}).get("total_count", 0))
                comments = int(item.get("comments", {}).get("summary", {}).get("total_count", 0))
                shares = int(item.get("shares", {}).get("count", 0) if isinstance(item.get("shares"), dict) else 0)
                result["posts"].append({
                    "platform": "facebook",
                    "id": item.get("id", ""),
                    "product_type": "page_post",
                    "views": 0,
                    "likes": likes,
                    "comments": comments,
                    "shares": shares,
                    "caption_snippet": msg.replace("\n", " ")[:120],
                    "has_caption": bool(msg),
                    "hashtags": re.findall(r"#\w+", msg.lower())[:12],
                    "posted_at": str(item.get("created_time", ""))[:16],
                })
        except Exception as e:
            logger.debug(f"Facebook analytics fetch notice: {e}")

        return result

    def _collect_local_social_telemetry(self) -> Dict[str, Any]:
        """Aggregates delivery reliability and recent campaigns across local social logs."""
        delivery = {"total_attempts": 0, "published": 0, "pending_queue": 0, "by_platform": {}}

        hist_file = config.OUTPUT_DIR / "social_history.json"
        if hist_file.exists():
            try:
                events = json.loads(hist_file.read_text(encoding="utf-8"))
                if isinstance(events, list):
                    for ev in events:
                        plat = str(ev.get("platform", "unknown")).lower()
                        st = str(ev.get("status", "")).upper()
                        bucket = delivery["by_platform"].setdefault(plat, {"published": 0, "other": 0})
                        delivery["total_attempts"] += 1
                        if st in ("PUBLISHED", "SUCCESS"):
                            delivery["published"] += 1
                            bucket["published"] += 1
                        else:
                            bucket["other"] += 1
            except Exception:
                pass

        queue_file = config.OUTPUT_DIR / "pending_social" / "queue.json"
        if queue_file.exists():
            try:
                q_items = json.loads(queue_file.read_text(encoding="utf-8"))
                delivery["pending_queue"] = sum(
                    1 for it in q_items if it.get("status") == "PENDING" and it.get("pending_platforms")
                )
            except Exception:
                pass

        recent_campaigns = []
        fest_hist = config.OUTPUT_DIR / "festival_history.json"
        if fest_hist.exists():
            try:
                f_data = json.loads(fest_hist.read_text(encoding="utf-8"))
                if isinstance(f_data, dict):
                    vals = sorted(f_data.values(), key=lambda x: x.get("date", ""), reverse=True)
                    recent_campaigns = [
                        {"date": x.get("date", ""), "name": x.get("festival", "")}
                        for x in vals[:12]
                    ]
            except Exception:
                pass

        return {"delivery": delivery, "recent_campaigns": recent_campaigns}

    def _summarize_social(
        self,
        ig_data: Dict[str, Any],
        fb_data: Dict[str, Any],
        local_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Computes objective social performance KPIs, winning hashtags, and Reel vs Feed contrast."""
        all_posts = list(ig_data.get("posts", [])) + list(fb_data.get("posts", []))
        reels = [p for p in ig_data.get("posts", []) if p.get("product_type") == "clips" or p.get("media_type") == 2]
        feeds = [p for p in ig_data.get("posts", []) if p.get("product_type") == "feed" and p.get("media_type") == 1]

        reel_views = sum(p.get("views", 0) for p in reels)
        reel_likes = sum(p.get("likes", 0) for p in reels)
        feed_likes = sum(p.get("likes", 0) for p in feeds)

        scored = sorted(
            all_posts,
            key=lambda p: p.get("views", 0) + p.get("likes", 0) * 15 + p.get("comments", 0) * 25 + p.get("shares", 0) * 20,
            reverse=True,
        )
        top_posts = scored[:8]
        underperformers = [p for p in reversed(scored) if p.get("views", 0) < 300 and p.get("likes", 0) < 20][:6]

        # Extract hashtags that actually correlated with top posts
        tag_counter: Counter = Counter()
        for p in scored[: max(1, len(scored) // 2)]:
            for t in p.get("hashtags", []):
                tag_counter[t] += 1
        top_hashtags = [t for t, _ in tag_counter.most_common(12)]

        # Compute objective score from real IG/FB metrics
        ig_acc = ig_data.get("account", {})
        followers = ig_acc.get("followers", 0)
        total_likes = sum(p.get("likes", 0) for p in all_posts)
        total_views = sum(p.get("views", 0) for p in all_posts)
        score = min(999, 100 + (followers // 10) + (total_views // 100) + total_likes)

        return {
            "instagram_stats": {
                **ig_acc,
                "recent_reels_count": len(reels),
                "recent_reels_avg_views": round(reel_views / max(len(reels), 1), 1),
                "recent_reels_avg_likes": round(reel_likes / max(len(reels), 1), 1),
                "recent_feed_photos_count": len(feeds),
                "recent_feed_avg_likes": round(feed_likes / max(len(feeds), 1), 1),
                "total_recent_views": total_views,
                "total_recent_likes": total_likes,
            },
            "facebook_posts_count": len(fb_data.get("posts", [])),
            "delivery": local_data.get("delivery", {}),
            "recent_campaigns": local_data.get("recent_campaigns", []),
            "top_posts": top_posts,
            "underperformers": underperformers,
            "top_hashtags": top_hashtags,
            "social_growth_score": score,
        }

    def evolve_social_strategy(self, force: bool = False, cache_hours: float = 4.0) -> Dict[str, Any]:
        """
        Fetches live Instagram/Facebook/local metrics, uses Gemini to extract winning
        Royal Enfield / cultural hooks & visual pacing rules, and saves output/social_growth.json.
        """
        memory = self.load_social_memory()
        last_ts = float(memory.get("last_analyzed_ts", 0) or 0)
        if (
            not force
            and last_ts > 0
            and (time.time() - last_ts) < cache_hours * 3600
            and memory.get("instagram_stats")
        ):
            logger.debug("Using fresh cached social growth strategy (<4h old).")
            return memory

        ig_data = self._fetch_instagram_metrics()
        fb_data = self._fetch_facebook_metrics()
        local_data = self._collect_local_social_telemetry()

        sources = []
        if ig_data.get("connected"):
            sources.append("instagram_api")
        if fb_data.get("connected"):
            sources.append("facebook_graph_api")
        sources.append("local_telemetry")

        all_posts = ig_data.get("posts", []) + fb_data.get("posts", [])
        if not all_posts:
            logger.info("Using baseline social growth strategy (no live posts retrieved yet).")
            memory["analytics_sources"] = sources
            memory["delivery"] = local_data.get("delivery", {})
            return memory

        digest = self._summarize_social(ig_data, fb_data, local_data)
        ig_stats = digest["instagram_stats"]
        logger.info(
            f"📱 [Social Growth] Analyzed {len(all_posts)} social post(s) "
            f"(IG @{ig_stats.get('username', 'N/A')}: {ig_stats.get('followers', 0)} followers, "
            f"Reels avg {ig_stats.get('recent_reels_avg_views', 0)} views / {ig_stats.get('recent_reels_avg_likes', 0)} likes)..."
        )

        evolved: Optional[dict] = None
        if self.client:
            prompt = f"""
You are a Social Media Growth & Reels Strategist for 'Chamunda Automobile Parts & Services' (Kalol, Gujarat — Royal Enfield Specialist Only).
Analyze real social account performance metrics:

INSTAGRAM STATS:
{json.dumps(ig_stats, indent=2)}

TOP PERFORMING POSTS (Highest Views/Likes/Comments):
{json.dumps(digest["top_posts"], indent=2, ensure_ascii=False)}

LOWER PERFORMING POSTS:
{json.dumps(digest["underperformers"], indent=2, ensure_ascii=False)}

TOP HASHTAGS FROM WINNERS:
{json.dumps(digest["top_hashtags"], indent=2)}

RECENT LOCAL CAMPAIGNS ALREADY POSTED:
{json.dumps(digest["recent_campaigns"][:8], indent=2)}

Task: Formulate specific improvements so daily Royal Enfield Reels, Posters, Stories & Captions get higher views, likes, shares, watch completion, and local workshop inquiries.
Notice what wins: specific RE mechanical/service topics (Kalol service, spare parts, exhaust/thump, bearing/maintenance) + high-emotion festival/devotional Reels outperform captionless or static posts!

Respond ONLY with valid JSON matching this schema:
{{
  "winning_content_angles": ["3 concrete winning content angles for Chamunda Automobile"],
  "winning_hook_formulas": ["3 opening 2-second voiceover/visual hooks for Reels & Stories"],
  "top_hashtags": ["8 to 12 high-reach hashtags including Royal Enfield and Gujarat/Kalol tags"],
  "caption_rules": ["3 specific caption rules (line 1 hook, CTA, clarity)"],
  "visual_and_pacing_rules": ["3 rules for higher Reel watch time and completion"],
  "avoid_patterns": ["3 underperforming patterns to stop repeating"],
  "recommended_daily_angles": ["5 fresh non-duplicate Royal Enfield daily topic ideas (technical tips + rider pride) distinct from recent campaigns"]
}}
"""
            try:
                res, used_model = call_gemini_resilient(
                    client=self.client,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.4,
                    ),
                    tier="argon",
                    task_name="Social Growth Strategy Evolution",
                )
                parsed = json.loads(res.text)
                if isinstance(parsed, dict) and parsed.get("winning_content_angles"):
                    evolved = parsed
                    logger.info(f"🚀 Social Growth Memory updated via {used_model}!")
            except Exception as e:
                logger.info(f"ℹ️ Social Gemini synthesis fallback ({e}); persisting live stats directly.")

        merged_tags = (evolved or {}).get("top_hashtags") or digest["top_hashtags"] or memory.get("top_hashtags", [])
        updated = {
            **memory,
            **(evolved or {}),
            "total_posts_analyzed": len(all_posts),
            "analytics_sources": sources,
            "instagram_stats": ig_stats,
            "top_posts": digest["top_posts"][:6],
            "top_hashtags": merged_tags,
            "delivery": digest["delivery"],
            "recent_campaigns": digest["recent_campaigns"],
            "social_growth_score": digest["social_growth_score"],
            "last_analyzed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_analyzed_ts": time.time(),
        }

        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.memory_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.memory_file)
        except Exception as e:
            logger.warning(f"Failed to persist social growth memory: {e}")

        return updated

    def get_social_prompt_context(self) -> str:
        """Formats live learned Social insights for injection into ChamundaFestivalCreator."""
        mem = self.load_social_memory()
        ig = mem.get("instagram_stats", {})
        angles = "\n".join([f"  • {a}" for a in mem.get("winning_content_angles", [])[:3]])
        hooks = "\n".join([f"  • {h}" for h in mem.get("winning_hook_formulas", [])[:3]])
        rules = "\n".join([f"  • {r}" for r in mem.get("visual_and_pacing_rules", [])[:3]])
        avoid = "\n".join([f"  ✗ {a}" for a in mem.get("avoid_patterns", [])[:3]])
        wins = "\n".join(
            [f"  ★ {p.get('views', 0)} views, {p.get('likes', 0)} likes: \"{p.get('caption_snippet', '')[:65]}\""
             for p in mem.get("top_posts", [])[:3]]
        )

        stats_line = (
            f"IG Followers={ig.get('followers', 0)}, Reels Avg={ig.get('recent_reels_avg_views', 0)} views / {ig.get('recent_reels_avg_likes', 0)} likes"
            if ig
            else "Using Chamunda Royal Enfield domain growth defaults"
        )

        parts = [f"LIVE SOCIAL ANALYTICS INTELLIGENCE ({stats_line}):"]
        if wins:
            parts.append(f"Top Performing Posts:\n{wins}")
        if angles:
            parts.append(f"Winning Angles:\n{angles}")
        if hooks:
            parts.append(f"Winning Hooks:\n{hooks}")
        if rules:
            parts.append(f"Visual & Retention Rules:\n{rules}")
        if avoid:
            parts.append(f"Patterns to Avoid:\n{avoid}")
        return "\n\n".join(parts)
