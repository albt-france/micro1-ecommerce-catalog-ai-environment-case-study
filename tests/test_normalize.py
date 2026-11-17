"""Unit tests of the normalisation rules (src/catalog/normalize.py)."""
import pytest

from catalog.normalize import (brand_key, norm_apparel_size, norm_colour, norm_shoe_size, parse_quantity, title_key,
                               to_cm, to_g, to_ml)


@pytest.mark.parametrize("v,u,exp", [(10, "inches", 25.4), (1, "m", 100), (55, "millimeters", 5.5), (2, "feet", 60.96)])
def test_length(v, u, exp):
    assert to_cm(v, u) == pytest.approx(exp)


@pytest.mark.parametrize("v,u,exp", [(1, "pounds", 453.59), (16, "oz", 453.59), (2, "kilograms", 2000), (500, "g", 500)])
def test_weight(v, u, exp):
    assert to_g(v, u) == pytest.approx(exp, abs=0.01)


def test_volume_and_unknown_unit():
    assert to_ml(12, "fl oz") == pytest.approx(354.88, abs=0.01)
    assert to_ml(1.5, "l") == 1500
    assert to_cm(3, "parsecs") is None


@pytest.mark.parametrize("txt,exp", [("12 x 330 ml", (3960.0, "ml")), ("16 oz (454g)", (453.59, "g")),
                                     ("1,5 L", (1500.0, "ml")), ("250g", (250.0, "g")), ("12 fl oz", (354.88, "ml")),
                                     ("a box", (None, None))])
def test_parse_quantity(txt, exp):
    v, u = parse_quantity(txt)
    assert u == exp[1]
    assert v == pytest.approx(exp[0], abs=0.01) if exp[0] else v is None


@pytest.mark.parametrize("raw,exp", [("navy", "blue"), ("Dark Blue", "blue"), ("bleu marine", "blue"), ("Noir", "black"),
                                     ("Gris anthracite", "grey"), ("Espresso", "brown"), ("off-white", "white"),
                                     ("Multi", "multicolour"), ("", None), ("Wolf", None)])
def test_colour(raw, exp):
    assert norm_colour(raw) == exp


def test_sizes():
    assert norm_apparel_size("Medium") == "M"
    assert norm_apparel_size("x-large") == "XL"
    assert norm_shoe_size("UK 8") == 42.0
    assert norm_shoe_size("EU 42") == 42.0
    assert norm_shoe_size("US 9") == 42.0


def test_brand_and_title_keys():
    assert brand_key("AmazonBasics") == brand_key("Amazon Basics, Inc.")
    assert title_key("Rivet Modern Sofa, Navy Blue, 80 inch", "Rivet") == title_key("Modern Sofa Rivet - Grey", "Rivet")


def test_missing_values_stay_missing():
    from catalog.enrich import _material
    assert norm_colour(float("nan")) is None
    assert _material(float("nan")) is None
    assert brand_key(None) == ""
