from datetime import datetime, timedelta

from netpulse.checks import CheckResult
from netpulse.storage import History, format_duration

T0 = datetime(2026, 10, 21, 12, 0, 0)


def up(target="router", check="ping"):
    return CheckResult(target, check, True, latency_ms=2.0, detail="reachable")


def down(target="router", check="ping"):
    return CheckResult(target, check, False, detail="no reply")


def test_first_run_alerts_only_on_failures():
    h = History(":memory:")
    changes = h.record([up("a"), down("b")], T0)
    assert [c.result.target for c in changes] == ["b"]
    assert changes[0].previous_ok is None


def test_no_repeat_alert_while_status_is_unchanged():
    h = History(":memory:")
    h.record([down()], T0)
    assert h.record([down()], T0 + timedelta(minutes=5)) == []
    assert h.record([down()], T0 + timedelta(minutes=10)) == []


def test_down_then_recovery_reports_how_long_it_was_down():
    h = History(":memory:")
    h.record([up()], T0)
    went_down = h.record([down()], T0 + timedelta(minutes=5))
    assert len(went_down) == 1 and went_down[0].previous_ok is True and not went_down[0].recovered

    h.record([down()], T0 + timedelta(minutes=10))
    back = h.record([up()], T0 + timedelta(minutes=17, seconds=30))
    assert len(back) == 1 and back[0].recovered
    assert back[0].down_for == timedelta(minutes=12, seconds=30)


def test_uptime_report():
    h = History(":memory:")
    for i, r in enumerate([up(), up(), up(), down()]):
        h.record([r], T0 + timedelta(minutes=5 * i))
    [row] = h.uptime(hours=24, now=T0 + timedelta(hours=1))
    assert (row.total, row.passed, row.uptime_pct) == (4, 3, 75.0)
    assert row.avg_latency_ms == 2.0
    assert row.current_ok is False


def test_uptime_ignores_old_results():
    h = History(":memory:")
    h.record([down()], T0)
    h.record([up()], T0 + timedelta(hours=30))
    [row] = h.uptime(hours=24, now=T0 + timedelta(hours=30))
    assert row.total == 1 and row.uptime_pct == 100.0


def test_history_persists_on_disk(tmp_path):
    db = tmp_path / "np.db"
    with History(db) as h:
        h.record([up()], T0)
    with History(db) as h:
        assert h.record([down()], T0 + timedelta(minutes=5))[0].previous_ok is True


def test_format_duration():
    assert format_duration(timedelta(seconds=42)) == "42s"
    assert format_duration(timedelta(minutes=12, seconds=30)) == "12m 30s"
    assert format_duration(timedelta(hours=2, minutes=5)) == "2h 5m"
