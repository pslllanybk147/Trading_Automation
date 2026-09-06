# -*- coding: utf-8 -*-
"""TradingView-style chart ของการเทรด — candles + จุดซื้อ/ขาย + log รายวัน

ดึงข้อมูลจาก 2 แหล่ง (ผสมกันได้):
  1) journal (paper/live):  data/journal.db หรือ data/journal_ab_mhm.db (--journal)
  2) backtest JSON:         backtest_results/backtest_result_*.json (--result)

ใช้ lightweight-charts v4 (TradingView open-source, โหลดจาก CDN ตอนเปิดไฟล์)
— ลาก/ซูม/ดูราคาแบบ TradingView

รัน:
  python plot_trades.py                                   # journal จริง (arm A)
  python plot_trades.py --journal data/journal_ab_mhm.db  # arm B
  python plot_trades.py --result backtest_results/backtest_result_1095d_golden_regime_g_tp2.8.json
  python plot_trades.py --all                             # ทุกแหล่งรวมกัน

ผลลัพธ์: trade_chart.html (เปิดในเบราว์เซอร์)
"""
from __future__ import annotations

import json
import sqlite3
import argparse
import html
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path

from pipeline.data_layer import load_cached_candles  # cache.db คือแหล่ง candle

OUT_HTML = Path("trade_chart.html")
CDN = ("https://unpkg.com/lightweight-charts@4.2.0/dist/"
       "lightweight-charts.standalone.production.js")


# ---------------------------------------------------------------- โหลดเทรด

def load_journal_trades(db_path: str) -> tuple[list[dict], str]:
    """เทรดจริงจาก paper journal (source of truth ของ pipeline)"""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT symbol, entry, exit, size_usdt, fee, ts_open, ts_close, "
            "reason, sl_price, tp1_price FROM trades ORDER BY ts_open"
        ).fetchall()
    finally:
        conn.close()
    trades = []
    for sym, entry, exit_, size, fee, t_open, t_close, reason, sl, tp1 in rows:
        if not t_close:
            continue  # ไม้ที่ยังเปิด — chart แสดงเฉพาะไม้จบแล้ว
        trades.append({
            "symbol": sym, "reason": reason or "trade",
            "open_ts": t_open, "entry": entry,
            "exit_ts": t_close, "exit": exit_,
            "size_usdt": size, "sl": sl or 0.0, "tp1": tp1 or 0.0,
            "pnl": round(size * (exit_ - entry) / entry - fee, 2),
            "exit_reason": "journal",
        })
    return trades, f"paper journal: {db_path}"


def load_result_trades(json_path: str) -> tuple[list[dict], str]:
    """เทรดจำลองจากไฟล์ผล backtest (มี entry/exit เต็มตั้งแต่ session นี้)"""
    d = json.load(open(json_path, encoding="utf-8"))
    trades = [t for t in d.get("trades", []) if "entry" in t]
    return trades, f"backtest: {Path(json_path).name}"


# ---------------------------------------------------------------- candles

def load_candles(symbol: str, interval: str, t0: int, t1: int) -> list[dict]:
    """โหลด OHLCV จาก cache.db ช่วงที่เทรดเกิด (+ margin 30 แท่ง)"""
    step = {"1h": 3600, "4h": 14400, "1d": 86400}.get(interval, 14400)
    margin = step * 30
    out = []
    for c in load_cached_candles(symbol, interval):
        if t0 - margin <= c.ts <= t1 + margin:
            out.append({"time": c.ts, "open": c.o, "high": c.h,
                        "low": c.l, "close": c.c, "volume": c.v})
    return out


# ---------------------------------------------------------------- จัดกลุ่ม

def group_series(trades: list[dict]) -> dict[str, list[dict]]:
    """จัดเทรดเป็นชุดต่อ symbol — แยก tab ต่อ symbol บน chart"""
    by: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by[t["symbol"]].append(t)
    return {s: sorted(v, key=lambda x: x["open_ts"]) for s, v in by.items()}


def daily_log(trades: list[dict]) -> list[dict]:
    """รวมเหตุการณ์ซื้อ/ขายเป็น log รายวัน (เรียงเก่า→ใหม่)"""
    days: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        d_open = datetime.fromtimestamp(t["open_ts"], UTC).strftime("%Y-%m-%d")
        days[d_open].append({"side": "BUY", "symbol": t["symbol"],
                             "price": t["entry"], "size": t["size_usdt"],
                             "note": t["reason"]})
        d_close = datetime.fromtimestamp(t["exit_ts"], UTC).strftime("%Y-%m-%d")
        wr = "WIN " if t["pnl"] > 0 else ("LOSS" if t["pnl"] < 0 else "FLAT")
        days[d_close].append({"side": wr, "symbol": t["symbol"],
                              "price": t["exit"], "size": t["size_usdt"],
                              "note": "pnl %+.2f (%s)" % (t["pnl"], t["exit_reason"])})
    return [{"date": d, "events": ev} for d, ev in sorted(days.items())]


# ---------------------------------------------------------------- HTML

def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _js(o) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def _log_rows(logs: list[dict]) -> str:
    """HTML ของ log รายวัน (หลีกเลี่ยง nested f-string — คำนวณ string ทีละชิ้น)"""
    cls_map = {"BUY": "buy", "WIN": "win", "LOSS": "loss"}
    rows = []
    for d in logs:
        evs = []
        for e in d["events"]:
            side = e["side"].strip()
            cls = cls_map.get(side, "flat")
            sym = _esc(e["symbol"])
            price_s = _esc("%,.4f".replace(",", ",") % () if False else f"{e['price']:,.4f}")
            size_s = f"{e['size']:,.0f}"
            note = _esc(e["note"])
            evs.append(
                '<span class="ev ' + cls + '">' + _esc(side) + "</span>"
                " <b>" + sym + "</b> @ " + price_s +
                ' <span class="dim">' + _esc(size_s) + " USDT · " + note + "</span>")
        day_html = ('<div class="day"><span class="date">' + _esc(d["date"]) +
                    '</span><div class="evs">' + "".join(evs) + "</div></div>")
        rows.append(day_html)
    return "".join(rows)


def _stat_rows(stats: list[dict]) -> str:
    rows = []
    for s in stats:
        cls = "pos" if s["pnl"] > 0 else ("neg" if s["pnl"] < 0 else "")
        pnl_s = f"{s['pnl']:+,.2f}"
        rows.append(
            "<tr><td>" + _esc(s["source"]) + "</td><td>" + str(s["trades"]) +
            "</td><td>" + str(s["wins"]) + "</td><td>" + str(s["losses"]) +
            '</td><td class="' + cls + '">' + _esc(pnl_s) + "</td></tr>")
    return "".join(rows)


def build_html(bundle: list[dict], logs: list[dict], stats: list[dict]) -> str:
    """bundle = [{label, symbol, candles, trades}] — tab ต่อ symbol"""
    tabs_data = [{"label": b["label"], "symbol": b["symbol"],
                  "candles": b["candles"], "trades": b["trades"]} for b in bundle]
    stat_html = _stat_rows(stats)
    log_html = _log_rows(logs) or (
        '<i class="dim">ยังไม่มีเทรด — ลอง --result เพื่อดูเทรดจาก backtest</i>')

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<title>Trade Chart — TradingView style</title>
<style>
  :root {{
    --bg:#131722; --panel:#1e222d; --border:#2a2e39;
    --text:#d1d4dc; --dim:#787b86; --green:#26a69a; --red:#ef5350;
    --blue:#2962ff; --amber:#ff9800;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
         font:13px/1.5 'Segoe UI',sans-serif; }}
  header {{ padding:14px 20px 8px; }}
  header h1 {{ font-size:17px; margin:0 0 2px; font-weight:600; }}
  header .sub {{ color:var(--dim); font-size:12px; }}
  .tabs {{ display:flex; gap:4px; padding:6px 20px 0; flex-wrap:wrap; }}
  .tab {{ background:var(--panel); border:1px solid var(--border);
          border-bottom:none; color:var(--dim); padding:6px 14px;
          border-radius:6px 6px 0 0; cursor:pointer; font-size:12px; }}
  .tab.active {{ color:var(--text); background:var(--panel); }}
  .chart-wrap {{ position:relative; margin:0 20px; border:1px solid var(--border);
                 border-radius:0 8px 8px 8px; background:var(--panel); }}
  .legend {{ position:absolute; top:8px; left:12px; z-index:5; font-size:12px;
             pointer-events:none; }}
  .legend b {{ font-size:13px; }}
  .legend .dim {{ color:var(--dim); }}
  #chart {{ height:520px; }}
  .layout {{ display:grid; grid-template-columns:1fr 380px; gap:16px;
             margin:16px 20px; }}
  @media (max-width:1100px) {{ .layout {{ grid-template-columns:1fr; }} }}
  .panel {{ background:var(--panel); border:1px solid var(--border);
            border-radius:8px; padding:12px 14px; }}
  .panel h2 {{ margin:0 0 8px; font-size:13px; color:var(--dim);
               font-weight:600; text-transform:uppercase; letter-spacing:.05em; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  td, th {{ padding:4px 6px; border-bottom:1px solid var(--border);
            text-align:left; }}
  th {{ color:var(--dim); font-weight:600; }}
  .pos {{ color:var(--green); }} .neg {{ color:var(--red); }}
  .log {{ max-height:560px; overflow-y:auto; }}
  .day {{ display:flex; gap:10px; padding:5px 2px;
          border-bottom:1px solid var(--border); }}
  .date {{ color:var(--amber); font-family:Consolas,monospace; flex-shrink:0;
           min-width:78px; }}
  .evs {{ display:flex; flex-direction:column; gap:2px; }}
  .ev {{ font-family:Consolas,monospace; font-size:11px; padding:0 6px;
         border-radius:3px; font-weight:700; }}
  .ev.buy {{ background:var(--blue); color:#fff; }}
  .ev.win {{ background:var(--green); color:#fff; }}
  .ev.loss {{ background:var(--red); color:#fff; }}
  .ev.flat {{ background:var(--border); color:var(--dim); }}
  .dim {{ color:var(--dim); font-weight:400; }}
  footer {{ padding:10px 20px 24px; color:var(--dim); font-size:11px; }}
  .legend .mk {{ display:inline-block; width:8px; height:8px;
                 border-radius:50%; margin:0 4px 0 10px; }}
  .mk.buy {{ background:var(--blue); }} .mk.sell {{ background:var(--amber); }}
</style>
</head>
<body>
<header>
  <h1>📊 Trade Chart — TradingView style</h1>
  <span class="sub">candles จาก cache.db · ▲ น้ำเงิน = ซื้อ · ▼ = ขาย (เขียว = กำไร,
    แดง = ขาดทุน, ตัวเลข = PnL USDT) · ลาก/ซูมได้เหมือน TradingView</span>
</header>
<div class="tabs" id="tabs"></div>
<div class="chart-wrap">
  <div class="legend" id="legend"></div>
  <div id="chart"></div>
</div>
<div class="layout">
  <div class="panel">
    <h2>สรุปต่อแหล่งข้อมูล</h2>
    <table>
      <tr><th>แหล่ง</th><th>เทรด</th><th>ชนะ</th><th>แพ้</th><th>PnL (USDT)</th></tr>
      {stat_html}
    </table>
  </div>
  <div class="panel log">
    <h2>Log รายวัน — ซื้อ/ขายอะไร วันไหน</h2>
    {log_html}
  </div>
</div>
<footer>
  สร้างโดย plot_trades.py · lightweight-charts (TradingView open-source) ·
  scroll = ซูม · ลาก = เลื่อน · แหล่งข้อมูล: paper journal + backtest JSON
</footer>
<script src="{CDN}"></script>
<script>
const TABS = {_js(tabs_data)};

const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  layout: {{ background: {{ type:'solid', color:'#1e222d' }}, textColor:'#d1d4dc' }},
  grid: {{ vertLines: {{ color:'#2a2e39' }}, horzLines: {{ color:'#2a2e39' }} }},
  rightPriceScale: {{ borderColor:'#2a2e39' }},
  timeScale: {{ borderColor:'#2a2e39', timeVisible:true, secondsVisible:false }},
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
}});
const candleSeries = chart.addCandlestickSeries({{
  upColor:'#26a69a', downColor:'#ef5350', borderVisible:false,
  wickUpColor:'#26a69a', wickDownColor:'#ef5350',
}});
const volSeries = chart.addHistogramSeries({{
  priceFormat: {{ type:'volume' }}, priceScaleId:'', lastValueVisible:false,
  priceLineVisible:false,
}});
volSeries.priceScale().applyOptions({{ scaleMargins: {{ top:0.82, bottom:0 }} }});

function renderTab(i) {{
  const t = TABS[i];
  document.querySelectorAll('.tab').forEach(function(el, j) {{
    el.classList.toggle('active', j === i);
  }});
  document.getElementById('legend').innerHTML =
    '<b>' + t.symbol + '</b> <span class="dim">· ' + t.label + '</span>' +
    '<span class="mk buy"></span>ซื้อ <span class="mk sell"></span>ขาย';
  candleSeries.setData(t.candles);
  volSeries.setData(t.candles.map(function(c) {{
    return {{ time: c.time, value: c.volume,
      color: c.close >= c.open ? 'rgba(38,166,154,.35)' : 'rgba(239,83,80,.35)' }};
  }}));
  const markers = t.trades.flatMap(function(tr) {{
    const sizeTxt = tr.size_usdt ? ' ' + (tr.size_usdt/1000).toFixed(1) + 'k' : '';
    return [
      {{ time: tr.open_ts, position: 'belowBar', shape: 'arrowUp',
         color: '#2962ff', text: 'B' + sizeTxt }},
      {{ time: tr.exit_ts, position: 'aboveBar', shape: 'arrowDown',
         color: tr.pnl >= 0 ? '#26a69a' : '#ef5350',
         text: (tr.pnl >= 0 ? '+' : '') + tr.pnl.toFixed(0) }},
    ];
  }});
  markers.sort(function(a, b) {{ return a.time - b.time; }});
  candleSeries.setMarkers(markers);
  if (t.candles.length) {{
    chart.timeScale().setVisibleRange({{
      from: t.candles[0].time,
      to: t.candles[t.candles.length - 1].time,
    }});
  }}
}}

const tabsEl = document.getElementById('tabs');
TABS.forEach(function(t, i) {{
  const el = document.createElement('button');
  el.className = 'tab';
  el.textContent = t.symbol + ' (' + t.trades.length + ')';
  el.onclick = function() {{ renderTab(i); }};
  tabsEl.appendChild(el);
}});
renderTab(0);
</script>
</body>
</html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="TradingView-style trade chart")
    ap.add_argument("--journal", default="data/journal.db",
                    help="ไฟล์ journal (default data/journal.db)")
    ap.add_argument("--result", action="append", default=[],
                    help="ไฟล์ backtest JSON (ใส่ซ้ำได้หลายไฟล์)")
    ap.add_argument("--all", action="store_true",
                    help="journal ทั้ง 2 arm + ผล benchmark รวมใน chart เดียว")
    ap.add_argument("-o", "--out", default=str(OUT_HTML))
    args = ap.parse_args()

    sources: list[tuple[list[dict], str]] = []
    if args.all:
        for j in ["data/journal.db", "data/journal_ab_mhm.db"]:
            if Path(j).exists():
                sources.append(load_journal_trades(j))
        bench = Path("backtest_results") / "backtest_result_1095d_golden_regime_g_tp2.8.json"
        if bench.exists():
            sources.append(load_result_trades(str(bench)))
    elif args.result:
        for f in args.result:
            sources.append(load_result_trades(f))
    else:
        sources.append(load_journal_trades(args.journal))

    bundle: list[dict] = []
    logs: list[dict] = []
    stats: list[dict] = []
    for trades, label in sources:
        if not trades:
            continue
        tag = label.split(":")[0].strip()
        for sym, ts in group_series(trades).items():
            t0 = min(t["open_ts"] for t in ts)
            t1 = max(t["exit_ts"] for t in ts)
            candles = load_candles(sym, "4h", t0, t1)
            if not candles:
                print(f"  (ข้าม {sym}: ไม่มี candle ใน cache)")
                continue
            bundle.append({"label": label, "symbol": sym,
                           "candles": candles, "trades": ts})
        wins = sum(1 for t in trades if t["pnl"] > 0)
        losses = sum(1 for t in trades if t["pnl"] < 0)
        stats.append({"source": label, "trades": len(trades), "wins": wins,
                      "losses": losses,
                      "pnl": round(sum(t["pnl"] for t in trades), 2)})
        for d in daily_log(trades):
            logs.append({"date": d["date"],
                         "events": [{**e, "note": "[" + tag + "] " + e["note"]}
                                    for e in d["events"]]})

    if not bundle:
        print("ไม่มีเทรดให้แสดง (journal ว่าง และไม่ได้ระบุ --result)")
        print("ลอง: python plot_trades.py --result "
              "backtest_results/backtest_result_1095d_golden_regime_g_tp2.8.json")
        return

    logs.sort(key=lambda d: d["date"])
    Path(args.out).write_text(build_html(bundle, logs, stats), encoding="utf-8")
    n_tr = sum(len(b["trades"]) for b in bundle)
    print(f"สร้าง {args.out}: {len(bundle)} symbol-tabs, {n_tr} เทรด "
          f"({'; '.join(s['source'] for s in stats)})")


if __name__ == "__main__":
    main()
