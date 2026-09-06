# -*- coding: utf-8 -*-
"""E3 backtest M15 driver — bar-by-bar, no lookahead, conservative fills.

กติกาการ fill ที่จงใจอนุรักษนิยม (ตาม kit):
  - Sweep detection ใช้ M15 close-based (ทำใน engine แล้ว)
  - Intrabar SL ชนก่อน TP เสมอ (adverse-first) → ผลจริงอาจดีกว่า backtest —
    ทิศทาง error ที่ถูกต้อง
  - Limit fill ต้องราคา "ทะลุจริง" (trade-through) ไม่ใช่แค่แตะ
  - ห้าม fill limit ในแท่งที่วาง order (กัน lookahead)
  - ทุก fill มี cost เสมอ (test_cost_always_applied)
"""
from __future__ import annotations

from .clock import at_flat_by, sessions_for_day, trade_window_for
from .config import E3Config
from .costs import CostModel
from .e3 import E3Engine, PendingOrder
from .metrics import Summary, TradeRecord, summarize
from .position import Position
from .risk import RiskGovernor
from .sizing import compute_lots
from .types import Bar, Phase, Side, check_monotonic

BAR_SECS = 900


class _OpenTrade:
    """สะสม partial fills ของไม้ที่กำลังเปิด — attribution ต่อไม้ (ไม่ใช่ต่อ run)"""

    def __init__(self):
        self.pnl = 0.0
        self.r = 0.0
        self.cost = 0.0

    def add(self, pnl: float, r: float, cost: float) -> None:
        self.pnl += pnl
        self.r += r
        self.cost += cost

    def take(self) -> tuple[float, float, float]:
        out = (self.pnl, self.r, self.cost)
        self.pnl = self.r = self.cost = 0.0
        return out


class Backtester:
    def __init__(self, cfg: E3Config, news_ts: list[int] | None = None,
                 spread_profile: dict[int, float] | None = None):
        self.cfg = cfg
        self.engine = E3Engine(cfg, news_ts=news_ts)
        self.costs = CostModel(cfg.costs)
        self.risk = RiskGovernor(cfg.risk, cfg.equity)
        self.news_ts = sorted(news_ts or [])
        self.spread_profile = spread_profile or {}
        self.equity = cfg.equity

    def _spread_at(self, ts: int) -> float:
        hour = (ts // 3600) % 24
        return self.spread_profile.get(hour, self.cfg.costs.spread_usd)

    def run(self, bars: list[Bar]) -> tuple[list[TradeRecord], Summary]:
        check_monotonic(bars)
        trades: list[TradeRecord] = []
        pos: Position | None = None
        pending: PendingOrder | None = None
        book = _OpenTrade()

        for bar in bars:
            # ---------- manage open position ----------
            if pos is not None:
                pos.update_mfe_mae(bar)
                closed = self._manage_position(pos, bar, book)
                if closed is not None:
                    t = closed
                    trades.append(t)
                    self.equity += t.pnl
                    self.risk.record_trade(t.exit_ts, t.pnl, is_loss=t.pnl < 0)
                    self.engine.on_position_closed(bar.ts)
                    pos = None

            # ---------- pending limit order ----------
            elif pending is not None:
                filled = self._try_fill(pending, bar)
                if filled is not None:
                    pos = filled
                    pending = None
                    self.engine.state.phase = Phase.IN_POSITION
                    self.engine.state.log(bar.ts, "IN_POSITION")
                elif bar.ts >= pending.expires_ts:
                    self.engine.state.log(bar.ts, "order_expired→IDLE")
                    self.engine.state.pending = None
                    self.engine.state.phase = Phase.IDLE
                    pending = None

            # ---------- signal engine (เฉพาะตอน flat) ----------
            if pos is None and pending is None:
                order = self.engine.on_bar(bar)
                if order is not None:
                    pending = order

        return trades, summarize(trades, self.cfg.equity)

    # ---------- fill sim ----------

    def _try_fill(self, p: PendingOrder, bar: Bar) -> Position | None:
        if bar.ts <= p.placed_ts:      # ห้าม fill ในแท่งที่วาง (กัน lookahead)
            return None
        if p.side is Side.SHORT:
            if bar.high <= p.limit_price:   # ไม่ trade-through = ไม่มี retest
                return None
            raw = p.limit_price
        else:
            if bar.low >= p.limit_price:
                return None
            raw = p.limit_price
        # spread guard ณ วินาทีส่งคำสั่ง (§5.1)
        spread = self._spread_at(bar.ts)
        atr = self.engine.atr_m15.value
        if spread > self.cfg.filters.spread_guard_atr * atr:
            self.engine.state.log(bar.ts, "spread_guard_reject")
            return None
        # daily/loss limits (§6) — เช็คก่อนวางไม้จริง
        ok, why = self.risk.can_trade(bar.ts)
        if not ok:
            self.engine.state.log(bar.ts, f"risk_block:{why}")
            return None
        # sizing (ห้าม round up)
        stop_distance = abs(raw - p.sl_price)
        scale = self.risk.risk_scale(bar.ts, self.equity)
        if scale <= 0:
            self.engine.state.log(bar.ts, "risk_scale_0_skip")
            return None
        sr = compute_lots(self.equity, stop_distance, self.cfg, risk_scale=scale)
        if sr.skipped:
            self.engine.state.log(bar.ts, f"skip:{sr.reason}")
            return None
        fill_price, cost = self.costs.entry_price(raw, p.side, is_market=False, spread_usd=spread)
        st = self.engine.state
        return Position(
            side=p.side, entry_ts=bar.ts, entry_price=fill_price,
            initial_size=sr.lots, sl_price=p.sl_price, risk_per_oz=stop_distance,
            equity_at_entry=self.equity, atr_m15_at_entry=atr,
            asian_mid=self._asian_mid(),
        )

    def _asian_mid(self) -> float:
        st = self.engine.state
        if st.asian_high is not None and st.asian_low is not None:
            return (st.asian_high + st.asian_low) / 2.0
        return 0.0

    # ---------- exits ----------

    def _manage_position(self, pos: Position, bar: Bar, book: _OpenTrade) -> TradeRecord | None:
        cfg = self.cfg
        inst = cfg.instrument
        spread = self._spread_at(bar.ts)
        atr = pos.atr_m15_at_entry
        oz_total = pos.initial_size * inst.contract_size
        sgn = 1.0 if pos.side is Side.LONG else -1.0

        def partial_exit(raw: float, frac: float, tag: str, is_market: bool) -> float:
            """ปิดบางส่วน — คืน pnl ของส่วนนั้น; เก็บ r/cost ใน book"""
            exit_px, c = self.costs.exit_price(raw, pos.side, is_market=is_market, spread_usd=spread)
            pnl = (exit_px - pos.entry_price) * sgn * frac * oz_total
            r = pos.r_multiple(exit_px) * frac
            cost = c.total * frac * oz_total
            pos.close_frac(frac, bar.ts, exit_px, tag)
            book.add(pnl, r, cost)
            return pnl

        # ---- SL ก่อนเสมอ (adverse-first, market exit) ----
        if pos.is_stop_hit(bar):
            exit_px, c = self.costs.exit_price(pos.sl_price, pos.side, True, spread)
            pnl = (exit_px - pos.entry_price) * sgn * pos.remaining * oz_total
            frac = pos.remaining
            pos.close_frac(frac, bar.ts, exit_px, "stop")
            book.add(pnl, pos.r_multiple(exit_px) * frac, c.total * frac * oz_total)
            pnl_t, r_t, cost_t = book.take()
            return self._make_trade(pos, bar.ts, exit_px, pnl_t, r_t, cost_t,
                                    "stop_be" if pos.sl_moved_be else "stop")

        # ---- TP1: ปิด 50% ของขนาดเริ่มต้น + ย้าย SL → BE (fraction อิง original size —
        #      ลำดับ TP1/TP2 สลับกันได้ตามราคาจริง รวมกันยัง ≤ 100%) ----
        if not pos.sl_moved_be and pos.is_tp1_hit(bar, cfg.timing.tp1_r):
            partial_exit(pos.price_at_r(cfg.timing.tp1_r), 0.5, "tp1", is_market=False)
            pos.move_sl_be()

        # ---- TP2: asian_mid ปิด 30% ของขนาดเริ่มต้น ----
        if not pos.tp2_done and pos.is_tp2_hit(bar):
            partial_exit(pos.asian_mid, cfg.timing.tp2_frac, "tp2", is_market=False)
            pos.tp2_done = True

        # ---- trail ทำงานหลัง BE เท่านั้น (กัน SL ขยับไปฝั่งขาดทุน) ----
        if pos.sl_moved_be and pos.remaining > 0.01:
            pos.trail_stop(atr, cfg.timing.trail_atr)

        # ---- time-stop: ครบ N bars แล้ว MFE < 0.5R → market out ที่เหลือ ----
        if pos.bars_held(bar.ts, BAR_SECS) >= cfg.timing.time_stop_bars \
                and pos.mfe_r < cfg.timing.time_stop_mfe_r:
            exit_px, c = self.costs.exit_price(bar.close, pos.side, True, spread)
            frac = pos.remaining
            pnl = (exit_px - pos.entry_price) * sgn * frac * oz_total
            pos.close_frac(frac, bar.ts, exit_px, "time_stop")
            book.add(pnl, pos.r_multiple(exit_px) * frac, c.total * frac * oz_total)
            pnl_t, r_t, cost_t = book.take()
            return self._make_trade(pos, bar.ts, exit_px, pnl_t, r_t, cost_t, "time_stop")

        # ---- flat-by: บังคับปิดทุกอย่าง ----
        if at_flat_by(bar.ts):
            exit_px, c = self.costs.exit_price(bar.close, pos.side, True, spread)
            frac = pos.remaining
            pnl = (exit_px - pos.entry_price) * sgn * frac * oz_total
            pos.close_frac(frac, bar.ts, exit_px, "flat_by")
            book.add(pnl, pos.r_multiple(exit_px) * frac, c.total * frac * oz_total)
            pnl_t, r_t, cost_t = book.take()
            return self._make_trade(pos, bar.ts, exit_px, pnl_t, r_t, cost_t, "flat_by")

        return None

    def _make_trade(self, pos: Position, exit_ts: int, exit_px: float, pnl: float,
                    r: float, cost_total: float, tag: str) -> TradeRecord:
        st = self.engine.state
        s = sessions_for_day(pos.entry_ts)
        session = "london" if s["london"].contains(pos.entry_ts) else "ny"
        return TradeRecord(
            entry_ts=pos.entry_ts, exit_ts=exit_ts, session=session,
            side=pos.side.value,
            entry_price=pos.entry_price, exit_price=exit_px,
            sl_initial=pos.sl_initial_price,
            sweep_extreme=st.sweep.extreme if st.sweep else 0.0,
            sweep_level=st.sweep.level if st.sweep else 0.0,
            sweep_depth_atr=st.sweep.depth_atr if st.sweep else 0.0,
            lots=pos.initial_size,
            risk_per_oz=pos.risk_per_oz,
            risk_dollars=pos.risk_per_oz * pos.initial_size * self.cfg.instrument.contract_size,
            equity_at_entry=pos.equity_at_entry,
            pnl=pnl, r_multiple=r, mfe_r=pos.mfe_r, mae_r=pos.mae_r,
            exit_tag=tag, bars_held=pos.bars_held(exit_ts, BAR_SECS),
            cost_usd_total=cost_total,
        )
