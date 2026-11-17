"""Navigation taxonomy: load the YAML, give every node an id, resolve Google Product Taxonomy ids, and classify
products with rules (source category first, then keywords). The text classifier lives in build_taxonomy.py.
"""
from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd
import yaml

from config import RAW, TAXO

# Generic source types: their own label says little, so keyword rules decide, restricted to these groups.
GENERIC = {
    "SHOES": ["Shoes", "Clothing"], "BOOT": ["Shoes"], "SANDAL": ["Shoes"],
    "HOME": ["Living Room Furniture", "Bedroom Furniture", "Storage Furniture", "Home Decor", "Lighting", "Bedding", "Bath",
             "Window Treatments", "Storage & Organisation", "Kitchen Tools & Storage"],
    "HOME_BED_AND_BATH": ["Bedding", "Bath", "Window Treatments", "Home Decor"],
    "HOME_FURNITURE_AND_DECOR": ["Living Room Furniture", "Bedroom Furniture", "Dining Furniture", "Home Office Furniture",
                                 "Storage Furniture", "Home Decor", "Lighting", "Window Treatments", "Patio & Garden"],
    "FURNITURE": ["Living Room Furniture", "Bedroom Furniture", "Dining Furniture", "Home Office Furniture", "Storage Furniture"],
    "CHAIR": ["Living Room Furniture", "Dining Furniture", "Home Office Furniture", "Patio & Garden"],
    "TABLE": ["Living Room Furniture", "Dining Furniture", "Home Office Furniture", "Patio & Garden"],
    "HOME_LIGHTING_AND_LAMPS": ["Lighting"],
    "ACCESSORY": ["Accessories"], "FINENECKLACEBRACELETANKLET": ["Jewelry"], "FASHIONNECKLACEBRACELETANKLET": ["Jewelry"],
    "KITCHEN": ["Cookware", "Dinnerware & Drinkware", "Kitchen Tools & Storage", "Small Kitchen Appliances"],
    "ABIS_KITCHEN": ["Cookware", "Dinnerware & Drinkware", "Kitchen Tools & Storage", "Small Kitchen Appliances"],
    "GROCERY": ["Breakfast & Spreads", "Snacks & Sweets / Savoury Snacks", "Snacks & Sweets / Sweet Snacks", "Bakery & Fresh",
                "Dairy & Chilled", "Beverages", "Pantry", "Vitamins & Supplements"],
    "PANTRY": ["Pantry", "Breakfast & Spreads"],
    "HEALTH_PERSONAL_CARE": ["Vitamins & Supplements", "Personal Care", "Health Care", "Cleaning", "Home Decor"],
    "BEAUTY": ["Personal Care"], "OFFICE_PRODUCTS": ["Office Supplies"],
    "SPORTING_GOODS": ["Fitness", "Outdoor Recreation", "Dinnerware & Drinkware"],
    "OUTDOOR_LIVING": ["Patio & Garden", "Outdoor Recreation"], "PET_SUPPLIES": ["Pet Supplies"],
    "TOOLS": ["Tools", "Hardware"], "HARDWARE": ["Hardware", "Tools"], "SWATCH": ["Living Room Furniture"],
    "BISS": ["Hardware", "Office Supplies", "Cleaning"], "INSTRUMENT_PARTS_AND_ACCESSORIES": ["Audio & Video"],
}
TEMPLATES_FILE = TAXO / "category_attributes.yaml"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


@lru_cache(maxsize=1)
def gpt_table() -> pd.DataFrame:
    rows = []
    for line in (RAW / "google_product_taxonomy.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or " - " not in line:
            continue
        i, path = line.split(" - ", 1)
        rows.append((int(i), path.strip()))
    return pd.DataFrame(rows, columns=["gpt_id", "gpt_path"])


@lru_cache(maxsize=1)
def load() -> tuple[pd.DataFrame, dict]:
    """Returns (leaves, templates). Leaves: one row per leaf with ids, paths, rules and Google id."""
    y = yaml.safe_load((TAXO / "navigation_taxonomy.yaml").read_text(encoding="utf-8"))
    tpl = yaml.safe_load(TEMPLATES_FILE.read_text(encoding="utf-8"))
    gpt = gpt_table().set_index("gpt_path").gpt_id
    rows = []
    for di, d in enumerate(y["departments"], 1):
        for gi, g in enumerate(d["groups"], 1):
            for li, leaf in enumerate(g["leaves"], 1):
                levels = [d["name"]] + [p.strip() for p in g["name"].split("/")] + [leaf["name"]]
                if levels[1] == levels[2]:
                    levels = [levels[0], levels[1], levels[-1]] if len(levels) == 4 else levels
                rows.append(dict(
                    category_id=f"C{di:02d}{gi:02d}{li:02d}", name=leaf["name"], department=d["name"], group=g["name"],
                    path=" > ".join(levels), depth=len(levels), attrs=leaf["attrs"], abo=leaf.get("abo", []),
                    off=leaf.get("off_cat", []), kw=leaf.get("kw"), gpt_path=leaf["gpt"], gpt_id=gpt.get(leaf["gpt"])))
    leaves = pd.DataFrame(rows)
    return leaves, tpl


def nodes() -> pd.DataFrame:
    """All tree nodes (department, group, subgroup, leaf) with parent ids: the adjacency list used by schema.sql."""
    leaves, _ = load()
    out = {}
    for _, r in leaves.iterrows():
        parts = r.path.split(" > ")
        parent = None
        for depth in range(1, len(parts) + 1):
            p = " > ".join(parts[:depth])
            if depth == len(parts):
                nid = r.category_id
            else:
                nid = "N" + slug(p)[:40]
            out.setdefault(p, dict(node_id=nid, parent_id=parent, name=parts[depth - 1], path=p, level=depth,
                                   is_leaf=depth == len(parts), gpt_id=r.gpt_id if depth == len(parts) else None))
            parent = out[p]["node_id"]
    return pd.DataFrame(out.values())


def required_attrs() -> dict:
    leaves, tpl = load()
    return {r.category_id: tpl["templates"][r.attrs]["required"] for r in leaves.itertuples()}


class RuleClassifier:
    """Stage 1: direct mapping of the source category (ABO product_type, OFF query category).
    Stage 2: keyword rules on browse path + title, restricted to the groups allowed for generic source types."""

    def __init__(self):
        self.leaves, _ = load()
        self.by_abo = {t: r.category_id for r in self.leaves.itertuples() for t in r.abo}
        self.by_off = {t: r.category_id for r in self.leaves.itertuples() for t in r.off}
        self.kw = [(r.category_id, r.group, re.compile(r.kw, re.I)) for r in self.leaves.itertuples() if r.kw]

    def keyword(self, text: str, groups=None):
        for cid, grp, rx in self.kw:
            if groups and grp not in groups:
                continue
            if rx.search(text or ""):
                return cid
        return None

    def classify(self, source: str, source_type, node_path, title) -> tuple[str | None, str]:
        """Returns (category_id, method)."""
        if source == "off" and source_type in self.by_off:
            return self.by_off[source_type], "source category"
        if source_type in GENERIC or source_type not in self.by_abo:
            groups = GENERIC.get(source_type)
            # browse path first (it is the source's own navigation), then the title
            node_path = node_path if isinstance(node_path, str) else ""
            title = title if isinstance(title, str) else ""
            node = node_path.split("/", 2)[-1] if node_path else ""
            for txt in (node, title):
                cid = self.keyword(txt, groups) if txt else None
                if cid:
                    return cid, "keyword rule"
            if source_type in self.by_abo:
                return self.by_abo[source_type], "source category"
            return None, "unassigned"
        return self.by_abo[source_type], "source category"
