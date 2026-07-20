from pathlib import Path

import pandas as pd

from src.config import load_config
from src.run_pipeline import reconcile_frames


ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_config_is_valid():
    config = load_config(ROOT / "params" / "pipeline_config.json")
    assert config["policy_version"] == "category-decision-v2"
    assert sum(config["scoring_weights"].values()) == 1


def test_reconciliation_covers_full_modules_and_promo_window():
    m1 = pd.DataFrame([{"cat": "housewares", "gmv": 100.0}])
    sku = pd.DataFrame(
        [
            {"price_band": "low", "gmv": 40.0},
            {"price_band": "high", "gmv": 60.0},
        ]
    )
    pricing = pd.DataFrame(
        [
            {"price_band": "low", "base_gmv": 40.0},
            {"price_band": "low", "base_gmv": 40.0},
            {"price_band": "high", "base_gmv": 60.0},
            {"price_band": "high", "base_gmv": 60.0},
        ]
    )
    promo = pd.DataFrame([{"gmv": 12.0}, {"gmv": 8.0}])
    audit = reconcile_frames(
        100.0, 20.0, m1, sku, pricing, promo, "housewares", 0.01
    )
    assert audit["full_period"]["passed"] is True
    assert audit["promotion_window"]["passed"] is True
