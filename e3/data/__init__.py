# -*- coding: utf-8 -*-
"""E3 data layer — loader + quality gate + calendar (spec §2 + kit จากแชท aipass)

หลักการ: normalize → scan → cache → stream
  - ไฟล์ดิบไม่เคยเข้า backtest ตรง ๆ
  - ห้ามซ่อมข้อมูลเงียบ ๆ (ไม่ synthesize bar, ไม่ forward-fill ราคา)
    เจอปัญหาให้ "กันวันนั้นออก" แทน (exclude ระดับ *วัน* ไม่ใช่แท่ง)
  - timestamp ต้อง tz-aware แปลงเป็น UTC ที่ schema เดียว — ห้ามเดา source_tz
"""
from .schema import SourceSpec, SpecError, PRESETS, to_spread_price
from .calendar import FXCalendar, default_holidays
from .quality import QualityScanner, DQIssue, QualityReport, TradeabilityMap
from .loader import Loader, load_bars, spread_profile_from_bars

__all__ = [
    "SourceSpec", "SpecError", "PRESETS", "to_spread_price",
    "FXCalendar", "default_holidays",
    "QualityScanner", "DQIssue", "QualityReport", "TradeabilityMap",
    "Loader", "load_bars", "spread_profile_from_bars",
]
