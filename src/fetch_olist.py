"""
fetch_olist.py — 从 GitHub 公开镜像下载 Olist 巴西电商数据集所需 8 张表到 data/raw/。
数据来源:Kaggle「Brazilian E-Commerce Public Dataset by Olist」,此处用 GitHub 镜像便于脚本化拉取。
运行:python src/fetch_olist.py
"""
from __future__ import annotations
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

BASE = ("https://raw.githubusercontent.com/spdrio/"
        "Brazilian-E-Commerce-Public-Dataset-by-Olist/master/files")
FILES = [
    "olist_orders_dataset.csv",                 # 订单状态 + 时间戳(大促窗口)
    "olist_order_items_dataset.csv",            # 价格 / 运费 / SKU 明细(经营核心表)
    "olist_order_payments_dataset.csv",         # 支付
    "olist_products_dataset.csv",               # 品类字段(本项目关键增量表)
    "product_category_name_translation.csv",    # 品类名葡→英
    "olist_order_reviews_dataset.csv",          # 评分(质量/售后代理)
    "olist_sellers_dataset.csv",                # 卖家(引入候选的供给侧维度)
    "olist_customers_dataset.csv",              # 客户(复购/地域)
]


def main():
    for f in FILES:
        dst = RAW / f
        if dst.exists():
            print(f"  已存在,跳过 {f}")
            continue
        print(f"  下载 {f} …")
        urllib.request.urlretrieve(f"{BASE}/{f}", dst)
    print(f"[完成] Olist 数据已就绪于 {RAW}")


if __name__ == "__main__":
    main()
