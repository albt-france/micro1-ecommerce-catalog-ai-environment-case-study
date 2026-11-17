"""Build the three raw sources in one listing-level table, values kept as the sources give them:
  abo  PUBLIC DATA   Amazon Berkeley Objects listings (sampled, seed 42)
  off  PUBLIC DATA   Open Food Facts products (UK/US, 22 food categories)
  mkb  SIMULATED     export from an "other marketplace": built from ABO items with that platform's own formats
                     (inches or cm in one text field, '5 lb' weights, other colour words, brand spellings, its own
                     category labels, 25 % without category). Two thirds of its rows are products already in the ABO
                     sample (cross-source duplicates with a known answer); one third are new.
Prices and stock levels do not exist in the public data: they are SIMULATED (seeded log-normal by product type).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from catalog.ingest import flatten_abo, flatten_off
from catalog.normalize import COLOUR_SYNONYMS, norm_colour
from config import N_ABO, N_OTHER, SEED

CAP = {"CELLULAR_PHONE_CASE": 1500, "SHOES": 900, "GROCERY": 700}
DEFAULT_CAP = 450
PRICE_MEDIAN = {  # USD, SIMULATED; matched on product_type / OFF category substrings, first hit wins
    "SOFA": 650, "BED": 420, "HEADBOARD": 230, "DRESSER": 380, "DESK": 240, "TABLE": 210, "CABINET": 190, "CHAIR": 170,
    "OTTOMAN": 110, "BENCH": 140, "STOOL": 95, "SHELF": 90, "RUG": 120, "LIGHT_FIXTURE": 95, "LAMP": 70, "MIRROR": 85,
    "MAJOR_HOME": 450, "AIR_CONDITIONER": 380, "VACUUM": 160, "FINE": 190, "WATCH": 120, "SUITCASE": 110, "LUGGAGE": 95,
    "HANDBAG": 55, "BACKPACK": 40, "SHOES": 55, "BOOT": 75, "SANDAL": 35, "CELLULAR_PHONE_CASE": 12, "SCREEN_PROTECTOR": 9,
    "HEADPHONES": 45, "SPEAKERS": 60, "COFFEE_MAKER": 70, "BLENDER": 55, "SAUTE_FRY_PAN": 32, "DUTCH": 60,
    "VITAMIN": 16, "SUPPLEMENT": 20, "GROCERY": 7, "COFFEE": 11, "TEA": 6, "WINE": 15,
    "HOME_BED_AND_BATH": 45, "HOME_FURNITURE_AND_DECOR": 60, "HOME": 30, "KITCHEN": 25, "PET_SUPPLIES": 30,
    "OUTDOOR_LIVING": 120, "SPORTING_GOODS": 30, "OFFICE": 15, "BATTERY": 12,
}
OFF_PRICE = {"olive-oils": 9, "coffees": 7, "cheeses": 5, "honeys": 7, "nuts": 5, "chocolates": 3.5, "teas": 4,
             "waters": 1.2, "sodas": 1.8, "fruit-juices": 3, "sandwiches": 4, "fresh-fruits": 2.5}
MKB_LABEL_PREFIX = ["", "Shop/", "All/"]


def _median(ptype: str, source: str) -> float:
    if source == "off":
        return OFF_PRICE.get(ptype, 3.0)
    for k, v in PRICE_MEDIAN.items():
        if k in str(ptype):
            return v
    return 25.0


def simulate_prices(df: pd.DataFrame, rng) -> pd.DataFrame:
    med = np.array([_median(t, s) for t, s in zip(df.source_type, df.source)])
    df["price"] = np.round(med * np.exp(rng.normal(0, 0.45, len(df))), 2).clip(0.79)
    df["price"] = np.floor(df.price) + np.where(rng.random(len(df)) < 0.7, 0.99, 0.49)
    out = rng.random(len(df)) < 0.08
    df["stock_qty"] = np.where(out, 0, rng.integers(1, 180, len(df)))
    df["in_stock"] = df.stock_qty > 0
    return df


def sample_abo(rng) -> tuple[pd.DataFrame, pd.DataFrame]:
    abo = flatten_abo()
    abo = abo[abo.title.notna() & abo.product_type.notna()].drop_duplicates("source_id")
    abo = abo.sample(frac=1, random_state=SEED)
    abo["_rank"] = abo.groupby("product_type").cumcount()
    cap = abo.product_type.map(CAP).fillna(DEFAULT_CAP)
    pool = abo[abo._rank < cap].drop(columns="_rank")
    main = pool.sample(n=min(N_ABO, len(pool)), random_state=SEED)
    rest = pool.drop(main.index)
    return main, rest


def abo_rows(a: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "sku": "ABO-" + a.source_id, "source": "abo", "source_id": a.source_id, "title": a.title, "brand_raw": a.brand,
        "source_type": a.product_type, "source_category": a.product_type + " | " + a.node_path.fillna(""),
        "node_path": a.node_path, "colour_raw": a.colour, "size_raw": None, "material_raw": a.material,
        "length_raw": a.length_raw, "width_raw": a.width_raw, "height_raw": a.height_raw,
        "dim_unit": a.length_unit.fillna(a.width_unit).fillna(a.height_unit), "dims_text": None,
        "weight_raw": a.weight, "weight_unit": a.weight_unit, "quantity_raw": None, "gtin": None,
        "language": a.title_lang.str[:2], "description": a.bullets, "keywords": a.keywords, "labels": None,
        "nutriscore": None, "allergens": None, "model_number": a.model_number, "style": a["style"], "pattern": a["pattern"],
        "price_text": None})


def off_rows() -> pd.DataFrame:
    o = flatten_off()
    o = o[o.title.notna() & (o.title.str.strip().str.len() > 2)]
    qty = o.product_quantity.astype(str) + " " + o.product_quantity_unit.fillna("")
    qty = qty.where(o.product_quantity.notna() & o.product_quantity_unit.notna(), o.quantity)
    labels = o.labels.fillna("").str.split(",").map(
        lambda t: ",".join(sorted({x.split(":", 1)[-1] for x in t if x.split(":", 1)[-1] in
                                   {"organic", "vegan", "vegetarian", "gluten-free", "fair-trade", "no-added-sugar", "palm-oil-free"}})) or None)
    return pd.DataFrame({
        "sku": "OFF-" + o.source_id, "source": "off", "source_id": o.source_id, "title": o.title.str.strip(),
        "brand_raw": o.brand.str.split(",").str[0].str.strip(), "source_type": o.query_category,
        "source_category": o.off_categories.str.split(",").str[:4].str.join(","), "node_path": None,
        "colour_raw": None, "size_raw": None, "material_raw": None, "length_raw": None, "width_raw": None,
        "height_raw": None, "dim_unit": None, "dims_text": None, "weight_raw": None, "weight_unit": None,
        "quantity_raw": qty, "gtin": o.source_id, "language": o.title_lang, "description": None, "keywords": None,
        "labels": labels, "nutriscore": o.nutriscore, "allergens": o.allergens.str.replace("en:", "", regex=False),
        "model_number": None, "style": None, "pattern": None, "price_text": None})


def _brand_variant(b: str, rng) -> str:
    if not isinstance(b, str):
        return b
    k = rng.integers(0, 5)
    if k == 0:
        return b.upper()
    if k == 1:
        return b.replace(" ", "")
    if k == 2:
        return b + " Inc."
    if k == 3 and "amazon brand" in b.lower():
        return b.split("-")[-1].split("–")[-1].strip()
    return b


def _colour_variant(c, rng):
    fam = norm_colour(c)
    if not fam or fam == "multicolour":
        return c
    syns = [s for s in COLOUR_SYNONYMS[fam] if s != fam]
    return str(rng.choice(syns)).title() if rng.random() < 0.7 else c


def _title_variant(t: str, brand, rng) -> str:
    s = t
    if isinstance(brand, str) and brand in s and rng.random() < 0.5:
        s = s.replace(brand, "").strip(" ,-–") + f" - {brand}"
    parts = [p.strip() for p in s.split(",")]
    if len(parts) > 2 and rng.random() < 0.5:
        parts = [parts[0]] + list(rng.permutation(parts[1:]))
    s = ", ".join(parts).replace(" with ", " w/ ").replace(" and ", " & ")
    return s.upper() if rng.random() < 0.15 else s


def mkb_rows(dupe_src: pd.DataFrame, new_src: pd.DataFrame, rng) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SIMULATED other-platform export. Returns (rows, answer key of cross-source duplicates)."""
    src = pd.concat([dupe_src.assign(_dup=True), new_src.assign(_dup=False)])
    rows, key = [], []
    for i, (_, a) in enumerate(src.iterrows()):
        sku = f"MKB-{100000 + i}"
        cm = rng.random() < 0.6
        f = 2.54 if cm else 1.0
        dims = [a.length_raw, a.width_raw, a.height_raw]
        dims_text = None
        if all(pd.notna(d) for d in dims):
            dims_text = " x ".join(f"{float(d) * f:.1f}" for d in dims) + (" cm" if cm else " in")
        w, wtxt = a.weight, None
        if pd.notna(w):
            u = rng.choice(["kg", "lb", "oz"])
            wv = float(w) * {"kg": 0.453592, "lb": 1.0, "oz": 16.0}[u]
            wtxt = f"{wv:.2f} {u}"
        label = None if rng.random() < 0.25 else rng.choice(MKB_LABEL_PREFIX) + str(a.product_type).replace("_", " ").title()
        rows.append({
            "sku": sku, "source": "mkb", "source_id": sku, "title": _title_variant(a.title, a.brand, rng),
            "brand_raw": _brand_variant(a.brand, rng), "source_type": label, "source_category": label, "node_path": None,
            "colour_raw": _colour_variant(a.colour, rng), "size_raw": None, "material_raw": a.material,
            "length_raw": None, "width_raw": None, "height_raw": None, "dim_unit": None, "dims_text": dims_text,
            "weight_raw": None, "weight_unit": None, "weight_text": wtxt, "quantity_raw": None, "gtin": None,
            "language": str(a.title_lang)[:2], "description": a.bullets, "keywords": None, "labels": None, "nutriscore": None,
            "allergens": None, "model_number": a.model_number if rng.random() < 0.5 else None, "style": a["style"],
            "pattern": a["pattern"], "price_text": None, "_abo_type": a.product_type})
        if a._dup:
            key.append({"sku": sku, "duplicate_of": "ABO-" + a.source_id})
    return pd.DataFrame(rows), pd.DataFrame(key)


def build_raw() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    main, rest = sample_abo(rng)
    n_dup = int(N_OTHER * 2 / 3)
    dupe_src = main.sample(n=n_dup, random_state=SEED)
    new_src = rest.sample(n=N_OTHER - n_dup, random_state=SEED)
    a, o = abo_rows(main), off_rows()
    m, key = mkb_rows(dupe_src, new_src, rng)
    raw = pd.concat([a, o, m.drop(columns="_abo_type")], ignore_index=True)
    # SIMULATED prices: a duplicate costs about the same as its original on the other platform
    raw["_ptype"] = raw.source_type.where(raw.source != "mkb", None)
    raw.loc[raw.source == "mkb", "_ptype"] = m._abo_type.values
    tmp = raw.assign(source_type=raw._ptype)
    tmp = simulate_prices(tmp, rng)
    raw["price"], raw["stock_qty"], raw["in_stock"] = tmp.price, tmp.stock_qty, tmp.in_stock
    orig_price = raw.set_index("sku").price
    dup_price = key.duplicate_of.map(orig_price) * np.exp(rng.normal(0, 0.03, len(key)))
    raw.loc[raw.sku.isin(key.sku), "price"] = np.round(dup_price.values, 2)
    mk = raw.source == "mkb"
    raw.loc[mk, "price_text"] = "$" + raw.loc[mk, "price"].map(lambda v: f"{v:,.2f}")
    raw["weight_text"] = raw.get("weight_text")
    return raw.drop(columns="_ptype"), key
