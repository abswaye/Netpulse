import socket

from netpulse.checks.dns import compare_answers
from netpulse.checks.ping import build_ping_command, parse_ping_output
from netpulse.checks.ports import check_port

WINDOWS_OK = """
Pinging 192.168.1.1 with 32 bytes of data:
Reply from 192.168.1.1: bytes=32 time=3ms TTL=64
"""
WINDOWS_SUB_MS = "Reply from 10.0.0.1: bytes=32 time<1ms TTL=64"
WINDOWS_UNREACHABLE = """
Pinging 192.168.1.99 with 32 bytes of data:
Reply from 192.168.1.50: Destination host unreachable.
"""
LINUX_OK = "64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=12.4 ms"


def test_ping_command_per_os():
    assert build_ping_command("h", 1000, "Windows") == ["ping", "-n", "1", "-w", "1000", "h"]
    assert build_ping_command("h", 1000, "Darwin") == ["ping", "-c", "1", "-W", "1000", "h"]
    assert build_ping_command("h", 2500, "Linux") == ["ping", "-c", "1", "-W", "2", "h"]


def test_parse_windows_reply():
    assert parse_ping_output(WINDOWS_OK, 0, "windows") == (True, 3.0)
    assert parse_ping_output(WINDOWS_SUB_MS, 0, "windows") == (True, 1.0)


def test_windows_unreachable_is_down_even_with_exit_code_zero():
    assert parse_ping_output(WINDOWS_UNREACHABLE, 0, "windows") == (False, None)


def test_parse_linux_reply():
    assert parse_ping_output(LINUX_OK, 0, "linux") == (True, 12.4)
    assert parse_ping_output("", 1, "linux") == (False, None)


def test_dns_compare_matches_ignoring_order_and_trailing_dot():
    ok, detail = compare_answers(["10.0.0.2", "10.0.0.1"], ["10.0.0.1", "10.0.0.2."])
    assert ok and detail == "10.0.0.1, 10.0.0.2"


def test_dns_compare_reports_drift():
    ok, detail = compare_answers(["10.0.0.9"], ["10.0.0.1"])
    assert not ok
    assert detail == "drift: missing 10.0.0.1; unexpected 10.0.0.9"


def test_dns_compare_without_expectation_just_lists_answers():
    assert compare_answers(["1.2.3.4"], []) == (True, "1.2.3.4")


def test_port_open_and_closed():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]
    try:
        assert check_port("local", "127.0.0.1", port).ok
    finally:
        server.close()
    closed = check_port("local", "127.0.0.1", port)
    assert not closed.ok and closed.detail == "refused"
