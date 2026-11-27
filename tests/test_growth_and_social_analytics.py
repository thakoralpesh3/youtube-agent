import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class TestYouTubeAndSocialAnalytics(unittest.TestCase):
    def test_growth_engine_parses_trilingual_long_and_detects_saturated(self):
        from growth.growth_engine import GrowthEngine, _parse_iso_duration_sec

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            run_dir = out_dir / "run_trilingual_20261126_090000"
            run_dir.mkdir(parents=True)
            (run_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "topic": "Stoic Focus",
                        "youtube": {
                            "en": {"video_id": "v_en_1", "title": "En Short"},
                            "hi": {"video_id": "v_hi_1", "title": "Hi Short"},
                            "gu": {"video_id": "v_gu_1", "title": "Gu Short"},
                        },
                        "youtube_video": {
                            "title": "Deep Masterclass",
                            "upload_result": {"video_id": "v_long_1"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            engine = GrowthEngine(api_key="dummy-key")
            engine.memory_file = out_dir / "channel_growth.json"

            self.assertEqual(_parse_iso_duration_sec("PT45S"), 45)
            self.assertEqual(_parse_iso_duration_sec("PT12M30S"), 750)
            self.assertEqual(_parse_iso_duration_sec("PT1H2M5S"), 3725)

            with patch("growth.growth_engine.config.OUTPUT_DIR", out_dir):
                local_meta = engine._collect_local_run_metadata()
            self.assertIn("v_en_1", local_meta)
            self.assertEqual(local_meta["v_en_1"]["lang"], "en")
            self.assertEqual(local_meta["v_hi_1"]["lang"], "hi")
            self.assertEqual(local_meta["v_gu_1"]["lang"], "gu")
            self.assertEqual(local_meta["v_long_1"]["format"], "long")

            videos = [
                {
                    "video_id": f"dup_{i}",
                    "title": "Repeated Trap Title #Shorts",
                    "published_at": "2026-11-20T09:00:00Z",
                    "duration_sec": 35,
                    "format": "short",
                    "lang": "en",
                    "views": 0,
                    "likes": 0,
                    "comments": 0,
                    "watch_minutes": 0.0,
                }
                for i in range(4)
            ] + [
                {
                    "video_id": "win_hi",
                    "title": "असली अनुशासन नियम #Shorts",
                    "published_at": "2026-11-22T09:00:00Z",
                    "duration_sec": 22,
                    "format": "short",
                    "lang": "hi",
                    "views": 180,
                    "likes": 9,
                    "comments": 2,
                    "watch_minutes": 43.2,
                },
                {
                    "video_id": "long_1",
                    "title": "10 Stoic Systems For Builders",
                    "published_at": "2026-11-24T09:00:00Z",
                    "duration_sec": 540,
                    "format": "long",
                    "lang": "en",
                    "views": 40,
                    "likes": 4,
                    "comments": 1,
                    "watch_minutes": 108.0,
                },
            ]
            summary = engine._summarize_analytics(videos)
            stats = summary["channel_stats"]
            self.assertEqual(stats["total_videos_analyzed"], 6)
            self.assertEqual(stats["total_views"], 220)
            self.assertGreater(stats["estimated_watch_hours"], 2.4)
            self.assertIn("Repeated Trap Title #Shorts", summary["saturated_titles"])
            self.assertEqual(summary["language_performance"]["hi"]["avg_views"], 180.0)

            engine.memory_file.write_text(
                json.dumps(
                    {
                        "saturated_titles": ["Repeated Trap Title #Shorts"],
                        "peak_engagement_themes": ["Focus discipline"],
                        "best_performing_hook_styles": ["Open with a 2-second contrast"],
                        "key_retention_rules": ["Keep 5 scenes under 4s each"],
                        "long_form_watch_hour_rules": ["Use bold 2-word thumbnail accents"],
                        "underperforming_patterns_to_avoid": ["Repeating identical fallback titles"],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(engine.get_saturated_titles(), ["Repeated Trap Title #Shorts"])
            self.assertIn("Repeated Trap Title #Shorts", engine.get_growth_prompt_context("shorts"))
            self.assertIn("Use bold 2-word thumbnail accents", engine.get_growth_prompt_context("long"))

    def test_social_growth_engine_summarizes_ig_and_local_history(self):
        from growth.social_analytics import SocialGrowthEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            engine = SocialGrowthEngine(api_key="dummy-key")
            engine.memory_file = tmp / "social_growth.json"

            ig_data = {
                "account": {"username": "royal_chamunda_auto", "followers": 575, "media_count": 110},
                "posts": [
                    {
                        "id": "r1",
                        "product_type": "clips",
                        "media_type": 2,
                        "likes": 150,
                        "comments": 8,
                        "views": 2400,
                        "caption_snippet": "Royal Enfield Classic 350 service in Kalol",
                        "hashtags": ["#royalenfield", "#kalol"],
                        "taken_at": "2026-11-20T10:00:00Z",
                    },
                    {
                        "id": "p1",
                        "product_type": "feed",
                        "media_type": 1,
                        "likes": 3,
                        "comments": 0,
                        "views": 0,
                        "caption_snippet": "Poster",
                        "hashtags": ["#royalenfield"],
                        "taken_at": "2026-11-21T10:00:00Z",
                    },
                ],
            }
            local = {
                "delivery": {"instagram": {"published": 4, "failed": 0}},
                "recent_campaigns": [{"date": "2026-11-26", "name": "Daily RE Special"}],
            }
            summary = engine._summarize_social(ig_data, None, local)
            self.assertEqual(summary["instagram_stats"]["recent_reels_avg_views"], 2400.0)
            self.assertEqual(summary["instagram_stats"]["recent_reels_avg_likes"], 150.0)
            self.assertEqual(summary["instagram_stats"]["recent_feed_avg_likes"], 3.0)
            self.assertIn("#royalenfield", summary["top_hashtags"])

            fake_res = SimpleNamespace(
                text=json.dumps({
                    "winning_content_angles": ["RE service thump"],
                    "winning_hook_formulas": ["Open with exhaust note"],
                    "top_hashtags": ["#RoyalEnfield", "#ChamundaAutomobile"],
                    "caption_rules": ["Hook on line 1"],
                    "visual_and_pacing_rules": ["Cut every 4s"],
                    "avoid_patterns": ["Static poster videos"],
                    "recommended_daily_angles": ["Monsoon Chain Care"],
                })
            )
            with patch.object(engine, "_fetch_instagram_metrics", return_value=ig_data), \
                 patch.object(engine, "_fetch_facebook_metrics", return_value={}), \
                 patch.object(engine, "_collect_local_social_telemetry", return_value=local), \
                 patch("growth.social_analytics.call_gemini_resilient", return_value=(fake_res, "gemini-3-flash-preview")):
                mem = engine.evolve_social_strategy(force=True)
                self.assertEqual(mem["winning_content_angles"], ["RE service thump"])
                self.assertTrue(engine.memory_file.exists())
                ctx = engine.get_social_prompt_context()
                self.assertIn("Reels Avg=2400.0 views", ctx)
                self.assertIn("RE service thump", ctx)

    def test_script_generator_duplicate_filter_and_rotating_fallback(self):
        from generator.script_generator import ScriptGenerator, is_repetitive_title

        self.assertTrue(is_repetitive_title(
            "Stop Letting Small Things Break You #Shorts",
            ["Stop Letting Small Things Break You"],
        ))
        self.assertFalse(is_repetitive_title(
            "Why 5 Minutes Of Boredom Fixes Broken Focus #Shorts",
            ["Stop Letting Small Things Break You #Shorts"],
        ))

        with patch("generator.script_generator.get_topic_history", return_value=[
            "Stop Letting Small Things Break You #Shorts",
            "The 3-Second Stoic Trick That Disarms Any Insult #Shorts",
        ]):
            sg = ScriptGenerator(api_key="dummy-key")
            with patch.object(sg.growth_engine, "get_saturated_titles", return_value=[
                "Why 90% Wake Up Exhausted After 8 Hours #Shorts",
            ]):
                pkg = sg._create_fallback_trilingual_package("stoic calm anger")
                self.assertNotIn(
                    pkg.english.title,
                    {
                        "Stop Letting Small Things Break You #Shorts",
                        "The 3-Second Stoic Trick That Disarms Any Insult #Shorts",
                        "Why 90% Wake Up Exhausted After 8 Hours #Shorts",
                    },
                )
                self.assertEqual(len(pkg.english.scenes), 5)
                self.assertTrue(all(s.estimated_duration_sec <= 4.5 for s in pkg.english.scenes))

    def test_duplicate_guard_adaptive_caption_and_reel_api(self):
        import upload_to_youtube as uyt
        from syndication.festival_creator import ChamundaFestivalCreator
        from syndication.festival_agent import FestivalSocialAgent
        from syndication.festival_detector import FestivalInfo
        from syndication.api_uploader import DirectSocialApiUploader

        cache = {
            "uploaded_files": {
                "h1": {"title": "Already Live #Shorts", "status": "ok"},
                "h2": {"title": "Ignored Skipped #Shorts", "status": "skipped_duplicate"},
            }
        }
        with patch("growth.growth_engine.GrowthEngine.get_saturated_titles", return_value=["Saturated Trap #Shorts"]):
            blocked = uyt._get_blocked_duplicate_titles(cache)
            self.assertIn(uyt._normalize_title_key("Already Live #Shorts"), blocked)
            self.assertIn(uyt._normalize_title_key("Saturated Trap #Shorts"), blocked)
            self.assertNotIn(uyt._normalize_title_key("Ignored Skipped #Shorts"), blocked)

        fest = FestivalInfo(
            is_festival=True,
            festival_name="Chamunda Special",
            date_str="2026-11-27",
            significance="RE care",
            motorcycle_theme="Classic 350",
            greeting_headline="Classic 350 Care",
            blessing_message_hi="हाय",
            blessing_message_gu="નમસ્તે",
            blessing_message_en="Ride proud!",
        )
        with patch("growth.social_analytics.SocialGrowthEngine.load_social_memory", return_value={
            "top_hashtags": ["#BulletKalol", "#RoyalEnfieldGujarat"],
            "recommended_daily_angles": ["Clutch Plate Life Check"],
        }):
            with patch("syndication.festival_creator.call_gemini_resilient", return_value=(
                "Save this Royal Enfield check before your next highway ride!",
                "gemini-3-flash-preview",
            )):
                creator = ChamundaFestivalCreator(api_key="dummy-key")
                cap = creator.generate_caption(fest, lang="en")
                self.assertIn("#BulletKalol", cap)
                self.assertIn("8490001582", cap)

            agent = FestivalSocialAgent(api_key="dummy-key")
            daily_info = agent._get_daily_re_showcase_info(datetime.date(2026, 11, 27))
            self.assertIn("Clutch Plate Life Check", daily_info.significance)

        uploader = DirectSocialApiUploader()
        mock_cl = MagicMock()
        mock_cl.clip_upload.return_value = SimpleNamespace(pk="999", code="REEL123")
        with patch.object(uploader, "get_instagram_client", return_value=mock_cl):
            res = uploader.post_instagram_reel_direct(Path("/tmp/fake_reel.mp4"), "Test Reel")
            self.assertEqual(res["status"], "PUBLISHED")
            self.assertEqual(res["url"], "https://www.instagram.com/reel/REEL123/")


if __name__ == "__main__":
    unittest.main()
