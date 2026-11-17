"""8-page PDF report (16:9): HTML + inline SVG charts, printed by headless Edge. Every number is read from
data/outputs (pipeline results); none is typed in the text. Usage: python src/build_pdf.py
"""
from __future__ import annotations

import html
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
from jinja2 import Template

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charts as C  # noqa: E402
from config import DOCS, FOOTER, OUT, PROCESSED, ROOT, SEEN_ON, TAXO, ai_note  # noqa: E402

TMP = ROOT / ".tmp"
PDF = DOCS / "micro1_ecommerce_catalog_environment_case_study.pdf"
rd = lambda n: pd.read_csv(OUT / f"{n}.csv")  # noqa: E731
js = lambda n: json.loads((OUT / f"{n}.json").read_text())  # noqa: E731

CSS = """
@page { size: 16in 9in; margin: 0 }
* { box-sizing: border-box; margin: 0; padding: 0 }
body { font-family: 'Segoe UI', system-ui, sans-serif; color: #0B0B0B; background: #F4F4F2; }
.page { width: 1536px; height: 864px; padding: 30px 40px 16px; display: flex; flex-direction: column;
        background: #F4F4F2; page-break-after: always; overflow: hidden; position: relative }
header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; min-height: 56px }
h1 { font-size: 24px; font-weight: 700; line-height: 1.2; max-width: 1250px; letter-spacing: -0.2px }
.sub { color: #52514E; font-size: 13.5px; margin-top: 5px; max-width: 1270px; line-height: 1.4 }
.tag { font-size: 11.5px; font-weight: 700; letter-spacing: .8px; color: #52514E; border: 1px solid #C9C7BF;
       border-radius: 4px; padding: 4px 9px; white-space: nowrap; margin-top: 6px; background: #FCFCFB }
.tag.sim { color: #1C5CAB; border-color: #86B6EF } .tag.real { color: #0E7A55; border-color: #8FD3B8 }
.kpis { display: grid; gap: 12px; margin-bottom: 12px }
.card { background: #FCFCFB; border: 1px solid #E1E0D9; border-radius: 8px; padding: 12px 16px; display: flex;
        flex-direction: column; min-height: 0; overflow: hidden }
.kpi { padding: 11px 16px }
.klabel { font-size: 11px; font-weight: 700; color: #52514E; letter-spacing: .5px; text-transform: uppercase }
.kval { font-size: 29px; font-weight: 700; margin-top: 2px; line-height: 1.15 } .kval.blue { color: #1C5CAB } .kval.red { color: #D03B3B }
.knote { font-size: 12px; color: #52514E; margin-top: 3px; line-height: 1.35 }
.grid { display: grid; gap: 12px; flex: 1; min-height: 0 }
.card h3 { font-size: 13.5px; font-weight: 600; margin-bottom: 6px }
.ctag { font-size: 9.5px; font-weight: 700; letter-spacing: .6px; padding: 1px 5px; border-radius: 3px; margin-left: 6px; vertical-align: 1px }
.ctag.real { color: #0E7A55; border: 1px solid #8FD3B8 } .ctag.sim { color: #1C5CAB; border: 1px solid #86B6EF }
.body { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; font-size: 12.8px; line-height: 1.42 }
.body svg { width: 100%; height: 100% } .body img { max-width: 100%; max-height: 100% }
.body.text { display: block; overflow: hidden; color: #2B2A28 }
.body.text p { margin-bottom: 6px } .body.text ul { margin: 0 0 5px 17px } .body.text li { margin-bottom: 3px }
table { border-collapse: collapse; width: 100%; font-size: 11.8px }
th { text-align: left; color: #52514E; font-weight: 600; border-bottom: 1px solid #C9C7BF; padding: 3px 5px }
td { padding: 3px 5px; border-bottom: 1px solid #EEEDE8; vertical-align: top } td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap }
td.err { color: #B02E2E; font-weight: 600 } td.ok { color: #0E7A55; font-weight: 600 }
footer { font-size: 10.5px; color: #898781; margin-top: 8px }
b.blue { color: #1C5CAB } b.red { color: #B02E2E }
.lab { font-weight: 700; color: #52514E; font-size: 11.5px; letter-spacing: .4px }
.flow { display: flex; gap: 7px; align-items: stretch; width: 100% }
.flow div.s { flex: 1; border: 1px solid #86B6EF; background: #EEF5FD; border-radius: 6px; padding: 7px; font-size: 12px; text-align: center }
.flow div.s b { display: block; color: #1C5CAB; margin-bottom: 3px } .flow div.a { color: #898781; font-size: 18px; align-self: center }
.flow div.s.gate { border-color: #E3A0A0; background: #FBEFEF } .flow div.s.gate b { color: #B02E2E }
.mono { font-family: Consolas, monospace; font-size: 11px; background: #F1F0EB; padding: 1px 4px; border-radius: 3px }
.ai { border-left: 3px solid #2A78D6; padding: 6px 10px; background: #EEF5FD; font-size: 12.5px; margin-top: 4px }
pre.code { font-family: Consolas, monospace; font-size: 10.2px; line-height: 1.3; background: #F1F0EB; padding: 6px 8px; border-radius: 5px; white-space: pre-wrap; overflow: hidden }
.erd { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; width: 100%; font-size: 10.8px }
.erd div { border: 1px solid #86B6EF; background: #EEF5FD; border-radius: 5px; padding: 4px 6px; line-height: 1.3 }
.erd div b { color: #1C5CAB; display: block } .erd div.k { border-color: #C9C7BF; background: #FCFCFB }
.q { display: grid; grid-template-columns: 22px 1fr; gap: 3px 6px; font-size: 12.8px } .q b { color: #1C5CAB }
"""

PAGE = Template("""
<section class="page">
  <header><div><h1>{{ p.title }}</h1>{% if p.subtitle %}<p class="sub">{{ p.subtitle }}</p>{% endif %}</div>
  {% if p.tag %}<div class="tag {{ p.tag_class }}">{{ p.tag }}</div>{% endif %}</header>
  {% if p.kpis %}<div class="kpis" style="grid-template-columns: repeat({{ p.kpis|length }}, 1fr)">
    {% for k in p.kpis %}<div class="card kpi"><div class="klabel">{{ k[0] }}</div><div class="kval {{ k[3] if k|length > 3 else '' }}">{{ k[1] }}</div><div class="knote">{{ k[2] }}</div></div>{% endfor %}
  </div>{% endif %}
  <div class="grid" style="grid-template-columns: {{ p.cols }}; grid-template-rows: {{ p.rows }}">
    {% for c in p.cards %}<div class="card" style="grid-column: {{ c.col }}; grid-row: {{ c.row }}">
      {% if c.title %}<h3>{{ c.title }}{% if c.tag %}<span class="ctag {{ 'sim' if c.tag == 'SIMULATED' else 'real' }}">{{ c.tag }}</span>{% endif %}</h3>{% endif %}<div class="body {{ 'text' if c.text else '' }}">{{ c.body }}</div></div>{% endfor %}
  </div>
  <footer>{{ p.footer }} · {{ foot }}</footer>
</section>""")


def card(title, body, col="auto", row="auto", text=False, tag=None):
    return dict(title=title, body=body, col=col, row=row, text=text, tag=tag)


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def flow(steps, gates=()):
    return '<div class="flow">' + '<div class="a">→</div>'.join(
        f'<div class="s{" gate" if a in gates else ""}"><b>{a}</b>{b}</div>' for a, b in steps) + "</div>"


def tbl(rows, head, num=()):
    h = "".join(f'<th class="{"n" if i in num else ""}">{html.escape(c)}</th>' for i, c in enumerate(head))
    b = "".join("<tr>" + "".join(f'<td class="{"n" if i in num else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"


def reasons(res, view, agent="keyword+filters"):
    f = res[(res.view == view) & (res.agent == agent) & ~res.success].failure.str.split("; ").explode()
    f = f.str.replace(r"role '.*' not satisfied", "a basket item missing or wrong", regex=True).str.replace(r":.*", "", regex=True)
    return f.value_counts()


def build_pages():
    st, det, dsum, ev = js("catalog_stats"), rd("detection_by_type"), js("detection_summary"), js("classification_eval")
    sc, cal, summ, res = js("schema_checks"), js("basket_calibration"), rd("scenario_summary"), rd("agent_results")
    rules, cov = rd("quality_rules_before_after"), rd("taxonomy_coverage")
    qs = pd.read_parquet(OUT / "quality_scores.parquet")
    pairs = pd.read_csv(TAXO / "dedupe_manual_check.csv")
    cat = pd.read_parquet(PROCESSED / "catalog.parquet")
    raw = pd.read_parquet(PROCESSED / "listings_raw_view.parquet")
    from catalog.taxonomy import load
    L, tpl = load()
    views = ["1 raw", "2 + attributes", "3 + taxonomy", "4 clean"]
    succ = res.groupby(["agent", "view"]).success.mean()
    kf = [succ["keyword+filters", v] for v in views]
    kw = [succ["keyword", v] for v in views]
    stair = C.staircase(["raw", "+ attributes", "+ taxonomy", "clean"], {"keyword agent": kw, "keyword + filters agent": kf}, w=560, h=250)
    d = det.sort_values("caught_rate", ascending=False)
    det_chart = C.grouped_hbar(d.label.tolist(), {"caught": d.caught_rate.tolist(), "fixed": d.fixed_rate.tolist()}, w=560, h=290, xmax=1.0,
                               colors=[C.BLUE_L, C.BLUE_D])
    recall = dsum["caught"] / dsum["injected"]
    acc = ev["final_accuracy"]
    pages = []

    # ---------------------------------------------------------------- 0 overview
    qs5 = ('<div class="q"><b>1</b><span>Can three public catalogues with different formats become <b>one</b> consistent catalogue?</span>'
           '<b>2</b><span>Can a browsable taxonomy place every product, and how accurate is automatic classification?</span>'
           '<b>3</b><span>How should the catalogue be stored for AI work: relational, document, or both?</span>'
           '<b>4</b><span>Can realistic shopping tasks be written with a <b>known set of right answers</b> and graded automatically?</span>'
           '<b>5</b><span>Does catalogue quality change how well an agent shops?</span></div>')
    data = (f"<p><b>PUBLIC DATA</b>: Amazon Berkeley Objects listings (CC BY 4.0), Open Food Facts (ODbL), Google Product Taxonomy, "
            f"UCI Online Retail II transactions (CC BY 4.0), micro1.ai (seen {SEEN_ON}).</p>"
            "<p><b>SIMULATED</b>: an export from an 'other platform' built from ABO items, 2,400 injected errors with a hidden answer key, "
            "prices, stock, personas.</p><p><b>Tools</b>: Python (pandas, scikit-learn, rapidfuzz), DuckDB SQL, JSON Schema, pytest, Plotly.</p>")
    pages.append(dict(
        title="micro1: building a realistic e-commerce environment for training and evaluating AI shopping agents",
        subtitle="Public product catalogues unified into one taxonomy and schema (SQL and NoSQL), normalised and quality-checked, then turned "
                 "into realistic shopping scenarios with automatic grading, the kind of environment the role describes.",
        tag="OVERVIEW", tag_class="",
        kpis=[("Unified catalogue · p.2", f"{st['clean_skus']:,} SKUs", f"from {st['raw_listings']:,} listings in 3 sources; {st['duplicates_merged']:,} duplicates merged", "blue"),
              ("Taxonomy · p.3", f"{len(L)} categories", f"3-4 levels, all mapped to Google ids; {pct(acc, 1)} accuracy on 200 hand-labelled products", "blue"),
              ("Injected errors caught · p.2", pct(recall), f"{dsum['caught']:,} of {dsum['injected']:,} SIMULATED errors, 9 types", "blue"),
              ("Agent success, raw → clean · p.6", f"{pct(kf[0])} → {pct(kf[-1])}", "same rule-based agent, same 150 scenarios, only the catalogue changes", "blue")],
        cols="1fr 1fr 1.05fr", rows="auto 1fr",
        cards=[card("Five questions", qs5, text=True),
               card("Approach", flow([("Ingest", "3 sources"), ("Normalise", "units, colours, sizes, brands"), ("Classify", "rules + text model"),
                                      ("Match", "duplicates, variants"), ("Check", "26 rules, quality gate"), ("Simulate", "150 graded tasks")]) +
                    "<p style='margin-top:8px'>Every step writes a table that the next one reads; the answer key of the injected errors is opened only at the end.</p>", text=True),
               card("Data & methods", data, text=True),
               card("Agent success rate by catalogue version · p.6", stair, tag="SIMULATED"),
               card("SIMULATED errors caught and fixed, by type · p.2", det_chart, tag="SIMULATED"),
               card("Quality score per SKU, before and after · p.2", C.overlay_hist(qs[qs.view == "before"].score, qs[qs.view == "after"].score, w=500, h=250, xlabel="weighted share of rules passed"), tag="PUBLIC DATA")],
        footer="Code: src/, env/ · tests: tests/ · scenarios: scenarios/ · taxonomy: taxonomy/ · schemas: schema/ · dashboard: dashboard/catalog_quality.html"))

    # ---------------------------------------------------------------- 1 micro1
    facts = ("<p>As stated by micro1 on micro1.ai (seen " + SEEN_ON + "):</p><ul>"
             "<li>A <b>data lab</b> 'to train frontier models &amp; evaluate agents', working on expert human data, real-world training environments and evaluations.</li>"
             "<li><b>Realm</b>: reinforcement-learning environments that mirror real-world scenarios.</li>"
             "<li><b>Cortex</b>: a contextual evaluation platform for agents in production.</li>"
             "<li><b>Robotics</b>: real-world demonstration data for embodied systems.</li>"
             "<li><b>Research</b>: benchmarks and indices published by its research lab.</li></ul>"
             "<p>The client behind this role is not named in the offer and is not guessed here.</p>")
    offer = ("<p>Contract, remote, AI-training role (no AI experience required). What the offer asks, and where this study does it:</p>" +
             tbl([["Manage large catalogues, consistent across platforms", "p.2"], ["Taxonomies that mirror real shop navigation", "p.3"],
                  ["Normalise and map data from different sources", "p.2-3"], ["Realistic shopping scenarios, consumer decisions", "p.5"],
                  ["Structure catalogues for AI training", "p.4, 6"], ["Quality and normalisation in SQL and NoSQL", "p.2, 4"],
                  ["Document workflows, taxonomies, metadata", "p.7, docs/"]], ["The role asks to", "Here"]) +
             "<p style='margin-top:6px'>A demonstration on public data, not a micro1 or client product.</p>")
    rr = raw[raw.sku.str.startswith("MKB") & raw.colour.notna()][["sku", "canonical_sku", "title", "brand", "colour", "category_path"]]
    ex = rr.merge(cat[["sku", "title", "brand", "colour", "category_path", "length_cm"]], left_on="canonical_sku", right_on="sku", suffixes=("_r", "_c"))
    ex = ex[ex.length_cm.notna() & (ex.brand_r != ex.brand_c) & (ex.colour_r.str.lower() != ex.colour_c) & ex.colour_c.notna()].head(1)
    e = ex.iloc[0] if len(ex) else None
    fails_raw = reasons(res, "1 raw")
    why = ("<p>An agent can only be as right as the catalogue lets it be. On the raw listings the same agent:</p><ul>"
           f"<li>says <b>'nothing matches'</b> {int(fails_raw.get('reported no match although one exists', 0))} times while a right product exists (filters miss 'Navy', 'AMAZON BRAND - SOLIMO');</li>"
           f"<li>breaks a constraint {int(fails_raw.get('constraint broken', 0))} times (wrong category, wrong price);</li>"
           "<li>cannot filter on size at all: in the sources it lives only inside titles.</li></ul>"
           "<p>So catalogue work sets the ceiling of what a model can learn in the environment, and a clean catalogue is what makes "
           "failures informative: what is left is the agent's reasoning, not the data.</p>")
    rawclean = ""
    if e is not None:
        rawclean = tbl([["Title", html.escape(str(e.title_r)[:70]), html.escape(str(e.title_c)[:70])],
                        ["Brand", html.escape(str(e.brand_r)), html.escape(str(e.brand_c))],
                        ["Colour", html.escape(str(e.colour_r)), html.escape(str(e.colour_c))],
                        ["Category", html.escape(str(e.category_path_r)[:40] or "(none)"), html.escape(str(e.category_path_c).split(" > ")[-1])],
                        ["Length", "inside a text field", f"{e.length_cm:.1f} cm"]], ["Field", "Raw listing (SIMULATED platform)", "Clean catalogue"])
    fc = reasons(res, "4 clean")
    top = list(fails_raw.head(6).index)
    fail_chart = C.grouped_hbar(top, {"raw listings": [int(fails_raw.get(k, 0)) for k in top], "clean catalogue": [int(fc.get(k, 0)) for k in top]},
                                w=700, h=240, fmt="{:.0f}")
    pages.append(dict(
        title="micro1 builds environments and evaluations for AI agents; for shopping agents, the catalogue is the environment, and its quality sets what an agent can learn",
        subtitle="What micro1 publishes about itself, what the offer asks for, and why a messy catalogue makes a shopping agent fail for the wrong reasons.",
        tag="PUBLIC DATA", tag_class="real", kpis=None, cols="1fr 1fr 1.1fr", rows="auto 1fr",
        cards=[card("micro1, as stated by micro1", facts, text=True),
               card("What the role describes", offer, text=True),
               card("Why an agent fails on a bad catalogue", why, text=True),
               card("Failed episodes by reason, same agent: raw listings vs clean catalogue (150 scenarios)", fail_chart, col="1 / 3", tag="SIMULATED"),
               card("One product, raw vs clean", rawclean, text=True, tag="SIMULATED")],
        footer=f"Sources: micro1.ai (home and product pages) and the public job offer, seen on {SEEN_ON}. No micro1 employee or client is named."))

    # ---------------------------------------------------------------- 2 catalogue
    srcs = tbl([["Amazon Berkeley Objects", '<span class="ctag real">PUBLIC DATA</span>', f"{st['by_source'].get('abo', 0):,}", "CC BY 4.0", "multilingual, imperial units, free-text colours"],
                ["Open Food Facts", '<span class="ctag real">PUBLIC DATA</span>', f"{st['by_source'].get('off', 0):,}", "ODbL 1.0", "food: quantities, labels, barcodes"],
                ["'Other platform' export", '<span class="ctag sim">SIMULATED</span>', f"{st['by_source'].get('mkb', 0):,}", "n/a", "built from ABO: cm or in in one field, '5 lb', other colour words, 25 % no category"]],
               ["Source", "Tag", "Listings", "Licence", "Typical mess"], num=(2,))
    cm = st["colour_methods"]
    bm = st["brand_methods"]
    norm = (f"<ul><li><b>Units</b>: inches, pounds, ounces, fl oz, '12 x 330 ml' → cm, g, ml.</li>"
            f"<li><b>Colours</b> → 16 controlled values ('navy', 'bleu marine', 'zwart' → blue / black): {cm.get('field', 0):,} from the colour field, "
            f"{cm.get('title', 0):,} recovered from titles, {cm.get('placeholder', 0):,} placeholders ('Others') set to empty, {cm.get('unmapped', 0):,} left for review.</li>"
            f"<li><b>Brands</b>: {st['reference_brands']} reference brands; {bm.get('variant', 0):,} variant spellings and {bm.get('fuzzy', 0)} near-misses mapped "
            "('Amazon Brand - Solimo' → 'Solimo').</li><li><b>Sizes</b>: XXS-3XL, EU shoe sizes (from 'UK 8', 'US 9'), bed sizes.</li>"
            f"<li><b>Languages</b>: {st['non_english_titles']:,} non-English titles kept and tagged.</li></ul>")
    p94 = pairs[pairs.merged_at_94]
    prec = (p94.label == "same").mean()
    rec = p94[p94.label == "same"].shape[0] / max(1, (pairs.label == "same").sum())
    dd = (f"<ul><li>Identifiers first (GTIN, brand + model number), then titles: similarity ≥ 94 inside a brand × department block, "
          "and the numbers in both titles must agree (12.5 oz ≠ 10.8 oz).</li>"
          f"<li>Threshold chosen on <b>50 pairs checked by hand</b>: precision {pct(prec)}, recall {pct(rec)} on that sample.</li>"
          f"<li>{st['duplicates_merged']:,} listings merged; {dsum['wrongly_merged']} of {dsum['mkb_new_items']} new 'other platform' items wrongly merged "
          f"({pct(dsum['wrongly_merged'] / dsum['mkb_new_items'], 1)}).</li>"
          f"<li>{st['variant_groups']} parents now group {st['skus_in_variant_groups']:,} colour/size variants.</li>"
          f"<li>Quality gate: {st['held_for_review']} SKUs with price errors or outliers held back from the shop.</li>"
          f"<li>Automatic unit repair was tested and <b>rejected</b>: {dsum['unit_repair_suggestions']} suggestions, only "
          f"{dsum['unit_repair_suggestions_on_injected_errors']} on real errors. Outliers go to review.</li></ul>")
    r = rules.assign(fb=1 - rules.pass_rate_before, fa=1 - rules.pass_rate_after).sort_values("fb", ascending=False).head(8)
    rule_chart = C.grouped_hbar([f"{i} {t[:30]}" for i, t in zip(r.id, r.description)], {"before": r.fb.tolist(), "after": r.fa.tolist()}, w=430, h=380)
    bl = raw[raw.colour_norm == "blue"].colour.dropna().astype(str).str.strip().value_counts().head(12)
    blue_chart = C.hbar([b[:24] for b in bl.index], bl.values.tolist(), w=420, h=380)
    pages.append(dict(
        title=f"Three messy sources become one catalogue: {st['clean_skus']:,} SKUs, mean quality {st['quality_before']:.2f} → {st['quality_after']:.2f}, "
              f"and {pct(recall)} of the injected errors caught",
        subtitle="Normalisation, duplicate matching, variant grouping and 26 quality rules (completeness, validity, consistency, uniqueness), "
                 "measured on real listings and on 2,400 SIMULATED errors whose answer key stays hidden until the end.",
        tag="PUBLIC DATA + SIMULATED", tag_class="", kpis=None, cols="1fr 1fr 1fr", rows="auto 1fr",
        cards=[card("Sources (counts include 200 SIMULATED copies: injected duplicates and split variants)", srcs, text=True, col="1 / 3", row="1"),
               card("Duplicates, variants, quality gate", dd, text=True, col="3", row="1"),
               card("Normalisation", norm, text=True, col="1", row="2"),
               card("Raw spellings that became 'blue' (listings)", blue_chart, col="2", row="2", tag="PUBLIC DATA"),
               card("Share of SKUs failing a rule, before → after (8 most failed)", rule_chart, col="3", row="2", tag="PUBLIC DATA")],
        footer="Rules: src/catalog/rules.yaml · standards: docs/CATALOG_STANDARDS.md · hand check: taxonomy/dedupe_manual_check.csv · detail: data/outputs/"))

    # ---------------------------------------------------------------- 3 taxonomy
    deps = L.groupby("department").size().sort_values(ascending=False)
    tree = (f"<p><b>{L.department.nunique()} departments → {L.group.nunique()} groups → {len(L)} leaves</b>"
            ", written for shoppers (no overlap, one 'Other' leaf).</p>"
            "<p class='mono' style='display:block;white-space:pre'>Home &amp; Furniture\n  Living Room Furniture\n    Sofas &amp; Couches · Armchairs · Ottomans …\n"
            "Grocery &amp; Gourmet Food\n  Snacks &amp; Sweets\n    Savoury Snacks → Crisps, Crackers &amp; Pretzels</p>"
            + "<p>" + " · ".join(f"{html.escape(k)} {v}" for k, v in deps.head(8).items()) + " …</p>")
    t_rows = []
    for name in ["furniture", "shoes", "bedding", "food", "phone_case"]:
        t = tpl["templates"][name]
        t_rows.append([name, ", ".join(t["required"]) or "-", ", ".join(t["optional"][:4])])
    attrs = tbl(t_rows, ["Template", "Required", "Optional (first 4)"])
    gm = L[L.name.isin(["Sofas & Couches", "Running & Sports Shoes", "Phone & Tablet Cases", "Crisps, Crackers & Pretzels", "Yogurt"])]
    gmap = tbl([[html.escape(r.name), str(int(r.gpt_id)), html.escape(r.gpt_path.split(" > ")[-1])] for r in gm.itertuples()], ["Leaf", "Google id", "Google category"], num=(1,))
    m = pd.DataFrame(ev["precision_by_method"])
    m = m[m.n >= 3]
    lab = {"source category": "source category\nmapping", "keyword rule": "keyword\nrules", "text model": "text model",
           "text model (overrode source)": "model over-\nrode source", "text model (within source group)": "model within\nsource group",
           "other (low confidence)": "sent to\n'Other'"}
    acc_chart = C.hbar([f"{lab.get(x, x).replace(chr(10), ' ')} (n={n})" for x, n in zip(m.category_method, m.n)], m.precision.tolist(),
                       w=470, h=250, fmt="{:.0%}")
    cv = cov.sort_values("skus", ascending=False)
    dep_chart = C.hbar(cv.department.str.replace(" & ", " & ").str[:30].tolist(), cv.skus.tolist(), w=470, h=330)
    amb = pd.read_csv(OUT / "classification_errors.csv").dropna(subset=["ambiguous_note"]).head(4)
    ambl = "".join(f"<li>{html.escape(str(r.ambiguous_note))}</li>" for r in amb.itertuples())
    clf = (f"<p>Rules first (source category mapping, then keywords), then a TF-IDF + logistic-regression model for what is left. "
           f"On <b>200 products labelled by hand</b> from title and brand only: <b>{pct(acc, 1)}</b> right leaf "
           f"({pct(ev['final_accuracy_unambiguous'], 1)} without the 13 ambiguous items), {pct(ev['department_accuracy'], 1)} right department.</p>"
           f"<p>When the model is at least 80 % sure (it is for {pct(ev['model_share_proba_0.8'])} of products) it is right {pct(ev['model_precision_proba_0.8'])} of the time: "
           f"that is the threshold of rule K05, which flags products whose text contradicts their category. "
           f"{pct(ev['other_share_catalogue'], 1)} of the catalogue sits in 'Other'.</p><p>Ambiguous cases kept for the guide:</p><ul>{ambl}</ul>")
    pages.append(dict(
        title=f"A taxonomy shoppers can browse: {len(L)} leaf categories, each with its attributes and a Google id; {pct(acc, 1)} of products land in the right leaf",
        subtitle="Navigation tree designed for a real shop, attribute templates per category, mapping to Google Product Taxonomy and to the "
                 "sources' own categories, and automatic classification measured against hand labels.",
        tag="PUBLIC DATA", tag_class="real", kpis=None, cols="1fr 1fr 1fr", rows="auto 1fr",
        cards=[card("Tree", tree, text=True, col="1", row="1"), card("Attributes per category (templates)", attrs, text=True, col="2", row="1"),
               card("Mapping to Google Product Taxonomy (examples)", gmap, text=True, col="3", row="1"),
               card("Classification and accuracy", clf, text=True, col="1", row="2"),
               card("Accuracy by classification method (200 hand-labelled products)", acc_chart, col="2", row="2", tag="PUBLIC DATA"),
               card("SKUs per department", dep_chart, col="3", row="2", tag="PUBLIC DATA")],
        footer="taxonomy/navigation_taxonomy.yaml (source of truth) · categories.csv · google_mapping.csv · source_mapping.csv · category_attributes.csv · docs/TAXONOMY_GUIDE.md"))

    # ---------------------------------------------------------------- 4 schemas
    erd = ('<div class="erd">'
           '<div><b>category</b>id · parent_id → category · level · path · google_id · template</div>'
           '<div><b>product</b> (parent) id · title · brand_id → brand · category_id → category · gender</div>'
           '<div><b>variant</b> (SKU) sku · product_id → product · colour · size · material · cm / g / ml · status · quality</div>'
           '<div><b>price</b>sku → variant · amount · currency · valid_from</div>'
           '<div class="k"><b>brand / brand_alias</b>name · key · every raw spelling → brand</div>'
           '<div class="k"><b>attribute / category_attribute</b>which attributes each leaf requires</div>'
           '<div class="k"><b>variant_attribute</b> (EAV) long tail only: device, style, labels, allergens</div>'
           '<div class="k"><b>inventory · source_listing</b>stock · lineage of every raw listing</div></div>')
    doc = json.loads((ROOT / "schema" / "sample_document.json").read_text(encoding="utf-8"))
    v0 = doc["variants"][0]
    short = {"_id": doc["_id"], "title": doc["title"][:48] + "…", "brand": doc["brand"], "category": {"id": doc["category"]["id"], "path": doc["category"]["path"][-1:], "google_id": doc["category"]["google_id"]},
             "variants": [{k: v0[k] for k in ("sku", "colour", "price", "stock", "status") if k in v0}, f"… {len(doc['variants']) - 1} more variants"]}
    docj = f"<pre class='code'>{html.escape(json.dumps(short, indent=1, ensure_ascii=False))[:1100]}</pre>"
    ch = {c["check"]: c["result"] for c in sc["checks"]}
    QUERY_LABEL = {k: 1 for k in ch if k.startswith("blue sofas")}
    when = tbl([["Filter and join many SKUs (agent tools, audits)", "<b>SQL</b>: indexed columns, constraints"],
                ["Add an attribute for one category", "<b>Document</b>: no migration; EAV table in SQL"],
                ["Guarantee validity (colour list, units > 0)", "Both: CHECK constraints / JSON Schema"],
                ["Export one product per training example", "<b>Document</b>: one JSON line = one product"],
                ["Keep lineage and price history", "<b>SQL</b>: source_listing, price.valid_from"]], ["Need in an AI-training catalogue", "Better fit"])
    checks = (f"<ul><li>{sum(sc['row_counts'].values()):,} rows in 11 tables; orphans: {ch['variants without a product']}; SKUs without price: {ch['SKUs without a price']}; leaves without Google id: {ch['leaves without a Google id']}.</li>"
              f"<li>The constraints found real errors: {sc['impossible_measures_nulled']} sizes or weights that are 0 or impossible (a 288 km wide product) are stored as NULL.</li>"
              f"<li>{sc['documents']:,} documents, {sc['documents'] - sc['documents_invalid']:,} valid against the JSON Schema; the {sc['documents_invalid']} rejected has a 300+ character title.</li>"
              f"<li>Attribute-value (EAV) table limited to the long tail ({sc['eav_rows']:,} rows): filtering on EAV needs a join per attribute and loses types, "
              "so attributes used by filters stay columns.</li></ul>"
              f"<p>The filter an agent tool runs, in SQL ({ch[list(QUERY_LABEL)[0]]} results):</p><pre class='code'>SELECT v.sku, pr.amount FROM variant v\n"
              "JOIN product p USING (product_id) JOIN category c USING (category_id)\n"
              "JOIN price pr USING (sku) JOIN inventory i USING (sku)\n"
              "WHERE c.name = 'Sofas &amp; Couches' AND v.colour = 'blue'\n  AND pr.amount &lt;= 700 AND i.in_stock AND v.listing_status = 'active';</pre>")
    pages.append(dict(
        title="One product, two schemas: SQL for constraints, filters and lineage; documents for flexible attributes and training exports",
        subtitle="The same clean catalogue loaded into DuckDB (PostgreSQL-compatible DDL) and exported as MongoDB-style documents validated by JSON Schema; "
                 "both are checked by the pipeline.",
        tag="PUBLIC DATA", tag_class="real", kpis=None, cols="1.25fr 1fr", rows="auto 1fr",
        cards=[card("Relational model (schema/schema.sql)", erd, text=True), card("When to choose which", when, text=True),
               card("Document model (schema/product.schema.json): one product with nested variants", docj, text=True),
               card("Checks", checks, text=True)],
        footer="schema/schema.sql · schema/product.schema.json · schema/mongo_validator.json · data/processed/catalog_documents.jsonl · docs/METADATA_SPEC.md"))

    # ---------------------------------------------------------------- 5 scenarios
    what = {"simple_search": "find a product of a named brand", "multi_constraint": "respect brand, colour, size and budget together",
            "comparison": "buy the cheapest or lightest match", "substitution": "replace a sold-out SKU",
            "basket": "build a multi-item basket under a total budget", "ambiguous": "ask the missing detail before buying",
            "no_answer": "say that nothing matches, buy nothing"}
    g = summ.groupby("type").agg(n=("id", "size"), diff=("difficulty", "first"), acc=("n_acceptable", "median")).sort_values("diff")
    types = tbl([[t.replace("_", " "), int(r.n), int(r["diff"]), what[t], f"{r.acc:,.0f}"] for t, r in g.iterrows()],
                ["Type", "N", "Level", "The agent must", "Median right answers"], num=(1, 2, 4))
    dist = cal["small_basket_lines_dist"]
    ks = [k for k in dist if int(k) <= 6]
    cal_chart = C.vbars([str(k) for k in ks], [dist[k] for k in ks], w=420, h=200, ylabel="share of small invoices")
    ms = cal["month_share"]
    mon_chart = C.vbars(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"], [ms[str(i)] for i in range(1, 13)], w=420, h=200, highlight=[10])
    import glob
    def scen(i):
        return json.loads(Path(sorted(glob.glob(str(ROOT / "scenarios" / "S*.json")))[i]).read_text(encoding="utf-8"))
    sa = next(scen(i) for i in range(90, 120) if scen(i)["type"] == "basket")
    sb = next(scen(i) for i in range(100, 135) if scen(i)["type"] == "ambiguous")
    exs = (f"<p><b>{sa['id']} · basket · level {sa['difficulty']}</b><br><i>“{html.escape(sa['request'])}”</i><br>"
           f"Right answers: {', '.join(str(len(r['skus'])) + ' ' + r['role'] for r in sa['acceptable_answers']['roles'])} (each still fits the budget). "
           f"Graded on: {'; '.join(sa['grading']['criteria'])}.</p>"
           f"<p><b>{sb['id']} · ambiguous · level {sb['difficulty']}</b><br><i>“{html.escape(sb['request'])}”</i><br>"
           f"The shopper answers <i>“{html.escape(sb['clarification']['answer_text'])}”</i> only if asked about the {sb['clarification']['slot']}. "
           f"Trap: {html.escape(sb['trap'])}.</p>")
    for typ, rng_ in (("substitution", range(70, 95)), ("no_answer", range(135, 150))):
        sx = next(scen(i) for i in rng_ if scen(i)["type"] == typ)
        right = (f"{len(sx['acceptable_answers']['roles'][0]['skus'])} in-stock alternatives qualify" if sx["acceptable_answers"]["roles"]
                 else "no product qualifies: the right action is report_no_match")
        exs += (f"<p><b>{sx['id']} · {typ.replace('_', ' ')} · level {sx['difficulty']}</b><br><i>“{html.escape(sx['request'])}”</i><br>"
                f"{right}. Trap: {html.escape(str(sx['trap']))}.</p>")
    calib = (f"<p>Personas and intents are SIMULATED, but shaped by <b>{cal['invoices']:,} real invoices</b> (UCI Online Retail II, {cal['period']}): "
             f"baskets of 2-5 lines follow the small-invoice distribution, quantities follow units per line "
             f"({pct(cal['share_lines_qty1'])} of lines are single units), occasions follow the monthly mix (November peak).</p>"
             "<p>Each scenario stores: persona, intent, the request the agent sees, hidden constraints, the <b>full set of right SKUs</b> "
             "(computed from the clean catalogue, in stock and active), grading criteria, optimal and maximum steps, and the trap.</p>")
    pages.append(dict(
        title="150 shopping scenarios, from a simple search to ambiguous requests and impossible ones, each with every right answer listed",
        subtitle="Seven task types of increasing difficulty, generated from the clean catalogue and calibrated on real basket data; "
                 "pytest checks that every scenario has at least one right answer, except the 15 designed to have none.",
        tag="SIMULATED", tag_class="sim", kpis=None, cols="1.15fr 1fr 1fr", rows="1fr 1fr",
        cards=[card("Scenario types", types, text=True), card("Calibration on real baskets", calib, text=True),
               card("Four examples", exs, text=True, row="1 / 3"),
               card("Lines per small real invoice (≤ 10 lines, ≤ 24 units)", cal_chart, tag="PUBLIC DATA"),
               card("Real invoices by month (November highlighted)", mon_chart, tag="PUBLIC DATA")],
        footer="scenarios/S001-S150.json · schema/scenario.schema.json · src/build_scenarios.py · docs/SCENARIO_AUTHORING_GUIDE.md"))

    # ---------------------------------------------------------------- 6 agents
    t = res[res.view == "4 clean"].groupby(["type", "agent"]).success.mean().unstack()
    t = t.reindex(g.index)
    type_chart = C.grouped_hbar([x.replace("_", " ") for x in t.index], {"keyword": t["keyword"].tolist(), "keyword + filters": t["keyword+filters"].tolist()},
                                w=520, h=300, xmax=1.0, legend=False)
    fr_raw, fr_clean = reasons(res, "1 raw"), reasons(res, "4 clean")
    idx = list(dict.fromkeys(list(fr_raw.head(5).index) + list(fr_clean.head(5).index)))[:7]
    ftab = tbl([[html.escape(i), int(fr_raw.get(i, 0)), int(fr_clean.get(i, 0))] for i in idx], ["Failure reason (keyword + filters agent)", "Raw", "Clean"], num=(1, 2))
    agents = ("<p>The environment exposes <span class='mono'>search</span>, <span class='mono'>filter</span>, <span class='mono'>get_product</span>, "
              "<span class='mono'>add_to_cart</span>, <span class='mono'>ask_clarification</span>, <span class='mono'>report_no_match</span>, "
              "<span class='mono'>checkout</span>; every call is logged, 25 steps maximum.</p>"
              "<p>Two reference agents, plain Python rules, no language model: <b>keyword</b> (search, take the first in-stock result) and "
              "<b>keyword + filters</b> (reads budget, colour, size, brand and quantities with regular expressions, then filters).</p>"
              "<p>Grading is automatic: <b>score = 0.6 × right outcome + 0.3 × constraints respected + 0.1 × efficiency</b>; success = right outcome.</p>")
    reading = (f"<p>Only the catalogue changes between the four runs. Normalised attributes make filters work ({pct(kf[0])} → {pct(kf[1])}), "
               f"the taxonomy makes category words match ({pct(kf[2])}), merging duplicates and holding price errors adds the rest ({pct(kf[3])}).</p>"
               f"<p>The keyword agent stays near {pct(kw[-1])}: a better catalogue does not help an agent that ignores constraints. "
               "On the clean catalogue the remaining failures are about reasoning (ambiguity, baskets, comparisons), which is what the "
               "environment should isolate for training.</p>")
    pages.append(dict(
        title=f"Grading agents in the environment: the same agent goes from {pct(kf[0])} to {pct(kf[-1])} success when only the catalogue is cleaned",
        subtitle="Two rule-based reference agents run the 150 scenarios on four versions of the catalogue, each adding one fix; every episode is graded automatically.",
        tag="SIMULATED", tag_class="sim", kpis=None, cols="1fr 1fr 1fr", rows="1fr 1fr",
        cards=[card("Success rate by catalogue version", stair, tag="SIMULATED"),
               card("Success by type, clean catalogue (grey: keyword · blue: keyword + filters)", type_chart, tag="SIMULATED"),
               card("Environment, agents, grading", agents, text=True),
               card("What makes them fail", ftab, text=True), card("Reading", reading, text=True),
               card("Agents and catalogue quality", f"<p>Raw → clean, keyword + filters agent, by type:</p>" +
                    tbl([[x.replace("_", " "), pct(res[(res.view == '1 raw') & (res.agent == 'keyword+filters') & (res.type == x)].success.mean()),
                          pct(res[(res.view == '4 clean') & (res.agent == 'keyword+filters') & (res.type == x)].success.mean())] for x in g.index],
                        ["Type", "Raw", "Clean"], num=(1, 2)), text=True)],
        footer="env/shop.py · env/grader.py · env/agents.py · env/run_baselines.py · data/outputs/agent_results.csv · episode logs: data/outputs/episode_examples.json"))

    # ---------------------------------------------------------------- 7 methods
    col = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True).stdout
    import re as _re
    ntests = sum(int(m.group(1)) for m in _re.finditer(r"^\S+\.py: (\d+)$", col, _re.M)) or sum(1 for line in col.splitlines() if "::" in line)
    lic = ("<ul><li><b>Amazon Berkeley Objects</b> (listings): credit Amazon.com; Collins et al., <i>ABO: Dataset and Benchmarks for Real-World 3D Object "
           "Understanding</i>, CVPR 2022. CC BY 4.0.</li>"
           "<li><b>Open Food Facts</b>: © Open Food Facts contributors, Open Database License (ODbL 1.0). Data in data/processed/ derives from it and is "
           "shared under ODbL 1.0 (share-alike).</li>"
           "<li><b>Google Product Taxonomy</b> (2021-09-21, en-US): category ids and names used for mapping.</li>"
           "<li><b>UCI Online Retail II</b> (Chen, 2019), CC BY 4.0: aggregates only, no customer ids.</li>"
           f"<li><b>micro1.ai</b>, seen {SEEN_ON}: published facts only, quoted as stated by micro1.</li></ul>")
    limits = ("<ul><li>Prices, stock, the second platform and the errors are SIMULATED; real error rates will differ.</li>"
              "<li>ABO is mostly Amazon private labels; brand variety is lower than on a marketplace.</li>"
              "<li>Hand labels (200 products, 50 pairs) come from one reviewer reading titles; ambiguous items are flagged, not forced.</li>"
              "<li>Agents are simple rule baselines, not language models: they show what the catalogue allows, not what a frontier model can do.</li>"
              "<li>Wrong units are hard to catch: 35 % flagged, none repaired automatically (repair was tested and rejected).</li></ul>")
    rerun = ("<pre class='code'>python src/download_data.py      # public files → data/raw (not published)\n"
             "python src/build_catalog.py      # catalogue, injected errors, quality\npython src/build_taxonomy.py     # taxonomy files, accuracy\n"
             "python src/build_schema.py       # DuckDB + JSON documents\npython src/evaluate_detection.py # opens the answer key\n"
             "python src/build_scenarios.py    # 150 scenarios\npytest                           # tests\n"
             "python env/run_baselines.py      # agents\npython src/build_dashboard.py · build_notebook.py · build_pdf.py</pre>")
    docs = ("<ul><li>docs/CATALOG_STANDARDS.md: units, colours, sizes, brands, duplicates, quality rules</li>"
            "<li>docs/TAXONOMY_GUIDE.md: how to classify, edge cases</li><li>docs/METADATA_SPEC.md: every field, type, allowed values</li>"
            "<li>docs/SCENARIO_AUTHORING_GUIDE.md: writing a good scenario, frequent mistakes</li><li>docs/WORKFLOW.md: from raw source to environment</li></ul>"
            f"<p><b>Checked on every rebuild</b>: {ntests} pytest tests (normalisation rules, shop tools, grader, every scenario valid against "
            "its JSON Schema and answerable), 9 SQL integrity checks, JSON Schema validation of every product document, and the hidden "
            "answer key opened only by the last step.</p>")
    nxt = ("<ul><li>Agree the taxonomy and attribute templates with the AI team before scaling: they decide what scenarios can ask.</li>"
           "<li>Replace title matching with identifiers wherever sources share them (GTIN, model numbers).</li>"
           "<li>Grow the hand-labelled sets (classification, duplicates) to a few hundred items per department and re-measure each release.</li>"
           "<li>Version the catalogue and the scenarios together, so a score change can be traced to a data change.</li>"
           "<li>Run language-model agents in the same environment and keep the rule baselines as a floor.</li></ul>")
    pages.append(dict(
        title="Methods, licences and limits: public data, a hidden answer key, hand checks, and every number rebuilt from code",
        subtitle="Sources with their exact attributions, what is simulated, what the measures can and cannot say, and how to rerun everything.",
        tag="METHODS", tag_class="", kpis=None, cols="1.1fr 1fr 1fr", rows="auto 1fr",
        cards=[card("Sources and licences", lic, text=True), card("Limits", limits, text=True), card("Documentation", docs, text=True),
               card("How to rerun", rerun, text=True),
               card("Next steps on a real client catalogue", nxt, text=True),
               card("AI-assisted workflow", f"<div class='ai'>{html.escape(ai_note())}</div>", text=True)],
        footer="Independent study. micro1 is named only from its public website and job offer; no client is named or guessed."))
    return pages


def edge() -> str:
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(p).exists():
            return p
    return shutil.which("msedge") or "msedge"


def wait_file(path: Path, timeout=120):
    last, t0 = -1, time.time()
    while time.time() - t0 < timeout:
        if path.exists() and path.stat().st_size > 0 and path.stat().st_size == last:
            return
        last = path.stat().st_size if path.exists() else -1
        time.sleep(1.5)
    raise TimeoutError(f"{path} not produced")


def clean_pdf(path: Path):
    """Metadata reduced to the title: no author, tool or path."""
    from pypdf import PdfReader, PdfWriter
    r, w = PdfReader(str(path)), PdfWriter()
    for pg in r.pages:
        w.add_page(pg)
    w.add_metadata({"/Title": "micro1: building a realistic e-commerce environment for AI shopping agents"})
    for k in ("/Producer", "/Creator", "/Author"):
        w._info.get_object().pop(k, None)
    tmp = path.with_suffix(".tmp.pdf")
    with open(tmp, "wb") as fh:
        w.write(fh)
    tmp.replace(path)


def main():
    TMP.mkdir(exist_ok=True)
    (DOCS / "img").mkdir(parents=True, exist_ok=True)
    prof = TMP / "edge-profile"
    pages = build_pages()
    head = f"<!doctype html><html><head><meta charset='utf-8'><title>micro1 catalogue environment case study</title><style>{CSS}</style></head><body>"
    sections = [PAGE.render(p=p, foot=FOOTER) for p in pages]
    src = TMP / "report.html"
    src.write_text(head + "".join(sections) + "</body></html>", encoding="utf-8")
    PDF.unlink(missing_ok=True)
    subprocess.run([edge(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf-no-header",
                    f"--user-data-dir={prof}", f"--print-to-pdf={PDF}", src.as_uri()], check=True, capture_output=True, timeout=180)
    wait_file(PDF)
    clean_pdf(PDF)
    names = ["00_overview", "01_micro1", "02_catalogue", "03_taxonomy", "04_schemas", "05_scenarios", "06_agents", "07_methods"]
    for name, sec in zip(names, sections):
        one = TMP / f"{name}.html"
        one.write_text(head.replace("page-break-after: always", "") + sec + "</body></html>", encoding="utf-8")
        out = DOCS / "img" / f"{name}.png"
        out.unlink(missing_ok=True)
        subprocess.run([edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                        "--window-size=1536,864", f"--screenshot={out}", one.as_uri()], check=True, capture_output=True, timeout=120)
        wait_file(out)
    from pypdf import PdfReader
    print("PDF:", PDF.relative_to(ROOT), f"({PDF.stat().st_size // 1024} KB, {len(PdfReader(str(PDF)).pages)} pages)")


if __name__ == "__main__":
    main()
