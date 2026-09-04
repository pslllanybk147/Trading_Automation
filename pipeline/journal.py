"""SQLite trade journal + monthly scorecard."""
from __future__ import annotations
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from pipeline.models import GovernorDecision, TradeRecord

log = logging.getLogger(__name__)


class Journal:
    def __init__(self, db_path: str = "data/journal.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        return conn

    def _init_db(self):
        conn = self._connect()
        conn.execute("""CREATE TABLE IF NOT EXISTS trades (
            symbol TEXT, side TEXT, entry REAL, exit REAL, size_usdt REAL,
            fee REAL, ts_open INTEGER, ts_close INTEGER, reason TEXT,
            regime TEXT, sl_price REAL, tp1_price REAL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS decisions (
            symbol TEXT, approved INTEGER, reason TEXT, regime TEXT, ts INTEGER)""")
        conn.commit()
        conn.close()

    def record_trade(self, r: TradeRecord) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (r.symbol, r.side, r.entry, r.exit, r.size_usdt, r.fee,
             r.ts_open, r.ts_close, r.reason, r.regime, r.sl_price, r.tp1_price),
        )
        conn.commit()
        conn.close()
        log.info("Recorded trade %s %s", r.symbol, r.side)

    def closed_since(self, ts: int) -> list[TradeRecord]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM trades WHERE ts_close>0 AND ts_close>=? ORDER BY ts_close",
            (ts,),
        ).fetchall()
        conn.close()
        return [self._row_to_record(r) for r in rows]

    def record_decision(self, symbol: str, decision: GovernorDecision) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO decisions VALUES (?,?,?,?,?)",
            (symbol, int(decision.approved), decision.reason, decision.regime,
             int(datetime.now().timestamp())),
        )
        conn.commit()
        conn.close()

    def open_trades(self) -> list[TradeRecord]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM trades WHERE ts_close=0 ORDER BY ts_open").fetchall()
        conn.close()
        return [self._row_to_record(r) for r in rows]

    def close_trade(self, symbol: str, exit_price: float, fee: float) -> TradeRecord | None:
        open_trades = [t for t in self.open_trades() if t.symbol == symbol]
        if not open_trades:
            return None
        t = open_trades[0]
        t.exit = exit_price
        t.fee = fee
        t.ts_close = int(datetime.now().timestamp())
        conn = self._connect()
        conn.execute(
            "UPDATE trades SET exit=?, fee=?, ts_close=? WHERE symbol=? AND ts_close=0",
            (exit_price, fee, t.ts_close, symbol),
        )
        conn.commit()
        conn.close()
        log.info("Closed %s @ %.2f (pnl %.2f)", symbol, exit_price, t.pnl())
        return t

    def monthly_scorecard(self, month: str) -> dict:
        """month = 'YYYY-MM'"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM trades WHERE ts_close>0 AND strftime('%Y-%m', ts_close, 'unixepoch')=?",
            (month,),
        ).fetchall()
        conn.close()
        trades = [self._row_to_record(r) for r in rows]
        if not trades:
            return {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                    "total_pnl": 0.0, "max_dd": 0.0, "btc_return": 0.0}
        pnls = [t.pnl() for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        gross_win = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        pf = gross_win / gross_loss if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for p in pnls:
            equity *= (1 + p / 1000.0)  # rough pnl% on 1000-unit baseline
            peak = max(peak, equity)
            max_dd = min(max_dd, equity / peak - 1)
        return {
            "trades": len(trades),
            "win_rate": wins / len(trades),
            "profit_factor": pf,
            "total_pnl": round(sum(pnls), 2),
            "max_dd": round(max_dd, 4),
            "btc_return": 0.0,
        }

    @staticmethod
    def _row_to_record(r) -> TradeRecord:
        return TradeRecord(symbol=r[0], side=r[1], entry=r[2], exit=r[3],
                           size_usdt=r[4], fee=r[5], ts_open=r[6], ts_close=r[7],
                           reason=r[8], regime=r[9], sl_price=r[10], tp1_price=r[11])
