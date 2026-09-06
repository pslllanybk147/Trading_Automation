import pytest
from pipeline.models import CandleData, Signal, GovernorDecision, RiskPlan
from pipeline.orchestrator import Orchestrator

_NOW = int(__import__('time').time())
_T0 = (_NOW // 14400) * 14400 - 39 * 14400  # แท่งท้าย = ปัจจุบัน (ผ่าน is_stale)


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
    """Tight-wick candles: h = c*1.001, l = c*0.999 so prior-bar highs stay
    near close (a wide 1% wick would defeat the breakout condition)."""
    vols = vols or [2000.0] * len(closes)
    return [CandleData("T", "4h", _T0 + i * 14400, c, c * 1.001, c * 0.999, c, vols[i])
            for i, c in enumerate(closes)]


def test_run_daily_cycle_end_to_end():
    # golden cross: deterministic 40-bar down-then-recovery series (verified
    # against the detector) — MA7 crosses MA25 in the last 5 bars with RSI in
    # band and a volume spike, so exactly one golden-cross signal fires and
    # flows through the whole pipeline.
    orch = Orchestrator(
        data=_signal_data(),
        governor=FakeGovernor(),
        risk=FakeRisk(),
        journal=FakeJournal(),
        validate=FakeValidation(),
        exchange=None,  # paper used internally when None
    )
    summary = orch.run_daily_cycle()
    assert summary["errors"] == []
    assert summary["signals"] >= 1
    assert summary["trades_opened"] >= 1


_GOLDEN_CLOSES = [
    99.947, 99.469, 99.154, 99.296, 99.176, 98.994, 98.907, 98.939, 98.921, 98.493,
    97.917, 97.554, 97.155, 96.713, 96.82, 96.877, 96.513, 96.405, 96.102, 96.188,
    95.932, 95.53, 95.115, 94.936, 94.533, 94.372, 94.445, 94.615, 94.686, 95.184,
    95.414, 95.414, 95.39, 95.401, 95.696, 96.081, 96.264, 96.249, 96.408, 96.906,
]


def _signal_data():
    """40 candles that fire exactly one golden-cross signal (deterministic)."""
    vols = [1000.0] * 39 + [2000.0]

    class FakeData:
        def get_top_symbols(self, n):
            return ["T"]

        def fetch_all(self):
            return {"T": _mk(_GOLDEN_CLOSES, vols)}

    return FakeData()


def _open_trade(symbol="T", price=10.0, sl=9.0, tp1=11.0):
    from pipeline.execution import PaperExchange
    from pipeline.models import RiskPlan

    ex = PaperExchange(equity=50_000.0)
    plan = RiskPlan(symbol, 1000.0, sl, tp1, tp1 + 1.0, 0.03, True)
    return ex.place_order(plan, price=price)


def test_orchestrator_restores_open_position_from_journal(tmp_path):
    """A fresh Orchestrator (new process) sees positions opened by an earlier run."""
    from pipeline.journal import Journal

    j = Journal(str(tmp_path / "j.db"))
    trade = _open_trade()
    j.record_trade(trade)

    orch = Orchestrator(
        data=_signal_data(), governor=FakeGovernor(), risk=FakeRisk(),
        journal=j, validate=FakeValidation(), exchange=None,
    )
    assert set(orch.exchange.positions()) == {"T"}
    # open fee only: 1000 * 0.1%
    assert orch.exchange.equity == pytest.approx(50_000.0 - 1.0)


def test_daily_cycle_does_not_reopen_symbol_already_held(tmp_path):
    from pipeline.journal import Journal

    j = Journal(str(tmp_path / "j.db"))
    j.record_trade(_open_trade())

    orch = Orchestrator(
        data=_signal_data(), governor=FakeGovernor(), risk=FakeRisk(),
        journal=j, validate=FakeValidation(), exchange=None,
    )
    summary = orch.run_daily_cycle()
    assert summary["trades_opened"] == 0  # signal fired but symbol held
    assert len(j.open_trades()) == 1


def test_kill_switch_blocks_daily_cycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "STOP").touch()

    orch = Orchestrator(
        data=_signal_data(), governor=FakeGovernor(), risk=FakeRisk(),
        journal=FakeJournal(), validate=FakeValidation(), exchange=None,
    )
    summary = orch.run_daily_cycle()
    assert summary["blocked_by"] == "kill_switch"
    assert summary["trades_opened"] == 0


def test_check_open_positions_partial_tp_records_fill_and_keeps_remainder(tmp_path):
    """Position ที่ config partial TP (0.5) — ราคาขึ้นแตะ TP1 → บันทึก partial fill
    และเหลือ position เปิดอยู่ size ครึ่งหนึ่ง (ตาม config ที่ส่งเข้า orchestrator)."""
    from pipeline.journal import Journal
    from pipeline.execution import PaperExchange
    from pipeline.models import RiskPlan

    class HighData:
        def fetch_one(self, symbol, interval="4h"):
            return [CandleData(symbol, "4h", 1700000100, 100.0, 112.0, 99.0, 112.0, 2000.0)]

    j = Journal(str(tmp_path / "j.db"))
    ex = PaperExchange(equity=50_000.0, partial_fraction=0.5, trail_atr=2.0)
    plan = RiskPlan("T", 1000.0, 95.0, 110.0, 120.0, 0.03, True, atr=2.0)
    ex.place_order(plan, price=100.0)
    j.record_trade(ex.positions()["T"])

    orch = Orchestrator(data=HighData(), governor=FakeGovernor(), risk=FakeRisk(),
                        journal=j, validate=FakeValidation(), exchange=ex,
                        config={"tp": {"partial_fraction": 0.5, "trail_atr": 2.0, "tp2_atr": 0.0}})
    orch.check_open_positions()

    open_trades = j.open_trades()
    assert len(open_trades) == 1
    assert open_trades[0].size_usdt == pytest.approx(500.0)
    assert open_trades[0].tp1_filled is True
    closed = j.closed_since(0)
    assert len(closed) == 1
    assert closed[0].exit == pytest.approx(110.0 * (1 - 0.0005))
    # กำไรครึ่งเดียว (TP1 110) หัก fee เปิด/ปิด — equity ควร > 50k - fee เปิด
    assert ex.equity == pytest.approx(
        50_000.0 - 1.0 + 500.0 * (110.0 * 0.9995 / 100.05 - 1.0) - 500.0 * 0.001)


def test_check_open_positions_full_tp1_closes_position(tmp_path):
    """config ตั้ง partial_fraction=0 (ค่าเริ่มต้น) → แตะ TP1 ปิดเต็มไม้เหมือนเดิม."""
    from pipeline.journal import Journal
    from pipeline.execution import PaperExchange
    from pipeline.models import RiskPlan

    class HighData:
        def fetch_one(self, symbol, interval="4h"):
            return [CandleData(symbol, "4h", 1700000100, 100.0, 112.0, 99.0, 112.0, 2000.0)]

    j = Journal(str(tmp_path / "j.db"))
    ex = PaperExchange(equity=50_000.0)  # default: ปิดเต็มที่ TP1
    plan = RiskPlan("T", 1000.0, 95.0, 110.0, 120.0, 0.03, True, atr=2.0)
    ex.place_order(plan, price=100.0)
    j.record_trade(ex.positions()["T"])

    orch = Orchestrator(data=HighData(), governor=FakeGovernor(), risk=FakeRisk(),
                        journal=j, validate=FakeValidation(), exchange=ex)
    orch.check_open_positions()

    assert j.open_trades() == []
    closed = j.closed_since(0)
    assert len(closed) == 1
    assert closed[0].exit == pytest.approx(110.0 * (1 - 0.0005))
    assert closed[0].pnl() > 0
