# NetPulse

A lightweight Python network monitor for home labs and small networks. NetPulse checks whether your devices are reachable, whether their services are listening, and whether your DNS servers are answering correctly. It flags **DNS drift** when a record changes when it shouldn't, sends a **Discord or email alert the moment something goes down or recovers**, and keeps an **uptime history** in SQLite.

Example output:

```
NetPulse check run  2026-10-21 03:46:22
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Target         ┃ Type          ┃ Check                  ┃ Status ┃ Latency ┃ Detail                                     ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ lab-server     │ Ubuntu server │ ping                   │   UP   │  0.4 ms │ reachable                                  │
│                │               │ port 22 (SSH)          │   UP   │  1.1 ms │ open                                       │
│ local-resolver │ dns           │ dns A example.com      │   OK   │  6.4 ms │ 93.184.215.14                              │
│ lab-record     │ dns           │ dns A server.home.arpa │  FAIL  │  5.8 ms │ drift: missing 192.168.1.20; unexpected    │
│                │               │                        │        │         │ 192.168.1.99                               │
└────────────────┴───────────────┴────────────────────────┴────────┴─────────┴────────────────────────────────────────────┘
1 of 4 checks failed
FAIL: lab-record dns A server.home.arpa  drift: missing 192.168.1.20; unexpected 192.168.1.99
alerts sent via: discord
```

## Features

- **Availability checks**: pings every device using the system `ping` command, so it works on Windows, macOS and Linux without admin rights, and reports round-trip latency.
- **Port checks**: confirms services (SSH, HTTPS, RDP, WireGuard and so on) are actually listening, not just that the host is up.
- **DNS health checks**: queries a *specific* DNS server for a record, catching timeouts, SERVFAIL and NXDOMAIN.
- **DNS drift detection**: compares answers against the values you expect and reports exactly what's missing or unexpected.
- **Change-based alerts**: Discord webhook and/or email, sent only when a check *changes* state (up to down, down to up). No alert spam every cycle, and recovery alerts say how long the outage lasted.
- **Uptime history**: every result is stored in SQLite; `--report` shows uptime percentage and average latency per check.
- **Continuous monitoring**: `--watch` re-runs every check on an interval, with everything logged to `netpulse.log`.
- **Fast and script-friendly**: checks run in parallel; `--json` output and exit codes (`0` all passed, `1` something failed, `2` config error) work well with cron or Task Scheduler.

## Quick start

Requires Python 3.10 or newer.

```bash
git clone https://github.com/abswaye/Netpulse.git
cd Netpulse
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

cp devices.example.yaml devices.yaml   # Windows: copy devices.example.yaml devices.yaml
# edit devices.yaml with your own devices and DNS servers

python -m netpulse
```

## Usage

```bash
python -m netpulse                  # run every check once
python -m netpulse --watch          # keep monitoring (every interval_seconds)
python -m netpulse --report         # uptime per check, last 24 hours
python -m netpulse --report 168     # ...or any number of hours (168 = 7 days)
python -m netpulse --test-alert     # confirm your alert channels work
python -m netpulse --no-alerts      # check and record without alerting
python -m netpulse --json           # machine-readable output
python -m netpulse -c other.yaml    # use a different config file
```

## Setting up alerts

Alert settings are secrets, so they live in a `.env` file that is git-ignored and never committed.

```bash
cp .env.example .env    # Windows: copy .env.example .env
```

**Discord:** in your server, open *Server Settings → Integrations → Webhooks → New Webhook*, pick a channel, click *Copy Webhook URL*, and paste it into `.env`:

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

**Email (optional):** fill in the `SMTP_*` and `ALERT_EMAIL_*` values. For Gmail or Outlook, use an app password, not your normal password.

Then run `python -m netpulse --test-alert`.

## Configuration

Everything else lives in one YAML file. `devices.yaml` is git-ignored so your real IP addresses stay private; see [`devices.example.yaml`](devices.example.yaml) for a full sample.

```yaml
settings:
  interval_seconds: 300        # how often --watch runs

devices:
  - name: firewall
    host: 192.168.1.1
    type: pfSense
    ports: [443]

dns_checks:
  - name: lab-record
    server: 192.168.1.1        # the DNS server to ask
    query: server.home.arpa
    record_type: A             # A, AAAA, CNAME, MX, TXT, ...
    expect: [192.168.1.20]     # optional: fail if the answer drifts
```

## How it works

1. **Load** the device list and DNS checks from `devices.yaml`, and alert settings from `.env`.
2. **Check** everything in parallel: ICMP ping, TCP port connects, and DNS queries to specific servers.
3. **Record** each result in SQLite and compare it with the last known state of that check.
4. **Alert** only on changes: a check that just failed, or one that just recovered (with outage length).
5. **Repeat** on an interval with `--watch`, or run once from cron / Task Scheduler.

## Project structure

```
netpulse/
├── __main__.py      # CLI: tables, watch loop, report, test alert
├── config.py        # loads and validates the YAML config
├── runner.py        # runs all checks in parallel
├── storage.py       # SQLite history + up/down state tracking
├── alerts.py        # Discord webhook + email alerts
└── checks/
    ├── ping.py      # ICMP availability + latency
    ├── ports.py     # TCP port checks
    └── dns.py       # DNS resolution + drift detection
tests/               # pytest suite (no internet access needed)
```

## Running the tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Roadmap

- [x] Ping, port and DNS checks with drift detection
- [x] Alert only on state changes (up → down, down → up)
- [x] Discord webhook and email alerts
- [x] SQLite uptime history, `--report`, and log file
- [x] Continuous monitoring (`--watch`)
- [ ] Automatic DNS remediation with config backup
- [ ] Web dashboard (Flask)
- [ ] Docker image and AWS EC2 deployment
- [ ] GitHub Actions CI

## License

MIT, see [LICENSE](LICENSE).
