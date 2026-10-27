#!/usr/bin/env python3
import json
import os
import subprocess
import sys
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

print("=" * 70)
print("🔑 YOUTUBE OAUTH2 RE-AUTHENTICATION & GITHUB SECRET SYNC")
print("=" * 70)

if not CLIENT_SECRET_FILE.exists():
    print(f"❌ Error: client_secret.json not found at {CLIENT_SECRET_FILE}")
    sys.exit(1)

flow = InstalledAppFlow.from_client_secrets_file(
    str(CLIENT_SECRET_FILE),
    scopes=SCOPES,
)

print("\n🌐 Starting local OAuth webserver on port 8090...")
print("👉 Please log in and authorize your YouTube channel when the browser opens.\n")

creds = flow.run_local_server(port=8090, prompt="consent", access_type="offline")

# Verify channel connection
try:
    yt = build("youtube", "v3", credentials=creds)
    ch = yt.channels().list(part="snippet,statistics", mine=True).execute()
    item = ch.get("items", [])[0]
    title = item["snippet"]["title"]
    subs = item["statistics"].get("subscriberCount", "0")
    videos = item["statistics"].get("videoCount", "0")
    print(f"\n🎉 Connected YouTube Channel: {title} ({subs} subscribers, {videos} videos)")
except Exception as e:
    print(f"⚠️ Warning: Could not fetch channel stats: {e}")

# Save token locally
token_json = creds.to_json()
BACKUP_TOKEN_FILE.write_text(token_json)
BACKUP_TOKEN_FILE.chmod(0o600)
LOCAL_TOKEN_FILE.write_text(token_json)
print(f"✅ Saved updated token to: {BACKUP_TOKEN_FILE} and {LOCAL_TOKEN_FILE}")

# Sync directly to GitHub repository secrets
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

print("=" * 70)
