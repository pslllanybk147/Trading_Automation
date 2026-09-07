# -*- coding: utf-8 -*-
"""E1 backtest — driver รัน engine บนข้อมูลจริงจาก loader + สรุปผล

กติกา:
  - feed แบบ event-time รวม (merge funding events + perp klines ตาม ts) —
    funding ที่ settle เท่านั้นที่เปลี่ยน state ได้
  - spot/perp kline ปิดแล้วเท่านั้น (แท่งสุดท้ายของไฟล์ถ้ายังไม่ครบเวลา = ข้าม)
  - ราคา fill = close ของแท่งที่ปิดแล้ว (conservative สำหรับค่าธรรมเนียม; ไม่มี
    slippage model — รายงานแยกต่างหาก)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .config import E1Config
from .engine import E1Engine, Outcome, utc_ms_to_iso
from .loader import E1Loader


@dataclass
class BacktestResult:
    symbol: str
    from_ms: int
    to_ms: int
    n_funding: int
    n_bars: int
    n_trades: int
    funding_total: float
    fees_total: float
    equity_start: float
    equity_end: float
    apy_on_pool: float          # %ต่อปี บน pool (equity×pool_pct) ไม่ใช่ notional
    sharpe_daily: float
    max_dd_pct: float
    liq_count: int
    n_topup: int
    n_delev: int
    reasons: dict[str, int]
    days: float

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["from_iso"] = utc_ms_to_iso(self.from_ms)
        d["to_iso"] = utc_ms_to_iso(self.to_ms)
        return d


def run_backtest(loader: E1Loader, symbol: str, cfg: E1Config,
                 start_ms: int | None = None, end_ms: int | None = None) -> BacktestResult:
    funding = loader.load_funding(symbol)
    perp = loader.load_klines(symbol, "perp", "1h")
    spot = loader.load_klines(symbol, "spot", "1h")
    if not funding or not perp or not spot:
        raise SystemExit(f"ข้อมูล {symbol} ไม่ครบ (funding/perp/spot) — sync ก่อน")

    eng = E1Engine(cfg)
    eng.set_symbol(symbol)

    # ---- merge เป็น event stream ตามเวลา (ไม่ lookahead: แท่งที่ปิดแล้วเท่านั้น) ----
    # bar open_time t คือแท่งที่ปิดเมื่อ t+interval — ให้ "พร้อมใช้" ที่ t+1h
    # เราจึงประเมิน ladder ที่ ts = open_time + 1h แต่ยังต้องเรียงก่อน funding ที่
    # settle หลังจากนั้น (funding เกิดทุก 8h พอดี — ไม่มีทางข้าม)
    events: list[tuple[int, int, object]] = []
    for k in perp:
        events.append((k.open_time_ms + 3_600_000, 0, k))     # bar พร้อมหลังปิด
    for k in spot:
        events.append((k.open_time_ms + 3_600_000, 1, k))
    for f in funding:
        events.append((f.funding_time_ms, 2, f))              # settle หลังปิดแท่งเสมอ
    events.sort(key=lambda e: (e[0], e[1]))

    spot_by_open: dict[int, object] = {k.open_time_ms: k for k in spot}
    perp_by_open: dict[int, object] = {k.open_time_ms: k for k in perp}

    last_perp = last_spot = None
    equity_curve: list[tuple[int, float]] = []
    n_funding = 0

    for ts, kind, obj in events:
        if kind == 0:                      # perp bar พร้อม
            last_perp = obj
            sp = spot_by_open.get(obj.open_time_ms)
            if sp is not None:
                last_spot = sp
                eng.update(obj, sp)
                eq = eng.equity(obj.close, sp.close)
                equity_curve.append((obj.open_time_ms + 3_600_000, eq))
        elif kind == 1:                    # spot bar พร้อม
            last_spot = obj
        else:                              # funding settle
            last_p = last_perp
            last_s = last_spot
            if last_p is None or last_s is None:
                continue
            n_funding += 1
            eng.on_funding(obj, last_p, last_s)

    if not equity_curve:
        raise SystemExit("ไม่มีแท่งที่ประเมินได้ — เช็คช่วงเวลาข้อมูล")

    # ---- summary ----
    eqs = [e for _, e in equity_curve]
    start, end = eqs[0], eqs[-1]
    from_ms, to_ms = equity_curve[0][0], equity_curve[-1][0]
    days = (to_ms - from_ms) / 86_400_000.0

    pool = cfg.equity * cfg.pool_pct
    ret_total = (end - start) / pool if pool > 0 else 0.0
    apy = ((1.0 + ret_total) ** (365.0 / max(days, 1.0)) - 1.0) if ret_total > -1 else -1.0

    # daily equity (แท่งสุดท้ายของแต่ละวัน) → Sharpe/MaxDD
    daily: dict[int, float] = {}
    for t, e in equity_curve:
        daily[t // 86_400_000] = e
    dvals = [daily[k] for k in sorted(daily)]
    rets = [(b / a - 1.0) for a, b in zip(dvals, dvals[1:]) if a > 0]
    sharpe = 0.0
    if len(rets) > 2:
        m = sum(rets) / len(rets)
        var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
        sd = math.sqrt(var)
        if sd > 0:
            sharpe = m / sd * math.sqrt(365.0)

    peak = -1.0
    maxdd = 0.0
    for e in dvals:
        peak = max(peak, e)
        if peak > 0:
            maxdd = max(maxdd, (peak - e) / peak)

    reasons: dict[str, int] = {}
    for o in eng.outcomes:
        reasons[o.reason] = reasons.get(o.reason, 0) + 1

    return BacktestResult(
        symbol=symbol, from_ms=from_ms, to_ms=to_ms, n_funding=n_funding,
        n_bars=len(perp), n_trades=len(eng.outcomes),
        funding_total=eng.funding_received, fees_total=eng.fees_open + eng.fees_close,
        equity_start=start, equity_end=end, apy_on_pool=apy,
        sharpe_daily=sharpe, max_dd_pct=maxdd * 100.0,
        liq_count=eng.liq_count,
        n_topup=sum(o.n_topup for o in eng.outcomes),
        n_delev=sum(o.n_delev for o in eng.outcomes),
        reasons=reasons, days=days,
    )
