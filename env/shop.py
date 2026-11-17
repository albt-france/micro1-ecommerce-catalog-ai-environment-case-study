"""A small text shop an agent can use: search, filter, get_product, add_to_cart, remove_from_cart, view_cart,
ask_clarification, report_no_match, checkout. Every call is logged; the episode ends at checkout, at
report_no_match or after `max_steps` calls. This is a demonstration environment inspired by what the role
describes, not a micro1 product.

The shop can be backed by two views of the same catalogue (data/processed/):
  - "clean": the normalised, de-duplicated, quality-checked catalogue;
  - "raw":   the same SKUs as they arrive from the sources, before normalisation (and with the SIMULATED errors).
Grading always uses the clean values (env/grader.py), so the gap between the two views measures what catalogue
quality is worth to an agent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

PUBLIC_FIELDS = ["sku", "title", "brand", "category_path", "colour", "size", "material", "price", "in_stock"]
DETAIL_FIELDS = PUBLIC_FIELDS + ["parent_id", "length_cm", "width_cm", "height_cm", "weight_g", "net_qty", "net_unit",
                                 "pack_count", "labels", "description"]


@dataclass
class Step:
    n: int
    tool: str
    args: dict
    result_size: int


@dataclass
class Episode:
    scenario_id: str
    steps: list = field(default_factory=list)
    cart: dict = field(default_factory=dict)          # sku -> quantity
    questions: list = field(default_factory=list)     # (step, text)
    no_match: str | None = None
    checked_out: bool = False
    done: bool = False
    first_cart_step: int | None = None


class Shop:
    def __init__(self, catalog: pd.DataFrame, max_steps: int = 25, page_size: int = 10):
        self.cat = catalog.reset_index(drop=True).copy()
        for c in DETAIL_FIELDS:
            if c not in self.cat:
                self.cat[c] = None
        self.by_sku = self.cat.set_index("sku", drop=False)
        text = (self.cat.title.fillna("") + " " + self.cat.brand.fillna("") + " " + self.cat.category_path.fillna("")
                + " " + self.cat.colour.fillna("").astype(str) + " " + self.cat.material.fillna("").astype(str))
        self.vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=1, stop_words="english")
        self.X = self.vec.fit_transform(text.str.lower())
        self.max_steps, self.page_size = max_steps, page_size
        self.ep: Episode | None = None
        self.scenario: dict | None = None

    # ------------------------------------------------------------ episode control
    def reset(self, scenario: dict) -> str:
        self.scenario, self.ep = scenario, Episode(scenario["id"])
        return scenario["request"]

    def _log(self, tool, args, size=0):
        ep = self.ep
        if ep.done:
            raise RuntimeError("episode is over")
        ep.steps.append(Step(len(ep.steps) + 1, tool, args, size))
        if len(ep.steps) >= self.max_steps and tool not in ("checkout", "report_no_match"):
            ep.done = True

    @staticmethod
    def _rows(df):
        out = df[PUBLIC_FIELDS].replace({np.nan: None}).to_dict("records")
        for r in out:
            r["price"] = None if r["price"] is None else round(float(r["price"]), 2)
            r["in_stock"] = bool(r["in_stock"])
        return out

    # ------------------------------------------------------------ tools
    def search(self, query: str, page: int = 1) -> list[dict]:
        q = self.vec.transform([str(query).lower()])
        s = (self.X @ q.T).toarray().ravel()
        idx = np.argsort(-s, kind="stable")
        idx = idx[s[idx] > 0][(page - 1) * self.page_size: page * self.page_size]
        res = self._rows(self.cat.iloc[idx])
        self._log("search", {"query": query, "page": page}, len(res))
        return res

    def filter(self, query: str | None = None, category: str | None = None, brand: str | None = None,
               colour: str | None = None, size: str | None = None, material: str | None = None,
               min_price: float | None = None, max_price: float | None = None, in_stock: bool | None = None,
               sort: str = "relevance", limit: int = 20) -> list[dict]:
        df, m = self.cat, np.ones(len(self.cat), bool)
        low = lambda s: s.fillna("").astype(str).str.lower()  # noqa: E731
        if category:
            m &= low(df.category_path).str.contains(re.escape(category.lower())).values
        if brand:
            m &= (low(df.brand) == brand.lower()).values
        if colour:
            m &= (low(df.colour) == colour.lower()).values
        if size:
            m &= (low(df["size"]) == str(size).lower()).values
        if material:
            m &= low(df.material).str.contains(re.escape(material.lower())).values
        if min_price is not None:
            m &= (df.price.fillna(-1) >= min_price).values
        if max_price is not None:
            m &= (df.price.fillna(np.inf) <= max_price).values
        if in_stock is not None:
            m &= (df.in_stock.astype(bool) == in_stock).values
        order = np.arange(len(df))
        if query:
            s = (self.X @ self.vec.transform([query.lower()]).T).toarray().ravel()
            m &= s > 0
            order = np.argsort(-s, kind="stable")
        sub = df.iloc[order][m[order]]
        if sort == "price_asc":
            sub = sub.sort_values("price", kind="stable")
        elif sort == "price_desc":
            sub = sub.sort_values("price", ascending=False, kind="stable")
        res = self._rows(sub.head(limit))
        args = {k: v for k, v in dict(query=query, category=category, brand=brand, colour=colour, size=size,
                                      material=material, min_price=min_price, max_price=max_price,
                                      in_stock=in_stock, sort=sort).items() if v not in (None, "relevance")}
        self._log("filter", args, len(res))
        return res

    def get_product(self, sku: str) -> dict | None:
        self._log("get_product", {"sku": sku})
        if sku not in self.by_sku.index:
            return None
        r = self.by_sku.loc[sku, DETAIL_FIELDS].replace({np.nan: None}).to_dict()
        if r.get("parent_id"):
            r["variants"] = self.cat.loc[self.cat.parent_id == r["parent_id"], ["sku", "colour", "size", "price", "in_stock"]] \
                .replace({np.nan: None}).to_dict("records")
        return r

    def add_to_cart(self, sku: str, quantity: int = 1) -> dict:
        self._log("add_to_cart", {"sku": sku, "quantity": quantity})
        if sku not in self.by_sku.index:
            return {"ok": False, "error": "unknown sku"}
        if not bool(self.by_sku.loc[sku, "in_stock"]):
            return {"ok": False, "error": "out of stock"}
        self.ep.cart[sku] = self.ep.cart.get(sku, 0) + int(quantity)
        if self.ep.first_cart_step is None:
            self.ep.first_cart_step = len(self.ep.steps)
        return {"ok": True, "cart": dict(self.ep.cart)}

    def remove_from_cart(self, sku: str) -> dict:
        self._log("remove_from_cart", {"sku": sku})
        self.ep.cart.pop(sku, None)
        return {"ok": True, "cart": dict(self.ep.cart)}

    def view_cart(self) -> dict:
        self._log("view_cart", {})
        total = sum(float(self.by_sku.loc[s, "price"]) * q for s, q in self.ep.cart.items())
        return {"items": dict(self.ep.cart), "total": round(total, 2)}

    def ask_clarification(self, question: str) -> str:
        """The simulated shopper answers from the scenario; an unexpected question gets a neutral reply."""
        self._log("ask_clarification", {"question": question})
        self.ep.questions.append((len(self.ep.steps), question))
        cl = (self.scenario or {}).get("clarification") or {}
        if cl and cl.get("slot", "").lower() in question.lower():
            return cl["answer_text"]
        return "I don't mind, anything that fits my request."

    def report_no_match(self, reason: str) -> str:
        self._log("report_no_match", {"reason": reason})
        self.ep.no_match, self.ep.done = reason, True
        return "noted"

    def checkout(self) -> dict:
        self._log("checkout", {})
        self.ep.checked_out, self.ep.done = True, True
        return {"ok": bool(self.ep.cart), "items": dict(self.ep.cart)}
