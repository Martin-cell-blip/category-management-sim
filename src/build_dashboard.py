"""
build_dashboard.py — 读取 output/*.csv,生成 docs/index.html 单文件静态看板(零外部依赖,纯 HTML/CSS)。
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT, DOCS = ROOT / "output", ROOT / "docs"
DOCS.mkdir(exist_ok=True)

m1 = pd.read_csv(OUT / "m1_price_band_matrix.csv")
sku = pd.read_csv(OUT / "m2_sku_scorecard.csv")
delist = pd.read_csv(OUT / "m2_delist_list.csv")
intro = pd.read_csv(OUT / "m2_intro_candidates.csv")
m3 = pd.read_csv(OUT / "m3_pricing_scenarios.csv")
m4 = pd.read_csv(OUT / "m4_promo_review.csv")

MAIN = m1[m1["cat"] == "housewares"]
gmv_total = MAIN["gmv"].sum()
roi = m4["promo_roi_total"].iloc[0]
bf_lift = (m4["gmv"].sum() / m4["gmv_wk"].sum() - 1) * 100


def bar(v: float, vmax: float, color: str = "#c8102e") -> str:
    w = max(2, round(v / vmax * 100))
    return f'<div class="bar"><i style="width:{w}%;background:{color}"></i></div>'


def table(df: pd.DataFrame, cols: dict[str, str], barcol: str | None = None) -> str:
    vmax = df[barcol].max() if barcol else 1
    head = "".join(f"<th>{h}</th>" for h in cols.values())
    rows = ""
    for _, r in df.iterrows():
        tds = ""
        for c in cols:
            v = r[c]
            if c == barcol:
                tds += f'<td class="num">{v:,.0f}{bar(v, vmax)}</td>'
            elif isinstance(v, float):
                tds += f'<td class="num">{v:,.2f}</td>'
            else:
                tds += f"<td>{v}</td>"
        rows += f"<tr>{tds}</tr>"
    return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


kpi = f"""
<div class="kpis">
 <div class="kpi"><b>R$ {gmv_total:,.0f}</b><span>主品类 GMV(housewares,已送达口径)</span></div>
 <div class="kpi"><b>{MAIN['skus'].sum():,}</b><span>在售 SKU</span></div>
 <div class="kpi"><b>{len(delist)}</b><span>汰换清单 SKU(末位15%+差评硬规则)</span></div>
 <div class="kpi"><b>{roi:.2f}</b><span>黑五大促 ROI(增量假设毛利÷让利成本)</span></div>
 <div class="kpi"><b>+{bf_lift:.0f}%</b><span>黑五周 GMV vs 前4周基线</span></div>
</div>"""

sec1 = table(MAIN, {"price_band": "价格带", "skus": "SKU", "items": "销量件",
                    "gmv": "GMV(R$)", "gmv_share": "GMV份额", "gap_ratio": "份额比",
                    "band_verdict": "判定"}, barcol="gmv")
sec2a = table(delist.head(10),
              {"product_id": "SKU(前10)", "price_band": "价格带", "items": "销量",
               "avg_review": "均分", "score": "综合分", "reason": "汰换理由"})
sec2b = table(intro.head(8),
              {"seller_id": "卖家(前8)", "band": "机会带", "skus": "SKU数",
               "gmv": "GMV(R$)", "avg_review": "均分", "action": "建议动作"})
piv = m3.pivot_table(index=["price_band", "verdict"], columns=["price_move", "elasticity"],
                     values="gp_chg_pct").round(1)
sec3 = piv.to_html(classes="pvt", border=0)
sec4 = table(m4, {"price_band": "价格带", "gmv": "黑五周GMV", "gmv_wk": "基线周GMV",
                  "gmv_lift_pct": "GMV提升%", "incr_gp": "增量假设毛利(R$)"})

html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>家居日用品类·采销经营模拟盘</title><style>
:root{{--red:#c8102e;--ink:#1a1a1a;--mut:#666;--line:#e5e5e5;--bg:#fafafa}}
*{{box-sizing:border-box;margin:0}}body{{font:15px/1.7 system-ui,"Microsoft YaHei",sans-serif;color:var(--ink);background:var(--bg);padding:32px 5vw}}
h1{{font-size:26px}}h2{{font-size:19px;margin:36px 0 12px;border-left:4px solid var(--red);padding-left:10px}}
.sub{{color:var(--mut);margin:6px 0 4px}}
.note{{background:#fff7e6;border:1px solid #ffd591;border-radius:8px;padding:10px 14px;margin:14px 0;font-size:13px;color:#7a5b00}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:20px 0}}
.kpi{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
.kpi b{{font-size:22px;color:var(--red);font-variant-numeric:tabular-nums}}
.kpi span{{display:block;font-size:12px;color:var(--mut);margin-top:4px}}
.tw{{overflow-x:auto;background:#fff;border:1px solid var(--line);border-radius:10px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th{{position:sticky;top:0;background:#f3f3f3;text-align:left;padding:8px 10px;white-space:nowrap}}
td{{padding:7px 10px;border-top:1px solid var(--line);white-space:nowrap}}
tr:nth-child(even) td{{background:#fbfbfb}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
.bar{{height:5px;background:#eee;border-radius:3px;margin-top:3px;min-width:90px}}.bar i{{display:block;height:100%;border-radius:3px}}
.pvt{{width:100%;background:#fff;font-size:12px}}.pvt th,.pvt td{{padding:6px 8px;border:1px solid var(--line);text-align:right}}
footer{{margin-top:40px;font-size:12px;color:var(--mut)}}
@media print{{body{{background:#fff;padding:0}}}}
</style></head><body>
<h1>家居日用品类 · 采销经营模拟盘</h1>
<p class="sub">品类结构 → 选品汰换 → 毛利控价 → 大促复盘 | DuckDB + Python 一键复现 | 配套作品:<a href="https://github.com/Martin-cell-blip/logistics-settlement-recon">结算对账引擎</a>(同一数据平台·结算侧)</p>
<div class="note">⚠️ 诚实声明:数据为 Olist 巴西电商真实交易(方法论演示,不代表中国市场;中国市场判断见配套《家居日用品类行业研究报告》);毛利为按价格带假设的参数层(取值依据行研,见 params/cost_assumptions.csv);价格弹性为敏感性假设而非估计值。</div>
{kpi}
<h2>① 品类结构与价格带(主品类 housewares)</h2>
<p class="sub">规则:GMV份额/SKU份额 &gt; 1.25 → 供给不足(机会带);&lt; 0.8 → 供给过密</p>{sec1}
<h2>② 选品/汰换:四维评分卡(GMV 35% · 动销 25% · 评分 25% · 运费占比 15%)</h2>{sec2a}
<p class="sub" style="margin-top:14px">机会带引入候选(评分≥4.5 的高分卖家)</p>{sec2b}
<h2>③ 毛利与控价:3档调价 × 3档弹性,毛利变动 %</h2>
<p class="sub">列 = (调价幅度, 弹性假设);行尾为带级判定</p><div class="tw">{sec3}</div>
<h2>④ 黑五大促复盘(2017-11-20 ~ 26 vs 前4周基线)</h2>{sec4}
<footer>category-management-sim · 求职作品(京东 TET 综合方向/采销) · 全部数字由 run_pipeline.py 生成并经跨模块 GMV 对账校验</footer>
</body></html>"""

(DOCS / "index.html").write_text(html, encoding="utf-8")
print(f"  看板已生成:{DOCS / 'index.html'}")
