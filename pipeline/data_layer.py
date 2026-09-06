"""Fetch OHLCV data from Binance public API with completeness check + SQLite cache."""
from __future__ import annotations
import json
import logging
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

from pipeline.models import CandleData

log = logging.getLogger(__name__)

BINANCE_KLINE_URL = "https://api.binance.com/api/v3/klines"
CACHE_DB = Path("data/cache.db")

# Fallback top-30 by market cap (used if CoinGecko unavailable)
FALLBACK_TOP30 = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "TRXUSDT",
    "DOTUSDT", "LTCUSDT", "BCHUSDT", "NEARUSDT", "UNIUSDT",
    "ATOMUSDT", "XLMUSDT", "ICPUSDT", "FILUSDT", "APTUSDT",
    "ETCUSDT", "IMXUSDT", "INJUSDT", "OPUSDT", "ARBUSDT",
    "SUIUSDT", "TONUSDT", "TIAUSDT", "SEIUSDT", "RNDRUSDT",
]


# Symbols that permanently fail on Binance klines (HTTP 400) — USDG is not a
# spot-tradeable pair, but CoinGecko rankings keep re-listing it via the
# len(s) > 6 heuristic. Never fetch or trade these.
SKIP_SYMBOLS = {"USDGUSDT"}


def parse_klines(symbol: str, interval: str, raw: list) -> list[CandleData]:
    candles = []
    for k in raw:
        candles.append(CandleData(
            symbol=symbol, timeframe=interval,
            ts=k[0] // 1000, o=float(k[1]), h=float(k[2]),
            l=float(k[3]), c=float(k[4]), v=float(k[5]),
        ))
    return candles


def fetch_klines(symbol: str, interval: str, limit: int = 500) -> list[CandleData]:
    url = f"{BINANCE_KLINE_URL}?symbol={symbol}&interval={interval}&limit={limit}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                raw = json.loads(resp.read().decode())
            candles = parse_klines(symbol, interval, raw)
            log.info("Fetched %d candles for %s %s", len(candles), symbol, interval)
            return candles
        except urllib.error.HTTPError as e:
            # 4xx (e.g. unknown symbol) is permanent — retrying with backoff is wasted
            # time; only transient failures (timeout, 5xx, connection) deserve retries.
            if 400 <= e.code < 500:
                log.warning("Permanent error for %s: HTTP %s — skipping", symbol, e.code)
                raise RuntimeError(f"HTTP {e.code} for {symbol}") from e
            log.warning("Attempt %d failed for %s: %s", attempt + 1, symbol, e)
            time.sleep([5, 15, 30][attempt])
        except Exception as e:
            log.warning("Attempt %d failed for %s: %s", attempt + 1, symbol, e)
            time.sleep([5, 15, 30][attempt])
    raise RuntimeError(f"Failed to fetch klines for {symbol} after 3 attempts")


def get_top_symbols(n: int = 30) -> list[str]:
    """CoinGecko market-cap ranking; falls back to hardcoded list on failure."""
    try:
        url = ("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
               "&order=market_cap_desc&per_page=100&page=1")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        symbols = [c["symbol"].upper() + "USDT" for c in data[:n]]
        # keep only symbols that look tradeable on Binance (and not known-bad)
        dropped = [s for s in symbols if s in SKIP_SYMBOLS]
        if dropped:
            log.info("Skipping blacklisted symbols: %s", ", ".join(dropped))
        return [s for s in symbols
                if s not in SKIP_SYMBOLS
                and (s in FALLBACK_TOP30 or len(s) > 6)][:n]
    except Exception as e:
        log.warning("CoinGecko failed (%s), using fallback top-%d", e, n)
        return [s for s in FALLBACK_TOP30[:n] if s not in SKIP_SYMBOLS]


def check_completeness(candles: list[CandleData], interval: str) -> bool:
    if not candles:
        return False
    step = {"1h": 3600, "4h": 14400, "1d": 86400}[interval]
    expected = (candles[-1].ts - candles[0].ts) // step + 1
    gap_ratio = 1 - len(candles) / expected
    ok = gap_ratio <= 0.05
    if not ok:
        log.warning("Incomplete data for %s: %d/%d candles (gap %.0f%%)",
                    candles[0].symbol, len(candles), expected, gap_ratio * 100)
    return ok


def _connect() -> sqlite3.Connection:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS candles (
        symbol TEXT, interval TEXT, ts INTEGER,
        o REAL, h REAL, l REAL, c REAL, v REAL,
        PRIMARY KEY (symbol, interval, ts))""")
    return conn


def cache_candles(symbol: str, interval: str, candles: list[CandleData]) -> None:
    conn = _connect()
    conn.executemany(
        "INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?)",
        [(c.symbol, c.timeframe, c.ts, c.o, c.h, c.l, c.c, c.v) for c in candles],
    )
    conn.commit()
    conn.close()


def load_cached_candles(symbol: str, interval: str) -> list[CandleData]:
    conn = _connect()
    rows = conn.execute(
        "SELECT symbol, interval, ts, o, h, l, c, v FROM candles "
        "WHERE symbol=? AND interval=? ORDER BY ts",
        (symbol, interval),
    ).fetchall()
    conn.close()
    return [CandleData(symbol=r[0], timeframe=r[1], ts=r[2], o=r[3], h=r[4], l=r[5], c=r[6], v=r[7]) for r in rows]
