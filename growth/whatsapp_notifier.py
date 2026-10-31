#!/usr/bin/env python3
"""
WhatsApp Failure Alert Engine
=============================
Provides real-time WhatsApp notifications to the user whenever the
YouTube Agent or Social Media Agent is unable to perform its task:
  1. Meta WhatsApp Cloud API (Graph API - fast, reliable, headless/cloud ready)
  2. CallMeBot WhatsApp Webhook (Free, zero-dependency cloud webhook)
  3. WhatsApp Web Local Automation (Selenium Firefox with persistent paired profile)

Includes incident deduplication (cooldown), formatted diagnostic templates,
and comprehensive audit logging to output/whatsapp_alerts.log.
"""

import argparse
import datetime
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import config

logger = logging.getLogger("WhatsAppNotifier")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class WhatsAppNotifier:
    """Dispatches actionable failure alerts to the user via WhatsApp."""

    def __init__(self):
        self.log_file = config.OUTPUT_DIR / "whatsapp_alerts.log"
        self._cooldown_cache: Dict[str, float] = {}
        self.cooldown_seconds = 900  # 15 minutes suppression for identical errors

    def clean_phone_number(self, phone: str) -> str:
        """Removes symbols (+, -, spaces, parentheses) from phone number."""
        clean = re.sub(r"[^\d]", "", phone or "")
        return clean

    def _format_alert_message(
        self,
        agent_name: str,
        failure_step: str,
        error_message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generates high-visibility, formatted WhatsApp markdown alert."""
        ist_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
        time_str = ist_now.strftime("%Y-%m-%d %H:%M:%S IST")

        # Clean / truncate error message
        err_clean = str(error_message).strip()
        if len(err_clean) > 300:
            err_clean = err_clean[:297] + "..."

        recommendation = "Check logs and system status."
        err_lower = err_clean.lower()
        if "quota" in err_lower or "quotaexceeded" in err_lower:
            recommendation = "Daily YouTube/Gemini API quota exhausted. Resumes tomorrow automatically."
        elif "token" in err_lower or "unauthorized" in err_lower or "auth" in err_lower:
            recommendation = "OAuth token or session expired. Re-authenticate credentials on your host machine."
        elif "network" in err_lower or "timeout" in err_lower or "connection" in err_lower:
            recommendation = "Network connectivity issue detected. Check internet connection."
        elif "ffmpeg" in err_lower or "video" in err_lower:
            recommendation = "Video rendering error. Verify input media and storage space."

        lines = [
            "🚨 *AGENT FAILURE ALERT* 🚨",
            "",
            f"🤖 *Agent*: {agent_name}",
            "❌ *Status*: *Unable to perform task*",
            f"🕒 *Time*: {time_str}",
            f"📋 *Failing Step*: {failure_step}",
            f"⚠️ *Error*: {err_clean}",
            f"💡 *Suggestion*: {recommendation}",
        ]

        if details:
            extra_lines = []
            for k, v in list(details.items())[:4]:
                extra_lines.append(f"  • {k}: {str(v)[:80]}")
            if extra_lines:
                lines.append("\n*Diagnostic Context*:\n" + "\n".join(extra_lines))

        lines.append("\n_YouTube & Social Media AI Autonomous Monitor_")
        return "\n".join(lines)

    def _is_in_cooldown(self, dedupe_key: str) -> bool:
        """Checks if identical alert was sent recently to prevent spam."""
        now = time.time()
        last_sent = self._cooldown_cache.get(dedupe_key, 0)
        if now - last_sent < self.cooldown_seconds:
            return True
        self._cooldown_cache[dedupe_key] = now
        return False

    def _log_alert(self, status: str, provider: str, agent_name: str, message: str, reason: str = ""):
        """Appends audit log to output/whatsapp_alerts.log."""
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp}] [{status}] Provider={provider} Agent='{agent_name}'"
            if reason:
                log_line += f" Reason='{reason}'"
            log_line += f" | {message.replace(chr(10), ' ')}\n"
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # PROVIDER 1: Meta WhatsApp Cloud API (Graph API)
    # --------------------------------------------------------------------------
    def _send_via_cloud_api(self, target_phone: str, message: str) -> Tuple[bool, str]:
        token = getattr(config, "WHATSAPP_TOKEN", "") or os.getenv("WHATSAPP_TOKEN", "")
        phone_id = getattr(config, "WHATSAPP_PHONE_NUMBER_ID", "") or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

        if not token or not phone_id or not target_phone:
            return False, "Cloud API credentials (token/phone_id) not configured"

        url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": target_phone,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=15)
            if res.status_code in (200, 201):
                return True, "Delivered via Meta Cloud API"
            return False, f"Cloud API HTTP {res.status_code}: {res.text[:200]}"
        except Exception as e:
            return False, f"Cloud API exception: {e}"

    # --------------------------------------------------------------------------
    # PROVIDER 2: CallMeBot Free WhatsApp Alert Webhook
    # --------------------------------------------------------------------------
    def _send_via_callmebot(self, message: str) -> Tuple[bool, str]:
        phone = getattr(config, "CALLMEBOT_PHONE", "") or os.getenv("CALLMEBOT_PHONE", "")
        apikey = getattr(config, "CALLMEBOT_APIKEY", "") or os.getenv("CALLMEBOT_APIKEY", "")

        if not phone or not apikey:
            return False, "CallMeBot phone/apikey not configured"

        encoded_text = urllib.parse.quote(message)
        url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_text}&apikey={apikey}"

        try:
            res = requests.get(url, timeout=15)
            if res.status_code == 200 and "success" in res.text.lower():
                return True, "Delivered via CallMeBot"
            return False, f"CallMeBot response: {res.text[:200]}"
        except Exception as e:
            return False, f"CallMeBot exception: {e}"

    # --------------------------------------------------------------------------
    # PROVIDER 3: WhatsApp Web Automation (Local Firefox Profile)
    # --------------------------------------------------------------------------
    def _send_via_whatsapp_web(self, target_phone: str, message: str) -> Tuple[bool, str]:
        clean_phone = self.clean_phone_number(target_phone)
        if not clean_phone:
            return False, "No target phone number provided for WhatsApp Web"

        try:
            from syndication.browser_uploader import BrowserUploader
            bu = BrowserUploader()
            if not bu.is_whatsapp_session_valid():
                return False, "WhatsApp Web profile in social_firefox is not authenticated"

            # Check DISPLAY environment
            display = os.environ.get("DISPLAY", ":0")
            os.environ["DISPLAY"] = display

            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys

            driver = bu.get_driver()
            encoded_text = urllib.parse.quote(message)
            target_url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={encoded_text}"

            logger.info(f"🌐 [WhatsApp Web Alert] Opening direct chat to +{clean_phone}...")
            driver.get(target_url)

            # Wait for WhatsApp Web UI to render chat
            bu.dismiss_overlays(driver)

            # Look for send button or active editable message box
            send_clicked = False
            for _ in range(30):  # Wait up to 60 seconds for chat to load
                time.sleep(2)
                bu.dismiss_overlays(driver)

                # Check for invalid phone popup
                invalid_popups = driver.find_elements(
                    By.XPATH,
                    "//*[contains(text(), 'Phone number shared via url is invalid')] | "
                    "//*[contains(text(), 'URL is invalid')]"
                )
                if invalid_popups:
                    return False, f"WhatsApp reported phone number +{clean_phone} is invalid"

                # Check for send button
                send_buttons = driver.find_elements(
                    By.XPATH,
                    "//button[@data-testid='compose-btn-send'] | "
                    "//button[@aria-label='Send'] | "
                    "//span[@data-icon='send']/parent::button | "
                    "//*[@data-icon='send']"
                )
                if send_buttons:
                    try:
                        send_buttons[0].click()
                        send_clicked = True
                        break
                    except Exception:
                        pass

                # Fallback: check if compose box is focused and press ENTER
                compose_boxes = driver.find_elements(
                    By.XPATH,
                    "//footer//div[@contenteditable='true'] | "
                    "//div[@aria-placeholder='Type a message']"
                )
                if compose_boxes:
                    try:
                        compose_boxes[0].send_keys(Keys.ENTER)
                        send_clicked = True
                        break
                    except Exception:
                        pass

            if send_clicked:
                time.sleep(4)  # Allow socket buffers to transmit message
                return True, f"Delivered via WhatsApp Web to +{clean_phone}"
            else:
                # Save debug screenshot for audit
                try:
                    debug_path = config.OUTPUT_DIR / "debug_wa_alert_timeout.png"
                    driver.save_screenshot(str(debug_path))
                except Exception:
                    pass
                return False, "Timed out waiting for WhatsApp Web Send button"

        except Exception as e:
            return False, f"WhatsApp Web automation error: {e}"

    # --------------------------------------------------------------------------
    # Main Public Dispatch Method
    # --------------------------------------------------------------------------
    def send_failure_alert(
        self,
        agent_name: str,
        failure_step: str,
        error_message: str,
        details: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> bool:
        """
        Main entrypoint: Formats failure details and dispatches alert via the best available WhatsApp method.
        """
        if not getattr(config, "ENABLE_WHATSAPP_ALERTS", True):
            logger.info("ℹ️ [WhatsApp Alert] WhatsApp alerts disabled in config (ENABLE_WHATSAPP_ALERTS=false).")
            return False

        dedupe_key = f"{agent_name}:{failure_step}:{str(error_message)[:60]}"
        if not force and self._is_in_cooldown(dedupe_key):
            logger.info(f"⏳ [WhatsApp Alert] Alert in 15m cooldown for '{dedupe_key}'. Suppressing duplicate.")
            return False

        message = self._format_alert_message(agent_name, failure_step, error_message, details)
        target_phone = getattr(config, "WHATSAPP_TARGET_PHONE", "") or os.getenv("WHATSAPP_TARGET_PHONE", "")
        clean_target = self.clean_phone_number(target_phone)

        logger.info(f"🚨 [WhatsApp Alert] Initiating WhatsApp failure alert for '{agent_name}' ({failure_step})...")

        # 1. Try Meta WhatsApp Cloud API (Graph API)
        if clean_target:
            success, reason = self._send_via_cloud_api(clean_target, message)
            if success:
                logger.info(f"✅ [WhatsApp Alert] {reason}")
                self._log_alert("DELIVERED", "MetaCloudAPI", agent_name, message)
                return True
            else:
                logger.debug(f"[WhatsApp Alert] Cloud API attempt: {reason}")

        # 2. Try CallMeBot Webhook
        success, reason = self._send_via_callmebot(message)
        if success:
            logger.info(f"✅ [WhatsApp Alert] {reason}")
            self._log_alert("DELIVERED", "CallMeBot", agent_name, message)
            return True
        else:
            logger.debug(f"[WhatsApp Alert] CallMeBot attempt: {reason}")

        # 3. Try WhatsApp Web Automation (Local Browser)
        if clean_target:
            success, reason = self._send_via_whatsapp_web(clean_target, message)
            if success:
                logger.info(f"✅ [WhatsApp Alert] {reason}")
                self._log_alert("DELIVERED", "WhatsAppWeb", agent_name, message)
                return True
            else:
                logger.warning(f"⚠️ [WhatsApp Alert] WhatsApp Web attempt failed: {reason}")
                self._log_alert("FAILED", "WhatsAppWeb", agent_name, message, reason=reason)
        else:
            reason = "No WHATSAPP_TARGET_PHONE configured in .env or config"
            logger.warning(f"⚠️ [WhatsApp Alert] {reason}. Cannot route to phone.")
            self._log_alert("FAILED", "ConfigMissing", agent_name, message, reason=reason)

        return False


# Global singleton instance
whatsapp_notifier = WhatsAppNotifier()


def main():
    parser = argparse.ArgumentParser(description="WhatsApp Failure Alert CLI Tester")
    parser.add_argument("--test", action="store_true", help="Send a test failure alert to verify WhatsApp integration")
    parser.add_argument("--phone", type=str, default="", help="Override target phone number for test")
    parser.add_argument("--agent", type=str, default="YouTube Agent", help="Agent name for test")
    parser.add_argument("--step", type=str, default="Test Video Assembly", help="Step name for test")
    parser.add_argument("--error", type=str, default="Simulated failure for verification", help="Error message for test")
    args = parser.parse_args()

    if args.phone:
        config.WHATSAPP_TARGET_PHONE = args.phone

    print("=" * 65)
    print("📱 WHATSAPP FAILURE ALERT DIAGNOSTICS & TEST DISPATCHER")
    print("=" * 65)
    phone = getattr(config, "WHATSAPP_TARGET_PHONE", "")
    print(f"📞 Configured Target Phone: {phone or '(Not set - set WHATSAPP_TARGET_PHONE in .env)'}")
    print(f"🔔 WhatsApp Alerts Enabled: {getattr(config, 'ENABLE_WHATSAPP_ALERTS', True)}")

    from syndication.browser_uploader import BrowserUploader
    bu = BrowserUploader()
    valid_session = bu.is_whatsapp_session_valid()
    print(f"🌐 Local WhatsApp Web Paired Session: {'VALID ✅' if valid_session else 'NOT PAIRED ❌'}")

    has_cloud = bool(getattr(config, "WHATSAPP_TOKEN", "") and getattr(config, "WHATSAPP_PHONE_NUMBER_ID", ""))
    print(f"☁️  Meta WhatsApp Cloud API: {'CONFIGURED ✅' if has_cloud else 'NOT CONFIGURED (Optional)'}")

    has_callmebot = bool(getattr(config, "CALLMEBOT_PHONE", "") and getattr(config, "CALLMEBOT_APIKEY", ""))
    print(f"🤖 CallMeBot Webhook: {'CONFIGURED ✅' if has_callmebot else 'NOT CONFIGURED (Optional)'}")
    print("=" * 65)

    if args.test:
        print("\n🚀 Sending test failure alert now...")
        res = whatsapp_notifier.send_failure_alert(
            agent_name=args.agent,
            failure_step=args.step,
            error_message=args.error,
            details={"DiagnosticTest": "True", "Host": os.uname().nodename},
            force=True,
        )
        if res:
            print("🎉 SUCCESS: Test WhatsApp alert delivered!")
            sys.exit(0)
        else:
            print("⚠️ Alert could not be delivered. Check output/whatsapp_alerts.log for details.")
            sys.exit(1)


if __name__ == "__main__":
    main()
