"""TCP port checks: is a service actually listening, not just the host up?"""

from __future__ import annotations

import socket
import time

from . import CheckResult

COMMON_SERVICES = {
    22: "SSH",
    53: "DNS",
    80: "HTTP",
    443: "HTTPS",
    3389: "RDP",
    8096: "Jellyfin",
    51820: "WireGuard",
}


def port_label(port: int) -> str:
    service = COMMON_SERVICES.get(port)
    return f"port {port} ({service})" if service else f"port {port}"


def check_port(name: str, host: str, port: int, timeout_ms: int = 1000) -> CheckResult:
    """Try a TCP connection to host:port and time it."""
    label = port_label(port)
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_ms / 1000):
            latency = (time.perf_counter() - start) * 1000
            return CheckResult(name, label, True, latency_ms=round(latency, 1), detail="open")
    except socket.timeout:
        return CheckResult(name, label, False, detail="timed out")
    except ConnectionRefusedError:
        return CheckResult(name, label, False, detail="refused")
    except socket.gaierror:
        return CheckResult(name, label, False, detail="hostname did not resolve")
    except OSError as exc:
        return CheckResult(name, label, False, detail=exc.strerror or str(exc))
