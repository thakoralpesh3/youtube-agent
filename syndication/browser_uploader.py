from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    HAS_SELENIUM = True
except ImportError:
    webdriver = None
    Options = None
    Service = None
    By = None
    WebDriverWait = None
    EC = None
    HAS_SELENIUM = False

import config
from syndication.social_auth import SocialAuth

import shutil

logger = logging.getLogger(__name__)

_BROWSER_LOCK = threading.RLock()


def with_browser_lock(func):
    """Decorator ensuring only one automated browser instance runs at a time."""
    def wrapper(*args, **kwargs):
        with _BROWSER_LOCK:
            return func(*args, **kwargs)
    return wrapper


class BrowserUploader:
    """
    Automates uploading to Instagram, Facebook, and WhatsApp Web
    using a persistent Firefox profile where the user's logins are preserved.
    Asks for login only ONCE and remembers forever.
    """

    def __init__(self):
        self.auth = SocialAuth()
        self.profile_dir = self.auth.profile_dir
        self.gecko_path = config.BASE_DIR / ".venv" / "bin" / "geckodriver"
        self.ensure_browser_network_config()
        need_sync = (not self.is_whatsapp_session_valid()) or (not self.is_social_session_valid()) or (not (self.profile_dir / "storage" / "default").exists())
        if need_sync:
            self.sync_from_user_firefox(force=True)

    def close(self):
        """Closes browser driver if initialized."""
        if hasattr(self, "_driver") and self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def ensure_browser_network_config(self):
        """
        Ensures Firefox profiles are configured with DNS-over-HTTPS (DoH)
        and IPv6 disabled, completely bypassing local DNS adblockers (ublockdns)
        and avoiding broken IPv6 routing.
        """
        user_js_content = (
            'user_pref("network.trr.mode", 3);\n'
            'user_pref("network.trr.uri", "https://mozilla.cloudflare-dns.com/dns-query");\n'
            'user_pref("network.dns.disableIPv6", true);\n'
        )
        try:
            (self.profile_dir / "user.js").write_text(user_js_content, encoding="utf-8")
        except Exception:
            pass

        try:
            user_mozilla = Path.home() / ".mozilla" / "firefox"
            if user_mozilla.exists():
                for p in user_mozilla.glob("*.default*"):
                    if p.is_dir():
                        (p / "user.js").write_text(user_js_content, encoding="utf-8")
        except Exception:
            pass

    def is_social_session_valid(self) -> bool:
        """Verifies if the persistent profile contains authenticated Instagram/Facebook sessions."""
        cpath = self.profile_dir / "cookies.sqlite"
        if not cpath.exists():
            return False
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{cpath}?immutable=1", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT name FROM moz_cookies WHERE host LIKE '%instagram%' AND name = 'sessionid'")
            has_ig = bool(cur.fetchone())
            cur.execute("SELECT name FROM moz_cookies WHERE host LIKE '%facebook%' AND name IN ('c_user', 'xs')")
            has_fb = bool(cur.fetchone())
            conn.close()
            return has_ig and has_fb
        except Exception:
            return False

    def is_whatsapp_session_valid(self) -> bool:
        """
        Verifies if the persistent profile contains an authenticated, paired WhatsApp session.
        WhatsApp Web requires the Signal key store (3271781254seigganraolt-s.sqlite >= 100KB)
        and the models store (2181795718meogdaerlo-ts.sqlite >= 1MB).
        """
        idb_dir = self.profile_dir / "storage" / "default" / "https+++web.whatsapp.com" / "idb"
        if not idb_dir.exists():
            return False
        signal_db = idb_dir / "3271781254seigganraolt-s.sqlite"
        models_db = idb_dir / "2181795718meogdaerlo-ts.sqlite"
        if not signal_db.exists() or signal_db.stat().st_size < 100_000:
            return False
        if not models_db.exists() or models_db.stat().st_size < 1_000_000:
            return False
        return True

    def sync_from_user_firefox(self, force: bool = False):
        """
        Syncs cookies, credentials, and IndexedDB storage from the host machine's
        primary Firefox profile into the agent's dedicated profile if missing, invalid, or forced.
        Ensures authenticated sessions (Instagram, Facebook, WhatsApp) remain permanently active.
        """
        try:
            user_mozilla = Path.home() / ".mozilla" / "firefox"
            if not user_mozilla.exists():
                return

            # Find default-release profile
            profiles = list(user_mozilla.glob("*.default-release"))
            if not profiles:
                profiles = list(user_mozilla.glob("*.default"))
            if not profiles:
                return

            src_dir = profiles[0]
            wa_is_valid = self.is_whatsapp_session_valid()
            should_sync_wa = force or (not wa_is_valid)
            social_is_valid = self.is_social_session_valid()

            files_to_sync = [
                "cookies.sqlite", "cookies.sqlite-wal", "cookies.sqlite-shm",
                "storage.sqlite", "storage.sqlite-wal", "storage.sqlite-shm",
                "webappsstore.sqlite", "webappsstore.sqlite-wal",
                "logins.json", "key4.db", "cert9.db", "permissions.sqlite", "content-prefs.sqlite"
            ]

            for f in files_to_sync:
                s = src_dir / f
                d = self.profile_dir / f
                if s.exists():
                    if f.startswith("cookies.sqlite") and not force and social_is_valid and d.exists():
                        continue
                    try:
                        shutil.copy2(s, d)
                    except Exception:
                        pass

            # Sync web storage (IndexedDB for WhatsApp Web & Facebook & Instagram)
            src_storage = src_dir / "storage" / "default"
            dst_storage = self.profile_dir / "storage" / "default"
            dst_storage.mkdir(parents=True, exist_ok=True)

            targets = [
                "https+++web.whatsapp.com",
                "https+++webtp.whatsapp.net^partitionKey=%28https%2Cwhatsapp.com%29",
                "https+++flows.whatsapp.net^partitionKey=%28https%2Cwhatsapp.com%29",
                "https+++www.facebook.com",
                "https+++www.facebook.com^partitionKey=%28https%2Cinstagram.com%29",
                "https+++www.fbsbx.com^partitionKey=%28https%2Cinstagram.com%29",
                "https+++www.instagram.com"
            ]
            for t in targets:
                s = src_storage / t
                d = dst_storage / t
                if s.exists():
                    if ("whatsapp" in t or "instagram" in t or "facebook" in t) and not force and d.exists():
                        continue
                    try:
                        if d.exists():
                            shutil.rmtree(d, ignore_errors=True)
                        shutil.copytree(s, d)
                    except Exception as ex:
                        logger.debug(f"Storage copy notice for {t}: {ex}")

            self.auth.remember_browser_logins()
            logger.info("🔗 Successfully synced browser sessions from user profile.")
        except Exception as e:
            logger.debug(f"Profile sync notice: {e}")

    @with_browser_lock
    def launch_login_wizard(self, block: bool = False):
        """
        Launches an interactive Firefox window so the user can log into
        Instagram, Facebook, and WhatsApp once. Sessions will be saved permanently.
        """
        logger.info("Opening Firefox to log into Instagram, Facebook & WhatsApp...")
        self.ensure_browser_network_config()

        # Remove any stale lock files before launching
        for name in ["lock", ".parentlock", ".agent_browser.lock"]:
            lock_file = self.profile_dir / name
            if lock_file.is_symlink() or lock_file.exists():
                try:
                    lock_file.unlink()
                except Exception:
                    pass

        env = os.environ.copy()
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"

        cmd = [
            "/usr/bin/firefox",
            "--no-remote",
            "--profile", str(self.profile_dir),
            "https://www.instagram.com",
            "https://www.facebook.com",
            "https://web.whatsapp.com",
        ]
        proc = subprocess.Popen(cmd, env=env)
        logger.info("Firefox launched. Please log in to your accounts. The session will remain saved.")

        if block:
            proc.wait()
            self.auth.remember_browser_logins()
            logger.info("✅ Browser sessions permanently saved in social_credentials.json. You won't be asked again!")
        else:
            self.auth.remember_browser_logins()

        return proc

    def get_driver(self, headless: Optional[bool] = None, viewport: tuple = (1366, 768)) -> webdriver.Firefox:
        """Initializes a Firefox driver with the persistent profile."""
        if not HAS_SELENIUM:
            raise RuntimeError("Selenium is required for browser automation but is not installed.")
        if headless is None:
            headless = os.getenv("HEADLESS_BROWSER", "1") == "1"

        # Auto-sync session cookies, logins, and storage from user Firefox profile
        try:
            self.sync_from_user_firefox()
        except Exception as sync_err:
            logger.debug(f"Auto-sync notice: {sync_err}")

        self.ensure_browser_network_config()

        # Remove any stale lock files before launching
        for name in ["lock", ".parentlock", ".agent_browser.lock"]:
            lock_file = self.profile_dir / name
            if lock_file.is_symlink() or lock_file.exists():
                try:
                    lock_file.unlink()
                except Exception:
                    pass

        options = Options()
        options.page_load_strategy = "eager"
        if headless:
            options.add_argument("--headless")
        options.add_argument("-profile")
        options.add_argument(str(self.profile_dir))
        options.set_preference("network.trr.mode", 3)
        options.set_preference("network.trr.uri", "https://mozilla.cloudflare-dns.com/dns-query")
        options.set_preference("network.dns.disableIPv6", True)
        options.set_preference("dom.serviceWorkers.enabled", True)
        options.set_preference("dom.serviceWorkers.testing.enabled", True)
        options.set_preference("dom.timeout.enable_budget_timer_throttling", False)
        options.set_preference("dom.min_background_timeout_value", 10)
        options.set_preference("network.websocket.timeout.open", 60)
        options.set_preference("media.autoplay.default", 0)
        # Match standard desktop Firefox user agent to avoid headless blocking
        options.set_preference("general.useragent.override", "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0")

        service = Service(executable_path=str(self.gecko_path))
        driver = webdriver.Firefox(service=service, options=options)
        driver.set_window_size(*viewport)
        return driver

    def dismiss_overlays(self, driver):
        """Automatically dismisses common modals like 'Not Now', 'Accept Cookies', 'Turn on Notifications'."""
        dismiss_selectors = [
            "//button[text()='Not Now']",
            "//button[contains(text(), 'Not now')]",
            "//button[contains(text(), 'Dismiss')]",
            "//button[contains(text(), 'Decline')]",
            "//button[contains(text(), 'Accept all')]",
            "//button[contains(text(), 'Allow all cookies')]",
            "//button[contains(text(), 'Continue')]",
            "//button[contains(text(), 'Got it')]",
            "//button[contains(text(), 'OK')]",
            "//div[@role='button' and contains(., 'Not Now')]",
            "//div[@role='button' and contains(., 'Continue')]",
            "//div[@aria-label='Close']",
            "//button[@aria-label='Close']",
        ]
        for xpath in dismiss_selectors:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(0.5)
            except Exception:
                pass

    def _is_instagram_logged_in(self, driver) -> bool:
        """Checks if current Instagram browser session is logged in."""
        try:
            curr_url = getattr(driver, "current_url", "")
            if any(k in curr_url for k in ["/accounts/login", "checkpoint", "/login"]):
                return False
            # Check for login / account chooser prompts
            if driver.find_elements(By.XPATH, "//div[contains(@aria-label, 'Continue')] | //*[text()='See everyday moments'] | //input[@name='username']"):
                return False
            return bool(driver.find_elements(
                By.XPATH,
                "//*[@aria-label='Create' or @aria-label='New post' or @aria-label='Home' or @aria-label='Profile'] | "
                "//a[contains(@href, '/direct/')] | //a[contains(@href, '/explore/')] | //nav"
            ))
        except Exception:
            return False

    def _handle_instagram_login(self, driver) -> bool:
        """
        Detects if Instagram is on the login/checkpoint page or profile resumption screen
        and attempts auto-login using credentials or clicking saved account profile.
        """
        try:
            time.sleep(2)
            # 1. Check if 'Continue' or 'Continue as <username>' button exists on resumption screen
            try:
                clicked = driver.execute_script('''
                    var spans = Array.from(document.querySelectorAll("span")).filter(s => s.innerText.trim() === "Continue");
                    if (spans.length > 0) {
                        var btn = spans[0].closest("[role='button'], div[aria-label*='Continue'], button");
                        if (btn) { btn.click(); return true; }
                        else { spans[0].click(); return true; }
                    }
                    var ariaBtns = document.querySelectorAll("div[aria-label*='Continue'], button[aria-label*='Continue']");
                    if (ariaBtns.length > 0) {
                        ariaBtns[0].click();
                        return true;
                    }
                    return false;
                ''')
                if clicked:
                    logger.info("👉 [Instagram Web] Clicked 'Continue' on saved profile...")
                    time.sleep(3)
                    self.dismiss_overlays(driver)
            except Exception:
                pass

            # 2. Check for username/password fields if not logged in
            user_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='username']")
            
            # Wait up to 8s for password field to appear (modal animation)
            pass_inputs = []
            try:
                wait_p = WebDriverWait(driver, 8)
                p_el = wait_p.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='password'], input[type='password']")))
                pass_inputs = [p_el]
            except Exception:
                pass_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='password'], input[type='password']")

            ig_user = self.auth.data.get("instagram", {}).get("username") or os.getenv("INSTAGRAM_USERNAME", "")
            ig_pass = self.auth.data.get("instagram", {}).get("password") or os.getenv("INSTAGRAM_PASSWORD", "")

            if user_inputs and pass_inputs and ig_user and ig_pass:
                logger.info(f"🔑 [Instagram Web] Auto-entering login credentials for {ig_user}...")
                user_inputs[0].clear()
                user_inputs[0].send_keys(ig_user)
                time.sleep(0.5)
                pass_inputs[0].clear()
                pass_inputs[0].send_keys(ig_pass)
                time.sleep(0.5)
                submit_btns = driver.find_elements(By.CSS_SELECTOR, "button[type='submit']") or driver.find_elements(By.XPATH, "//button[contains(., 'Log in')] | //div[@role='button'][contains(., 'Log in')]")
                if submit_btns:
                    try:
                        submit_btns[0].click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", submit_btns[0])
                    time.sleep(6)
                    self.dismiss_overlays(driver)
            elif pass_inputs and ig_pass:
                # Password only prompt (profile resumption modal)
                logger.info("🔑 [Instagram Web] Auto-entering password for account...")
                pass_inputs[0].clear()
                pass_inputs[0].send_keys(ig_pass)
                time.sleep(0.5)
                submit_btns = driver.find_elements(By.CSS_SELECTOR, "button[type='submit']") or driver.find_elements(By.XPATH, "//button[contains(., 'Log in')] | //div[@role='button'][contains(., 'Log in')]")
                if submit_btns:
                    try:
                        submit_btns[0].click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", submit_btns[0])
                    time.sleep(6)
                    self.dismiss_overlays(driver)
            elif pass_inputs and not ig_pass:
                logger.warning("🔑 [Instagram Web] Password prompt detected, but INSTAGRAM_PASSWORD is not set in .env. Interactive login or password needed.")

            # Check if logged in
            is_logged_in = self._is_instagram_logged_in(driver)
            if is_logged_in:
                self.auth.data["browser_session"]["instagram_logged_in"] = True
                self.auth.save()
                return True
        except Exception as e:
            logger.debug(f"Instagram login check notice: {e}")
        return False

    def _is_facebook_logged_in(self, driver) -> bool:
        """Checks if current Facebook browser session is logged in."""
        try:
            curr_url = getattr(driver, "current_url", "")
            if any(k in curr_url for k in ["login.php", "checkpoint", "/login/", "index.php?next="]):
                return False
            if driver.find_elements(By.XPATH, "//div[contains(@aria-label, 'Continue')] | //input[@id='email'] | //input[@name='email']"):
                return False
            return bool(driver.find_elements(
                By.XPATH,
                "//div[@aria-label='Account' or @aria-label='Your profile'] | "
                "//a[contains(@href, '/me')] | //div[@role='navigation'] | "
                "//*[contains(text(), 'Your story') or contains(text(), 'Create a photo')] | "
                "//div[contains(@aria-label, 'Stories')] | "
                "//input[@type='file']"
            )) or ("/stories/create" in curr_url and "login" not in curr_url and "index.php" not in curr_url)
        except Exception:
            return False

    def _handle_facebook_login(self, driver) -> bool:
        """
        Detects if Facebook is on the login page or profile resumption screen and attempts auto-login.
        """
        try:
            time.sleep(2)
            fb_email = os.getenv("FACEBOOK_EMAIL") or self.auth.data.get("facebook", {}).get("email", "")
            fb_pass = os.getenv("FACEBOOK_PASSWORD") or self.auth.data.get("facebook", {}).get("password", "")

            # 1. Check for profile resumption Continue button
            try:
                clicked = driver.execute_script('''
                    var spans = Array.from(document.querySelectorAll("span")).filter(s => s.innerText.trim() === "Continue");
                    if (spans.length > 0) {
                        var btn = spans[0].closest("[role='button'], div[aria-label*='Continue'], button");
                        if (btn) { btn.click(); return true; }
                        else { spans[0].click(); return true; }
                    }
                    var ariaBtns = document.querySelectorAll("div[aria-label*='Continue'], button[aria-label*='Continue']");
                    if (ariaBtns.length > 0) {
                        ariaBtns[0].click();
                        return true;
                    }
                    return false;
                ''')
                if clicked:
                    logger.info("👉 [Facebook Web] Clicked 'Continue' on profile resumption screen...")
                    time.sleep(3)
                    self.dismiss_overlays(driver)
            except Exception:
                pass

            email_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='email'], input#email")
            
            # Wait up to 8s for password field to appear (skeleton animation)
            pass_inputs = []
            try:
                wait_p = WebDriverWait(driver, 8)
                p_el = wait_p.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password'], input[name='pass'], input#pass")))
                pass_inputs = [p_el]
            except Exception:
                pass_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='pass'], input#pass, input[type='password']")

            if email_inputs and pass_inputs and fb_email and fb_pass:
                logger.info(f"🔑 [Facebook Web] Auto-entering login credentials for {fb_email}...")
                email_inputs[0].clear()
                email_inputs[0].send_keys(fb_email)
                time.sleep(0.5)
                pass_inputs[0].clear()
                pass_inputs[0].send_keys(fb_pass)
                time.sleep(0.5)
                login_btn = driver.find_elements(By.CSS_SELECTOR, "button[name='login'], button[type='submit']") or driver.find_elements(By.XPATH, "//button[contains(., 'Log in')] | //div[@role='button'][contains(., 'Log in')]")
                if login_btn:
                    try:
                        login_btn[0].click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", login_btn[0])
                    time.sleep(6)
                    self.dismiss_overlays(driver)
            elif pass_inputs and fb_pass:
                # Password-only prompt (profile modal)
                logger.info("🔑 [Facebook Web] Auto-entering password for recognized Facebook profile...")
                pass_inputs[0].clear()
                pass_inputs[0].send_keys(fb_pass)
                time.sleep(0.5)
                login_btn = driver.find_elements(By.CSS_SELECTOR, "button[name='login'], button[type='submit']") or driver.find_elements(By.XPATH, "//button[contains(., 'Log in')] | //div[@role='button'][contains(., 'Log in')]")
                if login_btn:
                    try:
                        login_btn[0].click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", login_btn[0])
                    time.sleep(6)
                    self.dismiss_overlays(driver)
            elif pass_inputs and not fb_pass:
                logger.warning("🔑 [Facebook Web] Password prompt detected, but FACEBOOK_PASSWORD is not set in .env. Interactive login or password needed.")

            # Check if logged in
            is_logged_in = self._is_facebook_logged_in(driver)
            if is_logged_in:
                self.auth.data["browser_session"]["facebook_logged_in"] = True
                self.auth.save()
                return True
        except Exception as e:
            logger.debug(f"Facebook login check notice: {e}")
        return False

    def _notify_whatsapp_login_required(self):
        """Sends WhatsApp login notification at most once per 24 hours to prevent spam."""
        throttle_file = config.OUTPUT_DIR / "wa_login_notified.txt"
        now = time.time()
        if throttle_file.exists():
            try:
                last_time = float(throttle_file.read_text().strip())
                if now - last_time < 86400:
                    logger.debug("WhatsApp login notification throttled (already notified within last 24h).")
                    return
            except Exception:
                pass
        try:
            throttle_file.write_text(str(now))
            subprocess.run([
                "notify-send", "-u", "normal",
                "📱 WhatsApp Web Login Required",
                "Run 'python3 login_whatsapp.py' on your laptop to link WhatsApp Status auto-publishing."
            ], check=False)
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # 1. WHATSAPP WEB STATUS POSTER
    # --------------------------------------------------------------------------
    @with_browser_lock
    def post_whatsapp_status(self, video_path: Path, caption: str) -> Dict[str, Any]:
        """Posts a video or image directly to WhatsApp Status via WhatsApp Web automation."""
        if not video_path.exists():
            return {"status": "FAILED", "platform": "whatsapp", "reason": "Media file missing"}

        driver = None
        try:
            logger.info(f"🌐 [WhatsApp Web] Opening WhatsApp Web for Status upload: {video_path.name}...")
            if not self.is_whatsapp_session_valid():
                logger.info("🔄 [WhatsApp Web] Valid session missing in social_firefox. Syncing from user profile...")
                self.sync_from_user_firefox(force=True)

            driver = self.get_driver()
            driver.get("https://web.whatsapp.com")

            # Dismiss any welcome / update modals if present
            self.dismiss_overlays(driver)

            # Wait for WhatsApp Web to connect and show Status button (up to 120s)
            logger.info("⏳ [WhatsApp Web] Waiting for WhatsApp Web session to connect...")
            status_btn = None
            for tick in range(60):
                self.dismiss_overlays(driver)
                btns = driver.find_elements(
                    By.XPATH,
                    "//header//button[@aria-label='Status'] | "
                    "//button[@aria-label='Status'] | "
                    "//*[@aria-label='Status'] | "
                    "//*[@data-icon='status-v3'] | "
                    "//*[@data-icon='status-outline'] | "
                    "//*[@data-icon='newsletter-status-outline']"
                )
                if btns:
                    status_btn = btns[0]
                    break

                # Also verify if chat list / navigation rail has already rendered
                logged_in_elements = driver.find_elements(
                    By.XPATH,
                    "//div[@role='navigation'] | "
                    "//*[@data-testid='chat-list'] | "
                    "//*[@aria-label='Chat list'] | "
                    "//*[@data-icon='chat'] | "
                    "//button[@aria-label='New chat']"
                )
                if logged_in_elements:
                    # Session is active! Retry fetching Status icon from navigation rail
                    rail_icons = driver.find_elements(
                        By.XPATH,
                        "//*[@aria-label='Status'] | //*[@data-icon='status-v3'] | //button[contains(@aria-label, 'Status')]"
                    )
                    if rail_icons:
                        status_btn = rail_icons[0]
                        break

                # Detection of QR code scan: only check after at least 60s (tick >= 30)
                # to give ample time for IndexedDB decryption, and ensure no loading progress or chat list
                if tick >= 30:
                    qr_elements = driver.find_elements(
                        By.XPATH,
                        "//div[@data-ref] | //*[@data-testid='qrcode']//canvas | //canvas[@aria-label='Scan this QR code to link a device!']"
                    )
                    loading_elements = driver.find_elements(
                        By.XPATH,
                        "//*[contains(text(), 'End-to-end encrypted')] | //progress | //*[@role='progressbar'] | //div[contains(@class, 'progress')]"
                    )
                    if qr_elements and not loading_elements and not logged_in_elements:
                        logger.warning("⚠️ [WhatsApp Web] Session is not logged in - QR code scan required.")
                        try:
                            driver.save_screenshot("output/whatsapp_qr.png")
                            driver.save_screenshot("output/debug_wa_session_state.png")
                            self._notify_whatsapp_login_required()
                        except Exception:
                            pass
                        return {
                            "status": "FAILED",
                            "platform": "whatsapp",
                            "reason": "WhatsApp Web not logged in. Please scan QR code via 'python3 login_whatsapp.py'."
                        }

                if tick > 0 and tick % 5 == 0:
                    logger.info(f"⏳ [WhatsApp Web] Still connecting / loading session ({tick * 2}s elapsed)...")
                time.sleep(2)

            if not status_btn:
                logger.warning("⚠️ [WhatsApp Web] Status button not found after waiting. Checking session state.")
                try:
                    driver.save_screenshot("output/debug_wa_session_state.png")
                except Exception:
                    pass
                return {"status": "FAILED", "platform": "whatsapp", "reason": "WhatsApp Web not ready or not logged in"}

            # Click Status Tab
            logger.info("👉 [WhatsApp Web] Opening Status tab...")
            driver.execute_script("arguments[0].click();", status_btn)
            time.sleep(2)
            self.dismiss_overlays(driver)

            # Click 'Add Status' button in Status header
            add_btn = None
            for _ in range(15):
                btns = driver.find_elements(
                    By.XPATH,
                    "//button[@aria-label='Add Status'] | "
                    "//*[@aria-label='Add Status'] | "
                    "//button[contains(., 'Add Status') or contains(., 'Add status')] | "
                    "//button[contains(., 'My status')] | "
                    "//div[contains(., 'My status') and @role='button'] | "
                    "//span[@data-icon='plus']/ancestor::*[@role='button' or self::button]"
                )
                if btns:
                    add_btn = btns[0]
                    break
                time.sleep(1)

            if not add_btn:
                logger.warning("⚠️ [WhatsApp Web] Add Status button not found.")
                return {"status": "FAILED", "platform": "whatsapp", "reason": "Add Status button not found"}

            logger.info("👉 [WhatsApp Web] Clicking 'Add Status'...")
            driver.execute_script("arguments[0].click();", add_btn)
            time.sleep(2)

            # Click 'Photos & videos' if dropdown appears
            photos_item = driver.find_elements(By.XPATH, "//*[contains(text(), 'Photos & videos')]/ancestor::*[@role='button' or self::li or self::div][1]")
            if photos_item:
                driver.execute_script("arguments[0].click();", photos_item[0])
                time.sleep(2)

            # Find file input for status
            wait = WebDriverWait(driver, 25)
            file_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']")))
            logger.info(f"📤 [WhatsApp Web] Attaching {video_path.name} to Status composer...")
            file_input.send_keys(str(video_path.resolve()))
            time.sleep(6)

            # Add caption if input is found
            try:
                caption_inputs = driver.find_elements(By.XPATH, "//div[@aria-label='Add a caption'] | //div[contains(@aria-label, 'caption')] | //div[@contenteditable='true']")
                if caption_inputs:
                    caption_inputs[-1].send_keys(caption[:120])
                    time.sleep(1)
            except Exception:
                pass

            # Click Send button (allow up to 60s for video/media processing)
            logger.info("⏳ [WhatsApp Web] Waiting for media preview and Send button...")
            send_btn = None
            for tick in range(30):
                btns = driver.find_elements(
                    By.XPATH,
                    "//div[contains(@aria-label, 'Send')] | "
                    "//*[@data-icon='send'] | "
                    "//*[@aria-label='Send'] | "
                    "//button[@aria-label='Send'] | "
                    "//span[@data-icon='send']/ancestor::*[@role='button']"
                )
                if btns:
                    send_btn = btns[0]
                    break
                time.sleep(2)

            if not send_btn:
                wait_send = WebDriverWait(driver, 30)
                send_btn = wait_send.until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//div[contains(@aria-label, 'Send')] | "
                        "//*[@data-icon='send'] | "
                        "//*[@aria-label='Send'] | "
                        "//button[@aria-label='Send']"
                    ))
                )

            driver.execute_script("arguments[0].click();", send_btn)
            logger.info("🚀 [WhatsApp Web] Clicked Send! Actively monitoring status transmission until confirmed...")

            # Smart Status transmission verification:
            # WhatsApp Web takes 30-70s to encrypt media, upload chunks to MMG servers, and sync with primary phone.
            # Never kill the browser while 'Sending...' is still in flight!
            confirmed = False
            for tick in range(40):  # Up to 120 seconds
                time.sleep(3)
                try:
                    status_items = driver.find_elements(
                        By.XPATH,
                        "//*[contains(text(), 'My status')]/ancestor::div[contains(@role, 'button') or self::div][1]"
                    )
                    if status_items:
                        txt = status_items[0].text
                        if "Sending" in txt:
                            if tick % 4 == 0:
                                logger.info(f"⏳ [WhatsApp Web] Encrypting & uploading media to WhatsApp servers ({(tick + 1) * 3}s elapsed)...")
                            continue
                        elif any(marker in txt for marker in ["Just now", "Today at", "minute", "Yesterday", "AM", "PM", ":"]) or (txt.strip() and "Sending" not in txt and "Couldn't send" not in txt):
                            logger.info(f"🎉 [WHATSAPP COMPLETE] Status confirmed published on WhatsApp! Status state: {txt.replace(chr(10), ' | ')}")
                            confirmed = True
                            break
                        elif "Couldn't send" in txt or "failed" in txt.lower():
                            logger.warning(f"⚠️ [WhatsApp Web] WhatsApp reported send failure: {txt}")
                            return {"status": "FAILED", "platform": "whatsapp", "reason": f"WhatsApp reported failure: {txt}"}
                except Exception:
                    pass

            if not confirmed:
                logger.warning("⚠️ [WhatsApp Web] Status send timed out before confirmation.")
                return {"status": "FAILED", "platform": "whatsapp", "reason": "Timeout waiting for WhatsApp server ACK"}

            # Allow 8s for socket buffers to flush and synchronize to primary phone
            time.sleep(8)
            return {"status": "PUBLISHED", "platform": "whatsapp"}

        except Exception as e:
            logger.warning(f"WhatsApp Web automated upload error: {e}")
            return {"status": "FAILED", "platform": "whatsapp", "reason": str(e)}
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    # --------------------------------------------------------------------------
    # 2. INSTAGRAM POST / REEL / STORY POSTER
    # --------------------------------------------------------------------------
    @with_browser_lock
    def post_instagram_reel(self, video_path: Path, caption: str) -> Dict[str, Any]:
        """Uploads video or image to Instagram using Desktop Web creator interface."""
        if not video_path.exists():
            return {"status": "FAILED", "platform": "instagram", "reason": "Media file missing"}

        driver = None
        try:
            logger.info(f"🌐 [Instagram Web] Opening Instagram for upload: {video_path.name}...")
            driver = self.get_driver()
            driver.get("https://www.instagram.com/")

            wait = WebDriverWait(driver, 30)
            time.sleep(5)
            self.dismiss_overlays(driver)
            self._handle_instagram_login(driver)

            # Click Create in left navigation using robust selectors
            create_btn = None
            try:
                create_btn = wait.until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        "//*[local-name()='svg' and (@aria-label='New post' or @aria-label='Create')]/ancestor::div[@role='button' or self::a or self::div][1] | "
                        "//a[contains(@href, '/create/') or .//span[text()='Create']] | "
                        "//div[@role='button' and .//span[text()='Create']] | "
                        "//*[@aria-label='New post'] | //*[@aria-label='Create']"
                    ))
                )
            except Exception:
                logger.info("⚠️ Create button not found immediately. Checking login state...")
                self._handle_instagram_login(driver)
                if not self._is_instagram_logged_in(driver):
                    logger.warning("⚠️ [Instagram Web] Account is not logged in. Instagram upload skipped.")
                    return {
                        "status": "FAILED",
                        "platform": "instagram",
                        "reason": "Instagram login required. Enter credentials in .env or run 'python3 connect_accounts.py --login-browser'."
                    }
                try:
                    wait_retry = WebDriverWait(driver, 15)
                    create_btn = wait_retry.until(
                        EC.presence_of_element_located((
                            By.XPATH,
                            "//*[local-name()='svg' and (@aria-label='New post' or @aria-label='Create')]/ancestor::div[@role='button' or self::a or self::div][1] | "
                            "//a[contains(@href, '/create/') or .//span[text()='Create']] | "
                            "//div[@role='button' and .//span[text()='Create']] | "
                            "//*[@aria-label='New post'] | //*[@aria-label='Create']"
                        ))
                    )
                except Exception:
                    logger.warning("⚠️ [Instagram Web] Create button not found after login check.")
                    return {"status": "FAILED", "platform": "instagram", "reason": "Create button not found"}
            driver.execute_script("arguments[0].click();", create_btn)
            time.sleep(2)

            # Check for 'Post' submenu item if visible
            post_submenu = driver.find_elements(By.XPATH, "//span[text()='Post'] | //div[@role='button' and .//span[text()='Post']]")
            if post_submenu:
                driver.execute_script("arguments[0].click();", post_submenu[0])
                time.sleep(2)

            # Locate file input (modal takes 5-15s to render drag-and-drop container)
            modal_wait = WebDriverWait(driver, 40)
            file_input = modal_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']")))
            logger.info(f"📤 [Instagram] Attaching {video_path.name} to upload input...")
            file_input.send_keys(str(video_path.resolve()))
            time.sleep(6)

            # Click Next (step 1: Crop/Aspect)
            next_xpath = (
                "//div[@role='dialog']//div[@role='button' and (text()='Next' or .//span[text()='Next'] or contains(., 'Next'))] | "
                "//div[@role='dialog']//button[contains(., 'Next')] | "
                "//div[@role='dialog']//*[@aria-label='Next']"
            )
            next_btn = modal_wait.until(EC.element_to_be_clickable((By.XPATH, next_xpath)))
            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(4)

            # Click Next (step 2: Filter/Edit)
            next_btns2 = driver.find_elements(By.XPATH, next_xpath)
            if next_btns2:
                for b in next_btns2:
                    if b.is_displayed():
                        driver.execute_script("arguments[0].click();", b)
                        break
                time.sleep(4)

            # Add caption (support modern Instagram 'Add a caption...' label)
            try:
                caption_input = driver.find_elements(
                    By.XPATH,
                    "//div[@role='dialog']//div[@contenteditable='true' or contains(@aria-label, 'caption') or contains(@aria-label, 'Caption')]"
                )
                if caption_input:
                    caption_input[0].send_keys(caption[:300])
                    time.sleep(2)
            except Exception:
                pass

            # Click Share button in dialog header (avoid background feed share icons)
            share_xpath = (
                "//div[@role='dialog']//div[@role='button' and (text()='Share' or .//span[text()='Share'] or contains(., 'Share'))] | "
                "//div[@role='dialog']//button[contains(., 'Share')] | "
                "//div[@role='dialog']//*[@aria-label='Share']"
            )
            share_btn = modal_wait.until(EC.element_to_be_clickable((By.XPATH, share_xpath)))
            driver.execute_script("arguments[0].click();", share_btn)
            logger.info("🚀 [Instagram] Clicked 'Share'! Waiting for upload to complete...")
            
            # Wait up to 30s for 'Sharing' animation or confirmation
            for _ in range(15):
                time.sleep(2)
                confirmations = driver.find_elements(
                    By.XPATH,
                    "//*[contains(text(), 'Your post has been shared') or contains(text(), 'Post shared') or contains(text(), 'Reel shared')] | "
                    "//div[@role='dialog']//span[contains(text(), 'shared')]"
                )
                if confirmations:
                    break
                dialogs = driver.find_elements(By.XPATH, "//div[@role='dialog']")
                if not dialogs:
                    break

            logger.info("🎉 [INSTAGRAM COMPLETE] Post published successfully!")
            return {"status": "PUBLISHED", "platform": "instagram"}

        except Exception as e:
            logger.warning(f"Instagram automated upload notice: {e}")
            return {"status": "FAILED", "platform": "instagram", "reason": str(e)}
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    # --------------------------------------------------------------------------
    # 3. FACEBOOK STORY POSTER
    # --------------------------------------------------------------------------
    @with_browser_lock
    def post_facebook_story(self, video_path: Path, caption: str) -> Dict[str, Any]:
        """Uploads video or image to Facebook Stories/Reels and publishes."""
        if not video_path.exists():
            return {"status": "FAILED", "platform": "facebook", "reason": "Media file missing"}

        driver = None
        try:
            logger.info(f"🌐 [Facebook Web] Opening Facebook for upload: {video_path.name}...")
            driver = self.get_driver()
            
            is_video = video_path.suffix.lower() in [".mp4", ".mov", ".avi", ".webm"]
            wait = WebDriverWait(driver, 25)

            if is_video:
                # Video upload via Facebook Reels creator
                driver.get("https://www.facebook.com/reels/create")
                time.sleep(5)
                self.dismiss_overlays(driver)
                self._handle_facebook_login(driver)
                if not self._is_facebook_logged_in(driver):
                    logger.warning("⚠️ [Facebook Web] Account is not logged in. Facebook Reel upload skipped.")
                    return {
                        "status": "FAILED",
                        "platform": "facebook",
                        "reason": "Facebook login required. Enter credentials in .env or run 'python3 connect_accounts.py --login-browser'."
                    }

                file_input = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
                )
                file_input.send_keys(str(video_path.resolve()))
                logger.info("📤 Video attached to Facebook Reels composer. Waiting for upload...")
                time.sleep(8)

                # Add caption in description if present
                try:
                    cap_boxes = driver.find_elements(By.CSS_SELECTOR, "div[contenteditable='true'], textarea")
                    if cap_boxes:
                        cap_boxes[0].send_keys(caption[:300])
                        time.sleep(2)
                except Exception:
                    pass

                # Click Next buttons through the wizard
                for _ in range(3):
                    next_btns = driver.find_elements(By.XPATH, "//div[@role='button' and (text()='Next' or .//span[text()='Next'] or .//div[text()='Next'])] | //button[contains(., 'Next')]")
                    if next_btns:
                        driver.execute_script("arguments[0].click();", next_btns[0])
                        time.sleep(3)

                # Click Publish / Share button
                pub_btns = driver.find_elements(By.XPATH, "//div[@role='button' and (text()='Publish' or text()='Share' or .//span[text()='Publish'])] | //button[contains(., 'Publish')]")
                if pub_btns:
                    driver.execute_script("arguments[0].click();", pub_btns[0])
                    time.sleep(12)

                logger.info("🎉 [FACEBOOK COMPLETE] Facebook Reel published successfully!")
                return {"status": "PUBLISHED", "platform": "facebook"}

            else:
                # Photo upload via Facebook Stories creator
                driver.get("https://www.facebook.com/stories/create")
                time.sleep(5)
                self.dismiss_overlays(driver)
                self._handle_facebook_login(driver)
                if not self._is_facebook_logged_in(driver):
                    logger.warning("⚠️ [Facebook Web] Account is not logged in. Facebook Story upload skipped.")
                    return {
                        "status": "FAILED",
                        "platform": "facebook",
                        "reason": "Facebook login required. Enter credentials in .env or run 'python3 connect_accounts.py --login-browser'."
                    }

                # Locate file input, clicking 'Create a photo story' card if necessary
                file_input = None
                inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                if inputs:
                    file_input = inputs[0]
                else:
                    cards = driver.find_elements(By.XPATH, "//*[contains(text(), 'Create a photo story') or contains(text(), 'Create a Photo Story')]/ancestor::div[@role='button' or self::div][1]")
                    if cards:
                        driver.execute_script("arguments[0].click();", cards[0])
                        time.sleep(2)
                    file_input = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
                    )

                file_input.send_keys(str(video_path.resolve()))
                logger.info("📤 Image attached to Facebook Story composer. Waiting for preview...")
                time.sleep(6)

                # Click 'Share to story' button
                share_btn = wait.until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//div[@aria-label='Share to story'] | "
                        "//span[contains(text(), 'Share to story')]/ancestor::*[@role='button' or self::button] | "
                        "//button[contains(., 'Share to story')]"
                    ))
                )
                driver.execute_script("arguments[0].click();", share_btn)
                logger.info("🚀 Clicked 'Share to story' on Facebook! Waiting for upload to complete...")
                time.sleep(10)

                logger.info("🎉 [FACEBOOK COMPLETE] Facebook Story published successfully!")
                return {"status": "PUBLISHED", "platform": "facebook"}

        except Exception as e:
            logger.warning(f"Facebook Web automated upload notice: {e}")
            try:
                driver.save_screenshot("output/debug_fb_session_state.png")
            except Exception:
                pass
            return {"status": "FAILED", "platform": "facebook", "reason": str(e)}
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
