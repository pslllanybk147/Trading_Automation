# -*- coding: utf-8 -*-
"""E3 config — dataclass mirror ของ configs/e3.yaml (ค่า default = spec §5-§8 ตัวต่อตัว)"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FiltersCfg:
    atr_rank_min: float = 0.35        # volatility floor
    atr_rank_max: float = 0.95        # volatility ceiling
    range_ratio_min: float = 0.25     # range sanity
    range_ratio_max: float = 1.20
    news_veto_minutes: int = 30       # ± window รอบ Tier-1 event
    spread_guard_atr: float = 0.35    # spread ≤ 0.35 × atr_m15
    sweep_min_atr: float = 0.15       # ความลึก sweep ต่ำสุด (× atr_m15)
    sweep_max_atr: float = 1.20       # ความลึก sweep สูงสุด
    use_h1_bias: bool = False         # confluence bonus — test แยก (spec §14)


@dataclass(frozen=True)
class TimingCfg:
    reclaim_bars: int = 3             # SWEPT → ต้อง reclaim ภายใน N M15 bars
    retest_bars: int = 4              # CONFIRMED → limit มีอายุ N M15 bars
    time_stop_bars: int = 8           # ถือครบ N bars แล้ว MFE < 0.5R → ปิด
    time_stop_mfe_r: float = 0.5
    trail_atr: float = 2.5            # Chandelier × atr_m15
    tp1_r: float = 1.0                # TP1 ที่ 1R ปิด 50%
    tp2_frac: float = 0.30            # ปิด 30% ที่ asian_mid
    trail_frac: float = 0.20          # ที่เหลือ 20% วิ่งตาม trail
    flat_by_local: str = "20:00"      # winter; summer คำนวณผ่าน clock (19:00)
    stop_atr: float = 0.30            # SL = sweep_extreme ± 0.30 × atr_m15


@dataclass(frozen=True)
class RiskCfg:
    risk_per_trade: float = 0.005     # 0.5% fixed fractional
    daily_loss_stop: float = 0.015    # -1.5% → หยุดวันนั้น
    weekly_loss_stop: float = 0.030   # -3.0% → หยุดสัปดาห์
    monthly_dd_halve: float = 0.06    # > -6% → ลด size ครึ่ง
    monthly_dd_kill: float = 0.12     # > -12% → kill switch
    max_trades_per_day: int = 2
    max_concurrent: int = 1           # ไม่มี pyramiding
    two_loss_pause: bool = True       # แพ้ 2 ไม้ติด → หยุดวันนั้น


@dataclass(frozen=True)
class CostsCfg:
    spread_usd: float = 0.30          # bid-ask spread ($/oz) — profile รายชั่วโมงเมื่อมีข้อมูลจริง
    slippage_usd: float = 0.05        # ต่อฝั่ง market order
    commission_pct: float = 0.00004   # 0.004% ของ notional ต่อฝั่ง (โบรก CFD ทั่วไป)
    stress_multiplier: float = 1.0    # G-5: ต้อง set 1.0 / 1.5 / 2.0 แล้วกำไรทั้ง 3


@dataclass(frozen=True)
class InstrumentCfg:
    contract_size: float = 100.0      # 1 lot = 100 oz (มาตรฐาน XAUUSD CFD)
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 50.0


@dataclass(frozen=True)
class E3Config:
    equity: float = 100_000.0
    filters: FiltersCfg = field(default_factory=FiltersCfg)
    timing: TimingCfg = field(default_factory=TimingCfg)
    risk: RiskCfg = field(default_factory=RiskCfg)
    costs: CostsCfg = field(default_factory=CostsCfg)
    instrument: InstrumentCfg = field(default_factory=InstrumentCfg)
    seed_bars: int = 400              # M15 bars ขั้นต่ำก่อน signal แรก (ATR/rank warm-up)

    @classmethod
    def from_yaml(cls, path: str) -> "E3Config":
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        sections = {}
        for key in ("filters", "timing", "risk", "costs", "instrument"):
            sub = raw.get(key) or {}
            sections[key] = sub
        return cls(
            equity=float(raw.get("equity", 100_000.0)),
            filters=FiltersCfg(**sections["filters"]),
            timing=TimingCfg(**sections["timing"]),
            risk=RiskCfg(**sections["risk"]),
            costs=CostsCfg(**sections["costs"]),
            instrument=InstrumentCfg(**sections["instrument"]),
            seed_bars=int(raw.get("seed_bars", 400)),
        )
