"""Execution layer: paper mode first, live stub."""
from __future__ import annotations
import logging
import time

from pipeline.models import RiskPlan, TradeRecord

log = logging.getLogger(__name__)

FEE_RATE = 0.001     # 0.1% taker
SLIPPAGE = 0.0005    # 0.05% modeled slippage


class PaperExchange:
    def __init__(self, equity: float = 50_000.0,
                 partial_fraction: float = 0.0,
                 trail_atr: float = 2.0,
                 tp2_atr: float = 0.0):
        self.equity = equity
        self.initial_equity = equity
        self._positions: dict[str, TradeRecord] = {}
        # Exit policy (mirrors backtest_history.py --partial-tp/--trail-atr/--tp2-atr):
        #   partial_fraction > 0  -> ปิดส่วนนั้นที่ TP1 แล้วปล่อยส่วนที่เหลือ
        #   tp2_atr > 0           -> ส่วนที่เหลือปิดที่ TP2 = entry + tp2_atr*ATR
        #   tp2_atr == 0          -> ส่วนที่เหลือตาม trailing stop trail_atr ATR
        self.partial_fraction = partial_fraction
        self.trail_atr = trail_atr
        self.tp2_atr = tp2_atr

    def place_order(self, plan: RiskPlan, price: float) -> TradeRecord:
        fill_price = price * (1 + SLIPPAGE)
        fee = plan.size_usdt * FEE_RATE
        # Equity = account value (cash + positions at cost), NOT a cash balance:
        # buying spends cash but you now own coins of equal value, so only the
        # fee is realized. Deducting full notional here would show a huge fake
        # drawdown while the position is open and stall the circuit breaker.
        self.equity -= fee
        # TP2 mode เปิดเฉพาะเมื่อ config tp2_atr > 0 (เหมือน harness --tp2-atr)
        # — ถ้าเป็น 0 ตอน partial TP1 จะใช้ trailing แทน
        tp2_price = plan.tp2 if self.tp2_atr > 0 else 0.0
        trade = TradeRecord(symbol=plan.symbol, side="LONG", entry=fill_price,
                            exit=0.0, size_usdt=plan.size_usdt, fee=fee,
                            ts_open=int(time.time()), ts_close=0,
                            reason=plan.note or "", sl_price=plan.sl, tp1_price=plan.tp1,
                            tp2_price=tp2_price, atr_ref=plan.atr,
                            partial_fraction=self.partial_fraction,
                            trail_atr=self.trail_atr)
        self._positions[plan.symbol] = trade
        log.info("[PAPER] BUY %s %.2f USDT @ %.2f (fee %.2f, equity %.2f)",
                 plan.symbol, plan.size_usdt, fill_price, fee, self.equity)
        return trade

    def positions(self) -> dict[str, TradeRecord]:
        return dict(self._positions)

    def check_position(self, symbol: str, price: float,
                       high: float | None = None, low: float | None = None) -> TradeRecord | None:
        """Manage an open position against SL/TP1 (+ partial TP, trailing, TP2).

        ใช้ high/low ของแท่งล่าสุด (ถ้าให้มา) เพื่อเลียนแบบ backtest ที่เช็ค
        low <= SL และ high >= TP ต่อแท่ง ถ้าไม่มี ให้ถือว่า high = low = price.
        คืน TradeRecord ที่ปิด (เต็ม หรือส่วนของ partial TP) — ถ้าเป็น partial TP
        position ยังเปิดอยู่ (size ลดลง) เช็คได้จาก positions().
        """
        trade = self._positions.get(symbol)
        if trade is None:
            return None
        hi = high if high is not None else price
        lo = low if low is not None else price
        # โหมดหลัง partial TP1: TP2 ตาม ATR หรือ trailing stop
        if trade.tp1_filled:
            if trade.tp2_price > 0:
                if lo <= trade.sl_price:
                    return self.close_position(trade, trade.sl_price)
                if hi >= trade.tp2_price:
                    return self.close_position(trade, trade.tp2_price)
                return None
            trade.trail_hi = max(trade.trail_hi, hi)
            if trade.atr_ref > 0:
                trail = max(trade.entry, trade.trail_hi - trade.trail_atr * trade.atr_ref)
                trade.sl_price = max(trade.sl_price, trail)  # ratchet ขึ้นเท่านั้น
            if lo <= trade.sl_price:
                return self.close_position(trade, trade.sl_price)
            return None
        # ปกติ: SL ก่อน TP1 ถ้าแตะทั้งคู่ในแท่งเดียว
        if lo <= trade.sl_price:
            return self.close_position(trade, trade.sl_price)
        if hi >= trade.tp1_price:
            if 0 < trade.partial_fraction < 1:
                return self._partial_fill(trade, trade.tp1_price, hi)
            return self.close_position(trade, trade.tp1_price)
        return None

    def _partial_fill(self, trade: TradeRecord, price: float, bar_high: float) -> TradeRecord:
        """ปิด partial_fraction ของ position ที่ TP1 — position ยังเปิดอยู่
        ด้วย size ที่ลดลง และสลับไปโหมด TP2/trailing."""
        fill_price = price * (1 - SLIPPAGE)
        frac = trade.partial_fraction
        sz = trade.size_usdt * frac
        close_fee = sz * FEE_RATE
        realized = sz * (fill_price / trade.entry - 1.0)
        self.equity += realized - close_fee
        fill = TradeRecord(symbol=trade.symbol, side=trade.side, entry=trade.entry,
                           exit=fill_price, size_usdt=sz,
                           fee=trade.fee * frac + close_fee,
                           ts_open=trade.ts_open, ts_close=int(time.time()),
                           reason=trade.reason, regime=trade.regime,
                           sl_price=trade.sl_price, tp1_price=trade.tp1_price,
                           tp2_price=trade.tp2_price, atr_ref=trade.atr_ref,
                           partial_fraction=trade.partial_fraction,
                           trail_atr=trade.trail_atr, tp1_filled=True,
                           trail_hi=trade.trail_hi)
        # เหลือส่วนที่ยังไม่ปิด: ลด size และส่วนแบ่ง fee เปิดลง
        trade.size_usdt -= sz
        trade.fee = trade.fee * (1 - frac)
        trade.tp1_filled = True
        trade.trail_hi = bar_high
        if self.tp2_atr > 0 and trade.atr_ref > 0:
            trade.tp2_price = trade.entry + self.tp2_atr * trade.atr_ref
        # ยก SL ขึ้นเป็น breakeven (เผื่อ fee 0.1%) ให้ส่วนที่เหลือ
        trade.sl_price = max(trade.sl_price, trade.entry * 1.001)
        log.info("[PAPER] PARTIAL SELL %s %.0f%% @ %.2f (pnl %.2f, remaining %.2f USDT)",
                 trade.symbol, frac * 100, fill_price, realized - close_fee, trade.size_usdt)
        return fill

    def close_position(self, trade: TradeRecord, price: float) -> TradeRecord:
        fill_price = price * (1 - SLIPPAGE)
        close_fee = trade.size_usdt * FEE_RATE
        trade.exit = fill_price
        trade.fee = trade.fee + close_fee
        trade.ts_close = int(time.time())
        # realized pnl on the notional, minus the close fee
        realized = trade.size_usdt * (fill_price / trade.entry - 1.0)
        self.equity += realized - close_fee
        self._positions.pop(trade.symbol, None)
        log.info("[PAPER] SELL %s @ %.2f (pnl %.2f, equity %.2f)",
                 trade.symbol, fill_price, trade.pnl(), self.equity)
        return trade

    def restore_state(self, open_trades: list, closed_trades: list) -> None:
        """Rebuild in-memory paper state from the journal so a fresh process
        (scheduled run) sees the same open positions and equity as the last one.

        equity = initial + realized pnl on closed trades - open fees paid.
        (Open notional is not deducted: open positions are valued at cost.)"""
        self._positions = {t.symbol: t for t in open_trades}
        realized = sum(t.pnl() for t in closed_trades)
        open_fees = sum(t.fee for t in open_trades)
        self.equity = self.initial_equity + realized - open_fees
        log.info("[PAPER] restored %d open position(s), equity %.2f",
                 len(open_trades), self.equity)

    def drawdown(self) -> float:
        return (self.equity - self.initial_equity) / self.initial_equity


class BinanceLive:
    """Live execution stub — only enabled after the paper gate passes."""

    def __init__(self, api_key: str = "", api_secret: str = ""):
        self._api_key = api_key
        self._api_secret = api_secret

    def place_order(self, plan: RiskPlan, price: float) -> TradeRecord:
        raise NotImplementedError(
            "Live execution is disabled until the 90-day paper gate passes")