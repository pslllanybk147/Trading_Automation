# -*- coding: utf-8 -*-
"""E3 sizing §6 — fixed fractional 0.5% risk; ห้าม round up เด็ดขาด (test_no_lot_round_up)

lots = (equity × risk_pct) / (stop_distance × contract_size)
จากนั้น floor เข้าหา lot_step; ถ้า < min_lot → SKIP TRADE
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .config import E3Config


@dataclass(frozen=True)
class SizingResult:
    lots: float
    skipped: bool
    reason: str | None


def compute_lots(equity: float, stop_distance: float, cfg: E3Config, risk_scale: float = 1.0) -> SizingResult:
    inst = cfg.instrument
    if stop_distance <= 0:
        return SizingResult(0.0, True, "stop_distance<=0")
    risk_dollars = equity * cfg.risk.risk_per_trade * risk_scale
    raw_lots = risk_dollars / (stop_distance * inst.contract_size)
    # floor เข้าหา lot_step เท่านั้น
    lots = math.floor(raw_lots / inst.lot_step) * inst.lot_step
    if lots < inst.min_lot:
        return SizingResult(0.0, True, "below_min_lot")
    if lots > inst.max_lot:
        lots = inst.max_lot
    return SizingResult(round(lots, 4), False, None)
