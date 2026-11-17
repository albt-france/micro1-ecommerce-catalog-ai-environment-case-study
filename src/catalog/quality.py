"""Quality rule engine: runs rules.yaml on a catalogue table, returns one boolean column per rule (True = problem),
a quality score per SKU and per category, and an issues log. Rules that do not apply to a SKU are NaN.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from catalog.enrich import BED_SIZES
from catalog.normalize import COLOURS, APPAREL_SIZES, fold, norm_colour

RULES = Path(__file__).with_name("rules.yaml")
WEIGHT = {"error": 3, "warning": 2, "info": 1}


def load_rules() -> list[dict]:
    return yaml.safe_load(RULES.read_text(encoding="utf-8"))["rules"]


def gtin_ok(code) -> bool:
    s = re.sub(r"\D", "", str(code))
    if len(s) not in (8, 12, 13, 14):
        return False
    d = [int(c) for c in s]
    tot = sum(v * (3 if i % 2 == 0 else 1) for i, v in enumerate(reversed(d[:-1])))
    return (10 - tot % 10) % 10 == d[-1]


def robust_z(x: pd.Series, groups: pd.Series) -> pd.Series:
    lx = np.log(x.where(x > 0))
    med = lx.groupby(groups).transform("median")
    mad = (lx - med).abs().groupby(groups).transform("median") * 1.4826
    n = lx.groupby(groups).transform("count")
    z = (lx - med) / mad.replace(0, np.nan)
    return z.where(n >= 8)


def _isnull(s: pd.Series) -> pd.Series:
    return s.isna() | (s.astype(str).str.strip().isin(["", "None", "nan"]))


def run_rules(df: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """ctx: required_attrs {category_id: [attr]}, food_prefix, brands (set of reference brand names),
    model_pred / model_proba (Series by sku, optional), dup_cluster (Series), split_variant (Series)."""
    rules = load_rules()
    out = pd.DataFrame(index=df.index)
    vals = {"colours": set(COLOURS), "sizes": None}
    for r in rules:
        c, f = r["check"], r.get("field")
        if c == "not_null":
            res = _isnull(df[f])
        elif c == "positive":
            res = (df[f].fillna(0) <= 0).where(df[f].notna())
        elif c == "in_list":
            allowed = vals.get(r["values"], r["values"]) if isinstance(r["values"], str) else set(r["values"])
            if f == "size":
                ok = df[f].astype(str).isin(APPAREL_SIZES + BED_SIZES + ["one size"]) | df[f].astype(str).str.fullmatch(r"\d{2}(\.5|\.0)?")
                res = (~ok).where(df[f].notna())
            else:
                res = (~df[f].isin(allowed)).where(df[f].notna())
        elif c == "required_attributes":
            req = df.category_id.map(ctx["required_attrs"])

            def miss(i):
                attrs = req.at[i]
                return any(_isnull(pd.Series([df.at[i, a] if a in df else None])).iloc[0] for a in attrs) if isinstance(attrs, list) and attrs else False
            res = pd.Series([miss(i) for i in df.index], index=df.index).where(req.notna())
        elif c == "food_net_quantity":
            food = df.category_id.astype(str).str.startswith(ctx["food_prefix"])
            res = (df.net_qty.isna() | (df.net_qty <= 0)).where(food)
        elif c == "gtin":
            res = df[f].map(lambda v: not gtin_ok(v)).where(df[f].notna())
        elif c == "title_length":
            n = df.title.fillna("").str.len()
            res = ((n < r["min"]) | (n > r["max"])).where(df.title.notna())
        elif c == "not_shouting":
            t = df.title.fillna("")
            letters = t.str.count(r"[A-Za-z]")
            res = ((t.str.count(r"[A-Z]") / letters.replace(0, np.nan)) > 0.8).where(letters > 10)
        elif c == "english_title":
            res = (df.language.fillna("en") != "en")
        elif c == "price_outlier":
            res = (robust_z(df.price, df.category_id).abs() > r["z"])
            res = res.where(robust_z(df.price, df.category_id).notna())
        elif c == "dimension_outlier":
            zs = [robust_z(df[col], df.category_id).abs() for col in ("length_cm", "weight_g") if col in df]
            z = pd.concat(zs, axis=1).max(axis=1)
            res = (z > r["z"]).where(z.notna())
        elif c == "title_colour":
            tcol = df.title.map(lambda t: _title_colour(t))
            res = (tcol.notna() & df.colour.notna() & (tcol != df.colour) & (df.colour != "multicolour")).where(tcol.notna() & df.colour.notna())
        elif c == "brand_known":
            res = (~df.brand.isin(ctx["brands"])).where(df.brand.notna())
        elif c == "category_model":
            p, pr = ctx.get("model_pred"), ctx.get("model_proba")
            if p is None:
                res = pd.Series(np.nan, index=df.index)
            else:
                p, pr = df.sku.map(p), df.sku.map(pr)
                res = ((p != df.category_id) & (pr >= r["min_proba"])).where(p.notna())
        elif c == "stock_flag":
            res = (df.in_stock.astype(bool) != (df.stock_qty.fillna(0) > 0))
        elif c == "variant_family":
            g = df[df.parent_id.notna()].groupby("parent_id")
            bad = (g.brand.transform("nunique") > 1) | (g.category_id.transform("nunique") > 1)
            res = bad.reindex(df.index).where(df.parent_id.notna())
        elif c == "raw_colour_mapped":
            res = (df.colour_raw.notna() & df.colour_raw.map(norm_colour).isna()).where(df.colour_raw.notna())
        elif c == "unique":
            res = df[f].duplicated(keep=False)
        elif c == "no_duplicate":
            res = ctx["dup_flag"].reindex(df.index).fillna(False)
        elif c == "no_split_variant":
            res = ctx["split_flag"].reindex(df.index).fillna(False)
        else:
            raise ValueError(f"unknown check {c}")
        out[r["id"]] = res.astype("float")
    return out


def _title_colour(t):
    f = fold(t)
    for c in COLOURS:
        if re.search(rf"\b{c}\b", f):
            return c
    return None


def score(flags: pd.DataFrame) -> pd.Series:
    w = pd.Series({r["id"]: WEIGHT[r["severity"]] for r in load_rules()})
    applicable = flags.notna().mul(w, axis=1).sum(axis=1)
    failed = flags.fillna(0).mul(w, axis=1).sum(axis=1)
    return (1 - failed / applicable.replace(0, np.nan)).round(4)


def summary(flags: pd.DataFrame) -> pd.DataFrame:
    rules = pd.DataFrame(load_rules()).set_index("id")
    rules["applicable"] = flags.notna().sum()
    rules["failed"] = flags.fillna(0).sum().astype(int)
    rules["pass_rate"] = (1 - rules.failed / rules.applicable.replace(0, np.nan)).round(4)
    return rules.reset_index()[["id", "dimension", "severity", "description", "applicable", "failed", "pass_rate"]]


def issues_log(df: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    rules = {r["id"]: r for r in load_rules()}
    s = flags.stack()
    s = s[s == 1]
    log = s.reset_index().rename(columns={"level_1": "rule_id"})[["level_0", "rule_id"]]
    log["sku"] = df.loc[log.level_0, "sku"].values
    log["severity"] = log.rule_id.map(lambda i: rules[i]["severity"])
    log["description"] = log.rule_id.map(lambda i: rules[i]["description"])
    log["status"] = "open"
    return log.drop(columns="level_0")
