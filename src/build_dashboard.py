"""Stand-alone HTML dashboard (dashboard/catalog_quality.html): three tabs (catalogue quality, taxonomy, scenarios
and agents), Plotly embedded so it works offline, aggregates only. Usage: python src/build_dashboard.py
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DASH, FOOTER, OUT, PROCESSED  # noqa: E402

BLUE, BLUE_L, BLUE_D, GRAY, RED, INK2 = "#2A78D6", "#86B6EF", "#1C5CAB", "#C9C7BF", "#D03B3B", "#52514E"
LAYOUT = dict(font=dict(family="Segoe UI, sans-serif", size=12, color=INK2), paper_bgcolor="#FCFCFB",
              plot_bgcolor="#FCFCFB", margin=dict(l=10, r=10, t=44, b=10), hoverlabel=dict(font_size=12))
_first = [True]


def div(fig, h=340):
    fig.update_layout(**LAYOUT, height=h)
    inc = _first[0]
    _first[0] = False
    return pio.to_html(fig, full_html=False, include_plotlyjs="inline" if inc else False,
                       config={"displayModeBar": False, "responsive": True})


def table(df, cols):
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols.values())
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(r[k]))}</td>" for k in cols) + "</tr>" for _, r in df.iterrows())
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def kpis(items):
    return '<div class="kpis">' + "".join(f'<div class="kpi"><div class="kl">{a}</div><div class="kv">{b}</div><div class="kn">{c}</div></div>'
                                          for a, b, c in items) + "</div>"


def main():
    st = json.loads((OUT / "catalog_stats.json").read_text())
    rules = pd.read_csv(OUT / "quality_rules_before_after.csv")
    det = pd.read_csv(OUT / "detection_by_type.csv")
    ev = json.loads((OUT / "classification_eval.json").read_text())
    cov = pd.read_csv(OUT / "taxonomy_coverage.csv")
    res = pd.read_csv(OUT / "agent_results.csv")
    sc = pd.read_parquet(OUT / "quality_scores.parquet")
    cat = pd.read_parquet(PROCESSED / "catalog.parquet")
    tabs = []

    # 1 quality ----------------------------------------------------------------------------------
    f1 = go.Figure()
    for v, c in (("before", GRAY), ("after", BLUE)):
        f1.add_histogram(x=sc[sc.view == v].score, name=v, marker_color=c, opacity=0.8, xbins=dict(size=0.025))
    f1.update_layout(barmode="overlay", title="Quality score per SKU, before and after the pipeline", xaxis_title="score (0-1)")
    r = rules.assign(rate_b=1 - rules.pass_rate_before, rate_a=1 - rules.pass_rate_after).sort_values("rate_b")
    f2 = go.Figure([go.Bar(y=r.id + " " + r.description.str[:48], x=r.rate_b, name="before", orientation="h", marker_color=GRAY),
                    go.Bar(y=r.id + " " + r.description.str[:48], x=r.rate_a, name="after", orientation="h", marker_color=BLUE)])
    f2.update_layout(title="Share of SKUs failing each rule", xaxis_tickformat=".0%", barmode="group")
    d = det.sort_values("caught_rate")
    f3 = go.Figure([go.Bar(y=d.label, x=d.caught_rate, name="caught", orientation="h", marker_color=BLUE_L),
                    go.Bar(y=d.label, x=d.fixed_rate, name="fixed in the clean catalogue", orientation="h", marker_color=BLUE_D)])
    f3.update_layout(title="SIMULATED errors: share caught and fixed, by type", xaxis_tickformat=".0%", barmode="group")
    tabs.append(("Catalogue quality", kpis([("SKUs", f"{st['clean_skus']:,}", f"from {st['raw_listings']:,} raw listings"),
                                           ("Duplicates merged", f"{st['duplicates_merged']:,}", "across and within sources"),
                                           ("Mean quality", f"{st['quality_before']:.2f} → {st['quality_after']:.2f}", "26 rules, weighted"),
                                           ("Held for review", f"{st['held_for_review']:,}", "price errors and outliers")])
                 + div(f1, 300) + div(f2, 720) + div(f3, 380)))

    # 2 taxonomy ---------------------------------------------------------------------------------
    c = cov.sort_values("skus")
    f4 = go.Figure(go.Bar(y=c.department, x=c.skus, orientation="h", marker_color=BLUE,
                          text=[f"{u}/{t} leaves" for u, t in zip(c.leaves_used, c.leaves_total)], textposition="outside"))
    f4.update_layout(title="SKUs per department (leaf categories used / defined)")
    m = pd.DataFrame(ev["precision_by_method"])
    f5 = go.Figure(go.Bar(x=m.category_method, y=m.precision, marker_color=BLUE, text=[f"n={n}" for n in m.n], textposition="outside"))
    f5.update_layout(title="Accuracy by classification method (200 products labelled by hand)", yaxis_tickformat=".0%")
    conf = pd.read_csv(OUT / "confusion_department.csv", index_col=0)
    f6 = go.Figure(go.Heatmap(z=conf.values, x=conf.columns, y=conf.index, colorscale=[[0, "#FCFCFB"], [1, BLUE_D]], showscale=False,
                              text=conf.values, texttemplate="%{text}"))
    f6.update_layout(title="Confusion by department (rows: hand label, columns: pipeline)", xaxis_tickangle=35)
    tabs.append(("Taxonomy", kpis([("Leaf categories", "151", "3-4 levels, all mapped to Google ids"),
                                  ("Accuracy (hand sample)", f"{ev['final_accuracy']:.0%}", f"{ev['final_accuracy_unambiguous']:.0%} without ambiguous items"),
                                  ("Department accuracy", f"{ev['department_accuracy']:.0%}", "right top-level aisle"),
                                  ("In 'Other'", f"{ev['other_share_catalogue']:.1%}", "low-confidence products")])
                 + div(f4, 460) + div(f5, 340) + div(f6, 520)))

    # 3 scenarios and agents ----------------------------------------------------------------------
    s = res.groupby(["view", "agent"]).success.mean().reset_index()
    f7 = go.Figure([go.Bar(x=s[s.agent == a].view, y=s[s.agent == a].success, name=a, marker_color=col)
                    for a, col in (("keyword", GRAY), ("keyword+filters", BLUE))])
    f7.update_layout(title="Success rate on 150 scenarios, by catalogue version", yaxis_tickformat=".0%")
    t = res[res.view == "4 clean"].groupby(["type", "agent"]).success.mean().unstack()
    f8 = go.Figure([go.Bar(y=t.index, x=t[a], name=a, orientation="h", marker_color=col) for a, col in (("keyword", GRAY), ("keyword+filters", BLUE))])
    f8.update_layout(title="Success by scenario type (clean catalogue)", xaxis_tickformat=".0%", barmode="group")
    fails = res[(res.view == "4 clean") & ~res.success].failure.str.split("; ").explode()
    fails = fails.str.replace(r"role '.*' not satisfied", "a basket item missing or wrong", regex=True).str.replace(r":.*", "", regex=True)
    fl = fails.value_counts().head(10).rename_axis("reason").reset_index(name="episodes")
    tabs.append(("Scenarios & agents", kpis([("Scenarios", "150", "7 types, difficulty 1-5"),
                                            ("Best agent, raw data", f"{s[(s.agent == 'keyword+filters') & (s.view == '1 raw')].success.iloc[0]:.0%}", "success rate"),
                                            ("Best agent, clean data", f"{s[(s.agent == 'keyword+filters') & (s.view == '4 clean')].success.iloc[0]:.0%}", "success rate"),
                                            ("Active SKUs in the shop", f"{(cat.listing_status == 'active').sum():,}", "SIMULATED prices and stock")])
                 + div(f7, 340) + div(f8, 360) + "<h3>Most frequent failure reasons, both agents (clean catalogue)</h3>" + table(fl, {"reason": "Reason", "episodes": "Episodes"})))

    nav = "".join(f'<a href="#{i + 1}" data-t="{i + 1}">{html.escape(n)}</a>' for i, (n, _) in enumerate(tabs))
    secs = "".join(f'<section id="t{i + 1}">{b}</section>' for i, (_, b) in enumerate(tabs))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Catalogue quality dashboard</title><style>
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#F4F4F2;color:#0B0B0B;margin:0}}
header{{padding:18px 24px 6px}} h1{{font-size:20px;margin:0}} .sub{{color:#52514E;font-size:13px;margin-top:4px}}
nav{{display:flex;gap:6px;padding:8px 24px;position:sticky;top:0;background:#F4F4F2;z-index:5}}
nav a{{padding:7px 14px;border-radius:6px;border:1px solid #C9C7BF;color:#52514E;text-decoration:none;font-size:13px;background:#FCFCFB}}
nav a.on{{background:#1C5CAB;color:#fff;border-color:#1C5CAB}} section{{display:none;padding:8px 24px 24px}} section.on{{display:block}}
section>div{{background:#FCFCFB;border:1px solid #E1E0D9;border-radius:8px;margin-bottom:12px;padding:6px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;background:none!important;border:none!important;padding:0!important}}
.kpi{{background:#FCFCFB;border:1px solid #E1E0D9;border-radius:8px;padding:10px 14px}} .kl{{font-size:11px;font-weight:700;color:#52514E;text-transform:uppercase}}
.kv{{font-size:24px;font-weight:700;color:#1C5CAB}} .kn{{font-size:12px;color:#52514E}}
table{{border-collapse:collapse;background:#FCFCFB;font-size:13px}} th,td{{padding:4px 10px;border-bottom:1px solid #E1E0D9;text-align:left}}
footer{{font-size:11px;color:#898781;padding:0 24px 18px}}</style></head><body>
<header><h1>Unified catalogue for AI shopping agents: quality, taxonomy, agents</h1>
<div class="sub">PUBLIC DATA: Amazon Berkeley Objects, Open Food Facts, Google Product Taxonomy, UCI Online Retail II · SIMULATED: other-platform export, injected errors, prices, stock, personas</div></header>
<nav>{nav}</nav>{secs}<footer>{FOOTER}</footer>
<script>function show(n){{document.querySelectorAll('section').forEach((s,i)=>s.classList.toggle('on',i+1==n));
document.querySelectorAll('nav a').forEach((a,i)=>a.classList.toggle('on',i+1==n));window.dispatchEvent(new Event('resize'));}}
document.querySelectorAll('nav a').forEach(a=>a.onclick=e=>{{show(+a.dataset.t);}});show(+(location.hash.slice(1)||1));</script></body></html>"""
    DASH.mkdir(exist_ok=True)
    (DASH / "catalog_quality.html").write_text(page, encoding="utf-8")
    print("dashboard:", DASH / "catalog_quality.html")


if __name__ == "__main__":
    main()
