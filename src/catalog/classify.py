"""Product classification into the navigation taxonomy.
Stage 1 rules (catalog/taxonomy.py): the source's own category through a mapping table, then keyword rules.
Stage 2 text model: TF-IDF (words 1-2 grams + character 3-5 grams) + logistic regression, trained on the products
the rules placed from a specific source category. It classifies what the rules left unassigned and, through
out-of-fold predictions, flags products whose text contradicts their source category (rule K05).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from catalog.taxonomy import GENERIC, RuleClassifier, load
from config import SEED

OTHER = None  # set from the taxonomy at import
MIN_PROBA_ASSIGN = 0.40   # below: the product goes to 'Other Products' and the review queue
MIN_PROBA_FLAG = 0.80     # K05: the model disagrees with the rules with at least this confidence
MIN_PROBA_FIX = 0.90      # the clean catalogue takes the model's category above this


def other_id() -> str:
    L, _ = load()
    return L.loc[L.name == "Other Products", "category_id"].iloc[0]


def mkb_type(label):
    if not isinstance(label, str) or not label.strip():
        return None
    return label.split("/")[-1].strip().upper().replace(" ", "_")


def rule_pass(df: pd.DataFrame) -> pd.DataFrame:
    rc = RuleClassifier()
    out = []
    for r in df.itertuples():
        st = mkb_type(r.source_type) if r.source == "mkb" else r.source_type
        src = "abo" if r.source == "mkb" else r.source
        if r.source == "mkb" and st is None:
            cid = rc.keyword(r.title)
            out.append((cid, "keyword rule" if cid else "unassigned"))
        else:
            out.append(rc.classify(src, st, r.node_path, r.title))
    return pd.DataFrame(out, index=df.index, columns=["rule_category", "rule_method"])


def model_text(df: pd.DataFrame) -> pd.Series:
    return (df.title_clean.fillna("") + " " + df.brand.fillna("") + " " + df.keywords.fillna("").str[:200]).str.lower()


class TextModel:
    def __init__(self):
        self.w = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=60000)
        self.c = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True, max_features=60000)
        self.m = LogisticRegression(C=8, max_iter=400)

    def _X(self, t, fit=False):
        if fit:
            return hstack([self.w.fit_transform(t), self.c.fit_transform(t)]).tocsr()
        return hstack([self.w.transform(t), self.c.transform(t)]).tocsr()

    def fit(self, text, y):
        self.m.fit(self._X(text, fit=True), y)
        return self

    def predict(self, text):
        p = self.m.predict_proba(self._X(text))
        return self.m.classes_[p.argmax(1)], p.max(1)


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Adds rule_category, rule_method, model_category, model_proba (out-of-fold for training rows),
    category_id (final) and category_method."""
    df = df.join(rule_pass(df))
    text = model_text(df)
    train = (df.rule_method == "source category") & df.source.isin(["abo", "off"]) & df.rule_category.notna()
    y = df.loc[train, "rule_category"]
    keep = y.map(y.value_counts()) >= 5
    tr_idx = y[keep].index
    df["model_category"], df["model_proba"] = None, np.nan
    skf = StratifiedKFold(n_splits=4, shuffle=True, random_state=SEED)
    for a, b in skf.split(tr_idx, y[keep]):
        m = TextModel().fit(text.loc[tr_idx[a]], y[keep].iloc[a])
        pc, pp = m.predict(text.loc[tr_idx[b]])
        df.loc[tr_idx[b], "model_category"], df.loc[tr_idx[b], "model_proba"] = pc, pp
    full = TextModel().fit(text.loc[tr_idx], y[keep])
    rest = df.index.difference(tr_idx)
    P = full.m.predict_proba(full._X(text.loc[rest]))
    cls = full.m.classes_
    df.loc[rest, "model_category"], df.loc[rest, "model_proba"] = cls[P.argmax(1)], P.max(1)

    oth = other_id()
    cat, how = df.rule_category.copy(), df.rule_method.copy()
    un = cat.isna()
    ok = un & (df.model_proba >= MIN_PROBA_ASSIGN)
    cat[ok], how[ok] = df.model_category[ok], "text model"
    # generic source types (e.g. SPORTING_GOODS): the model chooses among the leaves of the allowed groups only
    L, _ = load()
    stype = df.source_type.where(df.source != "mkb", df.source_type.map(mkb_type))
    pos = {i: k for k, i in enumerate(rest)}
    for i in df.index[un & ~ok & stype.isin(GENERIC)]:
        if i not in pos:
            continue
        allowed = np.isin(cls, L.loc[L.group.isin(GENERIC[stype[i]]), "category_id"].values)
        p = P[pos[i]] * allowed
        if p.sum() > 0 and p.max() / p.sum() >= 0.5:
            cat[i], how[i] = cls[p.argmax()], "text model (within source group)"
            ok[i] = True
    cat[un & ~ok], how[un & ~ok] = oth, "other (low confidence)"
    fix = ~un & (df.model_category != df.rule_category) & (df.model_proba >= MIN_PROBA_FIX)
    cat[fix], how[fix] = df.model_category[fix], "text model (overrode source)"
    df["category_id"], df["category_method"] = cat, how
    return df
