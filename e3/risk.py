# -*- coding: utf-8 -*-
"""E3 risk governor §6 — daily/weekly/monthly circuit breakers.

  Daily    หยุดที่ -1.5%
  Weekly   หยุดที่ -3.0%
  Monthly  > -6% → halve size, > -12% → kill switch
  Loss circuit — แพ้ 2 ไม้ติดในวันเดียวกัน → หยุดวันนั้น
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import RiskCfg


def _week_key(ts: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(ts, tz=timezone.utc)
    return (d.isocalendar().year, d.isocalendar().week)


def _month_key(ts: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(ts, tz=timezone.utc)
    return (d.year, d.month)


@dataclass
class RiskGovernor:
    cfg: RiskCfg
    equity_start: float
    _day_pnl: float = 0.0
    _day_key: int | None = None
    _week_pnl: float = 0.0
    _week_key: tuple[int, int] | None = None
    _month_peak: float = field(default=0.0)
    _month_key: tuple[int, int] | None = None
    _consecutive_losses_today: int = 0
    _trades_today: int = 0
    killed: bool = False

    def _roll(self, ts: int) -> None:
        dk = datetime.fromtimestamp(ts, tz=timezone.utc).toordinal()
        if self._day_key != dk:
            self._day_key = dk
            self._day_pnl = 0.0
            self._trades_today = 0
            self._consecutive_losses_today = 0
        wk = _week_key(ts)
        if self._week_key != wk:
            self._week_key = wk
            self._week_pnl = 0.0
        mk = _month_key(ts)
        if self._month_key != mk:
            self._month_key = mk
            self._month_peak = self.equity_start

    # ---- called before entering a trade ----
    def can_trade(self, ts: int) -> tuple[bool, str | None]:
        if self.killed:
            return False, "kill_switch"
        self._roll(ts)
        if self._day_pnl <= -self.cfg.daily_loss_stop * self.equity_start:
            return False, "daily_loss_stop"
        if self._week_pnl <= -self.cfg.weekly_loss_stop * self.equity_start:
            return False, "weekly_loss_stop"
        if self._trades_today >= self.cfg.max_trades_per_day:
            return False, "max_trades_per_day"
        if self.cfg.two_loss_pause and self._consecutive_losses_today >= 2:
            return False, "two_losses_today"
        return True, None

    def risk_scale(self, ts: int, equity: float) -> float:
        """monthly DD → 1.0 / 0.5 / 0 (kill)"""
        self._roll(ts)
        if self._month_key is None:
            return 1.0
        dd = (equity - self._month_peak) / self._month_peak if self._month_peak > 0 else 0.0
        if dd <= -self.cfg.monthly_dd_kill:
            self.killed = True
            return 0.0
        if dd <= -self.cfg.monthly_dd_halve:
            return 0.5
        return 1.0

    # ---- called after each closed trade ----
    def record_trade(self, ts: int, pnl: float, is_loss: bool) -> None:
        self._roll(ts)
        self._day_pnl += pnl
        self._week_pnl += pnl
        self._trades_today += 1
        if is_loss:
            self._consecutive_losses_today += 1
        else:
            self._consecutive_losses_today = 0
        if self._day_pnl <= -self.cfg.daily_loss_stop * self.equity_start:
            return  # วันถัดไป _roll จะ reset
        return
