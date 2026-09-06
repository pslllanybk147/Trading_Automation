# -*- coding: utf-8 -*-
"""E1 margin — ตาราง maintenance margin + คำนวณ liquidation/บันได margin

leverageBracket ของ Binance ต้องส่ง API key → เก็บตาราง static (notional bracket
จากหน้า leverage/margin tiers ที่ Binance เผยแพร่) + override จากไฟล์ JSON ได้

โมเดล liquidation ของชอร์ต perp (isolated, margin = เงินตั้งต้น M):
  margin_balance = M + (entry - mark) × qty          # unrealized ฝั่งชอร์ต
  mm = mmr × mark × qty + fee_close                  # maintenance + ค่าปิดโดยประมาณ
  liquidation เมื่อ margin_balance ≤ mm
  → ราคา liq ≈ (M + entry×qty) / (qty × (1 + mmr))   (แก้สมการตรง)

บันได margin 4 ชั้นตามสเปค (เห็นเป็น ratio margin_balance/mm):
  warn ≤2.2× → top-up เหลือ 1.8× → deleverage (ลดขนาด) เหลือ 1.5× → close ที่ 1.3×
"""
from __future__ import annotations

from dataclasses import dataclass


class MarginConfigError(ValueError):
    """margin tier config ไม่ถูกต้อง"""


@dataclass(frozen=True)
class MarginTier:
    """1 ชั้นของ notional bracket (USD) — notional_cap รวมชั้นก่อนหน้า"""
    notional_cap: float      # ขอบฟ้า notional ของชั้นนี้ (USD)
    mmr: float               # maintenance margin rate ของชั้นนี้ (เช่น 0.004)


# BTCUSDT (ตัวเลขใกล้เคียงตาราง Binance สาธารณะ — override ได้จาก JSON)
DEFAULT_TIERS: dict[str, tuple[MarginTier, ...]] = {
    "BTCUSDT": (
        MarginTier(50_000, 0.004),
        MarginTier(250_000, 0.005),
        MarginTier(1_000_000, 0.01),
        MarginTier(5_000_000, 0.02),
        MarginTier(20_000_000, 0.025),
        MarginTier(float("inf"), 0.05),
    ),
    "ETHUSDT": (
        MarginTier(25_000, 0.005),
        MarginTier(100_000, 0.006),
        MarginTier(500_000, 0.0125),
        MarginTier(2_000_000, 0.025),
        MarginTier(float("inf"), 0.05),
    ),
}
DEFAULT_MMR = (MarginTier(20_000, 0.005), MarginTier(100_000, 0.01),
               MarginTier(float("inf"), 0.025))   # alt ทั่วไป (fallback)


def mmr_for(symbol: str, notional: float,
            tiers: dict[str, tuple[MarginTier, ...]] | None = None) -> float:
    """mmr ตาม notional ปัจจุบัน (bracket สะสม) — ไม่รู้จักเหรียญ = ใช้ fallback แล้วเตือน"""
    table = (tiers or DEFAULT_TIERS).get(symbol, DEFAULT_MMR)
    for t in table:
        if notional <= t.notional_cap:
            return t.mmr
    return table[-1].mmr


def load_tiers(path: str) -> dict[str, tuple[MarginTier, ...]]:
    """โหลด override จาก JSON: {"BTCUSDT": [[50000, 0.004], ...], ...}"""
    import json
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    out: dict[str, tuple[MarginTier, ...]] = {}
    for sym, rows in raw.items():
        tiers = tuple(MarginTier(float(r[0]), float(r[1])) for r in rows)
        if not tiers or tiers[-1].notional_cap != float("inf"):
            raise MarginConfigError(f"{sym}: ชั้นสุดท้ายต้องมี notional_cap = inf")
        prev = 0.0
        for t in tiers:
            if t.notional_cap <= prev:
                raise MarginConfigError(f"{sym}: notional_cap ต้องเรียงเพิ่ม")
            if not (0 < t.mmr < 1):
                raise MarginConfigError(f"{sym}: mmr ผิดช่วง {t.mmr}")
            prev = t.notional_cap
        out[sym] = tiers
    return out


# ---------------- liquidation math (ชอร์ต perp, isolated) ----------------

def liq_price_short(entry: float, qty: float, margin: float,
                    symbol: str, tiers=None) -> float:
    """ราคาที่ตำแหน่งชอร์ตโดน liquidate (ประมาณ — ไม่รวม funding ที่จ่าย/ได้รับ)

    margin_balance(m) = margin + (entry - m)·qty
    mm(m)             = mmr(m)·m·qty  (fee_close ใส่เผื่อใน mmr แล้วแบบ conservative)
    ตั้งสมการ margin + entry·qty - m·qty = mmr·m·qty
    → m = (margin + entry·qty) / (qty·(1 + mmr))
    (mmr เป็นฟังก์ชันของ m — แก้ซ้ำ 2 รอบพอ: ครั้งแรกใช้ notional ที่ entry)
    """
    if qty <= 0 or entry <= 0 or margin <= 0:
        raise MarginConfigError("entry/qty/margin ต้อง > 0")
    r = mmr_for(symbol, entry * qty, tiers)
    m = (margin + entry * qty) / (qty * (1 + r))
    for _ in range(2):                      # iterate: notional ที่ราคา liq ใหม่
        r = mmr_for(symbol, m * qty, tiers)
        m = (margin + entry * qty) / (qty * (1 + r))
    return m


def margin_ratio_short(entry: float, mark: float, qty: float,
                       margin: float, symbol: str, tiers=None,
                       fee_close_rate: float = 0.0005) -> float:
    """margin_balance / maintenance ที่ราคา mark — ตัวเลขที่บันได 4 ชั้นใช้ตัดสิน
    (เช่น 3.0 = ปลอดภัย, 1.3 = ใกล้ close) — คิด mm รวมค่าปิดโดยประมาณ"""
    notional = mark * qty
    mm = mmr_for(symbol, notional, tiers) * notional + fee_close_rate * notional
    bal = margin + (entry - mark) * qty
    if mm <= 0:
        raise MarginConfigError("maintenance margin คำนวณได้ ≤ 0")
    return bal / mm


# ---------------- บันได margin 4 ชั้น (สเปค §RA/margin ladder) ----------------

@dataclass(frozen=True)
class LadderAction:
    level: str        # "ok" | "warn" | "topup" | "deleverage" | "close"
    ratio: float


@dataclass(frozen=True)
class MarginLadder:
    warn_at: float = 2.2      # ratio ≤ 2.2 → เตือน
    topup_to: float = 1.8     # จุดหมายหลังเติมเงิน
    deleverage_at: float = 1.5
    close_at: float = 1.3

    def __post_init__(self):
        if not (self.close_at < self.deleverage_at < self.topup_to < self.warn_at):
            raise MarginConfigError("ลำดับบันไดผิด: close < deleverage < topup < warn")

    def evaluate(self, ratio: float) -> LadderAction:
        if ratio > self.warn_at:
            return LadderAction("ok", ratio)
        if ratio > self.deleverage_at:
            return LadderAction("warn", ratio)
        if ratio > self.close_at:
            return LadderAction("deleverage", ratio)
        return LadderAction("close", ratio)

    def topup_amount(self, entry: float, mark: float, qty: float,
                     margin: float, symbol: str, tiers=None,
                     fee_close_rate: float = 0.0005) -> float:
        """เงินที่ต้องเติมให้ ratio กลับมาที่ topup_to (เติมฝั่ง perp margin เท่านั้น)
        mm ต้องใช้สูตรเดียวกับ margin_ratio_short (รวม fee ปิด) ไม่งั้นเติมแล้วไม่ถึงเป้า"""
        notional = mark * qty
        mm = mmr_for(symbol, notional, tiers) * notional + fee_close_rate * notional
        target_bal = self.topup_to * mm - (entry - mark) * qty
        need = target_bal - margin
        return max(0.0, need)
