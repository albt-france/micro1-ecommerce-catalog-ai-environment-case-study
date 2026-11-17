"""The shop environment, the grader and the 150 scenarios."""
import json
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

from grader import grade
from shop import Shop

ROOT = Path(__file__).resolve().parents[1]
CAT = pd.read_parquet(ROOT / "data" / "processed" / "catalog.parquet")
ACTIVE = CAT[CAT.listing_status == "active"]
SCEN = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "scenarios").glob("S*.json"))]
TRUTH = CAT.assign(canonical_sku=CAT.sku).set_index("sku", drop=False)
SCHEMA = json.loads((ROOT / "schema" / "scenario.schema.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def shop():
    return Shop(ACTIVE)


def test_150_scenarios_with_the_planned_mix():
    assert len(SCEN) == 150
    mix = pd.Series([s["type"] for s in SCEN]).value_counts().to_dict()
    assert mix == {"multi_constraint": 30, "simple_search": 25, "comparison": 20, "substitution": 20, "basket": 20,
                   "ambiguous": 20, "no_answer": 15}
    assert [s["difficulty"] for s in SCEN] == sorted(s["difficulty"] for s in SCEN)


@pytest.mark.parametrize("s", SCEN, ids=[s["id"] for s in SCEN])
def test_scenario_is_valid_and_answerable(s):
    errors = [e.message for e in Draft202012Validator(SCHEMA).iter_errors(s)]
    assert not errors, errors
    roles = s["acceptable_answers"]["roles"]
    if s["expected_action"] == "no_match":
        assert roles == []
        cons = {k: v for k, v in s["constraints"].items() if not k.startswith("_")}
        if cons:   # nothing active and in stock satisfies the constraints
            m = ACTIVE[ACTIVE.in_stock & (ACTIVE.category_id == cons["category_id"])]
            m = m[(m.colour == cons["colour"]) & (m.price <= cons["max_price"])]
            assert m.empty
        return
    for r in roles:
        assert r["skus"], f"{s['id']} role {r['role']} has no acceptable answer"
        ok = ACTIVE.set_index("sku").loc[r["skus"]]
        assert ok.in_stock.all(), "acceptable answers must be in stock and active"
    if s["acceptable_answers"]["total_budget"]:
        cheapest = sum(ACTIVE.set_index("sku").loc[r["skus"]].price.min() * r["quantity"] for r in roles)
        assert cheapest <= s["acceptable_answers"]["total_budget"]


def test_tools_log_every_call(shop):
    s = next(x for x in SCEN if x["type"] == "simple_search")
    shop.reset(s)
    res = shop.filter(category=CAT.category_path.iloc[0].split(" > ")[-1], in_stock=True)
    assert all(r["in_stock"] for r in res)
    p = shop.get_product(res[0]["sku"])
    assert p["sku"] == res[0]["sku"]
    assert shop.add_to_cart(res[0]["sku"])["ok"]
    shop.checkout()
    assert [st.tool for st in shop.ep.steps] == ["filter", "get_product", "add_to_cart", "checkout"]
    assert shop.ep.done


def test_out_of_stock_cannot_be_added(shop):
    s = next(x for x in SCEN if x["type"] == "substitution")
    shop.reset(s)
    assert shop.add_to_cart(s["sold_out_sku"]) == {"ok": False, "error": "out of stock"}


def test_grader_rewards_a_correct_purchase_and_penalises_a_wrong_one(shop):
    s = next(x for x in SCEN if x["type"] == "multi_constraint")
    shop.reset(s)
    shop.add_to_cart(s["acceptable_answers"]["roles"][0]["skus"][0])
    shop.checkout()
    g = grade(shop.ep, s, TRUTH)
    assert g["success"] and g["constraints"] == 1.0
    shop.reset(s)
    wrong = ACTIVE[(ACTIVE.category_id != s["constraints"]["category_id"]) & ACTIVE.in_stock].sku.iloc[0]
    shop.add_to_cart(wrong)
    shop.checkout()
    g = grade(shop.ep, s, TRUTH)
    assert not g["success"] and g["constraints"] < 1


def test_grader_no_match_and_clarification(shop):
    s = next(x for x in SCEN if x["type"] == "no_answer")
    shop.reset(s)
    shop.report_no_match("nothing fits")
    assert grade(shop.ep, s, TRUTH)["success"]
    a = next(x for x in SCEN if x["type"] == "ambiguous")
    shop.reset(a)
    shop.add_to_cart(a["acceptable_answers"]["roles"][0]["skus"][0])   # buys without asking first
    shop.checkout()
    assert not grade(shop.ep, a, TRUTH)["success"]
    shop.reset(a)
    reply = shop.ask_clarification(f"Which {a['clarification']['slot']} do you need?")
    assert reply == a["clarification"]["answer_text"]
    shop.add_to_cart(a["acceptable_answers"]["roles"][0]["skus"][0])
    shop.checkout()
    assert grade(shop.ep, a, TRUTH)["success"]


def test_step_limit_ends_the_episode(shop):
    s = SCEN[0]
    shop.reset(s)
    with pytest.raises(RuntimeError):
        for _ in range(30):
            shop.search("chair")
    assert shop.ep.done and len(shop.ep.steps) == shop.max_steps
