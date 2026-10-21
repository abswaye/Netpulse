"""SQLite history and up/down state tracking.

Every check result is stored so uptime can be reported later. The `state`
table remembers the last known status of each check, so NetPulse can tell
when something *changes* (up to down, down to up) and alert only then,
instead of repeating the same alert every cycle.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .checks import CheckResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    target      TEXT    NOT NULL,
    check_name  TEXT    NOT NULL,
    ok          INTEGER NOT NULL,
    latency_ms  REAL,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS idx_results_ts ON results (ts);
CREATE INDEX IF NOT EXISTS idx_results_key ON results (target, check_name);

CREATE TABLE IF NOT EXISTS state (
    target      TEXT    NOT NULL,
    check_name  TEXT    NOT NULL,
    ok          INTEGER NOT NULL,
    since       TEXT    NOT NULL,
    PRIMARY KEY (target, check_name)
);
"""

TS_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class Change:
    """A check whose status flipped (or that was down the first time it was seen)."""

    result: CheckResult
    previous_ok: bool | None      # None = first time this check was seen
    changed_at: datetime
    down_for: timedelta | None = None  # set on recovery: how long it was down

    @property
    def recovered(self) -> bool:
        return self.result.ok


@dataclass
class UptimeRow:
    target: str
    check: str
    total: int
    passed: int
    avg_latency_ms: float | None
    current_ok: bool

    @property
    def uptime_pct(self) -> float:
        return 100.0 * self.passed / self.total if self.total else 0.0


def format_duration(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


class History:
    def __init__(self, path: str | Path = "netpulse.db"):
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "History":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def record(self, results: list[CheckResult], when: datetime | None = None) -> list[Change]:
        """Store one run of results and return the checks whose status changed."""
        when = when or datetime.now()
        ts = when.strftime(TS_FORMAT)
        changes: list[Change] = []

        with self.conn:  # one transaction per run
            for r in results:
                self.conn.execute(
                    "INSERT INTO results (ts, target, check_name, ok, latency_ms, detail) VALUES (?, ?, ?, ?, ?, ?)",
                    (ts, r.target, r.check, int(r.ok), r.latency_ms, r.detail),
                )
                row = self.conn.execute(
                    "SELECT ok, since FROM state WHERE target = ? AND check_name = ?",
                    (r.target, r.check),
                ).fetchone()

                if row is None:
                    self.conn.execute(
                        "INSERT INTO state (target, check_name, ok, since) VALUES (?, ?, ?, ?)",
                        (r.target, r.check, int(r.ok), ts),
                    )
                    if not r.ok:  # down the first time we see it: worth an alert
                        changes.append(Change(r, None, when))
                    continue

                was_ok, since = bool(row[0]), datetime.strptime(row[1], TS_FORMAT)
                if was_ok != r.ok:
                    self.conn.execute(
                        "UPDATE state SET ok = ?, since = ? WHERE target = ? AND check_name = ?",
                        (int(r.ok), ts, r.target, r.check),
                    )
                    down_for = when - since if r.ok else None
                    changes.append(Change(r, was_ok, when, down_for))

        return changes

    def uptime(self, hours: float = 24, now: datetime | None = None) -> list[UptimeRow]:
        """Uptime per check over the last `hours`."""
        now = now or datetime.now()
        cutoff = (now - timedelta(hours=hours)).strftime(TS_FORMAT)
        rows = self.conn.execute(
            """
            SELECT r.target, r.check_name, COUNT(*), SUM(r.ok),
                   AVG(CASE WHEN r.ok = 1 THEN r.latency_ms END),
                   COALESCE(s.ok, 0)
            FROM results r
            LEFT JOIN state s ON s.target = r.target AND s.check_name = r.check_name
            WHERE r.ts >= ?
            GROUP BY r.target, r.check_name
            ORDER BY r.target, r.check_name
            """,
            (cutoff,),
        ).fetchall()
        return [
            UptimeRow(t, c, total, passed or 0, round(avg, 1) if avg is not None else None, bool(cur))
            for t, c, total, passed, avg, cur in rows
        ]
