"""SIMULATED errors injected into a copy of the raw catalogue, with an answer key written to data/_hidden_truth.csv.
The key is read only by src/evaluate_detection.py, after the pipeline has run (the pipeline never sees it).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from catalog.normalize import COLOUR_SYNONYMS, norm_colour
from config import SEED

N_PER_TYPE = 100
UNKNOWN_COLOURS = ["Midnight", "Ocean", "Sunset", "Storm", "Cloud", "Moonlight", "Desert", "Galaxy"]
FOREIGN = {"blue": ["bleu marine", "azul marino", "blau"], "black": ["noir", "schwarz", "nero"], "white": ["blanc", "weiss", "bianco"],
           "grey": ["gris", "grau", "grigio"], "red": ["rouge", "rot", "rosso"], "green": ["vert", "grün", "verde"],
           "brown": ["marron", "braun", "marrone"], "beige": ["sable", "sand"]}
OTHER_TYPES = ["SOFA", "CELLULAR_PHONE_CASE", "SHOES", "RUG", "LAMP", "VITAMIN", "COFFEE", "BACKPACK", "PET_SUPPLIES", "TOOLS"]
OFF_TYPES = ["breakfast-cereals", "cheeses", "waters", "honeys", "crisps", "teas"]


def _typo(s: str, rng) -> str:
    s = str(s)
    if len(s) < 4:
        return s + s[-1]
    i = int(rng.integers(1, len(s) - 1))
    k = rng.integers(0, 3)
    if k == 0:
        return s[:i] + s[i + 1:]                 # drop a letter
    if k == 1:
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]  # swap two letters
    return s[:i] + s[i] + s[i:]                  # double a letter


def inject(raw: pd.DataFrame, mkb_key: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED + 1)
    df = raw.copy()
    truth, used = [], set()

    def pick(mask, n=N_PER_TYPE):
        cand = df.index[mask & ~df.index.isin(list(used)) & ~df.sku.str.contains("-[DV]$")]
        idx = rng.choice(cand, size=min(n, len(cand)), replace=False)
        used.update(idx)
        return idx

    def log(i, typ, field, old, new, ref=None):
        truth.append(dict(sku=df.at[i, "sku"] if i in df.index else i, error_type=typ, field=field,
                          original=None if pd.isna(old) else str(old), injected=None if pd.isna(new) else str(new), ref_sku=ref))

    base = df.source.isin(["abo", "off"])
    # 1 colour words outside the controlled list (synonym, other language, or unknown marketing name)
    for i in pick(base & df.colour_raw.map(lambda c: norm_colour(c) not in (None, "multicolour"))):
        fam = norm_colour(df.at[i, "colour_raw"])
        r = rng.random()
        new = (rng.choice(UNKNOWN_COLOURS) if r < 0.3 else rng.choice(FOREIGN.get(fam, COLOUR_SYNONYMS[fam])) if r < 0.6
               else rng.choice([s for s in COLOUR_SYNONYMS[fam] if s != fam]).title())
        log(i, "colour_nonstandard", "colour", df.at[i, "colour_raw"], new)
        df.at[i, "colour_raw"] = new
    # 2 misspelled brands
    vc = df.brand_raw.value_counts()
    for i in pick(base & df.brand_raw.isin(vc[vc >= 20].index)):
        new = _typo(df.at[i, "brand_raw"], rng)
        log(i, "brand_misspelled", "brand", df.at[i, "brand_raw"], new)
        df.at[i, "brand_raw"] = new
    # 3 unit mislabelled: the number is kept, the unit is wrong
    for i in pick(base & df.length_raw.notna() & (df.dim_unit == "inches"), N_PER_TYPE // 2):
        unit = str(rng.choice(["centimeters", "millimeters"]))
        log(i, "unit_mislabel", "dimensions", "inches", unit)
        df.at[i, "dim_unit"] = unit
    for i in pick(base & df.weight_raw.notna() & (df.weight_unit == "pounds"), N_PER_TYPE // 2):
        unit = str(rng.choice(["kilograms", "ounces"]))
        log(i, "unit_mislabel", "weight", "pounds", unit)
        df.at[i, "weight_unit"] = unit
    # 4 wrong category in the source
    for i in pick(base):
        if df.at[i, "source"] == "off":
            new = rng.choice([t for t in OFF_TYPES if t != df.at[i, "source_type"]])
        else:
            new = rng.choice([t for t in OTHER_TYPES if t != df.at[i, "source_type"]])
        log(i, "wrong_category", "category", df.at[i, "source_type"], new)
        df.at[i, "source_type"] = new
        df.at[i, "node_path"] = None
    # 5 required attributes removed
    for i in pick(base & (df.colour_raw.notna() | df.material_raw.notna() | df.quantity_raw.notna())):
        field = "quantity_raw" if pd.notna(df.at[i, "quantity_raw"]) else ("material_raw" if pd.notna(df.at[i, "material_raw"]) and rng.random() < 0.5 else "colour_raw")
        if pd.isna(df.at[i, field]):
            field = "colour_raw" if pd.notna(df.at[i, "colour_raw"]) else "material_raw"
        log(i, "missing_required", field.replace("_raw", ""), df.at[i, field], None)
        df.at[i, field] = None
    # 6 price errors: decimal shift, cents typed as dollars, zero
    for i in pick(base & (df.price > 2)):
        k = rng.choice(["x10", "x100", "zero", "div10"], p=[0.35, 0.3, 0.15, 0.2])
        old = df.at[i, "price"]
        new = {"x10": old * 10, "x100": old * 100, "zero": 0.0, "div10": round(old / 10, 2)}[k]
        log(i, "price_outlier", f"price ({k})", old, new)
        df.at[i, "price"] = round(new, 2)
    # 7 duplicates inside one source with a reworded title
    new_rows = []
    for i in pick(base):
        r = df.loc[i].copy()
        words = str(r.title).split(" ")
        r["title"] = " ".join(words[:1] + list(rng.permutation(words[1:]))) if len(words) > 3 else str(r.title) + " (new)"
        r["sku"] = r.sku + "-D"
        r["stock_qty"] = int(rng.integers(1, 50)); r["in_stock"] = True
        new_rows.append(r)
        truth.append(dict(sku=r.sku, error_type="duplicate_reworded", field="title", original=df.at[i, "title"],
                          injected=r.title, ref_sku=df.at[i, "sku"]))
    # 8 colour variants listed as separate products
    for i in pick(base & df.colour_raw.map(lambda c: norm_colour(c) not in (None, "multicolour"))):
        r = df.loc[i].copy()
        fam = norm_colour(r.colour_raw)
        other = str(rng.choice([c for c in ["black", "white", "grey", "blue", "red", "green", "beige", "brown"] if c != fam]))
        r["colour_raw"] = other.title()
        r["title"] = str(r.title).replace(str(df.at[i, "colour_raw"]), other.title()) if str(df.at[i, "colour_raw"]) in str(r.title) else f"{r.title}, {other.title()}"
        r["sku"] = r.sku + "-V"
        r["model_number"] = None
        new_rows.append(r)
        truth.append(dict(sku=r.sku, error_type="split_variant", field="parent", original=None, injected=other, ref_sku=df.at[i, "sku"]))
    df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    # 9 cross-source duplicates come from the SIMULATED other-platform export
    for r in mkb_key.itertuples():
        truth.append(dict(sku=r.sku, error_type="cross_source_duplicate", field="sku", original=None, injected=None, ref_sku=r.duplicate_of))
    return df, pd.DataFrame(truth)
