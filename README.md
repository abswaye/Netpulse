# NetPulse

A lightweight Python network monitor for home labs and small networks. NetPulse checks whether your devices are reachable, whether their services are listening, and whether your DNS servers are answering correctly, and it flags **DNS drift** when a record changes when it shouldn't.

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
```

## Features

- **Availability checks**: pings every device using the system `ping` command, so it works on Windows, macOS and Linux without admin rights, and reports round-trip latency.
- **Port checks**: confirms services (SSH, HTTPS, RDP, WireGuard and so on) are actually listening, not just that the host is up.
- **DNS health checks**: queries a *specific* DNS server for a record, catching timeouts, SERVFAIL and NXDOMAIN.
- **DNS drift detection**: compares answers against the values you expect and reports exactly what's missing or unexpected.
- **Fast**: every check runs in parallel.
- **Script-friendly**: `--json` output and exit codes (`0` all passed, `1` something failed, `2` config error) make it easy to use from cron, Task Scheduler or other tools.

## Quick start

Requires Python 3.10 or newer.

```bash
git clone https://github.com/abswaye/netpulse.git
cd netpulse
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

cp devices.example.yaml devices.yaml   # Windows: copy devices.example.yaml devices.yaml
# edit devices.yaml with your own devices and DNS servers

python -m netpulse
```

Other options:

```bash
python -m netpulse --config path/to/other.yaml   # use a different config
python -m netpulse --json                        # machine-readable output
```

## Configuration

Everything lives in one YAML file. `devices.yaml` is git-ignored so your real IP addresses stay private; see [`devices.example.yaml`](devices.example.yaml) for a full sample.

```yaml
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

## Project structure

```
netpulse/
├── __main__.py      # CLI and table output
├── config.py        # loads and validates the YAML config
├── runner.py        # runs all checks in parallel
└── checks/
    ├── ping.py      # ICMP availability + latency
    ├── ports.py     # TCP port checks
    └── dns.py       # DNS resolution + drift detection
tests/               # pytest suite (no network access needed)
```

## Running the tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Roadmap

- [x] Ping, port and DNS checks with drift detection
- [ ] Alert only on state changes (up → down, down → up)
- [ ] Discord webhook and email alerts
- [ ] SQLite uptime history and log file
- [ ] Built-in scheduler (`--watch`)
- [ ] Automatic DNS remediation with config backup
- [ ] Web dashboard (Flask)
- [ ] Docker image and AWS EC2 deployment
- [ ] GitHub Actions CI

## License

MIT, see [LICENSE](LICENSE).
