"""Build the unified catalogue: ingest 3 sources -> inject SIMULATED errors (answer key hidden) -> normalise ->
classify -> de-duplicate -> repair units -> group variants -> quality rules before/after -> quality gate.
Outputs: data/processed/catalog.parquet (clean, one row per SKU), data/processed/listings_raw_view.parquet (every
raw listing as it arrived, with its canonical SKU), data/outputs/*.csv|json, taxonomy/brand_mapping.csv.
Usage: python src/build_catalog.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import quality as Q  # noqa: E402
from catalog.classify import classify  # noqa: E402
from catalog.dedupe import find_duplicates, group_variants, merge_clusters, survivors  # noqa: E402
from catalog.enrich import BrandTable, normalise  # noqa: E402
from catalog.inject import inject  # noqa: E402
from catalog.sources import build_raw  # noqa: E402
from catalog.taxonomy import load, required_attrs  # noqa: E402
from config import HIDDEN, OUT, PROCESSED, TAXO  # noqa: E402

KEEP = ["sku", "parent_id", "source", "source_id", "title", "brand", "category_id", "category_path", "department",
        "colour", "size", "material", "gender", "compatible_device", "length_cm", "width_cm", "height_cm", "weight_g",
        "net_qty", "net_unit", "capacity_ml", "pack_count", "labels", "nutriscore", "allergens", "style", "pattern",
        "price", "currency", "stock_qty", "in_stock", "language", "description", "keywords", "gtin", "model_number",
        "category_method", "brand_method", "colour_method", "duplicates_merged", "is_variant_group", "listing_status",
        "quality_score"]
UNIT_FACTORS = {"in->cm": 2.54, "mm->cm": 0.1, "cm->in": 1 / 2.54, "cm->mm": 10.0, "lb->kg": 1 / 2.20462,
                "kg->lb": 2.20462, "oz->lb": 16.0, "lb->oz": 1 / 16}


def apply_templates(df: pd.DataFrame) -> pd.DataFrame:
    """Keep category-specific attributes only where the category template uses them."""
    leaves, tpl = load()
    t = df.category_id.map(leaves.set_index("category_id")["attrs"])
    scale = t.map(lambda a: tpl["templates"][a].get("size_scale"))
    df["size"] = np.select([scale == "shoe_size", scale == "apparel_size", scale == "bed_size"],
                           [df.shoe_size.map(lambda v: None if pd.isna(v) else f"{v:g}"), df.apparel_size, df.bed_size], None)
    df.loc[~t.isin(["shoes", "apparel", "accessory", "jewelry"]), "gender"] = None
    df.loc[t != "phone_case", "compatible_device"] = None
    df.loc[~t.isin(["food", "health", "household"]), ["net_qty", "net_unit"]] = None
    df.loc[~t.isin(["tableware", "appliance", "bag"]), "capacity_ml"] = None
    return df


def add_paths(df):
    L, _ = load()
    m = L.set_index("category_id")
    df["category_path"] = df.category_id.map(m.path)
    df["department"] = df.category_id.map(m.department)
    return df


def unit_repair(df: pd.DataFrame) -> pd.DataFrame:
    """Suggest a unit fix for a dimension or weight that is an extreme outlier in its category (|z| > 5) and becomes
    typical (|z| < 1) after one standard conversion (x2.54, x10, x2.2, x16 ...). Suggestions only: tested as an
    automatic repair it changed far more correct values than wrong ones (docs/CATALOG_STANDARDS.md), so values
    are not changed; rule K02 sends outliers to review."""
    df = df.copy()
    df["unit_repair"] = None
    for col in ("length_cm", "width_cm", "height_cm", "weight_g"):
        z = Q.robust_z(df[col], df.category_id)
        lx = np.log(df[col].where(df[col] > 0))
        med = lx.groupby(df.category_id).transform("median")
        mad = (lx - med).abs().groupby(df.category_id).transform("median") * 1.4826
        for i in df.index[z.abs() > 5]:
            best = min(UNIT_FACTORS.items(), key=lambda kv: abs(lx[i] + np.log(kv[1]) - med[i]))
            new_z = (lx[i] + np.log(best[1]) - med[i]) / mad[i]
            if abs(new_z) < 1.0:
                df.at[i, col] = round(df.at[i, col] * best[1], 2)
                df.at[i, "unit_repair"] = f"{col} {best[0]}"
    return df


def before_view(df: pd.DataFrame) -> pd.DataFrame:
    """The catalogue as the sources deliver it: raw strings, declared units, source category only, no merges."""
    from catalog.enrich import _dims, _weight
    b = pd.DataFrame({"sku": df.sku, "source": df.source, "title": df.title, "brand": df.brand_raw,
                      "category_id": df.rule_category.where(df.rule_method == "source category"),
                      "category_path": df.source_category.fillna(""), "colour": df.colour_raw, "colour_raw": df.colour_raw,
                      "size": df.size_raw, "material": df.material_raw, "price": df.price, "currency": "USD",
                      "stock_qty": df.stock_qty, "in_stock": df.in_stock, "language": df.language,
                      "description": df.description, "gtin": df.gtin, "parent_id": None, "labels": df.labels,
                      "net_qty": df.net_qty, "gender": None, "compatible_device": None})
    dims = df.apply(_dims, axis=1)
    b["length_cm"], b["width_cm"], b["height_cm"] = dims.str[0], dims.str[1], dims.str[2]
    b["weight_g"] = df.apply(_weight, axis=1)
    return b


def run_quality(view: pd.DataFrame, brands_ref: set, dup_flag, split_flag, model_pred, model_proba) -> pd.DataFrame:
    L, _ = load()
    food = "C07"  # department prefix of Grocery & Gourmet Food
    food = L.loc[L.department == "Grocery & Gourmet Food", "category_id"].str[:3].iloc[0]
    ctx = dict(required_attrs=required_attrs(), food_prefix=food, brands=brands_ref, dup_flag=dup_flag,
               split_flag=split_flag, model_pred=model_pred, model_proba=model_proba)
    return Q.run_rules(view.reset_index(drop=True), ctx)


def main():
    t0 = time.time()
    raw, mkb_key = build_raw()
    raw, truth = inject(raw, mkb_key)
    HIDDEN.parent.mkdir(exist_ok=True)
    truth.to_csv(HIDDEN, index=False)   # answer key: read only by src/evaluate_detection.py
    trusted = raw[raw.source.isin(["abo", "off"])].brand_raw
    brands = BrandTable(trusted)
    print(f"{len(raw):,} raw listings · {brands.ref.size:,} reference brands")

    df = normalise(raw, brands)
    df = classify(df)
    df = add_paths(apply_templates(df))
    print("classified", df.category_method.value_counts().to_dict())
    df = survivors(find_duplicates(df))

    # ------------------------------------------------ the raw view (before) and its quality
    fam = group_variants(df.assign(size=df["size"]))
    split_before = fam.is_variant_group.values  # colour/size siblings listed as separate products in the sources
    dup_before = df.canonical_sku.map(df.canonical_sku.value_counts()).values > 1
    before = before_view(df)
    model_pred = pd.Series(df.model_category.values, index=df.sku)
    model_proba = pd.Series(df.model_proba.values, index=df.sku)
    ref = set(brands.ref.values)
    fb = run_quality(before, ref, pd.Series(dup_before), pd.Series(split_before), model_pred, model_proba)
    before["quality_score"] = Q.score(fb).values

    # ------------------------------------------------ the clean catalogue (after)
    fill = ["colour", "material", "length_cm", "width_cm", "height_cm", "weight_g", "net_qty", "net_unit", "description",
            "size", "gender", "compatible_device", "gtin", "labels"]
    clean = merge_clusters(df, fill)
    sugg = unit_repair(clean)
    sugg[sugg.unit_repair.notna()][["sku", "unit_repair"]].to_csv(OUT / "unit_repair_suggestions.csv", index=False)
    clean["unit_repair"] = None
    clean = group_variants(clean)
    clean["title"] = clean.title_clean
    clean = clean.reset_index(drop=True)
    fa = run_quality(clean, ref, pd.Series(False, index=clean.index), pd.Series(False, index=clean.index), model_pred, model_proba)
    clean["quality_score"] = Q.score(fa).values
    # quality gate: price errors and outliers are held back from the shop until reviewed
    held = (fa.V01 == 1) | (fa.C04 == 1) | (fa.K01 == 1) | (fa.K06 == 1)
    clean["listing_status"] = np.where(held, "held for review", "active")
    print(f"clean catalogue: {len(clean):,} SKUs, {clean.parent_id.nunique():,} parents, {held.sum():,} held")

    # ------------------------------------------------ outputs
    PROCESSED.mkdir(exist_ok=True)
    cat = clean[KEEP].copy()
    for c in ("gtin", "model_number", "size", "pack_count"):
        cat[c] = cat[c].astype("string")
    cat.to_parquet(PROCESSED / "catalog.parquet", index=False)
    rv = before.drop(columns=["quality_score"]).assign(canonical_sku=df.canonical_sku.values,
                                                       category_path=df.source_category.fillna("").values)
    rv["brand_norm"], rv["colour_norm"], rv["material_norm"] = df.brand.values, df.colour.values, df.material.values
    rv["size_norm"], rv["category_path_norm"] = df["size"].values, df.category_path.values
    for c in ("gtin", "size", "size_norm"):
        rv[c] = rv[c].astype("string")
    rv.to_parquet(PROCESSED / "listings_raw_view.parquet", index=False)
    # internal table for the evaluation and the taxonomy report (not a deliverable on its own)
    dbg = df[["sku", "source", "canonical_sku", "dup_method", "rule_category", "rule_method", "model_category",
              "model_proba", "category_id", "category_method", "brand_raw", "brand", "brand_method", "colour_raw",
              "colour", "colour_method", "title_clean", "keywords"]].copy()
    dbg = dbg.merge(clean[["sku", "unit_repair", "parent_id", "listing_status"]], on="sku", how="left")
    dbg["parent_of_canonical"] = dbg.canonical_sku.map(clean.set_index("sku").parent_id)
    dbg.to_parquet(OUT / "pipeline_trace.parquet", index=False)

    fb.assign(sku=before.sku.values).to_parquet(OUT / "flags_before.parquet", index=False)
    fa.assign(sku=clean.sku.values).to_parquet(OUT / "flags_after.parquet", index=False)
    rb, ra = Q.summary(fb), Q.summary(fa)
    rules = rb.merge(ra[["id", "applicable", "failed", "pass_rate"]], on="id", suffixes=("_before", "_after"))
    rules.to_csv(OUT / "quality_rules_before_after.csv", index=False)
    pd.DataFrame({"view": ["before"] * len(before) + ["after"] * len(clean),
                  "score": np.r_[before.quality_score.values, clean.quality_score.values]}).to_parquet(OUT / "quality_scores.parquet", index=False)
    bycat = clean.groupby(["department", "category_path"]).agg(skus=("sku", "size"), quality=("quality_score", "mean"),
                                                                held=("listing_status", lambda s: (s != "active").sum())).round(4)
    bycat.reset_index().to_csv(OUT / "quality_by_category.csv", index=False)
    log = Q.issues_log(clean, fa)
    log.to_csv(OUT / "issues_log.csv", index=False)
    bt = df.groupby(["brand_raw", "brand", "brand_method"]).size().rename("listings").reset_index()
    bt[bt.brand_raw != bt.brand].sort_values("listings", ascending=False).to_csv(TAXO / "brand_mapping.csv", index=False)
    stats = {
        "raw_listings": int(len(raw)), "by_source": raw.source.value_counts().to_dict(),
        "clean_skus": int(len(clean)), "parents": int(clean.parent_id.nunique()),
        "variant_groups": int(clean[clean.is_variant_group].parent_id.nunique()),
        "skus_in_variant_groups": int(clean.is_variant_group.sum()),
        "duplicates_merged": int(len(df) - len(clean)), "dup_methods": df.dup_method.value_counts().to_dict(),
        "held_for_review": int(held.sum()), "active": int((~held).sum()),
        "reference_brands": int(brands.ref.size), "brand_methods": df.brand_method.value_counts().to_dict(),
        "colour_methods": df.colour_method.value_counts().to_dict(),
        "category_methods": df.category_method.value_counts().to_dict(),
        "unit_repair_suggestions": int(sugg.unit_repair.notna().sum()),
        "non_english_titles": int((clean.language != "en").sum()),
        "quality_before": round(float(before.quality_score.mean()), 4), "quality_after": round(float(clean.quality_score.mean()), 4),
        "issues_before": int(fb.fillna(0).sum().sum()), "issues_after": int(fa.fillna(0).sum().sum()),
        "seconds": round(time.time() - t0),
    }
    (OUT / "catalog_stats.json").write_text(json.dumps(stats, indent=1, default=int))
    print(json.dumps({k: stats[k] for k in ("clean_skus", "parents", "duplicates_merged", "held_for_review", "quality_before", "quality_after", "seconds")}))


if __name__ == "__main__":
    main()
