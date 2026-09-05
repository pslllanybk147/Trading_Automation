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
    # Equity = account value (cash spent buys coins of equal value), so only
    # the open fee is realized at entry — not the full notional.
    assert ex.equity == pytest.approx(10000.0 - 1000.0 * FEE_RATE)
    trade = ex.positions()["BTCUSDT"]
    ex.close_position(trade, price=110.0)
    assert ex.equity > 10000.0  # closed with profit


def test_restore_state_rebuilds_positions_and_equity(tmp_path):
    from pipeline.journal import Journal

    j = Journal(str(tmp_path / "j.db"))
    ex1 = PaperExchange(equity=50_000.0)
    plan = RiskPlan("BTCUSDT", 1000.0, 95.0, 110.0, 120.0, 0.03, True)
    j.record_trade(ex1.place_order(plan, price=100.0))

    # A scheduled run is a fresh process: a new exchange must end up with the
    # same open positions and equity as the one that opened the trade.
    ex2 = PaperExchange(equity=50_000.0)
    ex2.restore_state(j.open_trades(), j.closed_since(0))
    assert set(ex2.positions()) == {"BTCUSDT"}
    assert ex2.equity == pytest.approx(ex1.equity)

    # SL/TP management survives across processes too.
    closed = ex2.check_position("BTCUSDT", price=94.0)  # below SL 95
    assert closed is not None and closed.pnl() < 0
    assert "BTCUSDT" not in ex2.positions()
    assert ex2.equity == pytest.approx(50_000.0 + closed.pnl())


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


def _plan(atr=2.0):
    return RiskPlan("BTCUSDT", 1000.0, 95.0, 110.0, 120.0, 0.03, True, atr=atr)


def test_partial_tp1_keeps_position_open_with_reduced_size():
    ex = PaperExchange(equity=10000.0, partial_fraction=0.5, trail_atr=2.0)
    ex.place_order(_plan(atr=2.0), price=100.0)
    fill = ex.check_position("BTCUSDT", price=111.0, high=111.0, low=111.0)
    assert fill is not None
    # ปิดที่ TP1 (110) ไม่ใช่ราคาที่เช็ค (111)
    assert fill.exit == pytest.approx(110.0 * (1 - SLIPPAGE))
    assert fill.size_usdt == pytest.approx(500.0)  # ปิดครึ่ง
    # เหลืออีกครึ่ง ยังเปิดอยู่ และสลับไปโหมด trailing
    assert "BTCUSDT" in ex.positions()
    rem = ex.positions()["BTCUSDT"]
    assert rem.size_usdt == pytest.approx(500.0)
    assert rem.tp1_filled is True
    # SL ยกเป็น breakeven (entry * 1.001)
    assert rem.sl_price == pytest.approx(rem.entry * 1.001)


def test_partial_tp1_then_trailing_closes_remainder():
    ex = PaperExchange(equity=10000.0, partial_fraction=0.5, trail_atr=2.0)
    ex.place_order(_plan(atr=2.0), price=100.0)
    ex.check_position("BTCUSDT", price=111.0, high=111.0, low=111.0)  # partial TP1
    # ราคาพุ่งไป 115 แล้วย่อลงแตะ trailing stop (trail_hi - 2*ATR = 115 - 4 = 111)
    ex.check_position("BTCUSDT", price=113.0, high=115.0, low=113.0)
    closed = ex.check_position("BTCUSDT", price=110.0, high=110.0, low=110.0)
    assert closed is not None
    assert closed.size_usdt == pytest.approx(500.0)  # ปิดส่วนที่เหลือ
    assert "BTCUSDT" not in ex.positions()
    assert closed.exit == pytest.approx(111.0 * (1 - SLIPPAGE))


def test_partial_tp1_then_tp2_closes_remainder():
    ex = PaperExchange(equity=10000.0, partial_fraction=0.5, tp2_atr=3.0)
    ex.place_order(_plan(atr=2.0), price=100.0)
    ex.check_position("BTCUSDT", price=111.0, high=111.0, low=111.0)  # partial TP1
    rem = ex.positions()["BTCUSDT"]
    assert rem.tp2_price == pytest.approx(rem.entry + 3.0 * 2.0)  # entry + 3 ATR
    # ราคาทะลุ TP2
    closed = ex.check_position("BTCUSDT", price=rem.tp2_price + 0.5,
                               high=rem.tp2_price + 0.5, low=rem.tp2_price + 0.5)
    assert closed is not None
    assert closed.size_usdt == pytest.approx(500.0)
    assert "BTCUSDT" not in ex.positions()


def test_partial_tp1_equity_books_realized_partial_only():
    ex = PaperExchange(equity=10000.0, partial_fraction=0.5, trail_atr=2.0)
    plan = _plan(atr=2.0)
    ex.place_order(plan, price=100.0)
    open_fee = 1000.0 * FEE_RATE
    before = ex.equity
    ex.check_position("BTCUSDT", price=111.0, high=111.0, low=111.0)
    # ปิดครึ่งที่ TP1 (110) หัก fee: realized = 500 * (110*0.9995 / 100*1.0005 - 1)
    fill_price = 110.0 * (1 - SLIPPAGE)
    entry = 100.0 * (1 + SLIPPAGE)
    realized = 500.0 * (fill_price / entry - 1.0)
    close_fee = 500.0 * FEE_RATE
    assert ex.equity == pytest.approx(before + realized - close_fee)


def test_partial_state_restores_across_processes(tmp_path):
    from pipeline.journal import Journal

    j = Journal(str(tmp_path / "j.db"))
    ex1 = PaperExchange(equity=50_000.0, partial_fraction=0.5, trail_atr=2.0)
    ex1.place_order(_plan(atr=2.0), price=100.0)
    j.record_trade(ex1.positions()["BTCUSDT"])
    fill = ex1.check_position("BTCUSDT", price=111.0, high=112.0, low=111.0)
    j.record_partial_fill(fill, ex1.positions()["BTCUSDT"])

    ex2 = PaperExchange(equity=50_000.0, partial_fraction=0.5, trail_atr=2.0)
    ex2.restore_state(j.open_trades(), j.closed_since(0))
    rem = ex2.positions()["BTCUSDT"]
    assert rem.size_usdt == pytest.approx(500.0)
    assert rem.tp1_filled is True
    assert rem.trail_hi == pytest.approx(112.0)
    assert ex2.equity == pytest.approx(ex1.equity)

    # trailing ยังทำงานต่อข้าม process — trail_hi 112, ระยะ 2 ATR = 4 → stop ที่ 108
    # (SL จะ ratchet ขึ้นตอน check: max(breakeven, 112 - 2*2) = 108)
    closed = ex2.check_position("BTCUSDT", price=107.0, high=107.0, low=107.0)
    assert closed is not None
    assert "BTCUSDT" not in ex2.positions()
    assert closed.exit == pytest.approx(108.0 * (1 - SLIPPAGE))
