---
name: crypto-scanner
description: >
  Scan Binance crypto markets for MA7/MA25 crossovers (Golden Cross / Death Cross), RSI momentum, volume spikes,
  and support/resistance levels. Generates trade setups with precise Entry, TP1, TP2, SL, and Risk:Reward ratio.
  Use when user asks to scan crypto markets, check pair technical analysis, look for MA crossovers, or evaluate trading setups.
---

Perform crypto market scanning and multi-timeframe technical analysis using Binance public API.

## Workflow

1. **Execute Market Scanner Script**:
   Run the Python script at `scripts/scanner.py` (or full path `~/.config/opencode/skills/crypto-scanner/scripts/scanner.py`):
   - Full market scan: `python3 scripts/scanner.py`
   - Single pair scan: `python3 scripts/scanner.py <SYMBOL>` (e.g. `python3 scripts/scanner.py ZECUSDT`)

2. **Technical Evaluation Criteria**:
   - **Required Fresh Crossover Trigger**: Recommend LONG only when MA7 freshly crosses above MA25 (Golden Cross), or SHORT only when MA7 freshly crosses below MA25 (Death Cross), between the two latest closed 1H candles. Trend-continuation setups without a fresh crossover must not receive a position recommendation.
   - **Trend Confirmation**: Require 4H MA7 vs MA25 alignment with the 1H crossover direction.
   - **RSI Momentum Guidelines**:
     - Optimal Long: 1H RSI between 50 - 68 (active momentum, not overbought).
     - Overbought Risk: 1H RSI > 70 (do not FOMO at local peaks).
     - Oversold Bounce: 4H RSI < 25 with 1H bullish reversal confirmation.
   - **Volume Verification**: 24h volume must be > $2,000,000 USDT to avoid low liquidity slippage.

3. **Output Response Structure (Match User's Language)**:
   Always respond in the user's language (Indonesian, English, etc.) and structure the response as follows:

   - **Best Scanned Pairs List**: Rank fresh 1H crossover pairs first. Present only pairs with a fresh Golden Cross or Death Cross; never promote trend-continuation pairs as position recommendations.
   - **Best Momentum Coin Recommendation**:
     - *If valid trade setup exists (LONG or SHORT)*:
       **Best Momentum Coin**: `PAIR` (Brief rationale: MA cross, RSI 1H/4H status, volume spike).
       **Position Suggestion [LONG or SHORT] (PAIR)**:
       - **Entry**: $ENTRY_RANGE
       - **TP 1**: $PRICE | **TP 2**: $PRICE
       - **Stop Loss (SL)**: $PRICE (below key support / MA25 for LONG, above resistance for SHORT)
       - **Risk:Reward**: $RR_RATIO (TP1) / $RR_RATIO (TP2)
     - *If NO strong/safe setup exists*:
       State clearly in user's language: "Currently no pairs meet the ideal criteria for opening a position. Recommended to **WAIT & SEE** because [reason: e.g. market sideways / low volume / extreme RSI without confirmation]."
