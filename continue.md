# 📌 Continue.md — Session: ทดสอบกลยุทธ์ MHM (วิดีโอ TradeX) + "ช่วง 0 + SMC" + Walk-forward

> อัปเดต 2026-09-06 · ต่อจาก `session_handoff.md` (สถานะ pipeline เดิมยังเหมือนเดิม
> — session นี้ไม่ได้แตะ pipeline/config หลัก แตะแค่ harness + ไฟล์ research)
> โปรเจค: `E:\Trading_Automation` | Windows, Python 3.13

## 1. Session นี้ทำอะไร

ผู้ใช้ให้ดูวิดีโอ YouTube `oADEAJ_nhj4` = "ผมก๊อปกลยุทธ์จากกองทุนหมื่นล้าน! | Quant
Trading Ep.1 | TradeX" แล้วถามว่าไอเดียในคอมเมนต์ ("ย่อเป็น H1 + จับช่วง 0 + SMC
แม่นมาก ใช้ได้จริงไหม") จะรอดไหม

**สิ่งที่ทำ:**
1. ดึง transcript ไทยด้วย yt-dlp (`th.json3`) → แกะกลยุทธ์ = **Multi-Horizon
   Momentum (AHL/Man Group)**: เทียบ close ปัจจุบันกับย้อนหลัง 4 จุด (1w/2w/1m/2m)
   แต่ละคู่ +1/−1 → score ∈ {−4..+4} (+4 ซื้อเต็ม / +2 ครึ่ง / 0 อยู่เฉย / ติดลบ =
   ฝั่ง sell), เช็คอาทิตย์ละครั้ง — คลิปนี้ยังไม่ให้ exit/sizing (อยู่ Ep.2)
2. เพิ่มโค้ด MHM + ตัวกรอง "score 0" ลงใน `backtest_history.py` (รายละเอียด §3)
3. รันชุดทดสอบ 3 ปี (30 เหรียญ 4h + BTC 1h) fee จริง → สรุปใน
   `mhm_quant_video_backtest_result.md`

## 2. ผลลัพธ์หลัก (30 เหรียญ · 4h · 3 ปี · fee 0.1%+slip 0.05% · เงินต้น 50k)

| ชุด | 3 ปี | MaxDD | เทรด | Win | PF |
|---|---|---|---|---|---|
| golden+regime+TP2.8 (benchmark) | +77.0% | −17.7% | 50 | 64% | 2.00 |
| **+ MHM gate ≥ 2** (weekly) | **+83.5%** | **−14.4%** | 41 | **68%** | **2.49** |
| + MHM gate ≥ 4 | +49.2% | −14.4% | 33 | 64% | 2.04 |
| MHM-only min2 / min4 (TP2.8) | −33.6% / +7.7% | −42.7% / −31.2% | 188 / 154 | 45% / 49% | 0.86 / 1.04 |
| SMC bos เดี่ยว (ไม่กรอง) | −22.5% | −50.1% | 180 | 44% | 0.90 |
| **SMC bos + เฉพาะช่วง score 0** | **+17.4%** | −16.7% | 58 | 50% | **1.19** |
| SMC bos + score0 + bull-regime | +0.9% | −10.7% | 13 | 46% | 1.05 |
| SMC bos + score0 + HTF bias | +8.1% | −20.3% | 49 | 49% | 1.11 |
| SMC reclaim เดี่ยว / +score0 | −59.8% / −55.3% | −71.6% / −60.9% | 304 / 135 | 21% / 17% | 0.78 / 0.56 |

**H1 (คำถามคอมเมนต์เป๊ะ):** BTC เดี่ยว 1h 3 ปี, SMC swing 96/bos 48, `--no-daily-gate`
- SMC bos baseline: −5.8% (15 ไม้, win 33%)
- SMC bos + score 0: **−8.9% (5 ไม้, win 0%)** → ไอเดียไม่รอดบน H1 สินทรัพย์เดียว

**ข้อสรุป:**
1. MHM score ≥ 2 เป็น "ตัวกรองชั้น 2" บน golden+regime **ดีกว่า benchmark จริง**
   (+83.5% / PF 2.49 / DD −14.4%) → ผู้สมัครเปิด A/B ใน paper
2. "จับช่วง 0 + SMC" มีเค้าบน 4h หลายเหรียญ (+17.4%) **แต่เปราะ**: เฉพาะ SMC bos,
   พอกรอง regime เพิ่มหาย, H1 ไม่รอด, แค่ 58 ไม้ → ยังไม่ควรเชื่อ ต้อง walk-forward
3. MHM ระบบเดี่ยว + TP คงที่ = แพ้ (โมเดลไม่ครบรูป — AHL ใช้ trailing/pyramid/std-dev
   sizing ตาม Ep.2 ที่คลิปยังไม่เฉลย)

## 3. โค้ดที่เพิ่มใน `backtest_history.py` (ยังไม่ได้ commit)

ฟังก์ชันใหม่: `compute_mhm_score()` (คะแนน multi-horizon) และ `compute_mhm_rows()`
(entry รายสัปดาห์ เฉพาะ daily bar) — ใช้ข้อมูลย้อนหลังเท่านั้น ไม่ lookahead
`compute_smc_rows()` parameterize `swing_n/bos_win` (เดิม hardcode 20/12)

Flag ใหม่:

| Flag | ความหมาย |
|---|---|
| `--mhm-only` | MHM เป็นสัญญาณหลัก (เช็ค `--mhm-cadence` วัน default 7) |
| `--mhm-min {2,4}` | ขั้นต่ำคะแนน (default 2) |
| `--mhm-horizons a,b,c,d` | horizons วัน (default 7,14,30,60) |
| `--tp-mhm X` | TP (default 2.8 ATR) |
| `--mhm-gate` | กรอง: สัญญาณต้องมี MHM score ≥ min ด้วย |
| `--smc-zero` | SMC เข้าเฉพาะแท่งที่ MHM score == 0 |
| `--smc-swing N / --smc-bos N` | window SMC เป็นแท่ง (1h ควร 96/48 ≈ 4 วัน/2 วัน) |

หมายเหตุ: ถ้าใช้ mhm/smc-zero harness ขยาย buffer ข้อมูลเป็น 70 วันก่อนเริ่ม (เผื่อ
horizon 60 วัน) อัตโนมัติ

**คำสั่งรันซ้ำ:**
```bash
python backtest_history.py --days 1095 --symbols 30 --golden-only --regime-filter --tp-golden 2.8 --mhm-gate --mhm-min 2
python backtest_history.py --days 1095 --symbols 30 --smc-only --smc-mode bos --smc-zero
python backtest_history.py --days 1095 --symbol-list BTCUSDT --interval 1h --smc-only --smc-mode bos --smc-swing 96 --smc-bos 48 --no-daily-gate --smc-zero
```

## 4. ไฟล์ใน session นี้

| ไฟล์ | คืออะไร |
|---|---|
| `backtest_history.py` | **แก้ไข** (เพิ่ม MHM + smc-zero/swing/bos; session 2: ปลด choices ของ --mhm-min) |
| `mhm_quant_video_backtest_result.md` | **ใหม่** — สรุปผลเต็มภาษาไทย |
| `backtest_walkforward_mhm.py` | **ใหม่ (session 2)** — walk-forward 4 folds ของ MHM gate |
| `walkforward_mhm_result.md` | **ใหม่ (session 2)** — สรุปผล walk-forward |
| `backtest_results/walkforward_mhm_result.json` | **ใหม่ (session 2)** — ผลดิบราย fold |
| `backtest_results/backtest_result_1095d_{golden_mhmg2,golden_mhmg4,mhm2,mhm4,smc_bos,smc_bos_mhm0,smc_reclaim_mhm0,smc_bos_mhm0_regime,smc_bos_mhm0_htf,...}.json` | **ใหม่** — ผล backtest |

git: ยังไม่ commit (มีแค่ `M backtest_history.py` + untracked ข้างบน) — ตรวจ
`git status` ก่อน commit

## 5. Walk-forward ของ MHM gate (session 2026-09-06 — ✅ ทำแล้ว)

สรุปเต็มใน `walkforward_mhm_result.md` · ผลดิบ `backtest_results/walkforward_mhm_result.json`
· สคริปต์ `backtest_walkforward_mhm.py` (ใหม่ — 4 folds, test 6 เดือน OOS, tune min บน train)

| test end | benchmark | gate min=2 | Δ |
|---|---|---|---|
| 2025-03-01 | +14.1% | +13.3% | −0.8% (DD ตื้นกว่า: −1.5% vs −3.2%) |
| 2025-09-01 | +16.8% | +13.9% | −2.9% |
| 2026-03-01 | 0.0% (0 ไม้) | 0.0% (0 ไม้) | — |
| 2026-09-01 | −4.7% | −1.2% | +3.5% (กรอบไม้แย่ปี 2026 ออก) |

**สรุป:** รวม 4 folds benchmark +13,112 vs gate +12,988 USDT = **return เท่ากัน≈
(แพ้ 124 USDT ≈1%) ไม่ใช่ +6.5% เหมือน in-sample** — จุดแข็งที่พิสูจน์ได้จริงคือ
**DD ตื้นกว่า 3/4 folds + กรอบไม้ขาดทุนปี 2026 ออก**; tune min บน train เลือก min ต่ำ
ทุก fold (= ค่า 2 ที่ประกาศ, คะแนน MHM เป็นเลขคู่เสมอทำให้ min 1≡2, 3≡4) — ไม่มี
selection bias เพิ่ม และ min=4 ไม่ได้ดีกว่า
→ **ข้อสรุป: +83.5% เป็นตัวเลข in-sample ที่ไม่ควรใช้อ้าง — ใน OOS gate = benchmark
เชิง return + ดีเชิง risk** ยัง A/B ใน paper ได้ (ต้นทุนคือเทรดน้อยลง ~30%)

อื่น ๆ ใน session นี้: `--mhm-min` ปลด choices [2,4] (รับทุกค่า เพื่อ sweep), 56 tests ผ่าน

## 6. ขั้นต่อไปที่ค้างไว้ (ถ้าจะต่อ)

1. ~~Walk-forward / OOS ของ MHM gate≥2~~ — ✅ ทำแล้ว (§5): return = benchmark,
   DD ดีกว่า → ถ้าจะใช้จริงให้เปิด A/B ใน paper แทนการเชื่อตัวเลข +83.5%
2. ทดสอบ `--smc-zero` แบบหลายชุด horizon/สินทรัพย์ (ETH/SOL/XAU) + ตรวจ robustness
   (จำนวนไม้ 58 น้อยไป) และทดสอบ SMC bos + score0 ที่ 1h/หลายเหรียญ
3. ถ้าจะทำ MHM เต็มรูปต้องเพิ่ม exit แบบ trailing + pyramid + ขนาดเงินตาม std-dev
   (เนื้อหา Ep.2) — ตอนนี้ประเมินได้แค่ "คะแนน + TP คงที่" ซึ่งไม่ยุติธรรมกับ AHL
4. ถ้าผู้ใช้สนใจของจริง: เปิด A/B "golden+regime vs golden+regime+mhm-gate2" ใน paper
   pipeline (config.json) แล้วเทียบหลัง 90 วัน — walk-forward แล้วว่า risk ดีขึ้นจริง (§5)

## 7. สถานะอื่น (ไม่เปลี่ยนจาก session_handoff.md)

- Pipeline รัน scheduled ตามเดิม (TradingCycle 01:00 / TradingCheck4h ทุก 4 ชม.)
- Paper journal เริ่ม 2026-09-04 เงินต้น 50k — 56 tests ผ่าน (session นี้รันซ้ำ ผ่าน)
- ข้อมูล 1h ของ BTC ถูก fetch เข้า cache.db แล้วระหว่างทดสอบ H1 (symbol อื่นยังไม่มี 1h)
