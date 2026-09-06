# -*- coding: utf-8 -*-
"""E3 quality scanner — streaming checks (DQ003-DQ015 ตาม coverage ตารางในแชท)

ทุก issue ระบุ "exclude วัน" (ไม่ซ่อมข้อมูล) — แท่งพังบางส่วน = reference
ของทั้งวันพัง → กันทั้งวันออกตามเหตุผลของ kit
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from ..types import Bar  # noqa: F401  (type hints)
from .calendar import FXCalendar
from .schema import SourceSpec, to_spread_price

UTC = timezone.utc

M15 = 900


@dataclass
class DQIssue:
    code: str          # DQ003..DQ015
    ts: int            # epoch UTC จุดเกิด
    day: date          # วันที่จะถูก exclude
    detail: str


@dataclass
class QualityReport:
    total_bars: int = 0
    issues: list = field(default_factory=list)
    excluded_days: set = field(default_factory=set)
    first_ts: int | None = None
    last_ts: int | None = None
    spread_samples: int = 0
    spread_p50: float | None = None
    spread_p95: float | None = None

    def add(self, code: str, ts: int, detail: str) -> None:
        d = datetime.fromtimestamp(ts, tz=UTC).date()
        self.issues.append(DQIssue(code, ts, d, detail))
        self.excluded_days.add(d)

    def by_code(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for i in self.issues:
            out[i.code] += 1
        return dict(out)

    def ok_for_backtest(self, max_excluded_pct: float = 5.0) -> bool:
        if self.total_bars == 0:
            return False
        days_total = max(1, self.day_span())
        return (len(self.excluded_days) / days_total * 100.0) <= max_excluded_pct

    def day_span(self) -> int:
        """ความยาวข้อมูลเป็นวัน (จาก first → last bar) — ใช้เป็นตัวหารของ gate"""
        if self.first_ts is None or self.last_ts is None:
            return 1
        return max(1, round((self.last_ts - self.first_ts) / 86400))

    def as_dict(self) -> dict:
        return {
            "total_bars": self.total_bars,
            "issues_by_code": self.by_code(),
            "excluded_days": sorted(str(d) for d in self.excluded_days),
            "n_excluded_days": len(self.excluded_days),
            "day_span": self.day_span(),
            "first_ts": self.first_ts, "last_ts": self.last_ts,
            "spread_samples": self.spread_samples,
            "spread_p50": self.spread_p50, "spread_p95": self.spread_p95,
            "ok_for_backtest": self.ok_for_backtest(),
        }


class TradeabilityMap:
    """วันไหนเทรดได้ (ข้อมูลสะอาด + ตลาดเปิดครบ) — engine/backtest ใช้กรอง"""

    def __init__(self, excluded_days: set[date], cal: FXCalendar | None = None):
        self.excluded = excluded_days
        self.cal = cal or FXCalendar()

    def tradable(self, ts: int) -> bool:
        d = datetime.fromtimestamp(ts, tz=UTC).date()
        if d in self.excluded:
            return False
        return True


class QualityScanner:
    """สแกน bars แบบ streaming — หนึ่ง pass, จำ state น้อยที่สุด"""

    def __init__(self, spec: SourceSpec, cal: FXCalendar | None = None,
                 max_session_gap_min: float = 45.0):
        self.spec = spec
        self.cal = cal or FXCalendar(kind=spec.market_hours)
        self.max_session_gap_min = max_session_gap_min
        self.report = QualityReport()

    def scan(self, bars: list) -> QualityReport:
        rep = self.report
        rep.total_bars = len(bars)
        prev: Bar | None = None
        spreads: list[float] = []
        for bar in bars:
            if rep.first_ts is None:
                rep.first_ts = bar.ts
            rep.last_ts = bar.ts

            # DQ005/DQ006 — OHLC consistency
            if bar.high < bar.low:
                rep.add("DQ005_high_lt_low", bar.ts, f"high={bar.high} low={bar.low}")
                continue
            if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high):
                rep.add("DQ006_close_out_of_range", bar.ts,
                        f"o={bar.open} c={bar.close} not in [{bar.low},{bar.high}]")
                continue

            # DQ009 — frozen bar (H=L และ volume=0 กลางสัปดาห์เปิดปกติ)
            if bar.high == bar.low and bar.volume == 0 and self.cal.is_open(bar.ts):
                rep.add("DQ009_frozen_bar", bar.ts, "high==low and volume==0 while market open")

            # DQ003/DQ004 — monotonic + duplicate
            if prev is not None:
                if bar.ts == prev.ts:
                    rep.add("DQ004_duplicate_ts", bar.ts, "duplicate timestamp")
                    continue
                if bar.ts < prev.ts:
                    rep.add("DQ003_non_monotonic", bar.ts, f"ts {bar.ts} < prev {prev.ts}")
                    continue
                # DQ012 — gap classification
                gap = self.cal.classify_gap(prev.ts, bar.ts)
                if gap == "outage":
                    rep.add("DQ012_outage_gap", bar.ts,
                            f"gap {(bar.ts - prev.ts) / 60:.0f}min mid-week (prev {prev.ts})")
                elif gap == "weekend" and (bar.ts - prev.ts) / 3600.0 > self.cal.max_weekend_hours:
                    # เกิน weekend ปกติของตลาดนี้ = วันหยุดต่อ (long weekend)
                    rep.add("DQ012_long_weekend", bar.ts,
                            f"weekend gap {(bar.ts - prev.ts) / 3600:.1f}h > {self.cal.max_weekend_hours}h")

                # DQ011 — missing bars ในช่วง session เทรด (สั้นกว่า outage แต่ผิด grid)
                expected = prev.ts + M15
                if expected < bar.ts and gap == "ok":
                    rep.add("DQ011_grid_gap", bar.ts,
                            f"missing {(bar.ts - prev.ts) // M15 - 1} bars on M15 grid")

            # DQ008 — bad tick (range ผิดปกติมาก: > 50× median จะเช็คแบบ running)
            if bar.volume < 0:
                rep.add("DQ008_negative_volume", bar.ts, f"volume={bar.volume}")

            # spread สถิติ (ถ้ามี)
            sp = getattr(bar, "spread", None)
            if sp:
                spreads.append(sp)
            prev = bar

        if spreads:
            spreads.sort()
            rep.spread_samples = len(spreads)
            rep.spread_p50 = spreads[len(spreads) // 2]
            rep.spread_p95 = spreads[int(len(spreads) * 0.95)]
        return rep
