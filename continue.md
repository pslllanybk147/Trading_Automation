# 📌 Continue.md — Session: ทดสอบกลยุทธ์ MHM (วิดีโอ TradeX) + "ช่วง 0 + SMC" + Walk-forward

> อัปเดต 2026-09-06 · ต่อจาก `session_handoff.md` (สถานะ pipeline เดิมยังเหมือนเดิม
> — session นี้ไม่ได้แตะ pipeline/config หลัก แตะแค่ harness + ไฟล์ research)
> โปรเจค: `E:\Trading_Automation` | Windows, Python 3.13
>
> **ภาษา:** ผู้ใช้สื่อสารเป็นภาษาไทย (ขอให้คุยไทย) — เอกสาร/สรุป/commit message
> ใน repo นี้จึงเขียนเป็นภาษาไทยตลอด

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
| `pipeline/signal_engine.py` + `orchestrator.py` + `config.py` | **แก้ไข (session 2)** — MHM gate + `paper.journal_path` |
| `main.py` / `run_task.cmd` | **แก้ไข (session 2)** — `--config` arg สำหรับ arm B |
| `config_ab_mhm.example.json` + `tests/test_mhm_gate.py` | **ใหม่ (session 2)** — config A/B + 15 tests |
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

## 6.5 Trade chart แบบ TradingView (session 2026-09-06 — ✅ ทำแล้ว)

- `plot_trades.py` (ใหม่): สร้าง `trade_chart.html` — chart แท่งเทียน 4h จาก cache.db
  + จุดซื้อ (▲ น้ำเงิน, ขนาดไม้) / จุดขาย (▼, เขียว=กำไร แดง=ขาดทุน, ตัวเลข=PnL)
  + volume bars + tab ต่อ symbol + ตารางสรุป + **log รายวันว่าซื้อ/ขายอะไรวันไหน**
  ใช้ lightweight-charts v4 (TradingView open-source, โหลดจาก CDN ตอนเปิดไฟล์)
- แหล่งข้อมูล: paper journal (`--journal`) และ/หรือ backtest JSON (`--result`,
  `--all` = รวมทั้ง 2 arm + benchmark) — ตอนนี้ journal ยังว่าง (race เพิ่งเริ่ม)
  จึงดูจากผล backtest benchmark ก่อน (24 symbol-tabs, 50 เทรด)
- `backtest_history.py`: JSON ผลลัพธ์เก็บ entry/exit/exit_ts/size/sl/tp1 ครบแล้ว
  (เดิมเก็บแค่ pnl/exit_reason) — rerun benchmark แล้ว, ตัวเลขตรงเดิม (+38,513 / 50 เทรด)
- รัน: `python plot_trades.py --all` → เปิด `trade_chart.html` ในเบราว์เซอร์
  (trade_chart.html เป็น regenerate ได้ทุกเมื่อ — commit แค่สคริปต์)

## 6.6 Cache hygiene รายสัปดาห์ (session 2026-09-06 — ✅ ทำแล้ว)

- ที่มา: เหรียญ delist (DAI/XMR/RNDR/TON) นอนใน cache เงียบ ๆ เดือน — `is_stale()`
  กันตอน pipeline รัน แต่ไม่มีตัวสรุปให้ดู → สร้าง `cache_hygiene.py`
- จัดชั้นตามอายุแท่งสุดท้าย: OK <7d / AGING 7-180d / STALE 180-365d / ARCHIVE >365d
  (delist ใหม่โผล่ในรายงานตั้งแต่อายุ 1 สัปดาห์ — ไม่ต้องรอปี); `--prune` ลบเฉพาะ
  ARCHIVE + VACUUM, `--also-stale` ลบ STALE ด้วย, `--dry-run`, `--json`
- `main.py hygiene` (ผ่าน run_task.cmd → logs/scheduled.log, exit 1 = มีของเก่า)
- ลงทะเบียน `TradingCacheHygiene` — ทุกอาทิตย์อาทิตย์ 02:10 (เสาร์-อาทิตย์ไม่ชน
  cycle 01:00/01:30) — รอบแรก 2026-09-13
- ผลรอบแรก: 64 pairs, 63 OK, 1 STALE = XAUUSD (ข้อมูลทองจาก histdata จบ 2025-12-31
  — เจตนาไว้ ยังไม่ prune; ถ้าจะทดสอบทองต่อต้อง fetch ขยายช่วง)
- 80 tests ผ่าน (+8 ใหม่: test_cache_hygiene.py)

## 9. แผนระบบเทรดตัวใหม่ (Core-Satellite 3 Engines) — จากแชท aipass ที่ export

> ที่มา: `chat_export_20260906_1403.md` (แชท "ออกแบบกลยุทธ์เทรดคริปโตและทองคำ" บน
> ไทยเอไอพาส) — เป็น **โปรเจกต์แยกต่างหาก** จาก pipeline นี้ (pipeline = ระบบเดียว
> golden+regime; แผนนี้ = หลาย engine ที่ correlation ต่ำ + Risk Allocator รวม)

**สถาปัตยกรรม:** E1 Carry (40%) + E2 Trend (35%) + E3 Gold sweep (25%) → RA Allocator
(vol target 10%, kill switch) — ปรัชญา: "ไม่มีกลยุทธ์เดียวที่ดีที่สุด มีแต่สถาปัตยกรรม
ที่ดีที่สุด" + validation โหด (walk-forward, param ±20%, Monte Carlo, cost stress ×2,
regime slice, paper 60-90 วัน; red flags: Sharpe>3, win>70%, กำไรจาก <5 ไม้)

### E3 — XAUUSD Session Liquidity Sweep (spec + code ครบสุด)
- **ไอเดีย:** sweep ขอบ Asian range ช่วง London/NY open → reclaim → retest entry
  (state machine IDLE→ARMED→SWEPT→CONFIRMED→IN_POSITION)
- **ตัวกรอง:** ATR rank 0.35-0.95, range_ratio 0.25-1.20, news veto ±30min, spread
  ≤0.35×ATR_M15, max 2 ไม้/วัน, แพ้ 2 ติดหยุด
- **Exit:** TP1 1R ปิด 50%+BE, TP2 asian mid 30%, trail 2.5 ATR 20%, time-stop 8 bars,
  flat-by บังคับ; risk 0.5%/ไม้, ห้าม round up lot
- **สถานะ:** chat มี implementation kit ครบ (test-first: no-lookahead/DST/golden G1-G12
  + data loader CSV/Parquet + quality gate) — **ยังไม่ได้เอาลง repo**
- ⚠️ **เทียบกับงานวิจัยของเรา:** SMC sweep บนทอง 4h (session_handoff §4.13) ไม่มี edge
  (reclaim PF 0.50) — E3 ต่างกันตรงเป็น intraday M15 + session window + quality filter
  ที่ละเอียดกว่ามาก ถ้าจะทำต้องยึด falsifiable claim ของมัน: **OOS PF < 1.15 = ปิดโปรเจกต์**

### E1 — Crypto Funding Carry Delta-Neutral (spec ครบ, ยังไม่มีโค้ด)
- **ไอเดีย:** long spot + short perp เก็บ funding; edge อยู่ที่ cost control + exit
  discipline (งานวิจัย: forced exit 95% ของโอกาส, arbitrage ≥20bp มีแค่ 17% ของเวลา)
- **Entry 10 เงื่อนไข (E1-E10):** f_ma7d ≥ 9% ann. + stability ≥0.8 + f_pred > 0 +
  basis_z < 2.5 (ห้ามเข้าตอน basis สุดขั้ว) + expected hold ≥ 1.5×H_min
- **H_min = break-even holding** (taker 4 ขา ≈ 7.3 วัน ที่ f=0.01%/8h) — ถือสั้นกว่านี้ =
  ขาดทุนแน่ นี่คือเหตุผล retail ทำแล้วเจ๊งทั้งที่ funding บวก
- **Risk:** APY-on-capital เท่านั้น (ไม่ใช่ notional APY), lev ≤3× + margin ladder
  4 ชั้น (warn 2.2× → top-up 1.8× → deleverage 1.5× → close 1.3×), exchange cap 40%,
  cash buffer ≥25%, exits X1-X8 (funding decay/basis inversion/hard stop −1.5%)
- **เป้า (สมจริง):** net APY-on-capital 8-18%, Sharpe 1.8-3.0, MaxDD <4%, liquidation = 0

### E2 — Crypto Trend (ยังไม่ได้เขียน spec เต็ม — มีแค่โครงในแชทแรก)
Donchian(55) + EMA(20/100) slope, vol-target 12%/position, Chandelier 3×ATR,
time-stop 30 วัน; KPI: Sharpe 0.8-1.2, win 35-42%

### RA — Portfolio Risk Allocator (spec ครบ, ยังไม่มีโค้ด)
- **หน้าที่:** engine เสนอ (ส่งเป็น risk units) — allocator อนุมัติขนาดเท่านั้น;
  ข้อมูลไม่ครบ = ลด exposure ไม่เคยเพิ่ม; kill switch = one-way door
- **Sizing:** ERC + **tail multiplier** (E1=2.2× หางซ้ายหนา vol หลอกตา, E2=0.9×, E3=1.3×)
  + strategic bounds (E1 15-50%, E2 15-55%, E3 10-40%, cash ≥20%) + performance tilt
  cap ±30% + regime multiplier (ยืนยัน 2 วัน, ใช้ min ไม่ใช่คูณ)
- **Correlation:** ρ_used = max(short, long, **ρ_stress**=worst-decile days); cold start
  บังคับ ρ=0.5; ρ>0.75 = collapse mode ถือว่าเป็น engine เดียว
- **DD governor 4 ชั้น:** −4% ×0.7 → −8% ×0.4 → −12% flat + manual review; recovery
  ต้องช้ากว่าลด (asymmetric ladder); kill switch 5 ระดับ (engine/venue/portfolio/systemic/
  operational — L5 = feed เสียให้หยุดเปิดใหม่ ไม่ใช่ปิดตาบอด)
- **ประเด็นละเอียดที่คุ้ม:** Net Exposure Resolver (E1 short ทับ E2 long → net แต่ต้องมี
  shadow book แยก attribution), Segregated capital pools (w_feasible ≠ w_target,
  allocation_drag >15% = โครงสร้างทุนผิด), procyclical vol-targeting ใส่ rate limit ±25%

### ความคืบหน้า + ทางเลือกต่อไป (ถ้าจะทำต่อ)
- ✅ ในแชท: spec E3/E1/RA ครบ + E3 implementation kit (code blocks ในแชท — ยังไม่ลง repo)
- ⏳ ที่เสนอไว้แล้วท้ายแชท: walk-forward harness + report generator (PF/window, param
  robustness, Monte Carlo) หรือเริ่ม backtest engine + cost model ร่วมของทุก engine
- 💡 ถ้าจะดำเนินการจริง: E3 คือตัวที่ code พร้อมที่สุด (แต่ต้องยอมรับความเสี่ยงว่า
  รูปแบบคล้าย SMC ที่เราเคยทดสอบแล้วไม่มี edge ที่ 4h — ต้องพิสูจน์ที่ M15 intraday
  ด้วยข้อมูล spread จริง), E1 คือตัวที่ "structural" ที่สุดแต่ต้องมี infra perp/venue
  จริง, แผน Roadmap 8 phase อยู่แชทแรก (data → backtest → E3 → E1 → E2 → allocator →
  live micro 5-10% ของทุน)

## 6. A/B ใน paper pipeline (✅ implement + เปิดรันแล้ว 2026-09-06)

MHM gate ลง pipeline จริงแล้ว (config-driven, default ปิด — ไม่กระทบ arm เดิม):
- `pipeline/signal_engine.py`: `compute_mhm_score(candles)` — ตัวเดียวกับ harness
  (test equivalence ตรง ๆ กับ `backtest_history.compute_mhm_score`), ข้อมูลไม่พอ =
  None = บล็อก (fail-closed)
- `pipeline/orchestrator.py`: gate ใน signal stage (ก่อน validate/governor),
  summary มี `mhm_blocked` นับไม้ที่ถูกกรอง
- `pipeline/config.py`: `signal.mhm_gate` (default false) / `signal.mhm_min`
  (default 2) / `paper.journal_path` (default data/journal.db)
- `main.py`: รับ `--config <path>` | `run_task.cmd <cmd> [config]` → arm B log
  `logs/scheduled_ab.log`
- config ตัวอย่าง `config_ab_mhm.example.json` (mhm_gate=true + journal แยก
  `data/journal_ab_mhm.db`, gitignore แล้ว)
- 71 tests ผ่าน (56 เดิม + 15 ใหม่: `tests/test_mhm_gate.py`)

**วิธีเปิด A/B จริง (2 ขั้น) — ✅ ทำแล้ว 2026-09-06:**
- `config_ab_mhm.json` สร้างแล้ว, `TradingCycleAB` (daily 01:30) + `TradingCheck4hAB` (ทุก 4 ชม.)
  ลงทะเบียนแล้ว (schtasks, interactive-only เหมือน arm A) — cycle/check ทดสอบผ่าน wrapper แล้ว
  (log `logs/scheduled_ab.log`, MHM gate บล็อกจริง: DAIUSDT score=None → blocked)
- ⚠️ บทเรียน: `run_task.cmd` ต้องเป็น **ASCII + CRLF** เท่านั้น — เวอร์ชันเดิม LF+Thai text ทำ
  cmd.exe parse ผิด (รันชิ้นส่วน REM เป็นคำสั่ง) แก้แล้ว; ถ้าแก้ไฟล์นี้อีกต้องเช็ค CRLF ทุกครั้ง
```bash
cp config_ab_mhm.example.json config_ab_mhm.json
schtasks /Create /TN TradingCycleAB /sc DAILY /st 01:30 /tr "E:\Trading_Automation\run_task.cmd cycle config_ab_mhm.json"
# + check ทุก 4 ชม.: schtasks /Create /TN TradingCheck4hAB /sc HOURLY /mo 4 /tr "E:\Trading_Automation\run_task.cmd check config_ab_mhm.json"
```
เทียบผลหลัง 90 วันด้วย scorecard 2 อัน (`main.py status` vs `--config ... status`)
— เกณฑ์ตัดสินจาก walk-forward: arm B ควร DD ตื้นกว่า / return ไม่แพ้มาก

## 7. ขั้นต่อไปที่ค้างไว้ (ถ้าจะต่อ)

1. ~~Walk-forward / OOS ของ MHM gate≥2~~ — ✅ ทำแล้ว (§5): return = benchmark,
   DD ดีกว่า → เปิด A/B ใน paper ได้ (infra พร้อม §6 — ต้อง register schtasks)
2. ~~ทดสอบ `--smc-zero` แบบหลายชุด horizon/สินทรัพย์ (ETH/SOL/XAU) + ตรวจ robustness
   (จำนวนไม้ 58 น้อยไป) และทดสอบ SMC bos + score0 ที่ 1h/หลายเหรียญ~~ — ✅ ทำแล้ว
   (สรุปใน `smc_zero_robustness_result.md`): **ปิดโจทย์** — +17.4% เดิมมาจาก 4 เหรียญ
   (BCH/APT/NEAR/FIL = +20.8k); ชุด 9 เหรียญที่ไม่มี 4 เหรียญนั้น = −9.8k, ทอง = ลบ,
   ETH 1h บวกแต่ n=13 (noise) และ +score0 กินกำไร baseline หาย — PF แย่ลงทุกชุด
3. ถ้าจะทำ MHM เต็มรูปต้องเพิ่ม exit แบบ trailing + pyramid + ขนาดเงินตาม std-dev
   (เนื้อหา Ep.2) — ตอนนี้ประเมินได้แค่ "คะแนน + TP คงที่" ซึ่งไม่ยุติธรรมกับ AHL
4. ~~เปิด A/B "golden+regime vs golden+regime+mhm-gate2" ใน paper pipeline~~ —
   ✅ **เปิดแล้ว** (2026-09-06): schtasks ลงทะเบียนครบ, arm B รัน cycle/check ผ่านแล้ว —
   นาฬิกา 90 วันเริ่ม; ตัดสินผลด้วย scorecard 2 อันหลัง 90 วัน (เกณฑ์ §5: arm B ควร DD ตื้นกว่า /
   return ไม่แพ้มาก)

## 8. สถานะอื่น (ไม่เปลี่ยนจาก session_handoff.md)

- Pipeline รัน scheduled ตามเดิม (TradingCycle 01:00 / TradingCheck4h ทุก 4 ชม.)
- Paper journal เริ่ม 2026-09-04 เงินต้น 50k — 56 tests ผ่าน (session นี้รันซ้ำ ผ่าน)
- ข้อมูล 1h ของ BTC ถูก fetch เข้า cache.db แล้วระหว่างทดสอบ H1 (symbol อื่นยังไม่มี 1h)
