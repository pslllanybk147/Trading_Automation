import tempfile
from pathlib import Path
import pytest
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


def test_roundtrip_partial_tp_fields(tmp_path):
    j = _journal(tmp_path)
    t = TradeRecord("BTCUSDT", "LONG", 100.0, 0.0, 500.0, 0.05, 1, 0, "golden_cross",
                    sl_price=95.0, tp1_price=110.0, tp2_price=116.0, atr_ref=2.0,
                    partial_fraction=0.5, trail_atr=2.0, tp1_filled=True, trail_hi=115.0)
    j.record_trade(t)
    (back,) = j.open_trades()
    assert back.tp2_price == 116.0
    assert back.atr_ref == 2.0
    assert back.partial_fraction == 0.5
    assert back.trail_atr == 2.0
    assert back.tp1_filled is True
    assert back.trail_hi == 115.0


def test_record_partial_fill_updates_open_row(tmp_path):
    j = _journal(tmp_path)
    j.record_trade(TradeRecord("BTCUSDT", "LONG", 100.0, 0.0, 1000.0, 1.0, 1, 0, "golden_cross",
                               sl_price=95.0, tp1_price=110.0, atr_ref=2.0,
                               partial_fraction=0.5, trail_atr=2.0))
    fill = TradeRecord("BTCUSDT", "LONG", 100.0, 110.0, 500.0, 0.55, 1, 2, "golden_cross",
                       sl_price=95.0, tp1_price=110.0, atr_ref=2.0,
                       partial_fraction=0.5, trail_atr=2.0, tp1_filled=True, trail_hi=111.0)
    remaining = TradeRecord("BTCUSDT", "LONG", 100.0, 0.0, 500.0, 0.5, 1, 0, "golden_cross",
                            sl_price=100.1, tp1_price=110.0, atr_ref=2.0,
                            partial_fraction=0.5, trail_atr=2.0,
                            tp1_filled=True, trail_hi=111.0, tp2_price=0.0)
    j.record_partial_fill(fill, remaining)
    assert len(j.closed_since(0)) == 1
    (open_trade,) = j.open_trades()
    assert open_trade.size_usdt == 500.0
    assert open_trade.fee == pytest.approx(0.5)
    assert open_trade.tp1_filled is True


def test_migrates_old_schema(tmp_path):
    """ฐานข้อมูล schema เก่า (ก่อน partial TP) ต้อง migrate เพิ่มคอลัมน์ใหม่ได้."""
    import sqlite3
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE trades (symbol TEXT, side TEXT, entry REAL, exit REAL,"
                 " size_usdt REAL, fee REAL, ts_open INTEGER, ts_close INTEGER,"
                 " reason TEXT, regime TEXT, sl_price REAL, tp1_price REAL)")
    conn.execute("INSERT INTO trades VALUES ('BTCUSDT','LONG',100,0,1000,1,1,0,'golden_cross','bull',95,110)")
    conn.commit()
    conn.close()

    j = Journal(str(db))
    (t,) = j.open_trades()
    assert t.partial_fraction == 0.0
    assert t.tp1_filled is False
    assert t.trail_hi == 0.0
