"""Load and validate the NetPulse YAML configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Raised when the config file is missing or invalid."""


@dataclass
class Device:
    name: str
    host: str
    type: str = "device"
    ports: list[int] = field(default_factory=list)


@dataclass
class DnsCheck:
    name: str
    server: str
    query: str
    record_type: str = "A"
    expect: list[str] = field(default_factory=list)


@dataclass
class Settings:
    ping_timeout_ms: int = 1000
    port_timeout_ms: int = 1000
    dns_timeout_ms: int = 2000
    interval_seconds: int = 300
    history_db: str = "netpulse.db"
    log_file: str = "netpulse.log"


@dataclass
class Config:
    settings: Settings
    devices: list[Device]
    dns_checks: list[DnsCheck]


def _require(entry: dict, key: str, where: str) -> str:
    value = entry.get(key)
    if value is None or str(value).strip() == "":
        raise ConfigError(f"{where}: missing required field '{key}'")
    return str(value).strip()


def _parse_ports(raw, where: str) -> list[int]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError(f"{where}: 'ports' must be a list, e.g. [22, 443]")
    ports = []
    for p in raw:
        try:
            port = int(p)
        except (TypeError, ValueError):
            raise ConfigError(f"{where}: invalid port {p!r}") from None
        if not 1 <= port <= 65535:
            raise ConfigError(f"{where}: port {port} is out of range 1-65535")
        ports.append(port)
    return ports


def parse_config(data: dict) -> Config:
    """Build a Config from already-loaded YAML data."""
    if not isinstance(data, dict):
        raise ConfigError("config must be a YAML mapping with 'devices' and/or 'dns_checks'")

    raw_settings = data.get("settings") or {}
    settings = Settings(
        ping_timeout_ms=int(raw_settings.get("ping_timeout_ms", 1000)),
        port_timeout_ms=int(raw_settings.get("port_timeout_ms", 1000)),
        dns_timeout_ms=int(raw_settings.get("dns_timeout_ms", 2000)),
        interval_seconds=int(raw_settings.get("interval_seconds", 300)),
        history_db=str(raw_settings.get("history_db", "netpulse.db")),
        log_file=str(raw_settings.get("log_file", "netpulse.log")),
    )
    if settings.interval_seconds < 10:
        raise ConfigError("settings: 'interval_seconds' must be at least 10")

    devices = []
    seen = set()
    for i, entry in enumerate(data.get("devices") or [], start=1):
        where = f"devices[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: each device must be a mapping")
        name = _require(entry, "name", where)
        if name in seen:
            raise ConfigError(f"{where}: duplicate device name '{name}'")
        seen.add(name)
        devices.append(
            Device(
                name=name,
                host=_require(entry, "host", where),
                type=str(entry.get("type", "device")),
                ports=_parse_ports(entry.get("ports"), where),
            )
        )

    dns_checks = []
    for i, entry in enumerate(data.get("dns_checks") or [], start=1):
        where = f"dns_checks[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: each DNS check must be a mapping")
        expect = entry.get("expect") or []
        if not isinstance(expect, list):
            expect = [expect]
        dns_checks.append(
            DnsCheck(
                name=_require(entry, "name", where),
                server=_require(entry, "server", where),
                query=_require(entry, "query", where),
                record_type=str(entry.get("record_type", "A")).upper(),
                expect=[str(e).strip() for e in expect],
            )
        )

    if not devices and not dns_checks:
        raise ConfigError("config has no 'devices' or 'dns_checks' to monitor")

    return Config(settings=settings, devices=devices, dns_checks=dns_checks)


def load_config(path: str | Path) -> Config:
    """Read a YAML config file from disk."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"config file not found: {path}\n"
            "Copy devices.example.yaml to devices.yaml and add your own devices."
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"could not parse {path}: {exc}") from None
    return parse_config(data)
