# -*- coding: utf-8 -*-
"""Cache hygiene — ตรวจ cache.db รายสัปดาห์: เหรียญไหนตาย/ใกล้ตาย/สด

ที่มา: เหรียญ delist (DAI/XMR/RNDR/TON) ยังนอนใน cache นานหลายเดือนก่อนถูกพบ —
is_stale() กันตอนรัน pipeline แล้ว แต่ไม่มีใคร "สรุปให้ดู" ว่า cache มีขยะหรือเปล่า
สคริปต์นี้จึงเป็นเครื่องมือตรวจสุขภาพ + ตัดขยะ (ไม่แก้ pipeline)

การจัดชั้น (จากอายุแท่งสุดท้าย — candle close time):
  OK       < 7 วัน           ปกติ (pipeline ดึงอยู่)
  AGING    7 วัน – 6 เดือน   ดูต่อ — เหรียญหยุดซื้อขายชั่วคราว/ตลาดตาย หรือแค่ไม่ได้ fetch
  STALE    6 เดือน – 1 ปี    น่าจะ delist ไปแล้ว — เช็ค announcement ก่อนเก็บต่อ
  ARCHIVE  > 1 ปี            เก่าชัดเจน (dead data) — --prune จะลบ
การจัดชั้นแบบนี้ทำให้ delist ใหม่ ๆ (อายุ 1-2 เดือน) โผล่ในรายงานทันทีที่ AGING
ไม่ต้องรอถึงปี — เหมือน TONUSDT ที่ถ้ามีสคริปต์นี้ก่อนจะถูกเห็นตั้งแต่อายุ 1 สัปดาห์

รัน:
  python cache_hygiene.py              # รายงานอย่างเดียว (exit 0 เสมอ)
  python cache_hygiene.py --prune      # ลบเฉพาะ ARCHIVE (> 1 ปี) + VACUUM
  python cache_hygiene.py --prune --also-stale   # ลบ STALE ด้วย (ระวัง: เหรียญ
                                       # ที่กลับมา list ใหม่จะหาย ต้อง fetch ครั้งเดียว)
  python cache_hygiene.py --json out.json        # ผลแบบ JSON (สำหรับ alert/CI)

exit code: 0 = ไม่มี STALE/ARCHIVE, 1 = มี (ให้ scheduled task/log สะท้อนปัญหา)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

CACHE_DB = Path("data/cache.db")
DAY = 86400

# เกณฑ์จัดชั้นเป็น "อายุ" (วัน)
AGING_AFTER = 7
STALE_AFTER = 180      # ~6 เดือน
ARCHIVE_AFTER = 365    # ~1 ปี


def classify(age_days: float) -> str:
    if age_days >= ARCHIVE_AFTER:
        return "ARCHIVE"
    if age_days >= STALE_AFTER:
        return "STALE"
    if age_days >= AGING_AFTER:
        return "AGING"
    return "OK"


def sweep(db_path: Path = CACHE_DB, now_ts: int | None = None) -> list[dict]:
    """อ่าน cache.db → รายการ {symbol, interval, bars, first, last, age_days, status}"""
    if now_ts is None:
        now_ts = int(time.time())
    if not db_path.exists():
        raise FileNotFoundError(f"{db_path} not found")
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT symbol, interval, COUNT(*), MIN(ts), MAX(ts) "
            "FROM candles GROUP BY symbol, interval"
        ).fetchall()
    finally:
        conn.close()
    out = []
    for sym, tf, n, t0, t1 in rows:
        age = max(0.0, (now_ts - t1) / DAY)
        out.append({
            "symbol": sym, "interval": tf, "bars": n,
            "first": t0, "last": t1, "age_days": round(age, 1),
            "status": classify(age),
        })
    out.sort(key=lambda r: (-r["age_days"], r["symbol"]))
    return out


def prune(rows: list[dict], db_path: Path = CACHE_DB,
          also_stale: bool = False, dry_run: bool = False) -> list[dict]:
    """ลบแถวของ symbol/interval ที่จัดชั้น ARCHIVE (หรือ STALE ถ้า --also-stale)"""
    targets = [r for r in rows
               if r["status"] == "ARCHIVE" or (also_stale and r["status"] == "STALE")]
    if dry_run or not targets:
        return targets
    conn = sqlite3.connect(db_path)
    try:
        for r in targets:
            conn.execute("DELETE FROM candles WHERE symbol=? AND interval=?",
                         (r["symbol"], r["interval"]))
        conn.commit()
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()
    return targets


def format_report(rows: list[dict], now_ts: int) -> str:
    lines = [
        f"Cache hygiene report — {datetime.fromtimestamp(now_ts, UTC):%Y-%m-%d %H:%M} UTC",
        f"{'symbol':<12} {'tf':<4} {'bars':>7} {'last':<12} {'age(d)':>8}  status",
        "-" * 60,
    ]
    counts = {"OK": 0, "AGING": 0, "STALE": 0, "ARCHIVE": 0}
    for r in rows:
        counts[r["status"]] += 1
        if r["status"] == "OK" and r["age_days"] < AGING_AFTER:
            continue  # รายงานเฉพาะสิ่งที่ต้องสนใจ; สรุปจำนวน OK ท้ายรายงาน
        last = datetime.fromtimestamp(r["last"], UTC).strftime("%Y-%m-%d")
        lines.append(f"{r['symbol']:<12} {r['interval']:<4} {r['bars']:>7} "
                     f"{last:<12} {r['age_days']:>8.1f}  {r['status']}")
    lines.append("-" * 60)
    lines.append(f"pairs: {len(rows)} | OK {counts['OK']} | AGING {counts['AGING']} "
                 f"| STALE {counts['STALE']} | ARCHIVE {counts['ARCHIVE']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="cache.db hygiene sweep")
    ap.add_argument("--db", default=str(CACHE_DB))
    ap.add_argument("--prune", action="store_true",
                    help="ลบ ARCHIVE (> 1 ปี) + VACUUM")
    ap.add_argument("--also-stale", action="store_true",
                    help="ลบ STALE (6 เดือน-1 ปี) ด้วย — เหรียญที่กลับมา list ใหม่จะถูก fetch ใหม่อัตโนมัติ")
    ap.add_argument("--dry-run", action="store_true",
                    help="แสดงสิ่งที่จะลบโดยไม่ลบจริง")
    ap.add_argument("--json", dest="json_out", default="",
                    help="เขียนผลเป็น JSON ที่ path นี้")
    args = ap.parse_args(argv)

    now_ts = int(time.time())
    rows = sweep(Path(args.db), now_ts)
    print(format_report(rows, now_ts))

    if args.prune or args.dry_run:
        removed = prune(rows, Path(args.db), also_stale=args.also_stale,
                        dry_run=args.dry_run)
        if removed:
            verb = "จะลบ (dry-run)" if args.dry_run else "ลบแล้ว"
            for r in removed:
                print(f"  {verb}: {r['symbol']} {r['interval']} ({r['bars']} bars)")
        else:
            print("prune: ไม่มีอะไรให้ลบ")

    if args.json_out:
        Path(args.json_out).write_text(
            __import__("json").dumps({"generated": now_ts, "rows": rows},
                                     ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"JSON: {args.json_out}")

    bad = [r for r in rows if r["status"] in ("STALE", "ARCHIVE")]
    if bad:
        print(f"\n⚠ พบ {len(bad)} pair ที่ควรจัดการ (STALE/ARCHIVE) — "
              f"รัน python cache_hygiene.py --prune")
        return 1
    print("\n✓ cache สะอาด")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
