# -*- coding: utf-8 -*-
"""E3 metrics — TradeRecord telemetry §12 + summary statistics.

TradeRecord.as_dict() ตรง schema ของ spec — ใช้ทำ post-hoc attribution
ได้ว่า edge มาจาก filter ไหน โดยไม่ต้องรัน backtest ใหม่
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TradeRecord:
    # identity
    symbol: str = "XAUUSD"
    engine: str = "E3"
    # timing
    entry_ts: int = 0
    exit_ts: int = 0
    session: str = ""                    # "london" | "ny"
    # direction / prices
    side: str = ""                       # "SHORT" | "LONG"
    entry_price: float = 0.0             # fill จริงหลัง cost
    exit_price: float = 0.0
    sl_initial: float = 0.0
    sweep_extreme: float = 0.0
    sweep_level: float = 0.0
    sweep_depth_atr: float = 0.0
    # size / risk
    lots: float = 0.0
    risk_per_oz: float = 0.0
    risk_dollars: float = 0.0
    equity_at_entry: float = 0.0
    # outcome
    pnl: float = 0.0
    r_multiple: float = 0.0              # net หลัง cost
    mfe_r: float = 0.0
    mae_r: float = 0.0
    exit_tag: str = ""                   # tp1+trail / stop / time_stop / flat_by ...
    bars_held: int = 0
    # costs
    cost_usd_total: float = 0.0
    # context snapshot
    atr_rank: float | None = None
    range_ratio: float | None = None
    h1_bias: int | None = None

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol, "engine": self.engine,
            "entry_ts": self.entry_ts, "exit_ts": self.exit_ts, "session": self.session,
            "side": self.side,
            "entry_price": self.entry_price, "exit_price": self.exit_price,
            "sl_initial": self.sl_initial,
            "sweep_extreme": self.sweep_extreme, "sweep_level": self.sweep_level,
            "sweep_depth_atr": self.sweep_depth_atr,
            "lots": self.lots, "risk_per_oz": self.risk_per_oz,
            "risk_dollars": self.risk_dollars, "equity_at_entry": self.equity_at_entry,
            "pnl": self.pnl, "r_multiple": self.r_multiple,
            "mfe_r": self.mfe_r, "mae_r": self.mae_r,
            "exit_tag": self.exit_tag, "bars_held": self.bars_held,
            "cost_usd_total": self.cost_usd_total,
            "atr_rank": self.atr_rank, "range_ratio": self.range_ratio,
            "h1_bias": self.h1_bias,
        }


@dataclass
class Summary:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_win: float = 0.0
    gross_loss: float = 0.0
    total_pnl: float = 0.0
    total_r: float = 0.0
    max_dd_pct: float = 0.0
    max_losing_streak: int = 0
    total_cost: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def profit_factor(self) -> float | None:
        if self.gross_loss == 0:
            return None if self.gross_win == 0 else float("inf")
        return self.gross_win / self.gross_loss

    @property
    def avg_r(self) -> float:
        return self.total_r / self.trades if self.trades else 0.0

    def as_dict(self) -> dict:
        return {
            "trades": self.trades, "wins": self.wins, "losses": self.losses,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": None if self.profit_factor is None else round(self.profit_factor, 4),
            "total_pnl": round(self.total_pnl, 2), "total_r": round(self.total_r, 3),
            "avg_r": round(self.avg_r, 4),
            "max_dd_pct": round(self.max_dd_pct, 3),
            "max_losing_streak": self.max_losing_streak,
            "total_cost": round(self.total_cost, 2),
        }


def summarize(trades: list[TradeRecord], equity_start: float) -> Summary:
    s = Summary()
    equity = equity_start
    peak = equity
    streak = 0
    for t in trades:
        s.trades += 1
        s.total_pnl += t.pnl
        s.total_r += t.r_multiple
        s.total_cost += t.cost_usd_total
        if t.pnl >= 0:
            s.wins += 1
            s.gross_win += t.pnl
            streak = 0
        else:
            s.losses += 1
            s.gross_loss += -t.pnl
            streak += 1
            s.max_losing_streak = max(s.max_losing_streak, streak)
        equity += t.pnl
        peak = max(peak, equity)
        if peak > 0:
            s.max_dd_pct = max(s.max_dd_pct, (peak - equity) / peak * 100.0)
    return s
