"""Final step: open the answer key of the SIMULATED errors (data/_hidden_truth.csv) and measure, per error type,
how many the pipeline caught (a rule flagged it, or a matching step linked it) and how many it fixed in the clean
catalogue. Run after build_catalog.py. Usage: python src/evaluate_detection.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog.enrich import BrandTable, clean_brand_text  # noqa: E402,F401
from catalog.normalize import norm_colour  # noqa: E402
from catalog.taxonomy import RuleClassifier  # noqa: E402
from config import HIDDEN, OUT, PROCESSED  # noqa: E402

LABEL = {"colour_nonstandard": "Colour word outside the list", "brand_misspelled": "Misspelled brand",
         "unit_mislabel": "Wrong unit (cm/in, kg/lb/oz)", "wrong_category": "Product in the wrong category",
         "missing_required": "Required attribute missing", "price_outlier": "Price error (x10, x100, /10, 0)",
         "duplicate_reworded": "Duplicate, reworded title", "split_variant": "Variant listed as separate product",
         "cross_source_duplicate": "Same product on 2 platforms"}
RULES = {"colour_nonstandard": ["V02", "K08"], "brand_misspelled": ["K04"], "unit_mislabel": ["K02"],
         "wrong_category": ["K05"], "missing_required": ["C05", "C07"], "price_outlier": ["V01", "K01"]}


def main():
    truth = pd.read_csv(HIDDEN)
    tr = pd.read_parquet(OUT / "pipeline_trace.parquet").set_index("sku")
    fb = pd.read_parquet(OUT / "flags_before.parquet").set_index("sku")
    fa = pd.read_parquet(OUT / "flags_after.parquet").set_index("sku")
    cat = pd.read_parquet(PROCESSED / "catalog.parquet").set_index("sku")
    rc = RuleClassifier()
    rows = []
    for r in truth.itertuples():
        s = r.sku
        canon = tr.at[s, "canonical_sku"]
        c = cat.loc[canon] if canon in cat.index else None
        flagged = bool(fb.loc[s, RULES[r.error_type]].fillna(0).max() > 0) if r.error_type in RULES else False
        fixed = False
        if r.error_type == "colour_nonstandard":
            want = norm_colour(r.original)
            fixed = c is not None and c.colour == want
            flagged = flagged or fixed
        elif r.error_type == "brand_misspelled":
            fixed = c is not None and isinstance(c.brand, str) and tr.at[s, "brand"] == tr.loc[tr.brand_raw == r.original, "brand"].mode().iloc[0]
            flagged = flagged or fixed
        elif r.error_type == "unit_mislabel":
            fixed = False   # values are not repaired automatically (see unit_repair_suggestions below)
        elif r.error_type == "wrong_category":
            src = "off" if s.startswith("OFF") else "abo"
            want, _ = rc.classify(src, r.original, None, tr.at[s, "title_clean"])
            fixed = c is not None and c.category_id == want
            flagged = flagged or tr.at[s, "category_method"] == "text model (overrode source)"
        elif r.error_type == "missing_required":
            col = {"colour": "colour", "material": "material", "quantity": "net_qty"}[r.field]
            fixed = c is not None and pd.notna(c[col])
        elif r.error_type == "price_outlier":
            fixed = c is not None and c.listing_status != "active"   # held back from the shop for review
        elif r.error_type in ("duplicate_reworded", "cross_source_duplicate"):
            flagged = fixed = canon == tr.at[r.ref_sku, "canonical_sku"]
        elif r.error_type == "split_variant":
            same_parent = tr.at[s, "parent_of_canonical"] == tr.at[r.ref_sku, "parent_of_canonical"]
            merged = canon == tr.at[r.ref_sku, "canonical_sku"]
            flagged = bool(same_parent or merged)
            fixed = bool(same_parent and not merged)
        rows.append(dict(sku=s, error_type=r.error_type, detail=r.field, caught=bool(flagged), fixed=bool(fixed)))
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "detection_detail.csv", index=False)
    g = d.groupby("error_type").agg(injected=("sku", "size"), caught=("caught", "sum"), fixed=("fixed", "sum")).reset_index()
    g["caught_rate"], g["fixed_rate"] = (g.caught / g.injected).round(3), (g.fixed / g.injected).round(3)
    g["label"] = g.error_type.map(LABEL)
    g["data"] = "SIMULATED errors on PUBLIC DATA products"
    g = g.sort_values("caught_rate", ascending=False)
    g.to_csv(OUT / "detection_by_type.csv", index=False)
    # false merges: new products of the SIMULATED platform (not in the ABO sample) merged into another SKU
    mkb_new = tr[(tr.source == "mkb") & ~tr.index.isin(truth[truth.error_type == "cross_source_duplicate"].sku)]
    fp = {"mkb_new_items": int(len(mkb_new)), "wrongly_merged": int((mkb_new.canonical_sku != mkb_new.index).sum())}
    sug = pd.read_csv(OUT / "unit_repair_suggestions.csv")
    hit = int(sug.sku.isin(truth[truth.error_type == "unit_mislabel"].sku).sum())
    tot = {"injected": int(g.injected.sum()), "caught": int(g.caught.sum()), "fixed": int(g.fixed.sum()), **fp,
           "unit_repair_suggestions": int(len(sug)), "unit_repair_suggestions_on_injected_errors": hit}
    (OUT / "detection_summary.json").write_text(json.dumps(tot, indent=1))
    print(g[["label", "injected", "caught_rate", "fixed_rate"]].to_string(index=False))
    print(tot)


if __name__ == "__main__":
    main()
