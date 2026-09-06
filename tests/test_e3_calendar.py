# -*- coding: utf-8 -*-
"""E3 calendar tests — สัปดาห์ FX, วันหยุด, จำแนกช่องว่าง"""
from __future__ import annotations

from datetime import date, datetime, timezone

from e3.data.calendar import FXCalendar, default_holidays

UTC = timezone.utc


def _ts(y, m, d, hh=0, mm=0):
    return int(datetime(y, m, d, hh, mm, tzinfo=UTC).timestamp())


def test_fx_week_open_close():
    cal = FXCalendar()
    assert cal.is_open(_ts(2026, 3, 8, 22, 0))       # อาทิตย์ 22:00 → เปิด
    assert not cal.is_open(_ts(2026, 3, 8, 21, 45))  # อาทิตย์ 21:45 → ยังปิด
    assert cal.is_open(_ts(2026, 3, 10, 12, 0))      # อังคารกลางวัน
    assert not cal.is_open(_ts(2026, 3, 6, 22, 0))   # ศุกร์ 22:00 → ปิด
    assert cal.is_open(_ts(2026, 3, 6, 21, 45))      # ศุกร์ 21:45 → เปิด
    assert not cal.is_open(_ts(2026, 3, 7, 12, 0))   # เสาร์


def test_holidays_closed():
    cal = FXCalendar()
    assert not cal.is_open(_ts(2026, 12, 25, 12, 0))   # Christmas (ศุกร์ 2026)
    assert not cal.is_open(_ts(2026, 1, 1, 12, 0))     # New Year (พฤหัส)
    # Good Friday 2026 = 3 เม.ย. (วันศุกร์)
    assert not cal.is_open(_ts(2026, 4, 3, 12, 0))


def test_early_close_christmas_eve():
    cal = FXCalendar()
    # 24 Dec 2026 = วันพฤหัส — early close 19:00 UTC
    assert cal.is_open(_ts(2026, 12, 24, 18, 0))
    assert not cal.is_open(_ts(2026, 12, 24, 19, 30))


def test_open_minutes_invariant():
    """วันธรรมดาปกติ = 24×60 นาที (OTC ไม่มีพักกลางวัน) — เสาร์/อาทิตย์ = 0/120"""
    cal = FXCalendar()
    assert cal.open_minutes(date(2026, 3, 10)) == 24 * 60   # อังคาร
    assert cal.open_minutes(date(2026, 3, 7)) == 0          # เสาร์
    assert cal.open_minutes(date(2026, 3, 8)) == 120        # อาทิตย์ 22:00-24:00
    assert cal.open_minutes(date(2026, 12, 25)) == 0        # Christmas


def test_classify_gap_types():
    cal = FXCalendar()
    assert cal.classify_gap(None, 1) == "ok"
    # ปกติ 15 นาที
    assert cal.classify_gap(_ts(2026, 3, 10, 12, 0), _ts(2026, 3, 10, 12, 15)) == "ok"
    # weekend: ศุกร์ 23:00 → อาทิตย์ 23:15
    assert cal.classify_gap(_ts(2026, 3, 6, 23, 0), _ts(2026, 3, 8, 23, 15)) == "weekend"
    # holiday: พฤหัสบดีก่อน Christmas → ศุกร์ (วันหยุด)
    assert cal.classify_gap(_ts(2025, 12, 24, 20, 0), _ts(2025, 12, 26, 0, 0)) == "holiday"
    # outage: กลางสัปดาห์หาย 6 ชม.
    assert cal.classify_gap(_ts(2026, 3, 10, 6, 0), _ts(2026, 3, 10, 12, 0)) == "outage"
