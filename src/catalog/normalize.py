"""Normalisation rules: units to SI (cm, g, ml), colours to a controlled list, sizes to one scale, brands through a
mapping table. Every function is pure and tested (tests/test_normalize.py). See docs/CATALOG_STANDARDS.md.
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------- units
LENGTH_TO_CM = {"cm": 1.0, "centimeters": 1.0, "centimetres": 1.0, "mm": 0.1, "millimeters": 0.1, "millimetres": 0.1,
                "m": 100.0, "meters": 100.0, "metres": 100.0, "in": 2.54, "inch": 2.54, "inches": 2.54, '"': 2.54,
                "ft": 30.48, "feet": 30.48, "foot": 30.48}
WEIGHT_TO_G = {"g": 1.0, "gr": 1.0, "grams": 1.0, "gram": 1.0, "kg": 1000.0, "kilograms": 1000.0, "kilogram": 1000.0,
               "mg": 0.001, "milligrams": 0.001, "lb": 453.592, "lbs": 453.592, "pounds": 453.592, "pound": 453.592,
               "oz": 28.3495, "ounces": 28.3495, "ounce": 28.3495}
VOLUME_TO_ML = {"ml": 1.0, "milliliters": 1.0, "millilitres": 1.0, "cl": 10.0, "dl": 100.0, "l": 1000.0, "liter": 1000.0,
                "liters": 1000.0, "litre": 1000.0, "litres": 1000.0, "fl oz": 29.5735, "floz": 29.5735, "fl. oz": 29.5735,
                "fluid ounces": 29.5735, "gallon": 3785.41, "gallons": 3785.41, "gal": 3785.41}


def _unit_key(u) -> str:
    return re.sub(r"\s+", " ", str(u or "").strip().lower().replace("_", " ")).rstrip(".")


def to_cm(value, unit):
    f = LENGTH_TO_CM.get(_unit_key(unit))
    return None if f is None or value is None else round(float(value) * f, 2)


def to_g(value, unit):
    f = WEIGHT_TO_G.get(_unit_key(unit))
    return None if f is None or value is None else round(float(value) * f, 2)


def to_ml(value, unit):
    f = VOLUME_TO_ML.get(_unit_key(unit))
    return None if f is None or value is None else round(float(value) * f, 2)


_QTY = re.compile(r"(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*(fl\.?\s*oz|kg|mg|g|gr|lbs?|oz|ml|cl|dl|l|litres?|liters?)\b", re.I)


def parse_quantity(text):
    """'12 x 330 ml' -> (3960.0, 'ml'); '16 oz (454g)' -> (453.59, 'g'); '1,5 L' -> (1500.0, 'ml').
    Returns (amount in g or ml, base unit) or (None, None)."""
    if not text:
        return None, None
    m = _QTY.search(str(text))
    if not m:
        return None, None
    n = int(m.group(1)) if m.group(1) else 1
    v = float(m.group(2).replace(",", ".")) * n
    u = _unit_key(m.group(3)).replace(" ", " ")
    u = "fl oz" if u.startswith("fl") else u
    if u in WEIGHT_TO_G:
        return to_g(v, u), "g"
    if u in VOLUME_TO_ML:
        return to_ml(v, u), "ml"
    return None, None


# ---------------------------------------------------------------- colours
COLOURS = ["black", "white", "grey", "silver", "gold", "brown", "beige", "red", "pink", "orange", "yellow", "green",
           "blue", "purple", "multicolour", "clear"]
COLOUR_SYNONYMS = {
    "black": ["black", "noir", "noire", "schwarz", "nero", "negro", "jet black", "onyx", "ebony", "charcoal black", "matte black", "zwart", "svart", "siyah", "preto"],
    "white": ["white", "blanc", "blanche", "weiss", "weiß", "bianco", "blanco", "ivory", "off white", "off-white", "cream", "snow", "wit", "vitt", "blanca", "crema", "chalk", "pearl", "bianca", "branco"],
    "grey": ["grey", "gray", "gris", "grau", "grigio", "charcoal", "graphite", "slate", "ash", "dark grey", "light grey",
             "dark gray", "light gray", "anthracite", "gunmetal", "smoke", "stone", "grijs", "grå", "dove", "pebble", "gris claro", "gris oscuro", "grigia"],
    "silver": ["silver", "argent", "silber", "argento", "plata", "chrome", "stainless steel", "nickel", "brushed nickel", "metallic", "plateado", "argentato", "níquel satinado", "niquel satinado", "pewter", "satin nickel"],
    "gold": ["gold", "or", "golden", "oro", "brass", "rose gold", "champagne", "bronze", "copper", "dorado", "dorato", "oro rosa"],
    "brown": ["brown", "marron", "braun", "marrone", "marrón", "walnut", "espresso", "chocolate", "coffee", "tan", "oak",
              "cherry", "mahogany", "camel", "cognac", "chestnut", "teak", "natural wood", "dark brown", "light brown", "barnwood", "wenge", "saddle", "bruin", "brun"],
    "beige": ["beige", "sand", "taupe", "khaki", "linen", "natural", "oatmeal", "nude", "ecru", "greige"],
    "red": ["red", "rouge", "rot", "rosso", "rojo", "burgundy", "maroon", "wine", "crimson", "scarlet", "bordeaux", "cherry red", "rood", "röd", "roja"],
    "pink": ["pink", "rose", "rosa", "blush", "fuchsia", "magenta", "coral", "salmon", "hot pink", "light pink", "roze", "rosado"],
    "orange": ["orange", "naranja", "arancione", "rust", "terracotta", "peach", "amber", "tangerine"],
    "yellow": ["yellow", "jaune", "gelb", "giallo", "amarillo", "mustard", "lemon", "ochre", "geel", "gul"],
    "green": ["green", "vert", "verte", "grün", "verde", "olive", "sage", "mint", "emerald", "teal", "forest green",
              "lime", "army green", "khaki green", "dark green", "light green", "turquoise", "groen", "grön"],
    "blue": ["blue", "bleu", "blau", "blu", "azul", "navy", "navy blue", "dark blue", "bleu marine", "marine", "royal blue",
             "light blue", "sky blue", "cobalt", "denim", "indigo", "aqua", "cyan", "midnight blue", "dusty blue", "azure", "marino", "marineblauw", "blauw", "blå", "azul marino"],
    "purple": ["purple", "violet", "lila", "viola", "morado", "lavender", "lilac", "plum", "mauve", "aubergine"],
    "multicolour": ["multicolour", "multicolor", "multi", "multi-colour", "multi-color", "multicoloured", "rainbow", "assorted", "mixed"],
    "clear": ["clear", "transparent", "crystal", "frosted", "transparente", "trasparente"],
}
_COLOUR_LOOKUP = {s: c for c, syns in COLOUR_SYNONYMS.items() for s in syns}


def fold(s) -> str:
    if s is None or s != s:          # None or NaN: missing, not the word "nan"
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s.lower())).strip()


_FOLDED_LOOKUP = {fold(k): v for k, v in _COLOUR_LOOKUP.items()}


def norm_colour(raw):
    """Map a free-text colour to the controlled list. Exact synonym first, then the longest synonym found inside
    the text ('Dark Navy Blue/White' -> blue). None when nothing matches (logged, never guessed)."""
    f = fold(raw)
    if not f:
        return None
    if f in _FOLDED_LOOKUP:
        return _FOLDED_LOOKUP[f]
    hits = [(len(k), v) for k, v in _FOLDED_LOOKUP.items() if re.search(rf"\b{re.escape(k)}\b", f)]
    if not hits:
        return None
    best = max(hits)[1]
    distinct = {v for _, v in hits}
    return "multicolour" if len(distinct) > 2 else best


# ---------------------------------------------------------------- sizes
APPAREL_SIZES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL"]
_SIZE_WORDS = {"extra small": "XS", "x-small": "XS", "xsmall": "XS", "small": "S", "petit": "S", "medium": "M", "moyen": "M",
               "large": "L", "grand": "L", "x-large": "XL", "xlarge": "XL", "extra large": "XL", "xx-large": "XXL",
               "xxlarge": "XXL", "2xl": "XXL", "xxxl": "3XL", "3x": "3XL", "2x": "XXL", "1x": "XL"}
UK_TO_EU_SHOE = {3: 36, 3.5: 36.5, 4: 37, 4.5: 37.5, 5: 38, 5.5: 38.5, 6: 39, 6.5: 40, 7: 40.5, 7.5: 41, 8: 42, 8.5: 42.5,
                 9: 43, 9.5: 44, 10: 44.5, 10.5: 45, 11: 46, 12: 47, 13: 48}


def norm_apparel_size(raw):
    s = fold(raw)
    if not s:
        return None
    if s.upper() in APPAREL_SIZES:
        return s.upper()
    return {fold(k): v for k, v in _SIZE_WORDS.items()}.get(s)


def norm_shoe_size(raw):
    """'UK 8' -> 42.0 (EU); 'EU 42' / '42' -> 42.0; 'US 9' (men) -> UK 8 -> 42.0."""
    s = fold(raw)
    m = re.search(r"(uk|eu|us)?\s*(\d+(?:\.\d)?)", s)
    if not m:
        return None
    sys_, v = m.group(1), float(m.group(2))
    if sys_ == "us":
        sys_, v = "uk", v - 1
    if sys_ == "uk" or (sys_ is None and v < 15):
        return float(UK_TO_EU_SHOE.get(v, round(v + 34, 1)))
    return v


# ---------------------------------------------------------------- brands
_LEGAL = re.compile(r"\b(inc|llc|ltd|limited|gmbh|co|corp|corporation|plc|sa|sas|brands?)\b")


def brand_key(raw) -> str:
    """Matching key for a brand: folded, legal suffixes and spaces removed ('AmazonBasics' == 'Amazon Basics, Inc.')."""
    return re.sub(r"\s+", "", _LEGAL.sub(" ", fold(raw)))


def title_key(title, brand=None, keep_numbers=False) -> str:
    """Matching key for a title: folded, brand, colour words, sizes and stop words removed, tokens sorted.
    keep_numbers=True for duplicate detection (a number often tells two products apart: 4 GB vs 8 GB)."""
    t = fold(title)
    if brand:
        t = t.replace(fold(brand), " ")
    stop = {"the", "a", "an", "and", "for", "with", "of", "in", "by", "set", "pack", "x", "cm", "inch", "inches", "mm"}
    toks = [w for w in t.split() if w not in stop and w not in _FOLDED_LOOKUP and (keep_numbers or not w.isdigit())
            and w.upper() not in APPAREL_SIZES and w not in _SIZE_WORDS]
    return " ".join(sorted(set(toks)))
