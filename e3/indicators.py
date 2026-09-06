# -*- coding: utf-8 -*-
"""E3 indicators — ATR/EMA streaming + percentile rank + seeding.

Streaming (state ต่อแท่งที่ปิดแล้วเท่านั้น) — ไม่มีทาง lookahead เพราะ
update หนึ่งครั้งต่อหนึ่ง closed bar และ query ค่าได้หลัง update เท่านั้น
"""
from __future__ import annotations

import math
from collections import deque


class ATR:
    """Wilder ATR — seed ด้วย SMA ของ TR ช่วงแรก period แท่ง แล้วค่อย smooth"""

    def __init__(self, period: int):
        self.period = period
        self._prev_close: float | None = None
        self._trs: list[float] = []
        self._value: float | None = None

    @property
    def ready(self) -> bool:
        return self._value is not None

    @property
    def value(self) -> float:
        if self._value is None:
            raise ValueError("ATR not seeded yet")
        return self._value

    def update_raw(self, tr: float) -> float | None:
        """push ค่า TR ที่คำนวณเองภายนอก (เช่น D1 จากการรวม M15 เป็นวัน)"""
        if self._value is None:
            self._trs.append(tr)
            if len(self._trs) >= self.period:
                self._value = sum(self._trs) / self.period
                self._trs = []
        else:
            self._value = (self._value * (self.period - 1) + tr) / self.period
        return self._value

    def update(self, high: float, low: float, close: float) -> float | None:
        if self._prev_close is not None:
            tr = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        else:
            tr = high - low
        self._prev_close = close
        if self._value is None:
            self._trs.append(tr)
            if len(self._trs) >= self.period:
                self._value = sum(self._trs) / self.period
                self._trs = []
        else:
            self._value = (self._value * (self.period - 1) + tr) / self.period
        return self._value


class EMA:
    """EMA — seed ด้วย SMA ช่วงแรก period แท่ง"""

    def __init__(self, period: int):
        self.period = period
        self._k = 2.0 / (period + 1.0)
        self._seed: list[float] = []
        self._value: float | None = None

    @property
    def ready(self) -> bool:
        return self._value is not None

    @property
    def value(self) -> float:
        if self._value is None:
            raise ValueError("EMA not seeded yet")
        return self._value

    def update(self, x: float) -> float | None:
        if self._value is None:
            self._seed.append(x)
            if len(self._seed) >= self.period:
                self._value = sum(self._seed) / self.period
                self._seed = []
        else:
            self._value = (x - self._value) * self._k + self._value
        return self._value


class PercentileRank:
    """percentile rank ของค่าปัจจุบันในหน้าต่าง trailing (default 252 D1 bars)
    — คืน None จนกว่าจะมีข้อมูล seed ถึง `warmup` (สั้นกว่า window เพื่อใช้ได้จริง)
    fail-closed: ก่อน warmup คืน None เสมอ"""

    def __init__(self, window: int = 252, warmup: int | None = None):
        self.window = window
        self.warmup = min(warmup if warmup is not None else window, window)
        self._buf: deque[float] = deque(maxlen=window)

    def update(self, x: float) -> float | None:
        # rank คิดจาก buffer *ก่อน* push ค่าปัจจุบันเข้าไป — กัน self-compare lookahead
        if len(self._buf) < self.warmup:
            self._buf.append(x)
            if len(self._buf) < self.warmup:
                return None
        count_le = sum(1 for v in self._buf if v <= x)
        self._buf.append(x)
        return count_le / len(self._buf)


def true_range(high: float, low: float, prev_close: float | None) -> float:
    if prev_close is None:
        return high - low
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def safe_div(a: float, b: float, eps: float = 1e-12) -> float:
    return a / b if abs(b) > eps else math.inf
