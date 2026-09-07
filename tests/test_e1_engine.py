# -*- coding: utf-8 -*-
"""E1 engine + backtest driver tests — fixture สังเคราะห์ ตรวจพฤติกรรมกลไก

ครอบคลุม: warmup/entry filters (E1-E5), funding collection (8h/4h), exit X1/X2/X4,
margin ladder (warn/topup/deleverage), liq (high-based), hard stop,
budget/leverage sizing, two-wallet accounting, no re-entry same settle

หมายเหตุ fixture: episode = ช่วงที่ f_ma7d ≥ เกณฑ์ (ดู engine) — rate บวกคงที่
จึง "เปิด episode เดียวยาว" ไม่มีวันปิด → test ที่ต้องการ median history ใช้
การจัด state โดยตรง (poke) แทนการป้อนข้อมูลจนครบ
"""
from __future__ import annotations

import pytest

from e1.config import E1Config
from e1.engine import E1Engine
from e1.data_schema import FundingEvent, Kline
from e1.margin import liq_price_short, margin_ratio_short

H1 = 3_600_000
H8 = 8 * H1
T0 = 1_600_000_000_000          # 2020-09-13 (funding settle ที่ T0, T0+8h, ...)


def _mkcfg(**kw) -> E1Config:
    base = dict(equity=10_000.0, pool_pct=0.50, cash_buffer_pct=0.25,
                min_notional=50.0)
    base.update(kw)
    return E1Config(**base)


def _kl(ts_ms: int, px: float, market: str = "perp", symbol: str = "BTCUSDT",
        low: float | None = None, high: float | None = None) -> Kline:
    lo = low if low is not None else px * 0.999
    hi = high if high is not None else px * 1.001
    return Kline(symbol, ts_ms, px, hi, lo, px, 10.0, market)


def _feed(eng: E1Engine, ts: int, rate: float, perp_px=20_000.0, spot_px=20_000.0,
          perp_low=None, perp_high=None, settle_ms=None):
    """ป้อน 1 แท่ง (ปิดแล้ว) + 1 funding settle"""
    perp = _kl(ts - H1, perp_px, "perp", low=perp_low, high=perp_high)
    spot = _kl(ts - H1, spot_px, "spot")
    eng.update(perp, spot)
    eng.on_funding(FundingEvent("BTCUSDT", settle_ms or ts, rate), perp, spot)
    return perp, spot


def _warm_flat(eng: E1Engine, rate=0.0004, px=20_000.0, n=25):
    """ป้อน n events (warmup ครบ) — ยัง FLAT (episode แรกยังเปิดอยู่ ไม่มี history)"""
    for i in range(n):
        b = 0.003 if i % 2 else -0.003        # basis noise ±0.3%
        _feed(eng, T0 + i * H8, rate, px * (1 + b), px)
    return eng


def _poke_ok(eng: E1Engine):
    """จัด state ให้ผ่าน E5 โดยตรง (history median 12 วัน) — สำหรับ test กลไกถัดไป"""
    eng._ep_history = [12.0, 14.0, 16.0]
    return eng


# ---------------- sizing ----------------

def test_sizing_targets_max_leverage_and_keeps_buffer():
    eng = E1Engine(_mkcfg())
    deploy = eng.cash * 0.75
    s = eng._sizing(20_000.0)
    assert s is not None
    qty, margin, spot_cash, fee = s
    notional = qty * 20_000.0
    assert margin == pytest.approx(notional / 2.0)          # lev 2×
    assert spot_cash == pytest.approx(notional)             # spot เต็ม notional
    assert notional == pytest.approx(deploy / (1 + 0.5 + 0.0015), rel=1e-9)
    assert eng.cash - (margin + spot_cash + fee) > 0        # buffer เหลือจริง
    assert margin_ratio_short(20_000.0, 20_000.0, qty, margin, "BTCUSDT") > 2.2


# ---------------- entry filters ----------------

def test_entry_warmup_blocks_until_ma_full():
    eng = E1Engine(_mkcfg(min_completed_episodes=0))   # ปิด E5 — ทดสอบ warmup เท่านั้น
    for i in range(21):
        _feed(eng, T0 + i * H8, 0.0004)
        if i < 20:
            assert eng.state == "FLAT"
    assert eng.state == "IN_POSITION"


def test_entry_blocks_when_funding_below_min():
    eng = E1Engine(_mkcfg(min_completed_episodes=0))
    for i in range(40):
        _feed(eng, T0 + i * H8, 0.00008)     # 8.76%/ปี < 9%
    assert eng.state == "FLAT"


def test_entry_stability_fail_closed_when_mixed():
    eng = E1Engine(_mkcfg(min_completed_episodes=0))
    for i in range(40):
        _feed(eng, T0 + i * H8, 0.0004 if i % 3 == 0 else -0.0002)
    assert eng.state == "FLAT"               # stability ≈ 0.33 < 0.8


def test_entry_blocked_by_extreme_basis_z():
    """ทดสอบฟิลเตอร์ E4 ตรง ๆ: warmup ด้วย basis noise ±0.1% (ยัง FLAT เพราะ
    ไม่มี episode history) แล้วโยนเงื่อนไขเข้าด้วย basis ปัจจุบัน 2 แบบ"""
    eng = _warm_flat(E1Engine(_mkcfg()), n=50)      # FLAT ตลอด, window = noise
    assert eng.state == "FLAT"
    ts = T0 + 50 * H8
    # กรณี 1: basis ปัจจุบัน +0.4% (perp แพงผิดปกติ) → z ≈ 4 → บล็อก
    perp = _kl(ts - H1, 20_000.0 * 1.004, "perp")
    spot = _kl(ts - H1, 20_000.0, "spot")
    eng._on_bar_passive(perp, spot)
    eng._try_entry(FundingEvent("BTCUSDT", ts, 0.0004), perp, spot)
    assert eng.state == "FLAT"
    # กรณี 2: basis ปกติ +0.1% → z ต่ำ → ผ่าน (poke episode history ให้ E5 ผ่าน)
    eng._ep_history = [12.0, 14.0, 16.0]
    perp2 = _kl(ts, 20_000.0 * 1.001, "perp")
    spot2 = _kl(ts, 20_000.0, "spot")
    eng._on_bar_passive(perp2, spot2)
    eng._try_entry(FundingEvent("BTCUSDT", ts + H8, 0.0004), perp2, spot2)
    assert eng.state == "IN_POSITION"


def test_entry_needs_episode_history_fail_closed():
    eng = _warm_flat(E1Engine(_mkcfg()))     # warmup ครบ แต่ episode แรกยังเปิด
    assert eng.state == "FLAT"               # ไม่มี history → บล็อก (fail-closed)


# ---------------- funding collection ----------------

def test_funding_credits_perp_wallet_8h():
    eng = _poke_ok(E1Engine(_mkcfg()))
    _warm_flat(eng, n=25)
    assert eng.state == "IN_POSITION"
    p0 = eng.pos
    before = p0.margin
    rec_expect = 0.0004 * p0.qty * 20_000.0
    ts = T0 + 200 * H8
    _feed(eng, ts, 0.0004)
    assert eng.pos.margin == pytest.approx(before + rec_expect)
    assert eng.funding_received > 0


def test_funding_4h_interval_annualizes_correctly():
    eng = _poke_ok(E1Engine(_mkcfg()))
    for i in range(25):
        ts = T0 + i * 4 * H1
        _feed(eng, ts, 0.0002)               # 0.0002×6×365 = 43.8%/ปี
    assert eng.state == "IN_POSITION"


def test_funding_exit_on_decay():
    eng = _poke_ok(E1Engine(_mkcfg()))
    _warm_flat(eng, n=25)
    assert eng.state == "IN_POSITION"
    for i in range(30):
        ts = T0 + (100 + i) * H8
        _feed(eng, ts, -0.0002)
        if eng.state == "FLAT":
            break
    assert eng.state == "FLAT"
    assert eng.outcomes[-1].reason == "funding_decay"


# ---------------- ladder / liq / hard stop ----------------

def test_ladder_topup_then_deleverage_then_close():
    """บันได 4 ชั้น: ไต่ราคา +2% ถึงใกล้โซน (ratio ≤2.2 แคบชิด liq ที่ lev 2×)
    แล้วค่อย ๆ เหลื่อม +0.15% → warn → topup ซ้ำ → delev ซ้ำ → ไม้เล็กเกินปิด"""
    eng = _poke_ok(E1Engine(_mkcfg(hard_stop_pct=1.0)))
    _warm_flat(eng, n=25)
    ts = T0 + 400 * H8
    kinds_seen: list[str] = []
    px = 20_000.0
    step = 0
    while px < 20_000.0 * 1.47 and eng.state == "IN_POSITION":
        px *= 1.02
        step += 1
        _feed(eng, ts + step * H8, 0.0004, perp_px=px, spot_px=20_000.0)
    while eng.state == "IN_POSITION" and step < 400:
        px *= 1.0015
        step += 1
        before = len(eng.ladder_log)
        _feed(eng, ts + step * H8, 0.0004, perp_px=px, spot_px=20_000.0)
        for e in eng.ladder_log[before:]:
            if not kinds_seen or kinds_seen[-1] != e.kind:
                kinds_seen.append(e.kind)
    assert kinds_seen[:2] == ["warn", "topup"], kinds_seen
    assert "deleverage" in kinds_seen, kinds_seen
    assert eng.state == "FLAT", "ไต่ต่อเนื่องต้องจบด้วยการปิดไม้จากบันได"
    assert eng.outcomes[-1].reason in ("deleverage_too_small", "ladder_close",
                                       "liquidation")


def test_liq_wipes_perp_wallet_only():
    """ราคาวิ่งชน liq intrabar (high ทะลุ) — wallet perp หายหมด แต่ spot ขายคืนได้"""
    eng = _poke_ok(E1Engine(_mkcfg(max_leverage=3.0, hard_stop_pct=1.0)))
    _warm_flat(eng, n=25)
    p = eng.pos
    p.margin = p.margin * 0.4          # เสมือนผ่านพายุมาแล้ว → liq เข้ามาใกล้
    liq = liq_price_short(p.entry, p.qty, p.margin, "BTCUSDT")
    assert liq < p.entry * 1.15        # 3× + wallet 40% → liq ≈ +13%
    ts = T0 + 400 * H8
    _feed(eng, ts, 0.0004, perp_px=liq * 0.999, spot_px=20_000.0,
          perp_high=liq * 1.0005)      # ปิดใต้ liq แต่ high ทะลุ → โดน
    assert eng.state == "FLAT"
    out = eng.outcomes[-1]
    assert out.reason == "liquidation" and out.liq is True
    assert eng.liq_count == 1
    assert eng.cash > 0                # spot ยังขายคืนได้
    assert out.pnl < 0


def test_hard_stop_exits_before_ladder():
    cfg = _mkcfg(hard_stop_pct=0.02)
    eng = _poke_ok(E1Engine(cfg))
    _warm_flat(eng, n=25)
    ts = T0 + 400 * H8
    # +4% บน notional (~2,500) = −100 ≈ 2% ของ pool (5,000) → hard stop ต้องยิง
    _feed(eng, ts, 0.0004, perp_px=20_800.0, spot_px=20_000.0)
    assert eng.state == "FLAT"
    assert eng.outcomes[-1].reason in ("hard_stop", "ladder_close", "liquidation")


# ---------------- ledger conservation ----------------

def test_ledger_conserves_cash_through_full_cycle():
    eng = _poke_ok(E1Engine(_mkcfg()))
    px = 20_000.0
    cash0 = eng.cash
    _warm_flat(eng, n=25, px=px)
    invested0 = cash0 - eng.cash
    assert invested0 == pytest.approx(eng._pos_invested)
    # ถือผ่าน funding + ราคาแกว่ง (ไม่ชน ladder/liq/hard stop)
    for i in range(10):
        ts = T0 + (400 + i) * H8
        pp = px * (1 + (0.002 if i % 2 else -0.002))
        sp = px * (1 + (0.001 if i % 2 else -0.001))
        _feed(eng, ts, 0.0004, perp_px=pp, spot_px=sp)
        assert eng.state == "IN_POSITION"
    # equity จุดกลาง = cash + wallet + unrealized − fee ปิดโดยประมาณ
    eq_mid = eng.equity(20_000.0, 20_000.0)
    p = eng.pos
    expect_mid = eng.cash + p.margin + (p.entry - 20_000.0) * p.qty \
        + p.spot_qty * 20_000.0 - (p.qty * 20_000.0 * 0.0005
                                   + p.spot_qty * 20_000.0 * 0.001)
    assert eq_mid == pytest.approx(expect_mid, rel=1e-9)
    # บังคับออกด้วย decay ที่ราคาเดิม
    for i in range(30):
        ts = T0 + (410 + i) * H8
        _feed(eng, ts, -0.0003, perp_px=px, spot_px=px)
        if eng.state == "FLAT":
            break
    assert eng.state == "FLAT"
    # บัญชี: cash จบ = cash0 + ผลรวม pnl ทุก episode (pnl รวม fee+funding แล้ว)
    assert eng.cash == pytest.approx(cash0 + sum(o.pnl for o in eng.outcomes),
                                     rel=1e-9)


def test_no_reentry_same_settle_after_exit():
    eng = _poke_ok(E1Engine(_mkcfg()))
    _warm_flat(eng, n=25)
    exit_ts = None
    for i in range(30):
        ts = T0 + (100 + i) * H8
        _feed(eng, ts, -0.0002)
        if eng.state == "FLAT":
            exit_ts = ts
            break
    assert exit_ts is not None
    # settle "เดียวกัน" (ts เดิม) ห้าม re-enter
    perp, spot = _kl(exit_ts - H1, 20_000.0, "perp"), _kl(exit_ts - H1, 20_000.0, "spot")
    eng._try_entry(FundingEvent("BTCUSDT", exit_ts, 0.0004), perp, spot)
    assert eng.state == "FLAT"


# ---------------- backtest driver ----------------

def test_backtest_driver_smoke(tmp_path):
    from e1.backtest import run_backtest
    from e1.loader import E1Loader

    loader = E1Loader(str(tmp_path / "c.db"))
    # rate 0.05% ต่อเนื่อง 100 events (episode เปิดยาว หลัง warmup) → เข้าไม้
    # แล้ว rate ค่อย ๆ ลดผ่าน 0.04%/8h (12%/ปี) → 0.01% (3%/ปี) → decay exit
    evs = []
    for i in range(100):
        evs.append((T0 + i * H8, 0.0005))
    for i in range(100, 140):
        evs.append((T0 + i * H8, 0.00015))
    for i in range(140, 260):
        evs.append((T0 + i * H8, 0.00002))
    conn = loader._conn
    conn.executemany("INSERT OR REPLACE INTO funding VALUES (?,?,?,?)",
                     [("BTCUSDT", ts, r, None) for ts, r in evs])
    n_hours = 260 * 8 + 24
    rows = []
    for h in range(n_hours):
        ts = T0 - H1 + h * H1
        rows.append(("BTCUSDT", "perp", "1h", ts, 20_000.0, 20_010.0, 19_990.0,
                     20_000.0, 10.0))
        rows.append(("BTCUSDT", "spot", "1h", ts, 20_000.0, 20_010.0, 19_990.0,
                     20_000.0, 10.0))
    conn.executemany("INSERT OR REPLACE INTO klines VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()

    res = run_backtest(loader, "BTCUSDT", _mkcfg(min_completed_episodes=0))
    assert res.n_trades >= 1
    assert res.funding_total > 0
    assert res.liq_count == 0
    assert res.n_bars > 1000
    assert res.apy_on_pool is not None
    loader.close()
