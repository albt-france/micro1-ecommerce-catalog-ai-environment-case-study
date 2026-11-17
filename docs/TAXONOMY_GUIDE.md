# Taxonomy guide

The navigation taxonomy of the demo shop: how it is built, how to classify a product, and the cases that need judgement. Source of truth: `taxonomy/navigation_taxonomy.yaml`; generated tables in `taxonomy/`.

## Structure

- **14 departments → 46 groups → 151 leaf categories**, 3 levels (4 for Grocery snacks: *Snacks & Sweets > Savoury Snacks > Crisps, Crackers & Pretzels*).
- Products are placed **only in leaves**. Departments and groups exist for navigation.
- Names are what a shopper would click: plural nouns, `&` for close siblings (*Pots, Saucepans & Cookware Sets*), no internal codes.
- **One `Other Products` leaf** for products the rules and the model cannot place with confidence (3.9 % of the catalogue). It is a review queue, not a destination.
- The tree was first drafted with 210 leaves, then leaves too thin to browse (fewer than ~20 products and close to a sibling) were merged: *Bean Bag Chairs* into *Armchairs & Accent Chairs*, *Dutch Ovens* and *Pressure Cookers* into *Pots, Saucepans & Cookware Sets*, and so on.

## Each leaf carries

| Field | Meaning |
|---|---|
| `gpt` | the closest **Google Product Taxonomy** category (2021-09-21); its numeric id is resolved at build time and the build fails if the path does not exist |
| `attrs` | an **attribute template** (`taxonomy/category_attributes.yaml`): required and optional attributes |
| `abo` | ABO `product_type` values that map directly to the leaf |
| `off_cat` | Open Food Facts categories that map directly |
| `kw` | a keyword regular expression on the source browse path and the title |

Several leaves can share a Google category (all eight shoe leaves map to *Apparel & Accessories > Shoes*, id 187, because Google has no shoe sub-categories). The mapping goes from our leaf to Google, not the reverse.

## How a product is classified (in this order)

1. **Source category mapping**: the source's own category (ABO product type, Open Food Facts category, the other platform's label) through the mapping table. Covers most products; 83 % precise on the hand sample.
2. **Keyword rules** for generic source types (`SHOES`, `HOME`, `GROCERY`, `ACCESSORY`...): the browse path first, then the title, only among the groups allowed for that source type (`GENERIC` in `src/catalog/taxonomy.py`). 83 % precise.
3. **Text model** (TF-IDF on words and character n-grams + logistic regression, trained on stage-1 products) for what is left: accepted at probability ≥ 0.40; for a generic source type it chooses only among the allowed groups.
4. **Override**: when the model contradicts the source category with probability ≥ 0.90, the model wins and the change is logged; between 0.80 and 0.90, rule K05 only flags it for review.
5. Otherwise → `Other Products`.

Accuracy on 200 products labelled by hand from title and brand only (`taxonomy/classification_manual_labels.csv`): **77.5 %** right leaf, 82.4 % without the 13 ambiguous items, 87.5 % right department. Errors are listed in `data/outputs/classification_errors.csv`.

## Rules for people classifying by hand

1. **Classify what the product is, not what it is used with.** A case for an Alexa remote is a TV/AV accessory, not a phone case.
2. **Function before material or shape.** A *steak knife set in a wooden box* is cutlery, not storage.
3. **The most specific leaf that fits all of the product.** A *daypack* goes to Backpacks, not Tote & Carry Bags.
4. **Sets go where the main item goes.** *Batteries + charger* → Batteries & Power.
5. **Food by what it is eaten as.** *Roasted cauliflower (ready to eat)* → Sandwiches & Ready Meals, not Vegetables. *Infant formula* → Baby & Feminine Care.
6. **If two leaves fit equally, write it down.** Use the leaf a shopper would look in first and add an `ambiguous_note`; ambiguous items are reported separately, never forced into the accuracy figure silently.
7. **If no leaf fits, use `Other Products` and propose a leaf** once five or more products share the gap.

## Edge cases met in this catalogue

| Product | Decision | Why |
|---|---|---|
| Skateboard | Other Products | no board-sports leaf; candidate for a new *Skate & Board Sports* leaf |
| Ski bag | Suitcases & Luggage | carried like luggage; *sports bags* would be a better leaf if volume grows |
| Drumsticks | Other Products | no music leaf in this catalogue |
| Pet training pads | Pet Harnesses, Carriers & Apparel | no pet-hygiene leaf; logged as a gap |
| Face coverings for kids | Safety Equipment | sold as protective gear; could be Health |
| Marking flags | Planters & Garden Watering | garden use dominates |
| Title is only a model name ('Movian Cinca') | Other Products | not enough information: ask the source for attributes |
| Office chair mat | Office Chairs | bought with the chair; could be Area Rugs |
| Salwar suit set | Dresses | the closest garment leaf; a *Traditional wear* leaf may be needed for Indian marketplaces |

## Changing the taxonomy

1. Edit `navigation_taxonomy.yaml` (keep names quoted; YAML reads an unquoted `off` as *false*, which is why the Open Food Facts key is `off_cat`).
2. Run `python src/build_catalog.py` and `python src/build_taxonomy.py`: the build fails on an unknown Google path; `source_mapping.csv` shows where every source category went.
3. Re-measure accuracy on the hand sample and add products to it when a new leaf is created.
