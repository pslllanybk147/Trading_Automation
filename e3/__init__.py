# -*- coding: utf-8 -*-
"""E3 — XAUUSD Session Liquidity Sweep engine (spec v1.0, from aipass chat).

สถานะ: test-first implementation ของ spec §1-§12
Falsifiable claim (ต้องจำไว้เสมอ):
  walk-forward OOS PF < 1.15 หรือ Avg R ≤ 0 → ปฏิเสธสมมติฐาน ปิดโปรเจกต์

โมดูล:
  types       — Bar, Side, Phase, exceptions (validate ทุกแท่ง)
  config      — dataclass mirror ของ configs/e3.yaml
  clock       — session windows + DST (tz database จุดเดียวที่แตะ timezone)
  indicators  — ATR/EMA streaming + percentile rank + seeding
  costs       — cost model §7 (spread/slippage/commission + stress ×1/×1.5/×2)
  sizing      — §6 lots = floor เท่านั้น, < min_lot = SKIP (ห้าม round up)
  risk        — daily/weekly/monthly governor
  position    — partials 50/30/20 + BE + Chandelier trail + time-stop
  e3          — state machine §5
  backtest    — M15 driver + fill sim (adverse-first, no lookahead)
  metrics     — PF/avg R/ streaks + TradeRecord telemetry schema §12
"""
