"""Taxonomy deliverables and classification accuracy. Run after build_catalog.py.
  taxonomy/categories.csv          every node (department, group, leaf) with parent id, level, Google id
  taxonomy/google_mapping.csv      leaf -> Google Product Taxonomy id and path
  taxonomy/source_mapping.csv      each source category value -> leaf, with counts and method
  taxonomy/category_attributes.csv leaf x attribute (required / optional) with the fill rate in the catalogue
  data/outputs/classification_eval.json, confusion_department.csv, classification_errors.csv
Accuracy is measured on 200 products labelled by hand from title and brand only
(taxonomy/classification_manual_labels.csv). Usage: python src/build_taxonomy.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog.classify import mkb_type  # noqa: E402
from catalog.taxonomy import gpt_table, load, nodes  # noqa: E402
from config import OUT, PROCESSED, TAXO  # noqa: E402


def main():
    L, tpl = load()
    n = nodes()
    n.assign(gpt_id=n.gpt_id.astype("Int64"), attribute_template=n.node_id.map(L.set_index("category_id")["attrs"])) \
        .to_csv(TAXO / "categories.csv", index=False)
    L[["category_id", "path", "gpt_id", "gpt_path"]].to_csv(TAXO / "google_mapping.csv", index=False)

    tr = pd.read_parquet(OUT / "pipeline_trace.parquet")
    raw = pd.read_parquet(PROCESSED / "listings_raw_view.parquet")[["sku", "category_path"]]
    tr = tr.merge(raw, on="sku", how="left")
    src_val = tr.category_path.str.split(" | ", regex=False).str[0]
    tr["source_value"] = src_val.where(tr.source != "mkb", tr.category_path.map(lambda v: mkb_type(v) or "(blank)"))
    sm = tr.groupby(["source", "source_value", "category_id", "category_method"]).size().rename("listings").reset_index()
    sm["category_path"] = sm.category_id.map(L.set_index("category_id").path)
    sm.sort_values(["source", "listings"], ascending=[True, False]).to_csv(TAXO / "source_mapping.csv", index=False)

    cat = pd.read_parquet(PROCESSED / "catalog.parquet")
    rows = []
    for r in L.itertuples():
        t = tpl["templates"][r.attrs]
        sub = cat[cat.category_id == r.category_id]
        for kind in ("required", "optional"):
            for a in t[kind]:
                fill = float(sub[a].notna().mean()) if a in sub and len(sub) else None
                rows.append(dict(category_id=r.category_id, category=r.name, template=r.attrs, attribute=a, status=kind,
                                 skus=len(sub), fill_rate=None if fill is None else round(fill, 3)))
    pd.DataFrame(rows).to_csv(TAXO / "category_attributes.csv", index=False)

    dept = L.set_index("category_id").department
    cov = cat.assign(dept=cat.category_id.map(dept)).groupby("dept").agg(skus=("sku", "size"), leaves_used=("category_id", "nunique"))
    cov["leaves_total"] = L.groupby("department").size()
    cov.reset_index().rename(columns={"dept": "department"}).to_csv(OUT / "taxonomy_coverage.csv", index=False)

    # -------------------------------------------------------------- accuracy on the hand-labelled sample
    m = pd.read_csv(TAXO / "classification_manual_labels.csv").merge(tr, on="sku", how="left")
    other = L.loc[L.name == "Other Products", "category_id"].iloc[0]
    m["final_ok"] = m.category_id == m.manual_category_id
    res = {"sample": int(len(m)), "ambiguous_in_sample": int(m.ambiguous_note.notna().sum()),
           "final_accuracy": round(float(m.final_ok.mean()), 3),
           "final_accuracy_unambiguous": round(float(m[m.ambiguous_note.isna()].final_ok.mean()), 3),
           "department_accuracy": round(float((m.category_id.map(dept) == m.manual_category_id.map(dept)).mean()), 3),
           "in_other": int((m.category_id == other).sum())}
    by = m.groupby("category_method").agg(n=("sku", "size"), precision=("final_ok", "mean")).round(3)
    res["precision_by_method"] = by.reset_index().to_dict("records")
    rules = m[m.rule_category.notna()]
    res["rules_precision"] = round(float((rules.rule_category == rules.manual_category_id).mean()), 3)
    res["rules_coverage"] = round(float(len(rules) / len(m)), 3)
    res["model_precision"] = round(float((m.model_category == m.manual_category_id).mean()), 3)
    hi = m[m.model_proba >= 0.8]
    res["model_precision_proba_0.8"] = round(float((hi.model_category == hi.manual_category_id).mean()), 3)
    res["model_share_proba_0.8"] = round(float(len(hi) / len(m)), 3)
    allc = pd.read_parquet(OUT / "pipeline_trace.parquet").category_method.value_counts(normalize=True).round(4)
    res["method_share_all_listings"] = allc.to_dict()
    res["other_share_catalogue"] = round(float((cat.category_id == other).mean()), 4)
    (OUT / "classification_eval.json").write_text(json.dumps(res, indent=1))
    conf = pd.crosstab(m.manual_category_id.map(dept).rename("manual"), m.category_id.map(dept).rename("predicted"))
    conf.to_csv(OUT / "confusion_department.csv")
    err = m[~m.final_ok][["sku", "title_clean", "manual_category", "category_id", "category_method", "ambiguous_note"]].copy()
    err["predicted_category"] = err.category_id.map(L.set_index("category_id")["name"])
    err.drop(columns="category_id").to_csv(OUT / "classification_errors.csv", index=False)
    print(json.dumps({k: v for k, v in res.items() if k not in ("precision_by_method", "method_share_all_listings")}, indent=0))
    print(by.to_string())


if __name__ == "__main__":
    _ = gpt_table()
    main()
