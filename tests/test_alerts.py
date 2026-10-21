import json
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from netpulse import alerts
from netpulse.checks import CheckResult
from netpulse.storage import Change

NOW = datetime(2026, 10, 21, 12, 0, 0)


def went_down():
    return Change(CheckResult("router", "ping", False, detail="no reply"), True, NOW)


def came_back():
    r = CheckResult("router", "ping", True, latency_ms=3.0, detail="reachable")
    return Change(r, False, NOW, down_for=timedelta(minutes=12, seconds=30))


def test_describe_down_and_recovery():
    assert alerts.describe(went_down()) == ("DOWN: router ping", "no reply")
    assert alerts.describe(came_back()) == ("RECOVERED: router ping", "Back to normal after 12m 30s (3 ms).")


def test_dns_failures_say_fail_not_down():
    c = Change(CheckResult("lab-record", "dns A server.home.arpa", False, detail="drift: missing 10.0.0.1"), True, NOW)
    assert alerts.describe(c)[0] == "FAIL: lab-record dns A server.home.arpa"


def test_discord_payload_colours_and_batches_of_ten():
    messages = alerts.discord_payload([went_down()] * 11 + [came_back()])
    assert len(messages) == 2
    assert len(messages[0]["embeds"]) == 10 and len(messages[1]["embeds"]) == 2
    assert messages[0]["embeds"][0]["color"] == alerts.RED
    assert messages[1]["embeds"][-1]["color"] == alerts.GREEN


def test_email_subject_counts():
    msg = alerts.build_email([went_down(), came_back()], "np@example.com", "me@example.com")
    assert msg["Subject"] == "[NetPulse] 1 down, 1 recovered"
    assert "DOWN: router ping" in msg.get_content()


def test_channels_skip_unconfigured():
    assert alerts.configured_channels({}) == []
    assert alerts.configured_channels({"DISCORD_WEBHOOK_URL": "x"}) == ["discord"]
    assert alerts.configured_channels({"SMTP_HOST": "h", "ALERT_EMAIL_TO": "t"}) == ["email"]
    assert alerts.send_alerts([went_down()], {}) == []


def test_discord_webhook_is_posted():
    received = []

    class Hook(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.headers["User-Agent"], json.loads(body)))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Hook)
    threading.Thread(target=server.handle_request, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/webhook"

    sent = alerts.send_alerts([went_down()], {"DISCORD_WEBHOOK_URL": url})
    server.server_close()

    assert sent == ["discord"]
    agent, payload = received[0]
    assert agent.startswith("NetPulse/")
    assert payload["embeds"][0]["title"] == "DOWN: router ping"


def test_failed_webhook_does_not_crash():
    assert alerts.send_alerts([went_down()], {"DISCORD_WEBHOOK_URL": "http://127.0.0.1:9/nothing"}) == []


def test_test_alert_wording():
    c = Change(CheckResult("netpulse", alerts.TEST_CHECK, True), False, NOW)
    assert alerts.describe(c)[0] == "NetPulse test alert"
