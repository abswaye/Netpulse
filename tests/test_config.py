import pytest

from netpulse.config import ConfigError, load_config, parse_config


def test_parses_devices_and_dns_checks():
    cfg = parse_config(
        {
            "devices": [{"name": "fw", "host": "10.0.0.1", "type": "pfSense", "ports": [22, "443"]}],
            "dns_checks": [{"name": "r", "server": "10.0.0.1", "query": "example.com", "expect": "1.2.3.4"}],
        }
    )
    assert cfg.devices[0].ports == [22, 443]
    assert cfg.dns_checks[0].record_type == "A"
    assert cfg.dns_checks[0].expect == ["1.2.3.4"]
    assert cfg.settings.ping_timeout_ms == 1000


@pytest.mark.parametrize(
    "data, message",
    [
        ({"devices": [{"host": "10.0.0.1"}]}, "missing required field 'name'"),
        ({"devices": [{"name": "a", "host": "x", "ports": [70000]}]}, "out of range"),
        ({"devices": [{"name": "a", "host": "x", "ports": "22"}]}, "must be a list"),
        ({"devices": [{"name": "a", "host": "x"}, {"name": "a", "host": "y"}]}, "duplicate device name"),
        ({}, "no 'devices' or 'dns_checks'"),
    ],
)
def test_rejects_bad_config(data, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(data)


def test_missing_file_gives_helpful_message(tmp_path):
    with pytest.raises(ConfigError, match="devices.example.yaml"):
        load_config(tmp_path / "nope.yaml")


def test_example_config_is_valid():
    cfg = load_config("devices.example.yaml")
    assert len(cfg.devices) >= 1 and len(cfg.dns_checks) >= 1


def test_rejects_too_short_interval():
    with pytest.raises(ConfigError, match="at least 10"):
        parse_config({"settings": {"interval_seconds": 2}, "devices": [{"name": "a", "host": "x"}]})
