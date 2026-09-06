# -*- coding: utf-8 -*-
"""E3 synth — market builder + fixture seeding สำหรับ golden tests.

แนวคิด: สร้างแท่ง M15 ทีละช่วงด้วยสคริปต์ง่าย ๆ
  - flat(price)        แท่งเรียบ
  - move(from, to)     แท่งไต่/ไหลตรง
  - spike_up/down      แท่งหนาม (wick ยาว)
แต่ละเคสต้อง seed indicators ด้วย bars ก่อนหน้า (~400 bars) จึงจะ ARM ได้
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from e3.types import Bar

UTC = timezone.utc
BAR = 900


def _day_start_utc(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> int:
    return int(datetime(y, m, d, hh, mm, tzinfo=UTC).timestamp())


class Builder:
    """สร้าง M15 bars เรียงต่อกัน — เริ่มจากเวลาที่กำหนด"""

    def __init__(self, start_ts: int):
        self.ts = start_ts
        self.bars: list[Bar] = []
        self.price = 2000.0

    def _push(self, o: float, h: float, l: float, c: float, ts: int | None = None) -> "Builder":
        bar = Bar(ts if ts is not None else self.ts, o, h, l, c, 100.0, True).validate()
        self.bars.append(bar)
        self.ts += BAR
        self.price = c
        return self

    def flat(self, price: float, n: int, wick: float = 0.5) -> "Builder":
        for _ in range(n):
            self._push(price, price + wick, price - wick, price)
        return self

    def move(self, to: float, n: int = 1) -> "Builder":
        """ไต่/ไหลจากราคาปัจจุบันไป `to` ใน n แท่ง (o/h/l/c ถูกต้องเสมอ)"""
        o = self.price
        for i in range(1, n + 1):
            c = o + (to - o) * i / n
            p_prev = o + (to - o) * (i - 1) / n
            hi = max(c, p_prev) + 0.1
            lo = min(c, p_prev) - 0.1
            self._push(p_prev, hi, lo, c)
        return self

    def spike_up(self, wick_top: float, body: float | None = None) -> "Builder":
        """แท่งยาวขึ้นบนแล้วปิดกลับมา (wick บน)"""
        body = body if body is not None else self.price
        o = self.price
        self._push(o, wick_top, min(o, body) - 0.05, body)
        return self

    def spike_down(self, wick_bot: float, body: float | None = None) -> "Builder":
        body = body if body is not None else self.price
        o = self.price
        self._push(o, max(o, body) + 0.05, wick_bot, body)
        return self

    def jump_to(self, price: float) -> "Builder":
        self.price = price
        return self

    def at(self, y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> "Builder":
        """ขยับเวลา (สร้าง gap จริงใน timeline) — อนุญาตกระโดดไปหน้าได้
        และแจ้งเตือนถ้าชนแท่งเดิม (backward jump ห้ามเด็ดขาด จะทำ non-monotonic)"""
        target = _day_start_utc(y, m, d, hh, mm)
        assert target >= self.ts, f"backward jump {self.ts} -> {target} ห้ามทำ (non-monotonic)"
        self.ts = target
        return self

    def seed_until(self, end_ts: int, base: float = 2000.0, vol: float = 8.0) -> "Builder":
        """สร้าง bars วันละ 96 แท่ง (00:00-23:45 UTC) ข้าม weekend จนถึง end_ts พอดี
        กัน overshoot — ใช้แทน seed_days เมื่อต้องการจบวันที่ระบุ
        ราคา flat ที่ base; wick สลับเป็น *บล็อก 3 วัน* loud(TR=3)/quiet(TR=1)
        เพื่อให้ ATR(96) ค่อย ๆ วิ่งเต็มช่วง [1.0, 3.0] — buffer ของ rank จะได้
        กระจายค่าจริง และวันเทรด (ต่อท้าย quiet block) จะได้ rank ~กลาง ๆ"""
        day = 0
        while self.ts < end_ts:
            cur = datetime.fromtimestamp(self.ts, tz=UTC)
            if cur.weekday() >= 5:                       # Sat/Sun → ข้ามไปจันทร์
                self.ts += (7 - cur.weekday()) * 86400
                continue
            day_start = _day_start_utc(cur.year, cur.month, cur.day)
            day_end = day_start + 96 * BAR
            n = 96 if day_end <= end_ts else (end_ts - day_start) // BAR
            wick = 1.5 if (day // 3) % 2 == 0 else 0.5   # บล็อก 3 วัน: loud/quiet สลับ
            for i in range(n):
                self._push(base, base + wick, base - wick, base)
            day += 1
            if day > 400:
                raise RuntimeError("seed_until run away — ตรวจ end_ts")
        return self

    def seed_days(self, days: int, base: float = 2000.0, vol: float = 8.0) -> "Builder":
        """สร้าง bars ต่อเนื่องหลายวัน — flat + wick บล็อก 3 วัน loud/quiet เหมือน seed_until"""
        for day in range(days):
            cur = datetime.fromtimestamp(self.ts, tz=UTC)
            if cur.weekday() >= 5:      # ข้าม Sat/Sun ไปจันทร์
                self.ts += (7 - cur.weekday()) * 86400
            wick = 1.5 if (day // 3) % 2 == 0 else 0.5
            for i in range(96):
                self._push(base, base + wick, base - wick, base)
        return self


def typical_day_builder(y: int = 2026, m: int = 3, d: int = 3) -> Builder:
    """วันอังคารปกติ (ไม่มี DST transition) — เริ่ม seed มาก่อน 30 วัน"""
    b = Builder(_day_start_utc(y, m, d) - 30 * 86400)
    b.seed_days(28)
    b.at(y, m, d - 1, 0, 0)      # วันก่อนหน้า — ใช้เป็น asian reference ของ "วันเทรด"
    return b
