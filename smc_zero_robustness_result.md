# SMC + "ช่วง 0" (smc-zero) — ทดสอบ robustness ข้ามสินทรัพย์/พารามิเตอร์ (2026-09-06)

> ปิดโจทย์ข้อ 2 จาก `continue.md` §7 — ไอเดียคอมเมนต์คลิป TradeX "ย่อเป็น H1 +
> จับช่วง 0 + SMC แม่นมาก" ผลเดิมบน 30 เหรียญ 4h (+17.4%, 58 ไม้) **ไม่ผ่านการทดสอบ
> robustness** — เป็นผลจาก 4 เหรียญโชคดี ไม่ใช่ edge ของโซน score 0

## 1. สิ่งที่ทดสอบ

`--smc-zero` = SMC sweep+BOS เข้าเฉพาะแท่งที่คะแนน MHM (เทียบ close กับ 4 horizons
1w/2w/1m/2m) **== 0** (โซนไร้เทรนด์/ไซด์เวย์) — เทียบกับ baseline SMC bos ไม่กรอง
ด้วย risk model เดียวกันทั้งหมด (3%/ไม้, SL −2 ATR, TP +2.8 ATR, fee จริง)

| เฟส | สินทรัพย์ | ช่วง | หมายเหตุ |
|---|---|---|---|
| 1 | 9 alt 4h (ETH,SOL,BNB,XRP,DOGE,ADA,AVAX,LINK,LTC) | 3 ปี | เลือกชุดที่ **ไม่มี** 4 เหรียญที่ทำเงินให้ผลเดิม |
| 2 | XAUUSD 4h | 5 ปี (2021-2025) | fee CFD จริง 0.005% + slip 0.002%, --no-volume |
| 3 | ETH 1h | 2 ปี (จำกัดด้วย cache 1h) | swing 96 / bos 48, --no-daily-gate — datapoint ที่ 2 ของ H1 |
| 4 | parameter sweep บนชุด 9 เหรียญ | 3 ปี | horizons ครึ่งหนึ่ง + swing/bos เร็วลง |

## 2. ผลรวม

| ชุด | ผลตอบแทน | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| **เฟส 1: 9 alt 4h** baseline smc bos | −10.0% | −29.3% | 91 | 44% | 0.93 |
| + smc-zero | −7.9% | −18.2% | 22 | 36% | **0.80** |
| + smc-zero, horizons 3,7,21,42 | −19.5% | −22.9% | 26 | 35% | **0.57** |
| + smc-zero, swing12/bos12 | −18.6% | −22.6% | 54 | 41% | **0.77** |
| baseline, swing12/bos12 | −22.3% | −36.1% | 178 | 44% | 0.91 |
| **เฟส 2: XAUUSD 4h** baseline smc bos | −0.8% | −3.6% | 8 | 38% | 0.83 |
| + smc-zero | −0.5% | −1.9% | 3 | 33% | **0.76** |
| **เฟส 3: ETH 1h 2y** baseline smc bos (sw96/bos48) | **+17.4%** | — | 13 | 69% | 2.41 |
| + smc-zero | +4.8% | — | 7 | 57% | 1.54 |

อ้างอิงเดิม (continue.md §2): 30 เหรียญ 4h baseline −22.5% → +score0 **+17.4%** (58 ไม้)
· BTC 1h baseline −5.8% → +score0 −8.9% (5 ไม้)

## 3. หลักฐานชี้ขาด: ผล +17.4% มาจาก 4 เหรียญ

แยก per-symbol จากไฟล์ผลเดิม `backtest_result_1095d_smc_bos_mhm0.json` (58 ไม้, PnL +8,699):

| เหรียญ | เทรด | PnL |
|---|---|---|
| BCHUSDT | 3 | **+5,941** |
| APTUSDT | 3 | **+5,483** |
| NEARUSDT | 2 | **+4,713** |
| FILUSDT | 4 | **+4,657** |
| ETHUSDT | 5 | −5,015 |
| XRPUSDT | 4 | −4,215 |
| (อีก 16 เหรียญ) | 36 | −3,875 |

- 4 เหรียญนี้ (12 ไม้) รวม **+20,794 USDT**; ตัดออกแล้วเหลือ −12,095 USDT
- ระบบเสริม: เฟส 1 ใช้ชุด 9 เหรียญที่ **ไม่มีทั้ง 4** → ได้ **−9,751 USDT / 26 ไม้ / win 36%**
  ตรงกับที่คำนวณ — พิสูจน์ว่า "โซน 0" ไม่ได้เลือกไม้เก่งอะไรเลย เจอเหรียญที่โชคดีแล้วจึงบวก
- กระจายเวลาไม่ช่วย: 4 ไม้ใหญ่ไม่ได้อยู่ปีเดียว แต่มัวร์อยู่เหรียญเดิม (BCH/APT/NEAR/FIL)

## 4. ข้อสรุป — ปิดโจทย์ smc-zero

1. **smc-zero ไม่มี edge ในทุกมิติที่ทดสอบ** — 8 จาก 9 ชุดทดสอบเป็นลบ, PF 0.57-0.93
   ยกเว้น ETH 1h ที่บวกทั้ง baseline และ +score0 แต่ n=13/7 เท่านั้น (noise) และ
   +score0 กินกำไร baseline หายเกือบหมด (+17.4% → +4.8%) — ตรงข้ามกับ BTC 1h ที่ลบทั้งคู่
2. **กลไกเดิมยืนยันซ้ำ**: "ฟังดูดี" ของ smc-zero = เทรดน้อยลง ~4 เท่าจาก strategy ที่
   expected value ติดลบ → ขาดทุนน้อยลง ไม่ใช่กำไรเพิ่ม (PF แย่ลงทุกชุด: 0.93→0.80,
   2.41→1.54 เมื่อเทียบในสินทรัพย์เดียวกัน)
3. **SMC bos เดี่ยว ๆ ก็ยังไม่มี edge** — บวกจริงแค่ ETH 1h (n=13) ซึ่ง BTC 1h ตรงข้าม
   (−5.8%) และ alt 4h/Gold เป็นลบหมด → ยังเป็นตามบทเรียนเดิม (session_handoff §5.4)
4. → **decision: ปิดโจทย์ "จับช่วง 0 + SMC" ทั้ง 4h/1h/crypto/ทอง** — ไอเดียจากคอมเมนต์
   ไม่รอดการทดสอบ robustness โดยไม่ต้องรอ walk-forward เพราะไม่มี in-sample edge ที่
   ยืนหยุดข้ามสินทรัพย์ให้ validate ต่อ

## 5. คำสั่งรันซ้ำ

```bash
# เฟส 1 (9 alt 4h, 3 ปี)
python backtest_history.py --days 1095 --symbol-list ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,LINKUSDT,LTCUSDT --smc-only --smc-mode bos --no-fetch --no-volume
python backtest_history.py --days 1095 --symbol-list ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,LINKUSDT,LTCUSDT --smc-only --smc-mode bos --smc-zero --no-fetch --no-volume
# เฟส 2 (ทอง 5 ปี, fee CFD)
python backtest_history.py --days 1825 --symbol-list XAUUSD --smc-only --smc-mode bos --no-fetch --no-volume --fee-rate 0.00005 --slippage 0.00002
# เฟส 3 (ETH 1h 2 ปี)
python backtest_history.py --days 730 --symbol-list ETHUSDT --interval 1h --smc-only --smc-mode bos --smc-swing 96 --smc-bos 48 --no-daily-gate --no-fetch --no-volume
# เฟส 4 (sweep): เพิ่ม --mhm-horizons 3,7,21,42 หรือ --smc-swing 12 --smc-bos 12
```

ไฟล์ผลดิบ: `backtest_results/backtest_result_1095d_{ethusdt_..._,}smc_bos{,_mhm0}.json`,
`backtest_result_1825d_xauusd_fee..._smc_bos{,_mhm0}.json`,
`backtest_result_730d_ethusdt_smc_bos{,_mhm0}_sw96_bos48.json`
