# 📌 Session Handoff — Trading Pipeline (อัปเดต 2026-09-04)

> เอกสารนี้เขียนเพื่อให้ session ใหม่ (หรือคนใหม่) ต่องานได้ทันทีโดยไม่งง
> โปรเจค: `E:\Trading_Automation` | สภาพแวดล้อม: Windows, Python 3.13, pytest 9.1, pandas/numpy

---

## 1. สถานะรวม

- **Pipeline ครบ 10 tasks (TDD), 46 tests ผ่าน** (`python -m pytest tests/`)
- **git:** 12 commits (ดู `git log --oneline`) — โค้ด pipeline ถูก commit ทั้งหมด
- **Scheduled tasks ลงทะเบียนแล้ว (Windows Task Scheduler):**
  - `TradingCycle` — ทุกวัน 01:00 → `run_task.cmd cycle`
  - `TradingCheck4h` — ทุก 4 ชม. → `run_task.cmd check`
  - โหมด Interactive only (รันเฉพาะตอน login) — log ที่ `logs/scheduled.log`
- **Paper journal:** ถูก reset ใหม่ 0 เทรด, equity 50,000 USDT — นาฬิกา 90 วันเริ่ม
  2026-09-04 (backup ของ v1 เก็บที่ `data/journal_v1_backup.db`)
- **46 tests ผ่าน** ครอบคลุม restore ข้าม process, equity model, kill-switch, duplicate-guard

## 2. Live Pipeline (config ปัจจุบันที่รันจริง)

| ส่วน | Config |
|---|---|
| สัญญาณ | **golden cross อย่างเดียว** (MA7×MA25, cross ≤5 แท่ง, RSI 45-75, volume ≥1.5x) — **turtle ปิด** |
| TP/SL | SL −2 ATR, **TP1 +2.8 ATR** (R:R 1.4) — ปิดเต็มที่ TP1/SL (default) |
| Partial TP | เปิดได้ผ่าน config `tp.partial_fraction` (เช่น 0.5 = ปิดครึ่งที่ TP1 แล้วปล่อยส่วนเหลือ) + `tp.trail_atr` (trailing กี่ ATR) หรือ `tp.tp2_atr` (ปิดที่ TP2 แทน trailing) — เริ่มต้น `partial_fraction: 0.0` = พฤติกรรมเดิม |
| AI governor | rule-based: บล็อก bear/range regime + event (FOMC/CPI ±1 วัน) — LLM ยังปิด (`use_llm=False`) |
| Risk ("รุก") | 3%/ไม้, max_total_risk 10%, max 5 ตำแหน่ง, 3 ขาดทุน/วันหยุด, DD −20% หยุด 1 สัปดาห์ |
| Execution | fee 0.1% + slippage 0.05% — equity = initial + realized pnl (หัก fee เท่านั้นตอนเปิด) |
| Persistence | ทุก process ใหม่ restore state จาก `data/journal.db` (source of truth) |
| Kill-switch | `python main.py kill` สร้าง `STOP` → cycle หยุดเปิดไม้ใหม่ |

**CLI:** `python main.py cycle|check|reconcile|status|kill`

## 3. Backtest Harness — `backtest_history.py`

รันซ้ำได้ deterministic (ข้อมูล cache ที่ `data/cache.db`, end_ts quantize กับแท่งปิด)

```bash
# golden benchmark (config ปัจจุบัน)
python backtest_history.py --days 1095 --symbols 30 --golden-only --regime-filter --tp-golden 2.8

# SMC variants
python backtest_history.py --days 1095 --symbols 30 --smc-only --smc-mode bos --regime-filter
python backtest_history.py --days 1095 --symbols 30 --smc-only --smc-mode reclaim --regime-filter

# FVG continuation
python backtest_history.py --days 1095 --symbols 30 --fvg --regime-filter

# Momentum rotation (cross-sectional)
python backtest_history.py --days 1095 --symbols 30 --rotation --rot-top 5 --rot-hold 30

# Golden + confluence (SMC ยืนยัน) + boost size
python backtest_history.py --days 1095 --symbols 30 --golden-only --regime-filter --tp-golden 2.8 --confluence sweep
python backtest_history.py --days 1095 --symbols 30 --golden-only --regime-filter --tp-golden 2.8 --confluence sweep --boost 2.0
python backtest_history.py --days 1095 --symbols 30 --golden-only --regime-filter --tp-golden 2.8 --confluence sweep --boost 2.0 --boost-only
```

Flags ทั้งหมด: `--days --equity --symbols --golden-only --smc-only --regime-filter --tp-golden --tp-turtle --tp-smc --smc-mode bos|reclaim --fvg --confluence none|sweep|fvg --boost --boost-only --momentum-top N --rotation --rot-top --rot-hold --rot-lookback`

## 4. ผลลัพธ์ทั้งหมด (เงินต้น 50k, 3 ปี, fee จริง — ตัวเลขซื่อสัตย์ post-bugfix)

### 4.1 กฎ v1 เดิม = แพ้
| ชุด | 2 ปี | 3 ปี |
|---|---|---|
| golden TP2.0 + turtle (v1 เดิม) | -37.4% | -50.9% |
| + bull-filter | -45.3% | -16.5% |

⚠️ ผล +27% ที่เคยรายงานช่วงแรก = **bug** (circuit breaker หยุดถาวรหลัง DD แรก) แก้แล้ว → ผลจริงเป็นลบ

### 4.2 Config ที่ชนะ (implement ใน live แล้ว)
| ชุด | 3 ปี | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| **golden-only + regime + TP2.8** | **+77.0%** | -17.7% | 50 | 64% | 2.00 |

- **Walk-forward ผ่าน:** TP2.0 แพ้ OOS (-1,516) / TP2.5-3.0 บวก (+3.6k ถึง +9.7k) — plateau กว้างไม่ใช่ spike
- กำไร 3 ปีติด (2023-2025) รวมปีที่ BTC ลง (-6.6% ใน 2025 ยังได้ +13,929) แต่ **2026 YTD แพ้ทุกแบบ** (win 40%, BTC ก็ -7.6%)
- Regime filter = ตัวสร้าง edge หลัก (win 37% → 64%, DD -47% → -17.7%)

### 4.3 SMC — แพ้ทุก variant
| variant | 3 ปี | MaxDD | Win | PF |
|---|---|---|---|---|
| sweep+BOS + regime | -35.8% | -50.2% | 38% | 0.73 |
| sweep+BOS (ไม่กรอง) | -20.3% | -50.1% | 44% | 0.91 |
| reclaim + regime | -29.3% | -29.8% | 20% | 0.73 |
| reclaim (ไม่กรอง) | -60.5% | -71.6% | 21% | 0.77 |
| TP กว้าง (3.5/4.0) | -25.5% / -19.0% | ~-50% | 33% | 0.86 |

### 4.4 FVG continuation — แย่ที่สุด
| variant | 3 ปี | MaxDD | Win |
|---|---|---|---|
| FVG + regime | -74.9% | -79.0% | 16% |
| FVG (ไม่กรอง) | -86.1% | -90.3% | 16% |

→ "ราคาย่อเข้า gap" ใน crypto = falling knife (research ภายนอกบอก FVG 64.8% ถูกเติม แต่ "ถูกเติม" ≠ "เด้งขึ้น")

### 4.5 Momentum rotation / relative-strength — ไม่ชนะ golden
| ชุด | 3 ปี | MaxDD |
|---|---|---|
| rotation top5/30d | +7.1% | -71.9% |
| rotation top10/30d | -7.4% | -77.6% |
| golden+regime+mom-top10 | +36.3% | -14.4% |
| golden+regime+mom-top15 | +40.7% | -17.2% |
| golden+mom-top10 (ไม่มี regime) | -39.4% | -53.8% |

### 4.6 SMC ประยุกต์กับ golden (คำถามล่าสุด) — feasible แต่ผล 2 ด้าน
| ชุด | 3 ปี | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| benchmark golden+regime+TP2.8 | +77.0% | -17.7% | 50 | 64% | 2.00 |
| + กรองเฉพาะจังหวะ SMC (3%) | +13.3% | **-6.2%** | 15 | 53% | 1.66 |
| + กรอง + boost 2x | +30.4% | **-11.0%** | 13 | 62% | 2.10 |
| + **boost-only 2x** (เพิ่มไซส์เฉพาะไม้ที่ผ่าน SMC) | **+81.2%** | -17.7% | 49 | 63% | 1.88 |

**ข้อสรุปสำคัญ:**
1. "กรองจังหวะสมบูรณ์แบบ" ลด DD มาก (-17.7%→-6.2%) แต่ win rate **ไม่ดีขึ้น** (53-62% vs 64%) → SMC ไม่ได้ "เลือกไม้ดีกว่า" แค่เทรดน้อยลง (คัดออก 271 ครั้ง รวมไม้ที่ชนะ)
2. boost-only 2x = +81.2% (+4% จาก benchmark) แต่ win rate เท่าเดิม → กำไรที่เพิ่มคือ **leverage ล้วน ๆ** ไม่ใช่ "ประเมินโอกาสดี" ตามที่ตั้งสมมุติฐานไว้
3. ตัวอย่าง 13-15 ไม้/3 ปี น้อยเกินไป — ส่วนต่าง win rate อาจเป็น noise

## 5. บทเรียนหลัก (จากการทดสอบทั้งหมด)

1. **Regime filter (bull-only) คือตัวเปลี่ยนเกมจริง** — ปรากฏซ้ำทุกการทดสอบ (ไม่มี = แพ้ทุกครั้ง)
2. **Fee คือศัตรูตัวจริง** — v1 แพ้เพราะเทรดถี่ (fee 23-36% ของเงินต้น) edge ต่อไม้แทบเป็นศูนย์
3. **R:R ต้องเผื่อ fee** — golden TP2.0 (R:R 1:1) ต้อง win >50% แต่ได้ ~45% → แพ้; TP2.8 (R:R 1.4) ต้อง win >42% ได้ 64% → ชนะ
4. **SMC/FVG แบบกลไกล้วน ๆ ไม่มี edge ใน crypto 4h** — win rate จริง 16-44% ตรงกับ research ภายนอก (38-48%) — คนที่กำไรคือ survivorship bias + discretion + filter ที่ encode ไม่ได้
5. **2026 YTD ระบบอ่อนแอ** (win 40%) — ช่วง sideway/ลง ยังไม่มีทางรอด ต้องเฝ้าดูใน paper

## 6. ไฟล์สำคัญ

| ไฟล์ | คืออะไร |
|---|---|
| `pipeline/` | โค้ดหลัก (models, data_layer, signal_engine, risk_engine, journal, ai_governor, execution, orchestrator, config) |
| `main.py` | CLI entrypoint |
| `tests/` | 46 tests |
| `backtest_history.py` | backtest harness (deterministic, cache) |
| `backtest_50k_result.md` | ผล v1 แพ้ + บทวิเคราะห์ |
| `backtest_variants_edge_result.md` | TP sweep + walk-forward (พบ config ชนะ) |
| `smc_backtest_result.md` | ผล SMC ทุก variant |
| `backtest_more_strategies_result.md` | FVG / momentum / rotation / confluence+boost |
| `trading_history_summary.md`, `news_trading_summary.md`, `legendary_traders_summary.md` | งานวิจัยเชิงคุณภาพ (Dalio, ข่าว, วงใน) |
| `run_task.cmd` | wrapper สำหรับ scheduled tasks |
| `data/journal.db` | paper journal (source of truth) |

**git status:** โค้ด pipeline commit ครบ; ไฟล์ backtest/research ยัง **untracked** (ไม่ได้ commit — ตัดสินใจได้ว่าจะเก็บไหม)

## 7. ขั้นต่อไปที่เสนอ (ยังไม่ได้ทำ)

1. **Paper 90 วันกำลังรัน** — ตรวจ scorecard รายเดือน: `python main.py status` (ต้องได้ ≥20 เทรด + ผ่าน 9 gates ถึงพิจารณา live)
2. **Partial TP / TP2 จริง** — ✅ implement แล้ว (config `tp.partial_fraction` / `tp.trail_atr` / `tp.tp2_atr`) — แต่ backtest 3 ปีพบว่า**ปิดเต็มที่ TP1 ชนะกว่า** (+77% vs partial 0.5+trail +70%) ยังไม่เปิดใช้ใน live — ถ้าจะลองเปิดผ่าน config.json
3. **LLM governor A/B** — เปิด `use_llm=True` เทียบ rule-based ใน paper
4. **5 ปี backtest (รวมตลาดหมี 2022)** — ตรวจว่า golden+regime+TP2.8 อยู่ครบวัฏจักรไหม
5. **ตัดสินใจ commit ไฟล์ backtest/research** เข้า git (ตอนนี้ untracked หมด)
6. ถ้าจะใช้ "เพิ่มไซส์ตามโอกาส" จริง — หลักฐานชี้ว่า boost ควรผูกกับ **regime/คุณภาพ validation** ไม่ใช่ SMC (SMC ไม่ได้เพิ่ม win rate)