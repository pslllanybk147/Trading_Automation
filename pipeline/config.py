"""Configuration loading with defaults per the design spec."""
from __future__ import annotations
import json
import os
from pathlib import Path

DEFAULTS = {
    "symbols": {"count": 30, "interval": "4h", "limit": 500},
    "risk": {
        "risk_per_trade": 0.03,
        "max_positions": 5,
        "max_total_risk": 0.10,
        "max_day_losses": 3,
        "max_total_dd": 0.20,
    },
    "paper": {"equity": 50_000.0, "fee_rate": 0.001, "slippage": 0.0005},
    "tp": {
        "partial_fraction": 0.0,   # 0 = ปิดเต็มที่ TP1 (พฤติกรรมเดิม); 0.5 = ปิดครึ่งที่ TP1
        "trail_atr": 2.0,           # ส่วนเหลือตาม trailing stop ระยะ trail_atr ATR จาก high สุด
        "tp2_atr": 0.0,             # ถ้า >0: ส่วนเหลือปิดที่ TP2 = entry + tp2_atr*ATR แทน trailing
    },
    "validation": {
        "min_sharpe": 0.0, "min_profit_factor": 1.3,
        "win_rate_min": 0.30, "win_rate_max": 0.60, "max_dd": 0.20,
    },
    "governor": {"model": "gpt-4o-mini", "use_llm": False},
}


def load_config(path: str | None = None) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    config_path = path or os.getenv("PIPELINE_CONFIG", "config.json")
    p = Path(config_path)
    if p.exists():
        with open(p) as f:
            user_cfg = json.load(f)
        for section, values in user_cfg.items():
            if section in cfg and isinstance(values, dict):
                cfg[section].update(values)
            else:
                cfg[section] = values
    if os.getenv("PIPELINE_EQUITY"):
        cfg["paper"]["equity"] = float(os.getenv("PIPELINE_EQUITY"))
    return cfg
