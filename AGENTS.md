# Antigravity Agent Workspace Guidelines & Automation Rules

## 🌐 1. Mandatory GitHub Autonomous Synchronization
Whenever Antigravity creates, modifies, or refactors any files in this repository:
1. **Always Synchronize to GitHub**:
   Before concluding any turn or task that modified code, documentation, or workflows, you MUST run:
   ```bash
   python3 core/github_sync.py -m "<concise descriptive message>"
   ```
   and verify that the changes are cleanly pushed to `origin/main`.
2. **Secret & Credential Synchronization**:
   If `token.json`, `client_secret.json`, `social_credentials.json`, or `.env` are created, updated, or re-authenticated, synchronize them to GitHub repository secrets:
   ```bash
   python3 core/github_sync.py --sync-secrets
   ```
3. **Safety Shield**:
   Never bypass or commit sensitive files (`.env`, `token.json`, `client_secret.json`, `social_credentials.json`, `output/run_*`, `*.log`). The `core/github_sync.py` script automatically enforces this blocklist.

---

## ☁️ 2. Dual-Execution Architecture
This agent is built to run seamlessly in two complementary modes:
- **Local Daemon (Laptop)**:
  - Managed by systemd user service `youtube-agent.service` running `autostart.sh` / `scheduler.py`.
  - Runs 24/7 in the background with local browser automation, folder monitoring (`Story/`), and local video rendering.
  - Automatically runs the `GitHubAutoSyncWatcher` in the background to detect and push changes.
- **Cloud Runner (GitHub Actions)**:
  - Workflows:
    - [`.github/workflows/daily_youtube_agent.yml`](.github/workflows/daily_youtube_agent.yml) (09:00 AM IST daily)
    - [`.github/workflows/daily_social_agent.yml`](.github/workflows/daily_social_agent.yml) (11:30 PM IST daily)
  - Runs autonomously on GitHub cloud runners with zero local computer dependency.
  - Can be triggered manually on demand via GitHub Actions `workflow_dispatch`.

---

## 🛠️ 3. Development Guidelines
- Always preserve comments, docstrings, and error handling.
- When creating video generation features, support both Trilingual Shorts (EN, HI, GU) and 16:9 Landscape masterclass videos.
- Test changes using `.venv/bin/python3`.
