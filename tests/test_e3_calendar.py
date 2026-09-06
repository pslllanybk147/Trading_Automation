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


# ---- gold market hours (histdata XAUUSD — วัดจากข้อมูลจริง 2018-01 + 2026-08) ----


def test_gold_open_close():
    cal = FXCalendar(kind="gold")
    assert cal.is_open(_ts(2026, 8, 9, 18, 0))        # อาทิตย์ 18:00 → เปิด
    assert not cal.is_open(_ts(2026, 8, 9, 17, 45))   # อาทิตย์ 17:45 → ยังปิด
    assert cal.is_open(_ts(2026, 8, 11, 12, 0))       # อังคารกลางวัน
    assert not cal.is_open(_ts(2026, 8, 11, 17, 30))  # อังคารพักกลางวัน 17:15-18:00
    assert cal.is_open(_ts(2026, 8, 11, 18, 0))       # เปิดคืน 18:00
    assert not cal.is_open(_ts(2026, 8, 14, 17, 30))  # ศุกร์หลัง 17:15 → ปิด
    assert cal.is_open(_ts(2026, 8, 14, 17, 0))       # ศุกร์ 17:00 → ยังเปิด
    assert not cal.is_open(_ts(2026, 8, 15, 12, 0))   # เสาร์


def test_gold_classify_gap():
    cal = FXCalendar(kind="gold")
    # daily break: อังคาร 16:45 → 18:00 = 75 นาที (ฤดูหนาวแท่งสุดท้ายเริ่ม 16:45)
    assert cal.classify_gap(_ts(2026, 8, 11, 16, 45), _ts(2026, 8, 11, 18, 0)) == "daily_break"
    # หน้าร้อนแท่งสุดท้ายเริ่ม 17:00 → 18:00 = 60 นาที
    assert cal.classify_gap(_ts(2026, 1, 13, 17, 0), _ts(2026, 1, 13, 18, 0)) == "daily_break"
    # weekend: ศุกร์ 16:45 → อาทิตย์ 18:00 = 49.25 ชม.
    assert cal.classify_gap(_ts(2026, 8, 14, 16, 45), _ts(2026, 8, 16, 18, 0)) == "weekend"
    # US Monday holiday (MLK 15 Jan 2018): จันทร์ 12:00 → 17:00 = 5 ชม. — วันหยุด ไม่ใช่ outage
    assert cal.classify_gap(_ts(2018, 1, 15, 12, 0), _ts(2018, 1, 15, 17, 0)) == "holiday"
    # outage จริง: กลางสัปดาห์หาย 4 ชม. (วันธรรมดาปกติ)
    assert cal.classify_gap(_ts(2026, 8, 12, 6, 0), _ts(2026, 8, 12, 10, 0)) == "outage"


def test_gold_open_minutes_invariant():
    """วันธรรมดาปกติ = 24h − 45min พัก = 1395 นาที | อาทิตย์ = 6h | เสาร์ = 0"""
    cal = FXCalendar(kind="gold")
    assert cal.open_minutes(date(2026, 8, 11)) == (24 * 60 - 45)   # อังคาร
    assert cal.open_minutes(date(2026, 8, 15)) == 0                # เสาร์
    assert cal.open_minutes(date(2026, 8, 9)) == 6 * 60            # อาทิตย์ 18:00-24:00
    assert cal.open_minutes(date(2026, 8, 14)) == 17 * 60 + 15     # ศุกร์ 00:00-17:15


def test_default_holidays_us_rules():
    h = default_holidays(range(2018, 2027))
    assert date(2018, 1, 15) in h      # MLK (3rd Mon Jan)
    assert date(2018, 2, 19) in h      # Presidents (3rd Mon Feb)
    assert date(2026, 5, 25) in h      # Memorial (last Mon May)
    assert date(2026, 9, 7) in h       # Labor (1st Mon Sep)
    assert date(2026, 11, 26) in h     # Thanksgiving (4th Thu Nov)
    assert date(2026, 7, 3) not in h   # จันทร์/ศุกร์ bridge ไม่ใส่ (ไม่เคยเห็นในข้อมูล)
