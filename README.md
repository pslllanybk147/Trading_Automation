# Trading Automation Pipeline

Full-auto swing trading pipeline on Binance Spot — rule-based signal engine + AI governor + risk engine, paper-first.

## Strategy (backtest-validated on 2-3y, walk-forward)

- **Signal:** golden cross (MA7 × MA25) only — turtle breakout is disabled (it
  dragged returns down: golden+turtle −45% vs golden-only in backtest)
- **Entry filters:** cross within last 5 bars, RSI 45–75, volume ≥ 1.5× the
  20-bar average
- **Hard blocks (AI governor):** bear/range regime + scheduled macro events
  (FOMC/CPI ± 1 day)
- **Exits:** SL −2 ATR, TP1 +2.8 ATR (R:R = 1.4). TP1 = 2.0 ATR was tested and
  **failed out-of-sample** — 2.5–3.0 is the robust plateau
- **Backtest result of this config:** +77% / MaxDD −17.7% / PF 2.0 / 50 trades
  over 3 years (2023-09 → 2026-09), profitable every year incl. the 2025
alt-rally; TP 2.0 did not survive the train/test split

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY (optional), Binance keys (only for live, after paper gate)
```

## Usage

```bash
python main.py cycle     # run daily cycle: scan signals -> open new paper trades
python main.py check     # check open positions against SL/TP (4h)
python main.py reconcile # verify journal and paper account agree
python main.py status    # monthly scorecard
python main.py kill      # engage kill-switch (create STOP file)
```

### A/B: golden+regime (benchmark) vs golden+regime+MHM gate

The MHM gate (Multi-Horizon Momentum ≥ 2, AHL-style) is a config-level second
filter, off by default. Walk-forward verdict: return = benchmark, max DD
shallower in 3/4 OOS folds — i.e. a risk reducer, not an alpha source. Run both
arms side by side with separate journals:

```bash
cp config_ab_mhm.example.json config_ab_mhm.json   # arm B: mhm_gate=true, own journal
python main.py --config config_ab_mhm.json cycle   # arm B cycle/check/status
python main.py status                              # arm A (benchmark) scorecard
python main.py --config config_ab_mhm.json status  # arm B scorecard
```

Scheduled (Windows Task Scheduler): `run_task.cmd cycle` for arm A (existing
`TradingCycle`), and `run_task.cmd cycle config_ab_mhm.json` for arm B — it logs
to `logs/scheduled_ab.log` and uses `data/journal_ab_mhm.db`, so the two arms
ever mix trades. Compare after 90 days via the two scorecards.

## Scheduled runs (Windows Task Scheduler)

The pipeline is meant to run unattended so paper stats accumulate over 90 days:

| Task | Schedule | Command |
|---|---|---|
| `TradingCycle` | daily 01:00 | `run_task.cmd cycle` |
| `TradingCheck4h` | every 4 h | `run_task.cmd check` |

Every run is a fresh process: the orchestrator **restores paper state from the
SQLite journal** (`data/journal.db` — the source of truth) at startup, so open
positions and equity survive across processes and SL/TP orders from earlier
runs are still managed. `main.py cycle` refuses to open a second position on a
symbol it already holds.

Output goes to `logs/scheduled.log` via `run_task.cmd`.

## Safety

- Paper-first: ≥ 90 days paper with ≥ 20 trades and passing 9 gates before live
- Fail-closed: any error → no trade; state restore failure aborts before trading
- Kill-switch: create a `STOP` file (or `python main.py kill`) to halt the daily cycle

## Trade chart (TradingView-style)

```bash
python plot_trades.py --all    # journals + benchmark backtest -> trade_chart.html
```

Self-contained HTML with lightweight-charts (TradingView open-source): 4h candles
from `data/cache.db`, buy/sell markers (PnL on exits), volume bars, a per-symbol
tab, a summary table, and a daily buy/sell log. Works for the paper journals
(`--journal data/journal_ab_mhm.db` for arm B) and for any backtest JSON with
full trade records (`--result <file>`; the harness saves entry/exit since this session).

## Tests

```bash
python -m pytest tests/ -v
```

## Docs

- Design spec: `docs/superpowers/specs/2026-09-04-trading-pipeline-design.md`
- Implementation plan: `docs/superpowers/plans/2026-09-04-trading-pipeline.md`
- Research: `trading_history_summary.md`, `news_trading_summary.md`, `legendary_traders_summary.md`
