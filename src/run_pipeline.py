"""
run_pipeline.py — 京东采销·家居日用品类经营模拟盘 一键管线
数据:Olist 巴西电商公开数据(方法论演示;中国市场判断见配套行研报告)
四模块:①品类结构与价格带 ②选品/汰换 ③毛利与控价情景 ④黑五大促复盘
运行:python src/run_pipeline.py   (自动含数据下载与跨模块对账校验)
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

try:
    from .config import load_config
except ImportError:
    from config import load_config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)
CONFIG_PATH = ROOT / "params/pipeline_config.json"
CONFIG = load_config(CONFIG_PATH)
MAIN_CAT = CONFIG["main_category"]
BENCH_CATS = CONFIG["benchmark_categories"]
WEIGHTS = CONFIG["scoring_weights"]
THRESHOLDS = CONFIG["thresholds"]
PRICE_MOVES = CONFIG["pricing"]["price_moves"]
ELASTICITIES = CONFIG["pricing"]["elasticities"]
PROMO = CONFIG["promotion_windows"]


def setup(con: duckdb.DuckDBPyConnection) -> None:
    """下载数据(如缺)并建底表。"""
    if not (ROOT / "data/raw/olist_products_dataset.csv").exists():
        subprocess.check_call([sys.executable, str(ROOT / "src/fetch_olist.py")], cwd=ROOT)
    categories = [MAIN_CAT, *BENCH_CATS]
    categories_sql = ", ".join("'" + value.replace("'", "''") + "'" for value in categories)
    sql = (ROOT / "sql/01_setup.sql").read_text(encoding="utf-8").format(
        categories_sql=categories_sql
    )
    con.execute(sql)


def load_margins() -> pd.DataFrame:
    m = pd.read_csv(ROOT / "params/cost_assumptions.csv")
    m["price_band"] = ["低价带(<25)", "中价带(25-50)", "中高价带(50-100)", "高价带(100+)"]
    return m[["price_band", "assumed_margin_rate"]]


def m1_price_band(con) -> pd.DataFrame:
    """模块1:品类结构与价格带矩阵 → 过密带/空缺带判断。"""
    df = con.execute(f"""
        SELECT cat, price_band,
               COUNT(DISTINCT product_id) AS skus,
               COUNT(*)                   AS items,
               ROUND(SUM(price), 2)       AS gmv,
               ROUND(AVG(review_score),2) AS avg_review
        FROM fact_items GROUP BY 1, 2
    """).df()
    tot = df.groupby("cat")[["skus", "gmv"]].transform("sum")
    df["sku_share"] = (df["skus"] / tot["skus"]).round(4)
    df["gmv_share"] = (df["gmv"] / tot["gmv"]).round(4)
    df["gap_ratio"] = (df["gmv_share"] / df["sku_share"]).round(2)
    df["band_verdict"] = df["gap_ratio"].map(
        lambda r: "供给不足(机会带)"
        if r > THRESHOLDS["gap_ratio"]
        else ("供给过密" if r < 1 / THRESHOLDS["gap_ratio"] else "均衡")
    )
    df = df.sort_values(["cat", "price_band"])
    df.to_csv(OUT / "m1_price_band_matrix.csv", index=False, encoding="utf-8-sig")
    return df


def m2_scorecard(con) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """模块2:SKU 四维评分卡 → 汰换清单 + 引入候选。"""
    sku = con.execute(f"""
        SELECT product_id, seller_id, price_band,
               COUNT(*)                                        AS items,
               ROUND(SUM(price), 2)                            AS gmv,
               ROUND(AVG(price), 2)                            AS avg_price,
               ROUND(AVG(review_score), 2)                     AS avg_review,
               ROUND(AVG(freight_value / NULLIF(price,0)), 3)  AS freight_ratio,
               DATE_DIFF('month', MIN(ts), MAX(ts)) + 1        AS months_active
        FROM fact_items WHERE cat = '{MAIN_CAT}'
        GROUP BY 1, 2, 3
    """).df()
    sku["velocity"] = (sku["items"] / sku["months_active"]).round(3)  # 月均动销

    def norm(s: pd.Series, inverse=False) -> pd.Series:
        r = (s - s.min()) / (s.max() - s.min() + 1e-9)
        return (1 - r) if inverse else r

    sku["score"] = (
        WEIGHTS["gmv"] * norm(sku["gmv"])
        + WEIGHTS["velocity"] * norm(sku["velocity"])
        + WEIGHTS["review"] * norm(sku["avg_review"].fillna(sku["avg_review"].median()))
        + WEIGHTS["freight"] * norm(
            sku["freight_ratio"].fillna(sku["freight_ratio"].median()), inverse=True
        )
    ).round(4)
    sku = sku.sort_values("score", ascending=False)
    sku.to_csv(OUT / "m2_sku_scorecard.csv", index=False, encoding="utf-8-sig")

    # 汰换:综合分末位 15%,或硬规则(差评+有一定销量,非偶发)
    cutoff = sku["score"].quantile(THRESHOLDS["delist_percentile"])
    delist = sku[
        (sku["score"] <= cutoff)
        | (
            (sku["avg_review"] < THRESHOLDS["hard_review_floor"])
            & (sku["items"] >= THRESHOLDS["hard_review_min_items"])
        )
    ].copy()
    delist["reason"] = delist.apply(
        lambda r: "差评硬规则(均分<3.0且销量≥3)"
        if (
            r["avg_review"] < THRESHOLDS["hard_review_floor"]
            and r["items"] >= THRESHOLDS["hard_review_min_items"]
        )
        else "综合分末位15%", axis=1)
    delist.to_csv(OUT / "m2_delist_list.csv", index=False, encoding="utf-8-sig")

    # 引入候选:模块1判定"供给不足带"里的高分卖家 → 建议扩充其货盘
    m1 = pd.read_csv(OUT / "m1_price_band_matrix.csv")
    gap_bands = m1[(m1["cat"] == MAIN_CAT) & (m1["band_verdict"] == "供给不足(机会带)")]["price_band"].tolist()
    intro = (
        sku[
            sku["price_band"].isin(gap_bands)
            & (sku["avg_review"] >= THRESHOLDS["intro_review_floor"])
        ]
        .groupby("seller_id")
        .agg(skus=("product_id", "count"), gmv=("gmv", "sum"),
             avg_review=("avg_review", "mean"), band=("price_band", "first"))
        .sort_values("gmv", ascending=False)
        .head(THRESHOLDS["intro_seller_limit"])
        .round(2)
        .reset_index()
    )
    intro["action"] = "机会带优质卖家,建议谈判扩充货盘/独家款"
    intro.to_csv(OUT / "m2_intro_candidates.csv", index=False, encoding="utf-8-sig")
    return sku, delist, intro


def m3_pricing(sku: pd.DataFrame, margins: pd.DataFrame) -> pd.DataFrame:
    """模块3:假设成本层 + 3档调价 × 3档弹性情景(GMV/毛利双目标)。"""
    base = sku.merge(margins, on="price_band")
    band = base.groupby("price_band").apply(
        lambda g: pd.Series({
            "gmv": g["gmv"].sum(),
            "gp": (g["gmv"] * g["assumed_margin_rate"]).sum(),  # 毛利 = GMV × 假设毛利率
            "margin_rate": g["assumed_margin_rate"].iloc[0],
        }), include_groups=False).reset_index()

    rows = []
    for _, b in band.iterrows():
        for mv in PRICE_MOVES:
            for e in ELASTICITIES:
                vol_chg = 1 + e * mv                    # 量变 = 1 + 弹性 × 价变(线性近似)
                gmv_new = b["gmv"] * (1 + mv) * vol_chg
                # 单位成本不变:新毛利 = (新价 - 原成本) × 新量
                gp_new = b["gmv"] * ((1 + mv) - (1 - b["margin_rate"])) * vol_chg
                rows.append({
                    "price_band": b["price_band"], "price_move": f"{mv:+.0%}",
                    "elasticity": e,
                    "base_gmv": round(float(b["gmv"]), 2),
                    "base_gp": round(float(b["gp"]), 2),
                    "gmv_chg_pct": round((gmv_new / b["gmv"] - 1) * 100, 1),
                    "gp_chg_pct": round((gp_new / b["gp"] - 1) * 100, 1),
                })
    sc = pd.DataFrame(rows)
    # 带级建议:+5% 在全部弹性假设下毛利仍为正增 → 有提价空间;-5% 仅作引流评估
    verdicts = []
    for pb, g in sc.groupby("price_band"):
        up_ok = (g[(g["price_move"] == "+5%")]["gp_chg_pct"] > 0).all()
        verdicts.append({"price_band": pb,
                         "verdict": "有提价空间(全弹性假设下毛利正增)" if up_ok
                         else "提价敏感,优先运营/结构手段"})
    sc = sc.merge(pd.DataFrame(verdicts), on="price_band")
    sc.to_csv(OUT / "m3_pricing_scenarios.csv", index=False, encoding="utf-8-sig")
    return sc


def m4_promo(con, margins: pd.DataFrame) -> pd.DataFrame:
    """模块4:2017 黑五真实尖峰复盘(增量/让利/ROI)。"""
    win = con.execute(f"""
        SELECT price_band, COUNT(*) items, SUM(price) gmv,
               COUNT(DISTINCT order_id) orders
        FROM fact_items
        WHERE cat = '{MAIN_CAT}' AND ts BETWEEN '{PROMO["event_start"]}' AND '{PROMO["event_end"]} 23:59:59'
        GROUP BY 1
    """).df()
    base = con.execute(f"""
        SELECT price_band, COUNT(*)/{PROMO["baseline_weeks"]} items_wk,
               SUM(price)/{PROMO["baseline_weeks"]} gmv_wk,
               COUNT(DISTINCT order_id)/{PROMO["baseline_weeks"]} orders_wk
        FROM fact_items
        WHERE cat = '{MAIN_CAT}' AND ts BETWEEN '{PROMO["baseline_start"]}' AND '{PROMO["baseline_end"]} 23:59:59'
        GROUP BY 1
    """).df()
    # 让利 proxy:同一 SKU 黑五周均价 vs 基线周均价,降价部分 × 黑五销量
    disc = con.execute(f"""
        WITH bf AS (
            SELECT product_id, AVG(price) p_bf, COUNT(*) q_bf FROM fact_items
            WHERE cat='{MAIN_CAT}' AND ts BETWEEN '{PROMO["event_start"]}' AND '{PROMO["event_end"]} 23:59:59'
            GROUP BY 1),
        bl AS (
            SELECT product_id, AVG(price) p_bl FROM fact_items
            WHERE cat='{MAIN_CAT}' AND ts BETWEEN '{PROMO["baseline_start"]}' AND '{PROMO["baseline_end"]} 23:59:59'
            GROUP BY 1)
        SELECT COALESCE(SUM((bl.p_bl - bf.p_bf) * bf.q_bf), 0) AS discount_cost
        FROM bf JOIN bl USING (product_id) WHERE bf.p_bf < bl.p_bl
    """).df()["discount_cost"][0]

    df = win.merge(base, on="price_band", how="left").merge(margins, on="price_band")
    df["gmv_lift_pct"] = ((df["gmv"] / df["gmv_wk"] - 1) * 100).round(1)
    df["incr_gmv"] = (df["gmv"] - df["gmv_wk"]).round(2)
    df["incr_gp"] = (df["incr_gmv"] * df["assumed_margin_rate"]).round(2)
    total_incr_gp = df["incr_gp"].sum()
    roi = total_incr_gp / disc if disc > 0 else float("inf")
    df["promo_roi_total"] = round(roi, 2)
    df.to_csv(OUT / "m4_promo_review.csv", index=False, encoding="utf-8-sig")
    print(f"  黑五复盘:让利成本 R${disc:,.0f} | 增量假设毛利 R${total_incr_gp:,.0f} | ROI {roi:.2f}")
    return df


def reconcile_frames(
    truth: float,
    promo_truth: float,
    m1: pd.DataFrame,
    sku: pd.DataFrame,
    pricing: pd.DataFrame,
    promo: pd.DataFrame,
    main_category: str,
    tolerance: float,
) -> dict:
    """Reconcile like-for-like measures and return a structured audit record."""
    g1 = round(m1[m1["cat"] == main_category]["gmv"].sum(), 2)
    g2 = round(sku["gmv"].sum(), 2)
    g3 = round(pricing.drop_duplicates("price_band")["base_gmv"].sum(), 2)
    g4 = round(promo["gmv"].sum(), 2)
    full_passed = bool(
        all(abs(float(value) - float(truth)) <= tolerance for value in (g1, g2, g3))
    )
    promo_passed = bool(abs(float(g4) - float(promo_truth)) <= tolerance)
    audit = {
        "full_period": {
            "base_table_gmv": round(float(truth), 2),
            "m1_price_band_gmv": g1,
            "m2_scorecard_gmv": g2,
            "m3_pricing_baseline_gmv": g3,
            "tolerance": tolerance,
            "passed": full_passed,
        },
        "promotion_window": {
            "base_table_gmv": round(float(promo_truth), 2),
            "m4_promotion_gmv": g4,
            "tolerance": tolerance,
            "passed": promo_passed,
        },
    }
    if not full_passed or not promo_passed:
        raise AssertionError(f"[对账失败] {json.dumps(audit, ensure_ascii=False)}")
    return audit


def reconcile(con, m1, sku, pricing, promo) -> dict:
    truth = con.execute(
        f"SELECT COALESCE(ROUND(SUM(price),2),0) FROM fact_items WHERE cat='{MAIN_CAT}'"
    ).fetchone()[0]
    promo_truth = con.execute(
        f"""SELECT COALESCE(ROUND(SUM(price),2),0) FROM fact_items
            WHERE cat='{MAIN_CAT}' AND ts BETWEEN
            '{PROMO["event_start"]}' AND '{PROMO["event_end"]} 23:59:59'"""
    ).fetchone()[0]
    audit = reconcile_frames(
        truth,
        promo_truth,
        m1,
        sku,
        pricing,
        promo,
        MAIN_CAT,
        CONFIG["reconciliation_tolerance"],
    )
    print(f"  [对账通过] 三大经营模块主品类 GMV 一致 = R${truth:,.2f}")
    print(f"  [窗口校验通过] 大促窗口 GMV = R${promo_truth:,.2f}")
    return audit


def _fingerprint(path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "bytes": path.stat().st_size,
    }


def write_manifest(con, audit: dict, frames: dict[str, pd.DataFrame]) -> None:
    inputs = sorted((ROOT / "data/raw").glob("*.csv"))
    manifest = {
        "manifest_version": "category-run-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy_version": CONFIG["policy_version"],
        "main_category": MAIN_CAT,
        "benchmark_categories": BENCH_CATS,
        "source_scope": {
            "olist_orders": int(
                con.execute("SELECT COUNT(DISTINCT order_id) FROM v_raw_items").fetchone()[0]
            ),
            "fact_item_rows": int(con.execute("SELECT COUNT(*) FROM fact_items").fetchone()[0]),
            "note": "Olist 全量数据集下载后，仅分析配置中的主品类与对照品类。",
        },
        "configuration": _fingerprint(CONFIG_PATH),
        "inputs": [_fingerprint(path) for path in inputs],
        "outputs": {name: len(frame) for name, frame in frames.items()},
        "reconciliation": audit,
    }
    (OUT / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    con = duckdb.connect()
    print("== 0. 数据与底表 ==");        setup(con)
    margins = load_margins()
    print("== 1. 品类结构与价格带 ==");  m1 = m1_price_band(con)
    print("== 2. 选品/汰换评分卡 ==");   sku, delist, intro = m2_scorecard(con)
    print(f"  评分卡 {len(sku)} SKU | 汰换 {len(delist)} | 引入候选卖家 {len(intro)}")
    print("== 3. 毛利与控价情景 ==");    pricing = m3_pricing(sku, margins)
    print("== 4. 黑五大促复盘 ==");      promo = m4_promo(con, margins)
    print("== 5. 跨模块对账 ==");        audit = reconcile(con, m1, sku, pricing, promo)
    write_manifest(
        con,
        audit,
        {"m1": m1, "m2_scorecard": sku, "m2_delist": delist,
         "m2_intro": intro, "m3": pricing, "m4": promo},
    )
    print("== 6. 生成看板 ==")
    subprocess.check_call([sys.executable, str(ROOT / "src/build_dashboard.py")], cwd=ROOT)
    print(f"[完成] 决策产物见 {OUT},看板见 docs/index.html")


if __name__ == "__main__":
    main()
