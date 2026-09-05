#!/usr/bin/env python3
import urllib.request
import urllib.parse
import urllib.error
import json
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor

def get_ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

ctx = get_ssl_context()

def get_klines(symbol, interval='1h', limit=50):
    encoded_symbol = urllib.parse.quote(symbol)
    url = f'https://api.binance.com/api/v3/klines?symbol={encoded_symbol}&interval={interval}&limit={limit}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        print(f"Binance HTTP error for {symbol}: {error.code}", file=sys.stderr)
        return []
    except urllib.error.URLError as error:
        print(f"Network error for {symbol}: {error.reason}", file=sys.stderr)
        return []
    except json.JSONDecodeError:
        print(f"Invalid JSON response from Binance for {symbol}", file=sys.stderr)
        return []
    except Exception as error:
        print(f"Unexpected error fetching {symbol}: {error}", file=sys.stderr)
        return []

def calculate_atr(k_lines, period=14):
    if len(k_lines) <= period:
        return 0.0
    tr = []
    for i in range(1, len(k_lines)):
        h = float(k_lines[i][2])
        l = float(k_lines[i][3])
        pc = float(k_lines[i-1][4])
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    
    atr = sum(tr[:period]) / period
    for i in range(period, len(tr)):
        atr = (atr * (period - 1) + tr[i]) / period
    return atr

def calculate_wilder_rsi(closes, period=14):
    if len(closes) <= period:
        return 50.0

    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]

    # Initial SMA for first period
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder's Smoothing for remaining data
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)

def calculate_risk_reward(entry, target, stop, is_short=False):
    if is_short:
        risk = stop - entry
        reward = entry - target
    else:
        risk = entry - stop
        reward = target - entry
        
    if risk <= 0:
        return 0.0
    return round(reward / risk, 2)

def is_valid_long(entry, tp1, sl, rr, trend_4h, rsi_1h, trend_1h, vol_spike):
    return (
        tp1 > entry and
        sl < entry and
        rr >= 1.5 and
        trend_4h and
        45 <= rsi_1h <= 68 and
        trend_1h and
        vol_spike
    )

def is_valid_short(entry, tp1, sl, rr, trend_4h, rsi_1h, trend_1h, vol_spike):
    return (
        tp1 < entry and
        sl > entry and
        rr >= 1.5 and
        not trend_4h and
        32 <= rsi_1h <= 55 and
        trend_1h and
        vol_spike
    )

def analyze_pair(t):
    sym = t['symbol']
    raw_k1h = get_klines(sym, '1h', 50)
    raw_k4h = get_klines(sym, '4h', 50)
    
    # Use last closed candles
    k1h = raw_k1h[:-1] if len(raw_k1h) > 1 else raw_k1h
    k4h = raw_k4h[:-1] if len(raw_k4h) > 1 else raw_k4h

    if len(k1h) < 30 or len(k4h) < 30:
        return None

    c1 = [float(x[4]) for x in k1h]
    c4 = [float(x[4]) for x in k4h]
    v1 = [float(x[5]) for x in k1h]

    m7_1h_curr, m25_1h_curr = sum(c1[-7:]) / 7, sum(c1[-25:]) / 25
    m7_1h_prev, m25_1h_prev = sum(c1[-8:-1]) / 7, sum(c1[-26:-1]) / 25

    m7_4h_curr, m25_4h_curr = sum(c4[-7:]) / 7, sum(c4[-25:]) / 25
    m7_4h_prev, m25_4h_prev = sum(c4[-8:-1]) / 7, sum(c4[-26:-1]) / 25

    rsi1 = calculate_wilder_rsi(c1)
    rsi4 = calculate_wilder_rsi(c4)

    avg_vol_20 = sum(v1[-21:-1]) / 20 if len(v1) >= 21 else sum(v1[:-1]) / max(len(v1[:-1]), 1)
    vol_ratio = round(v1[-1] / avg_vol_20, 2) if avg_vol_20 > 0 else 0.0
    volume_spike = vol_ratio >= 1.5

    cross_1h_bull = (m7_1h_prev <= m25_1h_prev and m7_1h_curr > m25_1h_curr)
    cross_1h_bear = (m7_1h_prev >= m25_1h_prev and m7_1h_curr < m25_1h_curr)
    cross_4h_bull = (m7_4h_prev <= m25_4h_prev and m7_4h_curr > m25_4h_curr)

    high_24h = max([float(x[2]) for x in k1h[-24:]])
    low_24h = min([float(x[3]) for x in k1h[-24:]])
    curr_price = c1[-1]

    atr1 = calculate_atr(k1h, period=14)

    # Dynamic ATR-buffered Stop Loss & Take Profit Calculations
    long_tp1 = round(high_24h, 4)
    long_tp2 = round(high_24h + (atr1 * 1.5), 4)
    
    # Base SL uses structural support (low_24h or MA25), buffered by 1.0x ATR to prevent noise stopouts
    struct_long_sl = max(low_24h, m25_1h_curr * 0.99) if low_24h < curr_price else curr_price * 0.98
    long_sl = round(min(struct_long_sl, curr_price - (atr1 * 1.0)), 4)
    if long_sl >= curr_price:
        long_sl = round(curr_price - max(atr1 * 1.0, curr_price * 0.015), 4)

    long_risk = round(curr_price - long_sl, 4)
    long_rr_tp1 = calculate_risk_reward(curr_price, long_tp1, long_sl, is_short=False)
    long_rr_tp2 = calculate_risk_reward(curr_price, long_tp2, long_sl, is_short=False)

    trend_4h_bull = m7_4h_curr > m25_4h_curr
    trend_1h_bull = cross_1h_bull

    valid_long = is_valid_long(
        entry=curr_price,
        tp1=long_tp1,
        sl=long_sl,
        rr=long_rr_tp1,
        trend_4h=trend_4h_bull,
        rsi_1h=rsi1,
        trend_1h=trend_1h_bull,
        vol_spike=volume_spike
    )

    # SHORT Setup Calculation
    short_tp1 = round(low_24h, 4)
    short_tp2 = round(low_24h - (atr1 * 1.5), 4)
    
    struct_short_sl = min(high_24h, m25_1h_curr * 1.01) if high_24h > curr_price else curr_price * 1.02
    short_sl = round(max(struct_short_sl, curr_price + (atr1 * 1.0)), 4)
    if short_sl <= curr_price:
        short_sl = round(curr_price + max(atr1 * 1.0, curr_price * 0.015), 4)

    short_risk = round(short_sl - curr_price, 4)
    short_rr_tp1 = calculate_risk_reward(curr_price, short_tp1, short_sl, is_short=True)
    short_rr_tp2 = calculate_risk_reward(curr_price, short_tp2, short_sl, is_short=True)

    trend_1h_bear = cross_1h_bear

    valid_short = is_valid_short(
        entry=curr_price,
        tp1=short_tp1,
        sl=short_sl,
        rr=short_rr_tp1,
        trend_4h=trend_4h_bull,
        rsi_1h=rsi1,
        trend_1h=trend_1h_bear,
        vol_spike=volume_spike
    )

    entry_low = round(min(m7_1h_curr, curr_price), 4)
    entry_high = round(max(m7_1h_curr, curr_price), 4)

    setup_data = None
    position_type = "NONE"

    if valid_long:
        position_type = "LONG"
        setup_data = {
            'position': 'LONG',
            'entry_range': f"${entry_low} - ${entry_high}",
            'tp1': long_tp1,
            'tp2': long_tp2,
            'sl': long_sl,
            'risk': long_risk,
            'reward_tp1': round(long_tp1 - curr_price, 4),
            'reward_tp2': round(long_tp2 - curr_price, 4),
            'rr_tp1': long_rr_tp1,
            'rr_tp2': long_rr_tp2
        }
    elif valid_short:
        position_type = "SHORT"
        setup_data = {
            'position': 'SHORT',
            'entry_range': f"${entry_low} - ${entry_high}",
            'tp1': short_tp1,
            'tp2': short_tp2,
            'sl': short_sl,
            'risk': short_risk,
            'reward_tp1': round(curr_price - short_tp1, 4),
            'reward_tp2': round(curr_price - short_tp2, 4),
            'rr_tp1': short_rr_tp1,
            'rr_tp2': short_rr_tp2
        }

    return {
        'symbol': sym,
        'price': curr_price,
        'high_24h': high_24h,
        'low_24h': low_24h,
        'rsi_1h': rsi1,
        'rsi_4h': rsi4,
        'volume_ratio': vol_ratio,
        'volume_spike': volume_spike,
        'cross_1h_bull': cross_1h_bull,
        'cross_1h_bear': cross_1h_bear,
        'cross_4h_bull': cross_4h_bull,
        'm7_gt_m25_1h': m7_1h_curr > m25_1h_curr,
        'm7_gt_m25_4h': m7_4h_curr > m25_4h_curr,
        'volume_24h': float(t['quoteVolume']),
        'position_type': position_type,
        'valid_long': valid_long,
        'valid_short': valid_short,
        'setup': setup_data
    }

def scan_markets(min_volume=2000000, target_symbol=None):
    url = 'https://api.binance.com/api/v3/ticker/24hr'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
            tickers = json.loads(response.read().decode())
    except Exception as error:
        print(f"Failed to fetch market tickers: {error}", file=sys.stderr)
        return []

    if target_symbol:
        pairs = [t for t in tickers if t['symbol'].upper() == target_symbol.upper()]
    else:
        pairs = sorted([
            t for t in tickers
            if t['symbol'].endswith('USDT') and t['symbol'].isascii() and t['symbol'].isalnum() and float(t['quoteVolume']) >= min_volume
        ], key=lambda x: float(x['quoteVolume']), reverse=True)

    # Use ThreadPoolExecutor for fast concurrent scanning across pairs
    with ThreadPoolExecutor(max_workers=15) as executor:
        results = list(executor.map(analyze_pair, pairs[:100]))

    return [r for r in results if r is not None]

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else None
    res = scan_markets(target_symbol=target)
    print(json.dumps(res, indent=2))
