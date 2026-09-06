"""Rule-based signal detection: golden cross (primary) + turtle breakout (disabled).

Backtest (2-3y, walk-forward) showed turtle entries were a drag and golden
cross TP1 = 2.0 ATR lost money out-of-sample; the surviving config is golden
cross only with TP1 = 2.8 ATR. Turtle code is kept for reference/experiments
but is not emitted by default."""
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
GOLDEN_SL_R = 2.0      # stop-loss: entry - 2 * ATR
GOLDEN_TP1_R = 2.8     # take-profit 1: backtest-validated (2.5-3.0 plateau; 2.0 lost OOS)
GOLDEN_TP2_R = 3.5
TURTLE_ENTRY = 20
TURTLE_TP1_R = 3.0
TURTLE_TP2_R = 5.0

# Multi-Horizon Momentum (AHL / Man Group — ตามคลิป TradeX Quant Ep.1):
# เทียบ close ปัจจุบันกับ close ย้อนหลัง 4 จุด (1w/2w/1m/2m): สูงกว่า = +1, ต่ำกว่า = -1
# → score ∈ {-4..+4}; ใช้เป็น gate ชั้น 2 ของ golden cross (walk-forward ยืนยัน:
# return = benchmark แต่ DD ตื้นกว่า — ใช้เป็นตัวลดความเสี่ยง ไม่ใช่ตัวเพิ่มกำไร)
MHM_HORIZONS_D = (7, 14, 30, 60)
MHM_STEP_SEC = {"1h": 3600, "4h": 14400, "1d": 86400}


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
    n = len(closes)
    if n < period + 1:
        return [None] * n
    gains, losses = [], []
    for i in range(1, n):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    # first computable RSI sits at close index `period` (covers closes[0..period])
    rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
    out: list[float | None] = [None] * period
    out.append(100.0 - 100.0 / (1.0 + rs))
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
    sl = entry - GOLDEN_SL_R * atr if atr > 0 else entry * 0.97
    tp1 = entry + GOLDEN_TP1_R * atr if atr > 0 else entry * 1.03
    tp2 = entry + GOLDEN_TP2_R * atr if atr > 0 else entry * 1.05
    log.info("Golden cross LONG %s @ %.2f", candles[0].symbol, entry)
    return Signal(symbol=candles[0].symbol, direction="LONG", entry=entry, sl=sl,
                  tp1=tp1, tp2=tp2, reason="golden_cross",
                  timeframe=candles[0].timeframe, ts=candles[last].ts,
                  rsi=r, volume_ratio=vols[last] / avg_vol, atr=atr)


def compute_mhm_score(candles: list[CandleData],
                      horizons_days: tuple[int, ...] = MHM_HORIZONS_D) -> float | None:
    """คะแนน Multi-Horizon Momentum จากแท่งที่มีอยู่ (ตัวเดียวกับ backtest_history.py
    compute_mhm_score แต่รับ list[CandleData] ของ live pipeline)

    เทียบ close ล่าสุดกับ close ย้อนหลังทุก horizon: สูงกว่า = +1, ต่ำกว่า = -1,
    เท่ากัน = 0 → รวมทุก horizon
    คืน None ถ้าข้อมูลไม่พอ (horizon ไกลสุดยังไม่มีแท่ง) — fail-closed ให้ gate บล็อก
    """
    if not candles:
        return None
    step = MHM_STEP_SEC.get(candles[0].timeframe)
    if step is None:
        return None
    closes = {c.ts: c.c for c in candles}
    last = candles[-1]
    score = 0.0
    for hd in horizons_days:
        bars = max(1, int(hd * 86400 // step))
        ts_ref = last.ts - bars * step
        prev = closes.get(ts_ref)
        if prev is None:
            return None  # ข้อมูลไม่ครบตาม horizon → ไม่ให้ผ่าน gate
        score += 1.0 if last.c > prev else (-1.0 if last.c < prev else 0.0)
    return score


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
                  timeframe=candles[0].timeframe, ts=candles[last].ts, atr=atr)


# Strategies emitted by the daily cycle. Turtle was disabled after the
# backtest showed it dragged returns down (golden+turtle -45% vs golden-only).
ENABLED_STRATEGIES = ("golden_cross",)
DETECTORS = {
    "golden_cross": detect_golden_cross,
    "turtle_breakout": detect_turtle_breakout,
}


def generate_signals(candles_map: dict[str, list[CandleData]]) -> list[Signal]:
    signals = []
    for symbol, candles in candles_map.items():
        for name, detector in DETECTORS.items():
            if name not in ENABLED_STRATEGIES:
                continue
            try:
                sig = detector(candles)
                if sig is not None:
                    signals.append(sig)
            except Exception as e:
                log.warning("Detector %s failed for %s: %s", detector.__name__, symbol, e)
    return signals
