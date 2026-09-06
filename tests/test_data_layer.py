import json
import time
from unittest import mock
from pipeline.data_layer import (
    fetch_klines, check_completeness, parse_klines, get_top_symbols,
    SKIP_SYMBOLS, is_stale,
)
from pipeline.models import CandleData


FAKE_KLINE = [
    1700000000000, "100.0", "101.0", "99.0", "100.5", "1234.5",
    1700003600000, "100.5", "102.0", "100.0", "101.0", "999.9", 0, 0, 0, 0, 0, 0,
]


def test_parse_klines():
    candles = parse_klines("BTCUSDT", "4h", [FAKE_KLINE])
    assert len(candles) == 1
    assert candles[0].symbol == "BTCUSDT"
    assert candles[0].c == 100.5
    assert candles[0].v == 1234.5


def test_fetch_klines_hits_api():
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__.return_value = m.return_value
        m.return_value.read.return_value = json.dumps([FAKE_KLINE]).encode()
        candles = fetch_klines("BTCUSDT", "4h", limit=1)
    assert len(candles) == 1
    assert candles[0].symbol == "BTCUSDT"


def test_check_completeness_ok():
    candles = [CandleData("X", "1d", 1700000000 + i * 86400, 1, 1, 1, 1, 1) for i in range(100)]
    assert check_completeness(candles, "1d") is True


def test_check_completeness_gappy():
    candles = [CandleData("X", "1d", 1700000000 + i * 86400, 1, 1, 1, 1, 1) for i in range(90)]
    candles.append(CandleData("X", "1d", 1700000000 + 99 * 86400, 1, 1, 1, 1, 1))  # jump 9 days
    assert check_completeness(candles, "1d") is False  # 10% gap > 5%


# ---------- skip list (HTTP 400 symbols) ----------

def test_skip_list_contains_usdg():
    assert "USDGUSDT" in SKIP_SYMBOLS


def test_skip_list_contains_dai():
    # DAIUSDT delisted 2020-08 — klines ยังคืนแท่งเก่าด้วย HTTP 200
    assert "DAIUSDT" in SKIP_SYMBOLS


# ---------- staleness guard (delisted symbols) ----------

def _candles_at(ts_list, symbol="OLD"):
    return [CandleData(symbol, "4h", ts, 1.0, 1.0, 1.0, 1.0, 100.0)
            for ts in ts_list]


def test_is_stale_flags_delisted_data():
    # แท่งสุดท้ายปี 2020 — เหมือน DAIUSDT ที่ API ยังคืนข้อมูลเก่า
    now_ts = 1_797_000_000  # ~2026-12
    old = _candles_at([1_595_505_600, 1_595_520_000, 1_595_538_400])
    assert is_stale(old, "4h", now_ts=now_ts) is True


def test_is_stale_passes_fresh_data():
    now_ts = int(time.time())
    fresh = _candles_at([now_ts - 3 * 14400, now_ts - 2 * 14400, now_ts - 14400])
    assert is_stale(fresh, "4h", now_ts=now_ts) is False


def test_is_stale_empty_is_stale():
    assert is_stale([], "4h") is True


def _coingecko_payload(symbols: list[str]) -> list[dict]:
    return [{"symbol": s} for s in symbols]


def test_get_top_symbols_filters_blacklisted():
    payload = _coingecko_payload(["btc", "usdg", "eth"])
    with mock.patch("urllib.request.urlopen") as m:
        m.return_value.__enter__.return_value = m.return_value
        m.return_value.read.return_value = json.dumps(payload).encode()
        out = get_top_symbols(3)
    assert "USDGUSDT" not in out
    assert "BTCUSDT" in out and "ETHUSDT" in out


def test_get_top_symbols_fallback_filters_blacklisted():
    with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("api down")):
        out = get_top_symbols(30)
    assert all(s not in SKIP_SYMBOLS for s in out)
    assert len(out) == 30
