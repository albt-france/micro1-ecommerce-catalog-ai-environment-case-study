"""Ingestion: flatten each public source into one row per listing with the raw values kept as they arrive
(ABO: multilingual JSON lines; OFF: API JSON). Nothing is normalised here; see normalize.py.
"""
from __future__ import annotations

import json

import pandas as pd

from config import RAW

EN_ORDER = ["en_US", "en_GB", "en_CA", "en_AU", "en_IN", "en_SG", "en_AE"]


def _pick(values, key="value"):
    """Value in the best English locale, else the first one. Returns (value, language_tag)."""
    if not values:
        return None, None
    by = {}
    for v in values:
        by.setdefault(v.get("language_tag") or "", v.get(key))
    for t in EN_ORDER:
        if t in by:
            return by[t], t
    for t, v in by.items():
        if t.startswith("en"):
            return v, t
    t, v = next(iter(by.items()))
    return v, t


def _en_list(values, n=3):
    en = [v["value"] for v in values or [] if str(v.get("language_tag", "")).startswith("en")]
    return " | ".join(en[:n]) if en else None


def flatten_abo() -> pd.DataFrame:
    dest = RAW / "abo_flat.parquet"
    if dest.exists():
        return pd.read_parquet(dest)
    rows = []
    with open(RAW / "abo_listings.jsonl", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            title, lang = _pick(d.get("item_name"))
            colour, _ = _pick(d.get("color"))
            std = (d.get("color") or [{}])[0].get("standardized_values")
            dims = d.get("item_dimensions") or {}
            w = (d.get("item_weight") or [{}])[0]
            node = (d.get("node") or [{}])[0]
            r = dict(
                source_id=d["item_id"], title=title, title_lang=lang, brand=_pick(d.get("brand"))[0],
                product_type=(d.get("product_type") or [{}])[0].get("value"), node_path=node.get("node_name"),
                colour=colour, colour_std=(std or [None])[0], material=_pick(d.get("material"))[0],
                style=_pick(d.get("style"))[0], pattern=_pick(d.get("pattern"))[0], fabric=_pick(d.get("fabric_type"))[0],
                shape=_pick(d.get("item_shape"))[0], finish=_pick(d.get("finish_type"))[0],
                model_number=(d.get("model_number") or [{}])[0].get("value"), model_name=_pick(d.get("model_name"))[0],
                keywords=_en_list(d.get("item_keywords"), 8), bullets=_en_list(d.get("bullet_point"), 3),
                domain=d.get("domain_name"), country=d.get("country"),
                weight=w.get("normalized_value", {}).get("value") if w.get("normalized_value") else w.get("value"),
                weight_unit=w.get("normalized_value", {}).get("unit") if w.get("normalized_value") else w.get("unit"),
            )
            for k in ("length", "width", "height"):
                v = dims.get(k) or {}
                nv = v.get("normalized_value") or {}
                r[f"{k}_raw"] = nv.get("value", v.get("value"))
                r[f"{k}_unit"] = nv.get("unit", v.get("unit"))
            rows.append(r)
    df = pd.DataFrame(rows)
    df.to_parquet(dest, index=False)
    return df


def flatten_off() -> pd.DataFrame:
    rows = []
    seen = set()
    with open(RAW / "off_products.jsonl", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if d.get("code") in seen:
                continue
            seen.add(d.get("code"))
            name = d.get("product_name_en") or d.get("product_name")
            if isinstance(name, dict):
                name = name.get("en") or next(iter(name.values()), None)
            if isinstance(name, list):
                name = name[0] if name else None
            brands = d.get("brands")
            if isinstance(brands, list):
                brands = ", ".join(brands)
            rows.append(dict(
                source_id=str(d.get("code")), title=name, title_lang=d.get("lang"), brand=brands,
                off_categories=",".join(d.get("categories_tags") or []), query_category=d.get("_query_category"),
                quantity=d.get("quantity"), product_quantity=d.get("product_quantity"),
                product_quantity_unit=d.get("product_quantity_unit"), labels=",".join(d.get("labels_tags") or []),
                countries=",".join(d.get("countries_tags") or []), nutriscore=d.get("nutriscore_grade"),
                allergens=",".join(d.get("allergens_tags") or []), serving_size=d.get("serving_size")))
    return pd.DataFrame(rows)
