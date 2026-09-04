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
    halted, reason = engine.check_circuit_breakers(day_losses=0, total_dd=-0.20)
    assert halted is True
    assert "20" in reason


def test_no_breaker_normal():
    engine = RiskEngine()
    halted, _ = engine.check_circuit_breakers(day_losses=1, total_dd=0.05)
    assert halted is False
