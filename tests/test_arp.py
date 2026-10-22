from unittest import mock

import pytest

from netpulse.checks import CheckResult
from netpulse.checks import arp
from netpulse.config import ConfigError, parse_config


def test_parse_windows_neighbor_states():
    assert arp.parse_windows_state("Reachable\r\n") == "reachable"
    assert arp.parse_windows_state("Unreachable\r\nReachable\r\n") == "reachable"
    assert arp.parse_windows_state("Incomplete\r\n") == "incomplete"
    assert arp.parse_windows_state("") is None


def test_parse_linux_neighbor_states():
    assert arp.parse_linux_state("192.168.1.5 dev wlan0 lladdr d8:fb:d6:4a:c8:3c REACHABLE") == "reachable"
    assert arp.parse_linux_state("192.168.1.9 dev wlan0 FAILED") == "failed"
    assert arp.parse_linux_state("") is None


def test_parse_macos_neighbor_states():
    assert arp.parse_macos_state("? (192.168.1.5) at d8:fb:d6:4a:c8:3c on en0 ifscope [ethernet]") == "reachable"
    assert arp.parse_macos_state("? (192.168.1.9) at (incomplete) on en0 ifscope [ethernet]") == "incomplete"
    assert arp.parse_macos_state("192.168.1.9 (192.168.1.9) -- no entry") is None


def _ping(ok):
    return CheckResult("tv", "ping", ok, latency_ms=3.0 if ok else None)


def test_device_that_blocks_ping_but_answers_arp_is_online():
    with mock.patch.object(arp, "ping", return_value=_ping(False)), \
         mock.patch.object(arp, "neighbor_state", return_value="reachable"):
        r = arp.check_arp("tv", "192.168.68.103")
    assert r.ok and r.detail == "online (answers ARP, blocks ping)"


def test_device_that_answers_ping_skips_arp_lookup():
    with mock.patch.object(arp, "ping", return_value=_ping(True)), \
         mock.patch.object(arp, "neighbor_state") as ns:
        r = arp.check_arp("tv", "192.168.68.103")
    assert r.ok and r.latency_ms == 3.0
    ns.assert_not_called()


def test_device_that_is_really_off_is_down():
    with mock.patch.object(arp, "ping", return_value=_ping(False)), \
         mock.patch.object(arp, "neighbor_state", return_value="unreachable"):
        r = arp.check_arp("tv", "192.168.68.103")
    assert not r.ok and r.detail == "no ARP reply (unreachable)"


def test_config_method_and_alert_options():
    cfg = parse_config({"devices": [{"name": "tv", "host": "192.168.68.103", "method": "arp", "alert": False}]})
    assert cfg.devices[0].method == "arp" and cfg.devices[0].alert is False


@pytest.mark.parametrize(
    "device, message",
    [
        ({"name": "tv", "host": "tv.local", "method": "arp"}, "needs an IPv4 address"),
        ({"name": "tv", "host": "1.2.3.4", "method": "snmp"}, "'ping' or 'arp'"),
        ({"name": "tv", "host": "1.2.3.4", "alert": "no"}, "true or false"),
    ],
)
def test_config_rejects_bad_options(device, message):
    with pytest.raises(ConfigError, match=message):
        parse_config({"devices": [device]})
