# -*- coding: utf-8 -*-
"""E1 config — ทุกตัวเลขจาก spec (entry E1-E10, H_min, ladder, sizing bounds)

ค่า default = VIP0 Binance (spot 0.1% / perp 0.05% taker) — เปลี่ยนได้ตาม tier จริง
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class E1Config:
    # ---- capital ----
    equity: float = 10_000.0
    pool_pct: float = 0.30            # E1 pool = 30% ของพอร์ต (RA bound 15-50%)
    cash_buffer_pct: float = 0.25     # deploy ได้ ≤ 75% ของ pool (เงินสดค้าง ≥25%)
    exchange_cap_pct: float = 0.40    # เงินใน exchange รวม ≤ 40% ของ equity
    max_leverage: float = 2.0         # spec อนุญาต ≤3× — default 2× (กันหนาว)

    # ---- entry (E1-E10 subset ที่วัดจากข้อมูลได้) ----
    entry_f_min: float = 0.09         # f_ma7d ≥ 9%/ปี
    entry_stability_min: float = 0.80 # สัดส่วน funding บวกในหน้าต่าง 7 วัน
    entry_f_pred_min: float = 0.0     # f_pred (EWMA) > 0
    basis_z_max: float = 2.5          # ห้ามเข้าตอน basis สุดขั้ว
    basis_z_window_days: int = 30
    hold_multiple: float = 1.5        # expected hold ≥ 1.5 × H_min
    h_min_days: float = 7.3           # taker 4 ขา
    min_completed_episodes: int = 3   # median episode ต้องมีตัวอย่างพอ (fail-closed)

    # ---- exit ----
    exit_f_decay: float = 0.04        # f_ma7d < 4%/ปี → ออก (decay)
    basis_z_inversion: float = -2.0   # X2: mean24h basis ต่ำกว่า norm ผิดปกติ
                                      # (z < −2, เกณฑ์เดียวกับ E4 ที่ z > +2.5) —
                                      # "inversion" = ราคาหลุดโครงสร้าง ไม่ใช่แค่
                                      # สัญญาณอ่อน; บน BTC จริง mean24h < 0 อยู่ 73%
                                      # ของเวลา (structural discount) จึงตีความ
                                      # เป็นขั้วเปล่าไม่ได้
    hard_stop_pct: float = 0.015      # ขาดทุนรวม ≥ 1.5% ของ pool → ออกทันที

    # ---- costs ----
    fee_spot: float = 0.001
    fee_perp: float = 0.0005

    # ---- windows ----
    ma_window_days: int = 7           # f_ma7d = ค่าเฉลี่ย 21 events (8h)
    min_notional: float = 100.0

    @property
    def ma_window_events(self) -> int:
        return self.ma_window_days * 3   # 8h → 3/วัน
