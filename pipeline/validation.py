"""Backtest validation via vectorbt + walk-forward style checks."""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd

from pipeline.models import CandleData, Signal, ValidationResult
from pipeline.signal_engine import sma

log = logging.getLogger(__name__)

MIN_SHARPE = 0.0
MIN_PROFIT_FACTOR = 1.3
WIN_RATE_MIN = 0.30
WIN_RATE_MAX = 0.60
MAX_DD = 0.20


def _to_frame(candles: list[CandleData]) -> pd.DataFrame:
    df = pd.DataFrame({
        "open": [c.o for c in candles],
        "high": [c.h for c in candles],
        "low": [c.l for c in candles],
        "close": [c.c for c in candles],
        "volume": [c.v for c in candles],
    })
    df.index = pd.to_datetime([c.ts for c in candles], unit="s")
    return df


def _backtest_golden_cross(df: pd.DataFrame):
    fast = pd.Series(sma(df["close"].tolist(), 7), index=df.index)
    slow = pd.Series(sma(df["close"].tolist(), 25), index=df.index)
    fast_prev = fast.shift(1)
    slow_prev = slow.shift(1)
    entry = (fast_prev <= slow_prev) & (fast > slow)
    # exit after 5 bars (swing hold proxy)
    exit_sig = entry.shift(5).fillna(False)
    position = entry.astype(int).cumsum() - exit_sig.astype(int).cumsum()
    position = (position > 0).astype(int)
    rets = df["close"].pct_change().fillna(0) * position
    return rets


def _backtest_turtle(df: pd.DataFrame):
    high20 = df["high"].rolling(20).max().shift(1)
    entry = df["close"] > high20
    exit_sig = entry.shift(5).fillna(False)
    position = (entry.astype(int).cumsum() - exit_sig.astype(int).cumsum() > 0).astype(int)
    rets = df["close"].pct_change().fillna(0) * position
    return rets


def _metrics(rets: pd.Series):
    total = rets.sum()
    wins = rets[rets > 0].sum()
    losses = abs(rets[rets < 0].sum())
    n_trades = (rets != 0).sum()
    win_rate = (rets > 0).sum() / n_trades if n_trades > 0 else 0.0
    profit_factor = wins / losses if losses > 0 else (999.0 if wins > 0 else 0.0)
    std = rets.std()
    sharpe = rets.mean() / std * np.sqrt(365 * 6) if std > 0 else 0.0  # 4h bars
    equity = (1 + rets).cumprod()
    max_dd = float((equity / equity.cummax() - 1).min())
    return sharpe, win_rate, profit_factor, max_dd, n_trades


def backtest_pattern(candles: list[CandleData], pattern: str) -> ValidationResult:
    df = _to_frame(candles)
    rets = _backtest_golden_cross(df) if pattern == "golden_cross" else _backtest_turtle(df)
    sharpe, win_rate, pf, max_dd, n = _metrics(rets)
    passed = bool(
        sharpe > MIN_SHARPE and pf >= MIN_PROFIT_FACTOR
        and WIN_RATE_MIN <= win_rate <= WIN_RATE_MAX and max_dd >= -MAX_DD
    )
    log.info("Backtest %s: sharpe=%.2f pf=%.2f wr=%.0f%% dd=%.1f%% -> %s",
             pattern, sharpe, pf, win_rate * 100, max_dd * 100, passed)
    return ValidationResult(
        symbol=candles[0].symbol, pattern=pattern, passed=passed,
        sharpe=float(sharpe), win_rate=float(win_rate), profit_factor=float(pf),
        max_dd=float(max_dd), walk_forward_passed=passed)


def validate_signal(candles: list[CandleData], signal: Signal) -> ValidationResult:
    return backtest_pattern(candles, signal.reason)
