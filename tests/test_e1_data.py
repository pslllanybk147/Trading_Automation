# -*- coding: utf-8 -*-
"""E1 data layer tests — schema/margin/quality/loader(fake API)/CLI helpers

ครอบคลุม: pagination ของ funding, incremental sync (ขอเฉพาะของใหม่),
cache roundtrip, liq math, margin ladder, DQ scanner
"""
from __future__ import annotations

import pytest

from e1 import binance, margin
from e1.data_schema import E1DataError, FundingEvent, Kline, funding_intervals_ms
from e1.loader import E1Loader, funding_summary
from e1.quality import scan_all

H8 = 8 * 3600 * 1000
D1 = 24 * 3600 * 1000
T0 = 1_600_000_000_000   # 2020-09-13 epoch ms


# ---------------- fake Binance session ----------------

class FakeSession:
    """จำลอง GET ของ funding + klines รวมถึงพฤติกรรม pagination"""

    def __init__(self, funding_rows: list[dict], spot_rows=None, perp_rows=None,
                 page_size: int = 500):
        self.funding_rows = sorted(funding_rows, key=lambda r: r["fundingTime"])
        self.spot_rows = spot_rows or []
        self.perp_rows = perp_rows or []
        self.page_size = page_size
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))

        class R:
            def __init__(self, payload, status=200):
                self._p = payload
                self.status_code = status
                self.text = str(payload)[:120]

            def json(self):
                if self.status_code != 200:
                    raise RuntimeError("http error")
                return self._p

        start = int(params.get("startTime") or 0)
        end = int(params.get("endTime") or 9_999_999_999_999)
        limit = int(params.get("limit") or 500)

        if url.endswith("/fundingRate"):
            sel = [r for r in self.funding_rows if start <= r["fundingTime"] <= end]
            # API จริง: ไม่มี startTime → คืน 'หน้าใหม่สุด' (ascending) — ต้องเลียนแบบ
            return R(sel[-self.page_size:])
        if url.endswith("/klines"):
            key = "perp_rows" if "fapi" in url else "spot_rows"
            rows = getattr(self, key)
            sel = [r for r in rows if start <= r[0] <= end]
            return R(sel[:1000])
        return R([], status=404)


def _funding_rows(n=1200, start=T0, step=H8):
    out = []
    for i in range(n):
        out.append({"symbol": "BTCUSDT", "fundingTime": start + i * step,
                    "fundingRate": f"{0.0001 * ((i % 7) - 2) / 3:.8f}",
                    "markPrice": "20000"})
    return out


def _kline_rows(n=48, start=T0, step=3600 * 1000, px=20000.0):
    rows = []
    for i in range(n):
        o = px + (i % 5)
        rows.append([start + i * step, f"{o}", f"{o+10}", f"{o-10}", f"{o+2}", "10"])
    return rows


def _to_klines(rows, market):
    return [Kline("BTCUSDT", r[0], float(r[1]), float(r[2]), float(r[3]),
                  float(r[4]), float(r[5]), market) for r in rows]


# ---------------- schema ----------------

def test_funding_event_validates_extreme_rate():
    with pytest.raises(E1DataError):
        FundingEvent("BTCUSDT", T0, 0.06)          # 6% ต่อ interval = ผิดปกติ
    FundingEvent("BTCUSDT", T0, 0.00075)           # 0.075% = cap เก่า ผ่านได้


def test_kline_validates_ohlc():
    with pytest.raises(E1DataError):
        Kline("BTCUSDT", T0, 100, 90, 110, 95, 1)  # high < low
    with pytest.raises(E1DataError):
        Kline("BTCUSDT", T0, 100, 120, 110, 115, 1)  # open > high
    Kline("BTCUSDT", T0, 100, 120, 90, 115, 1)     # ปกติ


def test_funding_intervals_counts():
    evs = [FundingEvent("X", T0 + i * H8, 0.0001) for i in range(5)]
    ivs = funding_intervals_ms(evs)
    assert ivs == {H8: 4}


# ---------------- margin ----------------

def test_mmr_by_notional_tiers():
    assert margin.mmr_for("BTCUSDT", 10_000) == 0.004
    assert margin.mmr_for("BTCUSDT", 100_000) == 0.005
    assert margin.mmr_for("BTCUSDT", 2_000_000) == 0.02
    assert margin.mmr_for("UNKNOWN", 5_000) == 0.005   # fallback ชั้นแรก


def test_liq_price_short_increases_with_leverage():
    # ชอร์ต: liq อยู่ 'เหนือ' entry เสมอ; leverage สูง = liq ใกล้ entry มากขึ้น
    liq_1x = margin.liq_price_short(entry=20_000, qty=0.5, margin=10_000,
                                    symbol="BTCUSDT")
    liq_2x = margin.liq_price_short(entry=20_000, qty=0.5, margin=5_000,
                                    symbol="BTCUSDT")
    assert liq_1x > liq_2x > 20_000
    # 1x short: liq ≈ 2× entry (margin เท่า notional)
    assert liq_1x == pytest.approx(20_000 * 2, rel=0.01)
    # 2x short: liq ≈ 1.5× entry
    assert liq_2x == pytest.approx(20_000 * 1.5, rel=0.01)


def test_margin_ratio_and_ladder():
    ratio = margin.margin_ratio_short(entry=20_000, mark=21_000, qty=0.5,
                                      margin=6_000, symbol="BTCUSDT")
    assert ratio > 0
    ladder = margin.MarginLadder()
    assert ladder.evaluate(3.0).level == "ok"
    assert ladder.evaluate(2.0).level == "warn"
    assert ladder.evaluate(1.4).level == "deleverage"
    assert ladder.evaluate(1.1).level == "close"
    with pytest.raises(margin.MarginConfigError):
        margin.MarginLadder(warn_at=1.0, topup_to=2.0)   # ลำดับผิด


def test_topup_amount_positive_when_pressured():
    # margin 900: bal = 900 + (20000−21800)×0.5 = 0 → กดบันไดจริง
    need = margin.MarginLadder().topup_amount(
        entry=20_000, mark=21_800, qty=0.5, margin=900, symbol="BTCUSDT")
    assert need > 0
    # และหลังเติม ratio ต้องกลับมาที่ topup_to
    r = margin.margin_ratio_short(20_000, 21_800, 0.5, 900 + need, "BTCUSDT")
    assert r == pytest.approx(margin.MarginLadder().topup_to, rel=0.02)


# ---------------- quality ----------------

def test_scan_funding_gaps_and_interval_info():
    evs = [FundingEvent("BTCUSDT", T0 + i * H8, 0.0001) for i in range(10)]
    evs.append(FundingEvent("BTCUSDT", evs[-1].funding_time_ms + 40 * 3600_000, 0.0001))
    rep = scan_all("BTCUSDT", evs, [], [], 3600 * 1000)[0]
    codes = rep.by_code()
    assert codes.get("E1D_FUNDING_GAP", 0) == 1
    assert any("8h" in i.detail for i in rep.issues if i.code == "E1D_INFO_INTERVALS")


def test_scan_klines_gap_and_duplicate():
    rows = _kline_rows(10)
    rows.append([rows[-1][0], "1", "1", "1", "1", "1"])   # dup
    kl = _to_klines(rows, "perp")
    reports = scan_all("BTCUSDT", [], [], kl, 3600 * 1000)
    assert reports[0].by_code().get("E1D_EMPTY_FUNDING", 0) == 1
    assert reports[2].by_code().get("E1D_DUP_PERP", 0) == 1


# ---------------- loader (fake API) ----------------

def test_sync_funding_paginates_and_caches(tmp_path):
    fs = FakeSession(_funding_rows(1200), page_size=500)
    loader = E1Loader(str(tmp_path / "c.db"))
    added = loader.sync_funding(fs, "BTCUSDT")
    assert added == 1200
    evs = loader.load_funding("BTCUSDT")
    assert len(evs) == 1200
    assert evs[0].funding_time_ms == T0
    # incremental: ส่งข้อมูลเพิ่ม 24 แถว → sync ใหม่ต้องขอเฉพาะหลัง last
    extra_start = T0 + 1200 * H8
    fs.funding_rows.extend(_funding_rows(24, start=extra_start))
    added2 = loader.sync_funding(fs, "BTCUSDT")
    assert added2 == 24
    assert len(loader.load_funding("BTCUSDT")) == 1224
    # request ล่าสุดต้องขอจากหลัง last เดิม (incremental จริง — cursor = last+1)
    last_call = [c for c in fs.calls if c[0].endswith("/fundingRate")][-1]
    assert int(last_call[1]["startTime"]) == T0 + 1199 * H8 + 1
    loader.close()


def test_sync_klines_roundtrip_and_scan(tmp_path):
    fs = FakeSession(_funding_rows(10), spot_rows=_kline_rows(48),
                     perp_rows=_kline_rows(48))
    loader = E1Loader(str(tmp_path / "c.db"))
    loader.sync_funding(fs, "BTCUSDT")
    loader.sync_klines(fs, "BTCUSDT", "1h", "spot")
    loader.sync_klines(fs, "BTCUSDT", "1h", "perp")
    funding, spot, perp, reports = loader.load_symbol("BTCUSDT", "1h")
    assert len(funding) == 10 and len(spot) == 48 and len(perp) == 48
    real_issues = [i for r in reports for i in r.issues
                   if not i.code.startswith("E1D_INFO")]
    assert real_issues == []   # ข้อมูลสมบูรณ์ = ไม่มีปัญหาจริง (INFO ไม่นับ)
    loader.close()


def test_fetch_funding_backward_walk_full_history():
    """ไม่ระบุ start → เดินถอยหลังจากปัจจุบัน ต้องได้ครบทั้งประวัติ เรียง ascending"""
    fs = FakeSession(_funding_rows(1200), page_size=500)
    rows = binance.fetch_funding(fs, "BTCUSDT")
    assert len(rows) == 1200
    ts = [r["fundingTime"] for r in rows]
    assert ts == sorted(ts)
    assert ts[0] == T0 and ts[-1] == T0 + 1199 * H8


def test_funding_summary_shape():
    evs = [FundingEvent("BTCUSDT", T0 + i * H8, 0.0001) for i in range(100)]
    s = funding_summary(evs)
    assert s["per_day"] == 3
    assert s["positive_pct"] == 100.0
    # 0.01% × 3/วัน × 365 = 10.95%/ปี
    assert s["ann_pct"] == pytest.approx(10.95, abs=0.01)
