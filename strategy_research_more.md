# 🔬 วิจัยแนวทางเพิ่มเติม: Mean Reversion + HTF Bias + สกิลใหม่

> วันที่: 2026-09-04 | เงินต้น 50,000 USDT | Binance Spot 4h | fee 0.1% + slippage 0.05%
> ต่อจาก `backtest_more_strategies_result.md` — ยังไม่มีอะไรชนะ golden+regime+TP2.8 (+77%)

---

## 1. สกิลใหม่ที่ติดตั้ง (session นี้)

| สกิล | แหล่ง | ให้อะไร | ใช้กับโปรเจคเราไหม |
|---|---|---|---|
| `backtesting-frameworks` | wshobson/agents (14.7K) | มาตรฐาน backtest: กัน look-ahead/survivorship/overfit | ✅ ยืนยันวิธีที่เราทำอยู่ถูกต้อง (fee+walk-forward+OOS) |
| `trading-signal` | binance/binance-skills-hub (8.6K) | สัญญาณ smart-money on-chain (BSC/Solana เท่านั้น) | ⚠️ ไม่ตรงกับ Spot top-30 แต่เป็นไอเดียแหล่งข้อมูลใหม่ |
| `backtesting-trading-strategies` | jeremylongshore (4.3K) | 8 กลยุทธ์สำเร็จรูป (SMA/EMA/RSI/MACD/Bollinger/Breakout/MR/Momentum) | ⚠️ ใช้ yfinance = หุ้น ไม่ใช่ crypto — แต่รายการกลยุทธ์เป็นแนวทาง |
| (มีของเดิมอยู่แล้ว) | regime-detection, walk-forward-validation, vectorbt, crypto-scanner, coingecko-api, dexscreener-api, defillama-api, opentrade-cex, vizier | — | ✅ |

## 2. Mean Reversion (RSI oversold bounce) — วิธีคนละขั้วกับ trend-following

**กติกา:** RSI(14) < 30 = oversold → เข้าเมื่อ RSI เด้งกลับเหนือ 30 | SL -2 ATR | TP +2.8 ATR

| ชุด | 3 ปี | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| meanrev + regime (bull เท่านั้น) | +3.45% | **-3.11%** | 3 | 67% | 2.07 |
| meanrev (ไม่กรอง) | -46.8% | -68.7% | 151 | 41% | 0.78 |

**ผล:** ใน bull regime 4h แทบไม่เกิดจังหวะ RSI<30 (แค่ 3 ครั้ง/3 ปี!) เพราะ bull ไม่ค่อย oversold
ลึกขนาดนั้น — พอไม่กรองก็เจอแต่ falling knife (-47%)
**บทเรียน:** mean reversion ต้องใช้กับข้อมูลที่ความถี่สูงกว่า (1h/15m) หรือตลาด range —
บน 4h bull มันไม่มีงานให้ทำ

## 3. HTF (Daily) Bias Filter — แทน regime filter 4h

**กติกา:** golden cross + กรองด้วยเทรนด์รายวัน (1D close > MA20 daily) แทน MA20>MA50 4h

| ชุด | 3 ปี | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| golden + regime 4h (benchmark) | **+77.0%** | -17.7% | 50 | 64% | 2.00 |
| golden + HTF daily bias | +29.2% | -31.2% | 166 | 48% | 1.10 |

**บทเรียน:** daily MA20 bias หลวมเกินไป (เทรด 166 vs 50 ไม้, win 48% vs 64%)
— regime filter 4h (MA20>MA50 + slope) ที่เรามีอยู่นั้น **เข้มและเลือกจังหวะได้ดีกว่า**
HTF bias แบบง่าย — ตรงข้ามกับที่งานวิจัย SMC บอกว่า "HTF bias ช่วยได้" เพราะของเขา
คือ bias จากเทรนด์ใหญ่หลายชั้น ไม่ใช่แค่ MA20 วันเดียว

## 4. สรุป

**ยังไม่มีอะไรชนะ golden+regime+TP2.8 (+77%, DD -17.7%)**

| แนวทาง | ผล | สรุป |
|---|---|---|
| golden+regime+TP2.8 | +77% | 🏆 ยังแชมป์ |
| boost-only 2x (เพิ่มไซส์ตอน SMC ยืนยัน) | +81% | เทียบเท่า = leverage ไม่ใช่ edge |
| mean rev + regime | +3.5% | 4h bull ไม่มีจังหวะให้ทำ |
| HTF daily bias | +29% | กรองหลวมเกินไป ยังแพ้ regime 4h |

## 5. ไอเดียต่อ (ยังไม่ได้ทดสอบ)

1. **Mean reversion บน timeframe เล็ก (1h/15m)** — ต้องดึงข้อมูลเพิ่ม (ตอนนี้ cache แค่ 4h)
2. **Fundamental/on-chain data (funding rate, exchange flow)** — สกิล trading-signal
   ชี้ทาง แต่ต้องหาข้อมูล Spot+perp
3. **Multi-strategy portfolio** — รวม golden+regime (trend) + meanrev 1h (MR) แบบ
   แบ่ง capital กัน ไม่ใช่เลือกตัวเดียว — ลด DD โดยรวม
4. **Partial TP / trailing** — ยังไม่ได้ทดสอบจริง (ปิดเต็มที่ TP1 ตอนนี้)

## ไฟล์ที่ใช้
- `backtest_history.py` — เพิ่ม flags: `--meanrev`, `--htf-bias`
- ผล JSON: `backtest_result_1095d_meanrev*.json`, `backtest_result_1095d_golden_htf_g_tp2.8.json`