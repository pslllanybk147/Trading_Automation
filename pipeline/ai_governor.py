"""AI Governor: regime detection + scheduled-event blocking + LLM approve/block (fail-closed)."""
from __future__ import annotations
import logging
import os
from datetime import UTC, datetime

from pipeline.models import CandleData, GovernorDecision, Signal
from pipeline.signal_engine import sma

log = logging.getLogger(__name__)

# FOMC + CPI announcement dates (UTC) — extend as needed
FOMC_CPI_2025_2026 = [
    # FOMC 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # FOMC 2026
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    # CPI 2025 (approx, mid-month)
    "2025-01-14", "2025-02-12", "2025-03-12", "2025-04-10",
    "2025-05-13", "2025-06-11", "2025-07-15", "2025-08-12",
    "2025-09-10", "2025-10-14", "2025-11-12", "2025-12-10",
]


class AIGovernor:
    def __init__(self, model: str = "gpt-4o-mini", use_llm: bool | None = None):
        self.model = model
        self.use_llm = os.getenv("OPENAI_API_KEY") is not None if use_llm is None else use_llm
        if self.use_llm:
            try:
                from openai import OpenAI  # lazy import
                self._client = OpenAI()
            except Exception as e:
                log.warning("OpenAI init failed (%s) — falling back to rule-based", e)
                self.use_llm = False

    def detect_regime(self, candles: list[CandleData]) -> str:
        if len(candles) < 60:
            return "unknown"
        closes = [c.c for c in candles]
        fast = [x for x in sma(closes, 20) if x is not None]
        slow = [x for x in sma(closes, 50) if x is not None]
        if not fast or not slow:
            return "unknown"
        slope = (fast[-1] - fast[-min(len(fast), 10)]) / max(len(fast), 1)
        spread = (fast[-1] - slow[-1]) / slow[-1]
        if slope > 0 and spread > 0.01:
            return "bull"
        if slope < 0 and spread < -0.01:
            return "bear"
        return "range"

    def check_events(self, ts: int) -> list[str]:
        day = datetime.fromtimestamp(ts, UTC).date()
        events = []
        for d in FOMC_CPI_2025_2026:
            ev = datetime.strptime(d, "%Y-%m-%d").date()
            if abs((ev - day).days) <= 1:
                events.append(d)
        return events

    def decide(self, signal: Signal, candles: list[CandleData]) -> GovernorDecision:
        regime = self.detect_regime(candles)
        events = self.check_events(signal.ts)

        # rule-based hard blocks (always applied, no LLM needed)
        if events:
            return GovernorDecision(symbol=signal.symbol, approved=False,
                                    reason=f"scheduled event within window: {events}",
                                    regime=regime, events_checked=events)
        if regime == "range":
            return GovernorDecision(symbol=signal.symbol, approved=False,
                                    reason="range regime — no trend to ride",
                                    regime=regime, events_checked=events)
        if regime == "bear":
            return GovernorDecision(symbol=signal.symbol, approved=False,
                                    reason="bear regime — spot LONG discouraged",
                                    regime=regime, events_checked=events)

        # optional LLM second opinion (fail-closed on error)
        if self.use_llm:
            try:
                ok, why = self._ask_llm(signal, regime)
                return GovernorDecision(symbol=signal.symbol, approved=ok, reason=why,
                                        regime=regime, events_checked=events)
            except Exception as e:
                log.error("LLM failed (%s) — fail-closed: blocking %s", e, signal.symbol)
                return GovernorDecision(symbol=signal.symbol, approved=False,
                                        reason=f"LLM failure (fail-closed): {e}",
                                        regime=regime, events_checked=events)

        log.info("Governor approved %s (regime=%s)", signal.symbol, regime)
        return GovernorDecision(symbol=signal.symbol, approved=True,
                                reason=f"no event, regime={regime}",
                                regime=regime, events_checked=events)

    def _ask_llm(self, signal: Signal, regime: str) -> tuple[bool, str]:
        prompt = (
            f"Regime: {regime}. Signal: LONG {signal.symbol} entry {signal.entry}, "
            f"SL {signal.sl}, TP1 {signal.tp1}, reason {signal.reason}. "
            "Approve or block this swing trade? Reply JSON: {\"approved\": bool, \"reason\": str}. "
            "Be conservative; block if any doubt."
        )
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        text = resp.choices[0].message.content
        import json
        parsed = json.loads(text)
        return bool(parsed["approved"]), str(parsed["reason"])
