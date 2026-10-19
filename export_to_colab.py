#!/usr/bin/env python3
"""
Google Colab Packaging & Deployment Tool
=========================================
Exports a clean, lightweight zip package of the YouTube Agent repository
that can be uploaded directly to Google Colab or Google Drive.
"""

import os
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_ZIP = BASE_DIR / "youtube_agent_colab_package.zip"

EXCLUDE_DIRS = {
    ".venv", "venv", ".git", "__pycache__", "output", "build", "dist",
    ".tempmediaStorage", ".pytest_cache", "browser_profiles", "cache2", "storage",
    "assets", "Story", "pending_social"
}
EXCLUDE_EXTENSIONS = {
    ".pyc", ".mp4", ".wav", ".mp3", ".zip", ".log", ".sqlite", ".sqlite-wal", ".sqlite-shm"
}
SENSITIVE_FILES = {
    ".env", "token.json", "client_secret.json", "social_credentials.json"
}

def create_colab_package(include_secrets: bool = False):
    print("=" * 60)
    print("📦 Packaging YouTube Agent for Google Colab...")
    print("=" * 60)
    
    file_count = 0
    total_size = 0
    
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BASE_DIR):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
            
            for file in files:
                file_path = Path(root) / file
                rel_path = file_path.relative_to(BASE_DIR)
                
                # Check sensitive files
                if file in SENSITIVE_FILES and not include_secrets:
                    continue
                
                # Check extensions
                if file_path.suffix.lower() in EXCLUDE_EXTENSIONS:
                    continue
                
                # Exclude output zip itself
                if file_path.name == OUTPUT_ZIP.name:
                    continue
                
                zf.write(file_path, rel_path)
                file_count += 1
                total_size += file_path.stat().st_size

    size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"✅ Successfully created {OUTPUT_ZIP.name}")
    print(f"   • Total Files Packaged: {file_count}")
    print(f"   • Archive Size        : {size_mb:.2f} MB")
    print("\n🚀 Ready for Google Colab:")
    print("1. Open Google Colab (https://colab.research.google.com)")
    print("2. Upload 'YouTube_Agent_Colab.ipynb' or drag-and-drop this zip!")
    print("=" * 60)

if __name__ == "__main__":
    create_colab_package()
