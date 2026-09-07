# -*- coding: utf-8 -*-
"""E1 engine — state machine FLAT → IN_POSITION ต่อ (symbol, pool)

สายไฟเดียวกับสเปค (§Entry E1-E10, §Exit X1-X8, §Margin ladder):
  - entry วัดจากข้อมูลได้ 5 เงื่อนไข: f_ma7d ≥ 9%/ปี + stability ≥0.8 +
    f_pred(EWMA) > 0 + basis_z < 2.5 + expect_hold ≥ 1.5·H_min + budget
    (ตัวที่วัดจากข้อมูลไม่ได้ใน backtest: news veto — ไม่ implement,
    drawdown watch อยู่ใน hard_stop แล้ว)
  - exits: funding decay (f_ma7d < 4%/ปี) / basis inversion (z < −2) /
    hard stop −1.5% ของ pool / ladder close / liquidation / end_of_data
  - margin ladder 4 ชั้นทุกแท่ง perp ที่ปิดแล้ว ตามสเปคเป๊ะ:
    warn (≤2.2×) → topup กลับขึ้น 1.8× (ใช้ cash สำรองของ pool) →
    deleverage ซื้อคืนครึ่งไม้ (≤1.5×) → close (≤1.3×); ราคา liq ถึง low = ตายทันที

Sizing ตามสเปค: perp margin = notional / max_leverage (lev 2× default →
liq ≈ +50% จาก entry), spot ถือเต็ม notional (delta-neutral) — เงินส่วนที่เหลือ
ของ pool = cash buffer 25% ใช้เป็นสำรองเติม margin เท่านั้น

บัญชีเงิน (สองกระเปาะ ตามสเปค):
  - perp wallet (pos.margin): เงิน margin จริงบน exchange — funding เข้านี้,
    topup เติมจาก cash, realized PnL (inc. deleverage) ตกที่นี่
  - spot: เหรียญถือจริง (spot_qty) — ขายคืนตอนปิดไม้เท่านั้น
  self.cash = เงินสดของ pool ที่ยังว่าง (รวม buffer)

No-lookahead: update() รับเฉพาะแท่งที่ปิดแล้ว; on_funding() รับเฉพาะ event ที่
settle แล้ว — เข้า/ออกไม้ได้เฉพาะตอน funding settle (ไม่เคย mid-interval)
ตำแหน่งใหม่จึงถือ funding interval แรกเต็มช่วงเสมอ
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .config import E1Config
from .data_schema import FundingEvent, Kline
from .margin import MarginLadder, margin_ratio_short


def utc_ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


@dataclass
class Position:
    entry_ms: int
    entry: float                     # ราคา perp ที่ชอร์ต
    qty: float                       # ไม้ perp (ขาย) — ลดลงเมื่อ deleverage
    margin: float                    # perp wallet (รวม funding/topup/realized)
    spot_cash: float                 # เงินที่จ่ายซื้อ spot ตอนเปิด (บันทึก)
    spot_qty: float                  # จำนวนเหรียญที่ถือจริง
    entry_spot: float                # ราคา spot ตอนซื้อ

    def unrealized(self, spot_p: float, perp_p: float) -> float:
        spot_pnl = (spot_p - self.entry_spot) * self.spot_qty
        perp_pnl = (self.entry - perp_p) * self.qty
        return spot_pnl + perp_pnl


@dataclass
class LadderEvent:
    ts_ms: int
    kind: str          # warn | topup | deleverage | close | liq
    ratio: float
    detail: str


@dataclass
class Outcome:
    exit_ms: int
    reason: str
    pnl: float                 # กำไรขาดทุนสุทธิของ episode (รวม fee + funding)
    fees: float                # ค่าธรรมเนียมตอนปิด (เปิดนับใน invested แล้ว)
    funding_received: float
    n_topup: int
    amt_topup: float
    n_delev: int
    liq: bool


class E1Engine:
    """รับ stream (funding event, perp kline closed, spot kline closed) ตามเวลา"""

    def __init__(self, cfg: E1Config):
        self.cfg = cfg
        self.ladder = MarginLadder()
        self.symbol = "BTCUSDT"           # set_symbol ก่อน feed รอบแรก
        self.state = "FLAT"
        self.pos: Position | None = None
        self.cash = cfg.equity * cfg.pool_pct      # pool เต็ม (deploy ≤ 75%)
        self.cash_start = self.cash
        self.funding_received = 0.0       # สะสม funding ทั้งชีวิต sim
        self.fees_open = 0.0
        self.fees_close = 0.0
        self.liq_count = 0
        self.outcomes: list[Outcome] = []
        self.ladder_log: list[LadderEvent] = []

        # ---- rolling state (อัปเดตจากข้อมูลที่ปิดแล้วเท่านั้น) ----
        self._f_win: list[tuple[int, float]] = []   # (ts, rate) หน้าต่าง 7 วัน
        self._funding_cnt = 0
        self._funding_pos = 0
        self._ewma: float | None = None             # f_pred
        self._basis_win: list[float] = []           # basis รายชม. (30 วัน)
        self._ep_history: list[float] = []          # ความยาว episode บวก (วัน)
        self._ep_open_ms: int | None = None
        self._bars_seen = 0

        # ---- per-episode accounting ----
        self._pos_topup = 0
        self._pos_topup_amt = 0.0
        self._pos_delev = 0
        self._pos_funding = 0.0
        self._pos_invested = 0.0        # เงินที่ตัดจาก cash (margin+spot+fee+topup)
        self._last_exit_ms = -1         # กัน re-enter ภายใน settle เดียวกับ exit

    # ---------------- setup ----------------

    def set_symbol(self, symbol: str) -> None:
        if self._bars_seen or self._funding_cnt or self.state != "FLAT":
            raise RuntimeError("set_symbol ต้องเรียกก่อน feed ข้อมูลรอบแรก")
        self.symbol = symbol

    # ---------------- rolling stats ----------------

    def _on_funding_passive(self, ev: FundingEvent) -> None:
        """อัปเดตสถิติ funding ทุก event (FLAT ก็อัปเดต — f_ma7d พร้อมเสมอ)"""
        ts = ev.funding_time_ms
        self._f_win.append((ts, ev.rate))
        cutoff = ts - self.cfg.ma_window_days * 86_400_000
        while self._f_win and self._f_win[0][0] <= cutoff:
            self._f_win.pop(0)
        self._funding_cnt += 1
        if ev.rate > 0:
            self._funding_pos += 1
        alpha = 2.0 / (self.cfg.ma_window_events + 1.0)
        self._ewma = ev.rate if self._ewma is None else \
            self._ewma + alpha * (ev.rate - self._ewma)

        # episode tracking — episode = ช่วงที่ **f_ma7d ≥ เกณฑ์เข้า** ต่อเนื่อง
        # (ไม่ใช่ rate เปลี่ยนขั้ว — rate ดิบสลับขั้วบ่อยจน episode หักเป็นเสี่ยง
        # 1 วัน; สิ่งที่กำหนดว่า "ถือแล้วคุ้ม" คือ regime เฉลี่ย 7 วันที่เข้าจริง)
        # ต้องรอ warmup ครบก่อน (f_ma7d ยังไม่น่าเชื่อถือ)
        if len(self._f_win) < self.cfg.ma_window_events:
            return
        f_ann = self._f_ma7d_ann()
        if self._ep_open_ms is None:
            if f_ann >= self.cfg.entry_f_min:
                self._ep_open_ms = ts
            return
        if f_ann < self.cfg.entry_f_min:
            days = (ts - self._ep_open_ms) / 86_400_000.0
            self._ep_history.append(days)
            self._ep_open_ms = None

    def _interval_ms(self) -> int:
        """ช่วงเก็บ funding จริงจาก ts ล่าสุด (8h default; เหรียญที่สลับ 4h ใช้จริง)"""
        if len(self._f_win) >= 2:
            d = self._f_win[-1][0] - self._f_win[-2][0]
            if 0 < d < 86_400_000:
                return d
        return 8 * 3_600_000

    def _f_ma7d_ann(self) -> float:
        """ค่าเฉลี่ย rate ในหน้าต่าง 7 วัน → annualized ต่อ notional"""
        if not self._f_win:
            return 0.0
        per_day = 86_400_000.0 / self._interval_ms()
        avg = sum(r for _, r in self._f_win) / len(self._f_win)
        return avg * per_day * 365.0

    def _on_bar_passive(self, perp: Kline, spot: Kline) -> None:
        basis = (perp.close - spot.close) / spot.close
        self._basis_win.append(basis)
        cap = self.cfg.basis_z_window_days * 24
        if len(self._basis_win) > cap:
            del self._basis_win[:-cap]
        self._bars_seen += 1

    def _basis_z(self, basis: float) -> float | None:
        w = self._basis_win
        if len(w) < max(24, self.cfg.basis_z_window_days // 2):
            return None
        m = sum(w) / len(w)
        sd = (sum((x - m) ** 2 for x in w) / len(w)) ** 0.5
        if sd <= 0:
            return None
        return (basis - m) / sd

    def _basis_mean_24h(self) -> float | None:
        """ค่าเฉลี่ย basis 24 ชม.ล่าสุด — ตัวตัดสิน X2 (inversion เชิงโครงสร้าง)
        basis รายชม.ดิบพลิกขั้วบ่อย (microstructure noise) — ใช้ดิบ = churn"""
        w = self._basis_win
        if len(w) < 24:
            return None
        return sum(w[-24:]) / 24.0

    # ---------------- sizing / open ----------------

    def _sizing(self, spot: float) -> tuple[float, float, float, float] | None:
        """คืน (qty, margin, spot_cash, fee) — None = เงินไม่พอ/min notional

        deploy = cash × (1 − buffer); notional N ต้องคุมทั้ง spot (N), margin (N/lev)
        และค่าธรรมเนียมเปิด — ที่เหลือใน cash คือ buffer สำรองเติม margin"""
        deploy = self.cash * (1.0 - self.cfg.cash_buffer_pct)
        if deploy <= 0:
            return None
        lev = self.cfg.max_leverage
        denom = 1.0 + 1.0 / lev + self.cfg.fee_spot + self.cfg.fee_perp
        notional = deploy / denom
        if notional < self.cfg.min_notional:
            return None
        qty = notional / spot
        margin = notional / lev
        fee = notional * (self.cfg.fee_spot + self.cfg.fee_perp)
        return qty, margin, notional, fee

    def _open(self, ev: FundingEvent, perp: Kline, spot: Kline) -> None:
        s = self._sizing(spot.close)
        if s is None:
            return
        qty, margin, spot_cash, fee = s
        spot_qty = spot_cash / spot.close          # fee จ่ายด้วยจำนวนเหรียญ
        invested = margin + spot_cash + fee
        self.cash -= invested
        self.fees_open += fee
        self._pos_invested = invested
        self.pos = Position(entry_ms=ev.funding_time_ms, entry=perp.close,
                            qty=qty, margin=margin, spot_cash=spot_cash,
                            spot_qty=spot_qty, entry_spot=spot.close)
        self.state = "IN_POSITION"

    # ---------------- close (บัญชีครบทั้งสองกระเปาะ) ----------------

    def _close(self, ts_ms: int, perp: Kline, spot: Kline, reason: str,
               liq: bool = False) -> Outcome:
        p = self.pos
        assert p is not None
        if liq:
            # perp wallet โดน wipe ทั้งก้อน (isolated) — เหลือขาย spot คืน
            proceeds = p.spot_qty * spot.close
            fee = proceeds * self.cfg.fee_spot
            cash_back = proceeds - fee
        else:
            # ซื้อคืน perp ทั้งไม้: wallet ได้ realized PnL, หักค่าธรรมเนียม
            realized = (p.entry - perp.close) * p.qty
            fee_p = perp.close * p.qty * self.cfg.fee_perp
            proceeds = p.spot_qty * spot.close
            fee_s = proceeds * self.cfg.fee_spot
            fee = fee_p + fee_s
            cash_back = p.margin + realized - fee_p + proceeds - fee_s
        self.fees_close += fee
        self.cash += cash_back
        out = Outcome(exit_ms=ts_ms, reason=reason,
                      pnl=cash_back - self._pos_invested, fees=fee,
                      funding_received=self._pos_funding,
                      n_topup=self._pos_topup, amt_topup=self._pos_topup_amt,
                      n_delev=self._pos_delev, liq=liq)
        self.outcomes.append(out)
        self.pos = None
        self.state = "FLAT"
        self._last_exit_ms = ts_ms
        self._pos_topup = self._pos_delev = 0
        self._pos_topup_amt = 0.0
        self._pos_funding = 0.0
        self._pos_invested = 0.0
        return out

    # ---------------- ladder / liq / hard stop (ทุกแท่ง perp ที่ปิดแล้ว) ----------------

    def _check_bar(self, perp: Kline, spot: Kline) -> None:
        if self.pos is None:
            return
        p = self.pos
        ts = perp.open_time_ms + 3_600_000          # เวลาที่แท่งปิด
        # liq ตรวจ **ก่อน** บันไดเสมอ (adverse-first): เจาะราคา liq intrabar = ตาย
        # ทันที แม้แท่งจะปิดในระดับที่บันไดยังไม่ trigger — ตามจริงที่ exchange ทำ
        from .margin import liq_price_short
        if perp.high >= liq_price_short(p.entry, p.qty, p.margin, self.symbol):
            self.liq_count += 1
            self._close(ts, perp, spot, "liquidation", liq=True)
            return
        ratio = margin_ratio_short(p.entry, perp.close, p.qty, p.margin,
                                   self.symbol)
        # บันได 4 ชั้นตามสเปค: warn >1.8, topup 1.5–1.8, delev 1.3–1.5, close ≤1.3
        level = self.ladder.evaluate(ratio).level
        if level == "warn" and ratio <= self.ladder.topup_to:
            level = "topup"
        if level == "warn":
            self.ladder_log.append(LadderEvent(ts, "warn", ratio, ""))
        elif level == "topup":
            need = self.ladder.topup_amount(p.entry, perp.close, p.qty,
                                            p.margin, self.symbol)
            pay = min(need, self.cash)
            if pay > 0:
                p.margin += pay
                self.cash -= pay
                self._pos_topup += 1
                self._pos_topup_amt += pay
                self._pos_invested += pay
                self.ladder_log.append(LadderEvent(
                    ts, "topup", ratio, f"add {pay:.2f} (need {need:.2f})"))
            else:
                self.ladder_log.append(LadderEvent(
                    ts, "topup", ratio, "no cash — skipped"))
        elif level == "deleverage":
            buy = p.qty / 2.0
            realized = (p.entry - perp.close) * buy
            fee = buy * perp.close * self.cfg.fee_perp
            p.qty -= buy
            p.margin += realized - fee             # realized อยู่ใน wallet ต่อ
            self.fees_close += fee
            self._pos_delev += 1
            self.ladder_log.append(LadderEvent(
                ts, "deleverage", ratio,
                f"buyback {buy:.6f} @ {perp.close:.2f} (realized {realized:+.2f})"))
            if p.qty * perp.close < self.cfg.min_notional:
                self._close(ts, perp, spot, "deleverage_too_small")
                return
        elif level == "close":
            self._close(ts, perp, spot, "ladder_close")
            return
        if self.pos is None:
            return
        # hard stop: ขาดทุนรวม ≥ hard_stop_pct ของ pool
        pool = self.cfg.equity * self.cfg.pool_pct
        if p.unrealized(spot.close, perp.close) <= -pool * self.cfg.hard_stop_pct:
            self._close(ts, perp, spot, "hard_stop")

    # ---------------- public feed ----------------

    def update(self, perp: Kline, spot: Kline) -> None:
        """แท่ง 1h ที่ปิดแล้ว (closed bar only) — ประเมิน ladder/stop เท่านั้น"""
        if perp.symbol != spot.symbol:
            raise ValueError("perp/spot symbol ไม่ตรงกัน")
        self._on_bar_passive(perp, spot)
        if self.state == "IN_POSITION":
            self._check_bar(perp, spot)

    def on_funding(self, ev: FundingEvent, perp: Kline, spot: Kline) -> None:
        """funding settle แล้ว (+แท่งล่าสุดที่ปิดแล้ว) — จุดเดียวที่เปลี่ยน state"""
        self._on_funding_passive(ev)
        if self.state == "IN_POSITION":
            p = self.pos
            rec = ev.rate * p.qty * perp.close      # ชอร์ตได้รับเมื่อ rate > 0
            p.margin += rec
            self.funding_received += rec
            self._pos_funding += rec
            # X1: funding decay / X2: basis inversion — ตัดสินที่ settle เท่านั้น
            # X2 = mean24h basis หลุดต่ำกว่า norm ของตัวเอง (z < −2) — "inversion"
            # เชิงโครงสร้าง (perp discount ผิดปกติ) ไม่ใช่การกลับขั้วเปล่า ๆ เพราะ
            # บนข้อมูลจริง mean24h < 0 ถึง 73% ของเวลา (structural discount)
            if self._f_ma7d_ann() < self.cfg.exit_f_decay:
                self._close(ev.funding_time_ms, perp, spot, "funding_decay")
            else:
                m = self._basis_mean_24h()
                z = self._basis_z(m) if m is not None else None
                if z is not None and z < self.cfg.basis_z_inversion:
                    self._close(ev.funding_time_ms, perp, spot, "basis_inversion")
        if self.state == "FLAT":
            self._try_entry(ev, perp, spot)

    def _try_entry(self, ev: FundingEvent, perp: Kline, spot: Kline) -> None:
        c = self.cfg
        if self.state != "FLAT" or ev.funding_time_ms <= self._last_exit_ms:
            return                                   # ไม่ re-enter ใน settle เดิม
        if len(self._f_win) < c.ma_window_events:
            return                                   # warmup
        if self._f_ma7d_ann() < c.entry_f_min:                      # E1
            return
        if self._funding_cnt == 0 or \
                self._funding_pos / self._funding_cnt < c.entry_stability_min:  # E2
            return
        if self._ewma is None or self._ewma <= 0:                   # E3
            return
        z = self._basis_z((perp.close - spot.close) / spot.close)
        if z is not None and z >= c.basis_z_max:                    # E4
            return
        # E5: expected hold — median episode ที่เห็นมา ≥ 1.5×H_min (fail-closed)
        # (ตั้ง min_completed_episodes = 0 เพื่อปิด E5 ได้ เช่นตอน backtest สั้น)
        if c.min_completed_episodes > 0:
            if len(self._ep_history) < c.min_completed_episodes:
                return
            hist = sorted(self._ep_history)
            n = len(hist)
            med = hist[n // 2] if n % 2 else (hist[n // 2 - 1] + hist[n // 2]) / 2.0
            if med < c.hold_multiple * c.h_min_days:
                return
        self._open(ev, perp, spot)

    # ---------------- report ----------------

    def equity(self, perp_close: float, spot_close: float) -> float:
        """equity ของ pool = cash + มูลค่าไม้ที่ถืออยู่ (หัก fee ปิดโดยประมาณ)"""
        eq = self.cash
        if self.pos is not None:
            p = self.pos
            fee = (p.qty * perp_close * self.cfg.fee_perp
                   + p.spot_qty * spot_close * self.cfg.fee_spot)
            eq += p.margin + (p.entry - perp_close) * p.qty \
                + p.spot_qty * spot_close - fee
        return eq
