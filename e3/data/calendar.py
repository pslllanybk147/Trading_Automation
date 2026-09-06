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

# ---- gold (histdata XAUUSD — วัดจากข้อมูลจริง 2018-01 + 2026-08, DST-free) ----
# daily break 17:00→18:00 UTC ทุกฤดู (หน้าหนาวแท่งสุดท้ายอาจเริ่ม 17:00 = เทรดถึง ~17:15)
# สัปดาห์: อาทิตย์ 18:00 → ศุกร์ ~17:00 UTC (weekend open-to-open = 49.25h)
GOLD_OPEN_DOW = 6                     # Sunday
GOLD_OPEN_UTC = (18, 0)
GOLD_CLOSE_DOW = 4                    # Friday
GOLD_CLOSE_UTC = (17, 15)             # รับแท่งที่เริ่ม ≤ 17:15 (หน้าหนาวเทรดถึง ~17:15)
GOLD_BREAK_START = (17, 15)           # ปิดกลางวัน
GOLD_BREAK_END = (18, 0)


@dataclass(frozen=True)
class Holiday:
    d: date
    name: str
    early_close_utc: tuple[int, int] | None = None   # None = ปิดทั้งวัน


def _nth_weekday(y: int, m: int, weekday: int, n: int) -> date:
    """นth weekday ของเดือน (weekday: 0=Mon) — n ติดลบ = นับจากท้าย"""
    if n > 0:
        d = date(y, m, 1)
        offset = (weekday - d.weekday()) % 7
        return d + timedelta(days=offset + 7 * (n - 1))
    # นับจากท้ายเดือน
    import calendar as _cal
    last = date(y, m, _cal.monthrange(y, m)[1])
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset + 7 * (-n - 1))


def default_holidays(years: range | None = None) -> dict[date, Holiday]:
    """วันหยุดตลาด — fixed-date + rule-based US holidays (เจอข้อมูลจริงแล้วปรับ)

    US Monday holidays (MLK/Presidents/Memorial/Labor/Columbus) + Juneteenth/
    Independence/Thanksgiving — ทองเปิดสั้น/พักยาว ถือเป็น full-day เพื่อ
    กัน false-outage (พรืดของ DQ012 ทั้งสัปดาห์นั้น)"""
    hol: dict[date, Holiday] = {}
    if years is None:
        years = range(2015, 2031)
    for y in years:
        hol[date(y, 12, 25)] = Holiday(date(y, 12, 25), "Christmas")
        hol[date(y, 12, 24)] = Holiday(date(y, 12, 24), "Christmas Eve", early_close_utc=(19, 0))
        hol[date(y, 1, 1)] = Holiday(date(y, 1, 1), "New Year")
        gf = _easter(y) - timedelta(days=2)
        hol[gf] = Holiday(gf, "Good Friday")
        # US rule-based
        hol[_nth_weekday(y, 1, 0, 3)] = Holiday(_nth_weekday(y, 1, 0, 3), "MLK Day")
        hol[_nth_weekday(y, 2, 0, 3)] = Holiday(_nth_weekday(y, 2, 0, 3), "Presidents Day")
        hol[_nth_weekday(y, 5, 0, -1)] = Holiday(_nth_weekday(y, 5, 0, -1), "Memorial Day")
        hol[_nth_weekday(y, 9, 0, 1)] = Holiday(_nth_weekday(y, 9, 0, 1), "Labor Day")
        hol[_nth_weekday(y, 10, 0, 2)] = Holiday(_nth_weekday(y, 10, 0, 2), "Columbus Day")
        hol[date(y, 6, 19)] = Holiday(date(y, 6, 19), "Juneteenth")
        hol[date(y, 7, 4)] = Holiday(date(y, 7, 4), "Independence Day")
        hol[_nth_weekday(y, 11, 3, 4)] = Holiday(_nth_weekday(y, 11, 3, 4), "Thanksgiving")
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
    """kind="fx" = majors (Sun 22:00 → Fri 22:00 UTC) | kind="gold" = XAUUSD histdata
    (Sun 18:00 → Fri ~17:15 UTC, break 17:15→18:00 UTC — DST-free จากข้อมูลจริง)"""

    def __init__(self, holidays: dict[date, Holiday] | None = None,
                 kind: str = "fx"):
        if kind not in ("fx", "gold"):
            raise ValueError(f"unknown calendar kind '{kind}'")
        self.kind = kind
        # weekend gap ปกติ (open-to-open): fx = 49h (Fri 21:45 → Sun 22:00),
        # gold = 49.25h (Fri ~16:45 → Sun 18:00) → เกินนี้ = วันหยุดต่อ (long weekend)
        self.max_weekend_hours = 49.0 if kind == "fx" else 52.0
        self.holidays = holidays if holidays is not None else default_holidays()

    # ---- open/closed ----

    def _gold_closed_intraday(self, hh: int, mm: int) -> bool:
        """ช่วงพักกลางวันของทอง 17:15–18:00 UTC"""
        return GOLD_BREAK_START <= (hh, mm) < GOLD_BREAK_END

    def is_open(self, ts: int) -> bool:
        dt = datetime.fromtimestamp(ts, tz=UTC)
        h = self.holidays.get(dt.date())
        if h is not None and h.early_close_utc is None:
            return False
        dow, hh, mm = dt.weekday(), dt.hour, dt.minute
        if self.kind == "gold":
            if dow == 5:                              # Saturday
                return False
            if dow == GOLD_OPEN_DOW:                  # Sunday
                return (hh, mm) >= GOLD_OPEN_UTC
            if dow == GOLD_CLOSE_DOW:                 # Friday
                ec = h.early_close_utc if h is not None else GOLD_CLOSE_UTC
                return (hh, mm) < ec
            if h is not None and h.early_close_utc is not None:
                return (hh, mm) < h.early_close_utc
            return not self._gold_closed_intraday(hh, mm)
        # ---- kind = "fx" (majors) ----
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
        if self.kind == "gold":
            # daily break: prev ในช่วงก่อนพัก (≤17:30) → next เปิดหลังพัก (18:00±45m), ≤ 3 ชม.
            if gap_min <= 180 and (pdt.hour, pdt.minute) <= (17, 30) \
                    and (dt.hour, dt.minute) >= (17, 45):
                return "daily_break"
            # weekend: ศุกร์ (แท่งสุดท้ายเริ่ม ~16:45-17:15) → อาทิตย์ ≥ 18:00, 40-52 ชม.
            if pdt.weekday() == GOLD_CLOSE_DOW and dt.weekday() == GOLD_OPEN_DOW \
                    and 40.0 <= gap_min / 60.0 <= 52.0:
                return "weekend"
            return "outage"
        # ---- kind = "fx" (majors) ----
        # weekend: ศุกร์ (แท่งสุดท้ายเปิด ≥ 21:00 — bar 21:45 คือแท่งท้ายสัปดาห์)
        # → อาทิตย์/จันทร์ (แท่งแรกเปิด ≤ 23:59 อาทิตย์ หรือวันจันทร์)
        if pdt.weekday() == WEEK_CLOSE_DOW and pdt.hour >= 21 \
                and (dt.weekday() == WEEK_OPEN_DOW or dt.weekday() == 0):
            return "weekend"
        if dt.date() != pdt.date() and gap_min <= 24 * 60 + 120:
            return "daily_break"
        return "outage"
