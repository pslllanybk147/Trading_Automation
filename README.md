# Trading Automation Pipeline

Full-auto swing trading pipeline on Binance Spot — rule-based signal engine + AI governor + risk engine, paper-first.

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

## Tests

```bash
python -m pytest tests/ -v
```

## Docs

- Design spec: `docs/superpowers/specs/2026-09-04-trading-pipeline-design.md`
- Implementation plan: `docs/superpowers/plans/2026-09-04-trading-pipeline.md`
- Research: `trading_history_summary.md`, `news_trading_summary.md`, `legendary_traders_summary.md`
