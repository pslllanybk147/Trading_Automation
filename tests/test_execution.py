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
