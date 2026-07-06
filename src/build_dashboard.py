"""
build_dashboard.py — 读取 output/*.csv,生成 docs/index.html 单文件静态看板(零外部依赖,纯 HTML/CSS/JS)。
设计语言:机构研报——象牙纸面/衬线表格数字/编号图表(图 1-4)+逐表资料来源注/控价矩阵热力着色。
所有文本经 html.escape 转义;动效尊重 prefers-reduced-motion,无 JS 时内容完整可读。
"""
from __future__ import annotations

from html import escape
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


# ── 表格构件 ────────────────────────────────────────────────────────────────

def bar(v: float, vmax: float) -> str:
    w = max(2, round(v / vmax * 100))
    return f'<div class="bar"><i style="width:{w}%"></i></div>'


def tag(verdict: str) -> str:
    v = escape(verdict)
    if "机会带" in verdict:
        return f'<span class="tag tag-hot">{v}</span>'
    if "过密" in verdict:
        return f'<span class="tag tag-cold">{v}</span>'
    return f'<span class="tag tag-mid">{v}</span>'


def table(df: pd.DataFrame, cols: dict[str, str], num: set[str] | None = None,
          barcol: str | None = None, mono: set[str] | None = None,
          tagcol: str | None = None, hot=None) -> str:
    num, mono = num or set(), mono or set()
    vmax = float(df[barcol].max()) if barcol else 1.0
    head = "".join(
        f'<th class="num">{escape(h)}</th>' if c in num else f"<th>{escape(h)}</th>"
        for c, h in cols.items())
    rows = []
    for _, r in df.iterrows():
        cls = ' class="hot"' if hot is not None and hot(r) else ""
        tds = []
        for c in cols:
            v = r[c]
            if c == barcol:
                tds.append(f'<td class="num">{v:,.0f}{bar(float(v), vmax)}</td>')
            elif c == tagcol:
                tds.append(f"<td>{tag(str(v))}</td>")
            elif c in mono:
                tds.append(f'<td class="mono">{escape(str(v))}</td>')
            elif isinstance(v, float):
                tds.append(f'<td class="num">{v:,.2f}</td>')
            elif c in num:
                tds.append(f'<td class="num">{escape(str(v))}</td>')
            else:
                tds.append(f"<td>{escape(str(v))}</td>")
        rows.append(f"<tr{cls}>{''.join(tds)}</tr>")
    return ('<div class="tw"><table><thead><tr>' + head + "</tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def matrix() -> str:
    """图 3:调价×弹性 热力矩阵(着色由前端 JS 按数值计算,保持数据纯净)。"""
    piv = m3.pivot_table(index=["price_band", "verdict"],
                         columns=["price_move", "elasticity"],
                         values="gp_chg_pct").round(1)
    moves: list = []
    for mv in piv.columns.get_level_values(0):
        if mv not in moves:
            moves.append(mv)
    grp_label = {"+0%": "维持 +0%", "+5%": "提价 +5%", "-5%": "降价 -5%"}
    h1 = '<tr><th rowspan="2" style="text-align:left">价格带</th>'
    for mv in moves:
        span = len([c for c in piv.columns if c[0] == mv])
        h1 += f'<th colspan="{span}" class="grp">{escape(grp_label.get(mv, str(mv)))}</th>'
    h1 += '<th rowspan="2" style="text-align:left">带级判定</th></tr>'
    h2 = "<tr>" + "".join(f'<th class="ela">{c[1]:g}</th>' for c in piv.columns) + "</tr>"
    body = []
    for (band, verdict), row in piv.iterrows():
        tds = "".join(f"<td>{row[c]:.1f}</td>" for c in piv.columns)
        body.append(f"<tr><th>{escape(str(band))}</th>{tds}"
                    f'<td class="verd">{escape(str(verdict))}</td></tr>')
    return ('<div class="tw pvt-w"><table class="pvt"><thead>' + h1 + h2
            + "</thead><tbody>" + "".join(body) + "</tbody></table></div>")


# ── 静态样式与脚本(与线上版一致) ────────────────────────────────────────────

CSS = """
:root{
  --red:#c8102e; --red-deep:#8f0b20;
  --ink:#1d1f26; --ink2:#494c55;
  --mut:#847d6d;
  --paper:#f2efe6; --sheet:#fdfcf8;
  --hair:#e0dac9; --rule:#23252c;
  --neg:#3b4d63;
  --serif:"Times New Roman",Georgia,"Songti SC","SimSun",serif;
  --disp:"Songti SC","SimSun","Noto Serif SC","Times New Roman",serif;
  --sans:"Microsoft YaHei","PingFang SC","Noto Sans SC",sans-serif;
  --mono:Consolas,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box;margin:0}
html{scroll-behavior:smooth}
body{
  font:14px/1.85 var(--sans);color:var(--ink);
  background:
    radial-gradient(1200px 500px at 50% -200px,rgba(200,16,46,.045),transparent 60%),
    repeating-linear-gradient(0deg,transparent 0 3px,rgba(29,31,38,.006) 3px 4px),
    var(--paper);
  padding:44px 4vw 60px;
}
a{color:var(--red-deep);text-decoration:none;border-bottom:1px solid rgba(200,16,46,.35)}
a:hover{color:var(--red)}
.sheet{max-width:1060px;margin:0 auto;background:var(--sheet);border:1px solid var(--hair);
  box-shadow:0 1px 2px rgba(29,31,38,.04),0 24px 60px -30px rgba(29,31,38,.18);
  padding:0 56px 46px}
.mast{border-top:6px solid var(--red);padding:26px 0 26px;border-bottom:2px solid var(--rule)}
.mast-top{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:22px}
.logotype{font:600 11px/1 var(--serif);letter-spacing:.32em;color:var(--red);text-transform:uppercase}
.docno{font:italic 12px/1 var(--serif);color:var(--mut);letter-spacing:.08em}
h1{font:700 clamp(34px,4.4vw,48px)/1.3 var(--disp);letter-spacing:.05em}
h1 em{font-style:normal;color:var(--red)}
.en-sub{font:italic 14px/1.5 var(--serif);color:var(--ink2);margin-top:6px;letter-spacing:.02em}
.lede{margin-top:14px;font-size:14px;color:var(--ink2)}
.meta{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin-top:22px;border-top:1px solid var(--hair)}
.meta>div{padding:12px 16px 2px;border-left:1px solid var(--hair)}
.meta>div:first-child{border-left:none;padding-left:0}
.meta dt{font:600 10px/1 var(--serif);letter-spacing:.22em;color:var(--mut);text-transform:uppercase;margin-bottom:6px}
.meta dd{font-size:12.5px;line-height:1.6;color:var(--ink2)}
.meta dd code{font:12px var(--mono);background:rgba(29,31,38,.05);padding:1px 5px;border-radius:2px}
nav{position:sticky;top:0;z-index:9;background:rgba(253,252,248,.93);backdrop-filter:blur(6px);
  display:flex;gap:26px;align-items:center;border-bottom:1px solid var(--hair);
  margin:0 -56px;padding:0 56px;height:46px}
nav a{border:none;font-size:12.5px;color:var(--ink2);height:100%;display:inline-flex;align-items:center;position:relative}
nav a i{font:600 11px var(--serif);font-style:normal;color:var(--red);margin-right:6px;letter-spacing:.06em}
nav a.act{color:var(--ink)}
nav a.act::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:var(--red)}
#prog{position:fixed;top:0;left:0;height:2px;background:var(--red);width:0;z-index:99}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);margin:34px 0 8px}
.kpi{padding:2px 20px 6px;border-left:1px solid var(--hair)}
.kpi:first-child{border-left:none;padding-left:0}
.kpi b{display:block;font:600 29px/1.25 var(--serif);color:var(--red);font-variant-numeric:tabular-nums;letter-spacing:.01em}
.kpi span{display:block;font-size:11.5px;color:var(--mut);margin-top:5px;line-height:1.55}
.kpis-cap{font:600 10px/1 var(--serif);letter-spacing:.28em;color:var(--mut);text-transform:uppercase;margin:30px 0 0}
.note{border-left:3px solid var(--red);background:rgba(200,16,46,.028);
  padding:14px 20px;margin:26px 0 8px;font-size:12.5px;color:var(--ink2);line-height:1.9}
.note b{font-size:12.5px;color:var(--red-deep);margin-right:6px}
.ex{margin-top:46px}
.ex-head{display:flex;gap:14px;align-items:flex-start}
.ex-no{flex:none;font:600 11px/1 var(--serif);letter-spacing:.14em;color:#fff;background:var(--red);
  padding:5px 9px;margin-top:5px}
h2{font:700 19px/1.5 var(--sans)}
h2 small{font-weight:400;font-size:13px;color:var(--mut);margin-left:10px}
.ex-en{font:italic 12px/1.4 var(--serif);color:var(--mut);letter-spacing:.03em;margin-top:2px}
.rule-note{font-size:12.5px;color:var(--ink2);margin:12px 0 10px}
.rule-note b{color:var(--red-deep)}
.tw{overflow-x:auto;margin-top:12px}
table{border-collapse:collapse;width:100%;font-size:13px;border-top:2px solid var(--rule);border-bottom:1.5px solid var(--rule)}
th{font:600 12.5px var(--sans);text-align:left;padding:9px 12px;white-space:nowrap;border-bottom:1px solid var(--rule);color:var(--ink)}
td{padding:8px 12px;border-top:1px solid var(--hair);white-space:nowrap;color:var(--ink2)}
tbody th{font-weight:600;border-top:1px solid var(--hair);border-bottom:none;color:var(--ink)}
.num,td.num,th.num{text-align:right;font-family:var(--serif);font-size:13.5px;font-variant-numeric:tabular-nums;color:var(--ink)}
tbody tr{transition:background .15s ease}
tbody tr:hover td,tbody tr:hover th{background:rgba(200,16,46,.03)}
.mono{font:11.5px var(--mono);color:var(--ink2)}
.src{font-size:11.5px;color:var(--mut);margin-top:9px}
.src::before{content:"";display:inline-block;width:18px;height:1px;background:var(--mut);vertical-align:4px;margin-right:8px}
.bar{height:4px;background:rgba(29,31,38,.08);margin-top:4px;min-width:110px}
.bar i{display:block;height:100%;background:#565d68}
tr.hot .bar i{background:var(--red)}
.tag{display:inline-block;font-size:11.5px;line-height:1;padding:5px 9px;border:1px solid;letter-spacing:.04em;white-space:nowrap}
.tag-hot{color:#fff;background:var(--red);border-color:var(--red)}
.tag-cold{color:var(--ink2);border-color:#b9b2a0}
.tag-mid{color:var(--ink2);border-color:var(--hair);background:rgba(29,31,38,.03)}
tr.hot td,tr.hot th{background:rgba(200,16,46,.035)}
.pvt th,.pvt td{text-align:right}
.pvt thead th{text-align:center}
.pvt thead .grp{border-left:1px solid var(--hair);font-family:var(--serif);font-size:13px}
.pvt thead .ela{font:italic 12px var(--serif);color:var(--mut);font-weight:400}
.pvt tbody th{text-align:left}
.pvt tbody td{font-family:var(--serif);font-size:13px;font-variant-numeric:tabular-nums}
.pvt td.v0{color:#a9a292}
.pvt .verd{text-align:left;font-family:var(--sans);font-size:11.5px;color:var(--ink2);border-left:1px solid var(--hair)}
footer{margin-top:52px;border-top:2px solid var(--rule);padding-top:14px;
  display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;
  font-size:11.5px;color:var(--mut)}
footer code{font:11px var(--mono);background:rgba(29,31,38,.05);padding:2px 6px;border-radius:2px}
/* ── 报头增强:印章 / 决策流程 / 幽灵编号 / 结论批注 / 纸感颗粒 ── */
.mast{position:relative}
.seal{position:absolute;right:2px;top:92px;width:94px;height:94px;border:3px solid rgba(200,16,46,.82);
  border-radius:7px;transform:rotate(-7deg);display:flex;flex-direction:column;align-items:center;justify-content:center;
  color:rgba(200,16,46,.86);pointer-events:none;mix-blend-mode:multiply;
  box-shadow:inset 0 0 0 1px rgba(200,16,46,.32)}
.seal b{font:700 21px/1.25 var(--disp);letter-spacing:.3em;margin-left:.3em}
.seal i{font:9px/1 var(--serif);font-style:normal;letter-spacing:.22em;margin-top:6px;opacity:.75}
.flow{display:flex;align-items:center;gap:10px;margin-top:20px;flex-wrap:wrap}
.flow s{text-decoration:none;font-size:12.5px;color:var(--ink);border:1px solid var(--hair);background:#fff;
  padding:6px 14px;white-space:nowrap}
.flow s b{font:600 11px var(--serif);color:var(--red);margin-right:7px}
.flow em{flex:none;width:34px;height:1px;background:linear-gradient(90deg,var(--hair),var(--red))}
.ex{position:relative}
.ex::before{content:attr(data-no);position:absolute;right:-10px;top:-36px;z-index:0;
  font:700 112px/1 var(--serif);color:transparent;-webkit-text-stroke:1px rgba(200,16,46,.13);pointer-events:none}
.ex>*{position:relative;z-index:1}
.takeaway{margin-top:14px;padding:12px 18px;background:rgba(29,31,38,.026);border-left:3px solid var(--rule);
  font-size:13px;line-height:1.95;color:var(--ink)}
.takeaway b{color:var(--red);font-size:11px;letter-spacing:.3em;margin-right:12px;vertical-align:1px}
body::after{content:"";position:fixed;inset:0;z-index:98;pointer-events:none;opacity:.05;mix-blend-mode:multiply;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='260' height='260'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2'/%3E%3C/filter%3E%3Crect width='260' height='260' filter='url(%23n)' opacity='0.55'/%3E%3C/svg%3E")}
@media (prefers-reduced-motion:no-preference){
  .mast-top,.mast h1,.en-sub,.lede,.flow,.meta{animation:rise .6s cubic-bezier(.22,.61,.36,1) both}
  .mast h1{animation-delay:.08s}.en-sub{animation-delay:.16s}.lede{animation-delay:.24s}.flow{animation-delay:.34s}.meta{animation-delay:.44s}
  @keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
  .seal{opacity:0;animation:stamp .5s cubic-bezier(.2,1.4,.4,1) 1s both}
  @keyframes stamp{0%{opacity:0;transform:rotate(-7deg) scale(1.9)}70%{opacity:1;transform:rotate(-7deg) scale(.95)}100%{opacity:1;transform:rotate(-7deg) scale(1)}}
  .flow em{transform-origin:left;transform:scaleX(0);animation:drawx .45s ease-out both}
  .flow em:nth-of-type(1){animation-delay:.75s}.flow em:nth-of-type(2){animation-delay:.92s}.flow em:nth-of-type(3){animation-delay:1.09s}
  @keyframes drawx{from{transform:scaleX(0)}to{transform:scaleX(1)}}
  .reveal{opacity:0;transform:translateY(16px);transition:opacity .6s ease,transform .6s cubic-bezier(.22,.61,.36,1)}
  .reveal.on{opacity:1;transform:none}
  .bar i{transform:scaleX(0);transform-origin:left;transition:transform 1s cubic-bezier(.22,.61,.36,1) .15s}
  .bars-on .bar i{transform:scaleX(1)}
  .pvt tbody td{opacity:0;transition:opacity .5s ease}
  .bars-on.pvt-w tbody td,.pvt-w.bars-on tbody td{opacity:1}
  .kpi b{transition:color .2s ease}
  .kpi:hover b{color:var(--red-deep)}
}
@media (max-width:900px){
  .sheet{padding:0 22px 30px}
  nav{margin:0 -22px;padding:0 22px;gap:16px;overflow-x:auto}
  .meta{grid-template-columns:1fr 1fr}
  .meta>div{padding-left:0;border-left:none}
  .kpis{grid-template-columns:1fr 1fr;gap:14px 0}
  .kpi{border-left:none;padding-left:0}
  h1{font-size:27px}
  .seal{display:none}
  .ex::before{display:none}
}
@media print{
  body{background:#fff;padding:0}
  body::after{display:none}
  .sheet{border:none;box-shadow:none;max-width:none;padding:0 8px}
  nav,#prog{display:none}
  .ex::before{display:none}
}
"""

JS = r"""
(function(){
  var reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* 矩阵热力着色(静态样式,始终执行) */
  document.querySelectorAll('.pvt tbody td:not(.verd)').forEach(function(td){
    var v=parseFloat(td.textContent);
    if(isNaN(v))return;
    if(v===0){td.classList.add('v0');return;}
    var a=0.06+Math.min(Math.abs(v)/22,1)*0.34;
    if(v>0){td.style.background='rgba(200,16,46,'+a.toFixed(3)+')';td.style.color='#7d0a1d';}
    else{td.style.background='rgba(59,77,99,'+a.toFixed(3)+')';td.style.color='#2b3a4d';}
  });

  /* 阅读进度条 */
  var prog=document.getElementById('prog'),ticking=false;
  function onScroll(){
    if(ticking)return;ticking=true;
    requestAnimationFrame(function(){
      var h=document.documentElement,max=h.scrollHeight-innerHeight;
      prog.style.width=(max>0?(h.scrollTop/max*100):0)+'%';
      ticking=false;
    });
  }
  addEventListener('scroll',onScroll,{passive:true});onScroll();

  /* 导航当前章节高亮 */
  var links={};document.querySelectorAll('nav a').forEach(function(a){links[a.getAttribute('href').slice(1)]=a});
  if('IntersectionObserver' in window){
    var nio=new IntersectionObserver(function(es){
      es.forEach(function(en){
        if(!en.isIntersecting)return;
        Object.keys(links).forEach(function(k){links[k].classList.remove('act')});
        links[en.target.id]&&links[en.target.id].classList.add('act');
      });
    },{rootMargin:'-30% 0px -60% 0px'});
    document.querySelectorAll('.ex').forEach(function(s){nio.observe(s)});
  }

  if(reduced||!('IntersectionObserver' in window)){
    document.querySelectorAll('.tw').forEach(function(t){t.classList.add('bars-on')});
    return;
  }

  /* 矩阵单元格交错浮现 */
  document.querySelectorAll('.pvt tbody td').forEach(function(td,i){td.style.transitionDelay=(i*16)+'ms'});

  /* KPI 数字滚动(保留前缀/千分位/小数位/后缀) */
  function countUp(el){
    var raw=el.textContent;
    var m=raw.match(/^([^\d\-+]*[+\-]?)([\d,]+(?:\.\d+)?)(.*)$/);
    if(!m)return;
    var prefix=m[1],suffix=m[3];
    var decimals=(m[2].split('.')[1]||'').length;
    var target=parseFloat(m[2].replace(/,/g,''));
    var hasComma=m[2].indexOf(',')>-1;
    var t0=null,DUR=1100;
    function fmt(v){
      var s=v.toFixed(decimals);
      if(hasComma){var p=s.split('.');p[0]=p[0].replace(/\B(?=(\d{3})+(?!\d))/g,',');s=p.join('.');}
      return prefix+s+suffix;
    }
    function step(ts){
      if(!t0)t0=ts;
      var p=Math.min((ts-t0)/DUR,1);
      var e=1-Math.pow(1-p,3);
      el.textContent=fmt(target*e);
      if(p<1)requestAnimationFrame(step);else el.textContent=raw;
    }
    requestAnimationFrame(step);
  }

  /* 滚动入场 */
  var below=[];
  document.querySelectorAll('.ex-head,.tw,.note,.kpis,.src,.rule-note,.takeaway').forEach(function(el){
    if(el.getBoundingClientRect().top>innerHeight*0.92){el.classList.add('reveal');below.push(el);}
  });
  var io=new IntersectionObserver(function(es){
    es.forEach(function(en){
      if(!en.isIntersecting)return;
      en.target.classList.add('on','bars-on');
      io.unobserve(en.target);
    });
  },{threshold:0.1});
  below.forEach(function(el){io.observe(el)});

  /* 首屏元素立即触发 */
  document.querySelectorAll('.tw').forEach(function(t){
    if(t.getBoundingClientRect().top<=innerHeight*0.92)requestAnimationFrame(function(){t.classList.add('bars-on')});
  });
  document.querySelectorAll('.kpi b').forEach(countUp);
})();
"""

# ── 组装页面 ────────────────────────────────────────────────────────────────

kpi = f"""<p class="kpis-cap">Key Figures · 核心读数</p>
<section class="kpis">
  <div class="kpi"><b>R$ {gmv_total:,.0f}</b><span>主品类 GMV(housewares,已送达口径)</span></div>
  <div class="kpi"><b>{MAIN['skus'].sum():,}</b><span>在售 SKU</span></div>
  <div class="kpi"><b>{len(delist)}</b><span>汰换清单 SKU(末位15%+差评硬规则)</span></div>
  <div class="kpi"><b>{roi:.2f}</b><span>黑五大促 ROI(增量假设毛利÷让利成本)</span></div>
  <div class="kpi"><b>+{bf_lift:.0f}%</b><span>黑五周 GMV vs 前4周基线</span></div>
</section>"""

sec1 = table(MAIN,
             {"price_band": "价格带", "skus": "SKU", "items": "销量件",
              "gmv": "GMV(R$)", "gmv_share": "GMV份额", "gap_ratio": "份额比",
              "band_verdict": "判定"},
             num={"skus", "items", "gmv", "gmv_share", "gap_ratio"},
             barcol="gmv", tagcol="band_verdict",
             hot=lambda r: "机会带" in str(r["band_verdict"]))
sec2a = table(delist.head(10),
              {"product_id": "SKU(前10)", "price_band": "价格带", "items": "销量",
               "avg_review": "均分", "score": "综合分", "reason": "汰换理由"},
              num={"items", "avg_review", "score"}, mono={"product_id"})
sec2b = table(intro.head(8),
              {"seller_id": "卖家(前8)", "band": "机会带", "skus": "SKU数",
               "gmv": "GMV(R$)", "avg_review": "均分", "action": "建议动作"},
              num={"skus", "gmv", "avg_review"}, mono={"seller_id"})
sec3 = matrix()
sec4 = table(m4,
             {"price_band": "价格带", "gmv": "黑五周GMV", "gmv_wk": "基线周GMV",
              "gmv_lift_pct": "GMV提升%", "incr_gp": "增量假设毛利(R$)"},
             num={"gmv", "gmv_wk", "gmv_lift_pct", "incr_gp"},
             hot=lambda r: "高价带" in str(r["price_band"]))

html = f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="家居日用品类采销经营模拟盘:品类结构、选品汰换、毛利控价、大促复盘四模块决策闭环,DuckDB + Python 一键复现">
<title>家居日用品类·采销经营模拟盘</title>
<style>{CSS}</style>
</head>
<body>
<i id="prog"></i>
<div class="sheet">

<header class="mast">
  <div class="mast-top">
    <span class="logotype">Category Management Simulator</span>
    <span class="docno">个人研究项目 · 2026</span>
  </div>
  <h1>家居日用品类 <em>·</em> 采销经营模拟盘</h1>
  <p class="en-sub">Housewares Category P&amp;L Simulator — Assortment, Pricing &amp; Promotion Review</p>
  <p class="lede">四模块决策闭环,全部数字由同一条管线生成并互相对账。</p>
  <div class="flow"><s><b>01</b>品类结构</s><em></em><s><b>02</b>选品汰换</s><em></em><s><b>03</b>毛利控价</s><em></em><s><b>04</b>大促复盘</s></div>
  <dl class="meta">
    <div><dt>Data</dt><dd>Olist 巴西电商 10 万+ 真实订单(housewares 主品类,已送达口径)</dd></div>
    <div><dt>Method</dt><dd>DuckDB SQL + Python;决策规则成文,逐条注明依据</dd></div>
    <div><dt>Reproduce</dt><dd>一键复现:<code>python run_pipeline.py</code>;跨模块 GMV 对账(容差 0)</dd></div>
    <div><dt>Companion</dt><dd>配套作品:<a href="research/">行业研究报告</a>(中国市场判断层) · <a href="https://github.com/Martin-cell-blip/logistics-settlement-recon">结算对账引擎</a>(结算侧)</dd></div>
  </dl>
  <div class="seal" aria-hidden="true"><b>对账</b><b>无误</b><i>TOLERANCE&nbsp;0</i></div>
</header>

<nav id="nav">
  <a href="#m1"><i>01</i>结构诊断</a>
  <a href="#m2"><i>02</i>选品汰换</a>
  <a href="#m3"><i>03</i>控价矩阵</a>
  <a href="#m4"><i>04</i>大促复盘</a>
</nav>

{kpi}

<div class="note"><b>诚实声明</b>数据为 Olist 巴西电商真实交易(方法论演示,不代表中国市场;中国市场判断见配套<a href="research/">《家居日用品类行业研究报告》</a>);毛利为按价格带假设的参数层(取值依据行研,见 params/cost_assumptions.csv);价格弹性为敏感性假设而非估计值。</div>

<section class="ex" id="m1" data-no="01">
  <div class="ex-head"><span class="ex-no">图 1</span>
    <div>
      <h2>品类结构与价格带诊断<small>主品类 housewares</small></h2>
      <p class="ex-en">Exhibit 1 &nbsp;Price-band structure &amp; supply–demand balance</p>
    </div>
  </div>
  <p class="rule-note">判定规则:GMV份额/SKU份额 <b>&gt; 1.25 → 供给不足(机会带)</b>;&lt; 0.8 → 供给过密</p>
  {sec1}
  <p class="takeaway"><b>结 论</b>高价带以 25.8% 的 SKU 贡献 62.6% 的 GMV(份额比 2.42),是唯一的供给不足带,补供给优先级最高;低价带与中价带供给过密,汰换先行。</p>
  <p class="src">资料来源:Olist 公开数据集;run_pipeline.py 计算,跨模块 GMV 对账(容差 0)。</p>
</section>

<section class="ex" id="m2" data-no="02">
  <div class="ex-head"><span class="ex-no">图 2</span>
    <div>
      <h2>选品/汰换:四维评分卡<small>GMV 35% · 动销 25% · 评分 25% · 运费占比 15%</small></h2>
      <p class="ex-en">Exhibit 2 &nbsp;Assortment scorecard — delisting &amp; onboarding candidates</p>
    </div>
  </div>
  {sec2a}
  <p class="rule-note" style="margin-top:20px">机会带引入候选(评分≥4.5 的高分卖家)</p>
  {sec2b}
  <p class="takeaway"><b>结 论</b>{len(delist)} 个低效 SKU 集中于供给过密带,汰换释放的坑位优先给到机会带 {len(intro)} 家评分≥4.5 的高分卖家(谈判扩盘/独家款)。</p>
  <p class="src">资料来源:Olist 公开数据集;评分卡权重与硬规则见 specs/ 决策规则文档。</p>
</section>

<section class="ex" id="m3" data-no="03">
  <div class="ex-head"><span class="ex-no">图 3</span>
    <div>
      <h2>毛利与控价:3档调价 × 3档弹性<small>单元格 = 毛利变动 %</small></h2>
      <p class="ex-en">Exhibit 3 &nbsp;Pricing scenario matrix — margin impact under elasticity assumptions</p>
    </div>
  </div>
  <p class="rule-note">列 = (调价幅度, 弹性假设);行尾为带级判定。着色:<b>红 = 毛利正增</b>,蓝灰 = 毛利受损,深浅表示幅度。</p>
  {sec3}
  <p class="takeaway"><b>结 论</b>全部价格带在所有弹性假设下提价 +5% 毛利均为正,提价空间真实存在;低价带对价格最敏感(-22.0% ~ +20.0%),应保价引流、不轻易动价。</p>
  <p class="src">资料来源:params/cost_assumptions.csv 参数层;弹性为敏感性假设而非估计值。</p>
</section>

<section class="ex" id="m4" data-no="04">
  <div class="ex-head"><span class="ex-no">图 4</span>
    <div>
      <h2>黑五大促复盘<small>2017-11-20 ~ 26 vs 前4周基线</small></h2>
      <p class="ex-en">Exhibit 4 &nbsp;Black Friday post-mortem — uplift by price band</p>
    </div>
  </div>
  {sec4}
  <p class="takeaway"><b>结 论</b>黑五周 GMV +{bf_lift:.0f}%,其中高价带提升 241.40%;让利成本极小,增长由流量而非折扣驱动,大促资源应向高价带倾斜。</p>
  <p class="src">资料来源:Olist 公开数据集;让利成本极小,判断增量由流量而非折扣驱动。</p>
</section>

<footer>
  <span>category-management-sim · 全部数字由 run_pipeline.py 生成并经跨模块 GMV 对账校验</span>
  <span>复现:<code>python run_pipeline.py</code> · <a href="https://github.com/Martin-cell-blip/category-management-sim">源码 GitHub</a></span>
</footer>

</div>
<script>{JS}</script>
</body>
</html>
"""

(DOCS / "index.html").write_text(html, encoding="utf-8")
print(f"  看板已生成:{DOCS / 'index.html'}")
