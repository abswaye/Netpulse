"""ICMP availability check using the system ping command.

Using the operating system's ping means NetPulse works on Windows, macOS
and Linux without administrator rights (raw ICMP sockets usually need them).
"""

from __future__ import annotations

import platform
import re
import subprocess

from . import CheckResult

# Matches "time=12ms", "time=12.3 ms", "time<1ms", "Zeit=4ms" style output.
_LATENCY_RE = re.compile(r"(?:time|zeit|temps|tiempo)[=<]\s*([\d.,]+)\s*ms", re.IGNORECASE)


def build_ping_command(host: str, timeout_ms: int, system: str | None = None) -> list[str]:
    """Return the ping command for one echo request on this OS."""
    system = (system or platform.system()).lower()
    if system == "windows":
        return ["ping", "-n", "1", "-w", str(timeout_ms), host]
    if system == "darwin":
        # macOS: -W is in milliseconds
        return ["ping", "-c", "1", "-W", str(timeout_ms), host]
    # Linux: -W is in whole seconds
    seconds = max(1, round(timeout_ms / 1000))
    return ["ping", "-c", "1", "-W", str(seconds), host]


def parse_ping_output(output: str, returncode: int, system: str | None = None) -> tuple[bool, float | None]:
    """Decide whether a ping succeeded and extract its latency.

    On Windows, ping can return exit code 0 for "Destination host
    unreachable", so a reply line containing TTL is also required.
    """
    system = (system or platform.system()).lower()
    match = _LATENCY_RE.search(output)
    latency = float(match.group(1).replace(",", ".")) if match else None

    if system == "windows":
        ok = returncode == 0 and "ttl=" in output.lower()
    else:
        ok = returncode == 0

    return ok, latency if ok else None


def ping(name: str, host: str, timeout_ms: int = 1000) -> CheckResult:
    """Ping a host once and report reachability and round-trip time."""
    cmd = build_ping_command(host, timeout_ms)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000 + 5,
        )
    except FileNotFoundError:
        return CheckResult(name, "ping", False, detail="ping command not found on this system")
    except subprocess.TimeoutExpired:
        return CheckResult(name, "ping", False, detail="ping timed out")

    ok, latency = parse_ping_output(proc.stdout + proc.stderr, proc.returncode)
    detail = "reachable" if ok else "no reply"
    return CheckResult(name, "ping", ok, latency_ms=latency, detail=detail)
