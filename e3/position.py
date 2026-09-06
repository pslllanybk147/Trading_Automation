# -*- coding: utf-8 -*-
"""E3 position management §5.3 — partials, BE move, Chandelier trail, time-stop.

Exit ladder:
  TP1  @ 1.0R  → ปิด 50% + ย้าย SL → breakeven
  TP2  @ asian_mid → ปิด 30%
  Trail (Chandelier 2.5×atr_m15 จาก extreme) → ปิด 20% ที่เหลือ
  Time-stop: ครบ 8 M15 bars แล้ว MFE < 0.5R → ปิดทั้งหมด at market
  Flat-by: ปิดทั้งหมดบังคับ
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import E3Config
from .types import Bar, Side


@dataclass
class Fill:
    ts: int
    price: float
    size_frac: float     # สัดส่วนของ position เริ่มต้น (0..1)
    tag: str             # "entry" | "tp1" | "tp2" | "trail" | "stop" | "time_stop" | "flat_by"


@dataclass
class Position:
    side: Side
    entry_ts: int
    entry_price: float   # fill จริงหลัง cost
    initial_size: float  # lots
    sl_price: float      # fill จริง (price level)
    risk_per_oz: float   # |entry - SL| — หน่วย R ต่อ oz
    equity_at_entry: float
    atr_m15_at_entry: float
    asian_mid: float
    sl_initial_price: float = 0.0   # SL ตั้งต้น (ก่อน BE/trail) — telemetry §12
    remaining: float = 1.0
    realized_r: float = 0.0          # รวม R ที่ realize แล้ว (บวก partial exits)
    mfe_r: float = 0.0
    mae_r: float = 0.0
    extreme: float = 0.0             # favorable extreme สำหรับ trail
    sl_moved_be: bool = False
    tp2_done: bool = False
    fills: list[Fill] = field(default_factory=list)

    def __post_init__(self):
        self.extreme = self.entry_price
        if not self.sl_initial_price:
            self.sl_initial_price = self.sl_price

    def price_at_r(self, r: float) -> float:
        """ราคาที่ +rR (สำหรับ short TP1 จึงอยู่ต่ำกว่า entry)"""
        sign = 1.0 if self.side is Side.LONG else -1.0
        return self.entry_price + sign * r * self.risk_per_oz

    def r_multiple(self, price: float) -> float:
        sign = 1.0 if self.side is Side.LONG else -1.0
        return sign * (price - self.entry_price) / self.risk_per_oz

    def is_stop_hit(self, bar: Bar) -> bool:
        # adverse-first ตาม spec: intrabar ทั้ง SL และ TP ชนในแท่งเดียว → นับ SL ก่อน
        if self.side is Side.LONG:
            return bar.low <= self.sl_price
        return bar.high >= self.sl_price

    def is_tp1_hit(self, bar: Bar, tp1_r: float = 1.0) -> bool:
        """TP1 = +1R (ฝั่งกำไร) — ยิงครั้งเดียว; ห้ามยิงหลังขยับ SL เป็น BE แล้ว"""
        if self.sl_moved_be:
            return False
        target = self.price_at_r(tp1_r)
        if self.side is Side.LONG:
            return bar.high >= target
        return bar.low <= target

    def is_tp2_hit(self, bar: Bar) -> bool:
        # TP2 ต้องอยู่ฝั่งกำไรของ entry เท่านั้น (กัน mid อยู่ฝั่งขาดทุนสำหรับ shallow fill)
        if self.side is Side.LONG:
            return self.asian_mid > self.entry_price and bar.high >= self.asian_mid
        return self.asian_mid < self.entry_price and bar.low <= self.asian_mid


    def update_mfe_mae(self, bar: Bar) -> None:
        r = self.r_multiple(bar.high)
        r2 = self.r_multiple(bar.low)
        self.mfe_r = max(self.mfe_r, r, r2)
        self.mae_r = min(self.mae_r, r, r2)
        # favorable extreme ตามทิศทาง
        if self.side is Side.LONG:
            self.extreme = max(self.extreme, bar.high)
        else:
            self.extreme = min(self.extreme, bar.low)

    def trail_stop(self, atr_m15: float, trail_atr: float = 2.5) -> None:
        if self.side is Side.LONG:
            new_sl = self.extreme - trail_atr * atr_m15
            self.sl_price = max(self.sl_price, new_sl)  # trail ขึ้นอย่างเดียว
        else:
            new_sl = self.extreme + trail_atr * atr_m15
            self.sl_price = min(self.sl_price, new_sl)  # trail ลงอย่างเดียว

    def move_sl_be(self) -> None:
        self.sl_price = self.entry_price
        self.sl_moved_be = True

    def close_frac(self, frac: float, ts: int, price: float, tag: str) -> None:
        """realize frac ของ *ขนาดเริ่มต้น* (sequence-independent — รวมกัน ≤ 1.0)
        ถ้า frac ที่เหลือน้อยกว่าที่ขอ ปิดเท่าที่เหลือ"""
        frac = min(frac, self.remaining)
        if frac <= 1e-9:
            return
        r = self.r_multiple(price)
        self.realized_r += r * frac
        self.remaining = max(0.0, self.remaining - frac)
        self.fills.append(Fill(ts, price, frac, tag))

    def bars_held(self, ts: int, bar_secs: int = 900) -> int:
        return (ts - self.entry_ts) // bar_secs
