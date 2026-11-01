"""
Test suite for Resilient Content Storage on Failure & Startup Recovery
Verifies:
1. YouTube Agent: Failed uploads are queued in output/pending_uploads with unique filenames per video.
2. YouTube Agent: Pending videos are swept and uploaded when the agent starts again.
3. Social Media Agent: Failed uploads are queued in Story/pending with metadata and captions.
4. Social Media Agent: Stored items are not purged after 24h and are swept when agent starts again.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
from growth.self_healer import SelfHealer
from syndication.social_queue import SocialQueueManager
import upload_to_youtube


class TestContentStorageAndRecovery(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_recovery_"))
        self.orig_output_dir = config.OUTPUT_DIR
        self.orig_base_dir = config.BASE_DIR

        # Patch paths to temporary test directory
        config.OUTPUT_DIR = self.test_dir / "output"
        config.BASE_DIR = self.test_dir
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        config.OUTPUT_DIR = self.orig_output_dir
        config.BASE_DIR = self.orig_base_dir
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_youtube_queue_for_later_unique_filenames(self):
        """Verifies each video in a trilingual run receives its own unique queue JSON file without collision."""
        healer = SelfHealer()
        run_dir = config.OUTPUT_DIR / "run_trilingual_20261101_120000"
        run_dir.mkdir(parents=True, exist_ok=True)

        vid_en = run_dir / "final_short_en.mp4"
        vid_hi = run_dir / "final_short_hi.mp4"
        vid_gu = run_dir / "final_short_gu.mp4"
        vid_std = run_dir / "final_video.mp4"

        for v in [vid_en, vid_hi, vid_gu, vid_std]:
            v.write_bytes(b"dummy_video_bytes_1234567890" * 500)

        # Queue each video
        q_en = healer.queue_for_later(vid_en, {"title": "English Short", "language": "en"})
        q_hi = healer.queue_for_later(vid_hi, {"title": "Hindi Short", "language": "hi"})
        q_gu = healer.queue_for_later(vid_gu, {"title": "Gujarati Short", "language": "gu"})
        q_std = healer.queue_for_later(vid_std, {"title": "Standard Video", "is_standard": True})

        # All 4 files must exist and be distinct
        queue_files = list((config.OUTPUT_DIR / "pending_uploads").glob("*.json"))
        self.assertEqual(len(queue_files), 4)

        paths = {q.name for q in [q_en, q_hi, q_gu, q_std]}
        self.assertEqual(len(paths), 4)
        self.assertTrue(any("final_short_en" in p for p in paths))
        self.assertTrue(any("final_short_hi" in p for p in paths))
        self.assertTrue(any("final_short_gu" in p for p in paths))
        self.assertTrue(any("final_video" in p for p in paths))

    def test_youtube_pending_videos_gathered_and_uploaded_on_startup(self):
        """Verifies get_pending_videos reads all stored queue items and sweep_and_upload_all_leftovers processes them."""
        healer = SelfHealer()
        run_dir = config.OUTPUT_DIR / "run_20261101_130000"
        run_dir.mkdir(parents=True, exist_ok=True)

        vid_file = run_dir / "final_video.mp4"
        vid_file.write_bytes(b"fake_video_content" * 1000)
        thumb_file = run_dir / "thumbnail.jpg"
        thumb_file.write_bytes(b"fake_thumbnail_content" * 100)

        healer.queue_for_later(
            vid_file,
            {"title": "Masterclass on Willpower", "description": "Full lecture", "tags": ["mindset"]},
            error_reason="Simulated network disconnect",
        )

        # Ensure get_pending_videos detects it
        with patch("upload_to_youtube.CACHE_FILE", config.OUTPUT_DIR / "cache.json"):
            pending = upload_to_youtube.get_pending_videos()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["script"]["title"], "Masterclass on Willpower")
            self.assertTrue(pending[0]["is_standard"])

            # Test upload sweep
            mock_uploader = MagicMock()
            mock_uploader.auth.is_token_valid.return_value = True
            mock_uploader.service.channels().list().execute.return_value = {
                "items": [{"id": "UC_TEST", "snippet": {"title": "Test Channel"}}]
            }
            mock_uploader.upload_video.return_value = {
                "status": "UPLOADED",
                "video_id": "test_vid_123",
                "video_url": "https://youtu.be/test_vid_123",
            }

            with patch("upload_to_youtube.YouTubeUploader", return_value=mock_uploader):
                results = upload_to_youtube.upload_all_pending()
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["video_id"], "test_vid_123")

                # Verify queue file was unlinked
                remaining_queue = list((config.OUTPUT_DIR / "pending_uploads").glob("*.json"))
                self.assertEqual(len(remaining_queue), 0)

    def test_social_queue_preserves_content_without_24h_stale_drop(self):
        """Verifies stored social media items are retained and not marked ARCHIVED_STALE after 24h."""
        qm = SocialQueueManager()
        story_media = qm.story_dir / "test_poster.jpg"
        story_media.write_bytes(b"fake_image_bytes" * 500)

        # Enqueue item
        item = qm.enqueue_failed(
            media_path=story_media,
            caption="Royal Enfield Chamunda Special Care",
            target_platforms=["instagram", "facebook", "whatsapp"],
            published_platforms=[],
            failed_platforms={"whatsapp": "Browser disconnected"},
        )

        # Manually alter created_at to 3 days ago (72 hours)
        items = qm.load_queue()
        items[0]["created_at"] = "2026-10-25 10:00:00"
        qm.save_queue(items)

        # Call get_pending_items()
        pending = qm.get_pending_items()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["status"], "PENDING")
        self.assertEqual(pending[0]["pending_platforms"], ["instagram", "facebook", "whatsapp"])

    def test_social_sweep_retries_and_completes_stored_content(self):
        """Verifies sweep_and_publish_all_leftover_stories retries pending platforms and moves media on completion."""
        qm = SocialQueueManager()
        media_file = qm.story_dir / "bullet_special.jpg"
        media_file.write_bytes(b"image_content_123" * 200)

        # Enqueue item with instagram already published, facebook and whatsapp pending
        qm.enqueue_failed(
            media_path=media_file,
            caption="Bullet 350 Servicing at Chamunda Automobile",
            target_platforms=["instagram", "facebook", "whatsapp"],
            published_platforms=["instagram"],
            failed_platforms={"facebook": "Timeout", "whatsapp": "Offline"},
        )

        mock_api = MagicMock()
        mock_api.post_facebook_direct.return_value = {"status": "PUBLISHED"}
        mock_api.post_whatsapp_direct.return_value = {"status": "PUBLISHED"}

        with patch("syndication.social_queue.BrowserUploader") as mock_browser, \
             patch("syndication.social_queue.DirectSocialApiUploader", return_value=mock_api):
            qm.api_uploader = mock_api
            res = qm.sweep_and_publish_all_leftover_stories(max_items=5)

            self.assertEqual(res["completed_count"], 1)
            self.assertEqual(res["remaining_pending"], 0)

            # Queue status should now be completed
            items = qm.load_queue()
            self.assertEqual(items[0]["status"], "COMPLETED")
            self.assertEqual(items[0]["pending_platforms"], [])
            self.assertIn("facebook", items[0]["published_platforms"])
            self.assertIn("whatsapp", items[0]["published_platforms"])


if __name__ == "__main__":
    unittest.main()
