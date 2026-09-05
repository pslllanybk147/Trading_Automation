#!/usr/bin/env python3
"""Event study: compare historical news events with BTC daily price statistics.

Fetches daily BTC close prices + volumes from CoinGecko (free tier, no key)
and computes returns / volume / volatility around well-known news events.
Uses only stdlib (urllib) - no external dependencies.
"""

import json
import math
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

BINANCE = "https://api.binance.com/api/v3/klines"

# (date, label) - date is the calendar day the news broke (UTC)
EVENTS = [
    ("2021-05-19", "China crypto crackdown"),
    ("2022-05-11", "LUNA/UST collapse"),
    ("2022-11-08", "FTX liquidity crisis"),
    ("2024-01-11", "SEC approves spot BTC ETFs (sell-the-news?)"),
    ("2024-04-20", "4th Bitcoin halving"),
    ("2024-08-05", "Yen carry trade unwind crash"),
    ("2024-11-06", "Trump wins US election"),
    ("2025-01-20", "Trump inauguration (ATH day)"),
    ("2025-04-02", "US 'Liberation Day' tariffs"),
    # 2025 FOMC meetings (decision day = 2nd day of meeting, 2pm ET = ~18:00-19:00 UTC)
    ("2025-01-29", "FOMC Jan 2025"),
    ("2025-03-19", "FOMC Mar 2025"),
    ("2025-05-07", "FOMC May 2025"),
    ("2025-06-18", "FOMC Jun 2025"),
    ("2025-07-30", "FOMC Jul 2025"),
    ("2025-09-17", "FOMC Sep 2025"),
]


def fetch_market_chart(coin: str = "BTCUSDT", start: str = "2021-01-01",
                       end: str = "2026-09-04") -> list[list]:
    """Fetch daily klines from Binance between start and end (no auth)."""
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").timestamp() * 1000)
    end_ms = int(datetime.strptime(end, "%Y-%m-%d").timestamp() * 1000)
    all_klines = []
    cur = start_ms
    while cur < end_ms:
        params = urllib.parse.urlencode({
            "symbol": coin, "interval": "1d",
            "startTime": cur, "endTime": end_ms, "limit": 1000})
        url = f"{BINANCE}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            klines = json.loads(resp.read().decode())
        if not klines:
            break
        all_klines.extend(klines)
        cur = klines[-1][0] + 1
        time.sleep(0.3)
    return all_klines


def build_series(klines: list[list]) -> list[tuple[str, float, float]]:
    """Return list of (date_str, close_price, volume) sorted by date.

    Binance kline format: [openTime, open, high, low, close, volume, ...]
    Volume here is base-asset (BTC) volume.
    """
    series = []
    for k in klines:
        ts = k[0]
        d = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        series.append((d, float(k[4]), float(k[5])))
    return series


def main() -> None:
    print("Fetching 5 years of BTC daily data from Binance ...")
    klines = fetch_market_chart()
    series = build_series(klines)
    by_date = {d: (px, vol) for d, px, vol in series}
    dates = [d for d, _, _ in series]
    print(f"Got {len(series)} daily points: {dates[0]} .. {dates[-1]}\n")

    def close_on(d: str) -> float | None:
        return by_date[d][0] if d in by_date else None

    def vol_on(d: str) -> float | None:
        return by_date[d][1] if d in by_date else None

    def index_of(d: str) -> int | None:
        if d in by_date:
            return dates.index(d)
        # nearest earlier date
        for i in range(len(dates) - 1, -1, -1):
            if dates[i] <= d:
                return i
        return None

    def vol_avg_before(d: str, n: int = 20) -> float:
        i = index_of(d)
        if i is None or i < n:
            return float("nan")
        return sum(series[j][2] for j in range(i - n, i)) / n

    header = (f"{'Event':<34}{'D-5→D-1':>10}{'D-1→D':>10}{'D→D+1':>10}"
              f"{'D→D+5':>10}{'Vol x':>8}")
    print(header)
    print("-" * len(header))
    results = []
    for date_str, label in EVENTS:
        i = index_of(date_str)
        if i is None:
            print(f"{label:<34} no data")
            continue
        d = dates[i]  # actual available date
        p0 = series[i][0]
        p5 = series[i - 5][1] if i - 5 >= 0 else None
        p1 = series[i - 1][1] if i - 1 >= 0 else None
        p_now = series[i][1]
        p_next = series[i + 1][1] if i + 1 < len(series) else None
        p_next5 = series[i + 5][1] if i + 5 < len(series) else None

        def pct(a, b):
            return (b / a - 1) * 100 if a else float("nan")

        pre = pct(p5, p1) if p5 and p1 else float("nan")
        evday = pct(p1, p_now) if p1 else float("nan")
        post1 = pct(p_now, p_next) if p_next else float("nan")
        post5 = pct(p_now, p_next5) if p_next5 else float("nan")
        v_avg = vol_avg_before(d)
        v_ratio = vol_on(d) / v_avg if v_avg == v_avg and v_avg > 0 else float("nan")

        results.append((date_str, label, pre, evday, post1, post5, v_ratio, d, p_now))
        print(f"{label:<34}{pre:>9.1f}%{evday:>9.1f}%{post1:>9.1f}%"
              f"{post5:>9.1f}%{v_ratio:>7.1f}x")

    print("\n--- Detail (price around event) ---")
    for date_str, label, pre, evday, post1, post5, v_ratio, d, p_now in results:
        i = index_of(d)
        win = series[max(0, i - 3):i + 4]
        prices_str = " ".join(f"{w[1]:>9,.0f}" for w in win)
        print(f"{label:<34} [{d}] {prices_str}")


if __name__ == "__main__":
    main()