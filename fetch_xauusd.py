# -*- coding: utf-8 -*-
"""โหลด XAUUSD (ทองคำ) M1 จาก histdata.com → resample เป็น 4h → เก็บเข้า data/cache.db
ภายใต้ symbol "XAUUSD" เพื่อให้ backtest_history.py รันกับทองได้ (`--symbol-list XAUUSD
--no-fetch --no-volume`)

histdata ASCII M1 format: `YYYYMMDD HHMMSS;O;H;L;C;V` — volume เป็น 0 เสมอ (ทองไม่มี
volume จริง → ต้องรัน harness ด้วย --no-volume เพื่อปิด volume spike filter)

หมายเหตุ timezone: histdata ให้เวลาตาม server (UTC) — ใช้ตรง ๆ 4h bar = floor(ts/4h)
"""
from __future__ import annotations
import datetime as _dt
import io
import json
import re
import time
import http.cookiejar
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from pipeline.data_layer import CACHE_DB, cache_candles
from pipeline.models import CandleData

BASE = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/xauusd/{year}"
GET_URL = "https://www.histdata.com/get.php"
STEP = 14400  # 4h


class Histdata:
    """session กับ cookie jar + Referer (histdata ต้องใช้ cookie ถึงจะให้ zip)"""
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj))

    def _get(self, url: str, data: bytes | None = None) -> bytes:
        headers = {"User-Agent": "Mozilla/5.0",
                   "Referer": url if data is None else GET_URL}
        req = urllib.request.Request(url, data=data, headers=headers)
        with self.op.open(req, timeout=180) as resp:
            return resp.read()

    def download_year_zip(self, year: int) -> bytes:
        """GET หน้าโหลด → ดึง token → POST /get.php → คืน zip bytes ของ M1 ทั้งปี."""
        page_url = BASE.format(year=year)
        page = self._get(page_url).decode("utf-8", "ignore")
        m = re.search(r'name="tk"[^>]*value="([^"]+)"', page)
        if not m:
            raise RuntimeError(f"no token for {year}")
        tk = m.group(1)
        form = urllib.parse.urlencode({
            "tk": tk, "date": str(year), "datemonth": str(year),
            "platform": "ASCII", "timeframe": "M1", "fxpair": "XAUUSD",
        }).encode()
        data = self._get(GET_URL, form)
        if len(data) < 1000 or not data[:2] == b"PK":
            raise RuntimeError(f"bad zip for {year}: {len(data)} bytes")
        return data


def parse_year_zip(zip_bytes: bytes) -> list[dict]:
    """อ่าน CSV M1 ข้างใน zip → list ของ dict (ts, o, h, l, c)"""
    rows = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        name = [n for n in zf.namelist() if n.lower().endswith(".csv")][0]
        text = zf.read(name).decode("utf-8", "ignore")
    for line in text.splitlines():
        parts = line.split(";")
        if len(parts) < 6:
            continue
        try:
            dt_s, tm_s = parts[0].split()
            ts = int(_dt.datetime.strptime(dt_s + tm_s, "%Y%m%d%H%M%S")
                     .replace(tzinfo=_dt.timezone.utc).timestamp())
            o, h, l, c = (float(parts[1]), float(parts[2]),
                          float(parts[3]), float(parts[4]))
        except ValueError:
            continue
        rows.append({"ts": ts, "o": o, "h": h, "l": l, "c": c})
    return rows


def resample_4h(rows: list[dict]) -> list[CandleData]:
    df = pd.DataFrame(rows)
    if df.empty:
        return []
    df["ts"] = (df["ts"] // STEP) * STEP
    g = df.groupby("ts")
    out = []
    for ts, grp in g:
        out.append(CandleData(
            symbol="XAUUSD", timeframe="4h", ts=int(ts),
            o=float(grp["o"].iloc[0]), h=float(grp["h"].max()),
            l=float(grp["l"].min()), c=float(grp["c"].iloc[-1]), v=0.0,
        ))
    return out


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2021,
                    help="ปีแรกที่โหลด (default 2021 = ครอบคลุม 5 ปีถึงปัจจุบัน)")
    ap.add_argument("--end-year", type=int, default=_dt.datetime.now().year)
    ap.add_argument("--keep-zip", action="store_true",
                    help="เก็บ zip ดิบไว้ใน data/xauusd_raw/ (default: ไม่เก็บ)")
    args = ap.parse_args()

    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    hd = Histdata()
    for year in range(args.start_year, args.end_year + 1):
        try:
            zb = hd.download_year_zip(year)
        except Exception as e:
            print(f"  [{year}] download failed: {e}")
            continue
        rows = parse_year_zip(zb)
        print(f"  {year}: {len(rows):,} M1 rows")
        all_rows.extend(rows)
        if args.keep_zip:
            raw = Path("data/xauusd_raw")
            raw.mkdir(parents=True, exist_ok=True)
            (raw / f"xauusd_{year}.zip").write_bytes(zb)
        time.sleep(0.3)

    if not all_rows:
        print("ไม่มีข้อมูลเลย")
        return
    candles = resample_4h(all_rows)
    print(f"Resample -> {len(candles):,} 4h bars "
          f"({_dt.datetime.fromtimestamp(candles[0].ts, _dt.timezone.utc):%Y-%m-%d} → "
          f"{_dt.datetime.fromtimestamp(candles[-1].ts, _dt.timezone.utc):%Y-%m-%d})")
    cache_candles("XAUUSD", "4h", candles)
    print(f"เก็บเข้า cache: {CACHE_DB} (symbol=XAUUSD interval=4h)")


if __name__ == "__main__":
    main()
