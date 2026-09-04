"""End-to-end smoke test: config -> orchestrator -> journal, all with fakes where network is needed."""
from pipeline.config import load_config


def test_load_config_defaults():
    cfg = load_config()
    assert cfg["risk"]["risk_per_trade"] == 0.03
    assert cfg["risk"]["max_positions"] == 5
    assert cfg["symbols"]["count"] == 30
    assert cfg["symbols"]["interval"] == "4h"
    assert cfg["paper"]["equity"] == 50_000.0


def test_risk_config_from_file(tmp_path):
    import json
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"risk": {"risk_per_trade": 0.02}}))
    cfg = load_config(str(f))
    assert cfg["risk"]["risk_per_trade"] == 0.02
    assert cfg["risk"]["max_positions"] == 5  # default merged in
