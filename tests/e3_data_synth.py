# -*- coding: utf-8 -*-
"""E3 data synth — สร้าง CSV ทดสอบควบคุมได้: tz, spread, holiday, outage, bad rows"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
M15 = 900


def write_csv(path: str | Path, rows: list[dict], tz_name: str = "UTC",
              spread_col: str | None = "spread") -> Path:
    """rows = [{'ts': epoch_utc, 'o','h','l','c','v', ('spread')}]
    timestamp เขียนเป็น ISO ใน tz ที่กำหนด (จำลอง MT5 EET ฯลฯ)"""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tz_name)
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    if spread_col:
        cols.append(spread_col)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            dt = datetime.fromtimestamp(r["ts"], tz=UTC).astimezone(tz)
            out = {
                "timestamp": dt.isoformat(),
                "open": r["o"], "high": r["h"], "low": r["l"], "close": r["c"],
                "volume": r.get("v", 100),
            }
            if spread_col:
                out[spread_col] = r.get("spread", 0.30)
            w.writerow(out)
    return p


def clean_week(y: int, m: int, d: int, base: float = 2000.0, wick: float = 0.5,
               spread: float = 0.30) -> list[dict]:
    """สัปดาห์ปกติ: (d ต้องเป็นวันอาทิตย์) อาทิตย์ 22:00 UTC → ศุกร์ 21:45 UTC —
    M15 ต่อเนื่อง ไม่มี daily break (ทอง OTC ไม่พักกลางวัน)"""
    assert datetime(y, m, d, tzinfo=UTC).weekday() == 6, "d ต้องเป็นวันอาทิตย์"
    rows = []
    start = datetime(y, m, d, 22, 0, tzinfo=UTC)          # อาทิตย์ 22:00
    end = start + timedelta(days=5)                       # ศุกร์ 22:00 (Sun→Fri = 5 วัน)
    t = start
    while t < end:
        rows.append({"ts": int(t.timestamp()), "o": base, "h": base + wick,
                     "l": base - wick, "c": base, "v": 100, "spread": spread})
        t += timedelta(minutes=15)
    return rows


def rows_with_outage(y: int, m: int, d: int, out_h: int = 12, n_missing: int = 8) -> list[dict]:
    """สัปดาห์ปกติ + ช่องว่างกลางวัน (feed outage)"""
    rows = clean_week(y, m, d)
    out_start = datetime(y, m, d + 1, out_h, 0, tzinfo=UTC)   # จันทร์
    out_end = out_start + timedelta(minutes=15 * n_missing)
    return [r for r in rows
            if not (out_start.timestamp() <= r["ts"] < out_end.timestamp())]


def rows_with_bad_bar(y: int, m: int, d: int) -> list[dict]:
    rows = clean_week(y, m, d)
    # แท่ง high < low ที่จันทร์ 10:00
    bad_ts = int(datetime(y, m, d + 1, 10, 0, tzinfo=UTC).timestamp())
    for r in rows:
        if r["ts"] == bad_ts:
            r["h"], r["l"] = 1990.0, 2000.0
    return rows
