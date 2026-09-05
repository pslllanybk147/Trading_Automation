# Popular Trading Skills - 20 สกิลน่าสนใจสำหรับ Crypto Trade & Pipeline

> สรุปจากการคุยกัน วันที่ 2026-09-03
> โปรเจค: D:\Trading_Automation
> มาตรฐาน: SKILL.md compatible กับ OpenCode (`.opencode/skills/` หรือ `~/.config/opencode/skills/`)

โฟลเดอร์นี้ยังว่าง แนะนำโครง:
```
D:\Trading_Automation\
  .opencode/skills/<skill-name>/SKILL.md
  popular_trading_skill.md (ไฟล์นี้)
```

---

## ภาพรวม Pipeline

```
[Market Data] -> [On-chain / Smart Money] -> [Signal] -> [Backtest] -> [Execution + Risk]
```

---

## กลุ่ม 1: Market Data Pipeline (1-5)

### 1. `crypto-scanner`
- **ทำอะไร:** สแกน 100 คู่ Binance USDT real-time หา Golden Cross MA7/MA25 + Wilder RSI + Volume Spike 1.5x ออก Entry / TP1 / TP2 / SL / R:R
- **Repo:** https://github.com/wahyujhoo17/crypto-scanner
- **ติดตั้ง OpenCode:**
```bash
npx skills add wahyujhoo17/crypto-scanner --agent opencode
```
- **เหมาะกับ:** Day-trade / หา setup รายวัน

### 2. `dexscreener-api`
- **ทำอะไร:** ดึงคู่ DEX ทุกเชน ไม่ต้อง auth ใช้ทำ universe screening / หาเหรียญใหม่
- **Repo:** https://github.com/metavox/claude-trading-skills
- **เหมาะกับ:** DEX screener เริ่มต้น pipeline

### 3. `birdeye-api`
- **ทำอะไร:** ราคา Solana + OHLCV + metadata + trader activity
- **Repo:** https://github.com/metavox/claude-trading-skills (หมวด Market Data & APIs)
- **เหมาะกับ:** สาย Solana / memecoin

### 4. `coingecko-api`
- **ทำอะไร:** ข้อมูล 13,000+ เหรียญ + global stats + history
- **Repo:** https://github.com/metavox/claude-trading-skills
- **เหมาะกับ:** Top-down filter / market overview

### 5. `defillama-api`
- **ทำอะไร:** TVL / Yields / Fees / Bridges / Volumes
- **Repo:** https://github.com/metavox/claude-trading-skills
- **เหมาะกับ:** กรองเหรียญ DeFi ที่มี fundamentals จริง

---

## กลุ่ม 2: On-chain / Smart Money (6-9)

### 6. `opentrade-market`
- **ทำอะไร:** ราคา + K-line + recent trades + smart money signals (KOL/whale)
- **Repo:** https://github.com/6551Team/opentrade
- **เหมาะกับ:** Data feed กลางทั้ง CEX+DEX

### 7. `opentrade-token`
- **ทำอะไร:** search token / info / holder distribution / trending
- **Repo:** https://github.com/6551Team/opentrade
- **เหมาะกับ:** Due diligence เหรียญก่อนเข้า

### 8. `whale-tracking + wallet-profiling`
- **ทำอะไร:** ตามกระเป๋าใหญ่ หา accumulation/distribution + win-rate / PnL / style
- **Repo:** https://github.com/metavox/claude-trading-skills (หมวด On-Chain Analysis)
- **เหมาะกับ:** Copy-trade / ตามเจ้า

### 9. `token-holder-analysis`
- **ทำอะไร:** เช็ค concentration / insider / bundler / sybil กัน rug
- **Repo:** https://github.com/metavox/claude-trading-skills
- **เหมาะกับ:** Risk filter ก่อนซื้อเหรียญเล็ก

---

## กลุ่ม 3: Signal Generation (10-13)

### 10. `cryptocurrency-trader`
- **ทำอะไร:** สาย quant: Bayesian inference + Monte Carlo 10,000 scenarios + GARCH + VaR/CVaR/Sharpe + Kelly + 6-stage validation + 14 circuit breakers ออก LONG/SHORT/NO_TRADE พร้อม confidence
- **Repo:** https://playbooks.com/skills/openclaw/skills/cryptocurrency-trader-skill
- **ใช้:** `python skill.py analyze BTC/USDT --balance 10000`
- **เหมาะกับ:** Signal แบบมี risk ครบ

### 11. `mirofish-opencode-agent-guide`
- **ทำอะไร:** Swarm AI traders มา debate กันแล้วสรุป consensus bullish/bearish/neutral
- **Repo:** https://skills.rest/skill/mirofish-opencode-agent-guide
- **เหมาะกับ:** Second opinion กัน bias โมเดลเดี่ยว

### 12. `feature-engineering + signal-classification`
- **ทำอะไร:** สร้าง feature จาก OHLCV + on-chain แล้วเทรน XGBoost/LightGBM แบบ walk-forward
- **Repo:** https://github.com/metavox/claude-trading-skills (หมวด ML for Trading)
- **เหมาะกับ:** สาย ML signal

### 13. `sentiment-analysis`
- **ทำอะไร:** ดึง sentiment จาก social/news มาทำ signal
- **Repo:** https://github.com/metavox/claude-trading-skills
- **เหมาะกับ:** เอาไปรวมกับเทคนิคอลเป็น confluence

---

## กลุ่ม 4: Backtest / Research (14-17)

### 14. `vectorbt`
- **ทำอะไร:** Backtest แบบ vectorized เร็วสุด ใช้ optimize parameter เยอะๆ
- **Repo:** https://github.com/metavox/claude-trading-skills (หมวด Backtesting & Strategy)
- **เหมาะกับ:** Backtest หลักของ pipeline

### 15. `walk-forward-validation`
- **ทำอะไร:** กัน overfit: time-series split + CPCV
- **Repo:** https://github.com/metavox/claude-trading-skills
- **เหมาะกับ:** บังคับใช้ก่อนขึ้น live

### 16. `ai-hedge-fund-manager + quant-mathematician`
- **ทำอะไร:** ยก desk มาเลย: สร้าง Pine Script -> backtest 10 คู่ x 4 timeframe -> optimize -> compare -> verdict Reject/Watchlist/Incubate/Candidate
- **Repo:** https://github.com/DaviddTech/ai-trading-agent
- **เหมาะกับ:** สาย TradingView / Pine Script

### 17. `moss-trade-bot-factory`
- **ทำอะไร:** พูดภาษาคนแล้วสร้าง bot + backtest Hyperliquid ฟีจริง + evolve รายสัปดาห์
- **Repo:** https://github.com/moss-site/moss-trade-bot-skills
- **เหมาะกับ:** สร้าง bot ไว + leaderboard copy

---

## กลุ่ม 5: Execution / Risk / Portfolio (18-20)

### 18. `opentrade-cex`
- **ทำอะไร:** เทรด Spot + Futures 5 CEX ด้วย API เดียว มี risk engine 4 ชั้น (rate-limit, price-deviation 10%, position-size, balance-reserve) + TP/SL/OCO/Hedge mode
- **Repo:** https://github.com/6551Team/opentrade
- **เหมาะกับ:** Execution จริงสาย CEX

### 19. `opentrade-dex-swap + dex-execution + slippage-modeling`
- **ทำอะไร:** Swap หลายเชนผ่าน Jupiter + ประเมิน slippage / price impact + Jito bundle กัน MEV
- **Repo:** https://github.com/6551Team/opentrade + https://github.com/metavox/claude-trading-skills
- **เหมาะกับ:** Execution สาย DEX/Solana

### 20. `vizier + risk-management + exit-strategies`
- **ทำอะไร:** ตัวจบ pipeline: Vizier เป็น brain คุม Scout (หาข้อมูล) + Valet (ยิงออเดอร์) แบบ paper-first, คำนวณ size ด้วย Kelly/fractional + trailing-stop/tiered-TP/time-exit + scorecard เทียบ BTC/SPY
- **Repo:**
  - https://github.com/pedrobraiti/vizier-trading-skill
  - https://github.com/metavox/claude-trading-skills (risk-management, position-sizing, kelly-criterion, exit-strategies)
- **เหมาะกับ:** คุมทั้งพอร์ต + risk สุดท้าย

---

## Starter Pack แนะนำ (เริ่ม 6 ตัวพอ)

1. `crypto-scanner` -> ได้ signal วันนี้เลย
2. `dexscreener-api + defillama-api` -> data pipeline
3. `cryptocurrency-trader` -> signal แบบมี risk
4. `vectorbt + walk-forward-validation` -> backtest กันเจ๊ง
5. `opentrade-cex` -> execution จริง
6. `vizier` -> คุมทั้ง pipeline

### ทางเลือกตามสาย
- **สาย CEX ซิ่ง (Binance/Hyperliquid):** 1, 6, 10, 14, 18, 20
- **สาย DEX/Solana On-chain:** 2, 3, 8, 9, 19
- **สาย Quant/Backtest:** 10, 12, 14, 15, 16, 17

---

## วิธีติดตั้งกับ OpenCode (Windows)

```powershell
# 1. เช็คโฟลเดอร์ config
Test-Path "$env:USERPROFILE\.config\opencode\skills"

# 2a. ติดตั้งแบบ auto (ถ้า repo รองรับ)
npx skills add wahyujhoo17/crypto-scanner --agent opencode

# 2b. ติดตั้งแบบ manual (project-local)
# git clone <repo-url> D:\Trading_Automation\.opencode\skills\<skill-name>
```

## Next Step
- [ ] เลือก 3-6 สกิลแรกมาลงจริง
- [ ] สร้าง `.opencode/skills/` ในโปรเจค
- [ ] ต่อ data -> signal -> backtest -> paper trade ให้รัน end-to-end ได้
- [ ] เพิ่ม risk limit + journal ก่อนขึ้น live
