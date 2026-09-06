# -*- coding: utf-8 -*-
"""Walk-forward / OOS validation: golden+regime+TP2.8 + MHM gate (mhm-min=2)

ทดสอบว่ากำไร +83.5% ของ config ที่ชนะ benchmark ใน session ก่อน (in-sample 3 ปี)
ยังอยู่ไหมเมื่อแบ่ง train/test ตาม walk-forward-validation skill:

  - ตัวเลข +83.5% = in-sample เต็ม 3 ปี (2023-09 → 2026-09) บน 30 เหรียญ 4h
  - แผน: 4 folds, test หน้าต่าง 6 เดือนแบบไม่ overlap (2024-09 → 2026-09)
      fold 1: train 365d ก่อน 2024-09-01 | test 2024-09-01 → 2025-03-01
      fold 2: train 365d ก่อน 2025-03-01 | test 2025-03-01 → 2025-09-01
      fold 3: train 365d ก่อน 2025-09-01 | test 2025-09-01 → 2026-03-01
      fold 4: train 365d ก่อน 2026-03-01 | test 2026-03-01 → 2026-09-01
  - สำหรับแต่ละ fold:
      1) PRE-REGISTERED: benchmark กับ gate min=2 (ค่าที่ประกาศไว้ก่อนรัน) เทียบกันบน test
      2) SELECTION ROBUSTNESS: tune mhm-min ∈ {1,2,3,4} บน train ด้วย Sharpe
         (เลือกจาก train เท่านั้น) แล้วเอาค่าที่เลือกไปเทสต์ OOS เทียบ benchmark

ข้อจำกัดข้อมูล: cache 4h เริ่ม 2021-08 → train ของ fold 1 (365d ก่อน 2024-09)
เริ่ม 2023-09 ได้ แต่ MHM horizon 60 วัน + warmup ทำให้ fold แรก train ได้สั้น
ประมาณ ~10 เดือน (harness จัดการ warmup เองด้วย buffer 70 วัน) — ตัวเลข train ของ
fold แรกจึงใช้เป็นแค่ "ข้อมูลช่วยเลือก" ไม่ใช่ผลหลัก ส่วน test ทั้ง 4 folds เต็ม 6 เดือน

รัน: python backtest_walkforward_mhm.py
ผลลัพธ์: backtest_results/walkforward_mhm_result.json + สรุปบน stdout
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

RESULTS_DIR = Path("backtest_results")
OUT_JSON = RESULTS_DIR / "walkforward_mhm_result.json"

# test windows = 6 เดือน ไม่ overlap ครบ 2 ปีล่าสุด (2024-09 → 2026-09)
FOLDS = [
    ("2024-09-01", "2025-03-01"),
    ("2025-03-01", "2025-09-01"),
    ("2025-09-01", "2026-03-01"),
    ("2026-03-01", "2026-09-01"),
]
TRAIN_DAYS = 365
TEST_DAYS = 180   # end_date quantize แล้ว test เริ่มที่ (train_end - 1 แท่ง) พอดี ไม่ overlap

COMMON = ["--symbols", "30", "--golden-only", "--regime-filter", "--tp-golden", "2.8"]
GATE = ["--mhm-gate", "--mhm-min"]
CANDIDATES = [1, 2, 3, 4]  # สำหรับ selection-robustness sweep บน train



def run(days: int, end_date: str, gate_min: int | None) -> dict | None:
    cmd = [sys.executable, "backtest_history.py", "--end-date", end_date,
           "--days", str(days), *COMMON]
    if gate_min is not None:
        cmd += [*GATE, str(gate_min)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("    RUN FAILED:", (r.stderr or r.stdout)[-400:])
        return None
    # harness บันทึกผลลง backtest_result_<days>d<tag>.json — อ่านไฟล์ใหม่สุด
    cands = sorted(RESULTS_DIR.glob("backtest_result_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        print("    no result json")
        return None
    try:
        d = json.loads(cands[0].read_text(encoding="utf-8"))
    except Exception as e:
        print("    parse error:", e)
        return None
    return d


def main() -> None:
    t0 = time.time()
    print("=" * 78)
    print("WALK-FORWARD: golden+regime+TP2.8 + MHM gate (min=2) — 4 folds, test 6 เดือน")
    print("(test windows abut train exactly: --days 180 + --end-date quantization)")
    print("=" * 78)

    rows = []
    for train_end, test_end in FOLDS:
        print(f"\n--- Fold: train 365d → {train_end} | test {train_end} → {test_end} ---")

        # 0) PRE-REGISTERED OOS: benchmark vs gate min=2 (ค่าที่ตั้งไว้ก่อนรัน)
        d_bench = run(TEST_DAYS, test_end, None)
        d_gate2 = run(TEST_DAYS, test_end, 2)
        if not d_bench or not d_gate2:
            print("  test run failed — ข้าม fold")
            continue

        def s(d, k, default=0.0):
            return d.get(k, default)

        n_bench = len(d_bench.get("trades", []))
        n_gate = len(d_gate2.get("trades", []))
        print(f"  TEST (OOS) benchmark : ret {s(d_bench,'total_return'):+7.1%} "
              f"DD {s(d_bench,'max_dd'):7.1%} sharpe {s(d_bench,'sharpe'):5.2f} "
              f"trades {n_bench}")
        print(f"  TEST (OOS) gate min=2: ret {s(d_gate2,'total_return'):+7.1%} "
              f"DD {s(d_gate2,'max_dd'):7.1%} sharpe {s(d_gate2,'sharpe'):5.2f} "
              f"trades {n_gate}")

        # 1) TUNE บน train: mhm-min ไหน Sharpe ดีสุด (train เท่านั้น)
        best_min, best_sh = 0, -9e9
        tune_log = []
        for m in CANDIDATES:
            d_tr = run(TRAIN_DAYS, train_end, m)
            if not d_tr:
                print(f"  train min={m}: no result")
                continue
            sh = d_tr.get("sharpe", 0.0)
            tr_n = len(d_tr.get("trades", []))
            tune_log.append({"mhm_min": m, "sharpe": sh,
                             "ret": d_tr.get("total_return", 0.0), "trades": tr_n})
            print(f"  train min={m}: ret {d_tr.get('total_return',0):+7.1%} "
                  f"sharpe {sh:5.2f} trades {tr_n}")
            if sh > best_sh:
                best_sh, best_min = sh, m
        print(f"  → เลือก min={best_min} (sharpe {best_sh:.2f}) บน train")

        # 2) TEST ค่าที่ tune ได้ OOS
        d_tuned = run(TEST_DAYS, test_end, best_min) if best_min else None
        tuned_block = None
        if d_tuned:
            tuned_block = {
                "mhm_min_chosen": best_min,
                "ret": d_tuned.get("total_return", 0.0),
                "max_dd": d_tuned.get("max_dd", 0.0),
                "sharpe": d_tuned.get("sharpe", 0.0),
                "trades": len(d_tuned.get("trades", [])),
            }
            print(f"  TEST (OOS) tuned min={best_min}: ret {tuned_block['ret']:+7.1%} "
                  f"DD {tuned_block['max_dd']:7.1%} sharpe {tuned_block['sharpe']:5.2f} "
                  f"trades {tuned_block['trades']}")

        rows.append({
            "train_end": train_end, "test_end": test_end,
            "bench": {"ret": s(d_bench, "total_return"), "max_dd": s(d_bench, "max_dd"),
                      "sharpe": s(d_bench, "sharpe"), "trades": n_bench,
                      "pnl": s(d_bench, "total_pnl"), "win": s(d_bench, "win_rate"),
                      "pf": s(d_bench, "profit_factor")},
            "gate2": {"ret": s(d_gate2, "total_return"), "max_dd": s(d_gate2, "max_dd"),
                      "sharpe": s(d_gate2, "sharpe"), "trades": n_gate,
                      "pnl": s(d_gate2, "total_pnl"), "win": s(d_gate2, "win_rate"),
                      "pf": s(d_gate2, "profit_factor")},
            "tuned": tuned_block,
            "train_tune": tune_log,
        })

    # ---- สรุปรวม ----
    print("\n" + "=" * 78)
    print("สรุป WALK-FORWARD (test = OOS 6 เดือน × 4 folds)")
    print("=" * 78)
    print(f"{'test end':<12} | {'bench ret':>9} {'gate2 ret':>9} {'Δ':>7} | "
          f"{'bench DD':>8} {'gate2 DD':>8} | {'bench sh':>8} {'gate2 sh':>8}")
    print("-" * 78)
    agg = {"bench_pnl": 0.0, "gate_pnl": 0.0, "gate_wins": 0, "folds": 0,
           "dd_wins": 0, "gate2_better_ret": 0, "gate2_better_dd": 0,
           "tuned_wins": 0, "tuned_folds": 0}
    for r in rows:
        b, g = r["bench"], r["gate2"]
        d_ret = g["ret"] - b["ret"]
        gate_better = g["ret"] > b["ret"]
        dd_better = g["max_dd"] > b["max_dd"]  # ค่าสูงกว่า = DD ตื้นกว่า
        if gate_better:
            agg["gate2_better_ret"] += 1
        if dd_better:
            agg["gate2_better_dd"] += 1
        agg["bench_pnl"] += b["pnl"]
        agg["gate_pnl"] += g["pnl"]
        agg["folds"] += 1
        t = r.get("tuned")
        if t:
            agg["tuned_folds"] += 1
            if t["ret"] > b["ret"]:
                agg["tuned_wins"] += 1
        print(f"{r['test_end']:<12} | {b['ret']:>+8.1%} {g['ret']:>+8.1%} {d_ret:>+6.1%} | "
              f"{b['max_dd']:>7.1%} {g['max_dd']:>7.1%} | "
              f"{b['sharpe']:>8.2f} {g['sharpe']:>8.2f}")
    if agg["folds"]:
        print("-" * 78)
        print(f"รวม PnL 4 folds: benchmark {agg['bench_pnl']:+,.0f} USDT vs "
              f"gate-min2 {agg['gate_pnl']:+,.0f} USDT")
        print(f"gate ชนะ return: {agg['gate2_better_ret']}/{agg['folds']} folds | "
              f"DD ตื้นกว่า: {agg['gate2_better_dd']}/{agg['folds']} folds")
        if agg["tuned_folds"]:
            print(f"tuned-on-train ชนะ return: {agg['tuned_wins']}/{agg['tuned_folds']} folds")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "config": {"folds": FOLDS, "train_days": TRAIN_DAYS,
                   "test_days": 183, "common": COMMON, "candidates": CANDIDATES},
        "folds": rows,
        "aggregate": agg,
        "elapsed_sec": round(time.time() - t0, 1),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nบันทึกผล: {OUT_JSON}")


if __name__ == "__main__":
    main()
