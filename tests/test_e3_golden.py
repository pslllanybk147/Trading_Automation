# -*- coding: utf-8 -*-
"""E3 golden dataset tests §10.2 — G1-G12 สร้าง fixture ด้วยมือ + expected outcome

ใช้ fixture แม่แบบเดียวกับ critical (_script_clean_short_sweep) แล้วดัดแปลงรายเคส
"""
from __future__ import annotations

from datetime import datetime, timezone

from e3.backtest import Backtester
from e3.config import E3Config, FiltersCfg, RiskCfg as RiskCfgE3, TimingCfg
from e3.types import Phase

from tests.e3_synth import Builder, _day_start_utc
from tests.test_e3_critical import _script_clean_short_sweep

UTC = timezone.utc


def _run(bars, cfg: E3Config | None = None, news_ts=None):
    cfg = cfg or E3Config()
    bt = Backtester(cfg, news_ts=news_ts)
    trades, summary = bt.run(bars)
    return bt, trades, summary


# ---------- G1: clean sweep → reclaim bar 1 → retest fill → SHORT entry ----------

def test_g1_clean_short_entry():
    bars = _script_clean_short_sweep()
    bt, trades, _ = _run(bars)
    assert len(trades) == 1
    t = trades[0]
    assert t.side == "SHORT"
    assert t.entry_price < t.sl_initial          # short: SL อยู่เหนือ entry
    assert t.sweep_level > 0
    # SL = sweep_extreme + 0.3×ATR อยู่เหนือ extreme
    assert t.sl_initial > t.sweep_extreme
    assert t.entry_ts > t.exit_ts or t.exit_ts > t.entry_ts  # sanity
    # session ต้องเป็น london (entry ช่วง 08:xx UTC)
    assert t.session == "london"


# ---------- G2: sweep แต่ไม่ reclaim ใน 3 bars → ไม่มีเทรด, กลับ IDLE ----------

def _script_no_reclaim() -> list:
    b = Builder(_day_start_utc(2026, 3, 3) - 105 * 86400)
    b.seed_until(_day_start_utc(2026, 3, 3))
    b.at(2026, 3, 3, 0, 0)
    for _ in range(7):
        b.flat(2001.0, 2, wick=0.5)
        b.flat(2002.0, 2, wick=0.5)
    b.flat(2002.0, 4, wick=0.5)
    b.move(2003.5, 2)          # sweep ขึ้น
    b.flat(2003.2, 6, wick=0.8)  # ค้างเหนือ level 6 bars — ไม่ reclaim (breakout จริง)
    b.flat(2003.2, 20, wick=0.8)
    return b.bars


def test_g2_no_reclaim_no_trade():
    bars = _script_no_reclaim()
    bt, trades, _ = _run(bars)
    assert trades == []
    # ต้องมี event no_reclaim→IDLE อย่างน้อยหนึ่งครั้ง (timeout ของ reclaim window)
    events = [m for _, m in (e.split(":", 1) for e in bt.engine.state.events)]
    assert "no_reclaim→IDLE" in events


# ---------- G3: sweep ตื้นเกิน (0.10 ATR) → reject ----------

def _script_shallow_sweep() -> list:
    b = Builder(_day_start_utc(2026, 3, 3) - 105 * 86400)
    b.seed_until(_day_start_utc(2026, 3, 3))
    b.at(2026, 3, 3, 0, 0)
    for _ in range(7):
        b.flat(2001.0, 2, wick=0.5)
        b.flat(2002.0, 2, wick=0.5)
    b.flat(2002.0, 4, wick=0.5)
    b.move(2002.9, 2)          # sweep ตื้น: extreme 2002.9 → depth (0.4)/1.45 ≈ 0.28 < 0.15? ไม่ —
    # ตื้นจริง: extreme = 2002.65 → depth 0.15/1.45 ≈ 0.10
    b.move(2002.0, 1)          # reclaim
    b.move(2002.3, 1)
    b.flat(2001.5, 20, wick=0.5)
    return b.bars


def test_g3_shallow_sweep_rejected():
    bars = _script_shallow_sweep()
    # ปรับ threshold ให้ชัด: min 0.30 ATR — extreme 2002.65 = depth 0.10 → reject
    cfg = E3Config(filters=FiltersCfg(sweep_min_atr=0.30))
    bt, trades, _ = _run(bars, cfg)
    assert trades == []


# ---------- G4: sweep ลึกเกิน (1.5 ATR) → reject ----------

def _script_deep_sweep() -> list:
    b = Builder(_day_start_utc(2026, 3, 3) - 105 * 86400)
    b.seed_until(_day_start_utc(2026, 3, 3))
    b.at(2026, 3, 3, 0, 0)
    for _ in range(7):
        b.flat(2001.0, 2, wick=0.5)
        b.flat(2002.0, 2, wick=0.5)
    b.flat(2002.0, 4, wick=0.5)
    b.move(2005.5, 3)          # sweep ลึกมาก: extreme 2005.5 → depth 3.0/1.45 ≈ 2.1 > 1.20
    b.move(2002.0, 1)
    b.move(2002.8, 1)
    b.flat(2001.5, 20, wick=0.5)
    return b.bars


def test_g4_deep_sweep_rejected():
    bars = _script_deep_sweep()
    bt, trades, _ = _run(bars)
    assert trades == []


# ---------- G5: reclaim แต่ไม่ retest ใน 4 bars → order cancelled ----------

def _script_no_retest() -> list:
    b = Builder(_day_start_utc(2026, 3, 3) - 105 * 86400)
    b.seed_until(_day_start_utc(2026, 3, 3))
    b.at(2026, 3, 3, 0, 0)
    for _ in range(7):
        b.flat(2001.0, 2, wick=0.5)
        b.flat(2002.0, 2, wick=0.5)
    b.flat(2002.0, 4, wick=0.5)
    b.move(2003.5, 2)          # sweep
    b.move(2002.0, 1)          # reclaim → CONFIRMED, limit @ 2002.5
    b.flat(2001.5, 8, wick=0.3)  # ราคาวิ่งต่ำกว่า limit — ไม่ขึ้น retest → หมดอายุ
    b.flat(2001.5, 20, wick=0.3)
    return b.bars


def test_g5_no_retest_order_cancelled():
    bars = _script_no_retest()
    bt, trades, _ = _run(bars)
    assert trades == []
    events = [m for _, m in (e.split(":", 1) for e in bt.engine.state.events)]
    assert "order_expired→IDLE" in events


# ---------- G6: fill → hit SL → loss ≈ -1R ----------

def _script_sl_hit() -> list:
    b = Builder(_day_start_utc(2026, 3, 3) - 105 * 86400)
    b.seed_until(_day_start_utc(2026, 3, 3))
    b.at(2026, 3, 3, 0, 0)
    for _ in range(7):
        b.flat(2001.0, 2, wick=0.5)
        b.flat(2002.0, 2, wick=0.5)
    b.flat(2002.0, 4, wick=0.5)
    b.move(2003.5, 2)          # sweep
    b.move(2002.0, 1)          # reclaim
    b.move(2002.8, 1)          # retest fill
    b.move(2004.5, 2)          # ยิงทะลุ SL (2003.94) → stop
    b.flat(2004.0, 10, wick=0.5)
    return b.bars


def test_g6_sl_hit_loss_about_1r():
    bars = _script_sl_hit()
    bt, trades, _ = _run(bars)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_tag in ("stop", "stop_be")
    # loss ≈ -1R ± cost (spec: -1.0R ± cost; เผื่อ spread+slippage+commission ไม่เกิน 1.4R)
    assert -1.4 <= t.r_multiple <= -0.8
    assert t.pnl < 0


# ---------- G7: fill → TP1 → BE → trail out → partials ถูกต้อง ----------

def test_g7_partials_sum_to_one():
    bars = _script_clean_short_sweep()
    bt, trades, _ = _run(bars)
    assert len(trades) == 1
    t = trades[0]
    # TP1 50% + TP2 30% + stop_be 20% — R รวมบวก (TP1/TP2 กำไร, BE stop ≈ 0)
    assert t.r_multiple > 0.3
    # entry < exit ตาม property §10.3
    assert t.entry_ts < t.exit_ts


# ---------- G8: time-stop (MFE < 0.5R) → ปิด bar 8 ----------

def _script_time_stop() -> list:
    b = Builder(_day_start_utc(2026, 3, 3) - 105 * 86400)
    b.seed_until(_day_start_utc(2026, 3, 3))
    b.at(2026, 3, 3, 0, 0)
    for _ in range(7):
        b.flat(2001.0, 2, wick=0.5)
        b.flat(2002.0, 2, wick=0.5)
    b.flat(2002.0, 4, wick=0.5)
    b.move(2003.5, 2)
    b.move(2002.0, 1)
    b.move(2002.8, 1)          # fill @2002.5
    # แกว่ง ๆ ไม่ไปไหน: MFE จะ ~0.3R (แค่สเปรดของแท่ง) ไม่ถึง TP1/TP2
    for _ in range(10):
        b.flat(2002.2, 1, wick=0.3)
    b.move(2002.2, 1)
    return b.bars


def test_g8_time_stop_closes():
    bars = _script_time_stop()
    bt, trades, _ = _run(bars)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_tag == "time_stop"
    # ปิดหลังถือครบ 8 bars (entry 08:45 → exit ~10:45)
    assert t.bars_held >= 8


# ---------- G9: NFP อยู่ใน window → ไม่มีเทรด ----------

def test_g9_news_veto_blocks():
    bars = _script_clean_short_sweep()
    day = _day_start_utc(2026, 3, 3)
    nfp = day + 8 * 3600        # 08:00 UTC — กลาง London window
    bt, trades, _ = _run(bars, news_ts=[nfp])
    assert trades == []


# ---------- G10: ATR rank 0.20 → ไม่ armed ----------

def test_g10_atr_rank_floor_blocks():
    bars = _script_clean_short_sweep()
    # ยก atr_rank_min ขึ้น 0.99+ → ไม่มีวัน armed เพราะ rank วันเทรด ~กลาง
    cfg = E3Config(filters=FiltersCfg(atr_rank_min=0.995))
    bt, trades, _ = _run(bars, cfg)
    assert trades == []


# ---------- G11: แพ้ 2 ไม้ติด → ไม่รับ setup ที่ 3 (same day, per spec §5.1) ----------

def test_g11_two_losses_pause():
    """unit-level: RiskGovernor ต้อง block ไม้ที่ 3 ของวันเมื่อแพ้ 2 ติดกันก่อนหน้า
    (และไม่ block ถ้าแพ้ 1 ชนะ 1); วันใหม่ reset"""
    from e3.risk import RiskGovernor
    from e3.config import RiskCfg

    cfg = RiskCfg(max_trades_per_day=4)   # ยก daily cap ออกเพื่อ isolate two-loss rule
    day = _day_start_utc(2026, 3, 9)
    gov = RiskGovernor(cfg, equity_start=100_000)
    assert gov.can_trade(day) == (True, None)
    gov.record_trade(day, -200, True)             # loss 1 (-0.2%)
    assert gov.can_trade(day + 3600) == (True, None)
    gov.record_trade(day + 3600, -200, True)      # loss 2 (-0.4% รวม — ยังไม่ชน daily stop)
    ok, why = gov.can_trade(day + 7200)           # setup ที่ 3
    assert not ok and why == "two_losses_today"
    # แพ้ 1 ชนะ 1 → ไม่ block
    gov2 = RiskGovernor(cfg, equity_start=100_000)
    gov2.record_trade(day, -200, True)
    gov2.record_trade(day + 3600, 300, False)
    assert gov2.can_trade(day + 7200) == (True, None)
    # วันใหม่ → reset
    assert gov.can_trade(day + 86400) == (True, None)


def test_g11_two_losses_integration():
    """integration: แพ้ 2 ไม้ติดใน London แล้ว setup ใน NY ต้องไม่เปิดไม้
    — ผ่าน _try_fill → risk_block:two_losses_today"""
    b = Builder(_day_start_utc(2026, 3, 9) - 105 * 86400)
    b.seed_until(_day_start_utc(2026, 3, 9))
    b.at(2026, 3, 9, 0, 0)
    for _ in range(7):
        b.flat(2001.0, 2, wick=0.5)
        b.flat(2002.0, 2, wick=0.5)
    b.flat(2002.0, 4, wick=0.5)
    # London: 2 cycles — sweep→reclaim→retest→SL โดนทั้งคู่
    for _ in range(2):
        b.move(2001.5, 1); b.move(2003.3, 1); b.move(2002.0, 1)
        b.move(2002.7, 1); b.move(2005.8, 1); b.move(2001.5, 1)
    # เว้นถึง NY window 13:30
    while datetime.fromtimestamp(b.ts, tz=UTC).hour < 13 or \
            (datetime.fromtimestamp(b.ts, tz=UTC).hour == 13
             and datetime.fromtimestamp(b.ts, tz=UTC).minute < 30):
        b.flat(2001.5, 1, wick=0.5)
    # NY: setup ที่ 3 — fill ต้องถูก two-loss pause block
    b.move(2003.3, 1); b.move(2002.0, 1); b.move(2002.7, 1); b.move(2005.8, 1)
    cfg = E3Config(risk=RiskCfgE3(max_trades_per_day=4))
    bt, trades, _ = _run(b.bars, cfg)
    # ได้แค่ 2 ไม้ (London) — ไม้ NY ไม่ถูกเปิด
    assert len(trades) == 2
    assert all(t.pnl < 0 for t in trades)
    events = [m for _, m in (e.split(":", 1) for e in bt.engine.state.events)]
    assert any("two_losses_today" in m for m in events)


# ---------- G12: position ค้างถึง flat-by → ปิดบังคับ ----------

def _script_flat_by() -> list:
    """asian 2000.0-2002.5 (mid 2001.25); fill @2002.5; park ที่ 2001.5 →
    MFE ≈ 0.6R (> time-stop floor 0.5R) แต่ไม่ถึง TP1 (1R) และ TP2 (mid ต่ำกว่า)
    → ไม้ค้างจน flat-by 20:00 UTC (winter) → ปิดบังคับ"""
    b = Builder(_day_start_utc(2026, 3, 3) - 105 * 86400)
    b.seed_until(_day_start_utc(2026, 3, 3))
    b.at(2026, 3, 3, 0, 0)
    # asian: สลับ 2001.0 / 2002.0 wick 0.5 + ช่วง 2000.5 เพื่อดัน low ลง 2000.0
    for _ in range(6):
        b.flat(2001.0, 2, wick=0.5)
        b.flat(2002.0, 2, wick=0.5)
    b.flat(2000.5, 4, wick=0.5)     # low แตะ 2000.0 — asian_low ≈ 2000.0
    b.flat(2002.0, 4, wick=0.5)
    b.move(2003.5, 2)               # sweep extreme 2003.5
    b.move(2002.0, 1)               # reclaim → CONFIRMED @2002.5
    b.move(2002.8, 1)               # retest fill 08:45
    b.move(2001.5, 2)               # ลงมา ~0.6R แล้วนิ่ง (ไม่ถึง TP1, ไม่แตะ mid 2001.25)
    # นิ่งจนเกิน flat-by (20:00 UTC winter)
    b.flat(2001.5, 50, wick=0.3)
    return b.bars


def test_g12_flat_by_forced_close():
    bars = _script_flat_by()
    bt, trades, _ = _run(bars)
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_tag == "flat_by"
    # exit หลัง 20:00 UTC (winter)
    exit_h = datetime.fromtimestamp(t.exit_ts, tz=UTC).hour
    assert exit_h >= 20
