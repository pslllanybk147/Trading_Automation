import json
from unittest import mock
from pipeline.data_layer import (
    fetch_klines, check_completeness, parse_klines, get_top_symbols, SKIP_SYMBOLS,
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
