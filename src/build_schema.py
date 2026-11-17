"""Load the clean catalogue into both models and check them.
  relational: schema/schema.sql in DuckDB (data/outputs/catalog.duckdb, not published) + integrity queries;
  document:   one JSON document per parent product (data/processed/catalog_documents.jsonl), every document
              validated against schema/product.schema.json; MongoDB $jsonSchema validator derived from it.
Usage: python src/build_schema.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog.normalize import brand_key  # noqa: E402
from catalog.taxonomy import load, nodes  # noqa: E402
from config import OUT, PROCESSED, SCHEMA  # noqa: E402

COLUMN_ATTRS = {"colour": "enum", "size": "text", "material": "text", "length_cm": "number", "width_cm": "number",
                "height_cm": "number", "weight_g": "number", "net_qty": "number", "capacity_ml": "number",
                "pack_count": "number", "gender": "enum"}
EAV_ATTRS = {"compatible_device": "text", "style": "text", "pattern": "text", "labels": "text", "nutriscore": "enum",
             "allergens": "text"}
UNITS = {"length_cm": "cm", "width_cm": "cm", "height_cm": "cm", "weight_g": "g", "capacity_ml": "ml"}
VERSION = "catalog-pipeline 1.0"
T_NONPOS = {}


def none(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA else v


def tables(cat: pd.DataFrame, raw: pd.DataFrame) -> dict:
    L, tpl = load()
    br = cat.brand.dropna().drop_duplicates().sort_values().reset_index(drop=True)
    brand = pd.DataFrame({"brand_id": np.arange(1, len(br) + 1), "name": br, "brand_key": br.map(brand_key)})
    brand = brand.drop_duplicates("brand_key")
    bid = brand.set_index("name").brand_id
    bkey = dict(zip(brand.brand_key, brand.brand_id))
    alias = raw[["brand", "brand_norm"]].dropna().drop_duplicates("brand")
    alias = alias.assign(brand_id=alias.brand_norm.map(lambda b: bkey.get(brand_key(b))), method="variant")
    alias.loc[alias.brand == alias.brand_norm, "method"] = "reference"
    alias = alias.dropna(subset=["brand_id"]).rename(columns={"brand": "alias"})[["alias", "brand_id", "method"]]
    n = nodes()
    leaf_tpl = L.set_index("category_id")["attrs"]
    category = pd.DataFrame({"category_id": n.node_id, "parent_id": n.parent_id, "name": n.name, "level": n.level,
                             "path": n.path, "is_leaf": n.is_leaf, "google_category_id": n.gpt_id.astype("Int64"),
                             "attribute_template": n.node_id.map(leaf_tpl)}).sort_values("level")  # parents first (FK)
    attribute = pd.DataFrame([dict(attribute_code=k, data_type=v, unit=UNITS.get(k), storage="column") for k, v in COLUMN_ATTRS.items()]
                             + [dict(attribute_code=k, data_type=v, unit=None, storage="eav") for k, v in EAV_ATTRS.items()])
    ca = []
    for r in L.itertuples():
        t = tpl["templates"][r.attrs]
        for a in t["required"]:
            ca.append((r.category_id, a, True))
        for a in t["optional"]:
            if a in COLUMN_ATTRS or a in EAV_ATTRS:
                ca.append((r.category_id, a, False))
    category_attribute = pd.DataFrame(ca, columns=["category_id", "attribute_code", "is_required"]).drop_duplicates(["category_id", "attribute_code"])
    first = cat.sort_values("sku").drop_duplicates("parent_id")
    product = pd.DataFrame({"product_id": first.parent_id, "title": first.title, "brand_id": first.brand.map(bid).astype("Int64"),
                            "category_id": first.category_id, "gender": first.gender, "description": first.description,
                            "language": first.language.fillna("en")})
    variant = cat[["sku", "parent_id", "title", "colour", "size", "material", "length_cm", "width_cm", "height_cm", "weight_g",
                   "net_qty", "net_unit", "capacity_ml", "pack_count", "gtin", "listing_status", "quality_score"]].rename(columns={"parent_id": "product_id"})
    num = ["length_cm", "width_cm", "height_cm", "weight_g", "net_qty", "capacity_ml"]
    cap = {"length_cm": 5000, "width_cm": 5000, "height_cm": 5000, "weight_g": 5e6, "net_qty": 1e6, "capacity_ml": 1e6}
    bad = pd.concat([(variant[c] <= 0) | (variant[c] > cap[c]) for c in num], axis=1)
    T_NONPOS["values"] = int(bad.sum().sum())   # 0, negative or physically impossible (> 50 m, > 5 t): stored as NULL
    for c in num:
        variant[c] = variant[c].where((variant[c] > 0) & (variant[c] <= cap[c]))
    variant.loc[variant.net_qty.isna(), "net_unit"] = None
    pc = pd.to_numeric(variant.pack_count, errors="coerce")
    variant = variant.assign(pack_count=pc.where(pc > 0).astype("Int64"),
                             gtin=variant.gtin.where(variant.gtin.astype(str).str.fullmatch(r"\d{8,14}")))
    price = pd.DataFrame({"sku": cat.sku, "currency": cat.currency, "amount": cat.price.round(2), "valid_from": pd.Timestamp("2026-11-17").date()})
    inventory = cat[["sku", "stock_qty", "in_stock"]].assign(stock_qty=cat.stock_qty.astype(int))
    eav = cat.melt(id_vars="sku", value_vars=list(EAV_ATTRS), var_name="attribute_code", value_name="value_text").dropna(subset=["value_text"])
    eav = eav.assign(value_text=eav.value_text.astype(str), value_num=None)
    src = raw[["sku", "source", "canonical_sku"]].rename(columns={"sku": "listing_sku"})
    src = src.assign(source_id=src.listing_sku.str.split("-", n=1).str[1], match_method=None)
    src = src[src.canonical_sku.isin(cat.sku)][["listing_sku", "source", "source_id", "canonical_sku", "match_method"]]
    return dict(brand=brand, brand_alias=alias, category=category, attribute=attribute, category_attribute=category_attribute,
                product=product, variant=variant, price=price, inventory=inventory, variant_attribute=eav[["sku", "attribute_code", "value_text", "value_num"]],
                source_listing=src)


CHECKS = {
    "variants without a product": "SELECT count(*) FROM variant v LEFT JOIN product p USING (product_id) WHERE p.product_id IS NULL",
    "products in a non-leaf category": "SELECT count(*) FROM product p JOIN category c USING (category_id) WHERE NOT c.is_leaf",
    "leaves without a Google id": "SELECT count(*) FROM category WHERE is_leaf AND google_category_id IS NULL",
    "SKUs without a price": "SELECT count(*) FROM variant v LEFT JOIN price p USING (sku) WHERE p.sku IS NULL",
    "SKUs without stock row": "SELECT count(*) FROM variant v LEFT JOIN inventory i USING (sku) WHERE i.sku IS NULL",
    "required attributes missing (active SKUs)": """
        SELECT count(*) FROM variant v JOIN product p USING (product_id)
        JOIN category_attribute ca ON ca.category_id = p.category_id AND ca.is_required
        WHERE v.listing_status = 'active' AND CASE ca.attribute_code
            WHEN 'colour' THEN v.colour IS NULL WHEN 'size' THEN v.size IS NULL WHEN 'material' THEN v.material IS NULL
            WHEN 'length_cm' THEN v.length_cm IS NULL WHEN 'net_qty' THEN v.net_qty IS NULL WHEN 'gender' THEN p.gender IS NULL
            WHEN 'compatible_device' THEN NOT EXISTS (SELECT 1 FROM variant_attribute a WHERE a.sku = v.sku AND a.attribute_code = 'compatible_device')
            ELSE FALSE END""",
    "listings merged into another SKU": "SELECT count(*) FROM source_listing WHERE listing_sku <> canonical_sku",
    "parents with 2+ variants": "SELECT count(*) FROM (SELECT product_id FROM variant GROUP BY 1 HAVING count(*) > 1)",
    "max tree depth": "WITH RECURSIVE t AS (SELECT category_id, 1 AS d FROM category WHERE parent_id IS NULL UNION ALL "
                      "SELECT c.category_id, t.d + 1 FROM category c JOIN t ON c.parent_id = t.category_id) SELECT max(d) FROM t",
}
QUERIES = {
    "blue sofas under $700 in stock (filter query an agent tool runs)": """
        SELECT count(*) FROM variant v JOIN product p USING (product_id) JOIN category c USING (category_id)
        JOIN price pr USING (sku) JOIN inventory i USING (sku)
        WHERE c.name = 'Sofas & Couches' AND v.colour = 'blue' AND pr.amount <= 700 AND i.in_stock AND v.listing_status = 'active'""",
}


def documents(cat: pd.DataFrame, raw: pd.DataFrame) -> list[dict]:
    L, _ = load()
    leaf = L.set_index("category_id")
    srcs = {}
    for src, sku, can in zip(raw.source, raw.sku, raw.canonical_sku):
        srcs.setdefault(can, []).append(dict(source=src, id=sku.split("-", 1)[1], match=None if sku == can else "merged"))
    docs = []
    for pid, g in cat.groupby("parent_id", sort=True):
        f = g.iloc[0]
        attrs = {k: none(f[k]) for k in ("style", "pattern", "nutriscore", "compatible_device") if none(f[k]) is not None}
        if none(f.labels):
            attrs["labels"] = str(f.labels).split(",")
        if none(f.allergens):
            attrs["allergens"] = [a for a in str(f.allergens).split(",") if a]
        variants = []
        for _, v in g.iterrows():
            d = {"sku": v.sku, "title": v.title, "colour": none(v.colour), "size": none(v["size"]), "material": none(v.material),
                 "price": {"amount": round(float(v.price), 2), "currency": "USD"},
                 "stock": {"qty": int(v.stock_qty), "in_stock": bool(v.in_stock)}, "status": v.listing_status,
                 "quality_score": round(float(v.quality_score), 4), "sources": srcs.get(v.sku, [])}
            dims = {k: round(float(v[f"{k}_cm"]), 2) for k in ("length", "width", "height") if none(v[f"{k}_cm"]) is not None and 0 < v[f"{k}_cm"] <= 5000}
            if dims:
                d["dimensions_cm"] = dims
            for k in ("weight_g", "capacity_ml"):
                if none(v[k]) is not None and v[k] > 0:
                    d[k] = round(float(v[k]), 2)
            if none(v.net_qty) is not None and v.net_qty > 0:
                d["net_quantity"] = {"value": round(float(v.net_qty), 2), "unit": v.net_unit}
            if none(v.pack_count) is not None and float(v.pack_count) >= 1:
                d["pack_count"] = int(float(v.pack_count))
            if none(v.gtin) is not None and str(v.gtin).isdigit() and 8 <= len(str(v.gtin)) <= 14:
                d["gtin"] = str(v.gtin)
            variants.append(d)
        docs.append({"_id": pid, "title": f.title,
                     "brand": {"name": f.brand, "key": brand_key(f.brand) or "".join(str(f.brand).lower().split())} if none(f.brand) else None,
                     "category": {"id": f.category_id, "path": leaf.at[f.category_id, "path"].split(" > "),
                                  "google_id": int(leaf.at[f.category_id, "gpt_id"])},
                     "gender": none(f.gender), "language": f.language or "en", "description": none(f.description),
                     "attributes": attrs, "variants": variants, "updated_from": VERSION})
    return docs


def mongo_validator(schema: dict) -> dict:
    """MongoDB $jsonSchema accepts draft-4 style keywords: drop $schema/$id/const/exclusiveMinimum numbers, map integer."""
    def conv(s):
        if isinstance(s, dict):
            out = {}
            for k, v in s.items():
                if k in ("$schema", "$id", "title"):
                    continue
                if k == "const":
                    out["enum"] = [v]; continue
                if k == "exclusiveMinimum":
                    out["minimum"] = v; out["exclusiveMinimum"] = True; continue
                if k == "type":
                    t = v if isinstance(v, list) else [v]
                    t = ["int" if x == "integer" else ("double" if x == "number" else x) for x in t]
                    t = ["bool" if x == "boolean" else x for x in t]
                    out["bsonType"] = t if len(t) > 1 else t[0]; continue
                out[k] = conv(v)
            return out
        if isinstance(s, list):
            return [conv(x) for x in s]
        return s
    return {"$jsonSchema": conv(schema)}


def main():
    cat = pd.read_parquet(PROCESSED / "catalog.parquet")
    raw = pd.read_parquet(PROCESSED / "listings_raw_view.parquet")
    T = tables(cat, raw)
    db = OUT / "catalog.duckdb"
    db.unlink(missing_ok=True)
    con = duckdb.connect(str(db))
    con.execute((SCHEMA / "schema.sql").read_text(encoding="utf-8")).fetchall()
    order = ["brand", "brand_alias", "category", "attribute", "category_attribute", "product", "variant", "price",
             "inventory", "variant_attribute", "source_listing"]
    counts = {}
    for t in order:
        df = T[t]
        cols = ", ".join(df.columns)
        # the category tree references itself: insert one level at a time so parents exist first
        parts = [g for _, g in df.groupby("level")] if t == "category" else [df]
        for part in parts:
            con.register("tmp", part)
            con.execute(f"INSERT INTO {t} ({cols}) SELECT {cols} FROM tmp").fetchall()
            con.unregister("tmp")
        counts[t] = int(con.execute(f"SELECT count(*) FROM {t}").fetchall()[0][0])
    checks = [{"check": k, "result": int(con.execute(q).fetchall()[0][0])} for k, q in {**CHECKS, **QUERIES}.items()]
    con.close()
    schema = json.loads((SCHEMA / "product.schema.json").read_text(encoding="utf-8"))
    val = Draft202012Validator(schema)
    docs = documents(cat, raw)
    errors = [(d["_id"], e.message) for d in docs for e in val.iter_errors(d)]
    with open(PROCESSED / "catalog_documents.jsonl", "w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    (SCHEMA / "mongo_validator.json").write_text(json.dumps(mongo_validator(schema), indent=1), encoding="utf-8")
    (SCHEMA / "sample_document.json").write_text(json.dumps(next(d for d in docs if len(d["variants"]) >= 3), indent=1, ensure_ascii=False), encoding="utf-8")
    res = {"row_counts": counts, "checks": checks, "documents": len(docs), "documents_invalid": len({e[0] for e in errors}),
           "validation_errors_sample": errors[:5], "eav_rows": counts["variant_attribute"], "impossible_measures_nulled": T_NONPOS.get("values", 0),
           "avg_variants_per_document": round(float(np.mean([len(d["variants"]) for d in docs])), 3)}
    (OUT / "schema_checks.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: res[k] for k in ("row_counts", "documents", "documents_invalid")}))
    for c in checks:
        print(f"  {c['check']}: {c['result']}")


if __name__ == "__main__":
    main()
