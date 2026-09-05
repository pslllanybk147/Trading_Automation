# Trading History Summary

> สรุปข้อสรุปการวางแผนเทรด + ผลวิจัยจากแหล่งต่าง ๆ
> โปรเจค: Trading_Automation
> วันที่อัปเดต: 2026-09-04
> หมายเหตุ: ไฟล์นี้สรุปจากบทสนทนา + การวิจัยออนไลน์ ควรใช้ประกอบการตัดสินใจ ไม่ใช่คำแนะนำการลงทุน

---

## 1. สกิลที่ติดตั้งแล้ว (`.agents/skills/`)

| สกิล | บทบาทใน pipeline | ที่มา |
|---|---|---|
| `brainstorming` | วางแผน/ออกแบบก่อนลงมือ | obra/superpowers |
| `crypto-scanner` | สแกน 100 คู่ Binance หา Golden Cross + Volume Spike | wahyujhoo17/crypto-scanner |
| `dexscreener-api` | ดึงข้อมูลคู่ DEX ทุกเชน | metavox/claude-trading-skills |
| `defillama-api` | TVL / Yields / Fees — กรอง fundamentals | metavox/claude-trading-skills |
| `coingecko-api` | ข้อมูล 13,000+ เหรียญ + global stats | metavox/claude-trading-skills |
| `regime-detection` | รู้ว่าตลาดอยู่ในช่วงไหน (trend/range/crisis) | metavox/claude-trading-skills |
| `vectorbt` | Backtest แบบ vectorized เร็ว | metavox/claude-trading-skills |
| `walk-forward-validation` | กัน overfit (time-series split + CPCV) | metavox/claude-trading-skills |
| `opentrade-cex` | เทรด CEX จริง (risk engine 4 ชั้น, TP/SL/OCO) | 6551Team/opentrade |
| `vizier` | คุมทั้งพอร์ต: Kelly sizing, trailing stop, scorecard | pedrobraiti/vizier-trading-skill |

**สกิลในไฟล์ `popular_trading_skill.md` ที่ยังไม่ได้ติดตั้ง** (หาใน marketplace ไม่เจอ): `cryptocurrency-trader`, `mirofish`, `ai-hedge-fund-manager`, `moss-trade-bot-factory` — ใช้ `regime-detection` + `vizier` ทดแทนในส่วน signal/risk

**สกิลเพิ่มเติมที่น่าสนใจใน metavox/claude-trading-skills** (ยังไม่ติดตั้ง): `sentiment-analysis`, `whale-tracking`, `token-holder-analysis`, `trade-journal`, `position-sizing`, `kelly-criterion`, `exit-strategies`, `risk-management`

---

## 2. สรุปผลวิจัย: ทำไมคนส่วนใหญ่แพ้ / คนที่ชนะทำอะไรต่าง

### 2.1 สถิติสำคัญ (จากงานวิจัยจริง)

| หลักฐาน | ตัวเลข |
|---|---|
| Day trader ขาดทุน (งานวิจัยบราซิล) | **97%** |
| Day trader กำไรสม่ำเสมอ (Barber & Odean, ไต้หวัน) | **~1%** |
| ผลตอบแทน day trader หลังหักต้นทุน (CMC) | **-3.8%/ปี** |
| ผลตอบแทน swing trader หลังหักต้นทุน (CMC) | **+2.1%/ปี** |
| เทรด memecoin แล้วขาดทุน | **>90%** |
| ผ่าน prop firm challenge (FTMO/Topstep) | **~5-10%** |
| ผู้ที่ผ่านแล้วอยู่รอดระยะยาว | ~70% ของบัญชี funded ตายในที่สุด |

### 2.2 8 พฤติกรรมของคนที่เทรดกำไร (จาก journal หลายแสนเทรด — Edgewonk)

1. **เล่น setup เดียว มากสุดสอง** — เชี่ยวชาญลึก แทนที่จะจับ 5-10 กลยุทธ์
2. **เทรดวันละ 2-4 ชั่วโมง** — ปกป้องช่วงเวลาที่ดีที่สุดของตัวเอง
3. **exit สำคัญกว่า entry** — กำหนด SL/TP/กฎการจัดการก่อนเข้าเสมอ
4. **ไม่ยึดติด win rate** — เน้น expectancy + reward:risk
5. **มีกระบวนการชัดเจน** — routine, watchlist, กฎตายตัว
6. **ทดสอบต่อเนื่องแบบตรงจุด** — ปรับนิดเดียวแล้ววัดผล
7. **อยู่กับ drawdown ได้** — ไม่ทิ้งระบบหลังแพ้ไม่กี่ครั้ง
8. **ความคาดหวังสมเหตุสมผล** — เป้า modest + ให้ compounding ทำงาน

### 2.3 จุดที่คนแพ้ซ้ำกันทุกตลาด

- เทรดถี่เกินไป (fee + slippage กินกำไร)
- ไม่มีกฎ risk management
- Overfit backtest — in-sample อธิบายผลนอกตัวอย่างได้แค่ **1-2%** (CXO Advisory, 888 กลยุทธ์)
- ตัดสินใจด้วยอารมณ์ (FOMO / แก้แค้น / ยึดติด position ที่ขาดทุน)

---

## 3. AI เข้ามาช่วยได้จริงแค่ไหน

**จุดแข็ง (edge จริง ~3-8% ไม่ใช่ "win rate 80%"):**
- ✅ สแกนปริมาณมากในไม่กี่วินาที
- ✅ Backtest parameter นับพันชุด
- ✅ บังคับ walk-forward validation (กัน overfit)
- ✅ Risk engine ทำงานโดยไม่มีอารมณ์
- ✅ Journal + วิเคราะห์พฤติกรรมตัวเอง
- ✅ Sentiment / regime context

**ข้อจำกัด:**
- ❌ ทำนาย regime ใหม่ที่ไม่เคยเห็นใน data training ไม่ได้
- ❌ แทน judgment ของมนุษย์ไม่ได้
- ⚠️ **AI ขยายวินัย ไม่ได้สร้างวินัย** — คนไม่มีกฎ risk จะแพ้เร็วขึ้นด้วย AI
- ⚠️ รูปแบบที่ดีสุดสำหรับรายย่อยคือ **hybrid**: ระบบสแกน/กรอง/risk อัตโนมัติ + มนุษย์กดปุ่มเข้าเทรด

---

## 4. การวางแผนเทรด: 3 แนวทางที่เสนอ

### Design A — Swing Rule-Based (แนะนำ)
```
[crypto-scanner] → [vectorbt backtest] → [walk-forward ผ่าน?] → [vizier: size + TP/SL] → [opentrade-cex]
```
- ถือ 1-7 วัน, เทรด ~6-10 ครั้ง/2 เดือน
- ข้อดี: ค่า fee น้อย, สถิติบวกชัดเจนที่สุด, เหมาะกับเงินทุนน้อย
- ข้อเสีย: โตช้า ต้องอดทน

### Design B — Day Trade CEX
- เข้า-ออกภายในวัน, มี circuit breaker
- ข้อเสีย: สถิติแย่ที่สุด (97% ขาดทุน), fee กินกำไร, ต้องเฝ้าหน้าจอ

### Design C — Swing + On-chain Filter
- Swing เป็นแกน + ตรวจ whale/holder ก่อนเข้า (กันปั๊ม-ทิ้ง)
- ต้องติดตั้งสกิลเพิ่ม: `whale-tracking`, `token-holder-analysis`

**ข้อสรุป:** เลือก **Design A** เป็นฐาน เพราะ implement สิ่งที่หลักฐานบอกว่ามันได้ผลตรงตัวที่สุด

### 5. คาดการณ์ผลตอบแทนจริง (เงินต้น 3,000 บาท, swing 2 เดือน, ทบต้น)

| Scenario | Return/เดือน | หลัง 2 เดือน |
|---|---|---|
| เฉลี่ยคนทั่วไป | ~+0.2% | ~3,010 บาท |
| เทรดดี มีวินัย | +2-4% | 3,120 - 3,240 บาท |
| เก่งจริง (top 10%) | +5-8% | 3,300 - 3,500 บาท |

⚠️ 3,000 บาทเล็กเกินกว่าจะ "ทบต้น" ให้เห็นผล — แนะนำให้มองเป็นบัญชีเรียนรู้ + ทำระบบให้สม่ำเสมอก่อน

---

## 6. การเทรดตามข่าว (News Trading) — ข้อมูลจากการวิจัย

### 6.1 คืออะไร
News trading = เทรดโดยใช้ประโยชน์จากความผันผวนรอบ ๆ เหตุการณ์ข่าว:
- **เหตุการณ์ตามกำหนด:** CPI, FOMC, NFP, รายงาน earnings, การประชุม Fed
- **เหตุการณ์ไม่คาดคิด:** ภัยธรรมชาติ, black swan, ข่าวด่วน

### 6.2 กลยุทธ์หลัก
1. **Buy the rumor, sell the news** — ราคาวิ่งขึ้นล่วงหน้าตอนมีข่าวลือ แล้วพลิกกลับ/นิ่งเมื่อข่าวออกจริง
   - ตัวอย่างจริง: BTC ร่วงหลัง 7 ใน 8 ครั้งของ FOMC ปี 2025 (CoinDesk) แม้ผลการประชุมจะต่างกัน
   - ตัวอย่าง: Bitcoin halving / spot ETF approval — ราคามักขึ้นก่อน แล้ว "sell the news"
2. **Fading** — เทรดสวนกระแสตอน enthusiasm จาง (เช่น หุ้นเปิดพุ่งหลัง earnings แล้ว short ตอน optimism หมด)
3. **เล่น volatility** — ไม่ต้องเดาทิศทาง ใช้ straddle/เทรดทั้งสองทางรอบเวลาประกาศ

### 6.3 ลักษณะสำคัญ (Investopedia)
- News traders ส่วนใหญ่เป็น **day trader** — ปิด position ภายในวัน เพราะผลของข่าวอยู่สั้น
- ใช้ข้อมูลเชิงประวัติศาสตร์ (ผล earnings ครั้งก่อน) ทำนายผลครั้งหน้า
- ใช้ alert + วิเคราะห์ correlation ระหว่างข่าวกับ price action
- โอกาสอยู่แค่ช่วงที่ข่าวยัง "สด"

### 6.4 ความเสี่ยง / ข้อควรระวัง
- **Prop firm ส่วนใหญ่ห้าม news trading** — ต้องเช็คกฎก่อน (บางเจ้าในปี 2026 อนุญาตแต่มีเงื่อนไข)
- Volatility ตัดสองทาง — spread กว้าง + slippage สูงช่วงประกาศข่าว
- Algo ของสถาบันวิ่งเร็วกว่ารายย่อย — ราคาปรับตัวภายในมิลลิวินาที
- "Sell the news" ไม่ได้เกิดทุกครั้ง — บางเหตุการณ์เป็น "buy the news" (เช่น ETF launch ที่ไม่ใช่ sell-the-news ตามที่ Pantera/MarketWatch วิเคราะห์)

### 6.5 AI ช่วยได้ยังไงใน news trading
- ✅ sentiment-analysis: รวมสัญญาณจากข่าว/โซเชียล ก่อนราคาปรับ
- ✅ ตั้ง alert อัตโนมัติ + correlate กับ price action
- ✅ Backtest รอบเหตุการณ์ย้อนหลัง (Build Alpha: ทดสอบก่อน/ระหว่าง/หลังเหตุการณ์ 25+ รายการ)
- ⚠️ แต่ news trading โดยแก่นคือ day trading — กลับไปเจอสถิติ 97% ขาดทุนอีกครั้ง
- 💡 **ข้อแนะนำ:** เอา news เป็น **ตัวกรอง/context** ของ swing trade (เช่น หลบการเข้าเทรดช่วง FOMC/CPI, หรือใช้ "sell the news" เป็นสัญญาณ exit) ดีกว่ามาเทรดช่วงประกาศข่าวตรง ๆ

---

## 7. เทคนิคของสุดยอดเทรดเดอร์ระดับโลก

> ดูไฟล์ `legendary_traders_summary.md` — วิเคราะห์ Ray Dalio, Jim Simons (Renaissance), George Soros, Paul Tudor Jones, Turtle Traders (Richard Dennis/Ed Seykota) + ตารางสิ่งที่เอามาปรับใช้กับระบบเราได้จริง

**แก่นร่วมของคนที่ชนะทุกยุค:** ระบบ/กฎตายตัว > การทำนาย, risk มาก่อน return, edge มาจากความซ้ำซากเชิงสถิติ (ไม่ใช่รู้ข่าวก่อน), ตัดขาดทุนเร็ว, กระจายหลาย edge, อยู่กับ drawdown ได้, และวินัยคือ edge จริง

---

## 8. Next Steps

- [ ] ล็อก Design A (swing rule-based) และเขียน design spec เต็ม
- [ ] ตั้งค่า pipeline: data → signal → backtest → paper trade ให้รัน end-to-end
- [ ] ใช้ vizier ในโหมด paper-first ก่อน
- [ ] เพิ่ม risk limit + trade journal ก่อนขึ้น live
- [ ] (ทางเลือก) ติดตั้งสกิลเพิ่ม: sentiment-analysis, whale-tracking, token-holder-analysis, trade-journal