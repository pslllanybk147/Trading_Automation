"""Typed data structures shared across all pipeline stages."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CandleData:
    symbol: str
    timeframe: str
    ts: int          # unix seconds (close time of candle)
    o: float
    h: float
    l: float
    c: float
    v: float

    def return_pct(self) -> float:
        return (self.c - self.o) / self.o * 100.0


@dataclass
class Signal:
    symbol: str
    direction: str          # "LONG" only in v1 (spot)
    entry: float
    sl: float
    tp1: float
    tp2: float
    reason: str             # "golden_cross", "turtle_breakout"
    timeframe: str
    ts: int
    rsi: Optional[float] = None
    volume_ratio: Optional[float] = None

    def rr(self) -> float:
        """Reward:risk on tp1."""
        risk = self.entry - self.sl
        if risk <= 0:
            return 0.0
        return (self.tp1 - self.entry) / risk


@dataclass
class ValidationResult:
    symbol: str
    pattern: str
    passed: bool
    sharpe: float
    win_rate: float
    profit_factor: float
    max_dd: float
    walk_forward_passed: bool


@dataclass
class GovernorDecision:
    symbol: str
    approved: bool
    reason: str
    regime: str = "unknown"
    events_checked: list = field(default_factory=list)


@dataclass
class RiskPlan:
    symbol: str
    size_usdt: float
    sl: float
    tp1: float
    tp2: float
    risk_used: float        # fraction of equity risked on this trade
    checks_passed: bool
    note: str = ""


@dataclass
class TradeRecord:
    symbol: str
    side: str
    entry: float
    exit: float
    size_usdt: float
    fee: float
    ts_open: int
    ts_close: int
    reason: str
    regime: str = "unknown"
    sl_price: float = 0.0      # stop-loss level stored at open
    tp1_price: float = 0.0     # take-profit 1 level stored at open

    def pnl(self) -> float:
        if self.exit == 0.0:
            return 0.0
        raw = (self.exit - self.entry) / self.entry * self.size_usdt
        return raw - self.fee
