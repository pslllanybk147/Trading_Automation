import math
from pipeline.models import CandleData, Signal
from pipeline.validation import backtest_pattern, validate_signal


def _mk_trend(closes):
    return [CandleData("T", "4h", 1700000000 + i * 14400, c, c * 1.01, c * 0.99, c, 2000.0)
            for i, c in enumerate(closes)]


def _wavy_uptrend(n=400, amp=2.0, period=20):
    """Rising sinusoid: golden crosses occur on each dip->rise, net positive."""
    closes = []
    px = 100.0
    for i in range(n):
        px += 0.2 + amp * math.sin(i / period)
        closes.append(round(px, 4))
    return closes


def test_backtest_pattern_returns_result():
    result = backtest_pattern(_mk_trend(_wavy_uptrend()), "golden_cross")
    assert result.pattern == "golden_cross"
    assert isinstance(result.passed, bool)


def test_validate_signal_on_good_trend():
    closes = _wavy_uptrend()
    sig = Signal(symbol="T", direction="LONG", entry=190.0, sl=180.0,
                 tp1=210.0, tp2=230.0, reason="golden_cross", timeframe="4h", ts=1)
    result = validate_signal(_mk_trend(closes), sig)
    # crosses occur on the dips -> positive exposure on an uptrend
    assert result.sharpe > 0
