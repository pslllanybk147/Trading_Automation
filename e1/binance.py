# -*- coding: utf-8 -*-
"""E1 binance fetchers — fundingRate (paginate) + klines spot/perp

- funding: /fapi/v1/fundingRate — cursor ด้วย startTime = last+1 (API คืน ≤500 แถว
  แม้ limit=1000 ในปัจจุบัน) — วนจนครบถึงปัจจุบัน
- klines: /api/v3/klines (spot) และ /fapi/v1/klines (perp) — paginate ด้วย
  openTime ของแท่งสุดท้าย + 1ms, limit=1000
- rate limit: sleep เล็ก ๆ ระหว่างหน้า (weight คำนวณคร่าว ๆ — อย่ายิงรัว)
"""
from __future__ import annotations

import time

import requests

SPOT = "https://api.binance.com/api/v3"
FAPI = "https://fapi.binance.com/fapi/v1"


class BinanceError(RuntimeError):
    pass


def _get(sess: requests.Session, url: str, params: dict) -> list:
    r = sess.get(url, params=params, timeout=30)
    if r.status_code != 200:
        raise BinanceError(f"HTTP {r.status_code}: {r.text[:160]} @ {url}")
    return r.json()


def fetch_funding(sess: requests.Session, symbol: str,
                  start_ms: int | None = None, end_ms: int | None = None,
                  pause: float = 0.15) -> list[dict]:
    """ประวัติ fundingRate — คืน list[dict] ดิบเรียงเวลา (ascending)

    พฤติกรรม API ที่วัดจริง: startTime=0 จะถูกเมินแล้วคืนหน้าล่าสุด (~500 แถว)
    → ถ้าไม่ระบุ start_ms = เดิน cursor **ถอยหลัง** จาก end ด้วย endTime
      (ทำงานกับเหรียญไหนก็ได้โดยไม่ต้องรู้วัน listing)
    ถ้าระบุ start_ms (incremental) = เดินไปหน้า ด้วย startTime จริง (honored เมื่อ > 0)
    """
    out: list[dict] = []
    end = end_ms if end_ms is not None else int(time.time() * 1000)
    if start_ms is None:
        cursor = end
        while True:
            rows = _get(sess, f"{FAPI}/fundingRate", {
                "symbol": symbol, "endTime": cursor, "limit": 1000})
            if not rows:
                break
            out.extend(rows)
            if len(rows) < 500:
                break
            cursor = rows[0]["fundingTime"] - 1
            time.sleep(pause)
        out.sort(key=lambda r: r["fundingTime"])
    else:
        cur = start_ms
        while True:
            rows = _get(sess, f"{FAPI}/fundingRate", {
                "symbol": symbol, "startTime": cur, "endTime": end, "limit": 1000})
            if not rows:
                break
            out.extend(rows)
            last = rows[-1]["fundingTime"]
            if len(rows) < 500 or last >= end:
                break
            cur = last + 1
            time.sleep(pause)
    # กันซ้ำขอบหน้า
    seen, uniq = set(), []
    for r in out:
        if r["fundingTime"] in seen:
            continue
        seen.add(r["fundingTime"])
        uniq.append(r)
    return uniq


def fetch_klines(sess: requests.Session, symbol: str, interval: str,
                 market: str = "perp", start_ms: int | None = None,
                 end_ms: int | None = None, pause: float = 0.1) -> list[list]:
    """แท่งเทียน spot/perp — คืน list row ดิบ [openTime, o, h, l, c, v, ...]"""
    base = FAPI if market == "perp" else SPOT
    out: list[list] = []
    cur = start_ms if start_ms is not None else 0
    end = end_ms if end_ms is not None else int(time.time() * 1000)
    while True:
        rows = _get(sess, f"{base}/klines", {
            "symbol": symbol, "interval": interval,
            "startTime": cur, "endTime": end, "limit": 1000})
        if not rows:
            break
        out.extend(rows)
        last_open = rows[-1][0]
        if len(rows) < 1000 or last_open >= end:
            break
        cur = last_open + 1
        time.sleep(pause)
    return out
