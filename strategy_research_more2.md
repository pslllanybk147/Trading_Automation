# 🔬 วิจัยต่อเนื่อง 4 แนวทาง (รอบ 3): Partial TP, Mean Reversion 1h, Portfolio, Funding Rate

> วันที่: 2026-09-04 | เงินต้น 50,000 USDT | fee 0.1% + slippage 0.05% | 3 ปี (1095 วัน) | 30 เหรียญ
> ต่อจาก `strategy_research_more.md` — ทดสอบครบ 4 ข้อที่ค้าง: partial TP/trailing, MR บน 1h, multi-strategy portfolio, on-chain/funding data

---

## 🏆 Benchmark (ทุกการทดสอบเทียบกับชุดนี้)

**golden+regime+TP2.8 (config กลางที่ pipeline ใช้อยู่):**
| 3 ปี | MaxDD | เทรด | Win | PF | Sharpe |
|---|---|---|---|---|---|
| +77.0% | -17.7% | 50 | 64% | 2.00 | 1.40 |

---

## 1. Partial TP / Trailing (Item 3) — ไม่ชนะ benchmark

**วิธีการ:** ปิดบางส่วนที่ TP1 (2.8 ATR) แล้วส่วนเหลือตาม trailing stop จาก high สุด ระยะ N ATR
(หรือปิดที่ TP2 คงที่) — ทดสอบบน golden+regime+TP2.8 เดิมทุกประการ

| Config | 3 ปี | MaxDD | Sharpe | PF | Win |
|---|---|---|---|---|---|
| **ปิดเต็มที่ TP1 (benchmark)** | **+77.0%** | -17.7% | 1.40 | 2.00 | 64% |
| partial 50% + trail 1.5 ATR | +70.0% | -17.7% | 1.36 | 1.93 | 64% |
| partial 50% + trail 2.0 ATR | +59.7% | -17.7% | 1.23 | 1.82 | 64% |
| partial 50% + trail 3.0 ATR | +53.0% | -17.9% | 1.11 | 1.78 | 63% |
| partial 50% + TP2 4.0 ATR | +67.7% | -17.3% | 1.29 | 1.93 | 64% |
| partial 70% + trail 1.5 ATR | +72.9% | -17.7% | 1.38 | 1.96 | 64% |
| partial 80% + trail 1.0 ATR | +77.3% | -17.7% | 1.40 | 2.01 | 64% |

**ข้อสรุป:** Partial TP **ไม่ได้เพิ่มกำไร** — ยิ่งปิดเร็ว/trail แน่น ยิ่งเสียผลตอบแทน (tail ใหญ่ของ golden
คือตัวทำเงิน การตัด tail ออก = ตัดกำไร) ที่ดีสุดคือ partial 80% + trail 1.0 ≈ benchmark พอดี
(เพราะแทบเท่ากับปิดเต็มที่ TP1 อยู่แล้ว) → **ไม่ต้องเปลี่ยน execution** การปิดเต็มที่ TP1
แค่ปิดที่ TP1 ยังเป็นทางเลือกที่ดีที่สุด

---

## 2. Mean Reversion บน 1h (Item 1) — แพ้เมื่อเทียบ golden แต่เปิดบทเรียนสำคัญ

**กติกา:** RSI(14) < 30 แล้วเด้งกลับเหนือ 30 → เข้า | SL -2 ATR | TP +2.8 ATR
**ข้อมูล:** ดึง 1h ใหม่ 30 เหรียญ 3 ปี (~26,700 แท่ง/เหรียญ) เข้า cache.db แยกจาก 4h

| Config | 3 ปี | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| MR 1h + HTF bias (daily MA20) | -17.6% | -19.7% | 51 | 33% | 0.74 |
| MR 1h + regime 1h | -8.5% | -8.5% | 3 | 0% | 0.00 |
| MR 1h ไม่กรอง (falling knife) | -40.9% | -41.1% | 133 | 38% | 0.73 |
| **MR 1h + HTF bias + ไม่ล็อก daily gate** | **+78.8%** | -25.3% | 469 | 52% | 1.09 |

**บทเรียนสำคัญสองอย่าง:**
1. **Daily gate คือตัวฆ่า MR:** ใน live pipeline เราเข้าได้วันละ 1 ครั้งที่แท่ง 00:00 เท่านั้น
   แต่จังหวะ oversold bounce บน 1h ต้องเข้าเร็ว (ภายใน 1-2 ชม.) รอถึงเที่ยงคืน = เข้าช้าเกินไป
   → พอปลดล็อก (เข้าได้ทุกแท่ง) MR 1h กลับมาบวกได้ (+78.8%) แต่ MaxDD -25.3% แย่กว่า golden
2. **Win rate 52% + PF 1.09 = edge บางมาก:** กำไรส่วนใหญ่คือ "เด้งกลับเร็ว" บนเหรียญที่ HTF เป็นขาขึ้น
   แต่พอเจอ falling near SL โดนเก็บชุดใหญ่ ตัวเลขจึงเปราะ (เทียบ golden win 64% PF 2.0)

**ข้อสรุป:** MR 1h ไม่ชนะ golden (DD แย่กว่า, edge บาง, ต้องรัน cycle ถี่ขึ้น = เปลี่ยนสถาปัตยกรรม)
→ **ไม่เอาเข้า pipeline** แต่ใช้เป็นตัวกระจายพอร์ต (ข้อ 3)

---

## 3. Multi-Strategy Portfolio (Item 2) — diversification ได้ผลเล็กน้อยจริง ✅

**วิธีการ:** แบ่งเงินต้นเป็น sub-account อิสระ 2 ก้อน → รวม daily equity curve
(เครื่องมือใหม่: `backtest_portfolio.py` + ทุก JSON บันทึก `daily_curve` แล้ว)

**ผล (3 ปี, 50k รวม):**

| Composition | 3 ปี | MaxDD | Sharpe |
|---|---|---|---|
| golden 100% (benchmark) | +77.0% | -17.7% | 1.40 |
| **golden 85% / MR-1h 15%** | **+77.3%** | **-16.4%** | **1.50** |
| golden 80% / MR-1h 20% | +77.4% | -16.3% | 1.47 |
| golden 50% / MR-1h 50% | +77.9% | -19.0% | 1.11 |
| golden+fundmin 90% / MR-1h 10% | +33.2% | **-6.7%** | 1.06 |

**ข้อสรุป:**
- Correlation ของ daily return ระหว่าง golden กับ MR-1h = **+0.05 เท่านั้น** (แทบไม่สัมพันธ์กันจริง!)
  → diversification มีที่ทาง
- แต่ MR มี DD ลึก (-25%) พอผสมเกิน 20% ค่าเฉลี่ย DD เริ่มพัง → จุดดีสุดคือ **golden 85% / MR 15%**
  ดีกว่า benchmark เล็กน้อย (Sharpe 1.40→1.50, DD -17.7%→-16.4%) แต่ตัวอย่างน้อย ต้องระวัง overfit
- ถ้าอยาก DD ต่ำมากจริง ๆ: golden+fundmin 90%/MR 10% ได้ DD แค่ -6.7% แต่ผลตอบแทน -33% (เสียกำไรครึ่ง)

**คำแนะนำ:** ยังเก็บ golden อย่างเดียวเป็นแกนหลัก; portfolio แบบ 85/15 เป็นการปรับปรุงเล็กน้อย
แต่ยังต้องให้ paper 90 วันยืนยัน golden ตัวเดียวก่อน ค่อยคิดเพิ่มสาขา

---

## 4. Funding Rate เป็นตัวกรอง (Item 4) — ทดสอบด้วยข้อมูลจริงจาก Binance fapi

**ข้อมูล:** funding history (USDT-M perp) 30 เหรียญ 3 ปี ดึงจาก public API `fapi.binance.com`
→ cache ที่ `data/funding_cache.json` (ส่วนใหญ่ 8h ต่อรอบ, บางตัว 4h)
**สมมติฐานจากงานวิจัย:** funding บวกสูง = long แน่นเกินไป (crowded) → เสี่ยง contrarian pullback

**ทดสอบบน golden+regime+TP2.8 (กรองด้วย funding เฉลี่ย 7 วัน):**

| ตัวกรอง | 3 ปี | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| ไม่กรอง (benchmark) | +77.0% | -17.7% | 50 | 64% | 2.00 |
| ข้ามถ้า funding > 0.05% (กรอง crowded) | +75.3% | -17.7% | 48 | 65% | 2.04 |
| ข้ามถ้า funding > 0.03% | +68.4% | -17.7% | 47 | 64% | 1.98 |
| ข้ามถ้า funding > 0.01% | +37.9% | -17.7% | 35 | 60% | 1.75 |
| **เทรดเฉพาะ funding > 0.01% (momentum ยืนยัน)** | **+28.1%** | **-7.7%** | 18 | 67% | 2.46 |
| เทรดเฉพาะ funding > 0.02% | +6.7% | -5.8% | 7 | 57% | 1.69 |

**ข้อสรุปที่ตรงข้ามกับ intuitions:**
1. **"กรอง crowded long ออก" = แพ้:** golden เป็นกลยุทธ์ momentum อยู่แล้ว funding สูง = เทรนด์แรง
   = ไม้ที่ golden ชนะบ่อย → กรองออก = ตัดกำไร (77% → 38%) ตรงข้ามกับงานวิจัย SMC/contrarian
   ที่ออกแบบสำหรับเล่นสวนทาง
2. **"เทรดเฉพาะ funding บวกแรง" = กำไรน้อยกว่าแต่ตัวอย่างคุณภาพสูงสุด:** PF 2.46, DD -7.7%
   — เทรด 18 ไม้/3 ปี บอกว่า "จังหวะที่คนทั้งตลาดมั่นใจมาก + golden cross + bull = setup คุณภาพสูง"
   แต่ตัวอย่าง 18 ไม้น้อยเกินไปจะสรุป และผลตอบแทน +28% ยังแพ้ golden ล้วน
3. **Funding ไม่ได้เพิ่ม edge ให้ golden** — มันแค่ "กรองปริมาณเทรด" เหมือน boost/confluence
   ที่ผ่านมา: ลดจำนวนลด DD แต่ก็ลดกำไร

---

## สรุปรวมทุกรอบ (กลยุทธ์ทั้งหมดที่ทดสอบแล้ว 12+ แบบ)

| แนวทาง | 3 ปี | MaxDD | เทียบ benchmark |
|---|---|---|---|
| **golden+regime+TP2.8** 🏆 | +77.0% | -17.7% | — |
| golden 85% / MR-1h 15% | +77.3% | -16.4% | Sharpe ดีขึ้นเล็กน้อย (1.50) |
| boost-only 2x (SMC ยืนยัน) | +81.2% | -17.7% | = leverage ไม่ใช่ edge |
| partial TP (ทุกแบบ) | ≤ +77% | -17.7% | แพ้/เท่าตัว |
| golden + funding-min 0.01% | +28.1% | -7.7% | DD ต่ำสุด แต่กำไรน้อย |
| MR 1h + HTF (no gate) | +78.8% | -25.3% | DD แย่ |
| HTF daily bias | +29.2% | -31.2% | แพ้ |
| rotation/momentum/meanrev/FVG/SMC | < 0 หรือ ≤ +41% | — | แพ้หมด |

**คำตอบตรง ๆ:** ยังไม่มีอะไรโค่น golden+regime+TP2.8 ได้จริง — ตัวที่ "ดีขึ้น" (85/15 portfolio, boost)
เป็นเพียงการปรับปรุงเล็กน้อยหรือ leverage ที่ DD เท่าเดิม และตัวอย่างยังน้อยเกินไป
**สิ่งเดียวที่ให้มุมมองใหม่จริง ๆ คือ funding-min** (setup คุณภาพสูงมาก: PF 2.46, DD -7.7%)
แต่เก็บไว้เป็นไอเดีย paper ในอนาคต ไม่ใช่เปลี่ยนกลยุทธ์ตอนนี้

---

## ไฟล์/คำสั่งใหม่

```bash
# flags ใหม่ใน backtest_history.py
--interval 1h                  # ใช้ข้อมูล 1h (fetch อัตโนมัติ, cache แยก)
--mr1h                         # ทางลัด: interval 1h + meanrev + htf_bias
--no-daily-gate                # research: เข้าได้ทุกแท่ง (ไม่ล็อกวันละครั้ง)
--partial-tp 0.5 --trail-atr 2.0   # partial TP + trailing
--partial-tp 0.5 --tp2-atr 4.0     # partial TP + TP2 คงที่
--funding-max 0.0005           # ข้ามเทรดถ้า funding เฉลี่ย 7 วัน > ค่า
--funding-min 0.0001           # เทรดเฉพาะ funding เฉลี่ย 7 วัน > ค่า

# portfolio combine (ต้องการ daily_curve ใน JSON — บันทึกอัตโนมัติแล้ว)
python backtest_portfolio.py <json_A> <json_B> [--equity 50000]

# ข้อมูลใหม่
data/funding_cache.json        # funding history 30 เหรียญ 3 ปี (ดึงรอบเดียว cache ถาวร)
data/cache.db                  # ตอนนี้มีทั้ง 4h และ 1h (แยก interval กัน)
```

**หมายเหตุ:** ไฟล์ backtest/research ยัง untracked — ถ้าอยาก commit เก็บบอกได้ครับ