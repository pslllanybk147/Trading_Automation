# -*- coding: utf-8 -*-
"""E3 quality tests — DQ codes บน fixture ที่ควบคุมได้"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from e3.data.calendar import FXCalendar
from e3.data.quality import QualityScanner
from e3.data.schema import SourceSpec

from tests.e3_data_synth import clean_week, rows_with_bad_bar, rows_with_outage, write_csv

UTC = timezone.utc


def _spec(path, tz="UTC", spread_column="spread"):
    return SourceSpec(path=path, source_tz=tz, spread_column=spread_column)


def test_clean_week_passes(tmp_path):
    p = write_csv(tmp_path / "clean.csv", clean_week(2026, 3, 8))
    bars, _ = _load(p, _spec(str(p)))
    rep = QualityScanner(_spec(str(p))).scan(bars)
    # อนุญาต minor issues — แต่ห้ามมี outage/out-of-range
    codes = rep.by_code()
    assert "DQ005_high_lt_low" not in codes
    assert "DQ006_close_out_of_range" not in codes
    assert "DQ012_outage_gap" not in codes
    assert "DQ004_duplicate_ts" not in codes
    assert rep.spread_samples > 0
    assert abs(rep.spread_p50 - 0.30) < 1e-9


def test_outage_detected(tmp_path):
    rows = rows_with_outage(2026, 3, 8, out_h=12, n_missing=8)   # หาย 2 ชม. วันจันทร์
    p = write_csv(tmp_path / "outage.csv", rows)
    bars, _ = _load(p, _spec(str(p)))
    rep = QualityScanner(_spec(str(p))).scan(bars)
    assert "DQ012_outage_gap" in rep.by_code()
    # วันที่เกิด outage ต้องถูก exclude
    assert date(2026, 3, 9) in rep.excluded_days


def test_bad_bar_detected_and_day_excluded(tmp_path):
    rows = rows_with_bad_bar(2026, 3, 8)
    p = write_csv(tmp_path / "bad.csv", rows)
    bars, _ = _load(p, _spec(str(p)))
    rep = QualityScanner(_spec(str(p))).scan(bars)
    assert "DQ005_high_lt_low" in rep.by_code()
    assert date(2026, 3, 9) in rep.excluded_days


def test_no_silent_repair(tmp_path):
    """ห้าม fill/smooth — bar ที่หายต้องหายจริงใน output"""
    rows = rows_with_outage(2026, 3, 8, out_h=12, n_missing=8)
    p = write_csv(tmp_path / "nr.csv", rows)
    bars, _ = _load(p, _spec(str(p)))
    ts_set = {b.ts for b in bars}
    out_start = int(datetime(2026, 3, 9, 12, 0, tzinfo=UTC).timestamp())
    # ไม่มี bar ใดถูกสร้างเติมในช่วง outage
    n_missing_slot = sum(1 for i in range(8) if out_start + i * 900 in ts_set)
    assert n_missing_slot == 0


def _load(p, spec):
    from e3.data.loader import Loader
    loader = Loader(cache_path=None)
    bars = loader.normalize(spec)
    return bars, None


def test_report_ok_gate(tmp_path):
    # 4 สัปดาห์ต่อเนื่อง (2/8, 2/15, 2/22, 3/1) + สัปดาห์ outage (3/8)
    rows = clean_week(2026, 2, 8) + clean_week(2026, 2, 15) + clean_week(2026, 2, 22)
    rows += clean_week(2026, 3, 1)
    rows += rows_with_outage(2026, 3, 8, out_h=12, n_missing=8)
    p = write_csv(tmp_path / "gate.csv", rows)
    bars, _ = _load(p, _spec(str(p)))
    rep = QualityScanner(_spec(str(p))).scan(bars)
    assert len(rep.excluded_days) == 1
    # 1 วัน จาก ~21 วัน span ≈ 5% — ไม่ผ่าน gate เข้ม แต่ผ่าน gate 8%
    assert rep.ok_for_backtest(max_excluded_pct=2.0) is False
    assert rep.ok_for_backtest(max_excluded_pct=8.0) is True
