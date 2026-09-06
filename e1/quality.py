# -*- coding: utf-8 -*-
"""E1 quality scanner — ตรวจความสะอาดของ funding + klines (สไตล์เดียวกับ E3)

หลักการเดียวกับ E3: **ไม่ซ่อมข้อมูลเงียบ ๆ** — ขาด = ขาดจริง แจ้งไว้ใน report
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .data_schema import E1DataError, FundingEvent, Kline, funding_intervals_ms

H8 = 8 * 3600 * 1000
H4 = 4 * 3600 * 1000


@dataclass
class DQIssue:
    code: str
    at_ms: int
    detail: str


@dataclass
class E1QualityReport:
    symbol: str = ""
    n_funding: int = 0
    n_spot: int = 0
    n_perp: int = 0
    first_ms: int | None = None
    last_ms: int | None = None
    issues: list = field(default_factory=list)

    def add(self, code: str, at_ms: int, detail: str) -> None:
        self.issues.append(DQIssue(code, at_ms, detail))

    def by_code(self) -> dict[str, int]:
        c: Counter = Counter()
        for i in self.issues:
            c[i.code] += 1
        return dict(c)

    def intervals(self, events: list[FundingEvent]) -> dict[int, int]:
        return funding_intervals_ms(events)

    def ok_for_backtest(self, max_issues: int = 50) -> bool:
        """คร่าว ๆ: ปัญหาเยอะจนใช้ไม่ได้ = False (เกณฑ์ตายากกว่านี้ที่ engine gate)"""
        return len(self.issues) <= max_issues


def scan_funding(symbol: str, events: list[FundingEvent]) -> E1QualityReport:
    rep = E1QualityReport(symbol=symbol, n_funding=len(events))
    if not events:
        rep.add("E1D_EMPTY_FUNDING", 0, "ไม่มีข้อมูล funding")
        return rep
    rep.first_ms, rep.last_ms = events[0].funding_time_ms, events[-1].funding_time_ms
    ivs = rep.intervals(events)
    rep.add("E1D_INFO_INTERVALS", 0,
            ", ".join(f"{k/3600000:g}h×{v}" for k, v in sorted(ivs.items())))
    # ช่องว่างมากกว่า 3× interval ปกติ = หายจริง (ปกติคือ 8h; รับ 4h ด้วย)
    base = min(ivs) if ivs else H8
    for a, b in zip(events, events[1:]):
        gap = b.funding_time_ms - a.funding_time_ms
        if gap > 3 * base:
            rep.add("E1D_FUNDING_GAP", b.funding_time_ms,
                    f"ห่าง {gap/3600000:g}h (>3×{base/3600000:g}h)")
    # rate สุดขั้ว (±0.75% = cap เก่าของ Binance) — ให้ผ่านแต่ mark ไว้
    for e in events:
        if abs(e.rate) >= 0.0075:
            rep.add("E1D_RATE_EXTREME", e.funding_time_ms, f"rate={e.rate:.6f}")
    return rep


def scan_klines(symbol: str, klines: list[Kline], label: str,
                interval_ms: int) -> E1QualityReport:
    rep = E1QualityReport(symbol=symbol, n_spot=len(klines) if label == "spot" else 0,
                          n_perp=len(klines) if label == "perp" else 0)
    if not klines:
        rep.add(f"E1D_EMPTY_{label.upper()}", 0, "ไม่มีข้อมูล kline")
        return rep
    rep.first_ms, rep.last_ms = klines[0].open_time_ms, klines[-1].open_time_ms
    prev = None
    for k in klines:
        if prev is not None:
            gap = k.open_time_ms - prev
            if gap == 0:
                rep.add(f"E1D_DUP_{label.upper()}", k.open_time_ms, "openTime ซ้ำ")
            elif gap < 0:
                rep.add(f"E1D_NONMONO_{label.upper()}", k.open_time_ms, "openTime ย้อนหลัง")
            elif gap > interval_ms and gap % interval_ms == 0:
                # ปกติ spot crypto ไม่มีวันปิด — เว้นแต่เหรียญเพิ่ง listing
                rep.add(f"E1D_KLINE_GAP_{label.upper()}", k.open_time_ms,
                        f"หาย {gap // interval_ms - 1} แท่ง")
        prev = k.open_time_ms
    return rep


def scan_all(symbol: str, funding: list[FundingEvent],
             spot: list[Kline], perp: list[Kline],
             kline_interval_ms: int) -> list[E1QualityReport]:
    out = [scan_funding(symbol, funding),
           scan_klines(symbol, spot, "spot", kline_interval_ms),
           scan_klines(symbol, perp, "perp", kline_interval_ms)]
    # ตรวจครอบคลุม: funding เริ่มหลัง spot มากไหม (เหรียญที่ futures เปิดช้า — เป็นข้อเท็จจริง
    # ของ listing ไม่ใช่ข้อมูลเสีย → INFO) — engine ต้องเริ่ม sim ที่ futures open เสมอ
    if funding and spot and funding[0].funding_time_ms - spot[0].open_time_ms > 90 * 86400 * 1000:
        out[0].add("E1D_INFO_LATE_FUTURES", funding[0].funding_time_ms,
                   "futures เปิดช้ากว่า spot >90 วัน — sim เริ่มที่ futures open")
    return out
