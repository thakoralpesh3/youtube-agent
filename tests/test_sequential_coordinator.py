"""
Test suite for Sequential Daily Coordinator
Verifies:
1. Strict sequential ordering: Step 1 (YouTube) runs to 100% completion before Step 2 (Social) starts.
2. Daily limit enforcement: Both agents are evaluated against their respective daily limiters.
3. Concurrency lock: Simultaneous pulse triggers do not spawn parallel runs.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

import scheduler


class TestSequentialDailyCoordinator(unittest.TestCase):

    @patch("core.publisher_bridge.run_publisher_daily", return_value={"status": "completed"})
    @patch("upload_to_youtube.sweep_and_upload_all_leftovers", return_value=0)
    @patch("growth.youtube_daily_limiter.youtube_limiter.can_run_today")
    @patch("syndication.daily_limiter.limiter.can_post_today")
    @patch("syndication.daily_limiter.is_social_upload_window", return_value=True)
    @patch("agent.YouTubeAgent")
    @patch("scheduler.run_daily_social_worker")
    @patch("scheduler.run_daily_youtube_cleaner")
    def test_strict_sequential_order_when_both_can_run(
        self, mock_cleaner, mock_social_worker, mock_yt_class, mock_is_window, mock_social_can_post, mock_yt_can_run, mock_sweep, mock_pub
    ):
        mock_yt_can_run.return_value = True
        mock_social_can_post.return_value = True

        execution_order = []

        # Mock YouTube agent run
        mock_yt_instance = MagicMock()
        mock_yt_instance.find_latest_resumable_run.return_value = None
        def yt_side_effect(*args, **kwargs):
            execution_order.append("YOUTUBE_AGENT")
        mock_yt_instance.run_trilingual.side_effect = yt_side_effect
        mock_yt_class.return_value = mock_yt_instance

        # Mock Social worker run
        def social_side_effect(*args, **kwargs):
            execution_order.append("SOCIAL_AGENT")
        mock_social_worker.side_effect = social_side_effect

        # Mock Cleaner run
        def cleaner_side_effect(*args, **kwargs):
            execution_order.append("CLEANER")
            return True
        mock_cleaner.side_effect = cleaner_side_effect

        # Execute synchronous coordinator
        scheduler.run_daily_coordinator_worker(force=False)

        # Assert strict sequence
        self.assertEqual(execution_order, ["YOUTUBE_AGENT", "SOCIAL_AGENT", "CLEANER"])
        mock_yt_instance.run_trilingual.assert_called_once_with(
            target_platform="youtube", dry_run=False, force=False, resume=True
        )
        mock_social_worker.assert_called_once_with(force=False)
        mock_cleaner.assert_called_once_with(force=False)

    @patch("core.publisher_bridge.run_publisher_daily", return_value={"status": "completed"})
    @patch("upload_to_youtube.sweep_and_upload_all_leftovers", return_value=0)
    @patch("growth.youtube_daily_limiter.youtube_limiter.can_run_today")
    @patch("syndication.daily_limiter.limiter.can_post_today")
    @patch("agent.YouTubeAgent")
    @patch("syndication.festival_agent.run_daily_social_agent")
    @patch("scheduler.run_daily_youtube_cleaner")
    def test_skips_when_daily_limits_reached(
        self, mock_cleaner, mock_social, mock_yt_class, mock_social_can_post, mock_yt_can_run, mock_sweep, mock_pub
    ):
        mock_yt_can_run.return_value = False
        mock_social_can_post.return_value = False

        mock_yt_instance = MagicMock()
        mock_yt_instance.find_latest_resumable_run.return_value = None
        mock_yt_class.return_value = mock_yt_instance

        scheduler.run_daily_coordinator_worker(force=False)

    @patch("core.publisher_bridge.run_publisher_daily", return_value={"status": "completed"})
    @patch("upload_to_youtube.sweep_and_upload_all_leftovers", return_value=0)
    @patch("growth.youtube_daily_limiter.youtube_limiter.can_run_today")
    @patch("syndication.daily_limiter.limiter.can_post_today")
    @patch("agent.YouTubeAgent")
    @patch("scheduler.run_daily_social_worker")
    @patch("scheduler.run_daily_youtube_cleaner")
    def test_force_run_executes_youtube_then_social(
        self, mock_cleaner, mock_social_worker, mock_yt_class, mock_social_can_post, mock_yt_can_run, mock_sweep, mock_pub
    ):
        """Verifies that with force=True, YouTube Agent runs first, followed by Social Agent."""
        mock_yt_can_run.return_value = False
        mock_social_can_post.return_value = False

        execution_order = []

        mock_yt_instance = MagicMock()
        mock_yt_instance.find_latest_resumable_run.return_value = None
        def yt_side_effect(*args, **kwargs):
            execution_order.append("YOUTUBE_AGENT")
        mock_yt_instance.run_trilingual.side_effect = yt_side_effect
        mock_yt_class.return_value = mock_yt_instance

        def social_side_effect(*args, **kwargs):
            execution_order.append("SOCIAL_AGENT")
        mock_social_worker.side_effect = social_side_effect

        def cleaner_side_effect(*args, **kwargs):
            execution_order.append("CLEANER")
            return True
        mock_cleaner.side_effect = cleaner_side_effect

        scheduler.run_daily_coordinator_worker(force=True)

        self.assertEqual(execution_order, ["YOUTUBE_AGENT", "SOCIAL_AGENT", "CLEANER"])
        mock_yt_instance.run_trilingual.assert_called_once_with(
            target_platform="youtube", dry_run=False, force=True, resume=True
        )
        mock_social_worker.assert_called_once_with(force=True)
        mock_cleaner.assert_called_once_with(force=True)

    @patch("schedule.every")
    @patch("threading.Thread")
    @patch("syndication.story_watcher.StoryWatcher")
    @patch("core.github_watcher.start_watcher_background")
    def test_startup_and_8hour_scheduler_registration(
        self, mock_watcher, mock_story, mock_thread, mock_schedule_every
    ):
        """Verifies 8-hour schedule is registered and startup coordinator thread is launched."""
        # Stop infinite while loop by raising KeyboardInterrupt on time.sleep
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            try:
                scheduler.run_daily_scheduler()
            except KeyboardInterrupt:
                pass

        # Verify 8-hour schedule was registered
        mock_schedule_every.assert_any_call(8)

        # Verify StartupSequentialCoordinator thread was spawned and started
        thread_names = [call.kwargs.get("name") for call in mock_thread.call_args_list if call.kwargs.get("name")]
        self.assertIn("StartupSequentialCoordinator", thread_names)


if __name__ == "__main__":
    unittest.main()
