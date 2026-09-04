"""Position sizing + circuit breakers + kill-switch checks."""
from __future__ import annotations
import logging
from pathlib import Path

from pipeline.models import RiskPlan, Signal

log = logging.getLogger(__name__)

STOP_FILE = Path("STOP")


class RiskEngine:
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.risk_per_trade = cfg.get("risk_per_trade", 0.03)
        self.max_positions = cfg.get("max_positions", 5)
        self.max_total_risk = cfg.get("max_total_risk", 0.10)
        self.max_day_losses = cfg.get("max_day_losses", 3)
        self.max_total_dd = cfg.get("max_total_dd", 0.20)

    def check_circuit_breakers(self, day_losses: int, total_dd: float) -> tuple[bool, str]:
        if total_dd <= -self.max_total_dd:
            return True, f"total drawdown {total_dd:.0%} <= -{self.max_total_dd:.0%}: halt 1 week"
        if day_losses >= self.max_day_losses:
            return True, f"{day_losses} consecutive losses: halt rest of day"
        return False, ""

    def plan(self, signal: Signal, equity: float, open_positions: int,
             day_losses: int, total_dd: float) -> RiskPlan | None:
        if self._kill_switch_active():
            log.warning("Kill-switch active — blocking %s", signal.symbol)
            return None
        halted, reason = self.check_circuit_breakers(day_losses, total_dd)
        if halted:
            log.warning("Circuit breaker: %s — blocking %s", reason, signal.symbol)
            return None
        if open_positions >= self.max_positions:
            log.warning("Max positions reached — blocking %s", signal.symbol)
            return None
        if open_positions * self.risk_per_trade + self.risk_per_trade > self.max_total_risk:
            log.warning("Total risk would exceed %.0f%% — blocking %s",
                        self.max_total_risk * 100, signal.symbol)
            return None

        risk_amount = equity * self.risk_per_trade
        risk_per_unit = signal.entry - signal.sl
        if risk_per_unit <= 0:
            log.warning("Invalid SL for %s", signal.symbol)
            return None
        # notional size such that a full SL hit loses exactly risk_amount:
        # loss = size * (entry - sl) / entry  ->  size = risk_amount * entry / (entry - sl)
        size = risk_amount * signal.entry / risk_per_unit
        log.info("Planned %s: size=%.2f USDT (risk %.1f%%)",
                 signal.symbol, size, self.risk_per_trade * 100)
        return RiskPlan(symbol=signal.symbol, size_usdt=round(size, 2), sl=signal.sl,
                        tp1=signal.tp1, tp2=signal.tp2, risk_used=self.risk_per_trade,
                        checks_passed=True)

    @staticmethod
    def _kill_switch_active() -> bool:
        return STOP_FILE.exists()
