"""DNS health checks against a specific DNS server.

Each check asks one server for one record and, if expected answers are
configured, flags a mismatch. A mismatch is how NetPulse spots DNS drift:
a record that changed when it should not have.
"""

from __future__ import annotations

import time

import dns.exception
import dns.resolver

from . import CheckResult


def compare_answers(answers: list[str], expect: list[str]) -> tuple[bool, str]:
    """Compare DNS answers with the expected values (order-insensitive)."""
    got = sorted(a.rstrip(".").lower() for a in answers)
    if not expect:
        return True, ", ".join(got) or "no records"
    want = sorted(e.rstrip(".").lower() for e in expect)
    if got == want:
        return True, ", ".join(got)
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    parts = []
    if missing:
        parts.append("missing " + ", ".join(missing))
    if extra:
        parts.append("unexpected " + ", ".join(extra))
    return False, "drift: " + "; ".join(parts)


def check_dns(
    name: str,
    server: str,
    query: str,
    record_type: str = "A",
    expect: list[str] | None = None,
    timeout_ms: int = 2000,
) -> CheckResult:
    """Resolve `query` through `server` and check the answer."""
    label = f"dns {record_type} {query}"
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [server]
    resolver.lifetime = timeout_ms / 1000

    start = time.perf_counter()
    try:
        answer = resolver.resolve(query, record_type)
    except dns.resolver.NXDOMAIN:
        return CheckResult(name, label, False, detail="NXDOMAIN (name does not exist)")
    except dns.resolver.NoAnswer:
        return CheckResult(name, label, False, detail=f"no {record_type} record")
    except dns.resolver.NoNameservers:
        return CheckResult(name, label, False, detail="server refused or failed (SERVFAIL)")
    except dns.exception.Timeout:
        return CheckResult(name, label, False, detail=f"no response from {server}")
    except (dns.exception.DNSException, ValueError) as exc:
        return CheckResult(name, label, False, detail=str(exc))

    latency = round((time.perf_counter() - start) * 1000, 1)
    ok, detail = compare_answers([r.to_text() for r in answer], expect or [])
    return CheckResult(name, label, ok, latency_ms=latency, detail=detail)
