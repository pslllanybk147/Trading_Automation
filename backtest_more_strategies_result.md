# 🔬 ผลทดสอบแนวทางเพิ่มเติม: FVG / Momentum Filter / Rotation

> วันที่: 2026-09-04 | เงินต้น 50,000 USDT | Binance Spot 4h | fee 0.1% + slippage 0.05%
> กฎ risk "รุก": 3%/เทรด, max 5 ตำแหน่ง, 3 ขาดทุน/วันหยุด, DD -20% หยุด 1 สัปดาห์
> คำถามต่อจาก SMC: ลองแนวทางอื่น (FVG, relative-strength, cross-sectional momentum rotation) ดีกว่า golden+regime+TP2.8 ไหม?

---

## 1. ตารางผลรวม (3 ปี, 30 symbols)

| กลยุทธ์ | ผลตอบแทน | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| **golden+regime+TP2.8** (benchmark ปัจจุบัน) | **+77.0%** | -17.7% | 50 | 64% | 2.00 |
| golden+regime+TP2.8 + mom-top10 | +36.3% | -14.4% | 24 | 63% | 2.04 |
| golden+regime+TP2.8 + mom-top15 | +40.7% | -17.2% | 29 | 62% | 1.94 |
| golden + mom-top10 (ไม่มี regime) | -39.4% | -53.8% | 109 | 37% | 0.76 |
| **FVG continuation + regime** | **-74.9%** | -79.0% | 251 | **16%** | 0.69 |
| FVG continuation (ไม่มี regime) | -86.1% | -90.3% | 485 | 16% | 0.74 |
| **Rotation top5 / 30 วัน** | **+7.1%** | -71.9% | — | — | — |
| Rotation top10 / 30 วัน | -7.4% | -77.6% | — | — | — |

---

## 2. สรุปแต่ละแนวทาง

### ① FVG continuation — แพ้ยับที่สุดในบรรดาที่เคยลอง (-75% ถึง -86%, win 16%)
- กติกา: หา bullish gap 3 แท่ง (low[i] > high[i-2]) แล้วเข้าตอนราคาย่อเข้าโซน gap
- ผล: win แค่ 16% → "ราคาย่อเข้า gap" ใน crypto 4h ไม่ได้แปลว่าจะเด้ง —
  ส่วนใหญ่เป็น **falling knife** (ทะลุโซนไหลต่อ) SL ใต้โซนโดนเก็บ
- สำคัญ: research ภายนอกบอกว่า FVG คือชิ้นส่วน SMC ที่ "ดีสุด" (64.8% ถูกกลับมาเติม)
  แต่ "ถูกเติม" ≠ "เด้งขึ้น" — ใน crypto มันถูกเติมแล้วไหลต่อ

### ② Relative-strength momentum filter (Top N ของ momentum 90 วัน)
- ติด golden+regime+TP2.8 → กำไรรวม**ลดลง** (+77% → +36-41%) เพราะกรองเทรดที่
  ชนะออกไปด้วย (50 → 24-29 เทรด) แม้ PF จะพอๆ กัน (2.04) และ MaxDD ดีขึ้นเล็กน้อย
- จุดสำคัญ: momentum 90 วันใน crypto **ไม่ช่วย**เหมือนในหุ้น — Top 90d ของ crypto
  มักเป็นเหรียญที่ขึ้นมามากแล้ว (mean-revert ในรอบถัดไป)
- ไม่มี regime filter = แพ้ (-39%) → **regime ยังเป็นตัวตัดสินหลัก ไม่ใช่ momentum**

### ③ Cross-sectional momentum rotation (ถือ Top N equal-weight รีบาลานซ์รายเดือน)
- วิธีการคนละแนวโดยสิ้นเชิง (periodic rebalance ไม่ใช่ event-driven)
- ผล: +7.1% / -7.4% แต่ **MaxDD -72% ถึง -78%** — ความเสี่ยงมหาศาล เทียบ BTC +215%
- บทเรียน: 2023-2026 กำไรกระจุกตัวใน BTC มากกว่า alt — ถือ alt แรงสุด 30d ไม่ได้ผล

---

## 3. บทสรุปตรงไปตรงมา

1. **golden+regime+TP2.8 (+77%, DD -17.7%) ยังเป็น config ที่ดีสุดที่เราหาเจอ** —
   3 แนวทางใหม่ (FVG / momentum filter / rotation) ไม่มีตัวไหนชนะ
2. **Regime filter คือหัวใจจริง ๆ** — ปรากฏซ้ำทุกการทดสอบ (ไม่มี regime = แพ้ทุกครั้ง)
3. FVG ที่ research ภายนอกชมว่า "ดีสุด" แพ้ยับใน crypto → ยิ่งตอกย้ำว่า SMC/แนวคิด
   ที่มองย้อนหลังสวย ๆ ไม่ได้แปลว่ามี edge หลังหัก fee
4. คนที่ "เทรด SMC กำไรสม่ำเสมอ" ที่เห็นตามโซเชียล = survivorship bias + discretion
   + filter ที่ encode ไม่ได้ — ไม่ใช่ตัว pattern เอง (ตรงกับบทเรียนข้อ 3)

## ไฟล์ที่ใช้
- `backtest_history.py` — เพิ่ม: `--fvg`, `--momentum-top N`, `--rotation --rot-top/--rot-hold/--rot-lookback`
- วิธีรันซ้ำ:
  - FVG: `python backtest_history.py --days 1095 --symbols 30 --fvg --regime-filter`
  - momentum: `python backtest_history.py --days 1095 --symbols 30 --golden-only --regime-filter --tp-golden 2.8 --momentum-top 10`
  - rotation: `python backtest_history.py --days 1095 --symbols 30 --rotation --rot-top 5 --rot-hold 30`