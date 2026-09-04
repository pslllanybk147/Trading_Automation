import pytest
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
    """40 candles: downtrend then recovery. MA7 crosses above MA25 at
    candle 37 (within the last 5 bars), RSI(14) at last close ~59.8
    (in 45-75 band), volume spike 2x on the last candle.
    Deterministic by construction (verified against the detector)."""
    closes = [99.947, 99.469, 99.154, 99.296, 99.176, 98.994, 98.907, 98.939, 98.921, 98.493,
              97.917, 97.554, 97.155, 96.713, 96.82, 96.877, 96.513, 96.405, 96.102, 96.188,
              95.932, 95.53, 95.115, 94.936, 94.533, 94.372, 94.445, 94.615, 94.686, 95.184,
              95.414, 95.414, 95.39, 95.401, 95.696, 96.081, 96.264, 96.249, 96.408, 96.906]
    vols = [1000.0] * 39 + [2000.0]
    return closes, vols


def test_golden_cross_detected():
    closes, vols = _cross_data()
    sig = detect_golden_cross(_mk(closes, vols))
    assert sig is not None
    assert sig.direction == "LONG"
    assert sig.reason == "golden_cross"
    assert sig.sl < sig.entry < sig.tp1


def test_golden_cross_tp1_is_2_8_atr():
    # backtest-validated config: SL -2 ATR, TP1 +2.8 ATR -> R:R = 1.4
    closes, vols = _cross_data()
    sig = detect_golden_cross(_mk(closes, vols))
    assert sig is not None
    assert sig.rr() == pytest.approx(2.8 / 2.0)


def test_golden_cross_no_volume():
    closes, _ = _cross_data()
    candles = _mk(closes, [1000.0] * len(closes))  # no volume spike
    assert detect_golden_cross(candles) is None


def test_generate_signals_excludes_turtle_by_default():
    # turtle-only data (breakout bar) fires no signal: golden cross needs 32+
    # bars and an RSI band + volume spike, so turtle being disabled means [].
    closes = [10.0] * 21 + [10.5]
    assert generate_signals({"T": _mk(closes)}) == []


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
