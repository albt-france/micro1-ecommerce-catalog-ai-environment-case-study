# Scenario authoring guide

How to write a shopping scenario that trains or evaluates an agent well, how the 150 scenarios of this study are built, and the mistakes to avoid. Format: `schema/scenario.schema.json`. Generator: `src/build_scenarios.py`.

## Anatomy of a scenario

```json
{
 "id": "S026", "type": "multi_constraint", "difficulty": 2,
 "persona": {"id": "P4", "label": "Regular runner replacing kit"},
 "month": 11,
 "intent": "buy a pair of sandals matching several constraints",
 "request": "Find me a pair of sandals, size 39 in grey for less than $53.",
 "constraints": {"category_id": "C040106", "colour": "grey", "size": "39", "max_price": 53},
 "expected_action": "purchase",
 "acceptable_answers": {"roles": [{"role": "sandals", "skus": ["ABO-…", "ABO-…"], "quantity": 1}], "total_budget": null},
 "grading": {"criteria": ["purchased item is in the acceptable set", "every constraint respected (clean values)"],
             "max_steps": 25, "optimal_steps": 3},
 "trap": "colour written as 'Dove Suede' in a source listing"
}
```

| Part | Seen by the agent? | Purpose |
|---|---|---|
| `request` | **yes** | what a shopper would type; the only input |
| `clarification.answer_text` | only if the agent asks about `clarification.slot` | simulates the shopper's reply |
| `persona`, `intent`, `month` | no | realism, sampling, analysis by segment |
| `constraints` | no | checked on the purchased items with **clean** values |
| `acceptable_answers` | no | the **complete** set of right SKUs per role, plus the basket budget |
| `grading` | no | criteria in plain words, optimal and maximum steps |
| `trap` | no | what is designed to mislead; used to analyse failures |

## The seven types

| Type | N | Level | The agent must | How the right set is built |
|---|---|---|---|---|
| simple_search | 25 | 1 | find a product of a named brand in a category | every active, in-stock SKU of that brand and leaf |
| multi_constraint | 30 | 2 | respect 3-4 constraints together (brand, colour, size, budget) | anchored on a real product, budget 5-50 % above its price, then every SKU meeting all constraints |
| comparison | 20 | 3 | buy the cheapest (or lightest) match | the minimum, with ties (1 cent, or 2 % for weight) |
| substitution | 20 | 3 | replace a sold-out SKU with an in-stock one of the same category, colour and size, within budget | every in-stock SKU meeting those constraints (≥ 2) |
| basket | 20 | 4 | build a basket for an occasion (picnic, breakfast, office restock…) under a total budget | per role, every SKU that still lets the cheapest rest of the basket fit the budget |
| ambiguous | 20 | 4 | ask the missing detail (size, phone model) before buying, then buy what fits the answer | SKUs matching the hidden answer |
| no_answer | 15 | 5 | say nothing matches and buy nothing | empty; a test proves no active in-stock SKU meets the constraints |

## Calibration on real behaviour

Personas and intents are SIMULATED. Basket shapes follow **real invoices** (UCI Online Retail II, 40,077 invoices, Dec 2009 - Dec 2011): the number of lines in a basket is drawn from the distribution of small invoices (≤ 10 lines, ≤ 24 units), quantities per role depend on the number of people, and the month of each scenario follows the real monthly mix (November is the peak, 14 % of invoices). Only aggregates of that dataset are used.

## Grading

```
score   = 0.6 x outcome + 0.3 x constraints + 0.1 x efficiency
success = outcome == 1
```

- **outcome**: purchase types: every role covered by an acceptable SKU in the right quantity and the basket within budget; ambiguous: the right detail asked *before* anything was added to the cart, then a right purchase; no_answer: `report_no_match` called and nothing bought.
- **constraints**: share of constraints the purchased items satisfy, checked on clean values. A duplicate listing bought from the raw view counts as its canonical SKU.
- **efficiency**: `min(1, optimal_steps / steps used)`; an episode stops after 25 tool calls.
- Each failure gets a reason (`constraint broken: max_price`, `did not ask the clarifying question`, `reported no match although one exists`…), so results can be grouped by cause.

## What makes a good scenario

1. **One clear success condition.** The grader must be able to say yes or no without a human.
2. **List every right answer, not one.** An agent that finds another valid sofa must not be punished. Compute the set from the catalogue with the same constraints, never by hand.
3. **Constraints the catalogue can check.** Only ask for attributes that exist as clean fields (colour, size, price…). "A cosy sofa" cannot be graded.
4. **Natural wording, controlled content.** Vary the phrasing (several templates per type) but keep every constraint written in the request; hidden constraints the shopper never stated are unfair.
5. **A trap that teaches something.** Spelling variants in the source, the same product listed twice, a cheaper item that is held or out of stock, a sold-out SKU named in the request.
6. **Feasible.** A test proves each purchase scenario has at least one right answer in stock and that each basket's cheapest combination fits its budget.
7. **Impossible on purpose, and provably so.** For no_answer scenarios, a test proves nothing qualifies.
8. **Tagged.** PUBLIC DATA for the products, SIMULATED for persona, prices, stock.

## Frequent mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| One "gold" SKU as the answer | correct alternatives are graded as failures | compute the full acceptable set |
| Constraint not in the request | the agent cannot know it | every graded constraint appears in `request` |
| Grading on raw values | an agent is punished for the catalogue's errors | grade on clean values; map duplicates to their canonical SKU |
| Ambiguous request with a single obvious answer | it does not test asking | check that several products match before the clarification |
| Budget below the cheapest option by accident | a purchase scenario that cannot be won | the feasibility test |
| Grammar the generator breaks ("a sandals") | unrealistic text, easy to spot by a model | article helper per noun (`art()`), review a sample by hand |
| Out-of-stock items in the right set | the cart refuses them | right sets use active, in-stock SKUs only |
