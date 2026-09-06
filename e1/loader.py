# -*- coding: utf-8 -*-
"""E1 loader — sqlite cache (incremental) + parse + scan + funding/basis helpers

Pattern เดียวกับ E3 loader: raw API → parse+validate → scan → cache → ให้ engine
ไม่มีการเดา/ซ่อมข้อมูล — ของหายต้องเห็นใน report

Cache schema (e1/data/cache_e1.db):
  funding(symbol, funding_time_ms, rate, mark_price, PRIMARY KEY(symbol, funding_time_ms))
  klines(symbol, market, interval, open_time_ms, o, h, l, c, v,
         PRIMARY KEY(symbol, market, interval, open_time_ms))
  meta(key, value)   — เช่น last fetch time
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import binance
from .data_schema import E1DataError, FundingEvent, Kline, funding_intervals_ms
from .quality import H8, E1QualityReport, scan_all


class E1Loader:
    def __init__(self, cache_path: str | None = "e1/data/cache_e1.db"):
        self.cache_path = cache_path
        if cache_path:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(cache_path)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS funding (
                symbol TEXT, funding_time_ms INTEGER, rate REAL, mark_price REAL,
                PRIMARY KEY (symbol, funding_time_ms))""")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS klines (
                symbol TEXT, market TEXT, interval TEXT, open_time_ms INTEGER,
                o REAL, h REAL, l REAL, c REAL, v REAL,
                PRIMARY KEY (symbol, market, interval, open_time_ms))""")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY, value TEXT)""")

    # ---------- cache ----------

    def _cached_max_ms(self, table: str, key: str, symbol: str,
                       extra: str = "") -> int | None:
        q = f"SELECT MAX({key}) FROM {table} WHERE symbol=? {extra}"
        row = self._conn.execute(q, (symbol,)).fetchone()
        return row[0] if row and row[0] is not None else None

    def _save_funding(self, rows: list[FundingEvent]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO funding VALUES (?,?,?,?)",
            [(e.symbol, e.funding_time_ms, e.rate, e.mark_price) for e in rows])
        self._conn.commit()

    def _save_klines(self, rows: list[Kline], interval: str) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO klines VALUES (?,?,?,?,?,?,?,?,?)",
            [(k.symbol, k.market, interval, k.open_time_ms,
              k.open, k.high, k.low, k.close, k.volume) for k in rows])
        self._conn.commit()

    def load_funding(self, symbol: str) -> list[FundingEvent]:
        cur = self._conn.execute(
            "SELECT funding_time_ms, rate, mark_price FROM funding "
            "WHERE symbol=? ORDER BY funding_time_ms", (symbol,))
        return [FundingEvent(symbol, ts, rate, mp) for ts, rate, mp in cur.fetchall()]

    def load_klines(self, symbol: str, market: str, interval: str) -> list[Kline]:
        cur = self._conn.execute(
            "SELECT open_time_ms, o, h, l, c, v FROM klines "
            "WHERE symbol=? AND market=? AND interval=? ORDER BY open_time_ms",
            (symbol, market, interval))
        return [Kline(symbol, ts, o, h, l, c, v, market)
                for ts, o, h, l, c, v in cur.fetchall()]

    # ---------- fetch + cache (incremental) ----------

    def sync_funding(self, sess, symbol: str) -> int:
        """ดึงเฉพาะส่วนที่ยังไม่มีใน cache — คืนจำนวนแถวใหม่"""
        last = self._cached_max_ms("funding", "funding_time_ms", symbol)
        raw = binance.fetch_funding(sess, symbol, start_ms=(last + 1) if last else None)
        events = [FundingEvent(symbol, int(r["fundingTime"]), float(r["fundingRate"]),
                               float(r["markPrice"]) if r.get("markPrice") else None)
                  for r in raw]
        if events:
            self._save_funding(events)
        return len(events)

    def sync_klines(self, sess, symbol: str, interval: str, market: str = "perp") -> int:
        last = self._cached_max_ms("klines", "open_time_ms", symbol,
                                   f"AND market='{market}' AND interval='{interval}'")
        raw = binance.fetch_klines(sess, symbol, interval, market,
                                   start_ms=(last + 1) if last else None)
        rows = []
        for r in raw:
            try:
                rows.append(Kline(symbol, int(r[0]), float(r[1]), float(r[2]),
                                  float(r[3]), float(r[4]), float(r[5]), market))
            except E1DataError:
                continue   # แท่งพัง (partial bar สุดท้าย) — แจ้งที่ report แทน
        if rows:
            self._save_klines(rows, interval)
        return len(rows)

    # ---------- high level: โหลดครบ + scan ----------

    def load_symbol(self, symbol: str, interval: str = "1h") -> \
            tuple[list[FundingEvent], list[Kline], list[Kline], list[E1QualityReport]]:
        funding = self.load_funding(symbol)
        spot = self.load_klines(symbol, "spot", interval)
        perp = self.load_klines(symbol, "perp", interval)
        iv_ms = _interval_ms(interval)
        return funding, spot, perp, scan_all(symbol, funding, spot, perp, iv_ms)

    def close(self):
        if self.cache_path:
            self._conn.close()


def _interval_ms(interval: str) -> int:
    unit = interval[-1]
    n = int(interval[:-1])
    mult = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}[unit]
    return n * mult


def funding_summary(events: list[FundingEvent]) -> dict:
    """สถิติพื้นฐานที่ตอบคำถาม 'edge มีจริงไหม' — annualized ต่อ notional"""
    if not events:
        return {}
    rates = [e.rate for e in events]
    n = len(rates)
    # สมมติ 8h (ตรวจจริงจาก intervals) → 3 ครั้ง/วัน × 365 = 1095 ครั้ง/ปี
    ivs = funding_intervals_ms(events)
    per_day = 86_400_000 / (min(ivs) if ivs else H8)
    avg = sum(rates) / n
    ann = avg * per_day * 365
    pos_pct = 100 * sum(1 for r in rates if r > 0) / n
    return {
        "n": n,
        "per_day": round(per_day, 3),
        "avg_rate": round(avg, 8),
        "ann_pct": round(ann * 100, 2),
        "positive_pct": round(pos_pct, 1),
        "p95": sorted(rates)[int(n * 0.95)],
        "p05": sorted(rates)[max(0, int(n * 0.05))],
        "first_ms": events[0].funding_time_ms,
        "last_ms": events[-1].funding_time_ms,
    }
