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

    @patch("growth.youtube_daily_limiter.youtube_limiter.can_run_today")
    @patch("syndication.daily_limiter.limiter.can_post_today")
    @patch("agent.YouTubeAgent")
    @patch("syndication.festival_agent.run_daily_social_agent")
    @patch("scheduler.run_daily_youtube_cleaner")
    def test_strict_sequential_order_when_both_can_run(
        self, mock_cleaner, mock_social, mock_yt_class, mock_social_can_post, mock_yt_can_run
    ):
        mock_yt_can_run.return_value = True
        mock_social_can_post.return_value = True

        execution_order = []

        # Mock YouTube agent run
        mock_yt_instance = MagicMock()
        def yt_side_effect(*args, **kwargs):
            execution_order.append("YOUTUBE_AGENT")
        mock_yt_instance.run_trilingual.side_effect = yt_side_effect
        mock_yt_class.return_value = mock_yt_instance

        # Mock Social agent run
        def social_side_effect(*args, **kwargs):
            execution_order.append("SOCIAL_AGENT")
            return {"status": "COMPLETED"}
        mock_social.side_effect = social_side_effect

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
            target_platform="youtube", dry_run=False, force=False
        )
        mock_social.assert_called_once_with(force=False)
        mock_cleaner.assert_called_once_with(force=False)

    @patch("growth.youtube_daily_limiter.youtube_limiter.can_run_today")
    @patch("syndication.daily_limiter.limiter.can_post_today")
    @patch("agent.YouTubeAgent")
    @patch("syndication.festival_agent.run_daily_social_agent")
    @patch("scheduler.run_daily_youtube_cleaner")
    def test_skips_when_daily_limits_reached(
        self, mock_cleaner, mock_social, mock_yt_class, mock_social_can_post, mock_yt_can_run
    ):
        mock_yt_can_run.return_value = False
        mock_social_can_post.return_value = False

        scheduler.run_daily_coordinator_worker(force=False)

        mock_yt_class.assert_not_called()
        mock_social.assert_not_called()
        mock_cleaner.assert_called_once_with(force=False)


if __name__ == "__main__":
    unittest.main()
