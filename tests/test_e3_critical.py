# -*- coding: utf-8 -*-
"""E3 critical tests §10.1 — เขียนก่อนโค้ด (TDD) — 6 ข้อตาม spec"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from e3.backtest import Backtester
from e3.clock import NY_LOCAL, sessions_for_day, trade_window_for
from e3.config import E3Config
from e3.sizing import compute_lots
from e3.types import Bar, BarError

from tests.e3_synth import Builder, _day_start_utc

UTC = timezone.utc


# ---------- test_closed_bar_only ----------

def test_closed_bar_only():
    with pytest.raises(BarError):
        Bar(1_700_000_000, 2000, 2001, 1999, 2000.5, closed=False).validate()


def test_bad_ohlc_rejected():
    with pytest.raises(BarError):
        Bar(1, 2000, 1999, 2001, 2000).validate()   # high < low
    with pytest.raises(BarError):
        Bar(2, 1990, 2001, 1999, 2000).validate()   # open outside


def test_duplicate_ts_rejected():
    t = _day_start_utc(2026, 3, 3)
    b1 = Bar(t, 2000, 2001, 1999, 2000)
    b2 = Bar(t, 2000, 2001, 1999, 2000)
    from e3.types import check_monotonic
    with pytest.raises(BarError):
        check_monotonic([b1, b2])


# ---------- test_dst_transition ----------

def _window_hours(ts: int) -> float:
    w = trade_window_for(ts)
    assert w is not None
    return (w.end - w.start).total_seconds() / 3600.0


def _utc_window(ts: int):
    """คืน (start, end) เป็น UTC hour ของ trade window ณ ts"""
    w = trade_window_for(ts)
    assert w is not None
    return w.start.astimezone(UTC), w.end.astimezone(UTC)


def test_dst_transition_london():
    # winter: 08:00-10:00 UTC (London GMT) — 4 Mar 2026
    ts_w = _day_start_utc(2026, 3, 4, 8, 15)
    s_h, e_h = _utc_window(ts_w)
    assert (s_h.hour, e_h.hour) == (8, 10)
    # summer: 07:00-09:00 UTC (London BST) — 3 Jun 2026
    ts_s = _day_start_utc(2026, 6, 3, 7, 15)
    s_h, e_h = _utc_window(ts_s)
    assert (s_h.hour, e_h.hour) == (7, 9)
    # ความยาว window คงที่ 2 ชั่วโมงทุกวัน (ตาม local ไม่ตาม UTC)
    assert _window_hours(ts_w) == 2.0
    assert _window_hours(ts_s) == 2.0


def test_dst_transition_ny_uk_us_different_weeks():
    # 2026: US เปลี่ยน DST 8 Mar, UK 29 Mar — คนละสัปดาห์
    # 10 Mar (หลัง US เปลี่ยน ก่อน UK): NY = EDT → 12:30 UTC; London ยัง GMT → 08:00 UTC
    ts = _day_start_utc(2026, 3, 10, 12, 45)
    s_h, e_h = _utc_window(ts)
    assert (s_h.hour, e_h.hour) == (12, 15)             # NY EDT 12:30-15:00 UTC
    assert trade_window_for(_day_start_utc(2026, 3, 10, 8, 30)) is not None  # London ยัง GMT 08:00-10:00
    # 1 Apr (ทั้งคู่ DST แล้ว): London 07:00-09:00 UTC, NY 12:30-15:00 UTC
    ts = _day_start_utc(2026, 4, 1, 12, 45)
    s_h, e_h = _utc_window(ts)
    assert (s_h.hour, e_h.hour) == (12, 15)
    ts = _day_start_utc(2026, 4, 1, 7, 30)
    s_h, e_h = _utc_window(ts)
    assert (s_h.hour, e_h.hour) == (7, 9)


def test_asian_range_summer_starts_prev_day():
    # Summer: Asian = 23:00 UTC (D-1) – 06:00 UTC — ตามตาราง spec §3
    ts_s = _day_start_utc(2026, 6, 3, 0, 30)     # 00:30 UTC = 01:30 London — อยู่ใน asian
    s = sessions_for_day(ts_s)
    assert s["asian"].contains(ts_s)
    # ขอบเริ่ม/จบเทียบเป็น UTC: summer เริ่ม 23:00 UTC ของวันก่อน จบ 06:00 UTC
    assert s["asian"].start.astimezone(UTC).hour == 23
    assert s["asian"].start.astimezone(UTC).day == 2      # วันก่อนหน้า (D-1)
    assert s["asian"].end.astimezone(UTC).hour == 6
    # Winter: 00:00–07:00 UTC ของวันเดียวกัน
    ts_w = _day_start_utc(2026, 3, 4, 0, 30)
    s = sessions_for_day(ts_w)
    assert s["asian"].contains(ts_w)
    assert s["asian"].start.astimezone(UTC).hour == 0
    assert s["asian"].end.astimezone(UTC).hour == 7


# ---------- test_asian_range_weekend_gap ----------

def test_weekend_gap_classified():
    from e3.clock import classify_gap
    fri = _day_start_utc(2026, 3, 6, 23, 0)       # ศุกร์ 23:00 UTC (ปิดแล้ว)
    sun = _day_start_utc(2026, 3, 8, 23, 30)      # อาทิตย์ 23:30 UTC
    assert classify_gap(fri, sun) == "weekend"
    # gap ผิดปกติกลางสัปดาห์ = outage
    tue1 = _day_start_utc(2026, 3, 3, 2, 0)
    tue2 = _day_start_utc(2026, 3, 3, 8, 0)
    assert classify_gap(tue1, tue2) == "outage"
    # ปกติ
    assert classify_gap(tue1, tue1 + 900) == "ok"


def test_monday_after_gap_no_nan_asian():
    """จันทร์หลัง weekend — asian range ต้องสร้างจาก bars ของวันนั้นเอง (ไม่ NaN/ค้างของศุกร์)"""
    cfg = E3Config()
    bt = Backtester(cfg)
    b = Builder(_day_start_utc(2026, 3, 2) - 105 * 86400).seed_until(_day_start_utc(2026, 3, 2))
    # จันทร์ 2 Mar: asian 00:00-07:00 UTC (winter) สร้างก่อน London
    st = bt.engine.state
    for bar in b.bars[-200:]:
        bt.engine.on_bar(bar)
        if bar.ts >= _day_start_utc(2026, 3, 2) and st.asian_high is not None:
            # ค่าต้องจาก sin-wave ของ seed (base 2000 ± vol 8 + day drift 0.5/วัน) ไม่ใช่ค่าค้างวันก่อน
            assert st.asian_high >= st.asian_low
            assert 1990 < st.asian_high <= 2060


# ---------- test_cost_always_applied ----------

def _run_simple_trade(cfg: E3Config, bars: list[Bar]):
    bt = Backtester(cfg)
    trades, summary = bt.run(bars)
    return trades, summary


def test_cost_always_applied():
    """ทุกไม้ที่ fill ต้องมี cost > 0 — spread 0.30 default ไม่มีทางเป็นศูนย์"""
    cfg = E3Config()
    bars = _script_clean_short_sweep()
    trades, _ = _run_simple_trade(cfg, bars)
    assert trades, "ต้องมีไม้จาก fixture นี้"
    for t in trades:
        assert t.cost_usd_total > 0


# ---------- test_no_lot_round_up ----------

def test_no_lot_round_up():
    """equity ต่ำจน lots < min_lot → SKIP ไม่ใช่เทรด min_lot"""
    cfg = E3Config(equity=200.0)     # 0.5% = $1 risk; stop ~ $10 → lots = 0.001 < 0.01
    sr = compute_lots(cfg.equity, stop_distance=10.0, cfg=cfg)
    assert sr.skipped and sr.reason == "below_min_lot"
    assert sr.lots == 0.0


def test_no_lot_round_up_in_backtest():
    """เช่นกันแต่ผ่าน backtest จริง — ไม่ควรมีไม้ที่ lots < min_lot"""
    cfg = E3Config(equity=100.0)
    bars = _script_clean_short_sweep()
    bt = Backtester(cfg)
    trades, _ = bt.run(bars)
    for t in trades:
        assert t.lots >= cfg.instrument.min_lot


# ---------- test_no_lookahead ----------

def test_no_lookahead():
    """ป้อน bar ทีละแท่ง (streaming) เทียบกับรัน batch ทีละแท่งเหมือนกัน →
    ต้องได้ sequence ของ pending-order placement / fills เหมือนกัน 100%
    (engine เป็น streaming อยู่แล้ว — จุดที่ต้องกันคือ fill ในแท่งที่วาง order)"""
    cfg = E3Config()
    bars = _script_clean_short_sweep()
    bt = Backtester(cfg)
    trades_batch, _ = bt.run(bars)

    # streaming: รันทีละ bar ด้วย backtester ใหม่
    bt2 = Backtester(cfg)
    trades_stream: list = []
    pos = None
    pending = None
    from e3.backtest import _OpenTrade
    book = _OpenTrade()
    for bar in bars:
        if pos is not None:
            pos.update_mfe_mae(bar)
            rec = bt2._manage_position(pos, bar, book)
            if rec is not None:
                trades_stream.append(rec)
                pos = None
                bt2.engine.on_position_closed(bar.ts)
        elif pending is not None:
            f = bt2._try_fill(pending, bar)
            if f is not None:
                pos = f
                pending = None
                bt2.engine.state.phase = bt2.engine.state.phase.__class__.IN_POSITION
            elif bar.ts >= pending.expires_ts:
                pending = None
                bt2.engine.state.pending = None
                bt2.engine.state.phase = bt2.engine.state.phase.__class__.IDLE
        if pos is None and pending is None:
            order = bt2.engine.on_bar(bar)
            if order is not None:
                pending = order
    assert [t.entry_ts for t in trades_batch] == [t.entry_ts for t in trades_stream]
    assert [t.entry_price for t in trades_batch] == [t.entry_price for t in trades_stream]


def test_order_not_filled_on_placement_bar():
    """SELL LIMIT ที่วางในแท่ง reclaim ห้าม fill ในแท่งนั้น แม้ราคาแตะ level (กัน lookahead)"""
    cfg = E3Config()
    bars = _script_clean_short_sweep()
    bt = Backtester(cfg)
    engine = bt.engine
    from e3.types import Phase
    placed_ts = None
    for bar in bars:
        order = engine.on_bar(bar)
        if order is not None and placed_ts is None:
            placed_ts = bar.ts
            # แท่งที่วาง order ต้องเป็นแท่ง reclaim — close ต่ำกว่า level
            assert order.limit_price == engine.state.asian_high
            assert bar.ts <= order.expires_ts - 900 * 4
    if placed_ts is not None:
        # ตรวจว่า backtest ไม่ fill ในแท่งวาง order
        bt2 = Backtester(cfg)
        trades, _ = bt2.run(bars)
        for t in trades:
            assert t.entry_ts > placed_ts


# ---------- fixture: clean short sweep scenario ----------

def _script_clean_short_sweep() -> list[Bar]:
    """สร้างวันที่ sweep ขึ้นแล้ว reclaim แบบ textbook — คำนวณตาม ATR ที่วัดได้จริง:
    seed quiet-block ท้าย → ที่ 08:00 atr_m15 ≈ 1.45, atr_d1 ≈ 2.42
      asian range 2000.5-2002.5 (range_ratio = 2/2.42 ≈ 0.83 ✓)
      sweep extreme 2003.5 (depth = 1.0/1.45 ≈ 0.69 ✓)
      reclaim close 2002.0 < 2002.5 → CONFIRMED → SELL LIMIT @2002.5
      SL = 2003.5 + 0.30×1.45 = 2003.94 (stop_dist ≈ 1.44)
      retest high 2002.8 → fill; ลงต่อ → TP1 @2001.06 ✓, TP2 @asian_mid 2001.5 ✓
    """
    b = Builder(_day_start_utc(2026, 3, 3) - 105 * 86400)
    b.seed_until(_day_start_utc(2026, 3, 3))   # seed จนถึงเที่ยงคืน 3 Mar พอดี (จบ quiet block)
    b.at(2026, 3, 3, 0, 0)      # เที่ยงคืน 3 Mar (asian เริ่ม)
    # Asian session 00:00-07:00 = 28 bars — range 2000.5-2002.5 (สลับ 2 ระดับ)
    for _ in range(7):          # 4 bars × 7 = 28
        b.flat(2001.0, 2, wick=0.5)
        b.flat(2002.0, 2, wick=0.5)
    # ก่อน London 07:00-08:00 = 4 bars เรียบ ๆ
    b.flat(2002.0, 4, wick=0.5)
    # London window 08:00-10:00
    b.move(2003.5, 2)           # sweep ขึ้น: high = 2003.5
    b.move(2002.0, 1)           # reclaim: close 2002.0 < asian_high 2002.5 → CONFIRMED
    b.move(2002.8, 1)           # retest: high 2002.8 ≥ limit 2002.5 → fill (แท่งถัดจากวาง)
    b.move(2001.0, 4)           # ลงต่อ → TP1 (2001.06) โดนก่อน แล้ว TP2 (2001.5)
    b.flat(2000.5, 10, wick=0.5)
    b.move(2003.0, 2)           # rebound → ชน SL (BE หลัง TP1) → ปิด 20% ที่เหลือ "stop_be"
    return b.bars
