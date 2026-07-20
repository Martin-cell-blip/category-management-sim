-- 01_setup.sql — 品类经营底表
-- 口径纪律:仅取已送达(delivered)订单;品类清单由 params/pipeline_config.json 注入

CREATE OR REPLACE VIEW v_raw_items AS
SELECT
    oi.order_id,
    oi.order_item_id,
    oi.product_id,
    oi.seller_id,
    oi.price,
    oi.freight_value,
    o.order_purchase_timestamp AS ts,
    t.product_category_name_english AS cat
FROM read_csv_auto('data/raw/olist_order_items_dataset.csv') oi
JOIN read_csv_auto('data/raw/olist_orders_dataset.csv') o USING (order_id)
JOIN read_csv_auto('data/raw/olist_products_dataset.csv') p USING (product_id)
JOIN read_csv_auto('data/raw/product_category_name_translation.csv') t USING (product_category_name)
WHERE o.order_status = 'delivered'
  AND t.product_category_name_english IN ({categories_sql});

-- 评分表:一订单可多条评价,取订单平均
CREATE OR REPLACE VIEW v_reviews AS
SELECT order_id, AVG(review_score) AS review_score
FROM read_csv_auto('data/raw/olist_order_reviews_dataset.csv')
GROUP BY order_id;

-- 明细事实表(带评分与价格带)
CREATE OR REPLACE TABLE fact_items AS
SELECT
    i.*,
    r.review_score,
    CASE
        WHEN i.price < 25  THEN '低价带(<25)'
        WHEN i.price < 50  THEN '中价带(25-50)'
        WHEN i.price < 100 THEN '中高价带(50-100)'
        ELSE '高价带(100+)'
    END AS price_band
FROM v_raw_items i
LEFT JOIN v_reviews r USING (order_id);
