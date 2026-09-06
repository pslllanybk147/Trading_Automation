# -*- coding: utf-8 -*-
"""E3 loader tests — tz conversion, MT5 preset, cache, spread profile"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from e3.data.loader import Loader, spread_profile_from_bars
from e3.data.schema import SpecError, SourceSpec, to_spread_price

from tests.e3_data_synth import clean_week, write_csv

UTC = timezone.utc


def test_source_tz_mandatory():
    with pytest.raises(SpecError):
        SourceSpec(path="x.csv", source_tz="")
    with pytest.raises(SpecError):
        SourceSpec(path="x.csv", source_tz="Not/AZone")


def test_mt5_eet_converted_to_utc(tmp_path):
    """MT5 เขียน 10:00 EET (UTC+2 winter) → ต้องเป็น 08:00 UTC"""
    rows = clean_week(2026, 3, 8)
    p = write_csv(tmp_path / "mt5.csv", rows, tz_name="Europe/Helsinki")
    spec = SourceSpec(path=str(p), source_tz="Europe/Helsinki", spread_column="spread")
    bars = Loader(cache_path=None).normalize(spec)
    # bar แรก: อาทิตย์ 22:00 UTC = เที่ยงคืน EET
    first = datetime.fromtimestamp(bars[0].ts, tz=UTC)
    assert (first.weekday(), first.hour) == (6, 22)


def test_epoch_timestamps(tmp_path):
    rows = clean_week(2026, 3, 8)
    # เขียน ts เป็น epoch ตรง ๆ
    p = tmp_path / "epoch.csv"
    import csv
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume", "spread"])
        for r in rows:
            w.writerow([r["ts"], r["o"], r["h"], r["l"], r["c"], r["v"], r["spread"]])
    spec = SourceSpec(path=str(p), source_tz="UTC", spread_column="spread")
    bars = Loader(cache_path=None).normalize(spec)
    assert bars[0].ts == rows[0]["ts"]


def test_spread_points_converted(tmp_path):
    """MT5 spread เป็น point (1 point = $0.01) — 30 points = $0.30"""
    rows = clean_week(2026, 3, 8)
    for r in rows:
        r["spread"] = 30.0        # points
    p = write_csv(tmp_path / "points.csv", rows, spread_col="spread")
    spec = SourceSpec(path=str(p), source_tz="UTC", spread_column="spread",
                      spread_points=True, point_value=0.01)
    bars = Loader(cache_path=None).normalize(spec)
    assert abs(bars[0].spread - 0.30) < 1e-9
    assert to_spread_price(30.0, spec) == pytest.approx(0.30)


def test_cache_roundtrip(tmp_path):
    rows = clean_week(2026, 3, 8)
    p = write_csv(tmp_path / "c.csv", rows)
    spec = SourceSpec(path=str(p), source_tz="UTC", spread_column="spread")
    cache = str(tmp_path / "cache.db")

    l1 = Loader(cache_path=cache)
    bars1, _ = l1.load(spec, force_rescan=True)
    l1.close()

    l2 = Loader(cache_path=cache)
    bars2, _ = l2.load(spec)            # จาก cache
    l2.close()
    assert len(bars1) == len(bars2)
    assert [b.ts for b in bars1] == [b.ts for b in bars2]
    assert bars1[0].close == bars2[0].close


def test_cache_invalidated_on_file_change(tmp_path):
    rows = clean_week(2026, 3, 8)
    p = write_csv(tmp_path / "v.csv", rows)
    spec = SourceSpec(path=str(p), source_tz="UTC", spread_column="spread")
    cache = str(tmp_path / "cache.db")

    l1 = Loader(cache_path=cache)
    n1 = len(l1.load(spec, force_rescan=True)[0])
    l1.close()

    # แก้ไฟล์ (ตัด row สุดท้ายออก) → sha เปลี่ยน → cache ต้อง refresh
    lines = p.read_text().splitlines()
    p.write_text("\n".join(lines[:-1]) + "\n")
    import os
    os.utime(p, (0, 0))  # บังคับ mtime เปลี่ยนชัวร์

    l2 = Loader(cache_path=cache)
    n2 = len(l2.load(spec, force_rescan=False)[0])
    l2.close()
    assert n2 == n1 - 1


def test_spread_profile_by_hour(tmp_path):
    """spread รายชั่วโมง — London/NY แคบกว่า Asian (จำลอง)"""
    rows = clean_week(2026, 3, 8)
    for r in rows:
        h = datetime.fromtimestamp(r["ts"], tz=UTC).hour
        r["spread"] = 0.20 if 8 <= h <= 20 else 0.45   # กว้างตอนตลาดบาง
    p = write_csv(tmp_path / "sp.csv", rows)
    spec = SourceSpec(path=str(p), source_tz="UTC", spread_column="spread")
    bars = Loader(cache_path=None).normalize(spec)
    profile = spread_profile_from_bars(bars)
    assert profile[10] < profile[3]      # London 10:00 แคบกว่า Asian 03:00
    assert abs(profile[10] - 0.20) < 1e-9
    assert abs(profile[3] - 0.45) < 1e-9
