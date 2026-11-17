"""Duplicate detection and variant grouping.

Duplicates (same product, two listings):
  1. identifiers: same GTIN, or same brand + model number + colour + size;
  2. titles: inside a block (same brand, same department), token-sort similarity of the title keys (brand, colours,
     sizes and stop words removed, numbers kept) >= THRESHOLD, and no conflicting attribute (numbers in the title, colour, size, length +-10 %).
     THRESHOLD was chosen on 50 pairs checked by hand (taxonomy/dedupe_manual_check.csv).
  Pairs are merged into clusters (union-find); the survivor is the most complete trusted record, and its missing
  fields are filled from the other members.
Variants (same product, different colour or size): same brand, same leaf category and same family key
(title key without colour, size and numbers) -> one parent, one child per colour/size.
"""
from __future__ import annotations

import hashlib
import re

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from catalog.normalize import title_key

THRESHOLD = 94   # sample of 50 hand-checked pairs: precision 0.80, recall 0.89 (taxonomy/dedupe_manual_check.csv)
SOURCE_RANK = {"abo": 0, "off": 0, "mkb": 1}


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def _size(r):
    return r.shoe_size if pd.notna(r.shoe_size) else (r.apparel_size or r.bed_size)


def _numbers(t) -> set:
    return set(re.findall(r"\d+(?:[.,]\d+)?", str(t)))


def _compatible(a, b) -> bool:
    na, nb = _numbers(a.title), _numbers(b.title)
    if na and nb and na != nb:          # 12.5 oz vs 10.8 oz, 55 cm vs 78 cm: different products
        return False
    for f in ("colour", "size_any"):
        if pd.notna(a[f]) and pd.notna(b[f]) and a[f] != b[f]:
            return False
    if pd.notna(a.length_cm) and pd.notna(b.length_cm) and max(a.length_cm, b.length_cm) > 1.1 * min(a.length_cm, b.length_cm) + 0.5:
        return False
    return True


def candidate_pairs(df: pd.DataFrame, cutoff: int = 70) -> pd.DataFrame:
    """All title pairs with similarity >= cutoff inside brand x department blocks (used for the manual check)."""
    df = df.assign(tkey=[title_key(t, b, keep_numbers=True) for t, b in zip(df.title_clean, df.brand)])
    rows = []
    for _, g in df[df.brand.notna()].groupby(["brand", "department"]):
        if len(g) < 2:
            continue
        keys = g.tkey.tolist()
        m = process.cdist(keys, keys, scorer=fuzz.token_sort_ratio, score_cutoff=cutoff, workers=-1)
        ii, jj = np.nonzero(np.triu(m, 1))
        for i, j in zip(ii, jj):
            rows.append((g.index[i], g.index[j], float(m[i, j])))
    return pd.DataFrame(rows, columns=["i", "j", "score"])


def find_duplicates(df: pd.DataFrame, threshold: int = THRESHOLD) -> pd.DataFrame:
    df = df.copy()
    df["size_any"] = df.apply(_size, axis=1)
    uf = UF()
    how = {}
    # 1 identifiers
    for col in ("gtin",):
        g = df[df[col].notna()].groupby(col).sku.apply(list)
        for skus in g[g.str.len() > 1]:
            for s in skus[1:]:
                uf.union(s, skus[0]); how[s] = "gtin"
    mk = df[df.model_number.notna() & df.brand.notna()]
    g = mk.groupby([mk.brand, mk.model_number.astype(str).str.lower(), mk.colour.fillna("-"), mk.size_any.astype(str)]).sku.apply(list)
    for skus in g[g.str.len() > 1]:
        for s in skus[1:]:
            uf.union(s, skus[0]); how.setdefault(s, "brand+model number")
    # 2 titles
    pairs = candidate_pairs(df, cutoff=threshold)
    for r in pairs.itertuples():
        a, b = df.loc[r.i], df.loc[r.j]
        if _compatible(a, b):
            uf.union(a.sku, b.sku); how.setdefault(b.sku, "title similarity")
    df["cluster"] = df.sku.map(uf.find)
    df["dup_method"] = df.sku.map(how)
    return df.drop(columns="size_any")


def survivors(df: pd.DataFrame) -> pd.DataFrame:
    """canonical_sku per listing: trusted source first, then the most complete record."""
    fields = ["brand", "colour", "material", "length_cm", "weight_g", "net_qty", "description", "price"]
    df = df.assign(_rank=df.source.map(SOURCE_RANK), _filled=-df[fields].notna().sum(axis=1), _inj=df.sku.str.contains("-[DV]$").astype(int))
    order = df.sort_values(["cluster", "_rank", "_inj", "_filled", "sku"])
    canon = order.groupby("cluster").sku.first()
    df["canonical_sku"] = df.cluster.map(canon)
    return df.drop(columns=["_rank", "_filled", "_inj"])


def merge_clusters(df: pd.DataFrame, fill_cols) -> pd.DataFrame:
    """One row per canonical SKU, missing fields filled from the other members of its cluster."""
    canon = df[df.sku == df.canonical_sku].set_index("canonical_sku")
    multi = df[df.duplicated("canonical_sku", keep=False)]
    if len(multi):
        filler = multi.sort_values("source").groupby("canonical_sku")[fill_cols].first()
        canon[fill_cols] = canon[fill_cols].combine_first(filler)[fill_cols]
        stock = df.groupby("canonical_sku").stock_qty.sum()
        canon["stock_qty"] = stock.reindex(canon.index)
        canon["in_stock"] = canon.stock_qty > 0
    canon["duplicates_merged"] = df.groupby("canonical_sku").size().reindex(canon.index) - 1
    return canon.reset_index(drop=False).rename(columns={"canonical_sku": "_c"}).drop(columns="_c")


def family_key(title, brand) -> str:
    k = title_key(title, brand)
    return " ".join(w for w in k.split() if not any(ch.isdigit() for ch in w))


def group_variants(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["family"] = [family_key(t, b) for t, b in zip(df.title_clean, df.brand)]
    g = df.groupby([df.brand.fillna("?"), df.category_id, df.family])
    df["_n"] = g.sku.transform("size")
    differ = (g.colour.transform("nunique") > 1) | (g["size"].transform("nunique") > 1)
    grouped = (df._n > 1) & differ & df.brand.notna() & (df.family.str.len() >= 6)
    pid = (df.brand.fillna("") + "|" + df.category_id + "|" + df.family).map(lambda s: "P-" + hashlib.md5(s.encode()).hexdigest()[:10])
    df["parent_id"] = np.where(grouped, pid, "P-" + df.sku)
    df["is_variant_group"] = grouped
    return df.drop(columns=["_n"])
