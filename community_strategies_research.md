# 🌐 วิจัย: เทคนิคการเทรดที่ชุมชนใช้งานจริง (Reddit / YouTube / TradingView / บอร์ดไทย)

> วันที่: 2026-09-05 | แหล่ง: r/algotrading, r/Daytrading, r/swingtrading, r/Trading, r/LETFs,
> TradingView scripts/ideas, Forex Factory, Elite Trader, ช่อง YouTube, Pantip
> วัตถุประสงค์: หาไอเดีย edge ที่เรายังไม่ได้ทดสอบ เทียบกับ benchmark golden+regime+TP2.8 (+77.2% 5 ปี)

---

## 1. สรุปสั้น

**ตระกูลกลยุทธ์ที่มีหลักฐานหนุนสุด = trend following + regime filter + breakout (volatility expansion)
— ซึ่งคือตระกูลเดียวกับระบบที่เรารันอยู่** ส่วนกลยุทธ์ที่ฮิตบนโซเชียล (SMC/ICT, FVG, pure MA cross)
มีหลักฐานอ่อนกว่า ทั้งจากงานวิจัยและจาก backtest ภายในโปรเจคเราเอง (SMC/FVG แพ้ทุกตัว)

ไอเดียที่ยังไม่ได้ทดสอบและน่าสนใจจริงมี 2 ข้อ:
1. **Funding rate / Open Interest เป็น regime หรือ entry filter** — crypto-native, noise น้อยกว่า crowd ratio
   ที่เพิ่ง reject ไป (มี `funding_cache` + flag `--funding-max/min` ใน harness อยู่แล้ว)
2. **Volatility squeeze → breakout เป็น regime state เสริม** — ปัจจุบัน regime filter มีแค่ bull/not-bull

---

## 2. เทคนิคที่ชุมชนใช้กันจริง (แบ่งตามตระกูล)

### 2.1 Trend following — หลักฐานหนุนสุด (ตระกูลเดียวกับระบบเรา)
| เทคนิค | ชุมชนหลัก | ความเห็นจากชุมชน |
|---|---|---|
| MA/EMA crossover (golden cross) | พูดถึงมากสุดทุกบอร์ด | "whipsaw machine" ในตลาด sideway — ที่รอดคือ **เอาไปทำ regime filter ไม่ใช่ entry ล้วน ๆ** (ตรงกับที่เราทำ: regime ทำให้ 5 ปี +77% vs -18.9% ถ้าไม่กรอง) |
| Pullback-in-trend (ย่อแตะ EMA20 ในขาขึ้น) | r/swingtrading, YouTube swing | ใช้คู่กับโครงสร้าง HH/HL ยืนยัน |
| Donchian / breakout จุดสูง N วัน | r/algotrading | "ไม่กี่กลยุทธ์พื้นฐานที่มีงานวิจัยรองรับ" (Turtle-style) |
| 200-day MA regime switch | r/LETFs, r/algotrading | "น่าเบื่อแต่ได้ผล" — ใช้เป็นตัวกรองความเสี่ยงระดับพอร์ต |

### 2.2 Mean reversion — ใช้ได้เฉพาะตลาด ranging
| เทคนิค | ชุมชนหลัก | ความเห็น |
|---|---|---|
| Bollinger Band mean reversion | r/algotrading | ใช้ได้**เฉพาะตลาด ranging** ต้องปิดตอน trend — เป็นปัญหา regime detection เหมือนเราพบ |
| RSI/Stochastic oversold-bounce | r/Daytrading, บอร์ดไทย | ฮิตสำหรับทอง/FX scalping |
| Pairs / statistical arbitrage | r/algotrading (quant) | อยู่ยากใน crypto — correlation พังบ่อย |
| VWAP reversion | r/Daytrading | ใช้เป็นทั้ง filter และ target |

### 2.3 Breakout / intraday
| เทคนิค | ชุมชนหลัก | ความเห็น |
|---|---|---|
| Opening Range Breakout (ORB) | r/Daytrading, QuantConnect | ถูก backtest มากที่สุดตัวหนึ่ง; ช่วง 15 นาทีแรก + VWAP กรองทิศ |
| Range/consolidation breakout + volume | r/swingtrading, TradingView | มาตรฐาน; ต้องมี volume ยืนยัน |
| Volatility squeeze → expansion | TradingView (Zeiierman) | Bollinger bandwidth/ATR ตีบแล้วแตก — framework เต็มตัวสร้างบนแนวนี้ |

### 2.4 Price action / SMC / ICT — ดังสุดแต่หลักฐานอ่อน
- **Order blocks, FVG, liquidity sweep, killzone** — กระแสหลักบน YouTube/TikTok
- Reddit แบ่ง 2 ฝั่ง: บางคนบอก "ช่วยให้ผมกำไร" / backtest ล่าสุดใน r/Trading เจอว่า FVG hold แย่กว่า random
- **โปรเจคเราเทสต์ SMC/FVG ไปแล้ว → แพ้ทุกตัว** (ดู `smc_backtest_result.md`) — สอดคล้องกับ verdict ชุมชน

### 2.5 On-chain / ตลาดอนุพันธ์
| เทคนิค | ความเห็น |
|---|---|
| MVRV / NUPL / whale accumulation / exchange reserves | ใช้เป็น macro filter |
| **Funding rate / Open Interest / Liquidation map** | ใช้เป็น contrarian signal (funding สูงมาก = crowded long) — **ไอเดียที่ยังไม่ได้เทสต์** |

---

## 3. สรุปตรง ๆ สำหรับโปรเจคเรา

1. **สิ่งที่เรารันอยู่ = ตระกูลที่หลักฐานหนุนสุดอยู่แล้ว** — trend following + regime filter + TP ตาม ATR
   และ backtest 5 ปี (+77.2% ผ่านตลาดหมี 2022) ก็สอดคล้องกับความเห็นชุมชน
2. **Funding rate filter** — มี flag + cache พร้อมใน harness ต้องเทสต์กับข้อมูล 5 ปีให้ครบวงจร
3. **SMC / FVG / pure MA cross / mean reversion** — หลักฐานอ่อนกว่าระบบปัจจุบันทั้งสิ้น ไม่ควรเสียเวลากับมัน
4. **Volatility squeeze → breakout** — เป็นไอเดียเสริม regime state ที่น่าศึกษาต่อ แต่ต้องระวัง overlap
   กับ golden cross (ทั้งคู่คือ "โมเมนตัมเพิ่งเริ่ม")

---

## 4. ที่มา (ตัวอย่าง)

- r/algotrading: "List of the most basic algorithmic trading strategies" — trend/momentum/mean-reversion/pairs
- r/Daytrading: "The best trading strategy after 3 years" — ORB, VWAP, price action
- r/swingtrading: "What kind of strategies are you using" — pullback-in-trend, 20 EMA
- r/LETFs: 200-day MA regime switch
- r/Trading: FVG backtest "holds less than random"
- TradingView (Zeiierman): volatility squeeze → breakout framework