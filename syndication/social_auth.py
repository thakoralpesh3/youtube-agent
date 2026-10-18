import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
import datetime

import config

logger = logging.getLogger(__name__)


class SocialAuth:
    """
    Manages persistent authentication for Instagram, Facebook, and WhatsApp.
    Asks only ONCE and remembers credentials and browser sessions permanently.
    """

    def __init__(self, creds_file: Optional[Path] = None):
        self.creds_file = creds_file or (config.BASE_DIR / "social_credentials.json")
        self.profile_dir = config.BASE_DIR / "assets" / "browser_profiles" / "social_firefox"
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        """Loads saved credentials from file or environment."""
        default_structure = {
            "instagram": {
                "access_token": os.getenv("INSTAGRAM_ACCESS_TOKEN") or os.getenv("META_ACCESS_TOKEN", ""),
                "account_id": os.getenv("INSTAGRAM_ACCOUNT_ID", ""),
                "username": os.getenv("INSTAGRAM_USERNAME", ""),
                "password": os.getenv("INSTAGRAM_PASSWORD", ""),
                "sessionid": os.getenv("INSTAGRAM_SESSIONID", ""),
                "is_authenticated": False,
            },
            "facebook": {
                "page_access_token": os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("META_ACCESS_TOKEN", ""),
                "page_id": os.getenv("FACEBOOK_PAGE_ID", ""),
                "is_authenticated": False,
            },
            "whatsapp": {
                "token": os.getenv("WHATSAPP_TOKEN", ""),
                "phone_number_id": os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
                "target_phone": os.getenv("WHATSAPP_TARGET_PHONE", ""),
                "is_authenticated": False,
            },
            "browser_session": {
                "instagram_logged_in": False,
                "facebook_logged_in": False,
                "whatsapp_logged_in": False,
                "first_setup_done": False,
            },
        }

        if self.creds_file.exists():
            try:
                with open(self.creds_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    # Merge with default structure to prevent missing keys
                    for k, v in saved.items():
                        if k in default_structure and isinstance(v, dict):
                            default_structure[k].update(v)
                        else:
                            default_structure[k] = v
            except Exception as e:
                logger.warning(f"Could not load social_credentials.json ({e}). Using defaults.")

        # If cookies or sqlite files exist in profile_dir, mark browser session as active
        cookie_file = self.profile_dir / "cookies.sqlite"
        if cookie_file.exists() and cookie_file.stat().st_size > 10000:
            default_structure["browser_session"]["first_setup_done"] = True

        return default_structure

    def save(self):
        """Persists credentials and session states to social_credentials.json."""
        try:
            with open(self.creds_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            logger.info("💾 Social credentials & session states saved permanently.")
        except Exception as e:
            logger.warning(f"Could not save social credentials: {e}")

    # --------------------------------------------------------------------------
    # Checks (Returns True if platform is ready so agent NEVER asks again)
    # --------------------------------------------------------------------------
    def is_instagram_ready(self) -> bool:
        ig = self.data.get("instagram", {})
        browser = self.data.get("browser_session", {})
        has_api = bool((ig.get("access_token") and ig.get("account_id")) or ig.get("sessionid"))
        has_browser = bool(browser.get("instagram_logged_in") or browser.get("first_setup_done"))
        return has_api or has_browser

    def is_facebook_ready(self) -> bool:
        fb = self.data.get("facebook", {})
        browser = self.data.get("browser_session", {})
        has_api = bool((fb.get("page_access_token") and fb.get("page_id")) or fb.get("user_id") or fb.get("xs"))
        has_browser = bool(browser.get("facebook_logged_in") or browser.get("first_setup_done"))
        return has_api or has_browser

    def is_whatsapp_ready(self) -> bool:
        wa = self.data.get("whatsapp", {})
        browser = self.data.get("browser_session", {})
        has_api = bool(wa.get("token") and wa.get("phone_number_id"))
        has_browser = bool(browser.get("whatsapp_logged_in") or browser.get("first_setup_done"))
        return has_api or has_browser

    # --------------------------------------------------------------------------
    # Remember Logins & Tokens
    # --------------------------------------------------------------------------
    def remember_tokens(
        self,
        meta_token: Optional[str] = None,
        ig_account_id: Optional[str] = None,
        fb_page_id: Optional[str] = None,
        wa_token: Optional[str] = None,
        wa_phone_id: Optional[str] = None,
    ):
        """Stores API tokens once and remembers them forever."""
        if meta_token:
            self.data["instagram"]["access_token"] = meta_token
            self.data["facebook"]["page_access_token"] = meta_token
        if ig_account_id:
            self.data["instagram"]["account_id"] = ig_account_id
            self.data["instagram"]["is_authenticated"] = True
        if fb_page_id:
            self.data["facebook"]["page_id"] = fb_page_id
            self.data["facebook"]["is_authenticated"] = True
        if wa_token:
            self.data["whatsapp"]["token"] = wa_token
        if wa_phone_id:
            self.data["whatsapp"]["phone_number_id"] = wa_phone_id
            self.data["whatsapp"]["is_authenticated"] = True

        self.save()

    def remember_instagram_credentials(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        sessionid: Optional[str] = None,
    ):
        """Stores direct Instagram API credentials or session cookie."""
        if username:
            self.data["instagram"]["username"] = username
        if password:
            self.data["instagram"]["password"] = password
        if sessionid:
            self.data["instagram"]["sessionid"] = sessionid
        self.data["instagram"]["is_authenticated"] = bool(username or sessionid)
        self.save()

    def remember_browser_logins(self):
        """Marks browser sessions as authenticated so agent never prompts again."""
        self.data["browser_session"]["instagram_logged_in"] = True
        self.data["browser_session"]["facebook_logged_in"] = True
        self.data["browser_session"]["whatsapp_logged_in"] = True
        self.data["browser_session"]["first_setup_done"] = True
        self.data["browser_session"]["last_verified"] = datetime.datetime.now().isoformat()
        self.save()

    def get_meta_credentials(self) -> Dict[str, str]:
        """Returns remembered Meta tokens."""
        return {
            "meta_access_token": self.data["instagram"].get("access_token") or self.data["facebook"].get("page_access_token", ""),
            "ig_account_id": self.data["instagram"].get("account_id", ""),
            "fb_page_id": self.data["facebook"].get("page_id", ""),
            "wa_token": self.data["whatsapp"].get("token", ""),
            "wa_phone_id": self.data["whatsapp"].get("phone_number_id", ""),
            "wa_target_phone": self.data["whatsapp"].get("target_phone", ""),
        }
