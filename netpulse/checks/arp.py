"""Layer 2 reachability check for devices that ignore ping.

Many smart TVs, streaming sticks and IoT devices drop ICMP echo requests,
so ping reports them DOWN even when they're online. Every device on the
local network still has to answer ARP, though, or nothing could talk to it.

This check sends a ping (which makes the OS resolve the device's MAC address
with ARP first), then reads the OS neighbor table. A REACHABLE entry means
the device answered ARP just now, so it's online even if the ping failed.
Only works for devices on the same subnet as the computer running NetPulse.
"""

from __future__ import annotations

import platform
import re
import subprocess

from . import CheckResult
from .ping import ping

# Neighbor states that mean "answered ARP recently".
_ALIVE = {"reachable", "delay", "probe", "permanent"}


def parse_windows_state(output: str) -> str | None:
    """Output of PowerShell (Get-NetNeighbor -IPAddress x).State, one state per line."""
    states = [line.strip().lower() for line in output.splitlines() if line.strip()]
    if not states:
        return None
    alive = [s for s in states if s in _ALIVE]
    return alive[0] if alive else states[0]


def parse_linux_state(output: str) -> str | None:
    """Output of `ip neigh show <ip>`, e.g. '192.168.1.5 dev wlan0 lladdr aa:bb:.. REACHABLE'."""
    match = re.search(r"\b(REACHABLE|STALE|DELAY|PROBE|FAILED|INCOMPLETE|PERMANENT|NOARP)\b", output)
    return match.group(1).lower() if match else None


def parse_macos_state(output: str) -> str | None:
    """Output of `arp -n <ip>`, e.g. '? (192.168.1.5) at aa:bb:cc:dd:ee:ff on en0 ...'."""
    if not output.strip() or "no entry" in output:
        return None
    if "incomplete" in output:
        return "incomplete"
    return "reachable" if re.search(r" at [0-9a-f]{1,2}(:[0-9a-f]{1,2}){5}", output, re.IGNORECASE) else None


def neighbor_state(host: str, system: str | None = None) -> str | None:
    """Ask the OS for the ARP/neighbor state of `host` (lowercase), or None if unknown."""
    system = (system or platform.system()).lower()
    if system == "windows":
        cmd = [
            "powershell", "-NoProfile", "-Command",
            f"(Get-NetNeighbor -IPAddress '{host}' -ErrorAction SilentlyContinue).State",
        ]
        parser = parse_windows_state
    elif system == "darwin":
        cmd, parser = ["arp", "-n", host], parse_macos_state
    else:
        cmd, parser = ["ip", "neigh", "show", host], parse_linux_state
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return parser(proc.stdout)


def check_arp(name: str, host: str, timeout_ms: int = 1000) -> CheckResult:
    """Online if the device answers ping OR answered ARP during the ping attempt."""
    pinged = ping(name, host, timeout_ms)
    if pinged.ok:
        return CheckResult(name, "arp", True, latency_ms=pinged.latency_ms, detail="reachable (ping)")
    state = neighbor_state(host)
    if state in _ALIVE:
        return CheckResult(name, "arp", True, detail="online (answers ARP, blocks ping)")
    return CheckResult(name, "arp", False, detail=f"no ARP reply ({state or 'no entry'})")
