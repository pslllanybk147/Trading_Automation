"""Execution layer: paper mode first, live stub."""
from __future__ import annotations
import logging
import time

from pipeline.models import RiskPlan, TradeRecord

log = logging.getLogger(__name__)

FEE_RATE = 0.001     # 0.1% taker
SLIPPAGE = 0.0005    # 0.05% modeled slippage


class PaperExchange:
    def __init__(self, equity: float = 50_000.0):
        self.equity = equity
        self.initial_equity = equity
        self._positions: dict[str, TradeRecord] = {}

    def place_order(self, plan: RiskPlan, price: float) -> TradeRecord:
        fill_price = price * (1 + SLIPPAGE)
        fee = plan.size_usdt * FEE_RATE
        # Equity = account value (cash + positions at cost), NOT a cash balance:
        # buying spends cash but you now own coins of equal value, so only the
        # fee is realized. Deducting full notional here would show a huge fake
        # drawdown while the position is open and stall the circuit breaker.
        self.equity -= fee
        trade = TradeRecord(symbol=plan.symbol, side="LONG", entry=fill_price,
                            exit=0.0, size_usdt=plan.size_usdt, fee=fee,
                            ts_open=int(time.time()), ts_close=0,
                            reason=plan.note or "", sl_price=plan.sl, tp1_price=plan.tp1)
        self._positions[plan.symbol] = trade
        log.info("[PAPER] BUY %s %.2f USDT @ %.2f (fee %.2f, equity %.2f)",
                 plan.symbol, plan.size_usdt, fill_price, fee, self.equity)
        return trade

    def positions(self) -> dict[str, TradeRecord]:
        return dict(self._positions)

    def check_position(self, symbol: str, price: float) -> TradeRecord | None:
        """Close if price hits SL or TP1 of the plan stored with the position."""
        trade = self._positions.get(symbol)
        if trade is None:
            return None
        # SL/TP stored alongside the trade at open time (fields on TradeRecord)
        if price <= trade.sl_price or price >= trade.tp1_price:
            return self.close_position(trade, price)
        return None

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
