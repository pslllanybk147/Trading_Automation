# Community Strategy Research — Reddit/YouTube Findings

> สรุปจากการค้นข้อมูลกระทู้ Reddit + YouTube + แหล่งอ้างอิง วันที่ 2026-09-05
> วัตถุประสงค์: คนที่เทรดสำเร็จจริงใช้เทคนิคอะไร และคนที่ใช้ AI เทรดใช้แบบไหน
> หมายเหตุ: Reddit บล็อกการอ่านเต็มกระทู้ (ต้อง login) — ข้อมูลจาก search snippet + แหล่งที่อ้างอิง/เผยแพร่ผลงานซ้ำ (GitHub, blog)

---

## 1. งานศึกษาใหญ่สุด: "42 public Freqtrade strategies, 8 ปี BTC — 33 ตัวขาดทุน"

**แหล่ง:** r/algotradingcrypto + GitHub `wiktorj137/btc-strategy-lab` (ผู้เขียนเปิดเผยผลงานเต็ม พร้อม harness ตรวจสอบ)

**ตัวเลขหลัก (BTC/USDT spot, 1h, fee 0.1%/side, ไม่มี leverage):**
| ตัวชี้วัด | ผล |
|---|---|
| กลยุทธ์สาธารณะ 42 ตัว ที่ทดสอบ | **33 ตัวขาดทุน** (79%) |
| Median return | **−81%** |
| ชนะ BTC buy & hold | แค่ 3 ตัว |
| Day trading 22 ตัว (5m candles) | **21 ตัวขาดทุน**, median **−95.6%** |

**บทเรียนที่ตรงกับงานเรา:**
1. **Day trading ตายเพราะ fee** — bot ทำ 6,000 รอบ เท่ากับจ่าย fee 12 เท่าของเงินต้น ตัว `EMASkipPump` ทำ 5,953 เทรด จ่าย fee 1,191% ของเงินต้น → ไม่มี indicator edge ไหนชนะค่า fee ได้ (ตรงกับบทเรียน v1 ของเรา: fee กิน 23–36%)
2. **Win-rate trap:** `Strategy001` ชนะ 88.6% ของเทรด แต่จบที่ **−98.6%** — ชนะเล็ก ๆ ถี่ ๆ ครั้งเดียวเจ๊งใหญ่ล้างทั้งหมด (ตรงกับ SMC reclaim ของเราที่ win 20% + SL แคบโดนเก็บ)
3. **กลยุทธ์ที่ชนะ = แค่ 4 กฎ:**
   - EMA 600h (~25 วัน) ราคาตัดขึ้น → ซื้อ
   - ราคาปิดต่ำกว่า EMA 2% → ขาย
   - **ข้าม entry เมื่อ funding rate อยู่ใน top 45% ของช่วง 180 วัน** ← ตัวกรองเดียวที่ผู้เขียนเพิ่มเอง
   - ผล: **+1,604% / MaxDD −33.8%** vs BTC B&H +781% / −76.6% — ตัวกรอง funding **ซื้อ drawdown ไม่ใช่ return** (1,353% → 1,604% แต่ DD −49.4% → −33.8%)
4. **ผ่าน validation gates:** walk-forward 8/13 windows กำไร (+1,125% compound OOS), PBO 0.21, ตรวจ look-ahead bias สะอาด
5. **ข้อจำกัดใหญ่: ไม่ generalize ไป altcoin** — กฎเดียวกันบน ETH/SOL/DOGE/XRP/BNB/AVAX/LINK: 3 ตัวขาดทุน, 4 ตัวแพ้การถือเฉย ๆ → "BTC เทรนด์คนละแบบกับ alt หรือผลลัพธ์คือการฟิตใส่ข้อมูลชุดเดียว ตอบไม่ได้ เลยถือว่า live ต้องดูใหม่"
6. **Funding ไม่ทำงาน intraday** — effect ต้องใช้เวลา 24–72 ชม. ถึงจะออก (+27 bps @24h, +69 bps @72h) และ **สัญญาณกลับข้างในปี 2023** (ก่อนหน้า low funding นำ rally; หลังกลับกัน) → ใช้เป็น "อย่าซื้อตอนฟอง" ฝั่งเดียวเท่านั้น
7. **Order flow ไม่มี edge intraday** — ทดสอบ open interest/taker/positioning 5m ตั้งแต่ 2021 (592k rows): ทุก horizon ชนะ cost floor ไม่ได้ (15m: 0.7bps vs cost 4bps) → "ปิดคำถามสำหรับ retail fee tier แล้ว"

---

## 2. กระทู้ "Backtested 16,000 retail trading strategies"

**แหล่ง:** r/algotrading (Jan 2026) — 50 stocks × 80 strategies × 4 timeframes = ~16,000 backtests

- ผู้เขียนให้คะแนนทุก backtest ด้วย composite: **Sharpe + alpha vs buy&hold + win rate + ลงโทษ turnover สูง**
- ประเด็นของกระทู้ = "จะไม่หลอกตัวเองยังไง" — สาระคือคนส่วนใหญ่เจอ "strategy กำไร 80%" แต่ส่วนใหญ่ไม่รอด validation
- **ไม่มีการเปิดเผยว่า strategy ไหนชนะสุด** — ตัวกระทู้เองคือตัวอย่างว่า "ตัวเลขสวย = จุดเริ่มต้นของปัญหา ไม่ใช่คำตอบ"

---

## 3. "I backtested a 400K views YouTube trading strategy"

**แหล่ง:** r/algotrading (Feb 2026)

| | ที่ YouTuber อ้าง | ผล backtest จริง |
|---|---|---|
| 100 เทรด, win rate | 56% | **39%** |
| R:R | 1.5 | 1.5 |
| ผลรวม | +40% | **−23%** |
| MaxDD | — | **−36%** |
| Expectancy | บวก | **ลบ** |

- วิดีโอ 400K views ที่ "ดูดีมากบนกระดาษ" พอเอามา backtest จริงแบบซื่อสัตย์ = **ขาดทุน**
- ตรงกับงานวิจัย SMC ของเราเป๊ะ: สิ่งที่ influencer โชว์ (win rate 70–80%) พอ encode เป็นกฎ + fee จริง = 38–48%

---

## 4. AI trading — ชุมชนพูดว่าอะไร "ได้ผลจริง"

### 4.1 r/ai_trading — "What's actually working in AI trading right now and what's just hype?" (Mar 2026)
- **ความเห็นหลัก: "LLMs สำหรับสร้างระบบ ไม่ใช่สำหรับตัดสินใจเทรด"**
- "AI มีประโยชน์กับ sentiment scraping หรือ data cleanup มากกว่าการทำนายราคา"
- กระทู้คู่ "I asked this sub how good AI trading actually is" (Aug 2026) — สองสัปดาห์ของคำตอบ ส่วนใหญ่เป็นเสียงกังขา

### 4.2 r/algotrading — เรื่อง LLM เขียน backtest
- **"LLM เขียน backtest — ระวัง look-ahead bias หนึ่งบรรทัด"** (May 2026): LLM ดีกับ boilerplate/plotting/refactor แต่โค้ด backtest ที่ generate ต้องอ่านทีละบรรทัดเรื่อง timing/fill logic
- **"LLM supported backtesting"** (Jul 2026): "LLM ช่วยอธิบาย/จัดระเบียบ research loop ได้ แต่**อย่าให้ LLM เป็นผู้ตัดสินผล backtest** — execution assumptions, fees, timing ต้องตรวจเอง"
- **"LLMs for trading"** (Apr 2025): เสียงส่วนใหญ่ — LLM เป็น associative model ทำนายราคาไม่ได้ ใช้เป็นเครื่องมือได้

### 4.3 r/Daytrading — "Can AI Trading Make You Profitable?" (Jul 2026)
> "Short answer: **No, not by itself. AI doesn't create an edge; it only executes what you give it.** A weak strategy just means losses happen faster."

### 4.4 บทความ "I tested 23 AI bots and lost $14,000" (Medium, May 2026 — ระวัง: เนื้อหาโปรโมต LLM agent โฆษณา แต่มุมบางส่วนตรงกับงานวิจัย)
- Grid bots: "กำไร $10 จาก grid แต่ขาดทุน unrealized 10 เท่า ตอน Solana ร่วง 25%" — **grid bot แพ้ในตลาด trending** (ตรงกับบทเรียน "range assumption")
- Cryptohopper/3Commas = **rule-based engine ไม่ใช่ AI** — 114 เทรด win rate 34% เพราะใช้ lagging indicator (MACD/Bollinger) ยืนยันตอน trend จบแล้ว
- 3Commas DCA: "ซื้อเพิ่มเรื่อย ๆ ตอนเหรียญกำลังจะไปศูนย์ — 7 safety trades บนเหรียญที่ตายแล้ว" = **ไม่มีตัวกรอง context**
- "Rules-based bots follow orders. AI agents follow objectives" — ตัว "fix" ที่เขาใช้อ้าง = LLM agent + sentiment filter + risk params

### 4.5 บทวิเคราะห์ที่เป็นกลาง: fortraders.com "AI Trading: What Genuinely Works in 2026" (Aug 2026)
แบ่ง "AI trading" เป็น 4 ประเภท — มีแค่ 2 ที่รอดกฎ drawdown ของบัญชีจริง:

| ประเภท | Edge จริง 2026 | รอดบัญชีจริง? |
|---|---|---|
| **Signal-generation bots** | ต่ำ — ส่วนใหญ่คือ indicator เดิมห่อ UI chatbot | มัก fail (curve-fit ตายที่ spread/slippage) |
| **LLM research assistant** | **สูง** — สรุปข่าว, draft code, stress-test thesis | ✅ (ใช้ถูกวิธี) |
| **Execution & risk automation** | **สูงสุด/เสี่ยงต่ำสุด** — บังคับ SL, sizing, daily loss limit | ✅ |
| **ML-driven strategy dev** | จริงแต่ต้องมีวินัย (walk-forward, OOS, ไม่ leak ข้อมูล) | ขึ้นกับ process |

> "AI earns its place as a **filter and guardrail**, not as a decision-maker — payoff ยิ่งใหญ่ตอน 'ให้ AI บังคับกฎที่เราเขียนไว้' ยิ่งกว่า 'ให้ AI เลือกเทรด'"

### 4.6 Survey เชิงวิชาการ: "Agentic Trading: When LLM Agents Meet Financial Markets" (Expert Systems with Applications, 2026)
- รวบรวม 77 งานวิจัย LLM trading agent — **protocol incomparability รุนแรง:**
  - แค่ **2/19** งานรายงาน time-consistent data split
  - แค่ **1/19** มี transaction-cost model
  - แค่ **1/19** จัดการ survivorship/universe bias
  - **0/19** ถึงระดับ reproducibility R3
- แปลว่า: งานวิจัย AI trading ที่ตีพิมพ์ ส่วนใหญ่**เทียบกันไม่ได้และพิสูจน์ซ้ำไม่ได้** — ตัวเลข "กำไร" จาก paper ไม่ควรเชื่อโดยไม่เห็น protocol

---

## 5. เครื่องมือ/เฟรมเวิร์กที่คนใช้จริง (จากกระทู้)

| เครื่องมือ | ใครใช้ยังไง |
|---|---|
| **Freqtrade** (Python, open-source) | เฟรมเวิร์ก backtest/live ยอดนิยมสุดของสาย crypto algo — Telegram integration, strategy testing |
| **TradingView Pine Script + webhook** | เขียน strategy บน TradingView → alert ส่ง webhook → bot (freqtrade/Octobot/Gunbot/Tickerly/3Commas) รับแล้ว execute |
| **Hummingbot / Jesse / Octobot** | ทางเลือก open-source อื่น ๆ |
| **Binance API ตรง** | คนเขียนเองแบบเรา (main.py → execution → journal) |

---

## 6. สรุป — ใช้กับโปรเจคเราได้อะไร

**A. เทคนิคที่ "คนทำได้จริง" ใช้ (หลักฐานจาก 16,000+42 backtests):**
1. **Trend following แบบง่าย ๆ บน timeframe สูง** (EMA cross ~25 วัน, เทรด ~14 ครั้ง/ปี) — ชนะสุดในการศึกษา 42 ตัว
2. **ตัวกรอง "อย่าซื้อตอนฟอง"** (funding top 45% / crowded long) — ซื้อ drawdown ไม่ใช่ return
3. **อยู่ห่างจาก day trading/intraday** — fee ฆ่าทุกอย่างที่ timeframe ต่ำ
4. **ไม่เชื่อตัวเลขสวยจาก YouTube/influencer** — 400K views = −23% จริง, SMC win rate จริง 38–48%

**B. AI ที่ใช้แล้วได้ผลจริง (ความเห็นพ้องของชุมชน):**
1. **AI = ตัวกรอง/การ์ดกันความเสี่ยง ไม่ใช่ตัวตัดสินใจ** — "filter and guardrail, not decision-maker"
2. **LLM = research assistant** (สรุปข่าว/เหตุการณ์, เขียนโค้ด, ตรวจ thesis) + **execution/risk automation**
3. **อย่าให้ LLM ตัดสินผล backtest หรือ generate โค้ดโดยไม่ตรวจ** — ระวัง look-ahead bias
4. **Sentiment/data cleanup > price prediction**

**C. เทียบกับสถาปัตยกรรมที่เราสร้างไปแล้ว:**
- ✅ golden cross + regime filter (bull-only) = ตรงกับ "EMA cross 4 กฎ" ที่ชนะ
- ✅ ai_governor = ตรงกับ "AI เป็น filter/guardrail ไม่ใช่ decision-maker" (LLM ตรวจ regime/event ห้ามเข้า ไม่ใช่สั่งซื้อ)
- ✅ 90 วัน paper + validation gate ก่อน live = ตรงกับ "ML strategy dev ต้องมีวินัย (walk-forward/OOS)"
- ✅ funding-min ที่เราทดสอบ (PF 2.46, MaxDD −7.7%) = ตรงกับ "funding ซื้อ drawdown" ของ EmaCrossFunding — ตอนนี้มีหลักฐานภายนอกยืนยันด้วย
- ⚠️ จุดที่ควรระวังเพิ่มจากข้อมูลนี้: **กฎไม่ generalize ไป altcoin** (BTC ชนะ / alt แพ้) + funding สัญญาณกลับข้างปี 2023 → paper 90 วันของเราบน 30 เหรียญจะตอบคำถามนี้เอง
- 💡 ไอเดียใหม่จากข้อมูล: ลองเทรด **เฉพาะ BTC** เทียบกับ 30 เหรียญ (งานวิจัยภายนอกชี้ BTC เทรนด์ต่างจาก alt), ตัวกรอง "crowd long/short ratio" (มี edge 24h แต่ decay — ต้องเช็คทั้งสองครึ่งเหมือนที่เขาทำ)

---

## แหล่งอ้างอิง
1. r/algotradingcrypto — "I backtested 42 public Freqtrade strategies on 8 years of BTC data. 33 lost money" (Aug 2026) + [github.com/wiktorj137/btc-strategy-lab](https://github.com/wiktorj137/btc-strategy-lab)
2. r/algotrading — "Backtested 16,000 retail trading strategies… how do you avoid fooling yourself?" (Jan 2026)
3. r/algotrading — "I backtested a 400K views YouTube trading strategy" (Feb 2026)
4. r/ai_trading — "What's actually working in AI trading right now and what's just hype?" (Mar 2026)
5. r/ai_trading — "I asked this sub how good AI trading actually is" (Aug 2026)
6. r/algotrading — "Letting an LLM write your backtest? Check for this one-line look-ahead…" (May 2026), "LLM Supported Back Testing" (Jul 2026), "LLMs for trading" (Apr 2025)
7. r/Daytrading — "Can AI Trading Make You Profitable?" (Jul 2026)
8. Medium — "I Tested 23 'AI' Bots and Lost $14,000" (May 2026, ⚠️ เนื้อหาโปรโมต — ใช้แค่มุมที่ตรงกับงานวิจัย)
9. fortraders.com — "AI Trading: What Genuinely Works in 2026, and What Just Sells" (Aug 2026)
10. arXiv 2605.19337 — "Agentic Trading: When LLM Agents Meet Financial Markets" (Expert Systems with Applications, 2026)
11. r/algotrading/r/pinescript — กระทู้ TradingView webhook + freqtrade/Octobot/Gunbot (2025-2026)