# category-management-sim — 家居日用品类·采销经营模拟盘

> **一句话**:扮演家居日用品类采销,在真实电商交易数据上跑通「品类结构 → 选品汰换 → 毛利控价 → 大促复盘」完整经营决策闭环——每个模块产出**可执行的决策清单**,而非图表。

🧪 **交互演示**:[docs/demo.html](docs/demo.html)(可输入模拟数据)｜📊 **核验看板**:[docs/index.html](docs/index.html)｜📄 **一页策略**:[docs/strategy_onepager.md](docs/strategy_onepager.md)｜🔗 **姊妹项目**:[logistics-settlement-recon](https://github.com/Martin-cell-blip/logistics-settlement-recon)(同一数据平台·结算侧)

## ⚠️ 诚实声明(先读)

1. **数据**:Olist 巴西电商公开数据集(10 万订单,真实交易)。本项目演示**采销决策方法论**,不代表中国市场;中国市场判断由配套《家居日用品类行业研究报告》承担(独立作品)。
2. **成本**:Olist 无成本字段。毛利为**按价格带分层的假设参数层**([params/cost_assumptions.csv](params/cost_assumptions.csv)),取值逐条引用行研结论(制造毛利 20-25%/渠道品牌 45% 等)。
3. **弹性**:价格弹性为敏感性假设区间(-0.8~-1.6),不是估计值。
4. **可信性**:全部数字由管线生成。模块①价格带、②SKU评分、③定价基线按同一全量口径校验主品类 GMV；模块④按大促窗口独立回查底表。校验失败即中止，并生成含输入哈希、配置版本、行数和校验结果的 `output/run_manifest.json`。
5. **研究证据**:完整 HTML 展示稿保留 100+ 条参考资料；`research/` 另存核心主张、关键来源、7 条假设、6 组口径矛盾与 14 项数据缺口，可运行 `python src/audit_research.py` 生成审计摘要和 manifest。

## 快速开始

```bash
pip install -r requirements.txt
python src/run_pipeline.py     # 自动下载数据 → SQL 底表 → 四模块 → 对账 → 看板
python src/audit_research.py   # 校验结构化行业研究证据台账
pytest -q                     # 配置与对账回归测试
```

## 四模块与决策产物

| 模块 | 决策产物(output/) | 关键结论(本次运行) |
|---|---|---|
| ① 品类结构与价格带 | `m1_price_band_matrix.csv` | 高价带以 25.8% SKU 吃下 62.6% GMV(份额比 2.42,供给不足);低价带 SKU 过密(份额比 0.18) |
| ② 选品/汰换评分卡 | `m2_sku_scorecard.csv` / `m2_delist_list.csv` / `m2_intro_candidates.csv` | 汰换 374 SKU(货盘 15.6%,GMV 影响仅 9.6%);机会带锁定 15 家高分卖家扩盘 |
| ③ 毛利与控价情景 | `m3_pricing_scenarios.csv` | ±5% 调价 × 3 档弹性;提价仅用于供给不足带,低价带保价引流(份额战略优先) |
| ④ 黑五大促复盘 | `m4_promo_review.csv` | 黑五周 GMV +198%,让利成本极小——增量由流量驱动,大促杠杆在曝光而非深折扣 |

## 技术栈与结构

SQL(DuckDB)+ Python(pandas);单文件静态看板(零外部依赖)。

```
sql/01_setup.sql          # 底表(已送达口径,主品类 housewares + 两个对照品类)
src/fetch_olist.py        # 数据下载(8 张表)
src/run_pipeline.py       # 一键管线:三模块同口径对账 + 大促窗口独立校验
src/audit_research.py     # 行研主张/来源/假设/矛盾/缺口完整性校验
src/build_dashboard.py    # 看板生成
params/                   # 版本化配置 + 成本假设 + 决策规则
research/                 # 结构化证据台账
output/                   # 决策产物 CSV
docs/                     # 看板 / 一页策略 / 设计文档(specs/)
```

## 与姊妹项目的关系

同一数据平台的两侧:[logistics-settlement-recon](https://github.com/Martin-cell-blip/logistics-settlement-recon) 管**结算侧**(三方对账/应收账龄/坏账),本项目管**经营侧**(品类/选品/定价/大促)——共同点是同一套工程纪律:一键复现、数字对账、规则可辩护。
