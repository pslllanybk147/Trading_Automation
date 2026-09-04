"""Daily-cycle orchestrator wiring all stages together."""
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path

from pipeline.ai_governor import AIGovernor
from pipeline.data_layer import (
    cache_candles, check_completeness, fetch_klines, get_top_symbols,
)
from pipeline.execution import PaperExchange
from pipeline.journal import Journal
from pipeline.models import Signal
from pipeline.risk_engine import RiskEngine
from pipeline.signal_engine import generate_signals
from pipeline.validation import validate_signal

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, data=None, governor=None, risk=None, journal=None,
                 exchange=None, validate=None):
        self.data = data or DataAdapter()
        self.governor = governor or AIGovernor()
        self.risk = risk or RiskEngine()
        self.journal = journal or Journal()
        self.exchange = exchange or PaperExchange()
        self.validate = validate or validate_signal
        # Scheduled runs are fresh processes; without this the exchange would
        # start empty and reset equity to initial on every run, so SL/TP on
        # positions opened by earlier runs would never be checked and the
        # 90-day paper stats would be meaningless.
        self._restore_paper_state()

    def _restore_paper_state(self) -> None:
        """Rehydrate paper positions/equity from the journal (source of truth)."""
        if getattr(self.exchange, "restore_state", None) is None:
            return
        j = self.journal
        if not (hasattr(j, "open_trades") and hasattr(j, "closed_since")):
            return
        self.exchange.restore_state(j.open_trades(), j.closed_since(0))

    def run_daily_cycle(self) -> dict:
        summary = {"signals": 0, "approved": 0, "trades_opened": 0, "errors": []}
        if Path("STOP").exists():
            log.warning("Kill-switch engaged (STOP exists) — daily cycle skipped")
            summary["blocked_by"] = "kill_switch"
            return summary
        try:
            candles_map = self.data.fetch_all()
        except Exception as e:
            log.error("Data fetch failed: %s", e)
            summary["errors"].append(f"data:{e}")
            return summary

        signals: list[Signal] = []
        for symbol, candles in candles_map.items():
            try:
                if not candles or not check_completeness(candles, candles[0].timeframe):
                    continue
                sig_list = generate_signals({symbol: candles})
                for sig in sig_list:
                    vr = self.validate(candles, sig)
                    if vr.passed:
                        signals.append(sig)
            except Exception as e:
                log.warning("Signal stage failed for %s: %s", symbol, e)
                summary["errors"].append(f"signal:{symbol}:{e}")
        summary["signals"] = len(signals)

        journal_open = self.journal.open_trades()
        open_symbols = {t.symbol for t in journal_open}
        open_positions = len(journal_open)
        day_start = int(datetime.combine(datetime.now().date(), datetime.min.time()).timestamp())
        day_losses = sum(1 for t in self.journal.closed_since(day_start) if t.pnl() < 0)
        total_dd = self.exchange.drawdown()

        for sig in signals:
            if sig.symbol in open_symbols:
                log.info("Already holding %s — skipping duplicate entry", sig.symbol)
                continue
            equity = self.exchange.equity
            decision = self.governor.decide(sig, candles_map[sig.symbol])
            self.journal.record_decision(sig.symbol, decision)
            if not decision.approved:
                log.info("Governor blocked %s: %s", sig.symbol, decision.reason)
                continue
            summary["approved"] += 1
            plan = self.risk.plan(sig, equity, open_positions, day_losses, total_dd)
            if plan is None or not plan.checks_passed:
                log.info("Risk blocked %s", sig.symbol)
                continue
            trade = self.exchange.place_order(plan, price=sig.entry)
            self.journal.record_trade(trade)
            open_positions += 1
            summary["trades_opened"] += 1

        log.info("Daily cycle done: %s", summary)
        return summary

    def check_open_positions(self) -> None:
        for symbol in list(self.exchange.positions()):
            try:
                candles = self.data.fetch_one(symbol)
                if not candles:
                    continue
                price = candles[-1].c
                closed = self.exchange.check_position(symbol, price)
                if closed is not None:
                    self.journal.close_trade(symbol, closed.exit, closed.fee)
                    log.info("Closed %s via SL/TP check @ %.2f", symbol, closed.exit)
            except Exception as e:
                log.error("Position check failed for %s: %s", symbol, e)

    def reconcile(self) -> None:
        journal_open = {t.symbol for t in self.journal.open_trades()}
        exchange_open = set(self.exchange.positions())
        if journal_open != exchange_open:
            log.error("Reconcile mismatch: journal=%s exchange=%s",
                      journal_open, exchange_open)
        else:
            log.info("Reconcile OK: %d open trades", len(journal_open))


class DataAdapter:
    def get_top_symbols(self, n: int = 30) -> list[str]:
        return get_top_symbols(n)

    def fetch_all(self, interval: str = "4h", limit: int = 500) -> dict[str, list]:
        result = {}
        for symbol in self.get_top_symbols():
            try:
                candles = fetch_klines(symbol, interval, limit)
                if check_completeness(candles, interval):
                    cache_candles(symbol, interval, candles)
                    result[symbol] = candles
            except Exception as e:
                log.warning("Skipping %s: %s", symbol, e)
        return result

    def fetch_one(self, symbol: str, interval: str = "4h") -> list:
        return fetch_klines(symbol, interval, 100)
