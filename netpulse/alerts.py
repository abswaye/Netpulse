"""Send alerts when a check changes state.

Channels are configured with environment variables (usually in a .env file
that is never committed):

    DISCORD_WEBHOOK_URL   Discord channel webhook
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    ALERT_EMAIL_FROM, ALERT_EMAIL_TO   optional email alerts (STARTTLS)

A channel with no settings is simply skipped, and a failed alert is logged
instead of crashing the monitor.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from . import __version__
from .storage import Change, format_duration

log = logging.getLogger("netpulse")

RED, GREEN = 0xE74C3C, 0x2ECC71
TEST_CHECK = "test alert"
USER_AGENT = f"NetPulse/{__version__} (+https://github.com/abswaye/Netpulse)"


def describe(change: Change) -> tuple[str, str]:
    """Return (title, body) text for one change."""
    r = change.result
    if r.check == TEST_CHECK:
        return "NetPulse test alert", "Alerts are working. You'll get a message here when a check goes down or recovers."
    is_dns = r.check.startswith("dns")
    if r.ok:
        title = f"RECOVERED: {r.target} {r.check}"
        body = "Back to normal"
        if change.down_for is not None:
            body += f" after {format_duration(change.down_for)}"
        if r.latency_ms is not None:
            body += f" ({r.latency_ms:g} ms)"
        body += "."
    else:
        title = f"{'FAIL' if is_dns else 'DOWN'}: {r.target} {r.check}"
        body = r.detail or "check failed"
        if change.previous_ok is None:
            body += " (failing since monitoring started)"
    return title, body


def discord_payload(changes: list[Change]) -> list[dict]:
    """Build Discord webhook messages (max 10 embeds per message)."""
    embeds = []
    for c in changes:
        title, body = describe(c)
        embeds.append(
            {
                "title": title,
                "description": body,
                "color": GREEN if c.result.ok else RED,
                "timestamp": c.changed_at.astimezone().isoformat(),
            }
        )
    return [{"username": "NetPulse", "embeds": embeds[i : i + 10]} for i in range(0, len(embeds), 10)]


def send_discord(webhook_url: str, changes: list[Change], timeout: float = 10) -> None:
    for message in discord_payload(changes):
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(message).encode(),
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout):
            pass


def build_email(changes: list[Change], sender: str, recipient: str) -> EmailMessage:
    down = sum(1 for c in changes if not c.result.ok)
    up = len(changes) - down
    parts = []
    if down:
        parts.append(f"{down} down")
    if up:
        parts.append(f"{up} recovered")
    msg = EmailMessage()
    msg["Subject"] = f"[NetPulse] {', '.join(parts)}"
    msg["From"] = sender
    msg["To"] = recipient
    lines = []
    for c in changes:
        title, body = describe(c)
        lines.append(f"{title}\n    {body}\n    at {c.changed_at:%Y-%m-%d %H:%M:%S}")
    msg.set_content("\n\n".join(lines) + "\n\n-- NetPulse")
    return msg


def send_email(changes: list[Change], env: dict[str, str]) -> None:
    msg = build_email(changes, env.get("ALERT_EMAIL_FROM") or env["SMTP_USER"], env["ALERT_EMAIL_TO"])
    with smtplib.SMTP(env["SMTP_HOST"], int(env.get("SMTP_PORT", 587)), timeout=15) as smtp:
        smtp.starttls()
        if env.get("SMTP_USER"):
            smtp.login(env["SMTP_USER"], env.get("SMTP_PASSWORD", ""))
        smtp.send_message(msg)


def configured_channels(env: dict[str, str] | None = None) -> list[str]:
    env = dict(os.environ) if env is None else env
    channels = []
    if env.get("DISCORD_WEBHOOK_URL"):
        channels.append("discord")
    if env.get("SMTP_HOST") and env.get("ALERT_EMAIL_TO"):
        channels.append("email")
    return channels


def send_alerts(changes: list[Change], env: dict[str, str] | None = None) -> list[str]:
    """Send alerts on every configured channel. Returns the channels that succeeded."""
    if not changes:
        return []
    env = dict(os.environ) if env is None else env
    sent = []
    for channel in configured_channels(env):
        try:
            if channel == "discord":
                send_discord(env["DISCORD_WEBHOOK_URL"], changes)
            else:
                send_email(changes, env)
            sent.append(channel)
        except (urllib.error.URLError, OSError, smtplib.SMTPException, KeyError) as exc:
            log.error("alert via %s failed: %s", channel, exc)
    return sent
