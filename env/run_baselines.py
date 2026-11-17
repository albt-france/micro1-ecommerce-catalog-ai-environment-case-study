"""Run the two reference agents on the 150 scenarios, on four versions of the same catalogue, and grade every
episode automatically. The versions add one fix at a time, so the score gap shows what each fix is worth:
  1 raw            listings as the sources deliver them
  2 + attributes   brand, colour, size and material normalised
  3 + taxonomy     products placed in the navigation taxonomy
  4 clean          + duplicates merged, units repaired, price errors held back (the published catalogue)
Usage: python env/run_baselines.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "env"), str(ROOT / "src")]
from agents import KeywordAgent, KeywordFilterAgent  # noqa: E402
from grader import grade  # noqa: E402
from shop import Shop  # noqa: E402

OUT = ROOT / "data" / "outputs"
PROC = ROOT / "data" / "processed"
VIEWS = ["1 raw", "2 + attributes", "3 + taxonomy", "4 clean"]


def load_scenarios() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "scenarios").glob("S*.json"))]


def views() -> tuple[dict, pd.DataFrame]:
    cat = pd.read_parquet(PROC / "catalog.parquet")
    raw = pd.read_parquet(PROC / "listings_raw_view.parquet")
    base = ["sku", "title", "price", "in_stock", "description", "parent_id", "length_cm", "width_cm", "height_cm",
            "weight_g", "net_qty", "labels"]
    v1 = raw[base + ["brand", "colour", "size", "material", "category_path"]].copy()
    v2 = raw[base + ["category_path"]].assign(brand=raw.brand_norm, colour=raw.colour_norm, size=raw.size_norm,
                                              material=raw.material_norm)
    v3 = v2.assign(category_path=raw.category_path_norm)
    v4 = cat[cat.listing_status == "active"].copy()
    truth = raw[["sku", "canonical_sku"]].merge(cat.drop(columns=["sku"]).assign(canonical_sku=cat.sku), on="canonical_sku", how="left")
    truth = truth.set_index("sku")
    return dict(zip(VIEWS, [v1, v2, v3, v4])), truth


def main():
    t0 = time.time()
    scen = load_scenarios()
    vs, truth = views()
    rows, examples = [], []
    for vname, df in vs.items():
        shop = Shop(df)
        for agent in (KeywordAgent(), KeywordFilterAgent()):
            for s in scen:
                req = shop.reset(s)
                try:
                    agent.run(shop, req)
                    err = ""
                except RuntimeError as e:   # episode ended (step limit)
                    err = str(e)
                g = grade(shop.ep, s, truth)
                g.update(view=vname, agent=agent.name, agent_error=err)
                rows.append(g)
                if vname in ("1 raw", "4 clean") and agent.name == "keyword+filters" and s["id"] in ("S010", "S040", "S100", "S120"):
                    examples.append(dict(view=vname, scenario=s["id"], request=s["request"], grade=g,
                                         steps=[dict(n=st.n, tool=st.tool, args=st.args, results=st.result_size) for st in shop.ep.steps],
                                         cart=shop.ep.cart, questions=[q for _, q in shop.ep.questions], no_match=shop.ep.no_match))
        print(f"{vname}: done ({time.time() - t0:.0f}s)")
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "agent_results.csv", index=False)
    (OUT / "episode_examples.json").write_text(json.dumps(examples, indent=1, default=str), encoding="utf-8")
    summ = res.groupby(["agent", "view"]).agg(success=("success", "mean"), score=("score", "mean")).round(3)
    print(summ.to_string())
    print(res[res.view == "4 clean"].groupby(["agent", "type"]).success.mean().unstack().round(2).to_string())


if __name__ == "__main__":
    main()
