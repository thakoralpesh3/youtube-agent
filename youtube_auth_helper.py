#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

CLIENT_SECRET_FILE = Path("/home/alpesh/.agent_credentials_backup/client_secret.json")
BACKUP_TOKEN_FILE = Path("/home/alpesh/.agent_credentials_backup/token.json")
LOCAL_TOKEN_FILE = Path("/home/alpesh/youtube-agent/token.json")

def save_and_sync(creds):
    token_json = creds.to_json()
    BACKUP_TOKEN_FILE.write_text(token_json)
    BACKUP_TOKEN_FILE.chmod(0o600)
    LOCAL_TOKEN_FILE.write_text(token_json)
    print(f"✅ Saved updated token to: {BACKUP_TOKEN_FILE}")
    print(f"✅ Saved updated token to: {LOCAL_TOKEN_FILE}")

    # Verify channel
    try:
        yt = build("youtube", "v3", credentials=creds)
        ch = yt.channels().list(part="snippet,statistics", mine=True).execute()
        item = ch.get("items", [])[0]
        title = item["snippet"]["title"]
        subs = item["statistics"].get("subscriberCount", "0")
        videos = item["statistics"].get("videoCount", "0")
        print(f"\n🎉 Connected YouTube Channel: {title} ({subs} subscribers, {videos} videos)")
    except Exception as e:
        print(f"⚠️ Channel verification notice: {e}")

    # Push to GitHub Secrets
    print("\n☁️ Syncing fresh token to GitHub Actions secret: YOUTUBE_TOKEN_JSON...")
    res = subprocess.run(
        ["gh", "secret", "set", "YOUTUBE_TOKEN_JSON", "-R", "thakoralpesh3/youtube-agent"],
        input=token_json,
        text=True,
        capture_output=True,
    )
    if res.returncode == 0:
        print("🎉 SUCCESS! YOUTUBE_TOKEN_JSON secret updated on GitHub repository!")
        print("YouTube Agent in GitHub Actions is now 100% authenticated for live publishing.")
    else:
        print(f"⚠️ Error updating GitHub secret: {res.stderr}")

def main():
    parser = argparse.ArgumentParser(description="YouTube OAuth Re-authentication & GitHub Secret Sync")
    parser.add_argument("--code", help="Authorization code from redirect URL")
    parser.add_argument("--url", help="Full redirect URL (e.g. http://localhost:8090/?code=...)")
    parser.add_argument("--port", type=int, default=8090, help="Local server port")
    args = parser.parse_args()

    print("=" * 70)
    print("🔑 YOUTUBE OAUTH2 RE-AUTHENTICATION & GITHUB SECRET SYNC")
    print("=" * 70)

    if not CLIENT_SECRET_FILE.exists():
        print(f"❌ Error: client_secret.json not found at {CLIENT_SECRET_FILE}")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_FILE),
        scopes=SCOPES,
        redirect_uri=f"http://localhost:{args.port}/",
    )

    # Mode 1: Code provided directly
    code = args.code
    if not code and args.url:
        parsed = urllib.parse.urlparse(args.url)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]

    if code:
        print(f"🔄 Exchanging authorization code for OAuth tokens...")
        flow.fetch_token(code=code)
        save_and_sync(flow.credentials)
        return

    # Mode 2: Local server flow
    print(f"\n🌐 Starting local OAuth webserver on port {args.port}...")
    print("👉 Please log in and authorize your YouTube channel when the browser opens.\n")
    sys.stdout.flush()
    creds = flow.run_local_server(port=args.port, prompt="consent", access_type="offline")
    save_and_sync(creds)
    print("=" * 70)

if __name__ == "__main__":
    main()
