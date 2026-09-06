# -*- coding: utf-8 -*-
"""E3 data schema — SourceSpec + presets + spread point→price conversion.

source_tz ห้ามเดา (SpecError ถ้าไม่ระบุ) — MT5 มักเป็น EET (Europe/Helsinki),
Dukascopy เป็น UTC, generic CSV ต้องบอกเอง
"""
from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo


class SpecError(ValueError):
    """source spec ไม่ครบ/ไม่ถูกต้อง"""


@dataclass(frozen=True)
class SourceSpec:
    """นิยามแหล่งข้อมูลดิบ — ทุกฟิลด์ที่ loader ต้องรู้เพื่อ normalize"""
    path: str
    source_tz: str                      # บังคับ — ห้าม None (SpecError)
    time_column: str = "timestamp"
    time_format: str | None = None      # None = auto (ISO 8601 หรือ epoch)
    columns: tuple[str, ...] = ("timestamp", "open", "high", "low", "close", "volume")
    spread_column: str | None = None    # ชื่อคอลัมน์ spread (bid-ask) ถ้ามี
    spread_points: bool = False         # True = spread หน่วย point (ต้องคูณ point_value)
    point_value: float = 0.01           # XAUUSD ทั่วไป: 1 point = $0.01/oz
    tz_of_timestamps_is_broker_local: bool = False  # True = naive ts ใน broker tz (มี DST เจ็บ)

    def __post_init__(self):
        if not self.source_tz:
            raise SpecError("source_tz is mandatory — ห้ามเดา timezone (spec §2)")
        try:
            ZoneInfo(self.source_tz)
        except Exception as e:
            raise SpecError(f"unknown source_tz '{self.source_tz}': {e}") from e
        if self.spread_points and self.spread_column is None:
            raise SpecError("spread_points=True ต้องระบุ spread_column ด้วย")
        if not self.path:
            raise SpecError("path is required")

    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.source_tz)


PRESETS: dict[str, dict] = {
    "mt5": {
        "source_tz": "Europe/Helsinki",   # MT5 default = EET (UTC+2/+3)
        "time_column": "timestamp",
        "spread_points": True,
        "point_value": 0.01,
    },
    "dukascopy": {
        "source_tz": "UTC",
        "time_column": "timestamp",
        "spread_points": False,
    },
    "generic": {
        "source_tz": "UTC",
        "time_column": "timestamp",
    },
}


def to_spread_price(spread_raw: float, spec: SourceSpec) -> float:
    """แปลง spread จากหน่วย point → $/oz (ถ้า spec บอกว่าเป็น point)"""
    if spec.spread_points:
        return spread_raw * spec.point_value
    return spread_raw
