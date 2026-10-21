import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

# Force IPv4 preference for Google OAuth endpoints to prevent SSLEOFError/Errno 93
try:
    _orig_getaddrinfo = socket.getaddrinfo
    def _ipv4_getaddrinfo(*args, **kwargs):
        res = _orig_getaddrinfo(*args, **kwargs)
        ipv4 = [r for r in res if r[0] == socket.AF_INET]
        return ipv4 if ipv4 else res
    socket.getaddrinfo = _ipv4_getaddrinfo
except Exception:
    pass

import requests
from requests.adapters import HTTPAdapter
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

import config

logger = logging.getLogger(__name__)

# Scopes required for uploading YouTube videos
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


class _TimeoutHTTPAdapter(HTTPAdapter):
    """Ensures Google OAuth request calls enforce explicit connection and read timeouts."""
    def __init__(self, timeout: int = 10, *args, **kwargs):
        self.timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, *args, **kwargs):
        kwargs["timeout"] = kwargs.get("timeout") or self.timeout
        return super().send(*args, **kwargs)


def _get_auth_request(timeout: int = 10) -> Request:
    """Builds a Google Auth Request object with explicit timeouts to prevent 20s socket stalls."""
    session = requests.Session()
    adapter = _TimeoutHTTPAdapter(timeout=timeout)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return Request(session=session)


class YouTubeAuth:
    def __init__(
        self,
        client_secret_file: Optional[Path] = None,
        token_file: Optional[Path] = None,
    ):
        self.client_secret_file = client_secret_file or Path(config.YOUTUBE_CLIENT_SECRET_FILE)
        self.token_file = token_file or Path(config.YOUTUBE_TOKEN_FILE)
        self._is_revoked: bool = False

    def has_credentials(self) -> bool:
        """Returns True if token.json or client_secret.json exists."""
        return self.token_file.exists() or self.client_secret_file.exists()

    def has_refresh_token(self) -> bool:
        """Returns True if token.json exists and contains a refresh token."""
        if not self.token_file.exists():
            return False
        try:
            data = json.loads(self.token_file.read_text(encoding="utf-8"))
            return bool(data.get("refresh_token"))
        except Exception:
            return False

    def is_token_valid(self, max_retries: int = 2) -> bool:
        """
        Returns True if valid, usable YouTube credentials currently exist.
        Safely attempts a silent refresh with timeout & retry if expired.
        Returns False only if the token is truly missing, corrupt, or revoked.
        """
        if not self.token_file.exists():
            return False
        try:
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
            if creds.valid:
                return True
            if creds.refresh_token:
                req = _get_auth_request(timeout=8)
                for attempt in range(max_retries):
                    try:
                        creds.refresh(req)
                        with open(self.token_file, "w") as token_out:
                            token_out.write(creds.to_json())
                        self._is_revoked = False
                        return True
                    except RefreshError as ref_err:
                        err_str = str(ref_err).lower()
                        if "invalid_grant" in err_str or "revoked" in err_str or "deleted" in err_str:
                            logger.warning(f"YouTube refresh token is permanently revoked or expired: {ref_err}")
                            self._is_revoked = True
                            return False
                        logger.warning(f"YouTube token refresh error (attempt {attempt + 1}/{max_retries}): {ref_err}")
                        time.sleep(1)
                    except (TransportError, requests.RequestException, socket.error) as net_err:
                        logger.debug(f"Network error during YouTube token refresh (attempt {attempt + 1}/{max_retries}): {net_err}")
                        time.sleep(1)
                    except Exception as e:
                        logger.warning(f"Unexpected error during YouTube token refresh: {e}")
                        break
            return False
        except Exception as e:
            logger.debug(f"Could not load or parse YouTube token file: {e}")
            return False

    def is_permanently_revoked(self) -> bool:
        """
        Returns True if the token is permanently revoked or invalid (invalid_grant),
        requiring interactive re-login. Returns False if token is valid or temporarily unreachable due to network.
        """
        if not self.token_file.exists() or not self.has_refresh_token():
            return True
        return self._is_revoked

    def get_credentials(self) -> Credentials:
        """
        Gets valid YouTube OAuth2 credentials.
        Loads existing token.json or initiates OAuth2 web flow with permanent offline access.
        """
        creds = None

        # 1. Check if token.json exists
        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
            except Exception as e:
                logger.warning(f"Failed to load existing token file: {e}")
                creds = None

        # 2. Refresh or create new token
        if not creds or not creds.valid:
            if creds and creds.refresh_token:
                logger.info("Refreshing expired YouTube OAuth2 credentials...")
                req = _get_auth_request(timeout=10)
                refresh_succeeded = False
                permanent_failure = False
                last_err = None

                for attempt in range(3):
                    try:
                        creds.refresh(req)
                        with open(self.token_file, "w") as token_out:
                            token_out.write(creds.to_json())
                        logger.info("Refreshed and saved updated credentials.")
                        refresh_succeeded = True
                        break
                    except RefreshError as ref_err:
                        last_err = ref_err
                        err_str = str(ref_err).lower()
                        if "invalid_grant" in err_str or "revoked" in err_str or "deleted" in err_str:
                            permanent_failure = True
                            self._is_revoked = True
                            logger.warning(f"YouTube refresh token permanently revoked: {ref_err}")
                            break
                        time.sleep(1)
                    except Exception as net_err:
                        last_err = net_err
                        logger.debug(f"Network error refreshing token (attempt {attempt + 1}/3): {net_err}")
                        time.sleep(1)

                if refresh_succeeded:
                    return creds

                if not permanent_failure:
                    # Token is NOT revoked; network or Google service was just temporarily unreachable
                    logger.warning(f"YouTube token refresh failed due to temporary network connectivity issue: {last_err}")
                    raise ConnectionError(f"Temporary network issue refreshing YouTube token: {last_err}. Will retry when connection resumes.")

                creds = None

            if not creds:
                if not self.client_secret_file.exists():
                    raise FileNotFoundError(
                        f"\n{'='*70}\n"
                        f"❌ MISSING CLIENT SECRET FILE: {self.client_secret_file.resolve()}\n\n"
                        f"To authenticate YouTube OAuth 2.0:\n"
                        f"1. Open https://console.cloud.google.com/\n"
                        f"2. Enable 'YouTube Data API v3' in APIs & Services > Library\n"
                        f"3. In 'OAuth consent screen', set User Type to External and add your Gmail to 'Test users'\n"
                        f"4. In 'Credentials', click 'Create Credentials' > 'OAuth client ID'\n"
                        f"   ⚠️ Application type MUST be 'Desktop App' (NOT Web application)\n"
                        f"5. Download the JSON file and save it as:\n"
                        f"   {self.client_secret_file.resolve()}\n"
                        f"{'='*70}\n"
                    )

                is_tty = bool(sys.stdin and sys.stdin.isatty())
                if not is_tty or os.environ.get("NON_INTERACTIVE") == "1":
                    logger.warning("⚠️ Non-interactive daemon environment detected. Skipping interactive YouTube OAuth flow to prevent hang.")
                    try:
                        from growth.notifier import notifier
                        notifier.send(
                            "⚠️ YouTube Login Required",
                            "YouTube OAuth token expired. Please open a terminal and run: python3 upload_to_youtube.py",
                            urgency="normal",
                            timeout_ms=10000,
                        )
                    except Exception:
                        pass
                    raise RuntimeError("YouTube OAuth requires interactive user authorization in a terminal. Run 'python3 upload_to_youtube.py'.")

                logger.info("Initiating YouTube OAuth2 browser authentication flow...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secret_file), SCOPES
                )
                
                # Use offline access and prompt=consent to ensure a permanent refresh_token
                try:
                    creds = flow.run_local_server(
                        port=8080,
                        prompt="consent",
                        access_type="offline",
                        open_browser=True,
                    )
                except Exception:
                    # Fallback to random dynamic port if 8080 is in use
                    creds = flow.run_local_server(
                        port=0,
                        prompt="consent",
                        access_type="offline",
                        open_browser=True,
                    )

            # Save credentials for future unattended runs
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, "w") as token_out:
                token_out.write(creds.to_json())
            logger.info(f"✅ YouTube OAuth2 credentials successfully saved to: {self.token_file.resolve()}")

        return creds

    def verify_channel(self) -> dict:
        """Verifies authentication and returns channel title and subscriber count."""
        from googleapiclient.discovery import build
        creds = self.get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
        response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
        items = response.get("items", [])
        if not items:
            raise RuntimeError("No YouTube channel found for the authenticated Google account.")
        ch = items[0]
        return {
            "title": ch["snippet"]["title"],
            "custom_url": ch["snippet"].get("customUrl", ""),
            "subscribers": ch["statistics"].get("subscriberCount", "0"),
            "videos": ch["statistics"].get("videoCount", "0"),
        }

