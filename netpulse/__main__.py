"""Command-line entry point: python -m netpulse"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime

from rich.console import Console
from rich.table import Table

from . import __version__
from .checks import CheckResult
from .config import ConfigError, load_config
from .runner import run_checks

EXIT_OK, EXIT_FAILURES, EXIT_CONFIG = 0, 1, 2


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
        status = "[green]UP[/green]" if r.ok else "[bold red]DOWN[/bold red]"
        if r.check.startswith("dns"):
            status = "[green]OK[/green]" if r.ok else "[bold red]FAIL[/bold red]"
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="netpulse",
        description="Check device availability, open ports and DNS health on your network.",
    )
    parser.add_argument("-c", "--config", default="devices.yaml", help="path to config file (default: devices.yaml)")
    parser.add_argument("--json", action="store_true", help="print results as JSON instead of a table")
    parser.add_argument("--version", action="version", version=f"netpulse {__version__}")
    args = parser.parse_args(argv)

    console = Console()
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        console.print(f"[bold red]Config error:[/bold red] {exc}")
        return EXIT_CONFIG

    results = run_checks(config)

    if args.json:
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "results": [asdict(r) for r in results],
        }
        print(json.dumps(payload, indent=2))
    else:
        types = {d.name: d.type for d in config.devices}
        render_table(results, types, console)

    return EXIT_OK if all(r.ok for r in results) else EXIT_FAILURES


if __name__ == "__main__":
    sys.exit(main())
