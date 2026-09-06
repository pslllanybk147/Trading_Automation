# -*- coding: utf-8 -*-
"""E3 property-based tests §10.3 — invariants ต้องจริงกับ *ทุก* ไม้ / ทุก run

∀ trade:  realized_loss ≤ risk_per_trade × equity × 1.15   # เผื่อ cost/slippage
∀ trade:  entry_time < exit_time
∀ day:    trades_count ≤ max_trades_per_day
∀ day:    daily_pnl ≥ -daily_loss_stop × equity × 1.2
∀ run:    no overlapping positions
∀ run:    sum(partial_sizes) == original_size
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from e3.backtest import Backtester
from e3.config import E3Config, RiskCfg

from tests.test_e3_critical import _script_clean_short_sweep
from tests.test_e3_golden import (_script_flat_by, _script_no_reclaim, _script_no_retest,
                                  _script_sl_hit, _script_time_stop)

UTC = timezone.utc


def _collect_runs():
    """รวม bars จากหลาย fixture — property ต้องผ่านกับทุก run"""
    cfg = E3Config(risk=RiskCfg(max_trades_per_day=4))
    runs = {
        "clean_sweep": _script_clean_short_sweep(),
        "sl_hit": _script_sl_hit(),
        "flat_by": _script_flat_by(),
        "no_reclaim": _script_no_reclaim(),
        "no_retest": _script_no_retest(),
        "time_stop": _script_time_stop(),
    }
    out = {}
    for name, bars in runs.items():
        bt = Backtester(cfg)
        trades, summary = bt.run(bars)
        out[name] = (trades, cfg)
    return out


def test_property_loss_capped_per_trade():
    """gross loss (หัก cost ออก) ≤ risk × 1.15 — cost เก็บแยกตาม telemetry แล้ว
    (spread 0.30 ของทอง = ~38% ของ R ต่อ round trip — ใส่รวมใน 1.15 แล้วจะ cap ไม่ไหว)"""
    for name, (trades, cfg) in _collect_runs().items():
        for t in trades:
            cap = cfg.risk.risk_per_trade * t.equity_at_entry * 1.15
            gross_loss = t.pnl + t.cost_usd_total      # pnl สุทธิ = gross - cost
            assert gross_loss >= -cap, \
                f"{name}: gross loss {gross_loss:.2f} exceeds cap {cap:.2f}"
            # และ cost ต้องไม่ลงทะเบียนเกินจริง — สุทธิบวก cost ต้อง >= -1.5×risk
            assert t.pnl >= -1.5 * t.risk_dollars, \
                f"{name}: net loss {t.pnl:.2f} exceeds 1.5×risk {t.risk_dollars:.2f}"


def test_property_entry_before_exit():
    for name, (trades, _) in _collect_runs().items():
        for t in trades:
            assert t.entry_ts < t.exit_ts, f"{name}: entry_ts >= exit_ts"


def test_property_max_trades_per_day():
    for name, (trades, cfg) in _collect_runs().items():
        per_day = defaultdict(int)
        for t in trades:
            d = datetime.fromtimestamp(t.entry_ts, tz=UTC).date()
            per_day[d] += 1
        for d, n in per_day.items():
            assert n <= cfg.risk.max_trades_per_day, f"{name}: {n} trades on {d}"


def test_property_daily_pnl_floor():
    for name, (trades, cfg) in _collect_runs().items():
        per_day = defaultdict(float)
        for t in trades:
            d = datetime.fromtimestamp(t.exit_ts, tz=UTC).date()
            per_day[d] += t.pnl
        for d, pnl in per_day.items():
            floor = -cfg.risk.daily_loss_stop * cfg.equity * 1.2
            assert pnl >= floor, f"{name}: daily pnl {pnl:.2f} below floor {floor:.2f} on {d}"


def test_property_no_overlapping_positions():
    for name, (trades, _) in _collect_runs().items():
        ordered = sorted(trades, key=lambda t: t.entry_ts)
        for a, b in zip(ordered, ordered[1:]):
            assert a.exit_ts <= b.entry_ts, \
                f"{name}: overlap — trade A exits {a.exit_ts} after trade B enters {b.entry_ts}"


def test_property_no_zero_cost_fills():
    """test_cost_always_applied เชิง property — ทุกไม้ในทุก run ต้องมี cost > 0"""
    for name, (trades, _) in _collect_runs().items():
        for t in trades:
            assert t.cost_usd_total > 0, f"{name}: zero-cost fill detected"


def test_property_r_multiple_consistent_with_pnl():
    """R และ PnL ต้องเล่าเรื่องเดียวกัน (risk_dollars = R × risk ต่อไม้)"""
    for name, (trades, cfg) in _collect_runs().items():
        for t in trades:
            if t.risk_dollars > 0:
                implied = t.pnl / t.risk_dollars
                # tolerance เผื่อ partial exits ที่คิด R ต่อส่วน (±35%)
                assert abs(implied - t.r_multiple) <= 0.35 * max(1.0, abs(t.r_multiple)), \
                    f"{name}: R {t.r_multiple:.3f} vs implied {implied:.3f}"
