"""Automatic grading of one episode against its scenario. Uses the clean catalogue as ground truth.

score = 0.6 x outcome + 0.3 x constraints + 0.1 x efficiency, success = outcome == 1
  outcome      purchase: every required role is covered by an acceptable SKU (and the basket budget holds);
               ask: the right detail was asked before anything was added to the cart, then the purchase is right;
               no_match: report_no_match was called and nothing was bought.
  constraints  share of the scenario constraints that the purchased items satisfy (clean values).
  efficiency   min(1, optimal_steps / steps used).
"""
from __future__ import annotations

import pandas as pd

from shop import Episode


def _check(item: pd.Series, key: str, val) -> bool:
    if key == "max_price":
        return float(item.price) <= val + 1e-9
    if key == "min_price":
        return float(item.price) >= val - 1e-9
    if key == "category_id":
        return item.category_id == val
    if key == "category_prefix":
        return str(item.category_id).startswith(val)
    if key in ("brand", "colour", "size", "material"):
        v = item.get(key)
        return (not pd.isna(v)) and str(v).lower() == str(val).lower()
    if key == "in_stock":
        return bool(item.in_stock) == val
    if key == "labels_contain":
        v = item.get("labels")
        return (not pd.isna(v)) and val in str(v)
    if key.startswith("max_") or key.startswith("min_"):
        col = key[4:]
        v = item.get(col)
        if v is None or pd.isna(v):
            return False
        return float(v) <= val if key.startswith("max_") else float(v) >= val
    return True


def grade(ep: Episode, scenario: dict, truth: pd.DataFrame) -> dict:
    """truth: clean values indexed by every SKU an agent can see (raw or clean), with its canonical_sku."""
    exp = scenario["expected_action"]
    acc = scenario["acceptable_answers"]
    cart = {}
    if ep.checked_out:
        for s, q in ep.cart.items():
            c = truth.at[s, "canonical_sku"] if s in truth.index else s
            cart[c] = cart.get(c, 0) + q
    items = truth.loc[[s for s in cart if s in truth.index]]
    reasons = []

    # ---------------- outcome
    outcome = 0.0
    if exp == "no_match":
        outcome = float(ep.no_match is not None and not cart)
        if ep.no_match is None:
            reasons.append("bought something although nothing matches" if cart else "did not report the missing product")
    else:
        if exp == "ask":
            asked = [q for st, q in ep.questions
                     if scenario["clarification"]["slot"] in q.lower() and (ep.first_cart_step is None or st < ep.first_cart_step)]
            if not asked:
                reasons.append("did not ask the clarifying question")
        roles = acc["roles"]
        covered = 0
        for r in roles:
            ok = set(r["skus"]) & set(cart)
            if ok and sum(cart[s] for s in ok) >= r.get("quantity", 1):
                covered += 1
            else:
                reasons.append(f"role '{r['role']}' not satisfied")
        budget_ok = True
        if acc.get("total_budget") is not None and len(items):
            total = float((items.price * pd.Series(cart).reindex(items.index)).sum())
            budget_ok = total <= acc["total_budget"] + 1e-9
            if not budget_ok:
                reasons.append("basket over budget")
        if not cart:
            reasons.append("no purchase" if ep.no_match is None else "reported no match although one exists")
        outcome = float(covered == len(roles) and budget_ok and bool(cart) and (exp != "ask" or not any("clarifying" in x for x in reasons)))

    # ---------------- constraints (on purchased items)
    cons = scenario.get("constraints") or {}
    if exp == "no_match":
        cscore = outcome
    elif not len(items):
        cscore = 0.0
    else:
        checks = [_check(it, k, v) for _, it in items.iterrows() for k, v in cons.items() if not k.startswith("_")]
        cscore = sum(checks) / len(checks) if checks else 1.0
        if checks and cscore < 1:
            bad = sorted({k for _, it in items.iterrows() for k, v in cons.items() if not k.startswith("_") and not _check(it, k, v)})
            reasons.append("constraint broken: " + ", ".join(bad))

    steps = max(1, len(ep.steps))
    eff = min(1.0, scenario["grading"]["optimal_steps"] / steps)
    if len(ep.steps) >= scenario["grading"]["max_steps"] and not (ep.checked_out or ep.no_match):
        reasons.append("ran out of steps")
    score = 0.6 * outcome + 0.3 * cscore + 0.1 * eff
    return {"scenario_id": scenario["id"], "type": scenario["type"], "difficulty": scenario["difficulty"],
            "success": bool(outcome == 1.0), "score": round(score, 4), "outcome": outcome,
            "constraints": round(cscore, 4), "efficiency": round(eff, 4), "steps": len(ep.steps),
            "failure": "; ".join(dict.fromkeys(reasons)) if outcome < 1 else ""}
