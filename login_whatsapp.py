#!/usr/bin/env python3
"""
WhatsApp Web Interactive Login Helper for Social Agent
======================================================
This script opens WhatsApp Web in an interactive Firefox window using the
agent's dedicated persistent profile: assets/browser_profiles/social_firefox.

Once you scan the QR code (or link via phone number):
1. The session is permanently saved in the agent's profile.
2. The agent automatically detects the active login.
3. WhatsApp Status auto-uploading is immediately enabled!
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Ensure repo root is in python path
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from syndication.social_auth import SocialAuth

PROFILE_DIR = REPO_ROOT / "assets" / "browser_profiles" / "social_firefox"


def clean_locks():
    for lock_name in ["lock", ".parentlock", ".agent_browser.lock"]:
        lock_path = PROFILE_DIR / lock_name
        if lock_path.is_symlink() or lock_path.exists():
            try:
                lock_path.unlink()
            except Exception:
                pass


def is_logged_in(driver) -> bool:
    from selenium.webdriver.common.by import By
    # Check for Status button or chat list or main header
    selectors = [
        "//header//button[@aria-label='Status']",
        "//*[@data-icon='status-v3']",
        "//*[@aria-label='Status']",
        "//*[@data-testid='chat-list']",
        "//div[@role='navigation']",
        "//*[@aria-label='Chat list']",
    ]
    for sel in selectors:
        if driver.find_elements(By.XPATH, sel):
            return True
    return False


def main():
    print("=" * 65)
    print("📱 WHATSAPP WEB AUTHENTICATION WIZARD")
    print("=" * 65)
    print(f"📁 Profile: {PROFILE_DIR}")

    clean_locks()

    display = os.environ.get("DISPLAY", ":0")
    os.environ["DISPLAY"] = display

    print(f"🖥️  Using display: {display}")
    print("🚀 Launching Firefox with WhatsApp Web...")

    try:
        from selenium import webdriver
        from selenium.webdriver.firefox.options import Options
        from selenium.webdriver.firefox.service import Service

        gecko_path = REPO_ROOT / ".venv" / "bin" / "geckodriver"
        if not gecko_path.exists():
            gecko_path = Path("/usr/bin/geckodriver")

        options = Options()
        options.add_argument("-profile")
        options.add_argument(str(PROFILE_DIR))
        options.set_preference("dom.serviceWorkers.enabled", True)
        options.set_preference("dom.serviceWorkers.testing.enabled", True)
        options.set_preference("dom.timeout.enable_budget_timer_throttling", False)
        options.set_preference("network.websocket.timeout.open", 60)
        options.set_preference("general.useragent.override", "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0")

        service = Service(executable_path=str(gecko_path))
        driver = webdriver.Firefox(service=service, options=options)
        driver.set_window_size(1280, 850)

        print("\n🌐 Navigating to https://web.whatsapp.com...")
        driver.get("https://web.whatsapp.com")

        print("\n" + "*" * 65)
        print("👉 ACTION REQUIRED ON YOUR PHONE:")
        print("1. Open WhatsApp on your phone.")
        print("2. Tap Menu (three dots) or Settings -> 'Linked Devices'.")
        print("3. Tap 'Link a device' and scan the QR code on your laptop screen.")
        print("*" * 65 + "\n")

        print("⏳ Monitoring login status (press Ctrl+C if you want to cancel)...")
        logged_in = False
        for tick in range(120):  # Wait up to 4 minutes
            time.sleep(2)
            if is_logged_in(driver):
                logged_in = True
                break
            if tick > 0 and tick % 10 == 0:
                print(f"   Waiting for QR scan... ({tick * 2}s elapsed)")

        if logged_in:
            print("\n" + "=" * 65)
            print("🎉 SUCCESS! WhatsApp Web is now authenticated and linked!")
            print("💾 The session has been permanently saved to your agent's profile.")
            print("=" * 65)

            # Update credentials
            auth = SocialAuth()
            auth.remember_browser_logins()

            # Send desktop notification
            try:
                subprocess.run([
                    "notify-send",
                    "🎉 WhatsApp Web Connected!",
                    "Social Agent can now automatically upload your stories to WhatsApp Status!"
                ], check=False)
            except Exception:
                pass

            # Wait 5 seconds to let indexedDB sync fully
            time.sleep(5)
            print("\n✅ Setup complete! You can now close the browser window.")
            return True
        else:
            print("\n⚠️ Login timed out. Please run this script again when you are ready to scan.")
            return False

    except KeyboardInterrupt:
        print("\n🛑 Cancelled by user.")
        return False
    except Exception as e:
        print(f"\n❌ Error launching WhatsApp Web: {e}")
        return False
    finally:
        clean_locks()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
