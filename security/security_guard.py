import datetime
import hashlib
import json
import logging
import os
import re
import shlex
import stat
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

import config

logger = logging.getLogger("SecurityGuard")


class SecurityGuard:
    """
    Autonomous Cybersecurity Sentinel & Anti-Hacker Defense Shield.
    Protects credentials, hardens file permissions, monitors codebase integrity (FIM),
    audits network listening ports, scans for malicious backdoor signatures, and sanitizes input data.
    """

    def __init__(self):
        self.root_dir = config.BASE_DIR
        self.baseline_file = self.root_dir / ".security_baseline.json"
        self.log_file = config.OUTPUT_DIR / "security_audit.log"
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # High-value credentials requiring strict chmod 600 (owner rw only)
        self.secret_files = [
            self.root_dir / ".env",
            self.root_dir / "client_secret.json",
            self.root_dir / "token.json",
            self.root_dir / "social_credentials.json",
            self.baseline_file,
        ]

        # Sensitive directories requiring strict chmod 700 (owner rwx only)
        self.secret_dirs = [
            self.root_dir / "assets" / "browser_profiles",
            self.root_dir / "assets" / "browser_profiles" / "social_firefox",
            config.OUTPUT_DIR,
        ]

    # --------------------------------------------------------------------------
    # 1. PERMISSION VAULT & HARDENING
    # --------------------------------------------------------------------------
    def harden_permissions(self) -> Dict[str, Any]:
        """
        Enforces strict Unix file permissions:
        - chmod 600 (-rw-------) on all credential files (no group/world access)
        - chmod 700 (drwx------) on browser session folders & output
        """
        hardened_files = []
        hardened_dirs = []
        warnings = []

        # 1. Harden secret files
        for f in self.secret_files:
            if f.exists():
                try:
                    current_mode = stat.S_IMODE(os.stat(f).st_mode)
                    target_mode = 0o600
                    if current_mode != target_mode:
                        os.chmod(f, target_mode)
                        hardened_files.append(f"{f.name} (0o{current_mode:o} -> 0o600)")
                        logger.info(f"🔒 [Vault Hardening] Locked permissions on {f.name} to 0600 (Owner Only)")
                except Exception as e:
                    warnings.append(f"Failed to harden {f.name}: {e}")

        # 2. Harden secret directories and all nested sqlite/cookie databases
        for d in self.secret_dirs:
            if d.exists():
                try:
                    current_mode = stat.S_IMODE(os.stat(d).st_mode)
                    if current_mode != 0o700:
                        os.chmod(d, 0o700)
                        hardened_dirs.append(f"{d.name} (0o700)")
                        logger.info(f"🔒 [Vault Hardening] Locked directory {d.name} to 0700 (Owner Only)")

                    # Also secure any sqlite, wal, db, or bin files inside profile
                    for root, dirs, files in os.walk(d):
                        for sub_d in dirs:
                            os.chmod(os.path.join(root, sub_d), 0o700)
                        for file_name in files:
                            if any(file_name.endswith(ext) for ext in [".sqlite", ".sqlite-wal", ".sqlite-shm", ".db", ".json", ".bin"]):
                                file_path = os.path.join(root, file_name)
                                try:
                                    os.chmod(file_path, 0o600)
                                except Exception:
                                    pass
                except Exception as e:
                    warnings.append(f"Failed to harden directory {d.name}: {e}")

        return {
            "status": "HARDENED",
            "hardened_files": hardened_files,
            "hardened_dirs": hardened_dirs,
            "warnings": warnings,
        }

    # --------------------------------------------------------------------------
    # 2. GIT SHIELD & SECRET LEAK PREVENTION
    # --------------------------------------------------------------------------
    def ensure_git_shield(self) -> Dict[str, Any]:
        """
        Verifies that .gitignore exists and contains critical rules
        to prevent accidental check-ins of credentials, tokens, or browser profiles.
        """
        gitignore = self.root_dir / ".gitignore"
        critical_patterns = [
            ".env", "client_secret*.json", "token*.json",
            "social_credentials*.json", "assets/browser_profiles/",
            "*.sqlite", ".security_baseline.json"
        ]

        if not gitignore.exists():
            return {"status": "MISSING", "action_needed": "Generate .gitignore"}

        content = gitignore.read_text(encoding="utf-8")
        missing = [p for p in critical_patterns if p not in content]

        if missing:
            logger.warning(f"⚠️ [Git Shield] .gitignore missing critical patterns: {missing}")
            return {"status": "INCOMPLETE", "missing_patterns": missing}

        return {"status": "PROTECTED", "message": "Git shield is active and blocking all credential leakage."}

    # --------------------------------------------------------------------------
    # 3. CRYPTOGRAPHIC FILE INTEGRITY MONITOR (FIM)
    # --------------------------------------------------------------------------
    def _compute_sha256(self, file_path: Path) -> str:
        """Calculates SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_core_codebase_files(self) -> List[Path]:
        """Returns list of critical scripts monitored for unauthorized tampering."""
        extensions = [".py", ".sh"]
        core_files = []

        # Top-level scripts
        for ext in extensions:
            core_files.extend(list(self.root_dir.glob(f"*{ext}")))

        # Subpackage scripts
        subdirs = ["generator", "growth", "syndication", "youtube", "security"]
        for sub in subdirs:
            p = self.root_dir / sub
            if p.exists():
                for ext in extensions:
                    core_files.extend(list(p.glob(f"*{ext}")))

        # Exclude temporary virtualenv or cache files
        filtered = [
            f for f in core_files 
            if ".venv" not in f.parts and "__pycache__" not in f.parts
        ]
        return sorted(filtered)

    def build_integrity_baseline(self) -> Dict[str, Any]:
        """Generates or updates cryptographic SHA-256 hashes of all codebase scripts."""
        core_files = self.get_core_codebase_files()
        hashes = {}
        for f in core_files:
            rel = f.relative_to(self.root_dir).as_posix()
            hashes[rel] = self._compute_sha256(f)

        data = {
            "created_at": datetime.datetime.now().isoformat(),
            "file_count": len(hashes),
            "hashes": hashes,
        }

        self.baseline_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(self.baseline_file, 0o600)
        except Exception:
            pass

        logger.info(f"🛡️ [Integrity Monitor] Built secure baseline across {len(hashes)} codebase files.")
        return {"status": "BASELINE_CREATED", "file_count": len(hashes)}

    def check_file_integrity(self) -> Dict[str, Any]:
        """
        Compares current file hashes against the trusted baseline.
        Detects unauthorized file modifications, backdoor injections, or deletions.
        """
        if not self.baseline_file.exists():
            return self.build_integrity_baseline()

        try:
            baseline = json.loads(self.baseline_file.read_text(encoding="utf-8"))
            saved_hashes = baseline.get("hashes", {})
        except Exception as e:
            return {"status": "ERROR", "message": f"Could not read baseline: {e}"}

        current_files = self.get_core_codebase_files()
        current_map = {f.relative_to(self.root_dir).as_posix(): f for f in current_files}

        modified = []
        added = []
        deleted = []

        for rel, path in current_map.items():
            if rel not in saved_hashes:
                added.append(rel)
            else:
                curr_hash = self._compute_sha256(path)
                if curr_hash != saved_hashes[rel]:
                    modified.append(rel)

        for rel in saved_hashes:
            if rel not in current_map:
                deleted.append(rel)

        if modified or added or deleted:
            logger.warning(
                f"🚨 [INTEGRITY ALERT] Codebase modifications detected! "
                f"Modified: {modified}, Added: {added}, Deleted: {deleted}"
            )
            return {
                "status": "COMPROMISED",
                "modified": modified,
                "added": added,
                "deleted": deleted,
            }

        return {
            "status": "VERIFIED",
            "message": f"Codebase 100% intact across {len(saved_hashes)} verified scripts.",
            "file_count": len(saved_hashes),
        }

    # --------------------------------------------------------------------------
    # 4. MALICIOUS CODE & BACKDOOR SIGNATURE SCANNER
    # --------------------------------------------------------------------------
    def scan_for_malicious_signatures(self) -> Dict[str, Any]:
        """
        Scans scripts for known attack, backdoor, and remote-shell signatures:
        - Obfuscated base64 execution (eval/exec)
        - Direct bash reverse shells (/dev/tcp, nc -e, pty.spawn)
        - Suspicious piped downloads (curl | sh, wget | bash)
        - Unauthorized crontab entries
        """
        threat_patterns = [
            (r"(?:eval|exec)\s*\(\s*(?:__import__\s*\(\s*['\"]base64['\"]|base64\.b64decode)", "Obfuscated Base64 Execution"),
            (r"/dev/tcp/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "Bash /dev/tcp Reverse Shell"),
            (r"nc\s+.*-e\s+/bin/(?:ba)?sh", "Netcat Reverse Shell"),
            (r"pty\.spawn\s*\(\s*['\"]/bin/(?:ba)?sh", "PTY Shell Spawn Injection"),
            (r"(?:curl|wget)\s+.*\|\s*(?:ba)?sh", "Piped Remote Shell Execution"),
        ]

        flagged = []
        core_files = self.get_core_codebase_files()

        for f in core_files:
            # Skip self to avoid matching the regex definitions themselves
            if f.name == "security_guard.py":
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                for pattern, desc in threat_patterns:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        flagged.append({
                            "file": f.relative_to(self.root_dir).as_posix(),
                            "threat": desc,
                            "match": match.group(0)[:60],
                        })
            except Exception:
                pass

        # Inspect crontabs for unauthorized backdoor jobs
        cron_threats = []
        try:
            cron_out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False).stdout
            for line in cron_out.splitlines():
                line_clean = line.strip()
                if line_clean and not line_clean.startswith("#"):
                    if any(x in line_clean.lower() for x in ["curl", "wget", "/dev/tcp", "nc ", "python -c"]):
                        cron_threats.append(line_clean)
        except Exception:
            pass

        if flagged or cron_threats:
            return {
                "status": "THREAT_DETECTED",
                "code_signatures": flagged,
                "cron_threats": cron_threats,
                "scanned_files": len(core_files),
            }

        return {
            "status": "CLEAN",
            "message": "No malicious backdoor or shell injection patterns detected.",
            "scanned_files": len(core_files),
        }

    # --------------------------------------------------------------------------
    # 5. NETWORK LISTENER & ROGUE PORT SENTINEL
    # --------------------------------------------------------------------------
    def scan_network_listeners(self) -> Dict[str, Any]:
        """
        Inspects active listening TCP/UDP ports on the host.
        Distinguishes between safe localhost-only sockets (127.0.0.1 / ::1)
        and publicly exposed listeners (0.0.0.0 / ::) that could expose the agent to hackers.
        Focuses alerts on exposed TCP listening servers (backdoors, web shells, bind shells).
        """
        public_tcp_listeners = []
        local_listeners = []

        try:
            cmd = ["ss", "-tulpn"]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            output = proc.stdout

            # Known harmless desktop/system services and agent's authorized web control center
            allowed_services = ["systemd-resolve", "avahi-daemon", "cupsd", "uvicorn"]
            web_port = str(getattr(config, "WEB_SERVER_PORT", 8085))

            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    proto = parts[0].lower()
                    local_addr = parts[4]
                    proc_info = parts[6] if len(parts) > 6 else "unknown"

                    # Parse IP and port
                    if ":" in local_addr:
                        ip, port = local_addr.rsplit(":", 1)
                        is_public = ip in ["0.0.0.0", "*", "[::]"]
                        is_local = ip in ["127.0.0.1", "[::1]", "localhost"]

                        entry = {
                            "proto": proto,
                            "port": port,
                            "address": local_addr,
                            "process": proc_info,
                        }

                        # Prioritize TCP listeners which represent listening servers/backdoors
                        if is_public and proto == "tcp":
                            is_authorized_python = (port in [web_port, "8080", "8081"] and "python" in proc_info.lower())
                            if not any(svc in proc_info for svc in allowed_services) and not is_authorized_python:
                                public_tcp_listeners.append(entry)
                        else:
                            local_listeners.append(entry)

        except Exception as e:
            return {"status": "ERROR", "message": f"Port scan notice: {e}"}

        if public_tcp_listeners:
            logger.warning(f"⚠️ [Network Sentinel] Unapproved public TCP listeners detected: {public_tcp_listeners}")
            return {
                "status": "WARNING",
                "public_listeners": public_tcp_listeners,
                "local_listeners_count": len(local_listeners),
            }

        return {
            "status": "SECURE",
            "message": f"Network surface is secured. All {len(local_listeners)} active services bound safely to localhost.",
            "local_listeners_count": len(local_listeners),
        }

    # --------------------------------------------------------------------------
    # 6. INPUT SANITIZATION & INJECTION SHIELD
    # --------------------------------------------------------------------------
    @staticmethod
    def sanitize_file_path(path_str: str, allowed_base: Optional[Path] = None) -> Path:
        """
        Sanitizes a file path to prevent path traversal (e.g. ../../etc/passwd)
        and invalid control characters.
        """
        # Neutralize traversal attempts
        cleaned = re.sub(r"\.\.[/\\]", "", path_str)
        cleaned = re.sub(r"[\x00-\x1f]", "", cleaned)
        p = Path(cleaned)

        if allowed_base:
            resolved_base = allowed_base.resolve()
            resolved_p = (allowed_base / p).resolve()
            if not resolved_p.is_relative_to(resolved_base):
                raise ValueError(f"Path traversal detected: {path_str}")
            return resolved_p

        return p

    @staticmethod
    def sanitize_command_arg(text: str) -> str:
        """Sanitizes text to neutralize shell command injection metacharacters."""
        return re.sub(r"[;&|`$<>\n\r\t]", "", text).strip()

    # --------------------------------------------------------------------------
    # 7. MASTER COMPREHENSIVE SECURITY AUDIT & PULSE
    # --------------------------------------------------------------------------
    def run_security_audit(self, auto_harden: bool = True, alert_on_threat: bool = True) -> Dict[str, Any]:
        """
        Executes complete 5-point cybersecurity defense audit:
        1. Vault Permission Hardening
        2. Git Shield & Credential Protection
        3. Codebase File Integrity Verification (FIM)
        4. Malicious Code & Backdoor Signature Scan
        5. Network Port & Listener Exposure Scan
        """
        logger.info("🛡️ [Cybersecurity Sentinel] Starting master security audit...")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        report = {
            "timestamp": timestamp,
            "overall_status": "SECURE",
            "findings": {},
        }

        # 1. Hardening
        if auto_harden:
            report["findings"]["vault_hardening"] = self.harden_permissions()
        else:
            report["findings"]["vault_hardening"] = {"status": "SKIPPED"}

        # 2. Git Shield
        report["findings"]["git_shield"] = self.ensure_git_shield()

        # 3. File Integrity
        fim_res = self.check_file_integrity()
        report["findings"]["code_integrity"] = fim_res
        if fim_res.get("status") == "COMPROMISED":
            report["overall_status"] = "THREAT_DETECTED"

        # 4. Signature Scan
        sig_res = self.scan_for_malicious_signatures()
        report["findings"]["malware_scan"] = sig_res
        if sig_res.get("status") == "THREAT_DETECTED":
            report["overall_status"] = "THREAT_DETECTED"

        # 5. Network Scan
        net_res = self.scan_network_listeners()
        report["findings"]["network_scan"] = net_res
        if net_res.get("status") == "WARNING" and report["overall_status"] != "THREAT_DETECTED":
            report["overall_status"] = "WARNING"

        # Log audit entry
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"\n[{timestamp}] Security Audit: Status={report['overall_status']}\n")
                f.write(json.dumps(report, indent=2) + "\n")
        except Exception:
            pass

        # Dispatch Desktop Alert if threats are detected
        if report["overall_status"] == "THREAT_DETECTED" and alert_on_threat:
            alert_msg = "Security threat detected! Check output/security_audit.log for details."
            if fim_res.get("status") == "COMPROMISED":
                alert_msg = f"Unauthorized file modifications detected: {', '.join(fim_res.get('modified', []))}"
            elif sig_res.get("status") == "THREAT_DETECTED":
                alert_msg = "Suspicious code signature / backdoor detected in codebase!"

            try:
                subprocess.run([
                    "notify-send",
                    "-a", "Cybersecurity Sentinel",
                    "-u", "critical",
                    "🚨 CYBERSECURITY ALERT!",
                    alert_msg
                ], check=False)
            except Exception:
                pass

        logger.info(f"🛡️ [Cybersecurity Sentinel] Audit finished. Status: {report['overall_status']}")
        return report
