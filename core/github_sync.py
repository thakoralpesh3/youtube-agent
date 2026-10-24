#!/usr/bin/env python3
"""
Antigravity to GitHub Automatic Synchronization Engine
======================================================
Monitors, stages, commits, and pushes any codebase modifications or command outputs
directly to GitHub, ensuring the remote repository stays 100% synchronized with Antigravity.

Features:
- Privacy Shield: Prevents accidental staging of .env, tokens, client secrets, or transient media.
- Auto-Commit: Generates meaningful semantic commit messages based on file diffs.
- Autonomous Remote Push: Pushes to origin main with graceful error diagnosis.
- CLI & Library Usage: Can be called from command-line, scripts, or interactive UI.
"""

import argparse
import datetime
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("GitHubSync")

# Critical files that must NEVER be committed to GitHub under any circumstances
BLOCKED_PATTERNS = [
    r"^\.env(\.(local|dev|prod|test|secrets|stage))?$",
    r"^client_secret.*\.json$",
    r"^token.*\.json$",
    r"^token.*\.pickle$",
    r"^social_credentials.*\.json$",
    r"^output/.*",
    r"^Story/(completed|failed|pending)/.*",
    r"^\.security_baseline\.json$",
    r".*\.sqlite(-wal|-shm)?$",
    r".*\.pyc$",
    r".*\.log$",
]


def _run_git_cmd(args: List[str], check: bool = True) -> Tuple[int, str, str]:
    """Runs a git command in the project root directory."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=check,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout.strip(), e.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git binary not found on system PATH"


def is_git_initialized() -> bool:
    """Checks if git repository is initialized in project root."""
    return (PROJECT_ROOT / ".git").is_dir()


def init_repository(branch: str = "main") -> bool:
    """Initializes git repository if not already present."""
    if is_git_initialized():
        return True

    logger.info("Initializing new Git repository in project root...")
    code, out, err = _run_git_cmd(["init", "-b", branch])
    if code != 0:
        logger.error(f"Failed to initialize git repository: {err}")
        return False

    # Set local user identity if global not configured
    _run_git_cmd(["config", "user.name", "Alpesh"])
    _run_git_cmd(["config", "user.email", "alpesh@example.com"])
    logger.info(f"✅ Git repository initialized on branch '{branch}'.")
    return True


def get_git_status() -> Dict[str, List[str]]:
    """Retrieves list of modified, added, deleted, and untracked files."""
    code, out, err = _run_git_cmd(["status", "--porcelain"])
    status = {"modified": [], "added": [], "deleted": [], "untracked": []}
    if code != 0 or not out:
        return status

    for line in out.splitlines():
        if len(line) < 3:
            continue
        code_xy = line[:2]
        file_path = line[3:].strip()
        if " -> " in file_path:
            file_path = file_path.split(" -> ")[1].strip()

        # Check safety blocklist
        is_blocked = False
        for pattern in BLOCKED_PATTERNS:
            if re.match(pattern, file_path):
                is_blocked = True
                break
        if is_blocked:
            continue

        if code_xy[0] == "M" or code_xy[1] == "M":
            status["modified"].append(file_path)
        elif code_xy[0] == "A":
            status["added"].append(file_path)
        elif code_xy[0] == "D" or code_xy[1] == "D":
            status["deleted"].append(file_path)
        elif code_xy == "??":
            status["untracked"].append(file_path)

    return status


def generate_commit_message(status: Dict[str, List[str]], custom_msg: Optional[str] = None) -> str:
    """Generates a concise, informative semantic commit message."""
    if custom_msg and custom_msg.strip():
        return custom_msg.strip()

    total_changes = len(status["modified"]) + len(status["added"]) + len(status["deleted"]) + len(status["untracked"])
    if total_changes == 0:
        return "chore: synchronization update from Antigravity"

    # Summarize key components
    components = set()
    all_files = status["modified"] + status["added"] + status["untracked"] + status["deleted"]
    for f in all_files:
        top_part = f.split("/")[0]
        components.add(top_part)

    comp_str = ", ".join(sorted(list(components))[:3])
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"feat({comp_str}): sync changes from Antigravity ({now_str})"


def get_remote_info() -> Dict[str, str]:
    """Inspects configured git remotes."""
    code, out, err = _run_git_cmd(["remote", "-v"], check=False)
    remotes = {}
    if code == 0 and out:
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                remotes[parts[0]] = parts[1]
    return remotes


def set_remote_url(remote_url: str, remote_name: str = "origin") -> bool:
    """Configures or updates remote URL."""
    remotes = get_remote_info()
    if remote_name in remotes:
        code, _, err = _run_git_cmd(["remote", "set-url", remote_name, remote_url])
    else:
        code, _, err = _run_git_cmd(["remote", "add", remote_name, remote_url])
    
    if code == 0:
        logger.info(f"✅ Git remote '{remote_name}' set to: {remote_url}")
        return True
    logger.error(f"Failed to set git remote: {err}")
    return False


def sync_to_github(
    message: Optional[str] = None,
    remote: str = "origin",
    branch: str = "main",
    push: bool = True,
) -> Dict[str, any]:
    """
    Executes complete synchronization:
    1. Checks repository initialization
    2. Validates safety & adds changed files
    3. Commits with descriptive message
    4. Pushes to remote repository on GitHub
    """
    if not is_git_initialized():
        init_repository(branch=branch)

    # 1. Inspect status
    status = get_git_status()
    total_changes = len(status["modified"]) + len(status["added"]) + len(status["deleted"]) + len(status["untracked"])

    if total_changes == 0:
        logger.info("✨ Working tree clean. No changes to commit.")
        # If there are unpushed commits, try pushing
        if push:
            code, out, err = _run_git_cmd(["push", remote, branch], check=False)
            if code == 0:
                logger.info("✅ All commits are up to date on GitHub.")
                return {"status": "UP_TO_DATE", "pushed": True}
        return {"status": "CLEAN", "pushed": False}

    logger.info(f"📝 Found {total_changes} change(s): {len(status['modified'])} mod, {len(status['added']) + len(status['untracked'])} new, {len(status['deleted'])} del.")

    # 2. Stage changes (respecting .gitignore and safety check)
    code, out, err = _run_git_cmd(["add", "-A"])
    if code != 0:
        logger.error(f"Failed to stage files: {err}")
        return {"status": "ERROR", "error": err}

    # Double check staged files against safety blocklist
    code, staged_out, _ = _run_git_cmd(["diff", "--name-only", "--cached"])
    for f in staged_out.splitlines():
        for pat in BLOCKED_PATTERNS:
            if re.match(pat, f):
                logger.warning(f"🛡️ Safety Shield: Unstaging blocked file: {f}")
                _run_git_cmd(["reset", "HEAD", f])

    # 3. Commit
    commit_msg = generate_commit_message(status, custom_msg=message)
    code, commit_out, commit_err = _run_git_cmd(["commit", "-m", commit_msg])
    if code != 0:
        if "nothing to commit" in commit_out or "nothing to commit" in commit_err:
            logger.info("✨ No changes to commit after safety filtering.")
            return {"status": "CLEAN", "pushed": False}
        logger.error(f"Commit failed: {commit_err}")
        return {"status": "ERROR", "error": commit_err}

    logger.info(f"✅ Committed: '{commit_msg}'")

    # 4. Push to GitHub
    if push:
        remotes = get_remote_info()
        if remote not in remotes:
            logger.warning(f"⚠️ Git remote '{remote}' is not configured yet. Commit saved locally.")
            logger.info(f"👉 Set remote using: python3 core/github_sync.py --set-remote <GITHUB_REPO_URL>")
            return {
                "status": "COMMITTED_LOCAL_ONLY",
                "message": commit_msg,
                "remote_needed": True,
            }

        logger.info(f"🚀 Pushing commits to GitHub ({remote}/{branch})...")
        code, push_out, push_err = _run_git_cmd(["push", "-u", remote, branch], check=False)
        if code != 0:
            logger.info("🔄 Push notice received. Attempting automatic rebase with remote...")
            pull_code, _, pull_err = _run_git_cmd(["pull", "--rebase", remote, branch], check=False)
            if pull_code == 0:
                logger.info("✅ Rebased cleanly. Retrying push...")
                code, push_out, push_err = _run_git_cmd(["push", "-u", remote, branch], check=False)

        if code == 0:
            logger.info("🎉 SUCCESS! All changes pushed to GitHub.")
            return {
                "status": "PUSHED",
                "message": commit_msg,
                "remote": remotes.get(remote),
                "branch": branch,
            }
        else:
            logger.warning(f"⚠️ Push notice ({push_err}). Check authentication or branch status.")
            return {
                "status": "COMMITTED_PUSH_DEFERRED",
                "message": commit_msg,
                "error": push_err,
            }

    return {"status": "COMMITTED", "message": commit_msg}


def sync_secrets_to_github() -> Dict[str, Any]:
    """Syncs GEMINI_API_KEY, client_secret.json, and token.json to GitHub repository secrets."""
    remotes = get_remote_info()
    repo_url = remotes.get("origin", "")
    match = re.search(r"github\.com[:/]([^/]+/[^/.]+)", repo_url)
    if not match:
        return {"status": "ERROR", "error": "Could not determine GitHub repository from remote URL."}
    repo_slug = match.group(1).removesuffix(".git")

    synced = []
    # 1. GEMINI_API_KEY
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key and (PROJECT_ROOT / ".env").exists():
        for line in (PROJECT_ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                gemini_key = line.split("=", 1)[1].strip()
                break
    if gemini_key:
        proc = subprocess.run(["gh", "secret", "set", "GEMINI_API_KEY", "-b", gemini_key, "-R", repo_slug], capture_output=True, text=True)
        if proc.returncode == 0:
            synced.append("GEMINI_API_KEY")

    # 2. YOUTUBE_CLIENT_SECRET_JSON
    cs_file = PROJECT_ROOT / "client_secret.json"
    if cs_file.exists():
        proc = subprocess.run(["gh", "secret", "set", "YOUTUBE_CLIENT_SECRET_JSON", "-R", repo_slug], input=cs_file.read_text(encoding="utf-8"), text=True, capture_output=True)
        if proc.returncode == 0:
            synced.append("YOUTUBE_CLIENT_SECRET_JSON")

    # 3. YOUTUBE_TOKEN_JSON
    tk_file = PROJECT_ROOT / "token.json"
    if tk_file.exists():
        proc = subprocess.run(["gh", "secret", "set", "YOUTUBE_TOKEN_JSON", "-R", repo_slug], input=tk_file.read_text(encoding="utf-8"), text=True, capture_output=True)
        if proc.returncode == 0:
            synced.append("YOUTUBE_TOKEN_JSON")

    # 4. SOCIAL_CREDENTIALS_JSON
    soc_file = PROJECT_ROOT / "social_credentials.json"
    if soc_file.exists():
        proc = subprocess.run(["gh", "secret", "set", "SOCIAL_CREDENTIALS_JSON", "-R", repo_slug], input=soc_file.read_text(encoding="utf-8"), text=True, capture_output=True)
        if proc.returncode == 0:
            synced.append("SOCIAL_CREDENTIALS_JSON")

    return {"status": "SUCCESS", "synced": synced, "repo": repo_slug}


def main():
    parser = argparse.ArgumentParser(description="Antigravity to GitHub Synchronization Tool")
    parser.add_argument("-m", "--message", type=str, default=None, help="Commit message")
    parser.add_argument("--set-remote", type=str, default=None, help="Set GitHub remote repository URL")
    parser.add_argument("--status", action="store_true", help="Display git status and remote configuration")
    parser.add_argument("--watch", action="store_true", help="Start real-time background auto-sync watcher")
    parser.add_argument("--sync-secrets", action="store_true", help="Sync local credentials to GitHub repository secrets")
    parser.add_argument("--no-push", action="store_true", help="Commit locally without pushing to GitHub")
    parser.add_argument("--branch", type=str, default="main", help="Git branch (default: main)")
    parser.add_argument("--remote", type=str, default="origin", help="Git remote name (default: origin)")

    args = parser.parse_args()

    if args.watch:
        from core.github_watcher import GitHubAutoSyncWatcher
        import time
        print("\n" + "=" * 60)
        print("🤖 ANTIGRAVITY REAL-TIME GITHUB AUTO-SYNC WATCHER")
        print("=" * 60)
        print("Monitoring repository for Antigravity changes...")
        print("Press Ctrl+C to exit.\n")
        w = GitHubAutoSyncWatcher(debounce_seconds=15, poll_interval=5)
        t = w.start(daemon=False)
        try:
            while t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping auto-sync watcher...")
            w.stop()
        return

    if args.set_remote:
        if not is_git_initialized():
            init_repository(branch=args.branch)
        set_remote_url(args.set_remote, remote_name=args.remote)
    if args.sync_secrets:
        print("\n" + "=" * 60)
        print("🔐 SYNCING LOCAL SECRETS TO GITHUB REPOSITORY SECRETS")
        print("=" * 60)
        res = sync_secrets_to_github()
        if res.get("status") == "SUCCESS":
            print(f"✅ Repository : {res.get('repo')}")
            for s in res.get("synced", []):
                print(f"  ✓ Secret updated: {s}")
        else:
            print(f"❌ Error: {res.get('error')}")
        print("=" * 60 + "\n")
        return

    if args.status:
        init_repository(branch=args.branch)
        remotes = get_remote_info()
        st = get_git_status()
        print("\n" + "=" * 60)
        print("🌐 GITHUB REPOSITORY SYNCHRONIZATION STATUS")
        print("=" * 60)
        print(f"📁 Repository Path : {PROJECT_ROOT}")
        print(f"🌿 Current Branch  : {args.branch}")
        print(f"🔗 Configured Remotes:")
        if remotes:
            for k, v in remotes.items():
                print(f"   • {k}: {v}")
        else:
            print("   • No remote configured yet (use --set-remote <URL>)")
        
        print("\n📋 Pending Changes:")
        print(f"   • Modified  : {len(st['modified'])}")
        print(f"   • New/Added : {len(st['added']) + len(st['untracked'])}")
        print(f"   • Deleted   : {len(st['deleted'])}")
        if st["modified"]:
            for f in st["modified"][:5]:
                print(f"     ~ {f}")
        if st["untracked"]:
            for f in st["untracked"][:5]:
                print(f"     + {f}")
        print("=" * 60 + "\n")
        return

    res = sync_to_github(
        message=args.message,
        remote=args.remote,
        branch=args.branch,
        push=not args.no_push,
    )
    print(f"Sync result: {res['status']}")


if __name__ == "__main__":
    main()
