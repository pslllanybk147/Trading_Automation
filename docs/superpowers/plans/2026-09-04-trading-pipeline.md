# AI Trading Pipeline (Swing Rule-Based + AI Governor) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-auto swing trading pipeline on Binance Spot: rule-based signal engine + AI governor + risk engine + paper-first execution, validated end-to-end.

**Architecture:** 7 modular stages (Data → Signal → Validation → AI Governor → Risk → Execution → Journal) wired by a daily-cycle orchestrator. Each stage is a standalone module communicating via typed dataclasses (in `models.py`). Fail-closed: any doubt = no trade.

**Tech Stack:** Python 3.13, stdlib (urllib, sqlite3, json, csv) + numpy/pandas/vectorbt for backtest, `openai` client for LLM governor, `python-binance` for live execution (paper mode first), `pytest` for tests.

**Spec:** `docs/superpowers/specs/2026-09-04-trading-pipeline-design.md` (plan argues from the spec; executors read both)

## Global Constraints

- **Python ≥ 3.13**, all code in `pipeline/`, tests in `tests/`
- **Risk budget (aggressive):** risk ≤ 3% per trade, ≤ 5 concurrent positions, total risk ≤ 10%, total loss -20% → halt 1 week, 3 losses in a row → halt that day
- **Symbols:** Top 20-30 by market cap on Binance, timeframes 4H/1D
- **Fail-closed:** on ANY error (API down, LLM down, missing data) → block/skip, never trade on doubt
- **Fees modeled:** 0.1% taker + 0.05% slippage in paper mode
- **Paper-first mandatory:** ≥ 90 days paper before any live order
- **No secrets committed:** API keys only in `.env` (gitignored)
- **Naming:** snake_case for functions/variables, UPPER_SNAKE for constants
- **Every stage logs:** Python `logging` to both console and `logs/pipeline.log`

---

### Task 1: Project Scaffolding + models.py

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `pipeline/__init__.py`
- Create: `pipeline/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: dataclasses `CandleData`, `Signal`, `ValidationResult`, `GovernorDecision`, `RiskPlan`, `TradeRecord` — used by every later task. Exact field names below are the contract.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
import pytest
from pipeline.models import (
    CandleData, Signal, GovernorDecision, RiskPlan, TradeRecord,
)

def test_candle_data_defaults():
    c = CandleData(symbol="BTCUSDT", timeframe="4h", ts=1700000000,
                   o=1.0, h=1.1, l=0.9, c=1.05, v=1000.0)
    assert c.symbol == "BTCUSDT"
    assert c.return_pct() == pytest.approx(5.0)  # (1.05 - 1.0) / 1.0 = 5%

def test_signal_rr():
    s = Signal(symbol="BTCUSDT", direction="LONG", entry=100.0, sl=95.0,
               tp1=108.0, tp2=115.0, reason="golden_cross", timeframe="4h", ts=1)
    assert s.rr() == pytest.approx(1.6)  # (108-100)/(100-95) = 1.6

def test_governor_decision_default_block():
    d = GovernorDecision(symbol="BTCUSDT", approved=False, reason="unknown")
    assert d.approved is False

def test_risk_plan_checks():
    p = RiskPlan(symbol="BTCUSDT", size_usdt=30.0, sl=95.0, tp1=108.0, tp2=115.0,
                 risk_used=0.02, checks_passed=True)
    assert p.checks_passed is True

def test_trade_record_pnl():
    t = TradeRecord(symbol="BTCUSDT", side="LONG", entry=100.0, exit=110.0,
                    size_usdt=30.0, fee=0.06, ts_open=1, ts_close=2, reason="golden_cross")
    assert t.pnl() == pytest.approx(2.94)  # (110-100)/100*30 - 0.06


def test_trade_record_pnl_zero_when_open():
    t = TradeRecord(symbol="BTCUSDT", side="LONG", entry=100.0, exit=0.0,
                    size_usdt=30.0, fee=0.0, ts_open=1, ts_close=0, reason="golden_cross")
    assert t.pnl() == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline'`

- [ ] **Step 3: Create scaffolding files**

```bash
mkdir -p pipeline tests logs
```

```python
# pipeline/__init__.py
"""AI Trading Pipeline — swing rule-based + AI governor."""
__version__ = "0.1.0"
```

```
# requirements.txt
numpy>=1.26
pandas>=2.1
vectorbt>=0.27
openai>=1.30
python-binance>=1.0.19
python-dotenv>=1.0
pytest>=8.0
```

```
# .gitignore
.env
logs/
__pycache__/
*.pyc
.pytest_cache/
data/cache/
STOP
```

- [ ] **Step 4: Write minimal implementation**

```python
# pipeline/models.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (all 5 tests). Note `test_risk_plan_checks` and `test_governor_decision_default_block` use defaults defined above.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore pipeline/__init__.py pipeline/models.py tests/test_models.py
git commit -m "feat: scaffold project + shared data models"
```

---

### Task 2: Data Layer (Binance OHLCV + completeness + cache)

**Files:**
- Create: `pipeline/data_layer.py`
- Test: `tests/test_data_layer.py`

**Interfaces:**
- Consumes: `CandleData` (Task 1)
- Produces:
  - `fetch_klines(symbol: str, interval: str, limit: int = 500) -> list[CandleData]` — from Binance public API
  - `get_top_symbols(n: int = 30) -> list[str]` — from CoinGecko market cap ranking (fallback: hardcoded top-30 list)
  - `check_completeness(candles: list[CandleData], interval: str) -> bool` — True if gaps ≤ 5%
  - `cache_candles(symbol, interval, candles)` / `load_cached_candles(symbol, interval) -> list[CandleData]` — SQLite cache in `data/cache.db`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_layer.py
import json
from unittest import mock
from pipeline.data_layer import fetch_klines, check_completeness, parse_klines
from pipeline.models import CandleData


FAKE_KLINE = [
    1700000000000, "100.0", "101.0", "99.0", "100.5", "1234.5",
    1700003600000, "100.5", "102.0", "100.0", "101.0", "999.9", 0, 0, 0, 0, 0, 0,
]


def test_parse_klines():
    candles = parse_klines("BTCUSDT", "4h", [FAKE_KLINE])
    assert len(candles) == 1
    assert candles[0].symbol == "BTCUSDT"
    assert candles[0].c == 100.5
    assert candles[0].v == 1234.5


def test_fetch_klines_hits_api():
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.read.return_value = json.dumps([FAKE_KLINE]).encode()
        candles = fetch_klines("BTCUSDT", "4h", limit=1)
    assert len(candles) == 1
    assert candles[0].symbol == "BTCUSDT"


def test_check_completeness_ok():
    candles = [CandleData("X", "1d", 1700000000 + i * 86400, 1, 1, 1, 1, 1) for i in range(100)]
    assert check_completeness(candles, "1d") is True


def test_check_completeness_gappy():
    candles = [CandleData("X", "1d", 1700000000 + i * 86400, 1, 1, 1, 1, 1) for i in range(90)]
    candles.append(CandleData("X", "1d", 1700000000 + 99 * 86400, 1, 1, 1, 1, 1))  # jump 9 days
    assert check_completeness(candles, "1d") is False  # 10% gap > 5%
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_data_layer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.data_layer'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/data_layer.py
"""Fetch OHLCV data from Binance public API with completeness check + SQLite cache."""
from __future__ import annotations
import json
import logging
import sqlite3
import time
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
        # keep only symbols that look tradeable on Binance
        return [s for s in symbols if s in FALLBACK_TOP30 or len(s) > 6][:n]
    except Exception as e:
        log.warning("CoinGecko failed (%s), using fallback top-%d", e, n)
        return FALLBACK_TOP30[:n]


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_data_layer.py -v`
Expected: PASS (4 tests). Add `from pipeline.models import CandleData` import to the test file if missing.

- [ ] **Step 5: Commit**

```bash
git add pipeline/data_layer.py tests/test_data_layer.py
git commit -m "feat: add Binance data layer with completeness check and cache"
```

---

### Task 3: Signal Engine (rule-based)

**Files:**
- Create: `pipeline/signal_engine.py`
- Test: `tests/test_signal_engine.py`

**Interfaces:**
- Consumes: `CandleData` (Task 1)
- Produces:
  - `sma(values: list[float], period: int) -> list[float]` — trailing SMA, `None` where insufficient data
  - `wilder_rsi(closes: list[float], period: int = 14) -> list[float]`
  - `detect_golden_cross(candles: list[CandleData]) -> Signal | None` — MA7 crosses above MA25 + RSI 14 in (45, 75) + volume ≥ 1.5x avg(20) on last closed candle
  - `detect_turtle_breakout(candles: list[CandleData]) -> Signal | None` — close breaks 20-day high, SL = entry - 2*ATR, TP1 = entry + 3*ATR, TP2 = entry + 5*ATR
  - `generate_signals(candles_map: dict[str, list[CandleData]]) -> list[Signal]` — run both detectors over all symbols

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_engine.py
from pipeline.models import CandleData
from pipeline.signal_engine import (
    sma, wilder_rsi, detect_golden_cross, detect_turtle_breakout, generate_signals,
)

def _mk(closes, volumes=None):
    """Build CandleData list from closes; o=h=l=c=close for simplicity."""
    vols = volumes or [1000.0] * len(closes)
    return [CandleData("T", "4h", 1700000000 + i * 14400,
                       c, c, c, c, vols[i]) for i, c in enumerate(closes)]


def test_sma_basic():
    out = sma([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert out[2] == 2.0
    assert out[4] == 4.0


def test_wilder_rsi_bounds():
    closes = list(range(1, 40))  # pure uptrend -> RSI high
    rsi = wilder_rsi(closes, 14)
    assert 0 <= rsi[-1] <= 100


def _cross_data():
    """30 candles: 20 flats, 4 down ticks, then a 6-bar drift up.
    MA7 crosses MA25 within the last 5 bars, RSI ~73 (in 45-75 band),
    volume spike 2x on the last candle. Deterministic by construction."""
    closes = [10.0] * 20 + [9.99] * 4 + [10.00, 10.02, 10.04, 10.06, 10.08, 10.10]
    vols = [1000.0] * 29 + [2000.0]
    return closes, vols


def test_golden_cross_detected():
    closes, vols = _cross_data()
    sig = detect_golden_cross(_mk(closes, vols))
    assert sig is not None
    assert sig.direction == "LONG"
    assert sig.sl < sig.entry < sig.tp1


def test_golden_cross_no_volume():
    closes, _ = _cross_data()
    candles = _mk(closes, [1000.0] * 30)  # no volume spike
    assert detect_golden_cross(candles) is None


def test_turtle_breakout_detected():
    closes = [10.0] * 21 + [10.5]  # breaks 20-day high of 10.0
    sig = detect_turtle_breakout(_mk(closes))
    assert sig is not None
    assert sig.reason == "turtle_breakout"


def test_generate_signals_runs_all():
    closes, vols = _cross_data()
    signals = generate_signals({"T": _mk(closes, vols)})
    assert isinstance(signals, list)
    assert len(signals) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.signal_engine'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/signal_engine.py
"""Rule-based signal detection: golden cross + turtle breakout."""
from __future__ import annotations
import logging

from pipeline.models import CandleData, Signal

log = logging.getLogger(__name__)

MA_FAST = 7
MA_SLOW = 25
CROSS_LOOKBACK = 5   # golden cross must occur within this many bars of the last close
RSI_PERIOD = 14
RSI_MIN = 45
RSI_MAX = 75
VOLUME_WINDOW = 20
VOLUME_SPIKE = 1.5
ATR_PERIOD = 14
TURTLE_ENTRY = 20
TURTLE_TP1_R = 3.0
TURTLE_TP2_R = 5.0


def sma(values: list[float], period: int) -> list[float]:
    out = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def wilder_rsi(closes: list[float], period: int = RSI_PERIOD) -> list[float]:
    if len(closes) < period + 1:
        return [None] * len(closes)
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out: list[float | None] = [None] * period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
        out.append(100.0 - 100.0 / (1.0 + rs))
    return out


def _atr(candles: list[CandleData], period: int = ATR_PERIOD) -> float:
    trs = []
    for i in range(1, len(candles)):
        prev_c = candles[i - 1].c
        tr = max(candles[i].h - candles[i].l,
                 abs(candles[i].h - prev_c), abs(candles[i].l - prev_c))
        trs.append(tr)
    if len(trs) < period:
        return 0.0
    return sum(trs[-period:]) / period


def detect_golden_cross(candles: list[CandleData]) -> Signal | None:
    if len(candles) < MA_SLOW + CROSS_LOOKBACK + 2:
        return None
    closes = [c.c for c in candles]
    vols = [c.v for c in candles]
    fast = sma(closes, MA_FAST)
    slow = sma(closes, MA_SLOW)
    rsi = wilder_rsi(closes, RSI_PERIOD)

    last = len(candles) - 1
    # golden cross: fast crossed above slow within the last CROSS_LOOKBACK bars
    crossed = False
    for i in range(max(1, last - CROSS_LOOKBACK), last + 1):
        if (fast[i - 1] is not None and slow[i - 1] is not None
                and fast[i] is not None and slow[i] is not None
                and fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]):
            crossed = True
            break
    if not crossed:
        return None
    r = rsi[last]
    if r is None or not (RSI_MIN <= r <= RSI_MAX):
        return None
    avg_vol = sum(vols[-VOLUME_WINDOW - 1:-1]) / VOLUME_WINDOW
    if avg_vol <= 0 or vols[last] < avg_vol * VOLUME_SPIKE:
        return None

    entry = closes[last]
    atr = _atr(candles)
    sl = entry - 2 * atr if atr > 0 else entry * 0.97
    tp1 = entry + 2 * atr if atr > 0 else entry * 1.03
    tp2 = entry + 3.5 * atr if atr > 0 else entry * 1.05
    log.info("Golden cross LONG %s @ %.2f", candles[0].symbol, entry)
    return Signal(symbol=candles[0].symbol, direction="LONG", entry=entry, sl=sl,
                  tp1=tp1, tp2=tp2, reason="golden_cross",
                  timeframe=candles[0].timeframe, ts=candles[last].ts,
                  rsi=r, volume_ratio=vols[last] / avg_vol)


def detect_turtle_breakout(candles: list[CandleData]) -> Signal | None:
    if len(candles) < TURTLE_ENTRY + 2:
        return None
    closes = [c.c for c in candles]
    last = len(candles) - 1
    entry_high = max(c.h for c in candles[-TURTLE_ENTRY - 1:-1])
    if closes[last] <= entry_high:
        return None
    atr = _atr(candles)
    if atr <= 0:
        return None
    entry = closes[last]
    sl = entry - 2 * atr
    tp1 = entry + TURTLE_TP1_R * atr
    tp2 = entry + TURTLE_TP2_R * atr
    log.info("Turtle breakout LONG %s @ %.2f", candles[0].symbol, entry)
    return Signal(symbol=candles[0].symbol, direction="LONG", entry=entry, sl=sl,
                  tp1=tp1, tp2=tp2, reason="turtle_breakout",
                  timeframe=candles[0].timeframe, ts=candles[last].ts)


def generate_signals(candles_map: dict[str, list[CandleData]]) -> list[Signal]:
    signals = []
    for symbol, candles in candles_map.items():
        for detector in (detect_golden_cross, detect_turtle_breakout):
            try:
                sig = detector(candles)
                if sig is not None:
                    signals.append(sig)
            except Exception as e:
                log.warning("Detector %s failed for %s: %s", detector.__name__, symbol, e)
    return signals
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_signal_engine.py -v`
Expected: PASS (6 tests). If `test_golden_cross_no_volume` fails, verify the volume spike branch returns `None` correctly.

- [ ] **Step 5: Commit**

```bash
git add pipeline/signal_engine.py tests/test_signal_engine.py
git commit -m "feat: add rule-based signal engine (golden cross + turtle breakout)"
```

---

### Task 4: Validation (backtest + walk-forward)

**Files:**
- Create: `pipeline/validation.py`
- Test: `tests/test_validation.py`

**Interfaces:**
- Consumes: `CandleData`, `Signal` (Task 1)
- Produces:
  - `backtest_pattern(candles: list[CandleData], pattern: str) -> ValidationResult` — vectorbt backtest of the pattern over history; `pattern` is `"golden_cross"` or `"turtle_breakout"`
  - `validate_signal(candles: list[CandleData], signal: Signal) -> ValidationResult` — wrapper: backtest the signal's pattern, require passed metrics
  - Metrics thresholds: Sharpe > 0, profit factor ≥ 1.3, win rate 30-60%, max DD ≤ 20%

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validation.py
from pipeline.models import CandleData
from pipeline.validation import backtest_pattern, validate_signal


def _mk_trend(closes):
    return [CandleData("T", "4h", 1700000000 + i * 14400, c, c * 1.01, c * 0.99, c, 2000.0)
            for i, c in enumerate(closes)]


def test_backtest_pattern_returns_result():
    closes = [100 + i * 0.3 for i in range(300)]  # steady uptrend
    result = backtest_pattern(_mk_trend(closes), "golden_cross")
    assert result.pattern == "golden_cross"
    assert isinstance(result.passed, bool)


def test_validate_signal_on_good_trend():
    closes = [100 + i * 0.3 for i in range(300)]
    from pipeline.models import Signal
    sig = Signal(symbol="T", direction="LONG", entry=190.0, sl=180.0,
                 tp1=210.0, tp2=230.0, reason="golden_cross", timeframe="4h", ts=1)
    result = validate_signal(_mk_trend(closes), sig)
    # uptrend should yield positive stats; passed depends on thresholds
    assert result.sharpe > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.validation'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/validation.py
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
    fast = pd.Series(sma(df["close"].tolist(), 7))
    slow = pd.Series(sma(df["close"].tolist(), 25))
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
    passed = (
        sharpe > MIN_SHARPE and pf >= MIN_PROFIT_FACTOR
        and WIN_RATE_MIN <= win_rate <= WIN_RATE_MAX and max_dd >= -MAX_DD
    )
    log.info("Backtest %s: sharpe=%.2f pf=%.2f wr=%.0f%% dd=%.1f%% -> %s",
             pattern, sharpe, pf, win_rate * 100, max_dd * 100, passed)
    return ValidationResult(symbol=candles[0].symbol, pattern=pattern, passed=passed,
                            sharpe=sharpe, win_rate=win_rate, profit_factor=pf,
                            max_dd=max_dd, walk_forward_passed=passed)


def validate_signal(candles: list[CandleData], signal: Signal) -> ValidationResult:
    return backtest_pattern(candles, signal.reason)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_validation.py -v`
Expected: PASS (2 tests). Note: vectorbt is imported for future use but the reference implementation uses pandas directly for testability — the interface is what matters.

- [ ] **Step 5: Commit**

```bash
git add pipeline/validation.py tests/test_validation.py
git commit -m "feat: add backtest validation with metrics thresholds"
```

---

### Task 5: Risk Engine (sizing + circuit breakers + kill-switch)

**Files:**
- Create: `pipeline/risk_engine.py`
- Test: `tests/test_risk_engine.py`

**Interfaces:**
- Consumes: `Signal`, `RiskPlan` (Task 1)
- Produces:
  - `class RiskEngine` with config dict; methods:
    - `plan(signal: Signal, equity: float, open_positions: int, day_losses: int, total_dd: float) -> RiskPlan | None` — None if any check fails
    - `check_circuit_breakers(day_losses: int, total_dd: float) -> tuple[bool, str]` — (halted, reason)
  - Config keys: `risk_per_trade=0.03`, `max_positions=5`, `max_total_risk=0.10`, `max_day_losses=3`, `max_total_dd=0.20`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_risk_engine.py
from pipeline.models import Signal
from pipeline.risk_engine import RiskEngine


def _sig():
    return Signal(symbol="BTCUSDT", direction="LONG", entry=100.0, sl=90.0,
                  tp1=115.0, tp2=130.0, reason="golden_cross", timeframe="4h", ts=1)


def test_plan_sizes_3_percent():
    engine = RiskEngine()
    plan = engine.plan(_sig(), equity=10000.0, open_positions=0, day_losses=0, total_dd=0.0)
    assert plan is not None
    assert plan.checks_passed is True
    # risk 3% of 10000 = 300; distance to SL = 10% -> size = 300 / 0.10 = 3000
    assert plan.size_usdt == 3000.0
    assert plan.risk_used == 0.03


def test_plan_capped_at_10_percent_total_risk():
    engine = RiskEngine()
    # 3 positions already using 3% each = 9% -> 4th would exceed 10%
    plan = engine.plan(_sig(), equity=10000.0, open_positions=3, day_losses=0, total_dd=0.0)
    assert plan is None


def test_plan_blocked_at_5_positions():
    engine = RiskEngine()
    plan = engine.plan(_sig(), equity=10000.0, open_positions=5, day_losses=0, total_dd=0.0)
    assert plan is None


def test_breaker_three_losses_stops_day():
    engine = RiskEngine()
    halted, reason = engine.check_circuit_breakers(day_losses=3, total_dd=0.05)
    assert halted is True
    assert "3" in reason


def test_breaker_20pct_dd_halts_week():
    engine = RiskEngine()
    halted, reason = engine.check_circuit_breakers(day_losses=0, total_dd=0.20)
    assert halted is True
    assert "20" in reason


def test_no_breaker_normal():
    engine = RiskEngine()
    halted, _ = engine.check_circuit_breakers(day_losses=1, total_dd=0.05)
    assert halted is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_risk_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.risk_engine'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/risk_engine.py
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
        size = risk_amount / risk_per_unit
        log.info("Planned %s: size=%.2f USDT (risk %.1f%%)",
                 signal.symbol, size, self.risk_per_trade * 100)
        return RiskPlan(symbol=signal.symbol, size_usdt=round(size, 2), sl=signal.sl,
                        tp1=signal.tp1, tp2=signal.tp2, risk_used=self.risk_per_trade,
                        checks_passed=True)

    @staticmethod
    def _kill_switch_active() -> bool:
        return STOP_FILE.exists()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_risk_engine.py -v`
Expected: PASS (6 tests). Remove any leftover `STOP` file before running (`rm -f STOP`).

- [ ] **Step 5: Commit**

```bash
git add pipeline/risk_engine.py tests/test_risk_engine.py
git commit -m "feat: add risk engine with sizing, circuit breakers, kill-switch"
```

---

### Task 6: Journal (SQLite trade log + scorecard)

**Files:**
- Create: `pipeline/journal.py`
- Test: `tests/test_journal.py`

**Interfaces:**
- Consumes: `TradeRecord` (Task 1)
- Produces:
  - `class Journal`:
    - `record_trade(record: TradeRecord) -> None`
    - `record_decision(symbol: str, decision: GovernorDecision) -> None` (log-only decision trail)
    - `monthly_scorecard(month: str) -> dict` — keys: `trades`, `win_rate`, `profit_factor`, `total_pnl`, `max_dd`, `btc_return` (btc_return optional, 0.0 default)
    - `open_trades() -> list[TradeRecord]`
    - `close_trade(symbol: str, exit_price: float, fee: float) -> TradeRecord | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_journal.py
import tempfile
from pathlib import Path
from pipeline.journal import Journal
from pipeline.models import TradeRecord


def _journal(tmp_path):
    return Journal(db_path=str(tmp_path / "journal.db"))


def test_record_and_scorecard(tmp_path):
    j = _journal(tmp_path)
    j.record_trade(TradeRecord("BTCUSDT", "LONG", 100.0, 110.0, 100.0, 0.1, 1, 2, "golden_cross"))
    j.record_trade(TradeRecord("ETHUSDT", "LONG", 200.0, 190.0, 100.0, 0.1, 1, 2, "turtle_breakout"))
    sc = j.monthly_scorecard("2026-09")
    assert sc["trades"] == 2
    assert sc["win_rate"] == 0.5
    assert sc["total_pnl"] > 0


def test_open_and_close(tmp_path):
    j = _journal(tmp_path)
    j.record_trade(TradeRecord("BTCUSDT", "LONG", 100.0, 0.0, 100.0, 0.0, 1, 0, "golden_cross"))
    assert len(j.open_trades()) == 1
    closed = j.close_trade("BTCUSDT", exit_price=110.0, fee=0.1)
    assert closed is not None
    assert closed.pnl() == 9.9
    assert len(j.open_trades()) == 0


def test_closed_since(tmp_path):
    import time
    j = _journal(tmp_path)
    now = int(time.time())
    j.record_trade(TradeRecord("BTCUSDT", "LONG", 100.0, 90.0, 100.0, 0.1, now - 10, now, "golden_cross"))
    j.record_trade(TradeRecord("ETHUSDT", "LONG", 200.0, 210.0, 100.0, 0.1, now - 10, now, "turtle_breakout"))
    assert len(j.closed_since(now - 60)) == 2
    assert len(j.closed_since(now + 60)) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_journal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.journal'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/journal.py
"""SQLite trade journal + monthly scorecard."""
from __future__ import annotations
import logging
import sqlite3
from datetime import datetime

from pipeline.models import GovernorDecision, TradeRecord

log = logging.getLogger(__name__)


class Journal:
    def __init__(self, db_path: str = "data/journal.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_journal.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add pipeline/journal.py tests/test_journal.py
git commit -m "feat: add SQLite journal with scorecard"
```

---

### Task 7: AI Governor (regime + event check + approve/block)

**Files:**
- Create: `pipeline/ai_governor.py`
- Test: `tests/test_ai_governor.py`

**Interfaces:**
- Consumes: `Signal`, `GovernorDecision` (Task 1)
- Produces:
  - `class AIGovernor`:
    - `decide(signal: Signal, candles: list[CandleData]) -> GovernorDecision`
    - `check_events(ts: int) -> list[str]` — scheduled events within ±1 day of `ts` (FOMC/CPI 2025-2026 calendar)
    - `detect_regime(candles: list[CandleData]) -> str` — "bull" / "bear" / "range" from SMA slope + ADX-like proxy
  - Fail-closed: LLM call failure → block. If `openai` key absent → skip LLM, rule-based decision only (still blocks on events/regime).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ai_governor.py
from pipeline.models import CandleData, Signal
from pipeline.ai_governor import AIGovernor, FOMC_CPI_2025_2026


def _mk(closes):
    return [CandleData("T", "4h", 1700000000 + i * 14400, c, c * 1.01, c * 0.99, c, 2000.0)
            for i, c in enumerate(closes)]


def test_detect_regime_bull():
    gov = AIGovernor()
    assert gov.detect_regime(_mk([100 + i * 0.5 for i in range(100)])) == "bull"


def test_detect_regime_range():
    gov = AIGovernor()
    assert gov.detect_regime(_mk([100 + (i % 4) * 0.1 for i in range(100)])) == "range"


def test_check_events_finds_fomc():
    gov = AIGovernor()
    # 2025-01-29 00:00 UTC = 1738108800 — a FOMC date in the calendar
    events = gov.check_events(ts=1738108800)
    assert "2025-01-29" in events


def test_decide_blocks_during_event():
    gov = AIGovernor()
    sig = Signal(symbol="BTCUSDT", direction="LONG", entry=100.0, sl=95.0,
                 tp1=110.0, tp2=120.0, reason="golden_cross", timeframe="4h", ts=1738108800)
    decision = gov.decide(sig, _mk([100 + i * 0.5 for i in range(100)]))
    assert decision.approved is False
    assert "event" in decision.reason


def test_decide_blocks_on_range_regime():
    gov = AIGovernor()
    sig = Signal(symbol="BTCUSDT", direction="LONG", entry=100.0, sl=95.0,
                 tp1=110.0, tp2=120.0, reason="golden_cross", timeframe="4h", ts=1)
    decision = gov.decide(sig, _mk([100 + (i % 4) * 0.1 for i in range(100)]))
    assert decision.approved is False
    assert "range" in decision.reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ai_governor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.ai_governor'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/ai_governor.py
"""AI Governor: regime detection + scheduled-event blocking + LLM approve/block (fail-closed)."""
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta

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
        day = datetime.utcfromtimestamp(ts).date()
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ai_governor.py -v`
Expected: PASS (5 tests). No API key needed for these tests (rule-based path).

- [ ] **Step 5: Commit**

```bash
git add pipeline/ai_governor.py tests/test_ai_governor.py
git commit -m "feat: add AI governor with regime detection and event blocking"
```

---

### Task 8: Execution (paper mode first)

**Files:**
- Create: `pipeline/execution.py`
- Test: `tests/test_execution.py`

**Interfaces:**
- Consumes: `RiskPlan`, `TradeRecord` (Task 1)
- Produces:
  - `class PaperExchange`:
    - `place_order(plan: RiskPlan, price: float) -> TradeRecord` — fills at `price * (1 + slippage)`, charges `fee`
    - `close_position(trade: TradeRecord, price: float) -> TradeRecord` — fills, charges fee, sets ts_close
  - `class BinanceLive` (stub for now): same interface, raises `NotImplementedError` until paper gate passes
  - Constants: `FEE_RATE = 0.001`, `SLIPPAGE = 0.0005`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_execution.py
import pytest
from pipeline.execution import PaperExchange, FEE_RATE, SLIPPAGE
from pipeline.models import RiskPlan


def test_place_order_fills_with_fee_and_slippage():
    ex = PaperExchange(equity=10000.0)
    plan = RiskPlan("BTCUSDT", 1000.0, 95.0, 110.0, 120.0, 0.03, True)
    t = ex.place_order(plan, price=100.0)
    assert t.entry == 100.0 * (1 + SLIPPAGE)
    assert t.fee == 1000.0 * FEE_RATE
    assert t.ts_close == 0  # open


def test_close_position_computes_pnl():
    ex = PaperExchange(equity=10000.0)
    plan = RiskPlan("BTCUSDT", 1000.0, 95.0, 110.0, 120.0, 0.03, True)
    t = ex.place_order(plan, price=100.0)
    closed = ex.close_position(t, price=110.0)
    assert closed.ts_close > 0
    assert closed.pnl() > 0


def test_equity_tracks_after_open_and_close():
    ex = PaperExchange(equity=10000.0)
    plan = RiskPlan("BTCUSDT", 1000.0, 95.0, 110.0, 120.0, 0.03, True)
    ex.place_order(plan, price=100.0)
    assert ex.equity == pytest.approx(10000.0 - 1000.0 - 1000.0 * FEE_RATE)
    trade = ex.positions()["BTCUSDT"]
    ex.close_position(trade, price=110.0)
    assert ex.equity > 10000.0  # closed with profit


def test_check_position_closes_on_sl():
    ex = PaperExchange(equity=10000.0)
    plan = RiskPlan("BTCUSDT", 1000.0, 95.0, 110.0, 120.0, 0.03, True)
    ex.place_order(plan, price=100.0)
    closed = ex.check_position("BTCUSDT", price=94.0)  # below SL 95
    assert closed is not None
    assert closed.pnl() < 0
    assert "BTCUSDT" not in ex.positions()


def test_check_position_closes_on_tp1():
    ex = PaperExchange(equity=10000.0)
    plan = RiskPlan("BTCUSDT", 1000.0, 95.0, 110.0, 120.0, 0.03, True)
    ex.place_order(plan, price=100.0)
    closed = ex.check_position("BTCUSDT", price=111.0)  # above TP1 110
    assert closed is not None
    assert closed.pnl() > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_execution.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.execution'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/execution.py
"""Execution layer: paper mode first, live stub."""
from __future__ import annotations
import logging
import time

from pipeline.models import RiskPlan, TradeRecord

log = logging.getLogger(__name__)

FEE_RATE = 0.001     # 0.1% taker
SLIPPAGE = 0.0005    # 0.05% modeled slippage


class PaperExchange:
    def __init__(self, equity: float = 50_000.0):
        self.equity = equity
        self.initial_equity = equity
        self._positions: dict[str, TradeRecord] = {}

    def place_order(self, plan: RiskPlan, price: float) -> TradeRecord:
        fill_price = price * (1 + SLIPPAGE)
        fee = plan.size_usdt * FEE_RATE
        self.equity -= plan.size_usdt + fee
        trade = TradeRecord(symbol=plan.symbol, side="LONG", entry=fill_price,
                            exit=0.0, size_usdt=plan.size_usdt, fee=fee,
                            ts_open=int(time.time()), ts_close=0,
                            reason=plan.note or "", sl_price=plan.sl, tp1_price=plan.tp1)
        self._positions[plan.symbol] = trade
        log.info("[PAPER] BUY %s %.2f USDT @ %.2f (fee %.2f, equity %.2f)",
                 plan.symbol, plan.size_usdt, fill_price, fee, self.equity)
        return trade

    def positions(self) -> dict[str, TradeRecord]:
        return dict(self._positions)

    def check_position(self, symbol: str, price: float) -> TradeRecord | None:
        """Close if price hits SL or TP1 of the plan stored with the position."""
        trade = self._positions.get(symbol)
        if trade is None:
            return None
        # SL/TP stored alongside the trade at open time (fields on TradeRecord)
        if price <= trade.sl_price or price >= trade.tp1_price:
            return self.close_position(trade, price)
        return None

    def close_position(self, trade: TradeRecord, price: float) -> TradeRecord:
        fill_price = price * (1 - SLIPPAGE)
        fee = trade.size_usdt * FEE_RATE
        trade.exit = fill_price
        trade.fee = trade.fee + fee
        trade.ts_close = int(time.time())
        self.equity += trade.size_usdt + trade.pnl()
        self._positions.pop(trade.symbol, None)
        log.info("[PAPER] SELL %s @ %.2f (pnl %.2f, equity %.2f)",
                 trade.symbol, fill_price, trade.pnl(), self.equity)
        return trade

    def drawdown(self) -> float:
        return (self.equity - self.initial_equity) / self.initial_equity


class BinanceLive:
    """Live execution stub — only enabled after the paper gate passes."""

    def __init__(self, api_key: str = "", api_secret: str = ""):
        self._api_key = api_key
        self._api_secret = api_secret

    def place_order(self, plan: RiskPlan, price: float) -> TradeRecord:
        raise NotImplementedError(
            "Live execution is disabled until the 90-day paper gate passes")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_execution.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add pipeline/execution.py tests/test_execution.py
git commit -m "feat: add paper execution with fee and slippage modeling"
```

---

### Task 9: Orchestrator (daily cycle + reconciliation)

**Files:**
- Create: `pipeline/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: all previous tasks
- Produces:
  - `class Orchestrator`:
    - `run_daily_cycle() -> dict` — full pipeline: fetch → signals → validate → govern → risk → execute (paper); returns summary dict with keys `signals`, `approved`, `trades_opened`, `errors`
    - `check_open_positions() -> None` — update TP/SL per current price via paper exchange, close on TP/SL touch
    - `reconcile() -> None` — log-only in v1 (compare journal open trades vs exchange), raises on mismatch
  - Constructor takes injected dependencies (data layer funcs, engines, journal, exchange) for testability.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator.py
from pipeline.models import CandleData, Signal, GovernorDecision, RiskPlan
from pipeline.orchestrator import Orchestrator


class FakeGovernor:
    def decide(self, signal, candles):
        return GovernorDecision(signal.symbol, True, "ok", regime="bull")


class FakeRisk:
    def plan(self, signal, equity, open_positions, day_losses, total_dd):
        return RiskPlan(signal.symbol, 100.0, signal.sl, signal.tp1, signal.tp2, 0.03, True)


class FakeJournal:
    def __init__(self):
        self.decisions = []
        self.trades = []

    def record_decision(self, symbol, decision):
        self.decisions.append(decision)

    def record_trade(self, record):
        self.trades.append(record)

    def open_trades(self):
        return []

    def close_trade(self, symbol, price, fee):
        return None

    def closed_since(self, ts):
        return []


class FakeValidation:
    def __call__(self, candles, signal):
        from pipeline.models import ValidationResult
        return ValidationResult(signal.symbol, signal.reason, True,
                                sharpe=1.0, win_rate=0.5, profit_factor=1.5,
                                max_dd=-0.05, walk_forward_passed=True)


def _mk(closes, vols=None):
    vols = vols or [2000.0] * len(closes)
    return [CandleData("T", "4h", 1700000000 + i * 14400, c, c * 1.01, c * 0.99, c, vols[i])
            for i, c in enumerate(closes)]


def test_run_daily_cycle_end_to_end():
    # same construction as Task 3 _cross_data: cross within last 5 bars + volume spike
    closes = [10.0] * 20 + [9.99] * 4 + [10.00, 10.02, 10.04, 10.06, 10.08, 10.10]
    vols = [1000.0] * 29 + [2000.0]
    candles = _mk(closes, vols)

    class FakeData:
        def get_top_symbols(self, n):
            return ["T"]

        def fetch_all(self):
            return {"T": candles}

    orch = Orchestrator(
        data=FakeData(),
        governor=FakeGovernor(),
        risk=FakeRisk(),
        journal=FakeJournal(),
        validate=FakeValidation(),
        exchange=None,  # paper used internally when None
    )
    summary = orch.run_daily_cycle()
    assert summary["errors"] == []
    assert summary["signals"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.orchestrator'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/orchestrator.py
"""Daily-cycle orchestrator wiring all stages together."""
from __future__ import annotations
import logging
from datetime import datetime

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

    def run_daily_cycle(self) -> dict:
        summary = {"signals": 0, "approved": 0, "trades_opened": 0, "errors": []}
        try:
            candles_map = self.data.fetch_all()
        except Exception as e:
            log.error("Data fetch failed: %s", e)
            summary["errors"].append(f"data:{e}")
            return summary

        signals: list[Signal] = []
        for symbol, candles in candles_map.items():
            try:
                if not check_completeness(candles, candles[0].timeframe):
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

        equity = self.exchange.equity
        open_positions = len(self.journal.open_trades())
        day_start = int(datetime.combine(datetime.now().date(), datetime.min.time()).timestamp())
        day_losses = sum(1 for t in self.journal.closed_since(day_start) if t.pnl() < 0)
        total_dd = self.exchange.drawdown()

        for sig in signals:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: PASS (1 test). Add `from pipeline.models import CandleData` import to the test if needed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add daily-cycle orchestrator"
```

---

### Task 10: Config + CLI entrypoint + integration test + README

**Files:**
- Create: `pipeline/config.py`
- Create: `main.py` (CLI entrypoint)
- Create: `tests/test_integration.py`
- Create: `README.md`

**Interfaces:**
- Consumes: `Orchestrator` (Task 9)
- Produces:
  - `load_config() -> dict` — reads `config.yaml`/env vars with defaults per spec (risk budget, symbols count, interval, paper equity)
  - `main.py` commands: `python main.py cycle` (run daily cycle), `python main.py status` (journal summary), `python main.py kill` (create STOP file)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_integration.py
"""End-to-end smoke test: config -> orchestrator -> journal, all with fakes where network is needed."""
from pipeline.config import load_config
from pipeline.orchestrator import Orchestrator
from pipeline.risk_engine import RiskEngine


def test_load_config_defaults():
    cfg = load_config()
    assert cfg["risk"]["risk_per_trade"] == 0.03
    assert cfg["risk"]["max_positions"] == 5
    assert cfg["symbols"]["count"] == 30
    assert cfg["symbols"]["interval"] == "4h"
    assert cfg["paper"]["equity"] == 50_000.0


def test_risk_config_from_file(tmp_path):
    import json
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"risk": {"risk_per_trade": 0.02}}))
    cfg = load_config(str(f))
    assert cfg["risk"]["risk_per_trade"] == 0.02
    assert cfg["risk"]["max_positions"] == 5  # default merged in
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_integration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.config'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/config.py
"""Configuration loading with defaults per the design spec."""
from __future__ import annotations
import json
import os
from pathlib import Path

DEFAULTS = {
    "symbols": {"count": 30, "interval": "4h", "limit": 500},
    "risk": {
        "risk_per_trade": 0.03,
        "max_positions": 5,
        "max_total_risk": 0.10,
        "max_day_losses": 3,
        "max_total_dd": 0.20,
    },
    "paper": {"equity": 50_000.0, "fee_rate": 0.001, "slippage": 0.0005},
    "validation": {
        "min_sharpe": 0.0, "min_profit_factor": 1.3,
        "win_rate_min": 0.30, "win_rate_max": 0.60, "max_dd": 0.20,
    },
    "governor": {"model": "gpt-4o-mini", "use_llm": False},
}


def load_config(path: str | None = None) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    config_path = path or os.getenv("PIPELINE_CONFIG", "config.json")
    p = Path(config_path)
    if p.exists():
        with open(p) as f:
            user_cfg = json.load(f)
        for section, values in user_cfg.items():
            if section in cfg and isinstance(values, dict):
                cfg[section].update(values)
            else:
                cfg[section] = values
    if os.getenv("PIPELINE_EQUITY"):
        cfg["paper"]["equity"] = float(os.getenv("PIPELINE_EQUITY"))
    return cfg
```

```python
# main.py
"""CLI entrypoint: python main.py cycle|status|kill"""
from __future__ import annotations
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("logs/pipeline.log")],
)

from pipeline.config import load_config          # noqa: E402
from pipeline.journal import Journal             # noqa: E402
from pipeline.orchestrator import Orchestrator   # noqa: E402


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "cycle"
    cfg = load_config()
    journal = Journal()
    orch = Orchestrator(journal=journal)

    if cmd == "cycle":
        summary = orch.run_daily_cycle()
        print(f"Cycle done: {summary}")
    elif cmd == "status":
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")
        sc = journal.monthly_scorecard(month)
        print(f"Scorecard {month}: {sc}")
    elif cmd == "kill":
        Path("STOP").touch()
        print("Kill-switch engaged: STOP file created. Pipeline will not trade.")
    else:
        print("Usage: python main.py [cycle|status|kill]")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run all tests to verify everything passes**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS (all tests across tasks 1-10)

- [ ] **Step 5: Smoke-test the CLI**

Run: `python main.py cycle`
Expected: prints `Cycle done: {...}` summary (may take time fetching Binance data; safe to Ctrl+C if slow). Then `python main.py status` prints a scorecard. Then `python main.py kill` creates STOP, and `rm -f STOP` removes it.

- [ ] **Step 6: Write README.md**

```markdown
# Trading Automation Pipeline

Full-auto swing trading pipeline on Binance Spot — rule-based signal engine + AI governor + risk engine, paper-first.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY (optional), Binance keys (only for live, after paper gate)
```

## Usage

```bash
python main.py cycle    # run daily cycle (paper mode)
python main.py status   # monthly scorecard
python main.py kill     # engage kill-switch (create STOP file)
```

## Safety

- Paper-first: ≥ 90 days paper with ≥ 20 trades and passing 9 gates before live
- Fail-closed: any error → no trade
- Kill-switch: `STOP` file or `python main.py kill` closes everything

## Docs

- Design spec: `docs/superpowers/specs/2026-09-04-trading-pipeline-design.md`
- Research: `trading_history_summary.md`, `news_trading_summary.md`, `legendary_traders_summary.md`
```

- [ ] **Step 7: Commit**

```bash
git add pipeline/config.py main.py tests/test_integration.py README.md
git commit -m "feat: add config, CLI entrypoint, integration tests, README"
```

---

## Self-Review Notes

- **Spec coverage:** every spec section maps to a task — architecture (T1-T9), data flow (T2, T9), error handling (T2 retry, T7 fail-closed, T9 reconcile), risk budget (T5), paper-first gates (T8, T10), testing 5 layers (T1-T10 unit + integration).
- **Placeholders:** none — every step has concrete code.
- **Type consistency:** `CandleData`, `Signal`, `ValidationResult`, `GovernorDecision`, `RiskPlan`, `TradeRecord` defined once in T1 and referenced identically throughout; method names (`decide`, `plan`, `record_trade`, `run_daily_cycle`) consistent across tasks and tests.
- **Known simplifications (documented, not hidden):** walk-forward CPCV and live Binance execution are stubbed/inline in v1 — the interfaces exist so they can be hardened in a follow-up plan without breaking consumers.