# -*- coding: utf-8 -*-
"""E1 data CLI — sync / ตรวจสุขภาพข้อมูล / สรุป funding

  python -m e1.cli sync BTCUSDT                # ดึง funding + klines (spot+perp 1h)
  python -m e1.cli summary BTCUSDT             # สถิติ funding (annualized, %บวก, p95)
  python -m e1.cli inspect BTCUSDT             # quality report ทั้งสามชุด
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import requests

from .loader import E1Loader, funding_summary
from .quality import scan_all


def _fmt_ms(ms: int | None) -> str:
    if ms is None:
        return "-"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def cmd_sync(args) -> int:
    sess = requests.Session()
    loader = E1Loader(args.cache)
    try:
        nf = loader.sync_funding(sess, args.symbol)
        ns = loader.sync_klines(sess, args.symbol, args.interval, "spot")
        np_ = loader.sync_klines(sess, args.symbol, args.interval, "perp")
        print(f"{args.symbol}: +{nf} funding, +{ns} spot klines, +{np_} perp klines")
    finally:
        loader.close()
    return 0


def cmd_summary(args) -> int:
    loader = E1Loader(args.cache)
    try:
        events = loader.load_funding(args.symbol)
    finally:
        loader.close()
    if not events:
        print("ไม่มีข้อมูล funding — รัน sync ก่อน", file=sys.stderr)
        return 1
    s = funding_summary(events)
    print(json.dumps({
        **s,
        "first": _fmt_ms(s["first_ms"]),
        "last": _fmt_ms(s["last_ms"]),
    }, indent=2))
    return 0


def cmd_inspect(args) -> int:
    loader = E1Loader(args.cache)
    try:
        funding, spot, perp, reports = loader.load_symbol(args.symbol, args.interval)
    finally:
        loader.close()
    fail = False
    for rep in reports:
        print(f"[{rep.symbol}] funding={rep.n_funding} spot={rep.n_spot} perp={rep.n_perp} "
              f"span {_fmt_ms(rep.first_ms)} → {_fmt_ms(rep.last_ms)}")
        codes = rep.by_code()
        print("  issues:", json.dumps(codes))
        if not rep.ok_for_backtest():
            fail = True
    return 1 if fail else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="e1.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("sync", "summary", "inspect"):
        sp = sub.add_parser(name)
        sp.add_argument("symbol")
        sp.add_argument("--interval", default="1h")
        sp.add_argument("--cache", default="e1/data/cache_e1.db")
        sp.set_defaults(func={"sync": cmd_sync, "summary": cmd_summary,
                              "inspect": cmd_inspect}[name])
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
