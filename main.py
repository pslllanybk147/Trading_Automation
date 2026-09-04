"""CLI entrypoint: python main.py cycle|check|reconcile|status|kill"""
from __future__ import annotations
import logging
import sys
from pathlib import Path

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("logs/pipeline.log")],
)

from pipeline.config import load_config          # noqa: E402
from pipeline.journal import Journal             # noqa: E402
from pipeline.orchestrator import Orchestrator   # noqa: E402


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "cycle"
    cfg = load_config()
    journal = Journal()
    orch = Orchestrator(journal=journal)

    if cmd == "cycle":
        summary = orch.run_daily_cycle()
        print(f"Cycle done: {summary}")
    elif cmd == "check":
        orch.check_open_positions()
        print("Position check done.")
    elif cmd == "reconcile":
        orch.reconcile()
        print("Reconcile done.")
    elif cmd == "status":
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")
        sc = journal.monthly_scorecard(month)
        print(f"Scorecard {month}: {sc}")
    elif cmd == "kill":
        Path("STOP").touch()
        print("Kill-switch engaged: STOP file created. Daily cycle will not open new trades.")
    else:
        print("Usage: python main.py [cycle|check|reconcile|status|kill]")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
