"""Row-level normalisation of the raw listings into catalogue fields (SI units, controlled colours, sizes, brands,
device compatibility, pack counts, net quantities). Every derived value keeps a trace of where it came from.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from catalog.normalize import (APPAREL_SIZES, brand_key, fold, norm_apparel_size, norm_colour, norm_shoe_size,
                               parse_quantity, to_cm, to_g)

PLACEHOLDER_COLOURS = {"others", "other", "na", "n a", "none", "see image", "as shown", "assorted color", "assorted colour", "0", "daylight", "soft white"}
BED_SIZES = ["California King", "King", "Queen", "Full", "Double", "Twin", "Single"]
DEVICE = re.compile(r"\bfor\s+((?:apple|iphone|samsung|galaxy|xiaomi|redmi|mi|oneplus|vivo|oppo|realme|nokia|motorola|moto|"
                    r"google|pixel|huawei|honor|lg|sony|asus|tecno|infinix|poco|lenovo|micromax|ipad|kindle|fire)\b[\w +()./-]*?)"
                    r"(?=\s*(?:[,|\[–]|\s-\s|\(|$|\bcase\b|\bcover\b))", re.I)
PACK = re.compile(r"(?:pack of|set of|case of)\s*(\d+)|(\d+)\s*[- ]?(?:pack|pk|count|ct|pcs|pieces)\b", re.I)
MATERIAL_MAP = {"faux leather": ["pu leather", "leatherette", "synthetic leather", "vegan leather", "faux leather", "polyurethane"],
                "leather": ["leather", "genuine leather", "real leather"], "wood": ["wood", "solid wood", "wooden", "engineered wood", "mdf", "oak", "pine", "acacia", "walnut", "rubberwood"],
                "metal": ["metal", "steel", "iron", "aluminium", "aluminum", "stainless steel", "brass", "alloy"],
                "fabric": ["fabric", "polyester", "linen", "velvet", "microfiber", "microfibre", "upholstery", "chenille", "tweed"],
                "cotton": ["cotton", "100% cotton"], "plastic": ["plastic", "polypropylene", "polycarbonate", "tpu", "silicone", "acrylic", "abs", "pvc"],
                "glass": ["glass", "tempered glass"], "ceramic": ["ceramic", "porcelain", "stoneware"], "wool": ["wool"],
                "gold": ["gold", "yellow gold", "rose gold", "white gold"], "silver": ["sterling silver", "silver"], "rubber": ["rubber"]}
_MAT = {fold(s): k for k, v in MATERIAL_MAP.items() for s in v}


def clean_brand_text(b) -> str | None:
    if not isinstance(b, str) or not b.strip():
        return None
    s = re.sub(r"^\s*amazon brand\s*[-–:]\s*", "", b.strip(), flags=re.I)
    m = re.match(r"^(.*?)\((.*?)\)\s*$", s)
    if m:
        out, inside = m.group(1).strip(), m.group(2).strip()
        latin = lambda x: bool(x) and all(ord(c) < 0x250 for c in x)  # noqa: E731
        s = inside if latin(inside) and not latin(out) else (out if latin(out) else s)
    s = re.sub(r"[,\s]+(inc|llc|ltd|limited|gmbh|corp|co)\.?$", "", s, flags=re.I).strip()
    if s.isupper() and len(s) > 4:
        s = s.title()
    return re.sub(r"\s+", " ", s) or None


class BrandTable:
    """Reference table from the brands seen at least 3 times in the trusted sources (ABO, OFF). Variants with the
    same key map to the most frequent spelling; rare unknown spellings are matched with fuzzy ratio >= 90."""

    def __init__(self, brands: pd.Series):
        c = brands.map(clean_brand_text).dropna()
        k = c.map(brand_key)
        d = pd.DataFrame({"display": c, "key": k})
        d = d[d.key.str.len() > 0]
        counts = d.groupby("key").size()
        disp = d.groupby(["key", "display"]).size().reset_index(name="n").sort_values("n", ascending=False).drop_duplicates("key")
        self.ref = disp.set_index("key").display[counts[counts >= 3].index]
        self.keys = list(self.ref.index)

    def map(self, raw) -> tuple[str | None, str]:
        c = clean_brand_text(raw)
        if c is None:
            return None, "missing"
        k = brand_key(c)
        if k in self.ref.index:
            return self.ref[k], "reference" if c == self.ref[k] else "variant"
        if len(k) >= 5:
            hit = process.extractOne(k, self.keys, scorer=fuzz.ratio, score_cutoff=90)
            if hit:
                return self.ref[hit[0]], "fuzzy"
        return c, "new"

    def table(self) -> pd.DataFrame:
        return pd.DataFrame({"brand_key": self.ref.index, "brand": self.ref.values})


def _colour(raw, title):
    f = fold(raw)
    if f and f not in PLACEHOLDER_COLOURS:
        c = norm_colour(raw)
        if c:
            return c, "field"
        return None, "unmapped"
    c = norm_colour_in_title(title)
    return (c, "title") if c else (None, "placeholder" if f else "missing")


def norm_colour_in_title(title):
    """Colour named in the last comma part of a title ('..., 96"W, Navy' -> blue); only unambiguous hits."""
    parts = [p.strip() for p in str(title or "").split(",")]
    for p in reversed(parts[-2:]):
        c = norm_colour(p)
        if c and len(p.split()) <= 3:
            return c
    return None


def _material(raw):
    f = fold(raw)
    if not f:
        return None
    if f in _MAT:
        return _MAT[f]
    for k in sorted(_MAT, key=len, reverse=True):
        if re.search(rf"\b{re.escape(k)}\b", f):
            return _MAT[k]
    return f[:30]


def _gender(text):
    t = str(text or "").lower()
    if re.search(r"\b(women'?s?|ladies|womens|female|damen|femme)\b", t):
        return "women"
    if re.search(r"\b(men'?s?|mens|male|herren|homme)\b", t):
        return "men"
    if re.search(r"\b(kids?|boys?|girls?|children'?s?|toddler)\b", t):
        return "kids"
    if "unisex" in t:
        return "unisex"
    return None


def _shoe_size(raw, title, gender):
    if raw:
        return norm_shoe_size(raw)
    m = re.search(r"\b(\d{1,2}(?:\.5)?)\s*(?:[A-Z]{1,2}\s+)?US\b", str(title or ""))
    if m:
        us = float(m.group(1))
        uk = us - 2 if gender == "women" else us - 1
        return norm_shoe_size(f"UK {uk:g}")
    m = re.search(r"\b(?:EU|EUR)\s*(\d{2}(?:\.5)?)\b|\b(?:UK)\s*(\d{1,2}(?:\.5)?)\b", str(title or ""))
    if m:
        return norm_shoe_size(("EU " + m.group(1)) if m.group(1) else ("UK " + m.group(2)))
    return None


def _apparel_size(raw, title):
    if raw:
        return norm_apparel_size(raw)
    parts = [p.strip() for p in str(title or "").split(",")]
    for p in reversed(parts):
        s = norm_apparel_size(p)
        if s:
            return s
    m = re.search(r"\bsize\s+([A-Za-z0-9-]+)", str(title or ""), re.I)
    return norm_apparel_size(m.group(1)) if m else None


def _bed_size(title):
    for s in BED_SIZES:
        if re.search(rf"\b{s}\b", str(title or ""), re.I):
            return s
    return None


def _dims(r):
    if pd.notna(r.length_raw) or pd.notna(r.width_raw) or pd.notna(r.height_raw):
        return [to_cm(v, r.dim_unit) if pd.notna(v) else None for v in (r.length_raw, r.width_raw, r.height_raw)]
    if isinstance(r.dims_text, str):
        m = re.match(r"([\d.]+) x ([\d.]+) x ([\d.]+) (cm|in)", r.dims_text)
        if m:
            return [to_cm(float(m.group(k)), m.group(4)) for k in (1, 2, 3)]
    return [None, None, None]


def _weight(r):
    if pd.notna(r.weight_raw):
        return to_g(r.weight_raw, r.weight_unit)
    if isinstance(r.weight_text, str):
        v, u = r.weight_text.split()
        return to_g(float(v), u)
    return None


def normalise(raw: pd.DataFrame, brands: BrandTable) -> pd.DataFrame:
    """Returns one row per raw listing with clean fields. Category-dependent fields (size, gender, device) are
    filled for every row and kept only where the category template uses them (see build_catalog.apply_templates)."""
    df = raw.copy()
    b = df.brand_raw.map(brands.map)
    df["brand"], df["brand_method"] = b.str[0], b.str[1]
    df["title_clean"] = df.title.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    caps = df.title_clean.str.count(r"[A-Z]") / df.title_clean.str.count(r"[A-Za-z]").replace(0, np.nan) > 0.8
    df.loc[caps, "title_clean"] = df.loc[caps, "title_clean"].str.title()
    col = [_colour(c, t) for c, t in zip(df.colour_raw, df.title)]
    df["colour"], df["colour_method"] = [c[0] for c in col], [c[1] for c in col]
    df["material"] = df.material_raw.map(_material)
    dims = df.apply(_dims, axis=1)
    df["length_cm"], df["width_cm"], df["height_cm"] = dims.str[0], dims.str[1], dims.str[2]
    df["weight_g"] = df.apply(_weight, axis=1)
    q = [parse_quantity(x) if isinstance(x, str) else parse_quantity(t) for x, t in zip(df.quantity_raw, df.title)]
    df["net_qty"], df["net_unit"] = [x[0] for x in q], [x[1] for x in q]
    df["capacity_ml"] = [v if u == "ml" else None for v, u in q]
    pk = df.title.str.extract(PACK)
    df["pack_count"] = pd.to_numeric(pk[0].fillna(pk[1]), errors="coerce")
    text = df.title.fillna("") + " " + df.node_path.fillna("")
    df["gender"] = text.map(_gender)
    df["shoe_size"] = [_shoe_size(s, t, g) for s, t, g in zip(df.size_raw, df.title, df.gender)]
    df["apparel_size"] = [_apparel_size(s, t) for s, t in zip(df.size_raw, df.title)]
    df["bed_size"] = df.title.map(_bed_size)
    dev = df.title.str.extract(DEVICE, expand=False)
    df["compatible_device"] = dev.str.strip(" -,").str.replace(r"\s+", " ", regex=True)
    df["price"] = pd.to_numeric(df.price, errors="coerce")
    df["currency"] = "USD"
    df["language"] = df.language.fillna("en").str[:2]
    return df
