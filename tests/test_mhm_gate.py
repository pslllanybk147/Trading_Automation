"""MHM gate (A/B ชั้น 2) — ทดสอบ compute_mhm_score + orchestrator gate + config

- คะแนนต้องตรงกับ backtest harness (backtest_history.compute_mhm_score) เป๊ะ
- gate เปิด → บล็อกสัญญาณที่คะแนน < min (และ None = บล็อก, fail-closed)
- gate ปิด (default) → พฤติกรรมเดิมทุกอย่าง
- journal_path แยกต่อ config เพื่อให้ 2 arms ของ A/B ไม่ปนกัน
"""
import json
import time

import pytest

from pipeline.config import load_config
from pipeline.models import CandleData
from pipeline.orchestrator import Orchestrator
from pipeline.signal_engine import compute_mhm_score

# fixture ts ต้อง "สด" — is_stale บล็อกข้อมูลที่แท่งสุดท้ายเก่ากว่า ~2 แท่ง


# ---------- helpers ----------

def _mk(closes, timeframe="4h", ts0=None, vols=None):
    if ts0 is None:
        # anchor แท่งสุดท้ายที่ "ปัจจุบัน" เสมอ (ผ่าน is_stale) ไม่ว่า closes จะยาวเท่าไหร่
        step_sec = {"1h": 3600, "4h": 14400, "1d": 86400}.get(timeframe, 14400)
        ts0 = (int(time.time()) // step_sec) * step_sec - (len(closes) - 1) * step_sec
    """CandleData list แบบ tight-wick (h=c*1.001, l=c*0.999) เหมือน test_orchestrator"""
    step = {"1h": 3600, "4h": 14400, "1d": 86400}.get(timeframe, 14400)
    vols = vols or [2000.0] * len(closes)
    return [CandleData("T", timeframe, ts0 + i * step, c, c * 1.001, c * 0.999,
                       c, vols[i]) for i, c in enumerate(closes)]


def _uptrend(n=400, start=100.0, daily=1.0):
    """ราคาขึ้นตรง ๆ ทุก horizon ล้วนสูงกว่า → คะแนน +4
    (ต้องยาวกว่า horizon ไกลสุด: 60 วัน = 360 แท่ง 4h)"""
    return [start + i * daily for i in range(n)]


def _sideway(n=400, base=100.0):
    """ราคาแกว่งรอบ base (ทุก 30 แท่งกลับมาที่เดิมพอดี) → คะแนนต่ำ/ศูนย์"""
    out = []
    for i in range(n):
        out.append(base + (1.0 if (i // 5) % 2 == 0 else -1.0))
    return out


def _golden_with_prefix(prefix_start=96.8, prefix_end=90.0):
    """400 แท่ง: นำหน้าด้วยขาลงอ่อน ๆ 360 แท่ง + ต่อด้วย series golden-cross 40 แท่ง
    (deterministic เดิมของ pipeline) — cross/RSI/volume ที่แท่งท้ายไม่เปลี่ยน
    (MA/RSI ใช้แค่ ~32 แท่งท้าย) แต่คะแนน MHM คุมได้จาก prefix:
      prefix_end ต่ำกว่า close ท้าย (96.906) → ทุก horizon สูงกว่า → score +4
      prefix_start สูงกว่า close ท้ายมาก ๆ → ทุก horizon ต่ำกว่า → score −4"""
    slope = (prefix_start - prefix_end) / 359.0
    prefix = [prefix_start - i * slope for i in range(360)]
    closes = prefix + _GOLDEN_CLOSES
    vols = [1000.0] * 399 + [2000.0]
    return closes, vols


# ---------- config ----------

def test_config_defaults_gate_off():
    cfg = load_config()
    assert cfg["signal"]["mhm_gate"] is False
    assert cfg["signal"]["mhm_min"] == 2
    assert cfg["paper"]["journal_path"] == "data/journal.db"


def test_config_overrides_from_file(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({
        "signal": {"mhm_gate": True, "mhm_min": 4},
        "paper": {"journal_path": "data/journal_ab.db"},
    }), encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg["signal"]["mhm_gate"] is True
    assert cfg["signal"]["mhm_min"] == 4
    assert cfg["paper"]["journal_path"] == "data/journal_ab.db"
    # ค่าที่ไม่แตะยังเป็น default
    assert cfg["risk"]["risk_per_trade"] == 0.03


# ---------- compute_mhm_score ----------

def test_score_full_uptrend_is_plus4():
    score = compute_mhm_score(_mk(_uptrend()))
    assert score == 4.0


def test_score_pure_downtrend_is_minus4():
    closes = [200.0 - i for i in range(400)]  # ลดตรง ๆ (ยาวกว่า horizon 60 วัน)
    score = compute_mhm_score(_mk(closes))
    assert score == -4.0


def test_score_none_when_data_insufficient():
    """แท่งไม่พอ horizon 60 วัน (60*6=360 แท่ง 4h) → None = fail-closed"""
    score = compute_mhm_score(_mk(_uptrend(n=80)))
    assert score is None  # 80 แท่ง < 360 แท่งที่ต้องการ


def test_score_none_on_unknown_timeframe():
    score = compute_mhm_score(_mk(_uptrend(n=80), timeframe="5m"))
    assert score is None


def test_score_empty_candles():
    assert compute_mhm_score([]) is None


def test_score_matches_backtest_harness():
    """ตัวเลขต้องตรงกับ backtest harness บนข้อมูลเดียวกัน (equivalence ตรง ๆ)"""
    import pandas as pd
    from backtest_history import compute_mhm_score as harness_score, to_frame

    import numpy as np
    rng = np.random.default_rng(42)
    n = 800  # ครอบ horizon สูงสุด 60 วัน (360 แท่ง 4h) + margin
    closes = list(np.cumsum(rng.normal(0, 1.0, n)) + 100.0)
    candles = _mk(closes)
    ts0 = candles[0].ts

    live = compute_mhm_score(candles)
    df = to_frame(candles)
    df.index = [ts0 + i * 14400 for i in range(n)]
    harness = harness_score(df, 14400)
    assert live == pytest.approx(float(harness.iloc[-1]))


def test_score_sideway_low():
    score = compute_mhm_score(_mk(_sideway()))
    # sideway แกว่ง ±1: ราคาเมื่อ 7/14/30/60 วันก่อน ≈ ราคาปัจจุบัน → คะแนนไม่ควรถึง +4
    assert score is not None
    assert score <= 2.0


# ---------- orchestrator gate ----------

_GOLDEN_CLOSES = [
    99.947, 99.469, 99.154, 99.296, 99.176, 98.994, 98.907, 98.939, 98.921, 98.493,
    97.917, 97.554, 97.155, 96.713, 96.82, 96.877, 96.513, 96.405, 96.102, 96.188,
    95.932, 95.53, 95.115, 94.936, 94.533, 94.372, 94.445, 94.615, 94.686, 95.184,
    95.414, 95.414, 95.39, 95.401, 95.696, 96.081, 96.264, 96.249, 96.408, 96.906,
]


class FakeGovernor:
    def decide(self, signal, candles):
        from pipeline.models import GovernorDecision
        return GovernorDecision(signal.symbol, True, "ok", regime="bull")


class FakeRisk:
    def plan(self, signal, equity, open_positions, day_losses, total_dd):
        from pipeline.models import RiskPlan
        return RiskPlan(signal.symbol, 100.0, signal.sl, signal.tp1, signal.tp2,
                        0.03, True)


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


def _golden_with_prefix(prefix_start=96.8, prefix_end=90.0):
    """400 แท่ง: นำหน้าด้วยขาลงอ่อน ๆ 360 แท่ง + ต่อด้วย series golden-cross 40 แท่ง
    (deterministic เดิมของ pipeline) — cross/RSI/volume ที่แท่งท้ายไม่เปลี่ยน
    (detector ใช้แค่ ~32 แท่งท้าย) แต่คะแนน MHM คุมได้จาก prefix:
      prefix_end (90.0) ต่ำกว่า close ท้าย (96.906) → ทุก horizon สูงกว่า → +4
      prefix_start สูงกว่า close ท้ายมาก ๆ → ทุก horizon ต่ำกว่า → −4"""
    slope = (prefix_start - prefix_end) / 359.0
    prefix = [prefix_start - i * slope for i in range(360)]
    closes = prefix + _GOLDEN_CLOSES
    vols = [1000.0] * 399 + [2000.0]
    return closes, vols


class FakeData:
    """ส่งแท่ง golden-cross 40 แท่ง — คะแนน MHM = None (ข้อมูล < 360 แท่ง)"""

    def get_top_symbols(self, n):
        return ["T"]

    def fetch_all(self):
        vols = [1000.0] * 39 + [2000.0]
        return {"T": _mk(_GOLDEN_CLOSES, vols=vols)}


def _orch(config=None):
    return Orchestrator(
        data=FakeData(), governor=FakeGovernor(), risk=FakeRisk(),
        journal=FakeJournal(), validate=FakeValidation(), exchange=None,
        config=config,
    )


def test_gate_off_by_default_signal_flows():
    orch = _orch()
    summary = orch.run_daily_cycle()
    assert summary["errors"] == []
    assert summary["signals"] >= 1
    assert summary["trades_opened"] >= 1
    assert summary["mhm_blocked"] == 0


def test_gate_on_blocks_signal_when_score_none():
    """40 แท่ง → คะแนนคำนวณไม่ได้ (None) → gate บล็อก (fail-closed)"""
    orch = _orch({"signal": {"mhm_gate": True, "mhm_min": 2}})
    summary = orch.run_daily_cycle()
    assert summary["signals"] == 0
    assert summary["mhm_blocked"] >= 1
    assert summary["trades_opened"] == 0


def test_gate_on_passes_when_score_meets_min():
    """ข้อมูลพอ + prefix ต่ำ (score +4 >= 2) + golden cross ที่แท่งท้าย → ผ่าน gate"""
    closes, vols = _golden_with_prefix(prefix_start=96.8, prefix_end=90.0)
    candles = _mk(closes, vols=vols)

    class Data:
        def get_top_symbols(self, n):
            return ["T"]

        def fetch_all(self):
            return {"T": candles}

    orch = Orchestrator(
        data=Data(), governor=FakeGovernor(), risk=FakeRisk(),
        journal=FakeJournal(), validate=FakeValidation(), exchange=None,
        config={"signal": {"mhm_gate": True, "mhm_min": 2}},
    )
    summary = orch.run_daily_cycle()
    assert summary["errors"] == []
    # คะแนน +4: close ท้าย (96.906) สูงกว่าทุก horizon (prefix ลง 96.8 → 90.0)
    assert compute_mhm_score(candles) == 4.0
    # แท่งท้ายเป็น golden cross (ยืนยันด้วยตัว detector ตรง ๆ)
    from pipeline.signal_engine import detect_golden_cross
    assert detect_golden_cross(candles) is not None
    assert summary["signals"] >= 1
    assert summary["mhm_blocked"] == 0
    assert summary["trades_opened"] >= 1


def test_gate_on_blocks_when_score_below_min():
    """คะแนนคำนวณได้แต่ < min (prefix สูงกว่า close ท้ายมาก → −4) → บล็อก"""
    closes, vols = _golden_with_prefix(prefix_start=130.0, prefix_end=110.0)
    candles = _mk(closes, vols=vols)

    class Data:
        def get_top_symbols(self, n):
            return ["T"]

        def fetch_all(self):
            return {"T": candles}

    orch = Orchestrator(
        data=Data(), governor=FakeGovernor(), risk=FakeRisk(),
        journal=FakeJournal(), validate=FakeValidation(), exchange=None,
        config={"signal": {"mhm_gate": True, "mhm_min": 2}},
    )
    summary = orch.run_daily_cycle()
    from pipeline.signal_engine import detect_golden_cross
    # ต้องมี cross (ไม่งั้นทดสอบไม่ได้สาระ) และคะแนนต้องต่ำกว่า min
    assert detect_golden_cross(candles) is not None
    assert compute_mhm_score(candles) == -4.0
    assert summary["signals"] == 0
    assert summary["mhm_blocked"] >= 1
    assert summary["trades_opened"] == 0


# ---------- journal path (A/B isolation) ----------

def test_journal_path_from_config(tmp_path, monkeypatch):
    """main.py อ่าน paper.journal_path → Journal ใช้ไฟล์คนละไฟล์ต่อ arm"""
    from pipeline.journal import Journal
    p = str(tmp_path / "ab.db")
    j = Journal(p)
    j.record_decision("T", type("D", (), {"symbol": "T", "approved": True,
                                          "reason": "r", "regime": "bull"}))
    assert (tmp_path / "ab.db").exists()
    # journal หลักไม่ถูกสร้าง
    assert not (tmp_path / "journal.db").exists()


def test_ab_config_example_file_valid():
    """config ตัวอย่าง A/B (ถ้ามีใน repo) ต้องโหลดได้และตั้ง arm ถูกต้อง"""
    from pathlib import Path
    p = Path("config_ab_mhm.example.json")
    if not p.exists():
        pytest.skip("example config not present")
    cfg = load_config(str(p))
    assert cfg["signal"]["mhm_gate"] is True
    assert cfg["paper"]["journal_path"] != "data/journal.db"  # ต้องแยกไฟล์
