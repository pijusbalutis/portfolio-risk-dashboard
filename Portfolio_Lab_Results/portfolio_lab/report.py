"""Self-contained HTML dashboard: embedded SVG charts, native controls, no CDN."""

from base64 import b64encode
from html import escape
from io import BytesIO
from pathlib import Path
import json
import numpy as np
from .data import atomic_write


def _image(figure, title: str) -> str:
    buffer = BytesIO()
    figure.savefig(buffer, format="svg", bbox_inches="tight")
    data = b64encode(buffer.getvalue()).decode()
    return f'<img src="data:image/svg+xml;base64,{data}" alt="{escape(title)}" loading="lazy">'


def _clean_number(value):
    return float(value) if np.isfinite(value) else None


def write_dashboard(analysis, figures: dict, path: Path):
    synthetic = analysis.metadata["data"]["synthetic"]
    badge = "SIMULATED DATA · DEMONSTRATION ONLY" if synthetic else "HISTORICAL RESEARCH · USD"
    first, last = analysis.prices.index[[0, -1]]
    rf = analysis.metadata["risk_free"]
    rf_label = (f"Fixed {rf['annual_effective_rate']:.2%} effective annual cash assumption"
                if rf["source"] == "fixed assumption" else "Lagged FRED DGS3MO yield proxy")
    payload = {
        "dates": analysis.prices.index.strftime("%Y-%m-%d").tolist(),
        "nav": {name: result.nav.round(8).tolist() for name, result in analysis.results.items()},
        "metrics": {name: {key: _clean_number(value) for key, value in row.items()}
                    for name, row in analysis.metrics.to_dict("index").items()},
    }
    encoded = json.dumps(payload, allow_nan=False).replace("<", "\\u003c")
    metric_titles = [
        ("cagr", "CAGR", "percent"), ("annual_volatility", "Annual volatility", "percent"),
        ("sharpe", "Sharpe ratio", "number"), ("max_drawdown", "Maximum drawdown", "percent"),
        ("ending_nav", "Ending value", "money"), ("total_fees", "Rebalancing costs", "money"),
    ]
    cards = "".join(
        f'<div class="kpi"><span>{title}</span><strong id="metric-{key}">—</strong>'
        f'<small>{kind}</small></div>' for key, title, kind in metric_titles
    )
    figures_html = {
        key: f'<article class="chart-card">{_image(fig, key.replace("_", " "))}</article>'
        for key, fig in figures.items() if key not in {"growth", "executive_summary"}
    }
    table = analysis.metrics.loc[:, ["cagr", "annual_volatility", "sharpe", "sortino",
                                    "max_drawdown", "beta", "tracking_error"]].copy()
    table.columns = ["CAGR", "Volatility", "Sharpe", "Sortino", "Max drawdown", "Beta", "Tracking error"]
    for col in ["CAGR", "Volatility", "Max drawdown", "Tracking error"]:
        table[col] = table[col].map(lambda x: f"{x:.2%}")
    for col in ["Sharpe", "Sortino", "Beta"]:
        table[col] = table[col].map(lambda x: f"{x:.2f}" if np.isfinite(x) else "N/A")
    comparison = table.to_html(classes="comparison", border=0)
    warnings = analysis.metadata["data_quality"]["warnings"]
    warning_html = "".join(f"<li>{escape(warning)}</li>" for warning in warnings)
    if not warning_html:
        warning_html = "<li>No flagged issues under the implemented quality checks.</li>"
    provenance = escape(json.dumps(analysis.metadata, indent=2))
    html = TEMPLATE
    replacements = {
        "__BADGE__": badge, "__FIRST__": str(first.date()), "__LAST__": str(last.date()),
        "__RF__": escape(rf_label), "__CARDS__": cards, "__PAYLOAD__": encoded,
        "__TABLE__": comparison, "__PROVENANCE__": provenance, "__WARNINGS__": warning_html,
        "__COST__": f"{analysis.config.cost_bps:g}",
        "__ROWS__": str(len(analysis.prices)), "__ASSETS__": str(len(analysis.prices.columns)),
        "__REBALANCE__": escape(analysis.config.rebalance),
        "__ANNUALIZATION__": str(analysis.config.annualization),
    }
    for key, value in figures_html.items():
        replacements["__" + key.upper() + "__"] = value
    for token, replacement in replacements.items():
        html = html.replace(token, replacement)
    atomic_write(path, html)


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Portfolio Lab | Performance & Risk</title>
<style>
:root{--ink:#142d4e;--muted:#637086;--teal:#087f8c;--line:#dce3ea;--coral:#d66a4b}
*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:var(--ink);font:15px/1.5 system-ui,-apple-system,sans-serif}
.wrap{max-width:1420px;margin:auto;padding:30px 40px 60px}.brand{font-size:12px;letter-spacing:.2em;font-weight:800;color:var(--teal)}
.top{display:flex;justify-content:space-between;gap:20px;align-items:start}.badge{padding:7px 12px;background:#fff0e9;color:#9b4029;border:1px solid #f2d1c2;font-size:11px;font-weight:750;border-radius:24px}
h1{font-size:36px;line-height:1.15;margin:12px 0 9px;letter-spacing:-.04em}h2{font-size:20px;margin:0 0 5px}p{color:var(--muted);margin:6px 0 20px}
.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:24px 0 18px}select,button{font:inherit;border:1px solid var(--line);border-radius:8px;padding:9px 14px;background:white;color:var(--ink);cursor:pointer}
button:focus-visible,select:focus-visible{outline:3px solid #81c8d0;outline-offset:3px}
.tabs{margin-left:auto;display:flex;gap:7px;flex-wrap:wrap}.tabs button[aria-selected=true],.ranges button.active{background:var(--ink);color:white;border-color:var(--ink)}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:18px 0}.kpi{background:white;border:1px solid var(--line);padding:20px;border-radius:12px}
.kpi span{font-size:12px;color:var(--muted);display:block}.kpi strong{font-size:27px;display:block;margin:7px 0 0;letter-spacing:-.035em}.kpi small{display:none}
.panel{background:white;border:1px solid var(--line);border-radius:14px;padding:24px;margin-bottom:18px}.chart-head{display:flex;align-items:center;justify-content:space-between;gap:20px}.ranges{display:flex;gap:6px}.ranges button{padding:5px 10px;font-size:12px}
.chart-host{position:relative;width:100%;height:355px;margin-top:12px}svg.main-chart{width:100%;height:100%;overflow:visible;touch-action:pan-y}
.tooltip{display:none;position:absolute;pointer-events:none;z-index:10;background:var(--ink);color:white;padding:10px 14px;border-radius:8px;font-size:12px;white-space:nowrap;box-shadow:0 4px 18px #142d4e25}
.legend{display:flex;gap:20px;flex-wrap:wrap;font-size:12px;color:var(--muted)}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}
.note{font-size:12px;color:var(--muted);margin:10px 0 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.chart-card{background:white;border:1px solid var(--line);border-radius:14px;overflow:hidden;padding:12px}.chart-card img{width:100%;height:auto;display:block}
.tab-content[hidden]{display:none}.table-wrap{overflow-x:auto}.comparison{width:100%;border-collapse:collapse;text-align:right;font-size:13px}.comparison th,.comparison td{padding:13px 10px;border-bottom:1px solid var(--line)}.comparison th:first-child{text-align:left}.comparison thead{color:var(--muted)}
pre{background:#f3f6fa;padding:18px;border-radius:8px;overflow:auto;max-height:480px;font-size:12px}li{margin:6px 0;color:var(--muted)}footer{margin-top:30px;font-size:12px;color:var(--muted)}
@media(max-width:1000px){.kpis{grid-template-columns:repeat(3,1fr)}.wrap{padding:24px}.tabs{margin-left:0}.top{display:block}.badge{display:inline-block;margin-top:12px}}
@media(max-width:680px){.grid{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}h1{font-size:29px}.wrap{padding:16px}.kpi{padding:14px}.kpi strong{font-size:24px}.panel{padding:16px}.chart-host{height:300px}.chart-head{display:block}.ranges{margin-top:10px}}
@media print{button,select,.controls{display:none}.tab-content[hidden]{display:block}.wrap{padding:0}.chart-card,.panel{break-inside:avoid}}
</style></head><body><main class="wrap">
<div class="top"><div><div class="brand">PORTFOLIO LAB / RESEARCH SYSTEMS</div>
<h1>Multi-Asset Performance & Risk</h1><p>__FIRST__ — __LAST__ · USD · __ASSETS__ assets · __ROWS__ price observations</p></div>
<span class="badge">__BADGE__</span></div>
<div class="controls"><label for="strategy">Inspect strategy</label><select id="strategy">
<option>Portfolio</option><option>Buy &amp; hold</option><option>Benchmark</option></select>
<div class="tabs" role="tablist" aria-label="Dashboard sections">
<button role="tab" aria-selected="true" data-tab="overview" aria-controls="overview">Overview</button>
<button role="tab" aria-selected="false" data-tab="risk" aria-controls="risk">Risk</button>
<button role="tab" aria-selected="false" data-tab="positions" aria-controls="positions">Attribution</button>
<button role="tab" aria-selected="false" data-tab="data" aria-controls="data">Data & assumptions</button></div></div>
<div class="kpis">__CARDS__</div>
<p class="note" id="metric-scope">All metrics use the full sample. Chart range buttons change the chart window only.</p>
<section id="overview" role="tabpanel" class="tab-content">
<div class="panel"><div class="chart-head"><div><h2>Portfolio value</h2><p class="note">Net of rebalancing costs · hover for exact observations</p></div>
<div class="ranges"><button data-years="1">1Y</button><button data-years="3">3Y</button><button data-years="0" class="active">All</button></div></div>
<div class="chart-host" id="chart-host"><svg class="main-chart" id="nav-chart" role="img" aria-label="Portfolio, buy-and-hold and benchmark values over time"></svg><div class="tooltip" id="tooltip"></div></div>
<div class="legend"><span><i class="dot" style="background:#087f8c"></i>Portfolio</span><span><i class="dot" style="background:#7b91b4"></i>Buy &amp; hold</span><span><i class="dot" style="background:#d66a4b"></i>Benchmark</span></div></div>
<div class="panel"><h2>Full-sample comparison</h2><p class="note">Same common history, starting capital and initial-holdings convention.</p><div class="table-wrap">__TABLE__</div></div>
<div class="grid">__DRAWDOWNS____MONTHLY_RETURNS__</div></section>
<section id="risk" role="tabpanel" class="tab-content" hidden>
<p>Rolling comparisons include all strategies. Asset correlations, component risk and scenarios describe the configured Portfolio.</p>
<div class="grid">__ROLLING_VOLATILITY____CORRELATION____RISK_CONTRIBUTIONS____STRESS__</div></section>
<section id="positions" role="tabpanel" class="tab-content" hidden><p>Portfolio allocation and dollar P&amp;L. Asset P&amp;L less trading costs equals the change in net asset value.</p>
<div class="grid">__WEIGHTS____PNL_ATTRIBUTION__</div></section>
<section id="data" role="tabpanel" class="tab-content" hidden>
<div class="panel"><h2>Model conventions</h2><ul>
<li>Risk-free input: __RF__. This is a cash-return proxy used for excess-return metrics.</li>
<li>Portfolio rebalancing: __REBALANCE__; benchmark: monthly; trades occur at the first observed session's close in the new period.</li>
<li>Cost: __COST__ basis points per dollar bought or sold. The cost is paid from portfolio value.</li>
<li>The portfolio begins already invested. Initial purchase and terminal liquidation costs are excluded for all strategies.</li>
<li>Adjusted total-return units include provider adjustments. Dividends are not added again.</li>
<li>Missing prices are never forward-filled. Only common observed sessions are used.</li>
<li>CAGR uses elapsed calendar years; volatility and moment-based ratios use __ANNUALIZATION__ sessions per year.</li>
<li>Universe selection is fixed. No taxes, leverage, external cash flows, or live order execution.</li>
</ul></div><div class="panel"><h2>Data-quality findings</h2><ul>__WARNINGS__</ul></div>
<div class="panel"><h2>Run provenance</h2><pre>__PROVENANCE__</pre></div></section>
<footer>Portfolio Lab · Reproducible quantitative research. Simulated runs are demonstrations; historical results describe the supplied data and stated assumptions.</footer>
</main><script id="portfolio-data" type="application/json">__PAYLOAD__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("portfolio-data").textContent);
const colors={"Portfolio":"#087f8c","Buy & hold":"#7b91b4","Benchmark":"#d66a4b"};
const strategies=Object.keys(data.nav), svg=document.getElementById("nav-chart");
let selected="Portfolio",years=0, geometry=null;
const ns="http://www.w3.org/2000/svg";
function add(tag,attrs,text){const el=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));if(text!==undefined)el.textContent=text;svg.appendChild(el);return el}
function metrics(){const values=data.metrics[selected];Object.entries(values).forEach(([key,value])=>{const node=document.getElementById("metric-"+key);if(!node)return;
let output="N/A";if(value!==null){output=["ending_nav","total_fees"].includes(key)?new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0}).format(value):key==="sharpe"?value.toFixed(2):(value*100).toFixed(2)+"%"}node.textContent=output});
document.getElementById("metric-scope").textContent=selected+" · full-sample metrics. Range buttons affect the chart only."}
function render(){if(document.getElementById("overview").hidden)return;svg.replaceChildren();const width=Math.max(svg.clientWidth,280),height=svg.clientHeight||355;
svg.setAttribute("viewBox","0 0 "+width+" "+height);const left=65,right=18,top=18,bottom=35;
const cutoff=years?new Date(data.dates.at(-1)+"T00:00:00Z").getTime()-years*365.25*86400000:0;
let start=years?data.dates.findIndex(d=>new Date(d+"T00:00:00Z").getTime()>=cutoff):0;if(start<0)start=0;
const last=data.dates.length-1;let low=Infinity,high=-Infinity;strategies.forEach(s=>data.nav[s].slice(start).forEach(v=>{low=Math.min(low,v);high=Math.max(high,v)}));
const pad=Math.max((high-low)*.12,high*.015);low-=pad;high+=pad;
const X=i=>left+(i-start)/Math.max(last-start,1)*(width-left-right),Y=v=>top+(high-v)/(high-low)*(height-top-bottom);
for(let j=0;j<5;j++){const v=low+(high-low)*j/4,y=Y(v);add("line",{x1:left,x2:width-right,y1:y,y2:y,stroke:"#e5eaf0"});add("text",{x:left-10,y:y+4,"text-anchor":"end",fill:"#637086","font-size":11},"$"+(v/1000).toFixed(0)+"k")}
for(let j=0;j<5;j++){const i=Math.round(start+(last-start)*j/4);add("text",{x:X(i),y:height-8,"text-anchor":"middle",fill:"#637086","font-size":11},data.dates[i].slice(0,7))}
strategies.filter(s=>s!==selected).concat([selected]).forEach(s=>{let path="";for(let i=start;i<=last;i++)path+=(i===start?"M":"L")+X(i).toFixed(2)+","+Y(data.nav[s][i]).toFixed(2);
add("path",{d:path,fill:"none",stroke:colors[s],"stroke-width":s===selected?2.6:1.4,opacity:s===selected?1:.65})});
const cursor=add("line",{x1:0,x2:0,y1:top,y2:height-bottom,stroke:"#9aaabd","stroke-dasharray":"4 4",visibility:"hidden"});
geometry={width,height,left,right,start,last,X,Y,cursor};}
svg.addEventListener("pointermove",event=>{if(!geometry)return;const g=geometry,box=svg.getBoundingClientRect(),px=event.clientX-box.left;
const i=Math.max(g.start,Math.min(g.last,Math.round(g.start+(px-g.left)/(g.width-g.left-g.right)*(g.last-g.start))));
g.cursor.setAttribute("x1",g.X(i));g.cursor.setAttribute("x2",g.X(i));g.cursor.setAttribute("visibility","visible");
const tip=document.getElementById("tooltip");tip.replaceChildren();const title=document.createElement("strong");title.textContent=data.dates[i];tip.appendChild(title);
strategies.forEach(s=>{const line=document.createElement("div");line.textContent=s+": "+new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0}).format(data.nav[s][i]);tip.appendChild(line)});
tip.style.display="block";tip.style.left=Math.max(0,Math.min(px+14,g.width-tip.offsetWidth-8))+"px";tip.style.top="18px"});
svg.addEventListener("pointerleave",()=>{document.getElementById("tooltip").style.display="none";if(geometry)geometry.cursor.setAttribute("visibility","hidden")});
document.getElementById("strategy").addEventListener("change",event=>{selected=event.target.value;metrics();render()});
document.querySelectorAll(".ranges button").forEach(button=>button.addEventListener("click",()=>{years=Number(button.dataset.years);document.querySelectorAll(".ranges button").forEach(b=>b.classList.toggle("active",b===button));render()}));
document.querySelectorAll("[data-tab]").forEach(button=>button.addEventListener("click",()=>{document.querySelectorAll("[data-tab]").forEach(b=>b.setAttribute("aria-selected",b===button?"true":"false"));document.querySelectorAll(".tab-content").forEach(p=>p.hidden=p.id!==button.dataset.tab);render()}));
window.addEventListener("resize",render);metrics();render();
</script></body></html>
"""
