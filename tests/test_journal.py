import tempfile
from pathlib import Path
from pipeline.journal import Journal
from pipeline.models import TradeRecord


def _journal(tmp_path):
    return Journal(db_path=str(tmp_path / "journal.db"))


def test_record_and_scorecard(tmp_path):
    import calendar
    from datetime import datetime, timezone
    # ts_close must land inside the queried month (2026-09)
    sep_2026 = calendar.timegm(datetime(2026, 9, 15, tzinfo=timezone.utc).timetuple())
    j = _journal(tmp_path)
    j.record_trade(TradeRecord("BTCUSDT", "LONG", 100.0, 110.0, 100.0, 0.1, sep_2026 - 10, sep_2026, "golden_cross"))
    j.record_trade(TradeRecord("ETHUSDT", "LONG", 200.0, 190.0, 100.0, 0.1, sep_2026 - 10, sep_2026, "turtle_breakout"))
    sc = j.monthly_scorecard("2026-09")
    assert sc["trades"] == 2
    assert sc["win_rate"] == 0.5
    assert sc["total_pnl"] > 0


def test_open_and_close(tmp_path):
    j = _journal(tmp_path)
    j.record_trade(TradeRecord("BTCUSDT", "LONG", 100.0, 0.0, 100.0, 0.0, 1, 0, "golden_cross"))
    assert len(j.open_trades()) == 1
    closed = j.close_trade("BTCUSDT", exit_price=110.0, fee=0.1)
    assert closed is not None
    assert closed.pnl() == 9.9
    assert len(j.open_trades()) == 0


def test_closed_since(tmp_path):
    import time
    j = _journal(tmp_path)
    now = int(time.time())
    j.record_trade(TradeRecord("BTCUSDT", "LONG", 100.0, 90.0, 100.0, 0.1, now - 10, now, "golden_cross"))
    j.record_trade(TradeRecord("ETHUSDT", "LONG", 200.0, 210.0, 100.0, 0.1, now - 10, now, "turtle_breakout"))
    assert len(j.closed_since(now - 60)) == 2
    assert len(j.closed_since(now + 60)) == 0
