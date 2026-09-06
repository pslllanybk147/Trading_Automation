# -*- coding: utf-8 -*-
"""E1 data schema — เวลาเป็น epoch **มิลลิวินาที** ตลอด (API ของ Binance เป็น ms)

- FundingEvent: 1 แถวของ fundingRate (เก็บทุก 8h หรือ 4h — ตรวจจาก delta จริง)
- Kline: แท่ง spot/perp (OHLCV) — ใช้หา basis + แทนที่ราคาตอน sim
- เวลาห้ามเดา timezone: Binance คืน UTC ms เสมอ → เก็บ ms ดิบไว้เป็น primary key
"""
from __future__ import annotations

from dataclasses import dataclass


class E1DataError(ValueError):
    """ข้อมูล E1 ไม่ถูกต้อง (ts ซ้ำ / rate ผิดปกติ / kline พัง)"""


@dataclass(frozen=True)
class FundingEvent:
    symbol: str
    funding_time_ms: int      # epoch ms — เวลา "เก็บ" funding (settlement)
    rate: float               # เช่น 0.0001 = 0.01% ต่อ interval (บวก = ชอร์ตได้รับ)
    mark_price: float | None = None

    def __post_init__(self):
        if self.funding_time_ms < 0:
            raise E1DataError(f"negative funding_time_ms {self.funding_time_ms}")
        if abs(self.rate) > 0.05:   # 5% ต่อ interval = ผิดปกติชัดเจน (cap จริง ~0.75%+)
            raise E1DataError(f"funding rate ผิดปกติ {self.rate} ที่ {self.funding_time_ms}")


@dataclass(frozen=True)
class Kline:
    symbol: str
    open_time_ms: int         # epoch ms — แท่งเปิด (closed bar เท่านั้นเมื่อ feed เข้า engine)
    open: float
    high: float
    low: float
    close: float
    volume: float
    market: str = "perp"      # "spot" | "perp"

    def __post_init__(self):
        if not (self.high >= self.low >= 0 and self.open > 0 and self.close > 0):
            raise E1DataError(f"kline พัง o={self.open} h={self.high} l={self.low} c={self.close}")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise E1DataError(f"o/c หลุดช่วง [l,h] ที่ {self.open_time_ms}")


def funding_intervals_ms(events: list[FundingEvent]) -> dict[int, int]:
    """นับช่วงเวลาเก็บ (ms → จำนวนครั้ง) — ใช้ตรวจว่าเหรียญนี้เป็น 8h หรือมีช่วง 4h"""
    deltas: dict[int, int] = {}
    for a, b in zip(events, events[1:]):
        d = b.funding_time_ms - a.funding_time_ms
        if d <= 0:
            raise E1DataError(f"fundingTime ซ้ำ/ย้อนหลังที่ {b.funding_time_ms}")
        deltas[d] = deltas.get(d, 0) + 1
    return deltas
