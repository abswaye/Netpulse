"""Individual network checks. Each returns a CheckResult."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CheckResult:
    target: str          # device or check name
    check: str           # "ping", "port 443", "dns A example.com"
    ok: bool
    latency_ms: float | None = None
    detail: str = ""
