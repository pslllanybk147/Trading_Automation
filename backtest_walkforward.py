"""Walk-forward validation for the crowd long/short filter (golden+regime+TP2.8).

วิธีตามสกิล walk-forward-validation:
  - แต่ละ fold: train = ช่วงก่อนหน้า, test = ช่วงถัดไป (ไม่ overlap)
  - เลือกค่า pct ที่ Sharpe ดีสุดบน TRAIN เท่านั้น
  - นำ pct นั้นไปเทสต์บน TEST (OOS — ระบบไม่เคยเห็น)
  - เทียบ benchmark (ไม่มีกรอง) บน TEST เดียวกัน

รัน: python backtest_walkforward.py
(ต้องมี data cache 4h + crowd_cache แล้ว — ถ้ายังไม่มี รันครั้งแรกจะดาวน์โหลดเอง)
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

CANDIDATES = [0.0, 0.6, 0.7, 0.8]   # 0.0 = ไม่กรอง
FOLDS = [
    # (train_end, test_end) — train ยาว 365 วัน, test ยาว ~182 วัน
    ("2024-09-01", "2025-03-01"),
    ("2025-03-01", "2025-09-01"),
    ("2025-09-01", "2026-03-01"),
]
TRAIN_DAYS = 365
# test_days คำนวณจาก test_end - train_end
TEST_DAYS = 182
COMMON = ["--symbols", "30", "--golden-only", "--regime-filter", "--tp-golden", "2.8"]
TMP = Path("data/wf_tmp.json")


def run(end_date: str, days: int, crowd_pct: float) -> dict | None:
    cmd = [sys.executable, "backtest_history.py",
           "--end-date", end_date, "--days", str(days),
           *COMMON]
    if crowd_pct > 0:
        cmd += ["--crowd-pct", str(crowd_pct)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("  RUN FAILED:", r.stderr[-500:])
        return None
    # หาไฟล์ JSON ล่าสุดที่บันทึก
    cands = sorted(Path(".").glob("backtest_result_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        return None
    try:
        d = json.loads(cands[0].read_text(encoding="utf-8"))
    except Exception:
        return None
    return d


def main() -> None:
    print("=" * 78)
    print("WALK-FORWARD: crowd filter (golden+regime+TP2.8) — 3 folds")
    print("=" * 78)
    rows = []
    for train_end, test_end in FOLDS:
        print(f"\n--- Fold train..{train_end} | test {train_end}..{test_end} ---")

        # 1) TUNE บน train: ลองทุก pct เลือก Sharpe สูงสุด
        best_pct, best_sharpe = 0.0, -9e9
        for pct in CANDIDATES:
            d = run(train_end, TRAIN_DAYS, pct)
            if not d:
                print(f"  train pct={pct}: no result")
                continue
            sh = d.get("sharpe", 0.0)
            ret = d.get("total_return", 0.0)
            print(f"  train pct={pct}: ret {ret:+.1%} sharpe {sh:.2f} "
                  f"trades {len(d.get('trades', []))}")
            if sh > best_sharpe:
                best_sharpe, best_pct = sh, pct
        print(f"  → เลือก pct={best_pct} (sharpe {best_sharpe:.2f}) บน train")

        # 2) TEST บน OOS: pct ที่เลือก vs benchmark (pct=0)
        d_tuned = run(test_end, TEST_DAYS, best_pct)
        d_bench = run(test_end, TEST_DAYS, 0.0)
        if not d_tuned or not d_bench:
            print("  test run failed")
            continue
        rows.append({
            "train_end": train_end, "test_end": test_end,
            "pct_chosen": best_pct,
            "bench": d_bench, "tuned": d_tuned,
        })
        def _s(d, k):
            return d.get(k, 0.0)
        print(f"  TEST (OOS): tuned pct={best_pct} "
              f"ret {_s(d_tuned,'total_return'):+.1%} / DD {_s(d_tuned,'max_dd'):.1%} "
              f"/ trades {len(d_tuned.get('trades', []))}")
        print(f"  TEST (OOS): benchmark    "
              f"ret {_s(d_bench,'total_return'):+.1%} / DD {_s(d_bench,'max_dd'):.1%} "
              f"/ trades {len(d_bench.get('trades', []))}")

    # 3) สรุป
    print("\n" + "=" * 78)
    print("สรุป: tuned (pct เลือกจาก train) เทียบ benchmark บน OOS")
    print(f"{'fold test':<22} {'pct':>4} {'tuned ret':>10} {'bench ret':>10} "
          f"{'tuned DD':>9} {'bench DD':>9} {'tuned win':>9} {'bench win':>9}")
    n_win = 0
    for r in rows:
        b, t = r["bench"], r["tuned"]
        t_ret, b_ret = t.get("total_return", 0), b.get("total_return", 0)
        t_dd, b_dd = t.get("max_dd", 0), b.get("max_dd", 0)
        t_w = t.get("win_rate", 0), b.get("win_rate", 0)
        mark = "✓" if t_ret > b_ret else "✗"
        if t_ret > b_ret:
            n_win += 1
        print(f"{r['test_end']:<22} {r['pct_chosen']:>4} {t_ret:>+9.1%} {b_ret:>+9.1%} "
              f"{t_dd:>8.1%} {b_dd:>8.1%} {t_w[0]:>8.1%} {t_w[1]:>8.1%}  {mark}")
    print(f"\nTuned ชนะ benchmark: {n_win}/{len(rows)} folds (OOS)")


if __name__ == "__main__":
    main()