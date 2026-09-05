# 📌 Session Handoff — Trading Pipeline (อัปเดต 2026-09-05)

> เอกสารนี้เขียนเพื่อให้ session ใหม่ (หรือคนใหม่) ต่องานได้ทันทีโดยไม่งง
> โปรเจค: `E:\Trading_Automation` | สภาพแวดล้อม: Windows, Python 3.13, pytest 9.1, pandas/numpy

---

## 1. สถานะรวม

- **Pipeline ครบ 10 tasks (TDD), 56 tests ผ่าน** (`python -m pytest tests/`)
- **git:** 21 commits (ดู `git log --oneline`) — โค้ด pipeline + ไฟล์ research/backtest/skills commit ทั้งหมด
- **Scheduled tasks ลงทะเบียนแล้ว (Windows Task Scheduler):**
  - `TradingCycle` — ทุกวัน 01:00 → `run_task.cmd cycle`
  - `TradingCheck4h` — ทุก 4 ชม. → `run_task.cmd check`
  - โหมด Interactive only (รันเฉพาะตอน login) — log ที่ `logs/scheduled.log`
- **Paper journal:** ถูก reset ใหม่ 0 เทรด, equity 50,000 USDT — นาฬิกา 90 วันเริ่ม
  2026-09-04 (backup ของ v1 เก็บที่ `data/journal_v1_backup.db`)
- **56 tests ผ่าน** ครอบคลุม restore ข้าม process, equity model, kill-switch, duplicate-guard + partial TP/trailing/TP2

## 2. Live Pipeline (config ปัจจุบันที่รันจริง)

| ส่วน | Config |
|---|---|
| สัญญาณ | **golden cross อย่างเดียว** (MA7×MA25, cross ≤5 แท่ง, RSI 45-75, volume ≥1.5x) — **turtle ปิด** |
| TP/SL | SL −2 ATR, **TP1 +2.8 ATR** (R:R 1.4) — ปิดเต็มที่ TP1/SL (default) |
| Partial TP | เปิดได้ผ่าน config `tp.partial_fraction` / `tp.trail_atr` / `tp.tp2_atr` (ดู §4.7) — **ปิดอยู่** (`partial_fraction: 0.0` = ปิดเต็มที่ TP1 เพราะ backtest ไม่ชนะ) |
| AI governor | rule-based: บล็อก bear/range regime + event (FOMC/CPI ±1 วัน) — LLM ยังปิด (`use_llm=False`) |
| Risk ("รุก") | 3%/ไม้, max_total_risk 10%, max 5 ตำแหน่ง, 3 ขาดทุน/วันหยุด, DD −20% หยุด 1 สัปดาห์ |
| Execution | fee 0.1% + slippage 0.05% — equity = initial + realized pnl (หัก fee เท่านั้นตอนเปิด) |
| Persistence | ทุก process ใหม่ restore state จาก `data/journal.db` (source of truth) |
| Kill-switch | `python main.py kill` สร้าง `STOP` → cycle หยุดเปิดไม้ใหม่ |

**Config เพิ่มเติม (ยังไม่เปิดใน live):**
```json
{"tp": {"partial_fraction": 0.5, "trail_atr": 1.5, "tp2_atr": 0}}
```

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

# Partial TP + trailing / TP2 (implement แล้วใน harness + paper pipeline)
python backtest_history.py --days 1095 --symbols 30 --golden-only --regime-filter --tp-golden 2.8 --partial-tp 0.5 --trail-atr 1.5
python backtest_history.py --days 1095 --symbols 30 --golden-only --regime-filter --tp-golden 2.8 --partial-tp 0.5 --tp2-atr 3.0
```

Flags ทั้งหมด: `--days --equity --symbols --golden-only --smc-only --regime-filter --tp-golden --tp-turtle --tp-smc --smc-mode bos|reclaim --fvg --confluence none|sweep|fvg --boost --boost-only --momentum-top N --rotation --rot-top --rot-hold --rot-lookback --partial-tp --trail-atr --tp2-atr --funding-max --funding-min --crowd-pct --end-date`

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

### 4.7 Partial TP / TP2 / trailing — ไม่ชนะปิดเต็มที่ TP1 (implement แล้วแต่ยังปิดใน live)
| ชุด | 3 ปี | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| benchmark golden+regime+TP2.8 (ปิดเต็ม TP1) | **+77.0%** | -17.7% | 50 | 64% | 2.00 |
| partial 0.3 + trail 1.5 | +67.2% | -17.7% | 50 | 64% | 1.90 |
| partial 0.5 + trail 1.5 | +70.0% | -17.7% | 50 | 64% | 1.93 |
| partial 0.5 + trail 2.0 | +59.7% | -17.7% | 50 | 64% | 1.82 |
| partial 0.5 + trail 3.0 | +53.0% | -17.9% | 49 | 63% | 1.78 |
| partial 0.5 + trail 4.0 | +59.6% | -19.0% | 49 | 63% | 1.87 |
| partial 0.5 + TP2 24 ATR (แทบไม่ TP2) | +67.7% | -17.2% | 50 | 64% | 1.93 |
| partial 0.7 + trail 1.5 | +72.8% | -17.7% | 50 | 64% | 1.96 |
| partial 0.8 + trail 1.0 | +77.3% | -17.7% | 50 | 64% | 2.01 |

**ข้อสรุปสำคัญ:**
1. **ไม่มี partial variant ไหนชนะ benchmark อย่างมีนัย** — ตัวสูงสุด (0.8+trail1) เท่ากันเป๊ะ (+77.3% vs +77.0%) = ใกล้เคียงปิดเต็ม TP1 อยู่ดี; trail ยิ่งกว้าง ยิ่งแพ้ (0.5+trail3-4 → +53-60%)
2. **DD ไม่ได้ดีขึ้น** — ทุกรูปแบบ ~-17.7% เท่า benchmark; partial TP ไม่ใช่ตัวลดความเสี่ยง
3. Trail แคบ (1.0-1.5) เสีย upside หลัง TP1 มากกว่าได้ — หุ้น crypto 4h วิ่งต่อหลัง breakout ไม่คุ้มที่จะปิดก่อน
4. → **decision: เปิดใช้เฉพาะถ้าอยาก A/B ใน paper** (`tp.partial_fraction` ใน config.json) — default ยังปิดเต็มที่ TP1

### 4.8 Backtest 5 ปี (2021-09 → 2026-09, รวมตลาดหมี 2022) — ✅ ยืนยัน golden+regime ครบวัฏจักร
| ตัวชี้วัด | golden+regime (5 ปี) | BTC hold |
|---|---|---|
| ผลตอบแทนรวม | **+77.2%** (CAGR 12.1%) | +53.9% |
| Max Drawdown | **-15.2%** | -77.0% |
| Win rate / PF | 56.8% / 1.65 | — |
| เทรด | 81 ครั้ง | — |
| Alpha vs BTC | +23.3% | — |

**รายปี:**
| ปี | ระบบ | สถานการณ์ตลาด |
|---|---|---|
| 2021 (Q4) | -14.0% | ช่วงท้าย bull |
| **2022** | **+9.4%** | ⚠️ ตลาดหมี BTC -77% |
| 2023 | +23.3% | bull |
| 2024 | +32.0% | bull |
| 2025 | +17.6% | bull แต่ BTC ปีนี้ลง |
| 2026 YTD | -1.6% | sideway/ลง |

**ข้อสรุปสำคัญ:**
1. **รอดตลาดหมี 2022 จริง** — +9.4% ขณะที่ BTC -77% (regime filter บล็อก 469 ครั้ง ช่วงหมีแทบไม่เทรด แล้วกลับมาเทรดตอน bull)
2. **ไม่กรอง regime 5 ปี = แพ้ -18.9% (DD -40.3%)** — ต่างชัดเจน = regime filter คือหัวใจจริง
3. **DD 5 ปี -15.2% ดีกว่า 3 ปี (-17.7%)** — ตัวเลขซื่อสัตย์ขึ้นเมื่อมี 2022 อยู่ในชุด
4. 2026 YTD ยังอ่อน (-1.6%) — ช่วง sideway/ลงไม่มีทางรอด แต่ไม่ขาดทุนหนัก → ต้องเฝ้าดูใน paper ต่อ
5. → config นี้ผ่านการพิสูจน์ครบวัฏจักร (bull + หมี + sideway) เก็บเป็น benchmark ต่อ

### 4.9 Funding-rate filter (จากวิจัย community 5 ปี) — ไม่ชนะ benchmark เหมือน crowd filter
| ชุด | 5 ปี | CAGR | MaxDD | เทรด | Win | PF | blocked(funding) |
|---|---|---|---|---|---|---|---|
| benchmark golden+regime+TP2.8 | **+77.2%** | 12.1% | -15.2% | 81 | 56.8% | 1.65 | 0 |
| fundmax 0.0003 (ข้ามเมื่อ funding สูง = crowded long) | +73.8% | 11.7% | -15.0% | 77 | 57.1% | 1.65 | 4 |
| fundmax 0.0002 | +59.2% | 9.8% | -16.0% | 73 | 56.2% | 1.57 | 9 |
| fundmin 0.00003 (เทรดเฉพาะ funding สูง = momentum ยืนยัน) | +68.7% | 11.0% | -16.0% | 55 | 60.0% | 2.02 | 31 |
| fundmin 0.00005 | +69.3% | 11.1% | -16.0% | 47 | 61.7% | 2.28 | 39 |
| fundmin 0.0001 (แรงเกินไป) | +19.2% | 3.6% | -15.6% | 27 | 55.6% | 1.53 | 61 |

**ข้อสรุปสำคัญ:**
1. **ไม่มี funding variant ไหนชนะ benchmark (+77.2%)** — fundmax ยิ่งกรองยิ่งแย่ (funding สูงมักมาพร้อม bull momentum ที่ดี); fundmin ปรับ win rate/PF ดีขึ้น (62%/2.28) แต่ตัดไม้กำไรใหญ่ออกไปด้วย → return ลด เหลือ 47-55 ไม้
2. **DD ไม่ดีขึ้น** (~-15 ถึง -16% เท่า benchmark) — เหมือน partial TP: ฟังดูดีแต่ไม่ใช่ตัวลดความเสี่ยง
3. funding data ขยายครบ 5 ปีแล้ว (`data/funding_cache.json` 2021-08 → ปัจจุบัน, gitignore ไว้) — รันซ้ำได้
4. → **decision: ไม่เปิดใน pipeline** — สอดคล้องกับ crowd filter ที่ reject ไป (single-factor filter ไม่มี edge เหนือ regime)

### 4.10 Volatility squeeze → breakout เป็น regime state เสริม (5 ปี) — ไม่ชนะเหมือนกัน
| ชุด | 5 ปี | CAGR | MaxDD | เทรด | Win | PF | Alpha vs BTC |
|---|---|---|---|---|---|---|---|
| benchmark golden+regime+TP2.8 (bull-only) | **+77.2%** | 12.1% | -15.2% | 81 | 56.8% | 1.65 | +23.3% |
| regime = squeeze→breakout **อย่างเดียว** (`--regime-mode squeeze`) | +29.4% | 5.3% | -29.5% | 111 | 48.6% | 1.18 | -25.0% |
| regime = bull **OR** squeeze→breakout (`--regime-mode or`) | +42.2% | 7.3% | -25.8% | 157 | 48.4% | 1.17 | -12.2% |

**คำนิยาม squeeze→breakout** (เพิ่มใน harness แล้ว, `--regime-mode {bull,squeeze,or}`):
Bollinger(20,2σ) bandwidth ต่ำกว่าค่าเฉลี่ย rolling 60 แท่ง (แรงอัด) → แล้ว close ทะลุ high 20 แท่งก่อน + ATR(14) > ค่าเฉลี่ย 20 แท่ง (แรงระเบิด) — state ต้องเกิดภายใน 6 แท่งก่อน breakout

**ข้อสรุปสำคัญ:**
1. **squeeze แทน bull = แย่กว่ามาก** (+29.4% / DD -29.5%) — state นี้ดักจับ bear-market rally + ช่วงเด้งหลังอัดตัว ซึ่ง win rate จริง ~48% ไม่พอรอด fee
2. **เอามาเสริม (bull OR squeeze) ก็ยังแพ้**: เทรดเพิ่ม 81 → 157 แต่ไม้ที่เพิ่มมา 85 ไม้ **PnL -5,140 net / win 42%** (แพ้ทุกปี ยกเว้น 2021, 2024) → ลาก benchmark จาก +77.2% ลงมาที่ +42.2% และ DD กว้างขึ้นเป็น -25.8%
3. กลไกเดียวกับ funding/crowd filter: **จังหวะที่ bull filter บล็อกไว้ (นอกโครงสร้างขาขึ้น) ส่วนใหญ่คือกับดัก ไม่ใช่ต้นเทรนด์ที่แท้จริง** — การคลายเกณฑ์กรอง = ใส่ไม้คุณภาพต่ำกลับเข้าไป
4. harness รองรับ mode นี้แล้ว (`--regime-mode`) แต่ → **decision: ไม่เปิดใน pipeline** — benchmark bull-only ยังยืนเป็น config ที่ดีที่สุด

### 4.11 Squeeze→breakout เป็น entry confluence ใน bull (`--squeeze-entry`, 5 ปี) — กรองไม้ดีทิ้ง ไม่ชนะ
| ชุด | 5 ปี | CAGR | MaxDD | เทรด | Win | PF | Avg PnL/ไม้ |
|---|---|---|---|---|---|---|---|
| benchmark golden+regime+TP2.8 | **+77.2%** | 12.1% | -15.2% | 81 | 56.8% | 1.65 | +477 |
| golden cross เฉพาะในหน้าต่าง squeeze→breakout (bull ยังกรอง) | +53.6% | 9.0% | -19.3% | 52 | 57.7% | 1.81 | +516 |

**วิธี:** `--squeeze-entry` — golden cross จะเข้าก็ต่อเมื่อมี squeeze→breakout เกิดภายใน 6 แท่งก่อน (ยังอยู่ใต้ bull gate เดิม) = ทดสอบไอเดีย "ไม้ใหญ่ ปิดเร็ว รอจังหวะระเบิด"

**ข้อสรุป:**
1. ไม้ที่เหลือมีคุณภาพดีขึ้นจริง (win 57.7%, PF 1.81, Avg PnL/ไม้สูงกว่า) — **แต่กรองไม้ดีทิ้งไป 32 ไม้ที่ PnL รวม +7,554 / win 53%** → ผลรวมต่ำกว่า benchmark (+53.6% vs +77.2%) และ DD กว้างขึ้น (-19.3%)
2. squeeze→breakout ฟังดูเป็น "จังหวะที่ดีกว่า" แต่ความจริงแล้ว golden cross ปกติใน bull จับไม้ใหญ่ได้หลากหลายกว่า — การบังคับให้ต้องเกิดแรงอัดก่อน แค่ทำให้พลาดไม้
3. รวมกับ §4.10: squeeze→breakout แพ้ทั้งตอนเป็น regime state และตอนเป็น entry filter → **decision: ไม่เปิด** — golden+regime+TP2.8 ยังเป็นคำตอบสุดท้ายของโจทย์ "เทรดเป็นช่วง ไม้ใหญ่ ปิดเร็ว รอสัญญาณ" (81 ไม้/5 ปี, เทรดเฉพาะ bull, ปิด TP เร็วอยู่แล้ว)

### 4.12 XAUUSD (ทอง) — golden+regime ใช้กับทองไม่ได้ (feasibility, 2021-2025)
| ชุด | 5 ปี | MaxDD | เทรด | Win | PF | เทียบ gold hold |
|---|---|---|---|---|---|---|
| **gold hold (XAUUSD buy&hold)** | **+126.5%** | -21.8% | — | — | — | — |
| golden+regime+TP2.8 (config เดิม) | +1.4% | -2.5% | 7 | 57.1% | 1.28 | แพ้ขาด (-125% alpha) |
| golden TP2.8 (ไม่กรอง regime) | -11.7% | -28.7% | 141 | 48.9% | 0.84 | แพ้ขาด |
| golden TP6.0 (ถือยาวขึ้น, ไม่กรอง) | +19.8% | -16.8% | 121 | 34.7% | 1.22 | ยังแพ้ hold |

**ที่มา:** `fetch_xauusd.py` (histdata M1 ฟรี → resample 4h → cache.db) + harness flags ใหม่ `--symbol-list / --no-fetch / --no-volume / --fee-rate / --slippage`; ช่วง 2021-01 → 2025-12 (ทอง bull ใหญ่: 2023 +12.9%, 2024 +27.2%, 2025 +64.5%)

**rerun ด้วย fee แบบ CFD จริง ($0.3/oz ≈ 0.005%/side + slip 0.002%)** — ตอบคำถาม "แพ้เพราะ fee ตั้งผิดหรือไม่มี edge":
| ชุด | fee 0.1% (Binance-style) | fee 0.005% (CFD จริง) | DD (fee จริง) |
|---|---|---|---|
| golden+regime+TP2.8 | +1.4% | +3.4% | -2.2% |
| golden TP2.8 (ไม่กรอง) | -11.7% | **+30.8%** | -12.5% |
| golden TP6.0 (ถือยาว) | +19.8% | **+69.3%** | -6.3% |
| SMC reclaim (sweep ล้วน) | -13.0% | +0.1% | -3.9% |
| SMC bos | -4.3% | -1.3% | -5.9% |
| gold buy&hold | — | **+126.5%** | -21.8% |

**ข้อสรุป (หลัง fee จริง):**
1. **fee ที่ตั้งไว้แพงเกินจริงมีผลจริง** — golden TP2.8 กลับมาจาก -11.7% → +30.8% ทันทีที่ใช้ fee จริง (ตอน 0.1% fee กินไป 11.5k จาก 50k); harness ตอนนี้รองรับ `--fee-rate/--slippage` แล้ว
2. **แต่ระบบยังแพ้ gold hold อยู่ดี** — ตัวดีสุด (golden TP6) ได้ +69.3% vs hold +126.5% แม้ DD ดีกว่าเยอะ (-6.3% vs -21.8%)
3. **regime filter ยังเป็นปัญหาหลัก** — บล็อก 151 ครั้งเหลือ 7 ไม้ (fee ไม่ใช่สาเหตุของจุดนี้)
4. **SMC แพ้ทุก fee level** — reclaim PF 1.01 / bos PF 0.80 = ไม่มี edge จริง ๆ
5. → **decision เดิมยืนยัน: อย่าเอา golden+regime ไปเทรดทอง** — ถ้าจะทำทองจริงต้อง trend-following ถือยาว (ตัวเลข TP6 ชี้ทางว่า "ถือให้ยาวขึ้น" คือทิศที่ถูก) + ไม่พึ่ง volume + ใช้ fee จริง

### 4.13 SMC liquidity sweep บน XAUUSD (2021-2025) — ไม่มี edge เหมือนบน crypto
| ชุด | 5 ปี | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| **gold hold** | **+126.5%** | -21.8% | — | — | — |
| SMC sweep **reclaim** (เข้าทันทีที่หลุด pool แล้วปิดกลับ = "sweep ล้วน") | -13.0% | -14.0% | 49 | 26.5% | 0.50 |
| SMC sweep + **BOS** (รอโครงสร้างหักขึ้นยืนยัน) | -4.3% | -7.5% | 11 | 36.4% | 0.46 |

**ที่มา:** `--smc-only --smc-mode reclaim/bos` บน XAUUSD 5 ปี (2021-2025) — SMC ไม่พึ่ง volume จึงใช้ได้ตรง ๆ กับทอง

**ข้อสรุป:**
1. **"sweep ล้วน" (ส่วนที่คิดว่ามีหลักฐานสุด) ก็แพ้** — win rate จริง 26.5% / PF 0.50 (worse กว่า bos ด้วยซ้ำ เพราะเข้าทุกแท่งหลอก) — ตรงกับที่ SMC บน crypto แพ้ (win 16-44%) และตรงกับ r/Forex ที่ backtest 20 ปีแล้วได้ ~1%/ปี
2. กลไกเดียวกัน: stop-hunt มีจริงในตลาด แต่การเข้าตาม pattern เปล่า ๆ ไม่รู้ว่า sweep ไหนจะเด้ง — ต้อง context/regime เพิ่มถึงจะพอมีโอกาส
3. → **decision: ปิดโจทย์ SMC ทั้ง crypto และทอง** — ส่วนประกอบ SMC (sweep/OB/FVG) ไม่มี edge แบบกลไกล้วน ๆ ในตลาดทั้งสอง

### 4.14 ออกแบบ signal ทองใหม่ด้วย skill trading-signals (2021-2025, fee จริง 0.005%) — turtle/ADX/seasonal ไม่ชนะ golden TP6

อัปเดตหลัง install community skill `trading-signals` (scientiacapital) — นำแนวทางจาก reference มา implement ใน harness:
- **turtle/Donchian breakout** (`--turtle-only --turtle-entry N --turtle-exit-n M`): เข้าเมื่อ close ทะลุ high N แท่ง (System 1=20, System 2=55) + exit แบบ classic = close หลุด low M แท่งก่อน (opposite Donchian — ปล่อยกำไรวิ่ง) แทน TP คงที่
- **ADX regime** (`--regime-mode adx`): trending_up = ADX(14) > 25 + +DI > -DI (Markov 4-state ใน skill) แทน MA20/50 ที่บล็อกทอง 151 ครั้ง
- **seasonal filter** (`--seasonal`): เข้าเฉพาะเดือนทองแข็งแรง (Jan-Feb, Jul-Sep — ตาม commodities research)

| ชุด (fee จริง, 5 ปี) | ผล | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| **gold hold** | **+126.5%** | -21.8% | — | — | — |
| **golden TP6 (best จาก §4.12)** | **+69.3%** | **-6.3%** | 121 | ~30% | ~2.0 |
| golden TP8 / TP10 | +68.6% / +60.8% | -20.4% | 102 / 88 | 29% / 25% | 2.0 / 1.96 |
| golden TP6 + ADX regime (thresh 25 / 20) | +20.9% / +31.5% | -5.2% / -6.2% | 29 / 67 | 41% / 34% | 2.12 / 1.70 |
| golden TP6 + seasonal | +25.6% | -4.9% | 54 | 37% | 1.86 |
| turtle S1 (20/10) ไม่กรอง | +7.6% | -10.0% | 57 | 40% | 1.27 |
| turtle S1 + ADX regime | +1.2% | -7.5% | 41 | 39% | 1.05 |
| turtle S2 (55/20) + ADX | +14.8% | -10.3% | 30 | 37% | 1.98 |
| turtle daily-scale (110/55) | +18.9% | -10.4% | 23 | 30% | 2.30 |

**ข้อสรุป:**
1. **ทุกแนวทางจาก skill แพ้ golden TP6 ล้วน** — ยิ่ง "ฉลาด" ยิ่งกรองไม้ดีทิ้ง: ADX regime บล็อก 119-151 ครั้ง (ทองมีช่วง trending แค่บางจังหวะ แต่ golden cross ที่เหลือก็กำไร), seasonal บล็อก 92 ครั้ง (ตัดไม้ Jan-Jun กลางปี 2024 ที่เป็นไม้ใหญ่), turtle ทุก variant ได้ PF สูงแต่ return ต่ำกว่าเพราะเข้า-ออกช้า
2. **จุดสูงสุดของการ "ถือยาวขึ้น" คือ TP6** — TP8/TP10 ได้กำไรเท่าเดิมแต่ DD กว้างขึ้นเป็น -20% (เท่า gold hold) — ยิ่งถือยาวกว่านี้ไม่ช่วย
3. **skill ชี้ตรงว่าสัญญาณหลักของทองคือ real rates (DFII10) + DXY + COT** — สิ่งเหล่านี้คือ macro/positioning ที่ไม่มีใน cache ปัจจุบัน (ต้อง fetch FRED/CFTC เพิ่ม) — เป็นทางเดียวที่ยังไม่ได้ทดสอบ แต่เป็นข้อมูลระดับสัปดาห์ ต้อง redesign การทดสอบใหม่ทั้งหมด
4. → **decision: ปิดโจทย์ "ออกแบบ signal ทองใหม่ด้วยเทคนิค price-based"** — เทคนิค price-action ทุกแบบ (golden/turtle/ADX/seasonal/SMC) ไม่ชนะถือทองเฉย ๆ ถ้าอยากได้ทองจริงต้องเริ่มจาก macro signal (real rates) ซึ่งอยู่นอกขอบเขตระบบ price-based ปัจจุบัน — flag ทั้งหมดเก็บไว้ใน harness (`--turtle-only/--turtle-entry/--turtle-exit-n/--regime-mode adx/--seasonal`)

### 4.15 Macro signal ทอง (real yield + DXY) — สุดท้ายก็ไม่ชนะ golden TP6 เหมือนเดิม

ปิดโจทย์ "ทางเดียวที่เหลือ" จาก §4.14: implement macro gate จาก skill trading-signals
(commodities.md: real yield 10Y TIPS = master gold signal, DXY = inverse ~70-80%)

**ข้อมูล:** `fetch_macro.py` — real yield จาก Treasury.gov daily real yield curve (TC_10YEAR =
FRED DFII10 ทุกค่า — verify แล้ว) + DXY จาก Yahoo DX-Y.NYB → `data/macro_cache.json` รายวัน 2021-2026
(FRED เองมี rate limit หนักจาก IP นี้ เลยใช้ Treasury/Yahoo แทน)

**เป็น entry filter (golden TP6 + macro gate, fee จริง):**
| ชุด | ผล | MaxDD | เทรด | PF | blocked |
|---|---|---|---|---|---|
| **golden TP6 (base)** | **+69.3%** | -6.3% | 121 | ~2.0 | — |
| + macro either (real_yield หรือ dxy ลด 20d) | +46.4% | -8.0% | 87 | 1.79 | 51 |
| + macro real_yield 20d | +35.4% | -6.5% | 65 | 1.85 | 78 |
| + macro dxy 20d | +28.5% | -11.8% | 66 | 1.68 | 75 |
| + macro both | +18.9% | -6.5% | 44 | 1.74 | 102 |

**เป็น holding strategy (ถือทองเมื่อ macro อนุญาต รายวัน ไม่มี SL/TP):**
| กลยุทธ์ | 5 ปี | เทรด | Win |
|---|---|---|---|
| **gold buy&hold** | **+124.6%** | — | — |
| real_yield ลด 60d (ถือ) | +54.1% | 35 | 60% |
| dxy ลด 20d (ถือ) | +53.0% | 55 | 45% |
| real_yield ลด 20d (ถือ) | +41.7% | 53 | 55% |
| real_yield+dxy ลด 20d | +25.2% | 56 | 50% |

**ข้อสรุป:**
1. **real yield ลด = ทองขึ้นจริง** (60% win rate, avg +1.35%/รอบที่ win 60d) — แต่สลับเข้า-ออก 35-56 รอบ/5 ปี ทำให้พลาดไม้ใหญ่กลางเทรนด์ (2024-2025 real yield ลดต่อเนื่อง ทองพุ่งตลอด)
2. **ทุกการใช้ macro แพ้ golden TP6 ล้วน** — เป็น filter ตัดไม้ดี (เช่นเดียวกับ ADX/seasonal/turtle) เป็น holding ก็แพ้ buy&hold
3. → **decision: ปิดโจทย์ทองครบทุกทางแล้ว** — ตั้งแต่ price-based (golden/turtle/ADX/seasonal/SMC) จนถึง macro (real yield/DXY): ไม่มีอะไรชนะถือทองเฉย ๆ 5 ปี; ระบบ crypto golden+regime ยังเป็นคำตอบเดียวที่พิสูจน์แล้ว และไม่ได้ออกแบบมาสำหรับทอง (ทอง = trend ตรง ควรถือ ไม่ใช่เทรด) — เก็บ `fetch_macro.py` + `--macro-regime` ไว้ใน harness เผื่อใช้กับสินทรัพย์อื่นในอนาคต

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
| `tests/` | 56 tests |
| `backtest_history.py` | backtest harness (deterministic, cache, partial TP/trailing/TP2, funding/crowd filter, `--regime-mode {bull,squeeze,or,adx}` + `--squeeze-entry`, `--turtle-only/--turtle-entry/--turtle-exit-n` (turtle classic), `--seasonal`, `--macro-regime/--macro-win` (real yield/DXY gate), `--symbol-list/--no-fetch/--no-volume/--fee-rate/--slippage` สำหรับสินทรัพย์นอก Binance) |
| `fetch_xauusd.py` | โหลด XAUUSD M1 จาก histdata ฟรี → resample 4h → cache (ทดสอบทองแล้ว) |
| `fetch_macro.py` | โหลด macro ทอง: real yield 10Y TIPS (Treasury.gov) + DXY (Yahoo) → `data/macro_cache.json` (FRED มี rate limit เลยใช้ทางเลือก) |
| `backtest_walkforward.py` | walk-forward อัตโนมัติ (เลือก pct จาก train → ทดสอบ OOS) |
| `backtest_results/` | ผล backtest JSON ทั้งหมด (จัดระเบียบเข้าโฟลเดอร์แล้ว) |
| `backtest_50k_result.md` | ผล v1 แพ้ + บทวิเคราะห์ |
| `backtest_variants_edge_result.md` | TP sweep + walk-forward (พบ config ชนะ) |
| `smc_backtest_result.md` | ผล SMC ทุก variant |
| `backtest_more_strategies_result.md` | FVG / momentum / rotation / confluence+boost |
| `community_strategy_research.md` / `community_strategies_research.md` ฯลฯ | งานวิจัยเชิงคุณภาพ (Dalio, ข่าว, วงใน, community techniques + ผล funding filter) |
| `run_task.cmd` | wrapper สำหรับ scheduled tasks |
| `data/journal.db` | paper journal (source of truth — schema migrate เพิ่มคอลัมน์ partial TP แล้ว) |

**git status:** โค้ด pipeline + ไฟล์ research/backtest/skills commit ครบ (253 ไฟล์ tracked) — ตรวจได้ด้วย `git status` ควรสะอาด

## 7. ขั้นต่อไปที่เสนอ (ยังไม่ได้ทำ)

1. **Paper 90 วันกำลังรัน** — ตรวจ scorecard รายเดือน: `python main.py status` (ต้องได้ ≥20 เทรด + ผ่าน 9 gates ถึงพิจารณา live)
2. **Partial TP / TP2 จริง** — ✅ implement แล้วใน harness + paper pipeline (config `tp.partial_fraction` / `tp.trail_atr` / `tp.tp2_atr`) — แต่ backtest 3 ปีสรุปว่า**ปิดเต็มที่ TP1 ชนะกว่า** (ดู §4.7) → ยังไม่เปิดใน live
3. **LLM governor A/B** — เปิด `use_llm=True` เทียบ rule-based ใน paper
4. **5 ปี backtest (รวมตลาดหมี 2022)** — ✅ ทำแล้ว (ดู §4.8) — golden+regime+TP2.8 ผ่านครบวัฏจักร: +77.2% / DD -15.2% รอดหมี 2022 ได้ +9.4%
5. **Commit ไฟล์ backtest/research** — ✅ ทำแล้ว (2 commits: ผล backtest 85 ไฟล์ → `backtest_results/` + เอกสาร/skills) — เหลือแค่ตัดสินใจเรื่อง `data/cache.db` (89MB, gitignore ไว้แล้ว)
6. ถ้าจะใช้ "เพิ่มไซส์ตามโอกาส" จริง — หลักฐานชี้ว่า boost ควรผูกกับ **regime/คุณภาพ validation** ไม่ใช่ SMC (SMC ไม่ได้เพิ่ม win rate)
7. **USDGUSDT error HTTP 400 ถาวร** — ถูก skip ทุก cycle ดูว่า symbol นี้ถูกลิสต์ผิดไหม
8. **Funding-rate filter** — ✅ ทดสอบแล้ว (ดู §4.9) ไม่ชนะ benchmark เหมือน crowd filter → ไม่เปิด
9. **Volatility squeeze → breakout** — ✅ ทดสอบครบ 2 รูปแบบแล้ว: เป็น regime state เสริม (§4.10) และเป็น entry confluence ใน bull `--squeeze-entry` (§4.11) — แพ้ทั้งคู่ → ไม่เปิด — ปิดโจทย์ "เทรดเป็นช่วง ไม้ใหญ่ ปิดเร็ว" ได้ข้อสรุปว่า golden+regime+TP2.8 เดิมคือคำตอบ
10. **ทอง (XAUUSD) ด้วย golden+regime** — ✅ feasibility ทดสอบแล้ว (§4.12): แพ้ gold hold ขาด (+1.4% vs +126.5%) เพราะ regime filter บล็อกหมด + ไม่มี volume + ทองเป็นเทรนด์ตรงไม่เหมาะ TP เร็ว → ไม่ทำ; มี `fetch_xauusd.py` + flags ใน harness เผื่ออยากออกแบบ signal ทองใหม่
11. **SMC liquidity sweep บนทอง** — ✅ ทดสอบแล้ว (§4.13): reclaim (sweep ล้วน) -13.0% / PF 0.50 และ bos -4.3% / PF 0.46 — ไม่มี edge เหมือนบน crypto → ปิดโจทย์ SMC ทั้งสองตลาด
12. **ออกแบบ signal ทองใหม่ด้วย skill (turtle/ADX/seasonal)** — ✅ ทดสอบแล้ว (§4.14): ทุกแนวทางจาก trading-signals skill แพ้ golden TP6 (+69.3%) และทอง buy&hold (+126.5%) — ทางเดียวที่เหลือคือ macro signal (real rates/DXY/COT)
13. **Macro signal ทอง (real yield/DXY)** — ✅ ทดสอบแล้ว (§4.15): implement `fetch_macro.py` (Treasury real yield + Yahoo DXY) + `--macro-regime` — ทุก variant แพ้ golden TP6 และ buy&hold → **ปิดโจทย์ทองครบทุกทางแล้ว**: price-based ทุกแบบ + macro ทุกแบบไม่มีอะไรชนะถือทองเฉย ๆ