# Trading Automation Pipeline

Full-auto swing trading pipeline on Binance Spot — rule-based signal engine + AI governor + risk engine, paper-first.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY (optional), Binance keys (only for live, after paper gate)
```

## Usage

```bash
python main.py cycle    # run daily cycle (paper mode)
python main.py status   # monthly scorecard
python main.py kill     # engage kill-switch (create STOP file)
```

## Safety

- Paper-first: ≥ 90 days paper with ≥ 20 trades and passing 9 gates before live
- Fail-closed: any error → no trade
- Kill-switch: `STOP` file or `python main.py kill` closes everything

## Tests

```bash
python -m pytest tests/ -v
```

## Docs

- Design spec: `docs/superpowers/specs/2026-09-04-trading-pipeline-design.md`
- Implementation plan: `docs/superpowers/plans/2026-09-04-trading-pipeline.md`
- Research: `trading_history_summary.md`, `news_trading_summary.md`, `legendary_traders_summary.md`
