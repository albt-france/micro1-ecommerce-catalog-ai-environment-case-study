"""Two simple reference agents (plain Python rules, no language model). They only see the shopper's request text and
the shop tools, never the scenario's answer key.

KeywordAgent        search(request) -> first in-stock result -> buy. Never asks, never reports a missing product.
KeywordFilterAgent  parses budget, colour, size, brand, quantity and the product noun with regular expressions, then
                    uses filter() with those values; handles 'cheapest', baskets, sold-out substitutes, a missing
                    size (asks) and empty results (reports no match).
"""
from __future__ import annotations

import re

from shop import Shop

COLOURS = ["black", "white", "grey", "silver", "gold", "brown", "beige", "red", "pink", "orange", "yellow", "green",
           "blue", "purple", "multicolour", "clear"]
SIZE_NOUNS = ("shoe", "boot", "sneaker", "sandal", "trainer", "t-shirt", "shirt", "dress", "jacket", "sweater", "hoodie",
              "trousers", "jeans", "shorts", "skirt", "coat", "top")
FILLER = r"\b(i'm|i am|i|need|want|wanted|looking|look|for|please|show|me|find|get|buy|it|some|a|an|the|pair of|pair|of|" \
         r"from|by|in|under|set|some|sell|do|if|so|one|you|have|available|less|than|looking|for|below|max|budget|total|keep|my|to|with|that|is|any|one|and|can|you|would|like|also|colour|color|" \
         r"what's|whats|what|which|cheapest|lowest|price|priced|most|expensive|options?)\b"


def parse(text: str) -> dict:
    t = text.strip()
    out = {}
    m = re.search(r"(?:under|below|less than|up to|max(?:imum)?|budget(?: of)?|within)\s*\$\s*(\d+(?:\.\d+)?)", t, re.I) \
        or re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(?:max|or less|tops)", t, re.I)
    if m:
        out["max_price"] = float(m.group(1))
    m = re.search(r"\bsize\s+([A-Za-z0-9.]+)", t, re.I)
    if m:
        out["size"] = m.group(1).upper()
    m = re.search(r"\b(?:by|from)\s+([A-Z0-9][\w&'.+-]*(?:\s+(?:[A-Z0-9&][\w&'.+-]*))*)", t)
    if m:
        out["brand"] = m.group(1).strip(" .,")
    low = t.lower()
    cols = [c for c in COLOURS if re.search(rf"\b{c}\b", low)]
    if cols:
        out["colour"] = cols[0]
    if re.search(r"\b(cheapest|lowest price|least expensive)\b", low):
        out["sort"] = "price_asc"
    elif re.search(r"\b(most expensive|premium|highest price)\b", low):
        out["sort"] = "price_desc"
    noun = low
    for k in ("brand",):
        if k in out:
            noun = noun.replace(out[k].lower(), " ")
    noun = re.sub(r"\$\s*\d+(?:\.\d+)?|\bsize\s+\S+|\b\d+\b", " ", noun)
    noun = re.sub("|".join(rf"\b{c}\b" for c in COLOURS), " ", noun)
    noun = re.sub(FILLER, " ", noun)
    out["noun"] = re.sub(r"[^a-z\- ]+", " ", noun).split()
    out["noun"] = " ".join(out["noun"][:6])
    return out


class KeywordAgent:
    name = "keyword"

    def run(self, shop: Shop, request: str):
        res = shop.search(request)
        pick = next((r for r in res if r["in_stock"]), None)
        if pick:
            shop.add_to_cart(pick["sku"], 1)
        shop.checkout()


class KeywordFilterAgent:
    name = "keyword+filters"

    def _find(self, shop: Shop, p: dict, exclude=()):
        kw = {k: p[k] for k in ("brand", "colour", "size", "max_price") if k in p}
        res = [r for r in shop.filter(query=p["noun"] or None, in_stock=True, sort=p.get("sort", "relevance"), **kw)
               if r["sku"] not in exclude]
        return res

    def _single(self, shop: Shop, text: str, qty=1):
        p = parse(text)
        res = self._find(shop, p)
        if not res:
            shop.report_no_match("no in-stock product matches all the constraints")
            return False
        shop.add_to_cart(res[0]["sku"], qty)
        return True

    def run(self, shop: Shop, request: str):
        low = request.lower()
        # sold-out substitute: read the original product, then search its category
        m = re.search(r"\bsku\s+([A-Z0-9-]+)", request, re.I)
        if m and re.search(r"out of stock|sold out|unavailable", low):
            orig = shop.get_product(m.group(1))
            p = parse(request)
            if orig:
                leaf = str(orig.get("category_path") or "").split(">")[-1].strip()
                kw = {k: p[k] for k in ("max_price",) if k in p}
                res = shop.filter(query=orig["title"], category=leaf or None, in_stock=True, **kw)
                res = [r for r in res if r["sku"] != orig["sku"]]
                if res:
                    shop.add_to_cart(res[0]["sku"], 1)
                    shop.checkout()
                    return
            shop.report_no_match("no in-stock substitute found")
            return
        # basket: "I need 4 x cups, 2 x crisps and 1 x juice ... under $40"
        items = re.findall(r"(\d+)\s*x\s+([^,.;]+?)(?=,|\band\b|\.|;|$)", request)
        if len(items) >= 2:
            budget = parse(request).get("max_price")
            total = 0.0
            for q, phrase in items:
                p = parse(phrase)
                res = shop.filter(query=p["noun"] or None, in_stock=True, sort="price_asc", limit=10)
                if not res:
                    shop.report_no_match(f"nothing found for '{phrase.strip()}'")
                    return
                shop.add_to_cart(res[0]["sku"], int(q))
                total += (res[0]["price"] or 0) * int(q)
            if budget is not None and total > budget:
                shop.report_no_match("the cheapest basket is over budget")
                return
            shop.checkout()
            return
        # missing size for a sized product: ask first
        p = parse(request)
        if "size" not in p and any(n in p["noun"] for n in SIZE_NOUNS):
            ans = shop.ask_clarification("Which size do you need?")
            request = request + " size " + (re.findall(r"[A-Z0-9.]+$", ans.strip(" .")) or [""])[0]
        if self._single(shop, request):
            shop.checkout()
