# 🚀 Universal Crypto Market Scanner AI Skill

> **Real-time Binance crypto scanner & technical analysis engine for AI Assistants, Coding Agents, and LLM CLI tools.**

`crypto-scanner` is an open-source AI agent skill that equips AI assistants with real-time crypto market scanning capabilities. It scans up to 100 high-volume Binance USDT pairs live to detect high-probability trade setups, Golden Crosses, Wilder RSI momentum, and volume spikes—delivering validated trade plans complete with **Entry, Take Profit (TP1 & TP2), Stop Loss (SL), and Risk-to-Reward (R:R) ratios**.

---

## ⚡ Compatibility Matrix

| Platform / Tool | Status | Integration Method |
| :--- | :---: | :--- |
| **Claude Code** | ✅ Tested | Skill Directory (`~/.claude/skills/`) |
| **OpenCode** | ✅ Tested | Skill Directory (`~/.config/opencode/skills/`) |
| **Codex CLI** | ✅ Tested | Agent Skill Folder |
| **Cursor** | 🟡 Manual Setup | System Prompt / Custom Agent |
| **Windsurf** | 🟡 Manual Setup | Custom Rules / Workflows |
| **Aider** | ⚪ Not Tested | Script Execution via CLI |

---

## 🔥 Key Features & Technical Specifications

- **🔒 Secure Network Requests**: Uses standard SSL verification with configurable timeout handling and detailed error logging to `sys.stderr`.
- **📈 Real-Time Binance Data**: Connects directly to Binance public REST APIs (no API key required) to fetch 24h tickers and OHLCV klines across up to 100 top USDT pairs.
- **📊 Multi-Timeframe Confluence**: Combines 1H execution signals with 4H trend confirmation to reduce false breakout risk.
- **🎯 Precise Technical Indicators**:
  - **Moving Averages**: 1H & 4H MA7 vs MA25 Golden Cross & Death Cross detection.
  - **Wilder's RSI**: Uses Wilder's RSI smoothing, designed to produce results comparable to common technical-analysis platforms. Handles flat market neutrality (RSI = 50.0).
  - **Volume Spike Detection**: Compares the latest closed 1H candle volume against the previous 20 closed candles (`volume_ratio >= 1.5x`).
  - **Liquidity Guard**: Automatically filters out low-volume pairs (< $2M 24h volume) to protect against slippage.
- **⚖️ Risk-to-Reward (R:R) Validation**:
  - Requires `TP1 > Entry`, `SL < Entry`, `Risk > 0`, and `RR_TP1 >= 1.5`.
  - Only generates a `LONG` recommendation when all risk management validation rules pass.
- **🛡️ Capital Protection ("WAIT & SEE")**: Explicitly recommends **WAIT & SEE** when market conditions are choppy, low-volume, or fail risk validation.
- **🌐 Multilingual Responses**: Adapts output language to match user queries (English, Indonesian, Spanish, etc.).

---

## 📁 Repository Structure

```text
crypto-scanner/
├── SKILL.md                 # Universal AI agent skill prompt & guidelines
├── README.md                # Skill documentation & compatibility matrix
├── LICENSE                  # MIT License
├── scripts/
│   └── scanner.py           # Core Python market scanner & indicator engine
├── tests/
│   └── test_scanner.py      # Unit tests for Wilder RSI and indicators
├── examples/
│   ├── input.md             # Sample user prompts
│   └── expected-output.md   # Sample trade analysis output
└── references/              # Technical analysis & indicator reference material
```

---

## ⚡ Quick Install

### Option 1: Via Skills CLI (Recommended)

Install interactively for any supported AI agent:

```bash
npx skills add wahyujhoo17/crypto-scanner
```

Install directly for specific agents:

```bash
# For Codex
npx skills add wahyujhoo17/crypto-scanner --agent codex

# For Claude Code
npx skills add wahyujhoo17/crypto-scanner --agent claude-code

# For OpenCode
npx skills add wahyujhoo17/crypto-scanner --agent opencode

# Install globally across all supported agents
npx skills add wahyujhoo17/crypto-scanner --global
```

Check for updates and update installed skills:

```bash
npx skills check
npx skills update
```

### Option 2: Manual Git Clone

```bash
# For Claude Code
git clone https://github.com/wahyujhoo17/crypto-scanner.git ~/.claude/skills/crypto-scanner

# For OpenCode
git clone https://github.com/wahyujhoo17/crypto-scanner.git ~/.config/opencode/skills/crypto-scanner
```

### Option 3: Standalone Execution & Testing

```bash
# Run unit tests
python3 -m unittest discover -s tests

# Run full market scan (Top 100 USDT pairs)
python3 scripts/scanner.py

# Analyze a specific trading pair
python3 scripts/scanner.py ZECUSDT
```

---

## 💡 Usage Examples

Simply prompt your AI assistant naturally:

- *"Scan the crypto market for the best MA crossover setups."*
- *"Cek pasar crypto mana pair yang paling potensial untuk open posisi."*
- *"Analyze ZECUSDT on 1H and 4H timeframes and provide a trade setup."*

---

## 📈 Sample AI Trade Output

```text
Top Scanned Pairs:
1. JTO/USDT - 1H Golden Cross (MA7 > MA25), RSI 1H: 63.4, RSI 4H: 64.5 (Volume Spike 1.6x)
2. NEAR/USDT - 1H Bullish Momentum, RSI 1H: 68.1, RSI 4H: 42.5

⭐ Best Momentum Recommendation: JTO/USDT
Fresh 1H Golden Cross confirmed with Wilder RSI alignment and volume spike (1.6x 20-candle average).

Position Suggestion [LONG] (JTO/USDT):
• Entry Range : $0.633 – $0.648
• Take Profit 1: $0.655
• Take Profit 2: $0.671
• Stop Loss   : $0.599 (Below MA25 support)
• Risk:Reward : 1:3.2 (TP1) / 1:4.6 (TP2)
```

---

## ⚠️ Risk Disclaimer

> **This project is an open-source educational market analysis tool, NOT financial advice.**  
> Cryptocurrency trading involves significant financial risk. Signals generated by this script may be delayed, incomplete, or affected by sudden market volatility. Always perform your own research (DYOR) and employ strict risk management.

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for details.

---

⭐ **If you find this skill helpful, give it a star on GitHub!**
