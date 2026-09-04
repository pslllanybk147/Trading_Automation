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
