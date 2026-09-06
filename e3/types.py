# -*- coding: utf-8 -*-
"""E3 types — Bar, Side, Phase, exceptions. ทุกแท่งต้อง validate ก่อนใช้ (closed bar only)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class BarError(ValueError):
    """แท่งเทียนไม่ถูกต้อง (OHLC พัง / closed=False / ts ซ้ำ)"""


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class Phase(str, Enum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    SWEPT = "SWEPT"
    CONFIRMED = "CONFIRMED"
    IN_POSITION = "IN_POSITION"


@dataclass(frozen=True)
class Bar:
    """แท่งเทียน M15 — timestamp เป็น epoch seconds UTC, ห้าม partial bar"""
    ts: int          # epoch seconds UTC (open time ของแท่ง)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    closed: bool = True

    def validate(self) -> "Bar":
        # closed bar only — partial bar = bug ใน pipeline ไม่ใช่ input ที่ยอมรับได้
        if not self.closed:
            raise BarError(f"partial bar at ts={self.ts} — closed bar only (spec §10.1)")
        for name in ("open", "high", "low", "close"):
            v = getattr(self, name)
            if not math.isfinite(v):
                raise BarError(f"{name} not finite at ts={self.ts}")
        if self.high < self.low:
            raise BarError(f"high < low at ts={self.ts}")
        if not (self.low <= self.open <= self.high):
            raise BarError(f"open outside [low,high] at ts={self.ts}")
        if not (self.low <= self.close <= self.high):
            raise BarError(f"close outside [low,high] at ts={self.ts}")
        return self

    @property
    def range_abs(self) -> float:
        return self.high - self.low


def check_monotonic(bars: list[Bar]) -> None:
    """DQ003/DQ004 — ts ต้องเพิ่มโดยเคร่งครัด ไม่มี duplicate"""
    prev = None
    for b in bars:
        if prev is not None and b.ts <= prev:
            raise BarError(f"non-monotonic/duplicate ts at {b.ts} (prev {prev})")
        prev = b.ts


class ContractError(ValueError):
    """คำสั่งไม่ถูกต้อง (SL/TP ผิดฝั่ง, size ≤ 0)"""
