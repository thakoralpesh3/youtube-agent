#!/usr/bin/env python3
"""
YouTube Stuck Processing Cleaner & Channel Health Auditor
=========================================================
Inspects your YouTube channel for videos stuck in:
  - "Processing will begin shortly"
  - "Processing abandoned"
  - Orphaned drafts with 0 views whose live Shorts counterparts already exist

Automatically purges the stuck ghost uploads to keep your YouTube Studio clean.
"""

import sys
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from youtube.auth import YouTubeAuth
from youtube.uploader import YouTubeUploader
from youtube.upload_healer import YouTubeUploadHealer


def main():
    print("=" * 65)
    print("🛡️  YOUTUBE STUCK VIDEO PROCESSING CLEANER & AUDITOR")
    print("=" * 65)

    auth = YouTubeAuth()
    if not auth.has_credentials():
        print("❌ No YouTube credentials found. Please authenticate first.")
        sys.exit(1)

    uploader = YouTubeUploader(auth=auth)
    healer = YouTubeUploadHealer(uploader=uploader)

    print("\n🔍 Scanning channel uploads for stuck processing videos...")
    res = healer.clean_stuck_ghost_videos(max_check=50)

    deleted = res.get("deleted", [])
    if deleted:
        print(f"\n🎉 Cleaned {len(deleted)} stuck ghost video(s) from YouTube:")
        for d in deleted:
            print(f"  • Deleted: '{d['title']}' (ID: {d['id']}, age: {d['age_hours']:.1f}h)")
    else:
        print("\n✨ All videos are healthy! No stuck processing drafts found on your channel.")

    print("\n" + "=" * 65)
    print("✅ Channel audit complete. YouTube Studio is clean!")
    print("=" * 65)


if __name__ == "__main__":
    main()
