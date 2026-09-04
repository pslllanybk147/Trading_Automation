# -*- coding: utf-8 -*-
"""รวมผล backtest 2 กลยุทธ์ (แบ่งเงินต้น) เป็น portfolio เดียว

วิธีคิด: แต่ละกลยุทธ์รันเป็น sub-account อิสระ (equity ละครึ่งของเงินต้น)
portfolio equity = eq_A + eq_B ทุกวัน -> คำนวณ return/DD/Sharpe รวม
รวมถึง correlation ของ daily return ระหว่างสองกลยุทธ์ (ตัวชี้ว่าลด DD ได้จริง)

รัน:
  python backtest_portfolio.py <json_A> <json_B> [--equity 50000]
"""
import argparse
import json
import math

import pandas as pd


def load_curve(path: str) -> pd.Series:
    d = json.load(open(path, encoding="utf-8"))
    pts = d.get("daily_curve") or []
    s = pd.Series({ts: eq for ts, eq in pts}, dtype=float)
    s.index = pd.to_datetime(s.index, unit="s")
    return s.sort_index()


def stats(name: str, s: pd.Series, equity: float, span_days: float):
    daily = s.resample("1D").last().dropna()
    total_ret = daily.iloc[-1] / equity - 1
    cagr = ((daily.iloc[-1] / equity) ** (365.25 / span_days) - 1) if daily.iloc[-1] > 0 else -1.0
    max_dd = float((daily / daily.cummax() - 1).min()) if len(daily) > 1 else 0.0
    rets = daily.pct_change().dropna()
    sharpe = (rets.mean() / rets.std() * math.sqrt(365)) if rets.std() > 0 and len(rets) > 5 else 0.0
    return {"name": name, "total_return": total_ret, "cagr": cagr,
            "max_dd": max_dd, "sharpe": sharpe, "days": len(daily)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_a")
    ap.add_argument("json_b")
    ap.add_argument("--equity", type=float, default=50_000.0)
    args = ap.parse_args()

    sa = load_curve(args.json_a)
    sb = load_curve(args.json_b)
    if len(sa) == 0 or len(sb) == 0:
        print("ไฟล์ JSON ต้องมี daily_curve (รัน backtest รุ่นใหม่)")
        return

    # รวมบนวันที่ทั้งคู่มีข้อมูล
    idx = sa.index.union(sb.index).sort_values()
    a = sa.reindex(idx).ffill()
    b = sb.reindex(idx).ffill()
    port = a + b
    span_days = max(1.0, (idx[-1] - idx[0]).total_seconds() / 86400)

    st_a = stats("A: " + args.json_a, sa, args.equity / 2, span_days)
    st_b = stats("B: " + args.json_b, sb, args.equity / 2, span_days)
    st_p = stats("PORTFOLIO (A+B)", port, args.equity, span_days)

    ra = sa.resample("1D").last().pct_change().dropna()
    rb = sb.resample("1D").last().pct_change().dropna()
    both = pd.concat([ra, rb], axis=1, join="inner").dropna()
    corr = float(both.iloc[:, 0].corr(both.iloc[:, 1])) if len(both) > 10 else 0.0

    L = []
    L.append("=" * 74)
    L.append("PORTFOLIO 2 กลยุทธ์ (แบ่งเงินต้นคนละครึ่ง) | equity รวม %.0f USDT" % args.equity)
    L.append("=" * 74)
    for st in (st_a, st_b, st_p):
        L.append(f"{st['name']:<28} ret {st['total_return']:+8.2%}  CAGR {st['cagr']:+7.2%}  "
                 f"MaxDD {st['max_dd']:7.2%}  Sharpe {st['sharpe']:.2f}  ({st['days']} วัน)")
    L.append(f"Correlation ของ daily return (A,B) : {corr:+.2f}")
    print("\n".join(L))
    # ข้อควรรู้: ถ้า corr ต่ำ portfolio MaxDD < แต่ละตัว = diversification ได้ผล


if __name__ == "__main__":
    main()