# -*- coding: utf-8 -*-
"""E3 cost model §7 — ทุก fill ต้องมี cost เสมอ (test_cost_always_applied)

  spread     — ครึ่งสเปรดต่อฝั่ง (เข้า-ออกคนละฝั่งของ bid/ask = เต็มสเปรดต่อ round trip)
  slippage   — market order เท่านั้น
  commission — % ของ notional ต่อฝั่ง
  stress_multiplier — G-5 ต้องผ่านที่ ×1.0 / ×1.5 / ×2.0
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import CostsCfg
from .types import Side


@dataclass(frozen=True)
class FillCost:
    half_spread: float      # $/oz
    slippage: float         # $/oz (market เท่านั้น)
    commission: float       # $/oz เทียบเท่า (คิดจาก % × ราคา)
    total: float            # $/oz ต่อฝั่ง

    @property
    def round_trip(self) -> float:
        return self.total * 2


class CostModel:
    def __init__(self, cfg: CostsCfg):
        self.cfg = cfg

    def side_cost(self, price: float, side: Side, is_market: bool, spread_usd: float | None = None) -> FillCost:
        """cost ต่อฝั่ง หน่วย $/oz — side บอกทิศที่ fill เสียเปรียบ
        (LONG entry จ่าย ask = price + half_spread; SHORT entry จ่าย bid = price - half_spread)
        commission แปลงเป็น $/oz เพื่อรวมกับ R ให้ง่าย"""
        m = self.cfg.stress_multiplier
        sp = (spread_usd if spread_usd is not None else self.cfg.spread_usd) * m
        slip = (self.cfg.slippage_usd * m) if is_market else 0.0
        comm = self.cfg.commission_pct * price * m
        total = sp / 2.0 + slip + comm
        return FillCost(half_spread=sp / 2.0, slippage=slip, commission=comm, total=total)

    def entry_price(self, raw: float, side: Side, is_market: bool, spread_usd: float | None = None) -> tuple[float, FillCost]:
        """ราคา fill จริงหลัง cost (ทิศทางเสียเปรียบเสมอ — adverse)"""
        c = self.side_cost(raw, side, is_market, spread_usd)
        if side is Side.LONG:
            return raw + c.total, c
        return raw - c.total, c

    def exit_price(self, raw: float, side: Side, is_market: bool, spread_usd: float | None = None) -> tuple[float, FillCost]:
        """ฝั่งตรงข้ามกับ entry — LONG ออกที่ bid (ลบ), SHORT ออกที่ ask (บวก)"""
        c = self.side_cost(raw, side, is_market, spread_usd)
        if side is Side.LONG:
            return raw - c.total, c
        return raw + c.total, c
