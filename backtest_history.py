# -*- coding: utf-8 -*-
"""Backtest กฎจริงของ pipeline กับข้อมูลย้อนหลัง 2-3 ปี (Binance 4h, Spot)

ใช้กฎจากโค้ดจริง:
  - สัญญาณ: signal_engine (golden cross MA7/25 + RSI 45-75 + volume spike 1.5x,
    turtle breakout Donchian 20) — vectorized ใหม่แต่เงื่อนไข/ค่า TP/SL เหมือนกัน
  - Risk: risk_engine "รุก" = risk 3%/เทรด, max_total_risk 10%, max_positions 5,
    3 ขาดทุน/วัน = หยุดวันนั้น, DD <= -20% = หยุด 1 สัปดาห์
  - Execution: fee 0.1% + slippage 0.05% (ค่าจริงจาก execution.py)
  - เงินต้น 50,000 USDT, Spot ไม่มี leverage -> size ถูก cap ด้วย cash ที่เหลือ

หมายเหตุความต่างจาก live (บันทึกให้เห็นภาพ):
  - live มี AI governor / validation gate คอยกรองอีกชั้น -> จำนวนเทรดจริง <= นี้
  - golden cross: เข้า 1 ครั้งต่อ cross (dedupe) เพื่อไม่ให้ cross เดียวเข้า 6 ครั้งซ้ำ
  - ปิดเต็มจำนวนที่ SL หรือ TP1 (เหมือน PaperExchange v1) TP2 ยังไม่ใช้
"""
from __future__ import annotations
import argparse
import bisect
import json
import math
import time
import urllib.request
from pathlib import Path

import pandas as pd

from pipeline.data_layer import (
    BINANCE_KLINE_URL, FALLBACK_TOP30, cache_candles,
    load_cached_candles, parse_klines,
)
from pipeline.execution import FEE_RATE, SLIPPAGE

STEP_SEC = {"1h": 3600, "4h": 14400, "1d": 86400}
MA_FAST, MA_SLOW, CROSS_LOOKBACK = 7, 25, 5
RSI_PERIOD, RSI_MIN, RSI_MAX = 14, 45, 75
VOLUME_WINDOW, VOLUME_SPIKE = 20, 1.5
ATR_PERIOD = 14
TURTLE_ENTRY = 20
SMC_SWING_N = 20   # liquidity pool: low สุดของ 20 แท่งก่อน (4h ≈ 3-4 วัน)
SMC_BOS_WIN = 12  # ต้อง Break of Structure ภายใน 12 แท่ง (≈ 2 วัน) หลัง sweep
FVG_FRESH = 20    # FVG ยังใช้งานได้ภายใน 20 แท่ง (≈ 3 วัน) หลังก่อตัว
MOM_BARS = 540    # momentum filter: ผลตอบแทน 90 วัน (540 แท่ง 4h)
CONF_WIN = 6      # confluence: golden ต้องมี SMC ยืนยันเกิดภายใน 6 แท่ง (1 วัน) ก่อนหน้า
MR_RSI_PERIOD = 14   # mean reversion: RSI period
MR_RSI_THRESH = 30   # oversold threshold

RESULTS_DIR = Path("backtest_results")

FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
FUNDING_CACHE = Path("data/funding_cache.json")
CROWD_URL = "https://data.binance.vision/data/futures/um/daily/metrics"
CROWD_CACHE = Path("data/crowd_cache.json")
CROWD_WIN_DAYS = 180  # หน้าต่าง trailing สำหรับคำนวณ percentile ของ long/short ratio
CROWD_COL = "count_long_short_ratio"  # crowd = ผู้ใช้ทั่วไป (ไม่ใช่ top trader)
# หมายเหตุ: live API (fapi /futures/data/*) เก็บแค่ ~30 วัน — ต้องใช้ daily archive
# data.binance.vision (5-min rows ตั้งแต่ 2021) ตามวิธีเดียวกับ btc-strategy-lab

RISK_PER_TRADE = 0.03
MAX_TOTAL_RISK = 0.10
MAX_POSITIONS = 5
MAX_DAY_LOSSES = 3
MAX_TOTAL_DD = -0.20
DD_HALT_SEC = 7 * 86400


def fetch_history(symbol: str, interval: str, start_ts: int, end_ts: int) -> list:
    step = STEP_SEC[interval]
    out = []
    cur = start_ts
    while cur < end_ts:
        url = (f"{BINANCE_KLINE_URL}?symbol={symbol}&interval={interval}"
               f"&startTime={cur * 1000}&limit=1000")
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                raw = json.loads(resp.read().decode())
        except Exception as e:
            print(f"  [{symbol}] fetch error at {cur}: {e}")
            time.sleep(1)
            break
        if not raw:
            break
        parsed = parse_klines(symbol, interval, raw)
        out.extend(parsed)
        last_ts = parsed[-1].ts
        if len(parsed) < 1000 or last_ts <= cur:
            break
        cur = last_ts + step
        time.sleep(0.12)
    candles = [c for c in out if c.ts <= end_ts]
    if candles:
        cache_candles(symbol, interval, candles)
    return candles


def cached_coverage(symbol: str, interval: str, start_ts: int) -> bool:
    cached = load_cached_candles(symbol, interval)
    if not cached:
        return False
    return cached[0].ts <= start_ts and cached[-1].ts > int(time.time()) - 86400


def fetch_funding_history(symbol: str, start_ts: int, end_ts: int) -> list:
    """Funding rate (USDT-M perp) จาก Binance fapi — public API ไม่ต้อง key.
    คืน [(ts, rate), ...] เรียงตามเวลา (ส่วนใหญ่ funding ทุก 8h)."""
    out = []
    cur = start_ts * 1000
    end_ms = end_ts * 1000
    while cur < end_ms:
        url = (f"{FUNDING_URL}?symbol={symbol}&startTime={cur}&limit=1000")
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                raw = json.loads(resp.read().decode())
        except Exception as e:
            print(f"  [{symbol}] funding fetch error at {cur}: {e}")
            time.sleep(1)
            break
        if not raw:
            break
        for r in raw:
            out.append((r["fundingTime"] // 1000, float(r["fundingRate"])))
        last = raw[-1]["fundingTime"]
        if len(raw) < 1000 or last <= cur:
            break
        cur = last + 1
        time.sleep(0.12)
    return out


def load_funding_cache() -> dict:
    if FUNDING_CACHE.exists():
        try:
            return json.loads(FUNDING_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_funding_cache(cache: dict) -> None:
    FUNDING_CACHE.parent.mkdir(parents=True, exist_ok=True)
    FUNDING_CACHE.write_text(json.dumps(cache), encoding="utf-8")


def fetch_crowd_history(symbol: str, start_ts: int, end_ts: int) -> list:
    """Long/short ratio (crowd = count_long_short_ratio) จาก daily metrics archive
    data.binance.vision — 5-min rows ตั้งแต่ 2021 (live API เก็บแค่ ~30 วัน).
    คืน [(ts, ratio), ...] ที่ resample เป็น 4h แล้ว. ดาวน์โหลด zip รายวันแบบขนาน
    (16 workers) — 3 ปี ≈ 1,095 ไฟล์/symbol ใช้เวลาประมาณ 1-2 นาที."""
    import io as _io
    import zipfile as _zip
    from concurrent.futures import ThreadPoolExecutor

    day0 = time.strftime("%Y-%m-%d", time.gmtime(start_ts))
    day1 = time.strftime("%Y-%m-%d", time.gmtime(end_ts))
    days = []
    cur = day0
    while cur <= day1:
        days.append(cur)
        cur = _next_day(cur)

    def _one(day: str):
        url = f"{CROWD_URL}/{symbol}/{symbol}-metrics-{day}.zip"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                z = _zip.ZipFile(_io.BytesIO(resp.read()))
            text = z.open(z.namelist()[0]).read().decode()
        except Exception:
            return None
        lines = text.splitlines()
        if not lines:
            return None
        hdr = lines[0].split(",")
        try:
            ci = hdr.index(CROWD_COL)
        except ValueError:
            return None
        day_rows = []
        for ln in lines[1:]:
            parts = ln.split(",")
            if len(parts) <= ci:
                continue
            try:
                ts = int(time.mktime(time.strptime(parts[0], "%Y-%m-%d %H:%M:%S")))
                val = float(parts[ci])
            except (ValueError, OverflowError):
                continue
            day_rows.append((ts, val))
        return day_rows

    all_rows = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for res in ex.map(_one, days):
            if res:
                all_rows.extend(res)
    if not all_rows:
        print(f"  [{symbol}] ไม่มีข้อมูล {CROWD_COL} ใน archive — ข้ามกรอง")
        return []
    all_rows.sort()
    all_rows = [(ts, v) for ts, v in all_rows if start_ts <= ts <= end_ts]
    # resample เป็น 4h: ใช้ค่า last ของแต่ละแท่ง 4h
    s = pd.Series({ts: v for ts, v in all_rows}).sort_index()
    s.index = pd.to_datetime(s.index, unit="s")
    s4 = s.resample("4h").last().dropna()
    return [(int(ts.timestamp()), float(v)) for ts, v in s4.items()]


def _next_day(day_str: str) -> str:
    import datetime as _dt
    d = _dt.date.fromisoformat(day_str) + _dt.timedelta(days=1)
    return d.isoformat()


def load_crowd_cache() -> dict:
    if CROWD_CACHE.exists():
        try:
            return json.loads(CROWD_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_crowd_cache(cache: dict) -> None:
    CROWD_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CROWD_CACHE.write_text(json.dumps(cache), encoding="utf-8")


def build_crowd_pct(symbol: str, start_ts: int, end_ts: int, pct: float) -> pd.Series:
    """คืน Series(index=ts) ของ percentile rank (0-1) ของ long/short ratio ณ แต่ละจุด
    เทียบกับ trailing window (CROWD_WIN_DAYS). ค่า >= pct หมายถึง crowd long แน่นเกินไป
    → ควรข้าม entry (ตรงกับงานวิจัย: returns ต่ำลงหลัง crowd เข้า long เยอะ).
    คืน None ถ้าไม่มีข้อมูล."""
    cache = load_crowd_cache()
    rows = cache.get(symbol)
    if not rows:
        rows = fetch_crowd_history(symbol, start_ts - CROWD_WIN_DAYS * 86400, end_ts)
        if rows:
            cache[symbol] = rows
            save_crowd_cache(cache)
    if not rows:
        return None
    s = pd.Series({ts: r for ts, r in rows}).sort_index()
    # ข้อมูลจาก archive เป็น 5-min — resample เป็น 4h ก่อน (ตรงกับแท่งของ backtest)
    s.index = pd.to_datetime(s.index, unit="s")
    s = s.resample("4h").last().dropna()
    # percentile rank แบบ rolling: สัดส่วนของค่าที่ <= ค่าปัจจุบัน ในหน้าต่างย้อนหลัง
    def _pct_rank(win: pd.Series) -> float:
        if len(win) < 20:
            return 0.0
        return float((win <= win.iloc[-1]).mean())
    return s.rolling(CROWD_WIN_DAYS * 86400 // (4 * 3600), min_periods=20).apply(
        _pct_rank, raw=False)


def build_funding_avg(symbol: str, start_ts: int, end_ts: int) -> pd.Series:
    """ค่าเฉลี่ย funding 7 วัน (จาก timestamp ย้อนหลัง) index เป็น unix ts ของแท่ง.
    คืน Series(index=ts) หรือ None ถ้าไม่มีข้อมูล (เช่น symbol ไม่อยู่ใน fapi)."""
    cache = load_funding_cache()
    rows = cache.get(symbol)
    if not rows:
        rows = fetch_funding_history(symbol, start_ts - 7 * 86400, end_ts)
        if rows:
            cache[symbol] = rows
            save_funding_cache(cache)
    if not rows:
        return None
    s = pd.Series({ts: r for ts, r in rows}).sort_index()
    # เฉลี่ย rolling 7 วัน ตามเวลาจริง (funding ทุก ~8h) — index เป็น datetime
    s.index = pd.to_datetime(s.index, unit="s")
    return s.rolling("7D", min_periods=3).mean()


def to_frame(candles) -> pd.DataFrame:
    df = pd.DataFrame({
        "o": [c.o for c in candles], "h": [c.h for c in candles],
        "l": [c.l for c in candles], "c": [c.c for c in candles],
        "v": [c.v for c in candles],
    })
    df.index = [c.ts for c in candles]
    return df


def compute_signals(df: pd.DataFrame, tp_golden: float = 2.0,
                   tp_turtle: float = 3.0, require_volume: bool = True):
    """คืน (g_rows, t_rows) สัญญาณของ symbol เดียว

    เงื่อนไข vectorized ให้ตรงกับ signal_engine.detect_* ทุกค่า:
      - golden: cross ภายใน 6 แท่ง + RSI 45-75 + volume >= 1.5x เฉลี่ย 20 แท่งก่อน
      - turtle: close > high สูงสุด 20 แท่งก่อน (Donchian breakout)
      - SL/TP: golden = 2 ATR SL / tp_golden ATR TP, turtle = 2 ATR SL / tp_turtle ATR TP
        (ค่าเริ่มต้น 2/2 และ 2/3 เหมือนใน signal_engine)
      - require_volume=False: ข้ามเงื่อนไข volume spike (ใช้กับสินทรัพย์ที่ไม่มี
        volume จริง เช่น XAUUSD — volume ใน histdata เป็น 0 ตลอด)
    """
    close, high, vol = df["c"], df["h"], df["v"]
    fast = close.rolling(MA_FAST).mean()
    slow = close.rolling(MA_SLOW).mean()
    cross_up = (fast.shift(1) <= slow.shift(1)) & (fast > slow)
    # cross เกิดภายใน 6 แท่งสุดท้าย (mirror loop range(last-CROSS_LOOKBACK, last+1))
    cross_win = cross_up.rolling(CROSS_LOOKBACK + 1, min_periods=1).max().fillna(0) > 0

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1 / RSI_PERIOD, adjust=False, min_periods=RSI_PERIOD).mean()
    al = loss.ewm(alpha=1 / RSI_PERIOD, adjust=False, min_periods=RSI_PERIOD).mean()
    rs = ag / al
    rsi = 100 - 100 / (1 + rs)

    avg_vol = vol.rolling(VOLUME_WINDOW).mean().shift(1)  # เฉลี่ย 20 แท่งก่อนหน้า
    if require_volume:
        spike = (vol >= avg_vol * VOLUME_SPIKE) & (avg_vol > 0)
    else:
        spike = pd.Series(True, index=df.index)

    atr = _atr_series(df)

    warm_g = df.index[MA_SLOW + CROSS_LOOKBACK + 2] if len(df) > MA_SLOW + CROSS_LOOKBACK + 2 else df.index[-1]
    golden_mask = (cross_win & rsi.between(RSI_MIN, RSI_MAX) & spike
                   & (df.index >= warm_g)).fillna(False)
    turtle_high = high.shift(1).rolling(TURTLE_ENTRY).max().fillna(0)
    warm_t = df.index[TURTLE_ENTRY + 1] if len(df) > TURTLE_ENTRY + 1 else df.index[-1]
    turtle_mask = ((close > turtle_high) & (df.index >= warm_t)).fillna(False)

    last_cross = cross_up[cross_up].index  # ตำแหน่ง cross จริง

    g_rows = []
    for ts in df.index[golden_mask]:
        prior = last_cross[last_cross <= ts]
        cb = prior[-1] if len(prior) else ts
        e = close.loc[ts]
        a = atr.loc[ts]
        g_rows.append({"ts": ts, "reason": "golden_cross", "entry": e,
                       "sl": e - 2 * a, "tp1": e + tp_golden * a,
                       "marker": cb, "crossbar": cb})
    t_rows = []
    for ts in df.index[turtle_mask]:
        e = close.loc[ts]
        a = atr.loc[ts]
        t_rows.append({"ts": ts, "reason": "turtle_breakout", "entry": e,
                       "sl": e - 2 * a, "tp1": e + tp_turtle * a,
                       "marker": ts, "crossbar": ts})
    return g_rows, t_rows


def _atr_series(df: pd.DataFrame) -> pd.Series:
    close = df["c"]
    tr = pd.concat([
        df["h"] - df["l"],
        (df["h"] - close.shift(1)).abs(),
        (df["l"] - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()
    return atr.where(atr > 0, close * 0.03)


def compute_smc_rows(df: pd.DataFrame, tp_smc: float = 2.8, mode: str = "bos"):
    """SMC แบบ deterministic (LONG เท่านั้น เหมือน pipeline): liquidity sweep

    กติกา (4h):
      1. liquidity pool = low สุดของ 20 แท่งก่อน (ไม่นับแท่งปัจจุบัน)
      2. sweep = แท่งที่ low ทะลุ pool ลงไป แต่ปิดกลับเหนือ pool (stop-hunt / fakeout)

    mode='bos' (default): รอ BOS ยืนยัน — เข้าที่ close แรกที่เหนือ high สูงสุด
      ของ 20 แท่งก่อน sweep (โครงสร้างหักขึ้น) ภายใน SMC_BOS_WIN แท่ง
    mode='reclaim': เข้าทันทีที่แท่ง reclaim (ปิดกลับเหนือ pool) — เร็ว/ราคาดีกว่า
      แต่ยังไม่มีการยืนยันโครงสร้าง, SL = ใต้ pool ที่โดน sweep (structural)

    เข้าได้ 1 ครั้งต่อ sweep (dedupe ด้วย marker = ts ของ sweep)
    """
    close, high, low = df["c"], df["h"], df["l"]
    atr = _atr_series(df)
    pool = low.shift(1).rolling(SMC_SWING_N).min()
    swept = (low < pool) & (close > pool) & pool.notna()
    rows = []
    for j in list(df.index[swept]):
        jpos = df.index.get_loc(j)
        lo = max(0, jpos - SMC_SWING_N)
        pool_val = float(pool.loc[j])
        if mode == "reclaim":
            # เข้าที่แท่ง reclaim เอง: SL ใต้ pool ที่ถูก sweep (structural)
            e, a = close.iloc[jpos], atr.iloc[jpos]
            sl = min(float(low.iloc[jpos]), pool_val) - 0.05 * a
            if e > sl:
                rows.append({"ts": df.index[jpos], "reason": "smc_reclaim",
                             "entry": e, "sl": sl, "tp1": e + tp_smc * a,
                             "marker": j})
            continue
        # mode='bos': รอ close เหนือ high ของ 20 แท่งก่อน sweep ภายใน BOS_WIN
        target = high.iloc[lo:jpos].max()
        end = min(jpos + 1 + SMC_BOS_WIN, len(df))
        k = jpos + 1
        while k < end and close.iloc[k] <= target:
            k += 1
        while k < end and close.iloc[k] > target:
            e, a = close.iloc[k], atr.iloc[k]
            rows.append({"ts": df.index[k], "reason": "smc_sweep", "entry": e,
                         "sl": e - 2 * a, "tp1": e + tp_smc * a, "marker": j})
            k += 1
    return rows


def compute_meanrev_rows(df: pd.DataFrame, tp_smc: float = 2.8):
    """Mean reversion (RSI oversold bounce) — วิธีคนละขั้วกับ trend-following

    กติกา (4h):
      1. RSI(14) < 30 = oversold (ใน bull regime ใช้ --regime-filter = ซื้อจังหวะตกในเทรนด์ขึ้น)
      2. entry ที่ close ของแท่งที่ RSI กลับขึ้นเหนือ 30 (ยืนยันเด้งแล้ว)
      3. SL -2 ATR | TP +tp_smc ATR (เงินจัดการเดียวกันเพื่อเทียบ entry ล้วน ๆ)
    """
    close = df["c"]
    atr = _atr_series(df)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1 / MR_RSI_PERIOD, adjust=False, min_periods=MR_RSI_PERIOD).mean()
    al = loss.ewm(alpha=1 / MR_RSI_PERIOD, adjust=False, min_periods=MR_RSI_PERIOD).mean()
    rs = ag / al
    rsi = 100 - 100 / (1 + rs)
    oversold = (rsi < MR_RSI_THRESH).fillna(False)
    bounce = oversold & rsi.shift(1).ge(MR_RSI_THRESH).fillna(True)
    rows = []
    for ts in df.index[bounce]:
        e, a = close.loc[ts], atr.loc[ts]
        rows.append({"ts": ts, "reason": "mean_rev", "entry": e,
                     "sl": e - 2 * a, "tp1": e + tp_smc * a, "marker": ts})
    return rows


def compute_htf_bias(df: pd.DataFrame, daily_ma: int = 20) -> pd.Series:
    """Higher-timeframe (1D) trend bias: daily close > MA(daily_ma) วัน.
    ใช้แทน/เสริม regime filter 4h — แนวคิดเดียวกับ HTF bias ในงานวิจัย SMC
    (กรองด้วยเทรนด์ใหญ่ก่อนเข้าตามเทรนด์เล็ก) คืน Series index เป็น unix ts
    เดียวกับ df เพื่อให้ regime[s].loc[ts] ใช้ได้"""
    dfi = df.copy()
    dfi.index = pd.to_datetime(dfi.index, unit="s")
    daily = dfi["c"].resample("1D").last().dropna()
    dma = daily.rolling(daily_ma).mean()
    daily_bias = (daily > dma).fillna(False)
    # map กลับ: bias ของวัน = ค่าล่าสุด ณ เวลานั้น (shift ให้ใช้ข้อมูลที่ปิดแล้วเท่านั้น)
    day_vals = pd.to_datetime((df.index // 86400) * 86400, unit="s")
    day_start = pd.Series(day_vals, index=df.index)
    mapped = daily_bias.reindex(day_vals.unique()).ffill()
    out = day_start.map(mapped).astype(bool)
    out.index = df.index
    return out


def compute_squeeze_state(df: pd.DataFrame, bb_period: int = 20, bb_k: float = 2.0,
                          sqz_win: int = 60, sqz_recent: int = 6,
                          brk: int = 20, expand: int = 20) -> pd.Series:
    """Volatility squeeze -> breakout (regime state เสริมสำหรับจับต้นเทรนด์)

    แนวคิดจาก Zeiierman/BB-squeeze framework: ก่อนเทรนด์ใหญ่เริ่ม มักมีช่วง
    แรงอัด volatility (Bollinger bandwidth หด) แล้วราคาทะลุออกพร้อมวอลุ่ม/ATR ขยาย

    กติกา (vectorized, ใช้ข้อมูลย้อนหลังเท่านั้น ไม่มี lookahead):
      1. bandwidth = (upper - lower) / middle ของ Bollinger(bb_period, bb_k sigma)
         squeeze = bandwidth ต่ำกว่าค่าเฉลี่ย rolling sqz_win แท่งของตัวเอง
      2. breakout = close > high สูงสุด brk แท่งก่อนหน้า (Donchian-style)
      3. expansion = ATR(14) > ค่าเฉลี่ย rolling expand แท่ง (แรงเริ่มระเบิดจริง)
      state = มี squeeze เกิดภายใน sqz_recent แท่งก่อน แล้วเพิ่ง breakout+expansion

    คืน boolean Series (index = unix ts เดียวกับ df) ให้ regime[s].loc[ts] ใช้ได้
    """
    close, high = df["c"], df["h"]
    mid = close.rolling(bb_period).mean()
    sd = close.rolling(bb_period).std(ddof=0)
    up, lo = mid + bb_k * sd, mid - bb_k * sd
    bw = ((up - lo) / mid).replace([float("inf"), float("-inf")], float("nan"))
    bw_avg = bw.rolling(sqz_win, min_periods=sqz_win).mean()
    squeeze = (bw < bw_avg).fillna(False)
    sqz_recently = squeeze.rolling(sqz_recent, min_periods=1).max().astype(bool)
    prior_high = high.shift(1).rolling(brk).max()
    breakout = close > prior_high
    atr = _atr_series(df)
    atr_avg = atr.rolling(expand).mean()
    expansion = atr > atr_avg
    return (sqz_recently & breakout & expansion).fillna(False)


def compute_squeeze_window(df: pd.DataFrame, event_win: int = 6) -> pd.Series:
    """Expansion window: True เมื่อมี squeeze->breakout เกิดภายใน event_win แท่งก่อน
    (รวมแท่งปัจจุบัน) — ใช้เป็น entry confluence: golden cross ที่เกิดระหว่างแรง
    ระเบิดออกจากแรงอัด (ยังอยู่ภายใต้ bull gate ถ้า --regime-filter on)"""
    ev = compute_squeeze_state(df)
    return ev.rolling(event_win, min_periods=1).max().astype(bool).fillna(False)


def compute_fvg_rows(df: pd.DataFrame, tp_smc: float = 2.8):
    """FVG (fair value gap) continuation — ชิ้นส่วน SMC ที่งานวิจัยบอกว่ามีหลักฐานดีสุด

    กติกา (4h):
      1. Bullish FVG = แท่ง i มี low > high ของแท่ง i-2 (gap ขึ้น) — โซน = [high[i-2], low[i]]
      2. ภายใน FVG_FRESH แท่งถัดมา ราคาย่อลงมาแตะโซน (pullback เข้า imbalance)
      3. entry ที่ close ของแท่งแรกที่ปิดอยู่ในโซน | SL ใต้โซน - 0.3 ATR | TP +tp_smc ATR
      4. เข้าได้ 1 ครั้งต่อ FVG (dedupe ด้วย marker = ts ที่ FVG ก่อตัว)
    """
    close, high, low = df["c"], df["h"], df["l"]
    atr = _atr_series(df)
    n = len(df)
    rows = []
    for i in range(2, n):
        if low.iloc[i] <= high.iloc[i - 2]:
            continue  # ไม่เกิด bullish gap
        zone_lo, zone_hi = high.iloc[i - 2], low.iloc[i]
        end = min(i + 1 + FVG_FRESH, n)
        for k in range(i + 1, end):
            c = close.iloc[k]
            if zone_lo <= c <= zone_hi:  # ราคาย่อเข้าโซนแล้ว
                a = atr.iloc[k]
                sl = zone_lo - 0.3 * a
                if c > sl:
                    rows.append({"ts": df.index[k], "reason": "smc_fvg",
                                 "entry": c, "sl": sl, "tp1": c + tp_smc * a,
                                 "marker": df.index[i]})
                break  # 1 ครั้งต่อ FVG
    return rows


def run_rotation(frames: dict, args, sim_start: int, end_ts: int) -> None:
    """Cross-sectional momentum rotation: ทุก rot_hold วัน ถือ Top rot_top เหรียญ
    ตาม momentum rot_lookback วัน แบบ equal-weight มี fee+slippage ทุกครั้งที่ซื้อ/ขาย
    ต่างจากกลยุทธ์อื่นตรงที่เป็น periodic rebalance ไม่ใช่ event-driven signal."""
    look = args.rot_lookback * 6  # แท่ง 4h
    cash = args.equity
    holdings = {}
    fees_total = 0.0
    all_ts = sorted(set().union(*[set(df.index) for df in frames.values()]))
    bar_idx = {s: df.index for s, df in frames.items()}

    def bar(symbol, ts):
        idx = bar_idx[symbol]
        i = bisect.bisect_right(idx, ts) - 1
        return i if i >= 0 and idx[i] == ts else None

    def mom(symbol, ts):
        i = bar(symbol, ts)
        if i is None or i < look:
            return None
        return frames[symbol]["c"].iloc[i] / frames[symbol]["c"].iloc[i - look] - 1.0

    # รีบาลานซ์เฉพาะวันที่ rot_hold (นับจาก sim_start)
    rebal_days = set()
    t0 = sim_start
    while t0 <= end_ts:
        rebal_days.add(t0)
        t0 += args.rot_hold * 86400

    curve = []
    peak_eq = args.equity
    halt_until = 0
    prev_ratio = 0.0
    for ts in all_ts:
        if ts < sim_start:
            continue
        # มูลค่าพอร์ต (ถือแบบ mark-to-market)
        eq = cash
        for sym, sh in holdings.items():
            i = bar(sym, ts)
            px = frames[sym]["c"].iloc[i] if i is not None else sh["entry"]
            eq += sh["size"] * (px / sh["entry"])
        curve.append((ts, eq))
        peak_eq = max(peak_eq, eq)
        ratio = eq / peak_eq - 1
        if ratio <= MAX_TOTAL_DD and prev_ratio > MAX_TOTAL_DD and ts >= halt_until:
            halt_until = ts + DD_HALT_SEC
        prev_ratio = ratio
        if ts not in rebal_days or ts < halt_until:
            continue

        # อันดับ momentum ณ วันนี้ → ขายทุกอย่างที่ถือ เก็บเงินสด
        mvals = {s: mom(s, ts) for s in frames}
        ranked = sorted((s for s, v in mvals.items() if v is not None),
                        key=lambda s: mvals[s], reverse=True)
        if len(ranked) < 2:
            continue
        target = ranked[: args.rot_top]
        # ขายของเดิมก่อน
        for sym in list(holdings.keys()):
            sh = holdings.pop(sym)
            i = bar(sym, ts)
            px = frames[sym]["c"].iloc[i] if i is not None else sh["entry"]
            fill = px * (1 - SLIPPAGE)
            cash += sh["size"] * (fill / sh["entry"])
            fees_total += sh["size"] * FEE_RATE
        # ซื้อ Top N ใหม่ equal-weight
        per = cash / len(target)
        for sym in target:
            i = bar(sym, ts)
            if i is None:
                continue
            fill = frames[sym]["c"].iloc[i] * (1 + SLIPPAGE)
            size = per
            f = size * FEE_RATE
            if size + f > cash:
                size = max(cash - f, 0.0)
            if size <= 5:
                continue
            cash -= size + f
            fees_total += f
            holdings[sym] = {"symbol": sym, "entry": fill, "size": size,
                             "open_ts": ts, "fee": f}

    # mark-to-market สุดท้าย
    final_eq = cash
    for sym, sh in holdings.items():
        i = bar(sym, end_ts)
        px = frames[sym]["c"].iloc[i] if i is not None else sh["entry"]
        final_eq += sh["size"] * (px / sh["entry"])

    curve_s = pd.Series([e for _, e in curve],
                        index=pd.to_datetime([t for t, _ in curve], unit="s"))
    daily = curve_s.resample("1D").last().dropna()
    total_ret = final_eq / args.equity - 1
    span_days = max(1.0, (end_ts - sim_start) / 86400)
    cagr = ((final_eq / args.equity) ** (365.25 / span_days) - 1) if final_eq > 0 else -1.0
    max_dd = float((daily / daily.cummax() - 1).min()) if len(daily) > 1 else 0.0
    rets = daily.pct_change().dropna()
    sharpe = (rets.mean() / rets.std() * math.sqrt(365)) if rets.std() > 0 and len(rets) > 5 else 0.0

    btc = frames.get("BTCUSDT")
    btc_ret = 0.0
    if btc is not None:
        sub = btc.loc[sim_start:]
        if len(sub) > 10:
            btc_ret = sub["c"].iloc[-1] / sub["c"].iloc[0] - 1

    L = []
    L.append("=" * 74)
    L.append(f"BACKTEST cross-sectional momentum rotation | {args.days} วัน | 4h")
    L.append(f"ถือ Top {args.rot_top} (momentum {args.rot_lookback}d) equal-weight, "
             f"รีบาลานซ์ทุก {args.rot_hold} วัน | fee {FEE_RATE:.1%}+slippage {SLIPPAGE:.2%}")
    L.append("=" * 74)
    L.append(f"ผลตอบแทนรวม      : {total_ret:+.2%}")
    L.append(f"CAGR              : {cagr:+.2%}")
    L.append(f"Equity สุดท้าย    : {final_eq:,.2f} USDT")
    L.append(f"Max Drawdown      : {max_dd:.2%}")
    L.append(f"Sharpe (รายวัน)   : {sharpe:.2f}")
    L.append(f"fees รวม          : {fees_total:,.2f} USDT")
    L.append(f"BTC buy&hold      : {btc_ret:+.2%}")
    L.append(f"Alpha vs BTC      : {total_ret - btc_ret:+.2%}")
    print("\n".join(L))

    name = RESULTS_DIR / f"backtest_result_{args.days}d_rot{args.rot_top}_{args.rot_hold}d.json"
    with open(name, "w", encoding="utf-8") as f:
        json.dump({"days": args.days, "symbols": len(frames),
                   "equity_start": args.equity, "total_return": total_ret,
                   "cagr": cagr, "final_equity": final_eq, "max_dd": max_dd,
                   "sharpe": sharpe, "fees": fees_total, "btc_return": btc_ret,
                   "alpha": total_ret - btc_ret, "trades": []}, f,
                  ensure_ascii=False, indent=2)
    print(f"\nบันทึกผล: {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=730, help="ย้อนหลังกี่วัน (730=2ปี, 1095=3ปี)")
    ap.add_argument("--equity", type=float, default=50_000.0)
    ap.add_argument("--symbols", type=int, default=30)
    ap.add_argument("--symbol-list", type=str, default="",
                    help="รันกับ symbol ที่ระบุเอง (คั่น ,) แทน top-30 — ใช้กับข้อมูลนอก Binance เช่น XAUUSD")
    ap.add_argument("--no-fetch", action="store_true",
                    help="ไม่ fetch จาก network — ใช้เฉพาะข้อมูลที่ cache ไว้แล้ว (สำหรับ symbol นอก Binance)")
    ap.add_argument("--no-volume", action="store_true",
                    help="ปิดเงื่อนไข volume spike ใน golden (สินทรัพย์ที่ไม่มี volume เช่น XAUUSD)")
    ap.add_argument("--interval", choices=["4h", "1h"], default="4h",
                    help="timeframe ของสัญญาณ (default 4h; 1h ใช้กับ mean-reversion)")
    ap.add_argument("--mr1h", action="store_true",
                    help="ทางลัด: mean reversion บน 1h (interval=1h + meanrev + HTF bias)")
    ap.add_argument("--no-daily-gate", action="store_true",
                    help="research: พิจารณา entry ทุกแท่ง ไม่จำกัดวันละครั้ง (เผื่อ 1h MR ต้องเข้าเร็ว)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--golden-only", action="store_true",
                       help="ใช้เฉพาะ golden cross (ปิด turtle breakout)")
    group.add_argument("--smc-only", action="store_true",
                       help="ใช้เฉพาะ SMC sweep+BOS (ปิด golden และ turtle)")
    ap.add_argument("--regime-filter", action="store_true",
                    help="กรองเฉพาะ bull regime (เหมือน governor rule-based)")
    ap.add_argument("--regime-mode", choices=["bull", "squeeze", "or"], default="bull",
                    help="ประเภท regime gate (ใช้คู่กับ --regime-filter): bull=เดิม "
                         "(MA20>MA50+slope), squeeze=volatility squeeze->breakout อย่างเดียว, "
                         "or=bull OR squeeze->breakout (regime state เสริม)")
    ap.add_argument("--squeeze-entry", action="store_true",
                    help="entry confluence: golden cross เข้าได้เฉพาะเมื่อเกิดในหน้าต่าง "
                         "squeeze->breakout (volatility expansion 6 แท่ง) — bull gate ยังกรองปกติ")
    ap.add_argument("--tp-golden", type=float, default=2.0,
                    help="TP ของ golden cross เป็นกี่เท่า ATR (default 2.0 = R:R 1:1)")
    ap.add_argument("--tp-turtle", type=float, default=3.0,
                    help="TP ของ turtle เป็นกี่เท่า ATR (default 3.0)")
    ap.add_argument("--tp-smc", type=float, default=2.8,
                    help="TP ของ SMC เป็นกี่เท่า ATR (default 2.8 = R:R 1:1.4)")
    ap.add_argument("--smc-mode", choices=["bos", "reclaim"], default="bos",
                    help="รูปแบบ SMC: bos=รอทะลุโครงสร้าง, reclaim=เข้าที่แท่งดีดกลับ")
    ap.add_argument("--fvg", action="store_true",
                    help="ใช้ FVG continuation แทน SMC sweep (โหมด smc-only)")
    ap.add_argument("--meanrev", action="store_true",
                    help="ใช้ mean reversion (RSI oversold bounce) แทน golden — วิธีคนละขั้ว")
    ap.add_argument("--htf-bias", action="store_true",
                    help="กรองด้วยเทรนด์ใหญ่รายวัน (1D close > MA20) แทน regime filter 4h")
    ap.add_argument("--confluence", choices=["none", "sweep", "fvg"], default="none",
                    help="จังหวะสมบูรณ์แบบ: golden ต้องมี SMC ยืนยัน (sweep+BOS หรือ FVG) "
                         "เกิดภายใน CONF_WIN แท่งก่อนหน้า ไม่งั้นไม่เข้า")
    ap.add_argument("--boost", type=float, default=1.0,
                    help="เพิ่ม size ของไม้ที่ผ่าน confluence: risk/เทรด = 3% x boost (1.5 = 4.5%)")
    ap.add_argument("--boost-only", action="store_true",
                    help="ไม่กรองเทรดออก แต่เพิ่ม size เฉพาะไม้ที่ผ่าน confluence "
                         "(ไม้ที่ไม่ผ่านยังเข้าได้ที่ risk ปกติ)")
    ap.add_argument("--momentum-top", type=int, default=0,
                    help="relative-strength: เข้าได้เฉพาะเหรียญที่ momentum 90 วันติด Top N (0=ปิด)")
    ap.add_argument("--rotation", action="store_true",
                    help="cross-sectional momentum rotation: ถือ Top N เหรียญ (90d) แบบ equal-weight รีบาลานซ์ทุกเดือน")
    ap.add_argument("--rot-top", type=int, default=5,
                    help="จำนวนเหรียญที่ถือใน rotation (default 5)")
    ap.add_argument("--rot-hold", type=int, default=30,
                    help="รีบาลานซ์ทุกกี่วัน (default 30)")
    ap.add_argument("--rot-lookback", type=int, default=90,
                    help="ใช้ momentum กี่วันในการจัดอันดับ (default 90)")
    ap.add_argument("--partial-tp", type=float, default=0.0,
                    help="ปิดบางส่วนที่ TP1 (fraction เช่น 0.5 = ปิดครึ่ง) แล้วปล่อยส่วนเหลือตาม trailing")
    ap.add_argument("--trail-atr", type=float, default=2.0,
                    help="trailing stop ระยะกี่ ATR จาก high สุด (default 2.0)")
    ap.add_argument("--tp2-atr", type=float, default=0.0,
                    help="ถ้า >0: ส่วนที่เหลือหลัง partial TP1 จะปิดที่ TP2 = entry + tp2_atr*ATR แทน trailing")
    ap.add_argument("--funding-max", type=float, default=0.0,
                    help="กรอง funding: ข้ามเทรดถ้า funding เฉลี่ย 7 วัน > ค่านี้ (เช่น 0.0005 = 0.05%)")
    ap.add_argument("--funding-min", type=float, default=0.0,
                    help="กรอง funding (ตรงข้าม): เทรดเฉพาะเมื่อ funding เฉลี่ย 7 วัน > ค่านี้ (momentum ยืนยัน)")
    ap.add_argument("--crowd-pct", type=float, default=0.0,
                    help="กรอง crowd: ข้ามเทรดถ้า long/short ratio อยู่ percentile >= ค่านี้ "
                         "ของ trailing 180 วัน (เช่น 0.8 = ข้ามเมื่อ crowd long แน่นสุด 20%)")
    ap.add_argument("--end-date", type=str, default="",
                    help="walk-forward: สิ้นสุด backtest ที่วันนี้ (YYYY-MM-DD) แทน 'ตอนนี้' "
                         "— ใช้รัน train/test บนช่วงประวัติศาสตร์โดยเฉพาะ")
    ap.add_argument("--fee-rate", type=float, default=0.001,
                    help="fee ต่อ side (default 0.1% เหมือน Binance spot) — สำหรับ CFD/สินทรัพย์อื่น "
                         "เช่น ทอง spread จริง ~0.3$/oz ≈ 0.005-0.01% ต่อ side")
    ap.add_argument("--slippage", type=float, default=0.0005,
                    help="slippage ต่อ side (default 0.05% เหมือน Binance spot) — CFD บางเจ้าต่ำกว่านี้มาก")
    args = ap.parse_args()

    # fee/slippage แบบกำหนดเอง: ใช้ local แทน constant จาก pipeline (ไม่แตะ execution)
    FEE = args.fee_rate
    SLIP = args.slippage

    if args.mr1h:
        args.interval = "1h"
        args.meanrev = True
        args.htf_bias = True
    interval = args.interval
    step = STEP_SEC[interval]
    daily_bar_hour = (24 - step // 3600) * 3600  # แท่งที่ปิดตอนเที่ยงคืน (4h: 20:00, 1h: 23:00)
    # end_ts = open time ของแท่ง 4h ล่าสุดที่ปิดแล้ว (quantize ให้ deterministic
    # ไม่ว่าวิ่งกี่โมง: แท่งล่าสุดที่ปิด = floor(now/step)*step - step)
    now_ts = int(time.time())
    if args.end_date:
        import datetime as _dt
        d = _dt.date.fromisoformat(args.end_date)
        end_dt = _dt.datetime(d.year, d.month, d.day, tzinfo=_dt.timezone.utc)
        end_ts = int(end_dt.timestamp())
        # quantize ลงเป็นแท่งที่ปิดแล้ว (ไม่ใช้แท่งที่ยังไม่จบ)
        end_ts = (end_ts // step) * step - step
    else:
        end_ts = (now_ts // step) * step - step
    buffer_days = 20
    start_ts = end_ts - (args.days + buffer_days) * 86400
    sim_start = end_ts - args.days * 86400

    if args.symbol_list:
        symbols = [s.strip() for s in args.symbol_list.split(",") if s.strip()]
    else:
        symbols = FALLBACK_TOP30[: args.symbols]
    min_bars = int(args.days * 86400 / step * 0.6)
    print(f"Load 4h data: {args.days} วัน ({len(symbols)} symbols)...")
    frames = {}
    for s in symbols:
        if not args.no_fetch and not cached_coverage(s, interval, start_ts):
            fetch_history(s, interval, start_ts, end_ts)
        c = [x for x in load_cached_candles(s, interval)
             if start_ts <= x.ts <= end_ts]
        if len(c) < min_bars:
            print(f"  skip {s}: only {len(c)} bars")
            continue
        frames[s] = to_frame(c)
        print(f"  {s}: {len(c)} bars")
    print(f"Symbols in backtest: {len(frames)}")
    if not frames:
        print("ไม่มี symbol ใดมีข้อมูลพอ — ลองลด --days หรือเพิ่ม --symbols")
        return

    if args.rotation:
        run_rotation(frames, args, sim_start, end_ts)
        return

    sigs = {}
    regime = {}
    momentum = {}
    sqz_entry = {}
    conf_events_ts = {}   # ts ของเหตุการณ์ SMC ยืนยัน ต่อ symbol (สำหรับ confluence)
    for s, df in frames.items():
        g_rows, t_rows = compute_signals(df, args.tp_golden, args.tp_turtle,
                                         require_volume=not args.no_volume)
        if args.meanrev:
            s_rows = compute_meanrev_rows(df, args.tp_smc)
        elif args.fvg:
            s_rows = compute_fvg_rows(df, args.tp_smc)
        else:
            s_rows = compute_smc_rows(df, args.tp_smc, args.smc_mode)
        if args.golden_only:
            t_rows = []
            s_rows = []
        elif args.smc_only or args.fvg or args.meanrev:
            g_rows = []
            t_rows = []
        sigs[s] = (g_rows, t_rows, s_rows)
        if args.confluence != "none":
            # เหตุการณ์ยืนยันสำหรับกรอง golden (อิสระจาก strategy ที่เลือก)
            if args.confluence == "sweep":
                ev_rows = compute_smc_rows(df, args.tp_smc, "bos")
            else:
                ev_rows = compute_fvg_rows(df, args.tp_smc)
            conf_events_ts[s] = sorted(r["ts"] for r in ev_rows)
        if args.momentum_top > 0:
            mom_bars = 90 * 86400 // step  # momentum 90 วันในหน่วยแท่งของ interval นี้
            momentum[s] = df["c"] / df["c"].shift(mom_bars) - 1.0
        if args.htf_bias:
            regime[s] = compute_htf_bias(df)
        elif args.regime_filter:
            f20 = df["c"].rolling(20).mean()
            f50 = df["c"].rolling(50).mean()
            slope = f20 - f20.shift(10)
            spread = (f20 - f50) / f50
            bull = (slope > 0) & (spread > 0.01)
            if args.regime_mode == "squeeze":
                # ทดสอบ: ใช้ squeeze->breakout state แทน bull อย่างเดียว
                regime[s] = compute_squeeze_state(df)
            elif args.regime_mode == "or":
                # เสริม: bull เดิม OR squeeze->breakout (จับต้นเทรนด์ที่นอก bull)
                regime[s] = bull | compute_squeeze_state(df)
            else:
                regime[s] = bull
        else:
            regime[s] = None
        if args.squeeze_entry:
            sqz_entry[s] = compute_squeeze_window(df)
        else:
            sqz_entry[s] = None

    cand_atr = {s: _atr_series(df) for s, df in frames.items()}
    funding_avg = {}
    if args.funding_max > 0 or args.funding_min > 0:
        print("Fetch funding history (fapi, public)...")
        for s in frames:
            funding_avg[s] = build_funding_avg(s, start_ts, end_ts)
            if funding_avg[s] is None:
                print(f"  [{s}] ไม่มี funding data — ข้ามกรอง symbol นี้")

    crowd_pct = {}
    if args.crowd_pct > 0:
        print(f"Fetch long/short ratio (fapi, public, {CROWD_WIN_DAYS}d trailing)...")
        for s in frames:
            crowd_pct[s] = build_crowd_pct(s, start_ts, end_ts, args.crowd_pct)
            if crowd_pct[s] is None:
                print(f"  [{s}] ไม่มี crowd data — ข้ามกรอง symbol นี้")

    all_ts = sorted(set().union(*[set(df.index) for df in frames.values()]))
    bar_idx = {s: df.index for s, df in frames.items()}

    def bar(symbol, ts):
        idx = bar_idx[symbol]
        i = bisect.bisect_right(idx, ts) - 1
        return i if i >= 0 and idx[i] == ts else None

    cash = args.equity
    positions = {}
    closed = []
    last_crossbar = {}
    last_sweepbar = {}
    day_losses = 0
    last_day = None
    last_entry_day = None  # daily cycle: พิจารณา entry ใหม่ 1 ครั้ง/วัน
    peak_eq = args.equity
    prev_ratio = 0.0
    halt_until = 0  # ข้าม -20% จาก peak ครั้งใหม่ = หยุดเข้าเทรดใหม่ 1 สัปดาห์พอดี
    fees_total = 0.0

    def equity_mtm(ts):
        eq = cash
        for p in positions.values():
            i = bar(p["symbol"], ts)
            px = frames[p["symbol"]]["c"].iloc[i] if i is not None else p["entry"]
            eq += p["size"] * (px / p["entry"])
        return eq

    def close_pos(symbol, ts, trigger, reason, frac=1.0):
        """ปิด frac ของ position (default ทั้งหมด) — บันทึกการปิดเป็นรายการใน closed.
        ถ้ายังเหลือส่วนที่ยังไม่ปิด จะลด size ใน positions ลงและเก็บไว้ต่อ."""
        nonlocal cash, fees_total, day_losses
        p = positions[symbol]
        fill = trigger * (1 - SLIP)
        sz = p["size"] * frac
        f_close = sz * FEE
        cash += sz * (fill / p["entry"]) - f_close
        fees_total += f_close
        pnl = sz * (fill - p["entry"]) / p["entry"] - p["fee"] * frac - f_close
        rec = dict(p)
        rec["exit_ts"], rec["exit"], rec["pnl"], rec["exit_reason"] = ts, fill, pnl, reason
        rec["hold_bars"] = (ts - p["open_ts"]) // step
        rec["size"] = sz
        rec["frac"] = frac
        closed.append(rec)
        if pnl < 0:
            day_losses += 1
        p["size"] -= sz
        p["fee"] -= p["fee"] * frac
        if p["size"] <= 1e-9:
            positions.pop(symbol)

    curve = []
    opened = 0
    blocked = {"positions": 0, "cash": 0, "dd_halt": 0, "day_halt": 0,
               "regime": 0, "dup_cross": 0, "momentum": 0, "confluence": 0,
               "no_sig_slot": 0, "funding": 0, "crowd": 0, "sqz_entry": 0}

    for ts in all_ts:
        if ts < sim_start:
            continue
        day = ts // 86400
        if day != last_day:
            last_day = day
            day_losses = 0

        # 1) จัดการ position ที่เปิดอยู่ (SL ก่อน TP ถ้าแตะทั้งคู่ในแท่งเดียว)
        for sym in list(positions.keys()):
            i = bar(sym, ts)
            if i is None:
                continue
            row = frames[sym].iloc[i]
            p = positions[sym]
            if p.get("tp1_filled"):
                # โหมดหลัง partial TP1: TP2 ตาม ATR หรือ trailing stop
                if args.tp2_atr > 0:
                    if row["l"] <= p["sl"]:
                        close_pos(sym, ts, p["sl"], "sl", 1.0)
                    elif row["h"] >= p["tp2"]:
                        close_pos(sym, ts, p["tp2"], "tp2", 1.0)
                    continue
                p["trail_hi"] = max(p["trail_hi"], row["h"])
                trail = max(p["entry"], p["trail_hi"] - args.trail_atr * p["atr_ref"])
                p["sl"] = max(p["sl"], trail)  # ratchet ขึ้นเท่านั้น
                if row["l"] <= p["sl"]:
                    close_pos(sym, ts, p["sl"], "trail", 1.0)
                continue
            if row["l"] <= p["sl"]:
                close_pos(sym, ts, p["sl"], "sl", 1.0)
            elif row["h"] >= p["tp1"]:
                if args.partial_tp > 0:
                    close_pos(sym, ts, p["tp1"], "tp1_part", args.partial_tp)
                    if sym in positions:  # ยังเหลือส่วนที่ยังไม่ปิด
                        p = positions[sym]
                        p["tp1_filled"] = True
                        p["trail_hi"] = row["h"]
                        if args.tp2_atr > 0:
                            p["tp2"] = p["entry"] + args.tp2_atr * p["atr_ref"]
                        # ยก SL ขึ้นเป็น breakeven (เผื่อ fee 0.1%) ให้ส่วนที่เหลือ
                        p["sl"] = max(p["sl"], p["entry"] * 1.001)
                else:
                    close_pos(sym, ts, p["tp1"], "tp1", 1.0)

        # 2) equity + circuit breaker: ข้ามลงไปต่ำกว่า -20% ของ peak ครั้งใหม่
        #    = หยุดเปิดเทรดใหม่ 1 สัปดาห์ (ตาม risk budget) แล้วค่อยกลับมาเทรดได้
        eq_now = equity_mtm(ts)
        curve.append((ts, eq_now))
        peak_eq = max(peak_eq, eq_now)
        ratio = eq_now / peak_eq - 1
        if ratio <= MAX_TOTAL_DD and prev_ratio > MAX_TOTAL_DD and ts >= halt_until:
            halt_until = ts + DD_HALT_SEC
        prev_ratio = ratio

        # 3) สัญญาณใหม่: daily cycle พิจารณา 1 ครั้ง/วัน (spec: รอบหลัก 01:00 UTC
        #    หลังปิด 1D -> แท่งที่ปิดตอนเที่ยงคืน: 4h เปิด 20:00 UTC / 1h เปิด 23:00 UTC)
        #    --no-daily-gate (research): เข้าได้ทุกแท่งที่สัญญาณเกิด (ใช้กับ MR 1h)
        is_daily_bar = (ts % 86400 == daily_bar_hour)
        if not is_daily_bar and not args.no_daily_gate:
            continue
        if ts < halt_until:
            if is_daily_bar and ts < halt_until:
                blocked["dd_halt"] += 1
            continue

        def top_momentum_syms(at_ts):
            """เหรียญที่ momentum 90 วันสูงสุด Top N ณ เวลา at_ts (relative-strength)"""
            vals = {}
            for s2, m in momentum.items():
                idx2 = bar_idx[s2]
                i2 = bisect.bisect_right(idx2, at_ts) - 1
                if i2 >= 0:
                    v = m.iloc[i2]
                    if pd.notna(v):
                        vals[s2] = v
            ranked = sorted(vals, key=vals.get, reverse=True)
            return set(ranked[: args.momentum_top])

        for sym, (g_rows, t_rows, s_rows) in sigs.items():
            if sym in positions:
                continue
            # หา signal ที่ ts นี้ก่อน (ลำดับ: golden → turtle → smc)
            cand = None
            for g in g_rows:  # golden ก่อน (ลำดับเดียวกับ generate_signals)
                if g["ts"] == ts:
                    if last_crossbar.get(sym) == g["crossbar"]:
                        blocked["dup_cross"] += 1
                        break
                    cand = g
                    break
            if cand is None:
                for t in t_rows:
                    if t["ts"] == ts:
                        cand = t
                        break
            if cand is None:
                for sm in s_rows:  # smc: เข้าได้ 1 ครั้งต่อ sweep event
                    if sm["ts"] == ts:
                        if last_sweepbar.get(sym) == sm["marker"]:
                            blocked["dup_cross"] += 1
                            break
                        cand = sm
                        break
            if cand is None:
                continue

            # confluence: จังหวะสมบูรณ์แบบ = golden ต้องมี SMC ยืนยันเพิ่งเกิด
            boost = 1.0
            if args.confluence != "none" and cand["reason"] == "golden_cross":
                ets = conf_events_ts.get(sym, [])
                i2 = bisect.bisect_right(ets, ts) - 1
                conf_ok = (i2 >= 0 and ets[i2] >= ts - CONF_WIN * 14400)
                if args.boost_only:
                    # ไม่กรอง: ไม้ที่ผ่าน confluence ได้ size ใหญ่ขึ้น
                    if conf_ok:
                        boost = args.boost
                else:
                    if not conf_ok:
                        blocked["confluence"] += 1
                        continue
                    boost = args.boost
            risk_used = RISK_PER_TRADE * boost

            if ts < halt_until:
                blocked["dd_halt"] += 1
                continue
            if len(positions) >= MAX_POSITIONS or \
               len(positions) * RISK_PER_TRADE + risk_used > MAX_TOTAL_RISK:
                blocked["positions"] += 1
                continue
            if day_losses >= MAX_DAY_LOSSES:
                blocked["day_halt"] += 1
                continue
            if regime[sym] is not None and not bool(regime[sym].loc[ts]):
                blocked["regime"] += 1
                continue
            if sqz_entry[sym] is not None and not bool(sqz_entry[sym].loc[ts]):
                blocked["sqz_entry"] += 1
                continue
            if args.momentum_top > 0:
                # relative strength: ต้องติด Top N ของ momentum 90 วัน ณ วันนั้น
                top = top_momentum_syms(ts)
                if sym not in top:
                    blocked["momentum"] += 1
                    continue

            if (args.funding_max > 0 or args.funding_min > 0) and funding_avg is not None:
                fa = funding_avg[sym]
                if fa is not None:
                    val = fa.asof(pd.to_datetime(ts, unit="s"))  # ค่าเฉลี่ย 7 วัน ณ เวลาล่าสุดก่อน ts
                    if val is not None and not pd.isna(val):
                        if args.funding_max > 0 and val > args.funding_max:
                            blocked["funding"] += 1
                            continue
                        if args.funding_min > 0 and val < args.funding_min:
                            blocked["funding"] += 1
                            continue

            if args.crowd_pct > 0 and crowd_pct is not None:
                cp = crowd_pct[sym]
                if cp is not None:
                    val = cp.asof(pd.to_datetime(ts, unit="s"))
                    if val is not None and not pd.isna(val) and val >= args.crowd_pct:
                        blocked["crowd"] += 1
                        continue

            entry = cand["entry"]
            if entry <= cand["sl"]:
                continue
            risk_amount = eq_now * risk_used
            raw_size = risk_amount * entry / (entry - cand["sl"])
            size = min(raw_size, max(cash - 1.0, 0.0))
            f_open = size * FEE
            if size + f_open > cash:
                size = max(cash - f_open, 0.0)
            if size <= 5:
                blocked["cash"] += 1
                continue
            cash -= size + f_open
            fees_total += f_open
            positions[sym] = {
                "symbol": sym, "entry": entry * (1 + SLIP), "size": size,
                "sl": cand["sl"], "tp1": cand["tp1"], "reason": cand["reason"],
                "open_ts": ts, "fee": f_open, "risk_used": risk_used,
                "atr_ref": cand_atr[sym].at[ts] if cand_atr[sym] is not None else 0.0,
            }
            if cand["reason"] == "golden_cross":
                last_crossbar[sym] = cand["crossbar"]
            elif cand["reason"] == "smc_sweep":
                last_sweepbar[sym] = cand["marker"]
            opened += 1

    # ปิด position ค้างที่ราคาสุดท้าย
    final_ts = all_ts[-1]
    for sym in list(positions.keys()):
        i = bar(sym, final_ts)
        px = frames[sym]["c"].iloc[i] if i is not None else positions[sym]["entry"]
        close_pos(sym, final_ts, px, "end_of_data")

    curve_s = pd.Series([e for _, e in curve],
                        index=pd.to_datetime([t for t, _ in curve], unit="s"))
    daily = curve_s.resample("1D").last().dropna()

    # reference สำหรับเทียบ buy&hold: BTCUSDT ถ้ามี (crypto) ไม่งั้นใช้ symbol แรกเอง
    # (เช่น XAUUSD — เทียบกับ gold hold โดยตรง)
    ref_name = "BTCUSDT" if "BTCUSDT" in frames else (list(frames)[0] if frames else "")
    btc = frames.get(ref_name) if ref_name else None
    btc_ret, btc_dd = 0.0, 0.0
    if btc is not None:
        sub = btc.loc[sim_start:]
        if len(sub) > 10:
            btc_ret = sub["c"].iloc[-1] / sub["c"].iloc[0] - 1
            btc_dd = float((sub["c"] / sub["c"].cummax() - 1).min())

    final_eq = cash
    total_ret = final_eq / args.equity - 1
    span_days = max(1.0, (final_ts - sim_start) / 86400)
    cagr = ((final_eq / args.equity) ** (365.25 / span_days) - 1) if final_eq > 0 else -1.0
    max_dd = float((daily / daily.cummax() - 1).min()) if len(daily) > 1 else 0.0
    rets = daily.pct_change().dropna()
    sharpe = (rets.mean() / rets.std() * math.sqrt(365)) if rets.std() > 0 and len(rets) > 5 else 0.0

    # รวมผลระดับ position (partial TP = 1 position อาจมีหลาย fill) เพื่อเทียบกับ
    # benchmark ที่ปิดเต็มไม้เดียวได้อย่างตรงไปตรงมา
    pos_agg = {}
    for c in closed:
        key = (c["symbol"], c["open_ts"])
        e = pos_agg.setdefault(key, {"pnl": 0.0, "fills": 0, "reasons": [], "hold": 0})
        e["pnl"] += c["pnl"]
        e["fills"] += 1
        e["reasons"].append(c["exit_reason"])
        e["hold"] = c["hold_bars"]
    pos_pnls = [e["pnl"] for e in pos_agg.values()]
    wins = [p for p in pos_pnls if p > 0]
    losses = [p for p in pos_pnls if p < 0]
    win_rate = len(wins) / len(pos_pnls) if pos_pnls else 0.0
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (999.0 if wins else 0.0)
    avg_hold = sum(e["hold"] for e in pos_agg.values()) / len(pos_agg) if pos_agg else 0

    L = []
    L.append("=" * 74)
    L.append(f"BACKTEST กฎจริง pipeline | {args.days} วัน | {interval} | เงินต้น {args.equity:,.0f} USDT")
    L.append(f"กฎ risk: {RISK_PER_TRADE:.0%}/เทรด, max_total {MAX_TOTAL_RISK:.0%}, "
             f"{MAX_DAY_LOSSES} ขาดทุน/วันหยุด, DD {MAX_TOTAL_DD:.0%} หยุด 1 สัปดาห์")
    L.append(f"fee {FEE:.1%} + slippage {SLIP:.2%} | symbols: {len(frames)}")
    if args.no_volume:
        L.append("volume spike filter = OFF (สินทรัพย์ไม่มี volume)")
    if args.regime_filter:
        if args.regime_mode == "bull":
            L.append("กรองเฉพาะ bull regime = ON")
        elif args.regime_mode == "squeeze":
            L.append("regime = volatility squeeze->breakout อย่างเดียว")
        else:
            L.append("regime = bull OR squeeze->breakout (state เสริม)")
    if args.squeeze_entry:
        L.append("entry confluence: เฉพาะ golden cross ที่เกิดในหน้าต่าง squeeze->breakout (expansion)")
    if args.htf_bias:
        L.append("กรองด้วย HTF bias (1D close > MA20) = ON")
    if args.golden_only:
        L.append("กฎ: golden cross อย่างเดียว (turtle ปิด)")
    elif args.meanrev:
        L.append(f"กฎ: mean reversion RSI{MR_RSI_PERIOD}<{MR_RSI_THRESH} bounce (TP {args.tp_smc:g} ATR)")
    elif args.fvg:
        L.append(f"กฎ: FVG continuation อย่างเดียว (TP {args.tp_smc:g} ATR)")
    elif args.smc_only:
        L.append(f"กฎ: SMC sweep ({args.smc_mode}) อย่างเดียว (TP {args.tp_smc:g} ATR)")
    if args.momentum_top > 0:
        L.append(f"relative-strength: เฉพาะ Top {args.momentum_top} ของ momentum 90d")
    if args.confluence != "none":
        mode = "boost-only (ไม่กรอง)" if args.boost_only else "กรองเฉพาะจังหวะ"
        L.append(f"confluence {mode}: SMC-{args.confluence} ภายใน {CONF_WIN} แท่ง "
                 f"| boost size x{args.boost:g} (risk {RISK_PER_TRADE * args.boost:.1%}/ไม้)")
    if args.partial_tp > 0:
        if args.tp2_atr > 0:
            L.append(f"Partial TP: ปิด {args.partial_tp:.0%} ที่ TP1 แล้วส่วนเหลือปิดที่ TP2 ({args.tp2_atr:g} ATR)")
        else:
            L.append(f"Partial TP: ปิด {args.partial_tp:.0%} ที่ TP1 แล้วส่วนเหลือตาม trailing {args.trail_atr:g} ATR")
    if args.funding_max > 0:
        L.append(f"Funding filter: ข้ามเทรดถ้า funding เฉลี่ย 7 วัน > {args.funding_max:.5f}")
    elif args.funding_min > 0:
        L.append(f"Funding filter (momentum ยืนยัน): เทรดเฉพาะเมื่อ funding เฉลี่ย 7 วัน > {args.funding_min:.5f}")
    if args.crowd_pct > 0:
        L.append(f"Crowd filter: ข้ามเทรดถ้า long/short ratio อยู่ percentile >= {args.crowd_pct:.0%} ของ trailing {CROWD_WIN_DAYS} วัน")
    if args.golden_only or args.smc_only or args.fvg or args.meanrev:
        pass
    else:
        L.append(f"กฎ: golden (TP {args.tp_golden:g} ATR) + turtle (TP {args.tp_turtle:g} ATR)")
    L.append("=" * 74)
    L.append(f"ผลตอบแทนรวม      : {total_ret:+.2%}")
    L.append(f"CAGR              : {cagr:+.2%}")
    L.append(f"Equity สุดท้าย    : {final_eq:,.2f} USDT")
    L.append(f"Max Drawdown      : {max_dd:.2%}")
    L.append(f"Sharpe (รายวัน)   : {sharpe:.2f}")
    L.append(f"เทรด (เปิด/ปิด)   : {opened} / {len(closed)}")
    L.append(f"Win rate          : {win_rate:.1%}  ({len(wins)}W / {len(losses)}L)")
    L.append(f"Profit factor     : {pf:.2f}")
    L.append(f"PnL รวม           : {sum(pos_pnls):+,.2f} USDT")
    L.append(f"Avg PnL/เทรด      : {sum(pos_pnls)/len(pos_pnls):+,.2f}" if pos_pnls else "")
    L.append(f"Avg hold          : {avg_hold:.1f} แท่ง {interval} ({avg_hold*step/86400:.1f} วัน)")
    L.append(f"fees รวม          : {fees_total:,.2f} USDT")
    L.append(f"{ref_name or 'ref'} buy&hold    : {btc_ret:+.2%} (MaxDD {btc_dd:.2%})")
    L.append(f"Alpha vs {ref_name or 'ref'}      : {total_ret - btc_ret:+.2%}")
    L.append(f"blocked: pos={blocked['positions']} cash={blocked['cash']} "
             f"dd_halt={blocked['dd_halt']} day_halt={blocked['day_halt']} "
             f"dup={blocked['dup_cross']} regime={blocked['regime']} "
             f"conf={blocked['confluence']} mom={blocked['momentum']} "
             f"funding={blocked['funding']} crowd={blocked['crowd']} "
             f"sqz_entry={blocked['sqz_entry']}")
    by_reason = {}
    for c in closed:
        by_reason.setdefault(c["reason"], []).append(c["pnl"])
    for k, v in by_reason.items():
        L.append(f"  [{k}] {len(v)} เทรด, PnL {sum(v):+,.2f}, "
                 f"win {sum(1 for x in v if x > 0)/len(v):.0%}")
    print("\n".join(L))

    tag = ""
    if args.equity != 50_000.0:
        tag += f"_eq{args.equity:.0f}"
    if args.symbol_list:
        tag += "_" + "_".join(s.lower() for s in symbols)
    if args.fee_rate != 0.001 or args.slippage != 0.0005:
        tag += f"_fee{args.fee_rate:.6f}_slip{args.slippage:.6f}"
    if args.golden_only:
        tag += "_golden"
    elif args.meanrev:
        tag += "_meanrev"
    elif args.fvg:
        tag += "_fvg"
    elif args.smc_only:
        tag += f"_smc_{args.smc_mode}"
    if args.regime_filter:
        tag += "_regime"
        if args.regime_mode == "squeeze":
            tag += "_sqz"
        elif args.regime_mode == "or":
            tag += "_orsqz"
    elif args.htf_bias:
        tag += "_htf"
    if args.squeeze_entry:
        tag += "_sqzent"
    if args.momentum_top > 0:
        tag += f"_mom{args.momentum_top}"
    if args.confluence != "none":
        tag += f"_conf{args.confluence}" + ("_bo" if args.boost_only else "")
    if args.boost != 1.0:
        tag += f"_boost{args.boost:g}"
    if args.partial_tp > 0:
        tag += f"_part{args.partial_tp:g}"
        if args.tp2_atr > 0:
            tag += f"_tp2{args.tp2_atr:g}"
        else:
            tag += f"_trail{args.trail_atr:g}"
    if args.funding_max > 0:
        tag += f"_fundmax{args.funding_max:.5f}".rstrip("0")
    elif args.funding_min > 0:
        tag += f"_fundmin{args.funding_min:.5f}".rstrip("0")
    if args.crowd_pct > 0:
        tag += f"_crowd{args.crowd_pct:g}"
    if args.golden_only and args.tp_golden != 2.0:
        tag += f"_g_tp{args.tp_golden:g}"
    if (args.smc_only or args.fvg) and args.tp_smc != 2.8:
        tag += f"_s_tp{args.tp_smc:g}"
    if not args.golden_only and not args.smc_only and not args.fvg and args.tp_turtle != 3.0:
        tag += f"_t_tp{args.tp_turtle:g}"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    name = RESULTS_DIR / f"backtest_result_{args.days}d{tag}.json"
    with open(name, "w", encoding="utf-8") as f:
        json.dump({
            "days": args.days, "symbols": len(frames), "equity_start": args.equity,
            "total_return": total_ret, "cagr": cagr, "final_equity": final_eq,
            "max_dd": max_dd, "sharpe": sharpe, "trades": len(closed),
            "win_rate": win_rate, "profit_factor": pf, "total_pnl": sum(pos_pnls),
            "fees": fees_total, "btc_return": btc_ret, "btc_max_dd": btc_dd,
            "alpha": total_ret - btc_ret,
            "blocked": blocked,
            "by_reason": {k: {"n": len(v), "pnl": sum(v)} for k, v in by_reason.items()},
            "trades": [{"symbol": c["symbol"], "reason": c["reason"],
                         "open_ts": c["open_ts"], "pnl": round(c["pnl"], 2),
                         "exit_reason": c["exit_reason"]} for c in closed],
            "daily_curve": [[int(t), round(e, 2)] for t, e in curve],
        }, f, ensure_ascii=False, indent=2)
    print(f"\nบันทึกผล: {name}")


if __name__ == "__main__":
    main()
