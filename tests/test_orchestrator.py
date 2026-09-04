import pytest
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
    """Tight-wick candles: h = c*1.001, l = c*0.999 so prior-bar highs stay
    near close (a wide 1% wick would defeat the breakout condition)."""
    vols = vols or [2000.0] * len(closes)
    return [CandleData("T", "4h", 1700000000 + i * 14400, c, c * 1.001, c * 0.999, c, vols[i])
            for i, c in enumerate(closes)]


def test_run_daily_cycle_end_to_end():
    # turtle breakout: 29 flat bars at 10.0, last close 10.05 breaks the prior
    # 20-bar high (max 10.01). 30 bars is too few for golden cross (needs 32),
    # so exactly one turtle signal fires and flows through the whole pipeline.
    closes = [10.0] * 29 + [10.05]
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
    assert summary["trades_opened"] >= 1


def _turtle_data():
    """29 flat bars then a breakout — fires exactly one turtle signal."""
    closes = [10.0] * 29 + [10.05]
    vols = [1000.0] * 29 + [2000.0]

    class FakeData:
        def get_top_symbols(self, n):
            return ["T"]

        def fetch_all(self):
            return {"T": _mk(closes, vols)}

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
        data=_turtle_data(), governor=FakeGovernor(), risk=FakeRisk(),
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
        data=_turtle_data(), governor=FakeGovernor(), risk=FakeRisk(),
        journal=j, validate=FakeValidation(), exchange=None,
    )
    summary = orch.run_daily_cycle()
    assert summary["trades_opened"] == 0  # signal fired but symbol held
    assert len(j.open_trades()) == 1


def test_kill_switch_blocks_daily_cycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "STOP").touch()

    orch = Orchestrator(
        data=_turtle_data(), governor=FakeGovernor(), risk=FakeRisk(),
        journal=FakeJournal(), validate=FakeValidation(), exchange=None,
    )
    summary = orch.run_daily_cycle()
    assert summary["blocked_by"] == "kill_switch"
    assert summary["trades_opened"] == 0
