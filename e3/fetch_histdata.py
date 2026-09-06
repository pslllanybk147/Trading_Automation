# -*- coding: utf-8 -*-
"""Fetch XAUUSD tick history จาก histdata.com → aggregate เป็น M15 + spread

ทำไม tick ไม่ใช่ M1 BID: ไฟล์ M1 เป็นฝั่งเดียว (BID) — ส่วน tick
(DAT_ASCII_XAUUSD_T_YYYYMM.csv) มีทั้ง bid+ask ต่อ tick → ได้ spread จริงต่อแท่ง
(spec §2 ต้องการ per-bar spread)

Flow ต่อ 1 เดือน (resume-able):
  1. GET หน้า month → scrape tk token
  2. POST /get.php → ZIP (DAT_ASCII_XAUUSD_T_YYYYMM.csv: "ts_ms,bid,ask,flag")
  3. aggregate tick → M15 bar (ts=UTC epoch, o/h/l/c จาก bid, spread=median(ask-bid))
  4. เขียน partial parquet ลง outdir — มีอยู่แล้ว = skip (จะ redownload ต้องลบไฟล์)

ใช้:
  python e3/fetch_histdata.py --outdir e3_data_raw --start 2018-01 --end 2026-08
  python e3/fetch_histdata.py --merge --outdir e3_data_raw \
      --out e3_data_raw/XAUUSD_M15_2018_2026.csv --tz UTC
"""
from __future__ import annotations

import argparse
import io
import json
import random
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

BASE = "https://www.histdata.com"
MONTH_URL = (BASE + "/download-free-forex-historical-data/"
             "?/ascii/tick-data-quotes/xauusd/{y}/{m}")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
M15 = 900
CSV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "spread"]


def month_list(start: str, end: str) -> list[tuple[int, int]]:
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def scrape_token(sess: requests.Session, y: int, m: int) -> str:
    url = MONTH_URL.format(y=y, m=f"{m:02d}")
    r = sess.get(url, timeout=30)
    r.raise_for_status()
    tks = re.findall(r'name="tk"[^>]*value="([0-9a-f]{32})"', r.text)
    if not tks:
        raise RuntimeError(f"no tk token at {url}")
    return tks[0]


def download_month_zip(sess: requests.Session, y: int, m: int,
                       retries: int = 4) -> bytes:
    tk = scrape_token(sess, y, m)
    form = {
        "tk": tk, "date": str(y), "datemonth": f"{y}{m:02d}",
        "platform": "ASCII", "timeframe": "T", "fxpair": "XAUUSD",
    }
    referer = MONTH_URL.format(y=y, m=f"{m:02d}")
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            r = sess.post(BASE + "/get.php", data=form, timeout=300,
                          headers={"Referer": referer})
            if r.status_code == 200 and r.content[:2] == b"PK":
                return r.content
            last_err = f"HTTP {r.status_code} len={len(r.content)}"
        except requests.RequestException as e:
            last_err = repr(e)[:120]
        time.sleep(3 * attempt + random.random() * 2)
    raise RuntimeError(f"download {y}-{m:02d} failed: {last_err}")


def aggregate_m15(zip_bytes: bytes) -> pd.DataFrame:
    """tick zip → DataFrame[timestamp, open, high, low, close, volume, spread]"""
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
    with zf.open(csv_name) as f:
        df = pd.read_csv(f, header=None, names=["ms", "bid", "ask", "flag"],
                         usecols=["ms", "bid", "ask"], dtype={"ms": str})
    df = df.dropna(subset=["bid", "ask"])
    # "20260802 180001000" = YYYYMMDD HHMMSSmmm (UTC)
    dt = pd.to_datetime(df["ms"], format="%Y%m%d %H%M%S%f", utc=True)
    # → epoch s (unit-safe: cast ลง resolution วินาทีก่อนแล้วค่อยเป็น int)
    df["ts"] = dt.astype("datetime64[s, UTC]").astype("int64")
    df = df[(df["ts"] > 0) & (df["bid"] > 0) & (df["ask"] > df["bid"] * 0.5)]
    df["ts15"] = df["ts"] - (df["ts"] % M15)
    g = df.groupby("ts15")
    out = pd.DataFrame({
        "open": g["bid"].first(),
        "high": g["bid"].max(),
        "low": g["bid"].min(),
        "close": g["bid"].last(),
        "volume": g["bid"].size(),
        "spread": (g["ask"].median() - g["bid"].median()),
    }).reset_index().rename(columns={"ts15": "timestamp"})
    out["timestamp"] = out["timestamp"].astype("int64")
    return out[CSV_COLUMNS]


def fetch_one(sess: requests.Session, y: int, m: int, outdir: Path,
              force: bool = False) -> tuple[Path, str]:
    part = outdir / f"tick_m15_{y}{m:02d}.parquet"
    if part.exists() and not force:
        return part, "cached"
    raw = download_month_zip(sess, y, m)
    df = aggregate_m15(raw)
    df.to_parquet(part, index=False)
    return part, f"ok rows={len(df)} zip={len(raw)//1024}KB"


def merge(outdir: Path, out_csv: Path) -> None:
    parts = sorted(outdir.glob("tick_m15_*.parquet"))
    if not parts:
        raise SystemExit("no partials to merge")
    dfs = [pd.read_parquet(p) for p in parts]
    big = pd.concat(dfs).drop_duplicates("timestamp").sort_values("timestamp")
    big = big.reset_index(drop=True)
    # sanity
    dup = int(big["timestamp"].duplicated().sum())
    gaps = (big["timestamp"].diff() // M15).dropna()
    n_gap_gt1 = int((gaps > 1).sum())
    big["iso"] = pd.to_datetime(big["timestamp"], unit="s", utc=True).dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    out = big[["iso"] + CSV_COLUMNS].copy()
    out.columns = ["timestamp"] + CSV_COLUMNS
    out.to_csv(out_csv, index=False)
    print(json.dumps({
        "parts": len(parts), "bars": len(big), "duplicates": dup,
        "gap_runs_gt1_bar": n_gap_gt1,
        "first": str(big["timestamp"].iloc[0]),
        "last": str(big["timestamp"].iloc[-1]),
        "csv": str(out_csv), "size_mb": round(out_csv.stat().st_size / 1e6, 1),
    }, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="e3_data_raw")
    ap.add_argument("--start", default="2018-01")
    ap.add_argument("--end", default="2026-08")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--out", default="e3_data_raw/XAUUSD_M15_2018_2026.csv")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if a.merge:
        merge(outdir, Path(a.out))
        return

    months = month_list(a.start, a.end)
    print(f"fetching {len(months)} months -> {outdir}", flush=True)
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    ok = skip = fail = 0
    for i, (y, m) in enumerate(months, 1):
        try:
            part, status = fetch_one(sess, y, m, outdir, force=a.force)
        except Exception as e:
            fail += 1
            print(f"[{i}/{len(months)}] {y}-{m:02d} FAIL {e}", flush=True)
            time.sleep(5)
            continue
        if status == "cached":
            skip += 1
        else:
            ok += 1
        print(f"[{i}/{len(months)}] {y}-{m:02d} {status}", flush=True)
        time.sleep(1.5 + random.random() * 1.5)   # ระวังเซิร์ฟเวอร์เขา
    print(f"DONE ok={ok} cached={skip} fail={fail}", flush=True)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
