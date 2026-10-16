import http.client
import logging
import socket
import ssl
import time
from typing import Any, Callable, Optional
import requests
import urllib3

logger = logging.getLogger(__name__)

NETWORK_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
    urllib3.exceptions.HTTPError,
    urllib3.exceptions.MaxRetryError,
    urllib3.exceptions.ProtocolError,
    socket.gaierror,
    socket.timeout,
    socket.error,
    ConnectionResetError,
    ConnectionRefusedError,
    ConnectionAbortedError,
    TimeoutError,
    http.client.RemoteDisconnected,
    http.client.CannotSendRequest,
    ssl.SSLError,
)


class NetworkGuard:
    """
    Autonomous Network Fault-Tolerance Guard.
    Detects internet outages, enters intelligent reconnection wait loops,
    and automatically resumes execution at the exact point of interruption.
    """

    @staticmethod
    def is_online(timeout: float = 3.0) -> bool:
        """
        Fast multi-host connectivity probe to verify genuine internet access.
        """
        # 1. Fast DNS / socket probe to reliable public DNS
        hosts = [("8.8.8.8", 53), ("1.1.1.1", 53), ("208.67.222.222", 53)]
        for host, port in hosts:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect((host, port))
                s.close()
                return True
            except Exception:
                continue

        # 2. HTTP fallback probe
        try:
            r = requests.get("https://clients3.google.com/generate_204", timeout=timeout)
            return r.status_code == 204
        except Exception:
            pass

        return False

    @staticmethod
    def wait_for_network(callback: Optional[Callable[[str], None]] = None, check_interval: float = 4.0) -> None:
        """
        Blocks execution gracefully when offline and waits for internet connection to be restored.
        """
        if NetworkGuard.is_online():
            return

        logger.warning("⚠️ Internet connection lost! Pipeline paused. Waiting for network reconnection...")
        if callback:
            callback("⚠️ Network connection lost. Waiting for internet to restore...")

        retry_count = 0
        while not NetworkGuard.is_online():
            retry_count += 1
            if callback:
                callback(f"⚠️ Network offline. Reconnect attempt #{retry_count} (checking every {int(check_interval)}s)...")
            time.sleep(check_interval)

        logger.info("🌐 Internet connection successfully restored! Resuming pipeline...")
        if callback:
            callback("🌐 Network connection restored! Resuming pipeline...")
        time.sleep(1)  # Allow network buffers to stabilize

    @staticmethod
    def resilient_call(
        func: Callable[..., Any],
        *args: Any,
        callback: Optional[Callable[[str], None]] = None,
        max_retries: int = 20,
        retry_delay: float = 3.0,
        **kwargs: Any,
    ) -> Any:
        """
        Executes a callable with zero-crash network resilience.
        If a network error occurs, pauses, waits for internet restoration, and retries.
        """
        attempts = 0
        while True:
            try:
                return func(*args, **kwargs)
            except NETWORK_EXCEPTIONS as e:
                attempts += 1
                logger.warning(f"Network error detected during {func.__name__} ({e}). Pausing for reconnection...")
                if callback:
                    callback(f"⚠️ Network error: {e}. Waiting for internet to resume...")

                NetworkGuard.wait_for_network(callback=callback)

                if attempts >= max_retries:
                    logger.error(f"Exceeded max network retries ({max_retries}) for {func.__name__}")
                    raise e

                time.sleep(retry_delay)
            except Exception as e:
                # Check for Google GenAI / API network-like error strings
                err_str = str(e).lower()
                if any(k in err_str for k in ["failed to connect", "connection reset", "name resolution", "temporary failure", "network unreachable"]):
                    attempts += 1
                    logger.warning(f"API network glitch detected ({e}). Waiting for network reconnection...")
                    NetworkGuard.wait_for_network(callback=callback)
                    if attempts >= max_retries:
                        raise e
                    time.sleep(retry_delay)
                else:
                    raise e


_shield_installed = False


def install_network_shield():
    """
    Installs a system-level network shield in Python:
    1. Forces IPv4 to bypass broken/unrouted IPv6 interfaces that cause timeouts.
    2. Transparently falls back to DNS-over-HTTPS (Google/Cloudflare DNS) if local
       DNS sinkholes (e.g. ublockdns) return 0.0.0.0 or fail.
    """
    global _shield_installed
    if _shield_installed:
        return
    _shield_installed = True

    _orig_getaddrinfo = socket.getaddrinfo

    def resilient_getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
        # 1. Force IPv4 and try original resolver
        try:
            results = _orig_getaddrinfo(host, port, socket.AF_INET, socktype, proto, flags)
            v4_results = [r for r in results if r[0] == socket.AF_INET]
            is_local = host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
            if v4_results and (is_local or not any(r[4][0] in ("0.0.0.0", "127.0.0.1") for r in v4_results)):
                return v4_results
        except Exception:
            pass

        # 2. If sinkholed or resolution failed, query DNS-over-HTTPS
        try:
            import urllib.request
            import json
            doh_url = f"https://dns.google/resolve?name={host}&type=A"
            req = urllib.request.Request(doh_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode())
                ips = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1]
                if ips:
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ips[0], port or 0))]
        except Exception:
            pass

        return _orig_getaddrinfo(host, port, socket.AF_INET, socktype, proto, flags)

    socket.getaddrinfo = resilient_getaddrinfo
    logger.debug("🛡️ NetworkGuard resilient IPv4 & DoH shield active.")


# Automatically activate shield whenever network_guard is imported
install_network_shield()
