# Design Spec: AI Trading Pipeline (Swing Rule-Based + AI Governor)

> วันที่: 2026-09-04
> สถานะ: Draft — รอ review จากผู้ใช้
> โปรเจค: Trading_Automation
> สกิลที่ใช้: brainstorming (superpowers) — ผ่านการถาม-ตอบ + อนุมัติ design แล้ว

---

## 1. เป้าหมายและขอบเขต

สร้างระบบเทรดคริปโตอัตโนมัติเต็มรูปแบบ (full-auto) บน Binance Spot แบบ swing rule-based
โดย AI ทำหน้าที่เป็น "Governor" (ตัวกำกับ/กรอง) ไม่ใช่ผู้ตัดสินใจหลัก

**เป้าหมาย:**
- Pipeline แข็งแรง แม่นยำ จัดการความเสี่ยงได้ดีเยี่ยม
- ทำกำไรสม่ำเสมอ (expectancy > 0) โดยอิงจาก backtest ที่ไม่ overfit
- ดึงเทคนิค/สกิลต่าง ๆ มาใช้ให้ถูกกับสถานการณ์ (regime-aware)
- เทรดด้วย AI แบบอัตโนมัติเต็มรูปแบบ แต่มี circuit breaker + kill-switch

**ขอบเขตเวอร์ชันแรก (MVP):**
- ตลาด: Binance Spot (ไม่มี leverage)
- ขอบเขตสัญญาณ: Top 20-30 เหรียญตาม market cap, timeframe 4H/1D
- โหมด: paper-first บังคับ ≥ 90 วัน ก่อนเปิด live
- สไตล์: swing ถือ 1-7 วัน (เทรด ~6-10 ครั้ง/2 เดือน)

**นอกขอบเขต (ตัดทิ้ง YAGNI):**
- Futures/leverage (เพิ่มทีหลังเมื่อระบบพิสูจน์แล้ว)
- Real-time scalping / day trading
- On-chain whale tracking (เป็นตัวเลือกขยายทีหลัง — Design C)
- DEX/memecoin

---

## 2. ข้อตกลงที่ตกลงร่วมกัน (จากการ brainstorming)

| หัวข้อ | ข้อตกลง |
|---|---|
| บทบาท AI | อัตโนมัติเต็มรูปแบบ (AI ยิงออเดอร์ได้เอง) แต่มี circuit breaker + kill-switch |
| กลไก AI | กฎเป็นฐาน (rule-based signal engine) + AI Governor กำกับ/กรอง |
| ลำดับพิสูจน์ | Paper-first บังคับ ≥ 90 วัน + ผ่านเกณฑ์ 9 ข้อ ก่อน live |
| ตลาด | Binance Spot |
| ขอบเขต | Top 20-30, 4H/1D |
| Risk budget | รุก: เสี่ยง 3% ต่อเทรด, สูงสุด 5 ตำแหน่ง (เสี่ยงรวม ≤ 10%), ขาดทุนรวม 20% = หยุดทั้งระบบ 1 สัปดาห์ |
| เงินเริ่มต้น | 3,000 บาท (มองเป็นบัญชีเรียนรู้) — เป้าหมายระยะยาว 1,000,000 บาท (ทบต้น + เงินเติมรายเดือน) |

**หมายเหตุเรื่อง risk:** ช่วง paper-first จะพิสูจน์ว่าโหมด "รุก" อยู่รอดหรือไม่
ถ้าสถิติบอกว่าอัตราตายสูง AI Governor จะเสนอให้ลดระดับเอง (เช่น ลดเหลือ 2% หรือ 1%)

---

## 3. สถาปัตยกรรม

### 3.1 ภาพรวม

```
┌─────────────────────────────────────────────────────────────┐
│                     DAILY CYCLE (วันละ 1-2 รอบ)              │
└─────────────────────────────────────────────────────────────┘
  1. Data Layer      — ดึง OHLCV 4H/1D ของ Top 20-30 บน Binance
                       + market cap ranking (coingecko-api)
  2. Signal Engine   — กฎตายตัว (crypto-scanner):
                       Golden Cross MA7/25 + Wilder RSI + Volume Spike
                       + Turtle breakout (Donchian 20/55) เป็น setup สำรอง
                       → ออก entry / TP1 / TP2 / SL / R:R
  3. Validation      — vectorbt: backtest pattern ย้อนหลัง 2-3 ปี
                       walk-forward (CPCV): ผ่านเกณฑ์หรือไม่
                       → สัญญาณที่ "ผ่าน" เท่านั้นถึงจะไปต่อ
  4. AI Governor     — ตรวจ regime (regime-detection)
                       บล็อกเทรดช่วง scheduled events (FOMC/CPI — 50/50)
                       ตรวจว่ากฎยังใช้ได้ (signal degradation)
                       อนุมัติ/บล็อก พร้อมเหตุผล (log ทุกครั้ง)
  5. Risk Engine     — vizier: Kelly/fractional capped ที่ 3%/เทรด
                       ≤ 5 ตำแหน่ง, ≤ 10% เสี่ยงรวม, TP/SL/trailing
                       circuit breaker: -20% = หยุด 1 สัปดาห์
  6. Execution       — opentrade-cex: Binance Spot
                       โหมด paper ก่อน (จำลอง fee 0.1% + slippage)
                       แล้วค่อย live ด้วย API key
  7. Journal         — บันทึกทุกเทรด + scorecard เทียบ BTC รายเดือน
└─────────────────────────────────────────────────────────────┘
```

### 3.2 หลักการออกแบบ

1. **กฎเป็นฐาน (rule-based core)** — Signal Engine หาสัญญาณด้วยกฎตายตัวที่พิสูจน์ได้ด้วย backtest
2. **AI Governor เป็นชั้นกรอง** — ไม่ใช่ผู้ตัดสินใจหลัก ตรวจ regime/ข่าว/ความเสื่อมของกฎ แล้ว approve/block
3. **การ์ดทุกจุด (defense in depth)** — Validation ห้ามสัญญาณ overfit ผ่าน, Risk Engine ห้ามเทรดเกินงบ, AI ห้ามเทรดช่วงข่าวเสี่ยง
4. **fail-closed เสมอ** — ถ้าไม่แน่ใจ = ไม่เทรด (ไม่มีเทรด ดีกว่าเทรดผิด)
5. **ทุก stage มี log + journal** — พอมีปัญหาจะรู้ว่าจุดไหนพัง
6. **โมดูลแยก ทดสอบแยก** — แต่ละ stage สื่อสารผ่าน typed dataclass

---

## 4. องค์ประกอบ (Components)

### 4.1 Data Layer
- ดึง OHLCV ราย 4H/1D จาก Binance public API (ไม่ต้องใช้ key สำหรับข้อมูล)
- ดึง market cap ranking จาก CoinGecko API (coingecko-api skill)
- ตรวจความสมบูรณ์ของข้อมูล: ถ้า candle หาย > 5% → ข้าม symbol นั้น
- เก็บข้อมูลลง local cache (SQLite/CSV) เพื่อลดการเรียก API ซ้ำ

### 4.2 Signal Engine (กฎเป็นฐาน)
- **Setup หลัก:** Golden Cross MA7/MA25 + Wilder RSI (14) + Volume Spike ≥ 1.5x
- **Setup สำรอง:** Turtle breakout (Donchian 20/55) + ATR sizing
- เงื่อนไข regime (จาก regime-detection): เทรดเฉพาะช่วง trend ไม่เทรดช่วง sideways/range
- ผลลัพธ์: `Signal` — symbol, direction, entry, SL, TP1, TP2, R:R, เหตุผล, timeframe, timestamp

### 4.3 Validation
- vectorbt: backtest setup ย้อนหลัง 2-3 ปี
- walk-forward validation (CPCV — Combinatorial Purged Cross-Validation) บังคับ
- เกณฑ์ผ่าน: Sharpe > 0, profit factor ≥ 1.3, win rate 30-60% (ไม่สูงเกิน = ไม่ overfit), max DD ≤ 20%
- บันทึกผล before/after ทุกครั้งที่ปรับกฎ (version กำกับ)

### 4.4 AI Governor
- ตรวจ regime ปัจจุบัน (bull/bear/sideways) จาก regime-detection
- เช็คปฏิทินข่าว scheduled events (FOMC/CPI/NFP) — บล็อกการเปิด Long ใหม่ก่อน/หลังเหตุการณ์ ตามบทเรียน event study
- ตรวจ signal degradation: กฎที่เคยผ่าน validation แต่ผลล่าสุดเสื่อม → ลดน้ำหนัก/บล็อก
- อนุมัติ/บล็อกแต่ละสัญญาณ พร้อมเหตุผล (log ทุกครั้ง, กัน bias)
- **fail-closed:** ถ้า LLM เรียกไม่ได้ → บล็อกทุกสัญญาณรอบนั้น
- ตัวชี้วัด: บล็อก < 40% ของสัญญาณ (ถ้าบล็อกเยอะ = กฎกับ AI ขัดกัน ต้องแก้)

### 4.5 Risk Engine
- Position sizing: Kelly/fractional capped ที่ 3% ของพอร์ตต่อเทรด
- สูงสุด 5 ตำแหน่งพร้อมกัน, เสี่ยงรวม ≤ 10% ของพอร์ต
- TP/SL/trailing กำหนดก่อนเข้าทุกครั้ง (exit สำคัญกว่า entry — บทเรียน Edgewonk)
- Circuit breaker รายวัน: เสีย 3 เทรดติดกัน → หยุดวันนั้น
- Circuit breaker รวม: ขาดทุนรวม -20% → หยุดทั้งระบบ 1 สัปดาห์
- Kill-switch: ไฟล์ `STOP` ในโปรเจค → ปิด position ทั้งหมด + ไม่เปิดใหม่; คำสั่ง kill ผ่าน terminal

### 4.6 Execution
- opentrade-cex wrapper: Binance Spot
- โหมด paper: จำลอง fee 0.1% + slippage (ไม่ใช้เงินจริง)
- โหมด live: ใช้ API key จาก `.env` (ไม่ commit)
- เช็ค price deviation (ราคาเคลื่อนเกิน X% จาก entry = ไม่ยิง), rate-limit
- startup reconciliation: เทียบ journal vs สถานะจริงจาก exchange

### 4.7 Journal
- บันทึกทุกเทรด: สัญญาณ, เหตุผล AI, size, TP/SL, ผลลัพธ์, fee
- scorecard รายเดือน: return, win rate, profit factor, max DD, เทียบ BTC
- ใช้เป็นข้อมูลป้อนกลับให้ AI Governor ตรวจ signal degradation

---

## 5. Data Flow และโครงสร้างข้อมูล

### 5.1 โครงสร้างข้อมูล (typed dataclass)

| ชื่อ | ฟิลด์หลัก |
|---|---|
| `CandleData` | symbol, timeframe, OHLCV, volume, timestamp |
| `Signal` | symbol, direction, entry, SL, TP1, TP2, R:R, reason, timeframe, timestamp |
| `ValidationResult` | passed, Sharpe, win_rate, profit_factor, max_dd, walk_forward_scores |
| `GovernorDecision` | approve/block, reason, regime, events_checked |
| `RiskPlan` | size_usdt, sl, tp1, tp2, risk_used, checks_passed |
| `OrderResult` / `TradeRecord` | สถานะ, fee, slippage, pnl |

### 5.2 วงรอบการทำงาน (Daily Cycle)

| เวลา (UTC) | งาน |
|---|---|
| 01:00 (หลังปิด 1D) | รอบหลัก: data → signal → validation → AI → risk → execute |
| 05:00, 09:00, 13:00... | รอบเช็ค 4H: อัปเดต TP/SL ของ position ที่เปิดอยู่, เช็ค circuit breaker |
| ทุก 4H | เช็คสถานะพอร์ต + บันทึก journal (แม้ไม่มีเทรด) |

---

## 6. Error Handling

| สถานการณ์ | การจัดการ | ผล |
|---|---|---|
| Binance API ล่ม/timeout | retry 3 ครั้ง (backoff 5s/15s/30s) | ข้ามรอบ ไม่เปิดเทรดใหม่ |
| rate-limit โดน | รอ + ลดความถี่รอบถัดไป | ไม่โดนแบน IP |
| ข้อมูลไม่ครบ | ตรวจ completeness < 95% → ข้าม symbol | ไม่คำนวณสัญญาณจากข้อมูลพร่อง |
| AI Governor ล่ม (LLM) | **fail-closed**: บล็อกทุกสัญญาณ | ปลอดภัยไว้ก่อน |
| ยิงออเดอร์ค้าง (partial fill) | เช็คสถานะจริง + retry/cancel | ไม่มี position ลอยค้าง |
| system crash ตำแหน่งค้าง | startup reconciliation | คืนสภาพพอร์ตให้ตรง |
| ราคาวิ่งเกิน SL (gap) | market order ทันที | ตัดขาดทุนแม้ราคากระโดด |

**Kill-switch ระดับบนสุด:**
1. อัตโนมัติ: ขาดทุนรวม -20% → หยุด 1 สัปดาห์
2. อัตโนมัติ: เสีย 3 เทรดติด → หยุดวันนั้น
3. Manual: ไฟล์ `STOP` → ปิดทั้งหมด + ไม่เปิดใหม่
4. Manual ฉุกเฉิน: คำสั่ง kill ผ่าน terminal

---

## 7. เกณฑ์การเลื่อน Paper → Live (ต้องผ่านครบ 9 ข้อ)

| # | เกณฑ์ (paper เงินจำลองเริ่ม 50,000 บาท) | ค่าที่ต้องผ่าน |
|---|---|---|
| 1 | ระยะเวลาทดสอบ | ≥ 90 วัน |
| 2 | จำนวนเทรดขั้นต่ำ | ≥ 20 เทรด |
| 3 | Expectancy | > 0 หลังหัก fee 0.1% + slippage |
| 4 | Profit factor | ≥ 1.3 |
| 5 | Win rate | 30-60% |
| 6 | Max drawdown | ≤ 20% |
| 7 | Walk-forward สอดคล้อง | ผล out-of-sample ยังบวก |
| 8 | AI Governor ไม่บล็อกเกินควร | บล็อก < 40% ของสัญญาณ |
| 9 | ไม่มี technical failure | ไม่มี position ค้าง/API error ที่ยังไม่แก้ |

**Live แบบค่อยเป็นค่อยไป:** เริ่ม 3,000-5,000 บาทจริง → ผ่าน 30 วัน (expectancy > 0, DD ≤ 10%) → เพิ่มเป็น 50,000 → ถ้าผิดพลาด กลับ paper ทันที

---

## 8. แผนการทดสอบ (5 ชั้น)

1. **Unit tests** — แต่ละโมดูล (signal rules เทียบเคสที่รู้คำตอบ, sizing ถูกสูตร, circuit breaker ทำงาน)
2. **Integration tests** — 1 รอบ daily cycle เต็มกับ mock exchange + error path ทุกแบบ
3. **Backtest validation** — vectorbt 2-3 ปี + walk-forward CPCV ทุกครั้งที่เปลี่ยนกฎ (บันทึก before/after)
4. **Paper trading** — รันจริงบนโหมด paper 90 วัน ผ่านเกณฑ์ข้อ 7
5. **Live ค่อย ๆ เพิ่ม** — เริ่มเล็ก → ผ่าน → เพิ่มขนาด → ผิดพลาดกลับ paper

---

## 9. โครงสร้างไฟล์

```
Trading_Automation/
  pipeline/
    __init__.py
    models.py            # dataclasses: CandleData, Signal, ValidationResult...
    data_layer.py        # ดึง OHLCV Binance + coingecko ranking
    signal_engine.py     # กฎ golden cross/RSI/volume + Turtle
    validation.py        # vectorbt + walk-forward wrapper
    ai_governor.py       # regime + event check + approve/block (LLM)
    risk_engine.py       # vizier sizing + circuit breaker + kill-switch
    execution.py         # opentrade-cex wrapper (paper/live)
    journal.py           # บันทึกเทรด + scorecard
    orchestrator.py      # daily cycle + startup reconciliation
    config.py            # พารามิเตอร์ทั้งหมด (risk budget, symbols, ...)
  tests/
    test_signal_engine.py
    test_risk_engine.py
    test_data_layer.py
    test_orchestrator.py
  .env                   # API keys (Binance, LLM) — ไม่ commit
  requirements.txt
```

**ลำดับการสร้าง:** models → data_layer → signal_engine → validation → risk_engine → journal → orchestrator → ai_governor → execution → tests

---

## 10. สกิลที่เกี่ยวข้อง (ติดตั้งแล้วทั้งหมด)

| Stage | สกิล |
|---|---|
| Data | `coingecko-api`, `dexscreener-api` (สำรอง), `defillama-api` (กรอง fundamentals) |
| Signal | `crypto-scanner`, `regime-detection` |
| Validation | `vectorbt`, `walk-forward-validation` |
| AI Governor | `regime-detection`, (ขยาย: `sentiment-analysis` ทีหลัง) |
| Risk | `vizier` |
| Execution | `opentrade-cex` |

**สกิลที่อาจติดตั้งเพิ่มในอนาคต:** `sentiment-analysis`, `whale-tracking`, `token-holder-analysis`, `trade-journal` (Design C)

---

## 11. ความเสี่ยงและข้อจำกัด

- สถิติ: คนส่วนใหญ่ขาดทุน — ระบบนี้ลดความเสี่ยงด้วย process ไม่ใช่การันตีกำไร
- เงิน 3,000 บาท: ค่า fee/slippage คิดเป็นสัดส่วนสูง — มองเป็นบัญชีเรียนรู้
- "รุก" (3%/เทรด) มีอัตราตายสูงกว่าอนุรักษ์นิยม — paper จะพิสูจน์ ถ้าไม่รอด AI Governor จะเสนอให้ลด
- LLM bias/ความไม่แน่นอนของ AI — AI เป็น Governor (กรอง) ไม่ใช่ผู้ตัดสินใจหลัก จึงจำกัดความเสียหาย
- Overfitting เป็นศัตรูอันดับ 1 — walk-forward CPCV บังคับทุกการปรับกฎ