# -*- coding: utf-8 -*-
"""E3 data CLI — ตรวจไฟล์จริงก่อนรัน backtest

  python -m e3.data.cli checktz data/XAUUSD_M1.csv --preset mt5 --tz Europe/Helsinki
  python -m e3.data.cli inspect data/XAUUSD_M15.csv --tz Europe/Helsinki --json-out reports/dq.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from .calendar import FXCalendar
from .loader import Loader
from .schema import PRESETS, SourceSpec


def _make_spec(args) -> SourceSpec:
    preset = PRESETS.get(args.preset, PRESETS["generic"])
    kwargs = dict(preset)
    kwargs.update({k: v for k, v in (
        ("source_tz", args.tz),
        ("spread_column", args.spread_column),
        ("path", args.path),
    ) if v is not None})
    return SourceSpec(**kwargs)


def cmd_checktz(args) -> int:
    """นับ bar ต่อชั่วโมง UTC — ดู pattern เปิด/ปิด/เที่ยงคืนเพื่อยืนยัน tz"""
    spec = _make_spec(args)
    loader = Loader(cache_path=None)
    bars = loader.normalize(spec)
    hours = Counter((b.ts // 3600) % 24 for b in bars)
    print(f"file: {spec.path}")
    print(f"source_tz: {spec.source_tz}   bars: {len(bars)}")
    print("hour(UTC) : count")
    for h in range(24):
        n = hours.get(h, 0)
        bar_str = "#" * min(60, n * 60 // max(1, max(hours.values())))
        print(f"{h:02d}        : {n:7d} {bar_str}")
    # วันต่อชั่วโมงเปิด — ถ้า tz ผิด จุดเปิด/ปิดจะไม่ตรง 22:00/23:00 UTC
    cal = FXCalendar()
    sunday_open = sum(hours.get(h, 0) for h in (22, 23))
    print(f"\nSunday 22-23 UTC bars: {sunday_open} (ต้อง > 0 ถ้า tz ถูก)")
    return 0


def cmd_inspect(args) -> int:
    spec = _make_spec(args)
    loader = Loader(cache_path=args.cache if args.cache else None)
    bars, rep = loader.load(spec, force_rescan=args.no_cache)
    d = rep.as_dict()
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False, default=str)
        print(f"report → {args.json_out}")
    print(f"bars: {rep.total_bars}")
    if rep.first_ts and rep.last_ts:
        f_ts = rep.first_ts
        l_ts = rep.last_ts
        print("span:", f_ts, "→", l_ts,
              f"({(l_ts - f_ts) / 86400:.1f} days)")
    print("issues by code:", json.dumps(rep.by_code(), indent=2))
    print(f"excluded days: {len(rep.excluded_days)} / span {rep.day_span()}d")
    if rep.spread_samples:
        print(f"spread: n={rep.spread_samples} p50={rep.spread_p50:.3f} p95={rep.spread_p95:.3f} $/oz")
    print("ok_for_backtest:", rep.ok_for_backtest())
    return 0 if rep.ok_for_backtest() else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="e3.data.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("checktz", "inspect"):
        sp = sub.add_parser(name)
        sp.add_argument("path")
        sp.add_argument("--preset", default="generic", choices=list(PRESETS))
        sp.add_argument("--tz", default=None, help="override source_tz")
        sp.add_argument("--spread-column", default=None)
        if name == "inspect":
            sp.add_argument("--json-out", default=None)
            sp.add_argument("--cache", default=None, help="cache db path")
            sp.add_argument("--no-cache", action="store_true")
        sp.set_defaults(func=cmd_checktz if name == "checktz" else cmd_inspect)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
