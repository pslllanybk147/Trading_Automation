# -*- coding: utf-8 -*-
"""Fetch macro drivers for gold → daily cache (data/macro_cache.json).

Sources (ฟรี ไม่ต้อง API key — FRED มี rate limit หนักจาก IP นี้เลยใช้ทางเลือก):
  - real_yield_10y_tips : 10Y TIPS real yield จาก Treasury.gov daily real yield curve
    (เท่ากับ FRED DFII10 ทุกค่า — verify แล้ว: 2024-01-02 = 1.74 ทั้งคู่)
    master gold signal: real yield ลด/ติดลบ = bullish gold
  - dxy_broad : DXY จาก Yahoo Finance (DX-Y.NYB) — gold สวนทาง USD ~70-80%

Usage:  python fetch_macro.py            # fetch 2021..today
"""
import json
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

CACHE = Path("data/macro_cache.json")
TREASURY_URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                "pages/xml?data=daily_treasury_real_yield_curve&field_tdr_date_value={year}")
DXY_URL = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?range={years}y&interval=1d"


def curl(url: str) -> str:
    r = subprocess.run(["curl", "-s", "--max-time", "45",
                        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"],
                       capture_output=True, text=True, input="", check=False)
    # curl ต้องรับ url เป็น argument — แก้: เรียกใหม่ให้ถูกต้อง
    r = subprocess.run(["curl", "-s", "--max-time", "45",
                        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", url],
                       capture_output=True, text=True, check=False)
    return r.stdout


def fetch_treasury_real_yield(start_year: int, end_year: int) -> dict[str, float]:
    """TC_10YEAR = 10Y TIPS real yield (เทียบเท่า FRED DFII10) — รายปี"""
    rows: dict[str, float] = {}
    for year in range(start_year, end_year + 1):
        text = ""
        for attempt in range(5):
            text = curl(TREASURY_URL.format(year=year))
            if "TC_10YEAR" in text:
                break
            print(f"  [{year}] โดนตัด attempt {attempt+1} — รอ 20s")
            time.sleep(20)
        dates = re.findall(r"<d:NEW_DATE[^>]*>([^<]+)</d:NEW_DATE>", text)
        vals = re.findall(r"<d:TC_10YEAR[^>]*>([^<]*)</d:TC_10YEAR>", text)
        n = 0
        for d, v in zip(dates, vals):
            if not v.strip():
                continue
            try:
                rows[d[:10]] = float(v)
                n += 1
            except ValueError:
                pass
        print(f"  {year}: {n} rows")
        time.sleep(3)
    return rows


def fetch_dxy(years: int) -> dict[str, float]:
    text = ""
    for attempt in range(5):
        text = curl(DXY_URL.format(years=years))
        if text.strip().startswith("{"):
            break
        print(f"  dxy โดนตัด attempt {attempt+1} — รอ 20s")
        time.sleep(20)
    rows: dict[str, float] = {}
    try:
        d = json.loads(text)
        r = d["chart"]["result"][0]
        ts = r["timestamp"]
        q = r["indicators"]["quote"][0]["close"]
        for t, v in zip(ts, q):
            if v is None:
                continue
            rows[datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")] = v
    except Exception as e:
        print(f"  dxy parse error: {e}")
    return rows


def main() -> None:
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2021,
                    help="เริ่มปีแรกของ real yield (default 2021 — ครอบคลุม backtest ทอง 5 ปี)")
    args = ap.parse_args()

    end_year = datetime.utcnow().year
    print("Fetch 10Y TIPS real yield (Treasury.gov)...")
    ry = fetch_treasury_real_yield(args.start_year, end_year)
    print("Fetch DXY (Yahoo)...")
    dxy = fetch_dxy(end_year - args.start_year + 1)

    out = {"fetched": datetime.utcnow().isoformat(timespec="seconds"),
           "start_year": args.start_year,
           "series": {"real_yield_10y_tips": ry, "dxy_broad": dxy}}
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"บันทึก: {CACHE} — real_yield {len(ry)} rows, dxy {len(dxy)} rows")


if __name__ == "__main__":
    main()