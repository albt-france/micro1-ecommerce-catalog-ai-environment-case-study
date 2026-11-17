"""Generate the 150 shopping scenarios (scenarios/S001.json ... S150.json) from the clean catalogue.
Personas and intents are SIMULATED; basket sizes, quantities per line and the seasonal mix of occasions are
calibrated on real transactions (UCI Online Retail II, see calibrate_baskets.py). Every scenario stores the
request the agent sees, the hidden constraints, the full set of acceptable answers, the grading rules and the trap.
Usage: python src/build_scenarios.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibrate_baskets import calibrate  # noqa: E402
from catalog.taxonomy import load  # noqa: E402
from config import OUT, PROCESSED, SCEN, SEED  # noqa: E402

PERSONAS = [  # SIMULATED, no personal data
    dict(id="P1", label="Budget-conscious student", price_focus="high", departments=["Grocery & Gourmet Food", "Office & School Supplies", "Electronics & Accessories"]),
    dict(id="P2", label="First-time home owner furnishing a flat", price_focus="medium", departments=["Home & Furniture", "Bed & Bath", "Kitchen & Dining"]),
    dict(id="P3", label="Parent organising family meals and outings", price_focus="high", departments=["Grocery & Gourmet Food", "Household Supplies"]),
    dict(id="P4", label="Regular runner replacing kit", price_focus="medium", departments=["Clothing, Shoes & Accessories", "Sports & Outdoors"]),
    dict(id="P5", label="Small-office manager restocking supplies", price_focus="medium", departments=["Office & School Supplies", "Household Supplies"]),
    dict(id="P6", label="Gift shopper in the end-of-year season", price_focus="low", departments=["Clothing, Shoes & Accessories", "Home & Furniture"]),
    dict(id="P7", label="Phone owner needing accessories", price_focus="high", departments=["Electronics & Accessories"]),
    dict(id="P8", label="Health-focused grocery shopper", price_focus="medium", departments=["Grocery & Gourmet Food", "Health & Personal Care"]),
]
# Shopper-facing noun per leaf (only these leaves are used in single-product scenarios)
NOUNS = {
    "Sofas & Couches": "sofa", "Armchairs & Accent Chairs": "armchair", "Ottomans & Poufs": "ottoman",
    "Coffee Tables, Side Tables & TV Stands": "coffee table", "Beds, Frames & Headboards": "bed frame",
    "Dining Chairs": "dining chair", "Office Chairs": "office chair", "Desks": "desk", "Area Rugs": "area rug",
    "Table & Floor Lamps": "lamp", "Ceiling & Wall Lights": "ceiling light", "Mirrors & Clocks": "wall clock",
    "Decorative Pillows & Cushion Covers": "cushion cover", "Sheets & Sheet Sets": "sheet set", "Pillowcases": "pillowcase",
    "Duvet Covers & Sets": "duvet cover", "Comforters & Duvets": "comforter", "Towels & Bath Mats": "towel set",
    "Curtains & Drapes": "curtain", "Frying Pans & Skillets": "frying pan", "Cups, Mugs & Glasses": "mug",
    "Sneakers & Trainers": "sneakers", "Running & Sports Shoes": "running shoes", "Formal & Dress Shoes": "formal shoes",
    "Boots": "boots", "Sandals & Slippers": "sandals", "Loafers & Moccasins": "loafers", "Backpacks": "backpack",
    "Handbags": "handbag", "Hats & Caps": "hat", "Necklaces & Pendants": "necklace", "Rings": "ring", "Earrings": "earrings",
    "Suitcases & Luggage": "suitcase", "Phone & Tablet Cases": "phone case", "Chargers & Cables": "charger",
    "Headphones & Speakers": "headphones", "Breakfast Cereals & Granola": "breakfast cereal", "Coffee": "coffee",
    "Tea": "tea", "Biscuits & Cookies": "biscuits", "Chocolate & Sweets": "chocolate", "Crisps, Crackers & Pretzels": "crisps",
    "Pasta & Noodles": "pasta", "Cooking Oils & Vinegar": "olive oil", "Jams & Preserves": "jam", "Cheese": "cheese",
    "Vitamins & Supplements": "vitamins", "Storage Boxes, Bins & Baskets": "storage box", "Shelves, Cabinets & Bookcases": "bookcase",
    "Dumbbells & Weights": "dumbbells", "Yoga Mats, Bands & Recovery": "yoga mat", "Pens & Writing Instruments": "pens",
    "Binders & Folders": "binder", "Light Bulbs & String Lights": "light bulb", "Wall Art, Posters & Decals": "wall art",
}
SIZED = {"shoes", "apparel", "bedding"}
OCCASIONS = [  # basket roles: (leaf, noun, units per person or fixed units)
    ("picnic", "Picnic for {n} people", [("Soft Drinks", "soft drink", "pp"), ("Crisps, Crackers & Pretzels", "crisps", "half"),
                                        ("Sandwiches & Ready Meals", "sandwich", "pp"), ("Fresh Fruit & Vegetables", "fruit", "half"),
                                        ("Biscuits & Cookies", "biscuits", 1)]),
    ("breakfast", "Breakfast restock for a household of {n}", [("Breakfast Cereals & Granola", "breakfast cereal", "half"),
                                                               ("Coffee", "coffee", 1), ("Fruit Juices", "fruit juice", "half"),
                                                               ("Jams & Preserves", "jam", 1), ("Tea", "tea", 1)]),
    ("movie", "Movie night for {n} friends", [("Crisps, Crackers & Pretzels", "crisps", "half"), ("Chocolate & Sweets", "chocolate", "pp"),
                                             ("Soft Drinks", "soft drink", "pp"), ("Nuts, Seeds & Trail Mix", "nuts", 1)]),
    ("pasta", "Pasta dinner for {n}", [("Pasta & Noodles", "pasta", "half"), ("Sauces, Soups & Condiments", "pasta sauce", "half"),
                                     ("Cheese", "cheese", 1), ("Cooking Oils & Vinegar", "olive oil", 1), ("Water", "water", "half")]),
    ("office", "Office restock for a team of {n}", [("Pens & Writing Instruments", "pens", "half"), ("Binders & Folders", "binder", "half"),
                                                  ("Paper, Notebooks & Envelopes", "notebook", "pp"), ("Coffee", "coffee", 1)]),
    ("cleaning", "Spring cleaning for a flat of {n}", [("Cleaning Products & Tools", "cleaning spray", 2), ("Trash Bags & Bins", "trash bags", 1),
                                                       ("Paper Towels & Tissues", "paper towels", "half"), ("Laundry & Dishwasher Detergents", "detergent", 1)]),
]
IMPOSSIBLE_NOUNS = ["lawn mower", "electric scooter", "kayak", "snowboard", "aquarium heater", "car tyre", "sewing machine",
                    "treadmill", "chainsaw", "surfboard", "trampoline", "violin", "telescope", "camera drone", "pressure washer"]
COUNTS = {"simple_search": 25, "multi_constraint": 30, "comparison": 20, "substitution": 20, "basket": 20, "ambiguous": 20, "no_answer": 15}
DIFF = {"simple_search": 1, "multi_constraint": 2, "comparison": 3, "substitution": 3, "basket": 4, "ambiguous": 4, "no_answer": 5}
OPT = {"simple_search": 3, "multi_constraint": 3, "comparison": 3, "substitution": 4, "ambiguous": 5, "no_answer": 2}


PAIRS = {"sneakers", "running shoes", "formal shoes", "boots", "sandals", "loafers", "earrings", "dumbbells"}
MASS = {"biscuits", "crisps", "vitamins", "pens", "coffee", "tea", "pasta", "cheese", "olive oil", "chocolate", "jam", "headphones"}


def art(noun: str) -> str:
    """Article for a shopper noun: 'a pair of sandals', 'some coffee', 'an armchair'."""
    if noun in PAIRS:
        return "a pair of " if noun not in ("dumbbells",) else "a set of "
    if noun in MASS:
        return "some " if noun != "headphones" else "a pair of "
    return "an " if noun[0] in "aeiou" else "a "


def money(x):
    return int(math.ceil(x))


class Gen:
    def __init__(self, cat: pd.DataFrame, raw: pd.DataFrame, calib: dict):
        self.rng = np.random.default_rng(SEED)
        L, tpl = load()
        self.leaf = L.set_index("category_id")
        self.cat = cat.assign(leaf=cat.category_id.map(self.leaf["name"]), tpl=cat.category_id.map(self.leaf["attrs"]))
        self.live = self.cat[(self.cat.listing_status == "active")]
        self.stock = self.live[self.live.in_stock]
        self.raw = raw
        self.calib = calib
        self.used = set()
        self.lower_titles = self.cat.title.astype(str).str.lower()
        self.month_w = np.array([calib["month_share"].get(str(m), calib["month_share"].get(m, 0)) for m in range(1, 13)], float)
        self.month_w /= self.month_w.sum()

    def persona_for(self, dept):
        ok = [p for p in PERSONAS if dept in p["departments"]] or PERSONAS
        return ok[int(self.rng.integers(len(ok)))]

    def match(self, cons, base=None):
        d = self.stock if base is None else base
        m = pd.Series(True, index=d.index)
        for k, v in cons.items():
            if k == "category_id":
                m &= d.category_id == v
            elif k == "max_price":
                m &= d.price <= v
            elif k in ("brand", "colour", "size", "material"):
                m &= d[k].astype(str).str.lower() == str(v).lower()
            elif k == "max_weight_g":
                m &= d.weight_g <= v
        return d[m]

    def trap(self, skus, cons):
        """Describe what can mislead an agent in the raw listings of the acceptable products."""
        r = self.raw[self.raw.canonical_sku.isin(skus)]
        notes = []
        if "colour" in cons:
            odd = r.colour_raw.dropna().astype(str)
            odd = odd[odd.str.lower() != cons["colour"]]
            if len(odd):
                notes.append(f"colour written as '{odd.iloc[0]}' in a source listing")
        if "brand" in cons:
            b = r.brand.dropna().astype(str)
            b = b[b != cons["brand"]]
            if len(b):
                notes.append(f"brand also spelled '{b.iloc[0]}'")
        if len(r) > len(skus):
            notes.append("the same product is listed twice across sources")
        return "; ".join(notes[:2]) or None

    def base(self, typ, i, persona, intent, request, cons, roles, expected="purchase", **kw):
        month = int(self.rng.choice(np.arange(1, 13), p=self.month_w))
        return dict(id=None, type=typ, difficulty=DIFF[typ], persona=persona, month=month, intent=intent, request=request,
                    constraints=cons, expected_action=expected,
                    acceptable_answers=dict(roles=roles, total_budget=kw.pop("total_budget", None)),
                    clarification=kw.pop("clarification", None),
                    grading=dict(criteria=kw.pop("criteria"), max_steps=25, optimal_steps=kw.pop("optimal_steps", OPT.get(typ, 6))),
                    trap=kw.pop("trap", None), data_tags=["SIMULATED persona and intent", "PUBLIC DATA products (ABO, Open Food Facts)",
                                                          "SIMULATED prices and stock"], **kw)

    def leaves_with(self, min_n=4, sized=None):
        g = self.stock.groupby("leaf").size()
        names = [n for n in NOUNS if g.get(n, 0) >= min_n]
        if sized is not None:
            names = [n for n in names if (self.leaf.set_index("name")["attrs"][n] in SIZED) == sized]
        return names

    # -------------------------------------------------------------- scenario types
    def simple(self):
        pairs = self.stock[self.stock.leaf.isin(NOUNS) & self.stock.brand.notna()].groupby(["leaf", "brand"]).size()
        pairs = pairs[pairs >= 1].reset_index()
        while True:
            r = pairs.iloc[int(self.rng.integers(len(pairs)))]
            if (r.leaf, r.brand) in self.used:
                continue
            self.used.add((r.leaf, r.brand))
            cons = {"category_id": self.stock[self.stock.leaf == r.leaf].category_id.iloc[0], "brand": r.brand}
            acc = self.match(cons)
            noun = NOUNS[r.leaf]
            req = self.rng.choice([f"I'm looking for {art(noun)}{noun} by {r.brand}.", f"Please find me {noun} from {r.brand}.",
                                   f"Can you get me {art(noun)}{noun} by {r.brand}?"])
            p = self.persona_for(acc.department.iloc[0])
            return self.base("simple_search", 0, p, f"buy {art(noun)}{noun} of a known brand", str(req), cons,
                             [dict(role=noun, skus=sorted(acc.sku), quantity=1)], criteria=["purchased item is in the acceptable set", "brand and category respected"],
                             trap=self.trap(acc.sku, cons))

    def multi(self):
        while True:
            a = self.stock[self.stock.leaf.isin(NOUNS) & self.stock.brand.notna()].sample(1, random_state=int(self.rng.integers(1e9))).iloc[0]
            cons = {"category_id": a.category_id}
            parts = []
            if pd.notna(a.colour) and a.colour not in ("multicolour", "clear"):
                cons["colour"] = a.colour; parts.append("colour")
            if a.tpl in SIZED and pd.notna(a["size"]):
                cons["size"] = a["size"]; parts.append("size")
            if len(parts) < 2 or self.rng.random() < 0.4:
                cons["brand"] = a.brand; parts.append("brand")
            cons["max_price"] = money(a.price * self.rng.uniform(1.05, 1.5))
            if len(cons) < 4 or (a.sku in self.used):
                continue
            self.used.add(a.sku)
            acc = self.match(cons)
            noun = NOUNS[a.leaf]
            col = f" in {cons['colour']}" if "colour" in cons else ""
            size = f", size {cons['size']}" if "size" in cons else ""
            br = f" by {cons['brand']}" if "brand" in cons else ""
            req = str(self.rng.choice([f"I need {art(noun)}{noun}{br}{col}{size}, under ${cons['max_price']}.",
                                       f"Looking for {art(noun)}{noun}{col}{br}{size}. Budget ${cons['max_price']} max.",
                                       f"Find me {art(noun)}{noun}{size}{col}{br} for less than ${cons['max_price']}."]))
            return self.base("multi_constraint", 0, self.persona_for(a.department), f"buy {art(noun)}{noun} matching several constraints", req, cons,
                             [dict(role=noun, skus=sorted(acc.sku), quantity=1)],
                             criteria=["purchased item is in the acceptable set", "every constraint respected (clean values)"],
                             trap=self.trap(acc.sku, cons))

    def comparison(self):
        while True:
            leaf = str(self.rng.choice(self.leaves_with(6)))
            d = self.stock[self.stock.leaf == leaf]
            cons = {"category_id": d.category_id.iloc[0]}
            kind = self.rng.choice(["cheapest", "cheapest_colour", "cheapest_brand", "lightest"], p=[0.3, 0.3, 0.2, 0.2])
            noun = NOUNS[leaf]
            if kind == "cheapest_colour":
                cols = d.colour.dropna().value_counts()
                cols = cols[(cols >= 3) & ~cols.index.isin(["multicolour", "clear"])]
                if not len(cols):
                    continue
                cons["colour"] = cols.index[int(self.rng.integers(len(cols)))]
            if kind == "cheapest_brand":
                bs = d.brand.dropna().value_counts()
                bs = bs[bs >= 3]
                if not len(bs):
                    continue
                cons["brand"] = bs.index[int(self.rng.integers(len(bs)))]
            pool = self.match(cons)
            key = (leaf, kind, cons.get("colour"), cons.get("brand"))
            if key in self.used or len(pool) < 3:
                continue
            if kind == "lightest":
                pool = pool[pool.weight_g.notna()]
                if len(pool) < 3:
                    continue
                best = pool[pool.weight_g <= pool.weight_g.min() * 1.02]
                req = f"Buy the lightest {noun} you have."
                crit = "purchased item has the lowest weight in the category (2 % tolerance)"
                cons_g = dict(cons, max_weight_g=round(float(best.weight_g.max()), 1))
            else:
                best = pool[pool.price <= pool.price.min() + 0.01]
                col = f" in {cons['colour']}" if "colour" in cons else ""
                br = f" by {cons['brand']}" if "brand" in cons else ""
                req = str(self.rng.choice([f"What's the cheapest {noun}{col}{br}? Buy it.", f"Buy the cheapest {noun}{br}{col} available."]))
                crit = "purchased item has the lowest price among matching in-stock items"
                cons_g = dict(cons, max_price=float(best.price.max()))
            self.used.add(key)
            return self.base("comparison", 0, self.persona_for(d.department.iloc[0]), f"compare {noun} options and buy the best one", req, cons_g,
                             [dict(role=noun, skus=sorted(best.sku), quantity=1)], criteria=[crit],
                             trap=self.trap(best.sku, cons) or "out-of-stock or held items can look cheaper in search results")

    def substitution(self):
        oos = self.live[~self.live.in_stock & self.live.leaf.isin(NOUNS)]
        while True:
            x = oos.sample(1, random_state=int(self.rng.integers(1e9))).iloc[0]
            if x.sku in self.used:
                continue
            budget = money(x.price * 1.25)
            cons = {"category_id": x.category_id, "max_price": budget}
            if pd.notna(x.colour) and x.colour != "multicolour":
                cons["colour"] = x.colour
            if x.tpl in SIZED and pd.notna(x["size"]):
                cons["size"] = x["size"]
            acc = self.match(cons)
            if len(acc) < 2:
                continue
            self.used.add(x.sku)
            same = f" in the same colour ({cons['colour']})" if "colour" in cons else ""
            sz = f", size {cons['size']}" if "size" in cons else ""
            req = (f"I wanted to buy SKU {x.sku} ({x.title[:70]}) but it is out of stock. Find me the closest in-stock "
                   f"alternative from the same category{same}{sz}, under ${budget}.")
            return self.base("substitution", 0, self.persona_for(x.department), "replace a sold-out product", req, cons,
                             [dict(role=NOUNS[x.leaf], skus=sorted(acc.sku), quantity=1)],
                             criteria=["purchased item is in stock, same category", "colour/size kept", "within budget"],
                             trap="the requested SKU is out of stock: add_to_cart fails on it", sold_out_sku=x.sku)

    def basket(self):
        dist = {int(k): v for k, v in self.calib["small_basket_lines_dist"].items() if 2 <= int(k) <= 5}
        ks, ws = np.array(list(dist)), np.array(list(dist.values()))
        while True:
            occ_name, occ_txt, roles = OCCASIONS[int(self.rng.integers(len(OCCASIONS)))]
            n_people = int(self.rng.choice([2, 3, 4, 4, 6]))
            n_roles = int(min(len(roles), max(2, self.rng.choice(ks, p=ws / ws.sum()))))
            pick = [roles[i] for i in sorted(self.rng.choice(len(roles), n_roles, replace=False))]
            spec, cheapest = [], 0.0
            ok = True
            for leaf, noun, q in pick:
                qty = n_people if q == "pp" else (max(1, n_people // 2) if q == "half" else int(q))
                d = self.stock[self.stock.leaf == leaf]
                if len(d) < 2:
                    ok = False; break
                spec.append((leaf, noun, qty, d))
                cheapest += float(d.price.min()) * qty
            key = (occ_name, n_people, tuple(p[0] for p in pick))
            if not ok or key in self.used:
                continue
            self.used.add(key)
            budget = money(cheapest * self.rng.uniform(1.4, 2.2))
            roles_out = []
            for leaf, noun, qty, d in spec:
                # an item is acceptable for a role if the rest of the basket can still fit the budget with it
                rest_min = cheapest - float(d.price.min()) * qty
                acc = d[d.price * qty + rest_min <= budget]
                roles_out.append(dict(role=noun, category_id=d.category_id.iloc[0], skus=sorted(acc.sku), quantity=qty))
            items = ", ".join(f"{r['quantity']} x {r['role']}" for r in roles_out[:-1]) + f" and {roles_out[-1]['quantity']} x {roles_out[-1]['role']}"
            req = f"{occ_txt.format(n=n_people)}: I need {items}. Keep the total under ${budget}."
            p = PERSONAS[2] if occ_name != "office" else PERSONAS[4]
            return self.base("basket", 0, p, f"build a basket for an occasion ({occ_name})", req, {}, roles_out,
                             total_budget=budget, criteria=["every role covered with the right quantity", "basket total within budget"],
                             optimal_steps=2 * len(roles_out) + 1,
                             trap="cheapest items per role are not always in stock; quantities differ per role")

    def ambiguous(self, slot):
        while True:
            if slot == "size":
                leaf = str(self.rng.choice(self.leaves_with(4, sized=True)))
                d = self.stock[(self.stock.leaf == leaf) & self.stock["size"].notna() & self.stock.brand.notna()]
                if len(d) < 2:
                    continue
                a = d.sample(1, random_state=int(self.rng.integers(1e9))).iloc[0]
                cons = {"category_id": a.category_id, "brand": a.brand, "size": a["size"]}
                noun = NOUNS[leaf]
                req = f"I need {art(noun)}{noun} by {a.brand}."
                cl = dict(slot="size", answer_text=f"Size {a['size']}.", why="size is a required attribute of the category")
            else:
                d = self.stock[(self.stock.leaf == "Phone & Tablet Cases") & self.stock.compatible_device.notna() & self.stock.brand.notna()]
                a = d.sample(1, random_state=int(self.rng.integers(1e9))).iloc[0]
                cons = {"category_id": a.category_id, "brand": a.brand}
                noun = "phone case"
                req = f"I need a {noun} by {a.brand}."
                cl = dict(slot="phone", answer_text=f"It's for a {a.compatible_device}.", why="a case only fits one device model")
            key = ("amb", a.sku)
            if key in self.used:
                continue
            acc = self.match(cons)
            if slot == "phone":
                acc = acc[acc.compatible_device.fillna("").str.lower() == str(a.compatible_device).lower()]
            if not len(acc):
                continue
            self.used.add(key)
            return self.base("ambiguous", 0, self.persona_for(a.department), f"buy {art(noun)}{noun} but a key detail is missing", req, cons,
                             [dict(role=noun, skus=sorted(acc.sku), quantity=1)], expected="ask", clarification=cl,
                             criteria=[f"asks about the {slot} before adding anything to the cart", "then buys an item that fits the answer"],
                             trap=f"many {noun} items match; only the {slot} disambiguates")

    def no_answer(self, kind):
        while True:
            if kind == "absent":
                free = [n for n in IMPOSSIBLE_NOUNS if ("absent", n) not in self.used and not self.lower_titles.str.contains(n, regex=False).any()]
                if not free:
                    kind = "budget"
                    continue
                noun = free[int(self.rng.integers(len(free)))]
                self.used.add(("absent", noun))
                req = f"Do you sell {art(noun)}{noun}? If so, buy one under $200."
                cons = {"_reason": f"no '{noun}' in the catalogue"}
                dept = "Sports & Outdoors"
            else:
                leaf = str(self.rng.choice(self.leaves_with(6)))
                d = self.stock[self.stock.leaf == leaf]
                cols = d.colour.dropna().value_counts()
                cols = cols[~cols.index.isin(["multicolour", "clear"])]
                if not len(cols):
                    continue
                c = cols.index[int(self.rng.integers(len(cols)))]
                low = float(d[d.colour == c].price.min())
                budget = max(1, int(low * 0.4))
                cons = {"category_id": d.category_id.iloc[0], "colour": c, "max_price": budget}
                if len(self.match(cons)) or ("nb", leaf, c) in self.used or low < 3:
                    continue
                self.used.add(("nb", leaf, c))
                noun = NOUNS[leaf]
                req = f"I need {art(c + ' ' + noun) if noun not in PAIRS | MASS else art(noun)}{c} {noun} under ${budget}."
                dept = d.department.iloc[0]
            return self.base("no_answer", 0, self.persona_for(dept), "ask for something the shop cannot provide", req, cons, [],
                             expected="no_match", criteria=["reports that nothing matches", "buys nothing"],
                             trap="similar products exist, but none meets every constraint" if kind != "absent" else "search still returns loosely related items")


def main():
    calib = calibrate()
    cat = pd.read_parquet(PROCESSED / "catalog.parquet")
    raw = pd.read_parquet(PROCESSED / "listings_raw_view.parquet")
    g = Gen(cat, raw, calib)
    out = []
    for _ in range(COUNTS["simple_search"]):
        out.append(g.simple())
    for _ in range(COUNTS["multi_constraint"]):
        out.append(g.multi())
    for _ in range(COUNTS["comparison"]):
        out.append(g.comparison())
    for _ in range(COUNTS["substitution"]):
        out.append(g.substitution())
    for _ in range(COUNTS["basket"]):
        out.append(g.basket())
    for i in range(COUNTS["ambiguous"]):
        out.append(g.ambiguous("phone" if i % 5 == 4 else "size"))
    for i in range(COUNTS["no_answer"]):
        out.append(g.no_answer("absent" if i % 3 == 0 else "budget"))
    out.sort(key=lambda s: s["difficulty"])
    SCEN.mkdir(exist_ok=True)
    for f in SCEN.glob("S[0-9][0-9][0-9].json"):
        f.unlink()
    for k, s in enumerate(out, 1):
        s["id"] = f"S{k:03d}"
        (SCEN / f"{s['id']}.json").write_text(json.dumps(s, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    summ = pd.DataFrame([dict(id=s["id"], type=s["type"], difficulty=s["difficulty"], persona=s["persona"]["id"],
                              n_acceptable=sum(len(r["skus"]) for r in s["acceptable_answers"]["roles"]),
                              roles=len(s["acceptable_answers"]["roles"]), has_trap=bool(s["trap"])) for s in out])
    summ.to_csv(OUT / "scenario_summary.csv", index=False)
    print(summ.groupby("type").agg(n=("id", "size"), median_acceptable=("n_acceptable", "median")).to_string())


if __name__ == "__main__":
    main()
