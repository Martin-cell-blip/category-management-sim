"""Validated configuration for the category decision pipeline."""
from __future__ import annotations

import json
from pathlib import Path


def load_config(path: str | Path) -> dict:
    config_path = Path(path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    required = {
        "policy_version",
        "main_category",
        "benchmark_categories",
        "scoring_weights",
        "thresholds",
        "pricing",
        "promotion_windows",
        "reconciliation_tolerance",
    }
    missing = required - set(config)
    if missing:
        raise ValueError(f"pipeline_config 缺少字段: {sorted(missing)}")
    weights = config["scoring_weights"]
    if set(weights) != {"gmv", "velocity", "review", "freight"}:
        raise ValueError("scoring_weights 必须包含 gmv/velocity/review/freight")
    if abs(sum(float(value) for value in weights.values()) - 1.0) > 1e-9:
        raise ValueError("scoring_weights 权重之和必须为 1")
    if not config["benchmark_categories"]:
        raise ValueError("benchmark_categories 不得为空")
    if config["main_category"] in config["benchmark_categories"]:
        raise ValueError("主品类不得同时作为对照品类")
    if not 0 < float(config["thresholds"]["delist_percentile"]) < 1:
        raise ValueError("delist_percentile 必须在 0 与 1 之间")
    return config
