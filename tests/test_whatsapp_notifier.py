#!/usr/bin/env python3
"""
Unit tests for WhatsApp Failure Alert Engine & Notification Hub
==============================================================
Tests:
1. Message formatting & diagnostic recommendation rules
2. Phone number sanitization
3. Incident deduplication / cooldown suppression
4. Multi-tier provider dispatch & fallback logic
5. DesktopNotifier integration
"""

import unittest
from unittest.mock import MagicMock, patch

import config
from growth.whatsapp_notifier import WhatsAppNotifier, whatsapp_notifier
from growth.notifier import DesktopNotifier


class TestWhatsAppNotifier(unittest.TestCase):

    def setUp(self):
        self.notifier = WhatsAppNotifier()
        self.notifier._cooldown_cache.clear()

    def test_clean_phone_number(self):
        self.assertEqual(self.notifier.clean_phone_number("+91 98765-43210"), "919876543210")
        self.assertEqual(self.notifier.clean_phone_number("(+1) 555-0199"), "15550199")
        self.assertEqual(self.notifier.clean_phone_number("919876543210"), "919876543210")
        self.assertEqual(self.notifier.clean_phone_number(""), "")

    def test_format_alert_message_recommendations(self):
        # Quota recommendation test
        msg_quota = self.notifier._format_alert_message(
            agent_name="YouTube Agent",
            failure_step="Upload",
            error_message="quotaExceeded: daily quota limit reached",
            details={"Run": "test_run_123"},
        )
        self.assertIn("AGENT FAILURE ALERT", msg_quota)
        self.assertIn("YouTube Agent", msg_quota)
        self.assertIn("quota exhausted", msg_quota.lower())
        self.assertIn("test_run_123", msg_quota)

        # Auth token recommendation test
        msg_auth = self.notifier._format_alert_message(
            agent_name="Social Media Agent",
            failure_step="Instagram Publishing",
            error_message="OAuth token unauthorized or expired",
        )
        self.assertIn("Social Media Agent", msg_auth)
        self.assertIn("re-authenticate", msg_auth.lower())

    def test_cooldown_deduplication(self):
        dedupe_key = "TestAgent:Step1:GenericError"
        # First call should NOT be in cooldown
        self.assertFalse(self.notifier._is_in_cooldown(dedupe_key))
        # Immediate second call SHOULD be in cooldown
        self.assertTrue(self.notifier._is_in_cooldown(dedupe_key))

    @patch("requests.post")
    def test_send_via_cloud_api_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        with patch.object(config, "WHATSAPP_TOKEN", "fake_token"):
            with patch.object(config, "WHATSAPP_PHONE_NUMBER_ID", "12345678"):
                success, reason = self.notifier._send_via_cloud_api("919876543210", "Hello alert")
                self.assertTrue(success)
                self.assertIn("Meta Cloud API", reason)
                mock_post.assert_called_once()

    @patch("requests.get")
    def test_send_via_callmebot_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Success: Message queued"
        mock_get.return_value = mock_response

        with patch.object(config, "CALLMEBOT_PHONE", "919876543210"):
            with patch.object(config, "CALLMEBOT_APIKEY", "secret_key"):
                success, reason = self.notifier._send_via_callmebot("Hello alert")
                self.assertTrue(success)
                self.assertIn("CallMeBot", reason)
                mock_get.assert_called_once()

    @patch.object(WhatsAppNotifier, "_send_via_cloud_api")
    def test_send_failure_alert_triggers_cloud_api(self, mock_cloud):
        mock_cloud.return_value = (True, "Delivered via Meta Cloud API")
        with patch.object(config, "ENABLE_WHATSAPP_ALERTS", True):
            with patch.object(config, "WHATSAPP_TARGET_PHONE", "919876543210"):
                res = self.notifier.send_failure_alert(
                    agent_name="YouTube Agent",
                    failure_step="Test Step",
                    error_message="Test Error",
                    force=True,
                )
                self.assertTrue(res)
                mock_cloud.assert_called_once()

    @patch("growth.whatsapp_notifier.whatsapp_notifier.send_failure_alert")
    @patch("subprocess.run")
    def test_desktop_notifier_notify_agent_failure(self, mock_subproc, mock_wa_alert):
        dn = DesktopNotifier()
        dn.notify_agent_failure(
            agent_name="YouTube Agent",
            failure_step="Video Rendering",
            error_message="ffmpeg memory error",
            details={"resolution": "1080x1920"},
        )
        # Desktop notification attempted
        mock_subproc.assert_called()
        # WhatsApp notification attempted
        mock_wa_alert.assert_called_once_with(
            agent_name="YouTube Agent",
            failure_step="Video Rendering",
            error_message="ffmpeg memory error",
            details={"resolution": "1080x1920"},
            force=False,
        )


if __name__ == "__main__":
    unittest.main()
