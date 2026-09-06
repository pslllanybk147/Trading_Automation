# -*- coding: utf-8 -*-
"""E3 state machine §5 — IDLE → ARMED → SWEPT → CONFIRMED → IN_POSITION.

Design decisions ที่จงใจอนุรักษนิยม (ตาม spec §สรุปท้าย kit):
  - sweep detection ใช้ M15 close-based reclaim (เข้าช้ากว่าจริงเล็กน้อย แต่
    repeatable 100% และไม่มีทาง lookahead)
  - SELL LIMIT วางที่ asian_high (retest), อายุ 4 M15 bars
  - SL = sweep_extreme ± 0.30 × atr_m15
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .clock import at_flat_by, is_asian, sessions_for_day, trade_window_for
from .config import E3Config
from .indicators import ATR, EMA, PercentileRank
from .types import Bar, Phase, Side


@dataclass
class SweepEvent:
    ts: int
    side: Side
    level: float            # asian_high/low ที่ถูก sweep
    extreme: float          # high/low สุดของการ sweep
    depth_atr: float        # ความลึก sweep หน่วย × atr_m15


@dataclass
class PendingOrder:
    side: Side
    limit_price: float      # asian_high (short) / asian_low (long)
    sl_price: float
    placed_ts: int
    expires_ts: int         # placed + retest_bars × 900
    sweep: SweepEvent


@dataclass
class E3State:
    phase: Phase = Phase.IDLE
    asian_high: float | None = None
    asian_low: float | None = None
    asian_day_key: int | None = None
    sweep: SweepEvent | None = None
    sweep_bars: int = 0
    pending: PendingOrder | None = None
    pending_bars: int = 0
    armed_ts: int | None = None
    events: list[str] = field(default_factory=list)

    def log(self, ts: int, msg: str) -> None:
        self.events.append(f"{ts}:{msg}")


class E3Engine:
    """Signal engine — เดินทีละ closed M15 bar เท่านั้น"""

    def __init__(self, cfg: E3Config, news_ts: list[int] | None = None):
        self.cfg = cfg
        self.news_ts = sorted(news_ts or [])
        self.atr_m15 = ATR(20)
        # D1 context = ATR(14) บนแท่งรายวันจริง (OHLC รวมทั้งวัน) — spec ต้องการ daily ATR
        # (ของเดิม: Wilder ATR(96) บน M15 = ใกล้ค่าคงที่ → rank เป็น noise ติดขั้ว 0/1)
        self.atr_d1 = ATR(14)
        self.atr_rank = PercentileRank(window=252, warmup=60)   # วัน — warmup 60 วัน แล้วใช้ได้ (สเปก 252 สำหรับ production)
        self._d1_ohlc: list[tuple[float, float, float]] = []   # (h, l, c) ของวันปัจจุบัน
        self.ema21_h1 = EMA(21)
        self.ema55_h1 = EMA(55)
        self.state = E3State()
        self._last_day_key: int | None = None
        self._d1_prev_close: float | None = None
        self._last_atr_rank: float | None = None   # rank snapshot ล่าสุด (fail-closed จน seed ครบ)

    # ---------- data quality / context ----------

    def _news_veto(self, ts: int) -> bool:
        w = self.cfg.filters.news_veto_minutes * 60
        for n in self.news_ts:
            if abs(ts - n) <= w:
                return True
            if n > ts + w:
                break
        return False

    def _feed_context(self, bar: Bar) -> None:
        """อัปเดต indicators ทุกแท่ง (ทำก่อน signal logic เสมอ)"""
        self.atr_m15.update(bar.high, bar.low, bar.close)
        # H1 EMA: feed เฉพาะแท่งที่เป็นขอบชั่วโมง (close ของ H1 = close ของ M15 แท่งสุดท้ายในชั่วโมง)
        if (bar.ts + 900) % 3600 == 0:
            self.ema21_h1.update(bar.close)
            self.ema55_h1.update(bar.close)
        # D1 จริง: สะสม (h,l,c) ของวัน Tokyo ปัจจุบัน → ปิดวัน = push TR ของวันนั้น
        s = sessions_for_day(bar.ts)
        day_start = int(s["asian"].start.timestamp())
        if self._last_day_key != day_start:
            if self._last_day_key is not None and self._d1_ohlc:
                hs = [x[0] for x in self._d1_ohlc]
                ls = [x[1] for x in self._d1_ohlc]
                close = self._d1_ohlc[-1][2]
                prev_close = self._d1_prev_close
                tr = max(hs) - min(ls)
                if prev_close is not None:
                    tr = max(tr, abs(max(hs) - prev_close), abs(min(ls) - prev_close))
                self._d1_prev_close = close
                self.atr_d1.update_raw(tr)
                if self.atr_d1.ready:
                    r = self.atr_rank.update(self.atr_d1.value)
                    if r is not None:
                        self._last_atr_rank = r
            self._d1_ohlc = []
            self._last_day_key = day_start
        self._d1_ohlc.append((bar.high, bar.low, bar.close))

    def _day_key(self, ts: int) -> int:
        return int(sessions_for_day(ts)["asian"].start.timestamp())

    def _refresh_asian_range(self, ts: int) -> None:
        """เมื่อขึ้นวันใหม่ → reset asian range (สร้างใหม่จาก data ของวันนั้น)"""
        dk = self._day_key(ts)
        if self.state.asian_day_key != dk:
            self.state.asian_day_key = dk
            self.state.asian_high = None
            self.state.asian_low = None
            self.state.sweep = None
            self.state.sweep_bars = 0

    def _build_asian(self, bar: Bar) -> None:
        if is_asian(bar.ts):
            st = self.state
            if st.asian_high is None:
                st.asian_high = bar.high
                st.asian_low = bar.low
            else:
                st.asian_high = max(st.asian_high, bar.high)
                st.asian_low = min(st.asian_low, bar.low)

    # ---------- filters (§5.1) ----------

    def _filters_pass(self, ts: int) -> tuple[bool, str | None]:
        f = self.cfg.filters
        if not self.atr_m15.ready or not self.atr_d1.ready:
            return False, "indicators_not_ready"
        rank = self._last_atr_rank
        if rank is None:
            return False, "atr_rank_not_seeded"
        if not (f.atr_rank_min <= rank <= f.atr_rank_max):
            return False, f"atr_rank_out_of_band({rank:.2f})"
        st = self.state
        if st.asian_high is None or st.asian_low is None:
            return False, "no_asian_range"
        atr_d1 = self.atr_d1.value
        rr = (st.asian_high - st.asian_low) / atr_d1 if atr_d1 > 0 else 0.0
        if not (f.range_ratio_min <= rr <= f.range_ratio_max):
            return False, f"range_ratio_out_of_band({rr:.2f})"
        if self._news_veto(ts):
            return False, "news_veto"
        if at_flat_by(ts):
            return False, "past_flat_by"
        return True, None

    # ---------- main step: หนึ่ง closed M15 bar ----------

    def on_bar(self, bar: Bar) -> PendingOrder | None:
        """คืน PendingOrder เมื่อเพิ่งวาง limit (CONFIRMED) — caller จัดการ fill"""
        bar.validate()
        st = self.state
        self._feed_context(bar)
        self._refresh_asian_range(bar.ts)
        self._build_asian(bar)

        # IN_POSITION จัดการโดย caller (backtest) — engine เฉพาะ signal
        if st.phase is Phase.IN_POSITION:
            return None

        win = trade_window_for(bar.ts)
        in_window = win is not None

        # ---- ARMED check ----
        if st.phase is Phase.IDLE and in_window:
            ok, why = self._filters_pass(bar.ts)
            if ok:
                st.phase = Phase.ARMED
                st.armed_ts = bar.ts
                st.log(bar.ts, "ARMED")
            else:
                st.log(bar.ts, f"not_armed:{why}")

        # ---- sweep detection (close-based) — ทำงานทั้ง IDLE→ARMED แล้ว ----
        if st.phase is Phase.ARMED and in_window:
            atr = self.atr_m15.value
            f = self.cfg.filters
            # sweep บน: close ทะลุขึ้นเหนือ asian_high (intraday touch พอ)
            if bar.high > st.asian_high:
                extreme = max(bar.high, bar.high)  # session extreme สะสม
                if st.sweep is not None and st.sweep.side is Side.SHORT:
                    extreme = max(extreme, st.sweep.extreme)
                depth = (extreme - st.asian_high) / atr
                if st.sweep is None or st.sweep.side is not Side.SHORT:
                    st.sweep = SweepEvent(bar.ts, Side.SHORT, st.asian_high, extreme, depth)
                    st.sweep_bars = 0
                    st.phase = Phase.SWEPT
                    st.log(bar.ts, f"SWEPT_up:{depth:.2f}atr")
                else:
                    st.sweep.extreme = max(st.sweep.extreme, bar.high)
                    st.sweep.depth_atr = (st.sweep.extreme - st.sweep.level) / atr
            elif bar.low < st.asian_low:
                extreme = bar.low
                if st.sweep is not None and st.sweep.side is Side.LONG:
                    extreme = min(extreme, st.sweep.extreme)
                depth = (st.asian_low - extreme) / atr
                if st.sweep is None or st.sweep.side is not Side.LONG:
                    st.sweep = SweepEvent(bar.ts, Side.LONG, st.asian_low, extreme, depth)
                    st.sweep_bars = 0
                    st.phase = Phase.SWEPT
                    st.log(bar.ts, f"SWEPT_down:{depth:.2f}atr")
                else:
                    st.sweep.extreme = min(st.sweep.extreme, bar.low)
                    st.sweep.depth_atr = (st.sweep.level - st.sweep.extreme) / atr

        # ---- SWEPT: รอ reclaim ภายใน reclaim_bars ----
        if st.phase is Phase.SWEPT and st.sweep is not None:
            st.sweep_bars += 1
            atr = self.atr_m15.value
            sw = st.sweep
            f = self.cfg.filters
            if sw.side is Side.SHORT:
                reclaimed = bar.close < sw.level
                if bar.high > sw.extreme:
                    sw.extreme = bar.high
                    sw.depth_atr = (sw.extreme - sw.level) / atr
            else:
                reclaimed = bar.close > sw.level
                if bar.low < sw.extreme:
                    sw.extreme = bar.low
                    sw.depth_atr = (sw.level - sw.extreme) / atr

            if reclaimed and st.sweep_bars <= self.cfg.timing.reclaim_bars:
                # news veto ตรวจซ้ำ ณ วินาทีส่งคำสั่ง (spec §5.1 spread guard ก็ทำเช่นเดียวกัน)
                if self._news_veto(bar.ts):
                    st.log(bar.ts, "news_veto_at_order")
                    self._reset_to_idle(bar.ts)
                    return None
                # quality: ความลึก sweep ต้องอยู่ใน [min, max] × atr_m15
                if not (f.sweep_min_atr <= sw.depth_atr <= f.sweep_max_atr):
                    st.log(bar.ts, f"sweep_depth_reject:{sw.depth_atr:.2f}")
                    self._reset_to_idle(bar.ts)
                    return None
                # confluence (optional)
                if self.cfg.filters.use_h1_bias and self.ema21_h1.ready and self.ema55_h1.ready:
                    bias = 1 if self.ema21_h1.value > self.ema55_h1.value else -1
                    if sw.side is Side.SHORT and bias == 1:
                        st.log(bar.ts, "h1_bias_conflict")
                        self._reset_to_idle(bar.ts)
                        return None
                    if sw.side is Side.LONG and bias == -1:
                        st.log(bar.ts, "h1_bias_conflict")
                        self._reset_to_idle(bar.ts)
                        return None
                # place limit @ level (retest), อายุ retest_bars
                stop_dist_extra = self.cfg.timing.stop_atr * atr
                if sw.side is Side.SHORT:
                    sl = sw.extreme + stop_dist_extra
                else:
                    sl = sw.extreme - stop_dist_extra
                st.pending = PendingOrder(
                    side=sw.side,
                    limit_price=sw.level,
                    sl_price=sl,
                    placed_ts=bar.ts,
                    expires_ts=bar.ts + self.cfg.timing.retest_bars * 900,
                    sweep=sw,
                )
                st.pending_bars = 0
                st.phase = Phase.CONFIRMED
                st.log(bar.ts, f"CONFIRMED:{sw.side.value}@{sw.level:.2f}")
                return st.pending

            if st.sweep_bars > self.cfg.timing.reclaim_bars:
                st.log(bar.ts, "no_reclaim→IDLE")
                self._reset_to_idle(bar.ts)

        # ---- CONFIRMED: รอ retest fill จนหมดอายุ ----
        if st.phase is Phase.CONFIRMED and st.pending is not None:
            st.pending_bars += 1
            if bar.ts >= st.pending.expires_ts:
                st.log(bar.ts, "order_expired→IDLE")
                self._reset_to_idle(bar.ts)

        return None

    def _reset_to_idle(self, ts: int) -> None:
        st = self.state
        st.phase = Phase.IDLE
        st.sweep = None
        st.sweep_bars = 0
        st.pending = None
        st.pending_bars = 0
        st.armed_ts = None
        st.log(ts, "IDLE")

    def on_position_closed(self, ts: int) -> None:
        """caller แจ้งเมื่อ position ปิดแล้ว"""
        self._reset_to_idle(ts)
