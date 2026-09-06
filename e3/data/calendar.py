# -*- coding: utf-8 -*-
"""E3 FX calendar — FX week, daily break, holidays, gap classification.

Invariant ที่ test ได้: สัปดาห์ปกติ = Sun 22:00 UTC → Fri 22:00 UTC
ปิด daily break 23:00-22:00 ต่อวัน (ประมาณ CME/OTC gold — โบรกเกอร์จริง
อาจต่าง 1-2 ชม. ให้ปรับ MarketHours ตาม broker ก่อนใช้ DQ011)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc

# FX/gold week (UTC): เปิดอาทิตย์ 22:00 → ปิดศุกร์ 22:00
WEEK_OPEN_DOW = 6        # Sunday
WEEK_OPEN_UTC = (22, 0)
WEEK_CLOSE_DOW = 4       # Friday
WEEK_CLOSE_UTC = (22, 0)
# daily break 21:59-22:00... ใช้ gap สั้น ๆ ก่อนปิดวันใหม่ของ NY 17:00 ET = 22:00 UTC (winter)
DAILY_BREAK_MIN = 60     # นาที — ช่องว่างปกติระหว่างวัน (17:00 ET close → 18:00 ET open ประมาณ)


@dataclass(frozen=True)
class Holiday:
    d: date
    name: str
    early_close_utc: tuple[int, int] | None = None   # None = ปิดทั้งวัน


def default_holidays(years: range | None = None) -> dict[date, Holiday]:
    """Christmas + New Year + Good Friday (ประมาณ — เจอข้อมูลจริงแล้วปรับ)
    Good Friday คำนวณจาก Easter (algorithm ของ Gauss/Meeus)"""
    hol: dict[date, Holiday] = {}
    if years is None:
        years = range(2015, 2031)
    for y in years:
        hol[date(y, 12, 25)] = Holiday(date(y, 12, 25), "Christmas")
        hol[date(y, 12, 24)] = Holiday(date(y, 12, 24), "Christmas Eve", early_close_utc=(19, 0))
        hol[date(y, 1, 1)] = Holiday(date(y, 1, 1), "New Year")
        gf = _easter(y) - timedelta(days=2)
        hol[gf] = Holiday(gf, "Good Friday")
    return hol


def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


class FXCalendar:
    def __init__(self, holidays: dict[date, Holiday] | None = None):
        self.holidays = holidays if holidays is not None else default_holidays()

    # ---- open/closed ----

    def is_open(self, ts: int) -> bool:
        dt = datetime.fromtimestamp(ts, tz=UTC)
        h = self.holidays.get(dt.date())
        if h is not None and h.early_close_utc is None:
            return False
        dow, hh, mm = dt.weekday(), dt.hour, dt.minute
        if dow == WEEK_OPEN_DOW:      # Sunday
            return (hh, mm) >= WEEK_OPEN_UTC
        if dow == WEEK_CLOSE_DOW:     # Friday
            if h is not None and h.early_close_utc is not None:
                return (hh, mm) < h.early_close_utc
            return (hh, mm) < WEEK_CLOSE_UTC
        if dow == 5:                  # Saturday
            return False
        if h is not None and h.early_close_utc is not None:
            return (hh, mm) < h.early_close_utc
        return True

    def open_minutes(self, d: date) -> int:
        """จำนวนนาทีตลาดเปิดของวัน d (UTC) — ใช้เป็นเกณฑ์แยก outage จาก gap ปกติ"""
        start = int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())
        return sum(1 for m in range(24 * 60) if self.is_open(start + m * 60))

    # ---- gap classification (DQ012) ----

    def classify_gap(self, prev_ts: int, ts: int) -> str:
        """จำแนกช่องว่างระหว่างแท่ง M15:
        ok / daily_break / weekend / holiday / outage"""
        if prev_ts is None:
            return "ok"
        gap_min = (ts - prev_ts) / 60.0
        if gap_min <= 15:
            return "ok"
        pdt = datetime.fromtimestamp(prev_ts, tz=UTC)
        dt = datetime.fromtimestamp(ts, tz=UTC)
        # วันหยุด: ตรวจทุกวันในช่วง gap (ครอบคลุม gap ข้ามหลายวัน เช่น พฤหัส→ศุกร์ Christmas)
        d = pdt.date()
        end_d = dt.date()
        while d <= end_d:
            h = self.holidays.get(d)
            if h is not None and h.early_close_utc is None:
                return "holiday"
            d += timedelta(days=1)
        # weekend: ศุกร์ (แท่งสุดท้ายเปิด ≥ 21:00 — bar 21:45 คือแท่งท้ายสัปดาห์)
        # → อาทิตย์/จันทร์ (แท่งแรกเปิด ≤ 23:59 อาทิตย์ หรือวันจันทร์)
        if pdt.weekday() == WEEK_CLOSE_DOW and pdt.hour >= 21 \
                and (dt.weekday() == WEEK_OPEN_DOW or dt.weekday() == 0):
            return "weekend"
        if dt.date() != pdt.date() and gap_min <= 24 * 60 + 120:
            return "daily_break"
        return "outage"
