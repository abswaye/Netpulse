"""Run every configured check in parallel and collect the results."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .checks import CheckResult
from .checks.arp import check_arp
from .checks.dns import check_dns
from .checks.ping import ping
from .checks.ports import check_port
from .config import Config


def run_checks(config: Config, max_workers: int = 16) -> list[CheckResult]:
    """Run ping, port and DNS checks concurrently; keep config order in the output."""
    s = config.settings
    jobs = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for d in config.devices:
            reach = check_arp if d.method == "arp" else ping
            jobs.append(pool.submit(reach, d.name, d.host, s.ping_timeout_ms))
            for port in d.ports:
                jobs.append(pool.submit(check_port, d.name, d.host, port, s.port_timeout_ms))
        for c in config.dns_checks:
            jobs.append(
                pool.submit(check_dns, c.name, c.server, c.query, c.record_type, c.expect, s.dns_timeout_ms)
            )
        return [job.result() for job in jobs]
