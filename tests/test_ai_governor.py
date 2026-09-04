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
