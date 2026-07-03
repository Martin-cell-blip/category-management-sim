"""
run_pipeline.py — 京东采销·家居日用品类经营模拟盘 一键管线
数据:Olist 巴西电商公开数据(方法论演示;中国市场判断见配套行研报告)
四模块:①品类结构与价格带 ②选品/汰换 ③毛利与控价情景 ④黑五大促复盘
运行:python src/run_pipeline.py   (自动含数据下载与跨模块对账校验)
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

MAIN_CAT = "housewares"                       # 主品类(对齐行研"家居日用"边界)
BENCH_CATS = ["bed_bath_table", "furniture_decor"]  # 对照品类

# 模块2 评分卡权重(依据见 params/decision_rules.md R2)
W_GMV, W_VELOCITY, W_REVIEW, W_FREIGHT = 0.35, 0.25, 0.25, 0.15
DELIST_PCT = 0.15          # 综合分末位 15% 进入汰换候补
HARD_REVIEW_FLOOR = 3.0    # 硬规则:均分 < 3.0 且销量>=3 直接汰换
GAP_RATIO = 1.25           # 模块1:GMV份额/SKU份额 > 1.25 判定为"供给不足带"

# 模块3 情景参数(弹性为敏感性假设,非估计值;见 decision_rules.md R3)
PRICE_MOVES = [-0.05, 0.0, 0.05]
ELASTICITIES = [-0.8, -1.2, -1.6]

# 模块4 黑五窗口(Olist 真实大促尖峰:2017-11-24)
BF_START, BF_END = "2017-11-20", "2017-11-26"
BASE_START, BASE_END = "2017-10-23", "2017-11-19"   # 前 4 周基线


def setup(con: duckdb.DuckDBPyConnection) -> None:
    """下载数据(如缺)并建底表。"""
    if not (ROOT / "data/raw/olist_products_dataset.csv").exists():
        subprocess.check_call([sys.executable, str(ROOT / "src/fetch_olist.py")], cwd=ROOT)
    con.execute((ROOT / "sql/01_setup.sql").read_text(encoding="utf-8"))


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
        lambda r: "供给不足(机会带)" if r > GAP_RATIO else ("供给过密" if r < 1 / GAP_RATIO else "均衡")
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
        W_GMV * norm(sku["gmv"])
        + W_VELOCITY * norm(sku["velocity"])
        + W_REVIEW * norm(sku["avg_review"].fillna(sku["avg_review"].median()))
        + W_FREIGHT * norm(sku["freight_ratio"].fillna(sku["freight_ratio"].median()), inverse=True)
    ).round(4)
    sku = sku.sort_values("score", ascending=False)
    sku.to_csv(OUT / "m2_sku_scorecard.csv", index=False, encoding="utf-8-sig")

    # 汰换:综合分末位 15%,或硬规则(差评+有一定销量,非偶发)
    cutoff = sku["score"].quantile(DELIST_PCT)
    delist = sku[
        (sku["score"] <= cutoff)
        | ((sku["avg_review"] < HARD_REVIEW_FLOOR) & (sku["items"] >= 3))
    ].copy()
    delist["reason"] = delist.apply(
        lambda r: "差评硬规则(均分<3.0且销量≥3)"
        if (r["avg_review"] < HARD_REVIEW_FLOOR and r["items"] >= 3)
        else "综合分末位15%", axis=1)
    delist.to_csv(OUT / "m2_delist_list.csv", index=False, encoding="utf-8-sig")

    # 引入候选:模块1判定"供给不足带"里的高分卖家 → 建议扩充其货盘
    m1 = pd.read_csv(OUT / "m1_price_band_matrix.csv")
    gap_bands = m1[(m1["cat"] == MAIN_CAT) & (m1["band_verdict"] == "供给不足(机会带)")]["price_band"].tolist()
    intro = (
        sku[sku["price_band"].isin(gap_bands) & (sku["avg_review"] >= 4.5)]
        .groupby("seller_id")
        .agg(skus=("product_id", "count"), gmv=("gmv", "sum"),
             avg_review=("avg_review", "mean"), band=("price_band", "first"))
        .sort_values("gmv", ascending=False).head(15).round(2).reset_index()
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
        WHERE cat = '{MAIN_CAT}' AND ts BETWEEN '{BF_START}' AND '{BF_END} 23:59:59'
        GROUP BY 1
    """).df()
    base = con.execute(f"""
        SELECT price_band, COUNT(*)/4.0 items_wk, SUM(price)/4.0 gmv_wk,
               COUNT(DISTINCT order_id)/4.0 orders_wk
        FROM fact_items
        WHERE cat = '{MAIN_CAT}' AND ts BETWEEN '{BASE_START}' AND '{BASE_END} 23:59:59'
        GROUP BY 1
    """).df()
    # 让利 proxy:同一 SKU 黑五周均价 vs 基线周均价,降价部分 × 黑五销量
    disc = con.execute(f"""
        WITH bf AS (
            SELECT product_id, AVG(price) p_bf, COUNT(*) q_bf FROM fact_items
            WHERE cat='{MAIN_CAT}' AND ts BETWEEN '{BF_START}' AND '{BF_END} 23:59:59'
            GROUP BY 1),
        bl AS (
            SELECT product_id, AVG(price) p_bl FROM fact_items
            WHERE cat='{MAIN_CAT}' AND ts BETWEEN '{BASE_START}' AND '{BASE_END} 23:59:59'
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


def reconcile(con, m1: pd.DataFrame, sku: pd.DataFrame) -> None:
    """跨模块 GMV 对账:m1 主品类合计 == m2 评分卡合计 == 底表直查,容差 0.01。"""
    truth = con.execute(f"SELECT ROUND(SUM(price),2) FROM fact_items WHERE cat='{MAIN_CAT}'").fetchone()[0]
    g1 = round(m1[m1["cat"] == MAIN_CAT]["gmv"].sum(), 2)
    g2 = round(sku["gmv"].sum(), 2)
    assert abs(g1 - truth) < 0.01 and abs(g2 - truth) < 0.01, \
        f"[对账失败] 底表={truth} m1={g1} m2={g2}"
    print(f"  [对账通过] 主品类 GMV 三处一致 = R${truth:,.2f}")


def main() -> None:
    con = duckdb.connect()
    print("== 0. 数据与底表 ==");        setup(con)
    margins = load_margins()
    print("== 1. 品类结构与价格带 ==");  m1 = m1_price_band(con)
    print("== 2. 选品/汰换评分卡 ==");   sku, delist, intro = m2_scorecard(con)
    print(f"  评分卡 {len(sku)} SKU | 汰换 {len(delist)} | 引入候选卖家 {len(intro)}")
    print("== 3. 毛利与控价情景 ==");    m3_pricing(sku, margins)
    print("== 4. 黑五大促复盘 ==");      m4_promo(con, margins)
    print("== 5. 跨模块对账 ==");        reconcile(con, m1, sku)
    print("== 6. 生成看板 ==")
    subprocess.check_call([sys.executable, str(ROOT / "src/build_dashboard.py")], cwd=ROOT)
    print(f"[完成] 决策产物见 {OUT},看板见 docs/index.html")


if __name__ == "__main__":
    main()
