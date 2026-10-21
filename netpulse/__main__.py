"""Command-line entry point: python -m netpulse"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import __version__
from .alerts import TEST_CHECK, configured_channels, describe, send_alerts
from .checks import CheckResult
from .config import Config, ConfigError, load_config
from .runner import run_checks
from .storage import Change, History

EXIT_OK, EXIT_FAILURES, EXIT_CONFIG = 0, 1, 2
log = logging.getLogger("netpulse")


def setup_logging(path: str) -> None:
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def status_word(r: CheckResult) -> str:
    if r.check.startswith("dns"):
        return "OK" if r.ok else "FAIL"
    return "UP" if r.ok else "DOWN"


def render_table(results: list[CheckResult], types: dict[str, str], console: Console) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    table = Table(title=f"NetPulse check run  [dim]{stamp}[/dim]", title_justify="left")
    table.add_column("Target", style="bold")
    table.add_column("Type", style="dim")
    table.add_column("Check")
    table.add_column("Status", justify="center")
    table.add_column("Latency", justify="right")
    table.add_column("Detail", overflow="fold")

    last = None
    for r in results:
        word = status_word(r)
        status = f"[green]{word}[/green]" if r.ok else f"[bold red]{word}[/bold red]"
        latency = f"{r.latency_ms:g} ms" if r.latency_ms is not None else "-"
        name = r.target if r.target != last else ""
        table.add_row(name, types.get(r.target, "dns") if name else "", r.check, status, latency, r.detail)
        last = r.target
    console.print(table)

    failed = [r for r in results if not r.ok]
    if failed:
        console.print(f"[bold red]{len(failed)} of {len(results)} checks failed[/bold red]")
    else:
        console.print(f"[green]All {len(results)} checks passed[/green]")


def render_changes(changes: list[Change], sent: list[str], console: Console, alerts_on: bool) -> None:
    for c in changes:
        title, body = describe(c)
        colour = "green" if c.result.ok else "red"
        console.print(f"[bold {colour}]{title}[/bold {colour}]  {body}")
    if changes and alerts_on:
        console.print(f"[dim]alerts sent via: {', '.join(sent) if sent else 'none (no channel configured)'}[/dim]")


def render_report(history: History, hours: float, console: Console) -> None:
    rows = history.uptime(hours)
    if not rows:
        console.print("No history yet. Run a check first: python -m netpulse")
        return
    table = Table(title=f"NetPulse uptime, last {hours:g} hours", title_justify="left")
    table.add_column("Target", style="bold")
    table.add_column("Check")
    table.add_column("Uptime", justify="right")
    table.add_column("Checks", justify="right")
    table.add_column("Avg latency", justify="right")
    table.add_column("Now", justify="center")
    for row in rows:
        pct = row.uptime_pct
        colour = "green" if pct >= 99 else "yellow" if pct >= 90 else "red"
        now = "[green]OK[/green]" if row.current_ok else "[bold red]FAIL[/bold red]"
        avg = f"{row.avg_latency_ms:g} ms" if row.avg_latency_ms is not None else "-"
        table.add_row(row.target, row.check, f"[{colour}]{pct:.1f}%[/{colour}]", str(row.total), avg, now)
    console.print(table)


def run_once(config: Config, history: History, console: Console, args) -> list[CheckResult]:
    results = run_checks(config)
    for r in results:
        log.info("%-16s %-24s %-4s %s", r.target, r.check, status_word(r), r.detail)

    changes = history.record(results)
    for c in changes:
        log.warning("%s - %s", *describe(c))

    sent = []
    if changes and not args.no_alerts:
        sent = send_alerts(changes)

    if args.json:
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "results": [asdict(r) for r in results],
            "changes": [describe(c)[0] for c in changes],
        }
        print(json.dumps(payload, indent=2))
    else:
        render_table(results, {d.name: d.type for d in config.devices}, console)
        render_changes(changes, sent, console, alerts_on=not args.no_alerts)
    return results


def send_test_alert(console: Console) -> int:
    channels = configured_channels()
    if not channels:
        console.print("[bold red]No alert channel configured.[/bold red] Set DISCORD_WEBHOOK_URL in your .env file.")
        return EXIT_CONFIG
    sample = Change(CheckResult("netpulse", TEST_CHECK, True, detail="test"), False, datetime.now())
    sent = send_alerts([sample])
    for channel in channels:
        ok = channel in sent
        console.print(f"{channel}: " + ("[green]sent[/green]" if ok else "[bold red]failed (see netpulse.log)[/bold red]"))
    return EXIT_OK if len(sent) == len(channels) else EXIT_FAILURES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="netpulse",
        description="Check device availability, open ports and DNS health, and alert when something changes.",
    )
    parser.add_argument("-c", "--config", default="devices.yaml", help="path to config file (default: devices.yaml)")
    parser.add_argument("-w", "--watch", action="store_true", help="keep running, checking every interval_seconds")
    parser.add_argument("--report", nargs="?", const=24, type=float, metavar="HOURS",
                        help="show uptime per check from history (default: last 24 hours)")
    parser.add_argument("--test-alert", action="store_true", help="send a test alert to every configured channel")
    parser.add_argument("--no-alerts", action="store_true", help="record and display results without sending alerts")
    parser.add_argument("--json", action="store_true", help="print results as JSON instead of a table")
    parser.add_argument("--version", action="version", version=f"netpulse {__version__}")
    args = parser.parse_args(argv)

    load_dotenv(Path.cwd() / ".env")  # .env in the folder you run NetPulse from
    console = Console()

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        console.print(f"[bold red]Config error:[/bold red] {exc}")
        return EXIT_CONFIG

    setup_logging(config.settings.log_file)

    if args.test_alert:
        return send_test_alert(console)

    with History(config.settings.history_db) as history:
        if args.report is not None:
            render_report(history, args.report, console)
            return EXIT_OK

        if not args.watch:
            results = run_once(config, history, console, args)
            return EXIT_OK if all(r.ok for r in results) else EXIT_FAILURES

        interval = config.settings.interval_seconds
        channels = configured_channels()
        console.print(
            f"[bold]NetPulse watching[/bold] every {interval}s  "
            f"[dim]alerts: {'off' if args.no_alerts else ', '.join(channels) or 'none configured'}  "
            f"(Ctrl+C to stop)[/dim]"
        )
        log.info("watch started, interval %ss", interval)
        try:
            while True:
                started = time.monotonic()
                run_once(config, history, console, args)
                time.sleep(max(0, interval - (time.monotonic() - started)))
        except KeyboardInterrupt:
            console.print("\nStopped.")
            log.info("watch stopped")
            return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
