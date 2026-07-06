# 设计文档:家居日用品类·采销经营模拟盘(category-management-sim)

> 日期:2026-04-03 | 状态:已获批准的设计,待实施
> 作者:马准名(与 Claude Code 协作)
> 用途:采销/品类经营决策方法论的可复现演示项目

## 0. 一句话定位

扮演家居日用品类采销,在 Olist 真实电商交易数据上跑通"品类结构 → 选品汰换 → 毛利控价 → 大促复盘"完整经营决策闭环,每个模块产出**可执行的决策产物**(而非图表),以 HTML 看板 + 一页《采销经营策略》交付。

## 1. 叙事策略(双层,诚实声明)

- **中国市场判断层**:由《家居日用品类行业研究报告》承担(独立作品),提供价格带 5-30 元、白牌格局、利润倒挂、"份额行业"等中国语境结论。
- **方法论演示层**:本项目用 Olist(巴西电商,10 万+ 真实订单)演示采销决策方法,README 顶部诚实声明:①数据为巴西市场,不代表中国;②成本为假设参数层,取值引用行研结论并标注。
- 与 `logistics-settlement-recon` README 互相交叉引用:同一数据平台的"结算侧"与"经营侧"两个项目。

**保真红线**:任何数字产物必须可复现(固定种子);任何决策规则必须有成文依据;假设与事实分层标注。

## 2. 数据层

| 项 | 决策 |
|---|---|
| 数据源 | Olist Brazilian E-Commerce(Kaggle 公开),复用现有 fetch 模式 |
| 需补拉的表 | `olist_products_dataset.csv`(品类字段)、`product_category_name_translation.csv`(葡→英)、`olist_order_reviews_dataset.csv`(评分,作质量/售后代理) |
| 已有可复用表 | orders / order_items / payments / sellers / customers——本 repo 独立 fetch 全量九表(不跨 repo 复制文件,保证独立一键复现;fetch 脚本逻辑可参考 recon 项目) |
| 主品类 | `housewares`(对齐行研"家居日用"边界) |
| 对照品类 | `bed_bath_table`、`furniture_decor`(用于结构对比与基准) |
| 假设成本层 | `cost = price × (1 − 假设毛利率)`;毛利率按 SKU 价格带分层抽样:低价带白牌逻辑毛利偏低、高价带品牌逻辑偏高,区间参数引用行研 §3.2(制造毛利 20-25%、渠道品牌 45%);固定 seed;参数独立成 `params/cost_assumptions.csv` |

## 3. 四模块与决策产物

每模块 = 一个 SQL 底表(DuckDB) + 一段 Python 决策逻辑 + 一份决策产物(CSV/MD):

| # | 模块 | 输入 | 决策规则(示例,实施时成文于规则表) | 决策产物 |
|---|---|---|---|---|
| 1 | 品类结构与价格带 | order_items × products(主+对照品类) | 价格带分桶(对数分桶或分位数);带内 SKU 密度 vs GMV 占比错配判断 | `m1_price_band_matrix.csv` + "过密带/空缺带"结论 |
| 2 | 选品/汰换 | 模块1 + reviews + freight | SKU 评分卡:GMV 贡献/动销(月均单量)/评分/运费占比 四维加权;末位 N% 且低评分 → 汰换;空缺带+高评分卖家 → 引入候选 | `m2_sku_scorecard.csv` + `m2_delist_list.csv` + `m2_intro_candidates.csv` |
| 3 | 毛利与控价 | 模块2 + 假设成本层 | 3 档调价情景(−5%/0/+5%)× 价格弹性假设(弹性系数作敏感性参数而非"真值");毛利瀑布分解 | `m3_pricing_scenarios.csv` + 毛利瀑布数据 |
| 4 | 大促 ROI 复盘 | orders 时间序列(2017-11 黑五真实尖峰) | 大促窗口(黑五周)vs 基线(前 4 周均值):增量订单/GMV、价格让利 proxy(窗口内价差)、ROI = 增量假设毛利 ÷ 让利成本 | `m4_promo_review.csv` + 复盘结论段 |

**跨模块对账约束**:模块 1-4 各自汇总的主品类 GMV 总量必须一致(容差 0),校验脚本失败即管线报错——延续"对账"个人风格。

## 4. 交付物

1. **repo**:`D:\category-management-sim`,结构沿用 recon 项目惯例(`data/raw`、`data/generated`、`sql/`、`src/`、`output/`、`docs/`、`params/`)
2. **一键管线**:`src/run_pipeline.py`:fetch → DuckDB(01_setup / 02_category / 03_scorecard / 04_pricing / 05_promo)→ 决策产物 → 看板生成
3. **看板**:`docs/index.html` 单文件静态(Python 生成,内联数据,零外部 CDN),KPI 卡 + 四模块各一区块;挂 GitHub Pages
4. **一页策略**:`docs/strategy_onepager.md`(可转 PDF):以行研中国判断为框架,用模拟盘数字演示决策链
5. **README**:双层叙事声明 + 快速开始 + 四产物预览 + 与 recon 项目交叉链接

## 5. 质量与验证

- 跨模块 GMV 对账(§3);固定 seed 复现;`pytest` 式轻量断言脚本(行数/非空/对账)跑在管线末尾
- 决策规则表(`params/decision_rules.md`):每条规则一行依据(数据事实或行研引用)
- 看板自查:单文件、无外链、移动端不横向溢出

## 6. 工期计划

| 天 | 内容 |
|---|---|
| Day 1 | 数据补拉 + SQL 底表 + 模块 1/2 |
| Day 2 | 模块 3/4 + 看板 |
| Day 3 | 一页策略 + README + Pages 发布 + 简历 bullet 更新 |

## 7. 明确不做(YAGNI)

- ❌ 交互 what-if 滑杆(预计算情景表替代)
- ❌ 爬取中国电商数据
- ❌ 机器学习需求预测(超出采销日常决策叙事,增加可辩护成本)
- ❌ Power BI 版本(后续可选,不入本期)
