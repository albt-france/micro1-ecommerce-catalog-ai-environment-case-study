# Catalogue standards

How every product field is normalised, how duplicates and variants are handled, and which quality rules apply. Code: `src/catalog/`. Rules: `src/catalog/rules.yaml`.

## 1. Identifiers

| Field | Rule |
|---|---|
| `sku` | `<SOURCE>-<source id>`: `ABO-B07B4MD5CG`, `OFF-5060146370738`, `MKB-100042`. Unique (rule U01). |
| `parent_id` | `P-` + hash of brand, leaf category and family key for grouped variants; `P-<sku>` for a product with one variant. |
| `gtin` | Digits only, 8, 12, 13 or 14 long, valid check digit (rule V04). Open Food Facts barcodes are kept as GTIN. |
| Lineage | Every raw listing keeps its own SKU in `listings_raw_view.parquet` / table `source_listing`, with the `canonical_sku` it was merged into. Nothing is deleted. |

## 2. Units

All measures are stored in **SI units**: length, width and height in **cm**, weight in **g**, volume and capacity in **ml**. Conversion factors are in `normalize.py` (`LENGTH_TO_CM`, `WEIGHT_TO_G`, `VOLUME_TO_ML`), for example 1 in = 2.54 cm, 1 lb = 453.592 g, 1 oz = 28.3495 g, 1 fl oz = 29.5735 ml.

- Quantities written in text are parsed: `12 x 330 ml` → 3,960 ml, `16 oz (454g)` → 453.59 g, `1,5 L` → 1,500 ml.
- Food and health products store a **net quantity** (`net_qty` + `net_unit` g or ml).
- A value of 0, a negative value or a physically impossible one (over 50 m or 5 t) is stored as empty and counted (148 values in the current build).
- **Units are not repaired automatically.** A repair rule (an extreme outlier that becomes typical after one standard conversion) was tested: of 296 suggested repairs only 18 were real injected errors. Outliers are flagged by rule K02 and go to manual review; the suggestions are kept in `data/outputs/unit_repair_suggestions.csv`.

## 3. Colours

16 controlled values: black, white, grey, silver, gold, brown, beige, red, pink, orange, yellow, green, blue, purple, multicolour, clear.

1. The source colour field is matched exactly against a synonym table (English, French, German, Spanish, Italian, Dutch, Swedish, Turkish words): `navy`, `dark blue`, `bleu marine`, `marineblauw` → blue.
2. If no exact match, the longest synonym found inside the text wins (`Dark Navy Blue/White` → blue); three or more colour families → multicolour.
3. Placeholders (`Others`, `0`, `see image`, `Daylight` for bulbs) are treated as empty, not as a colour.
4. When the field is empty, the colour named in the last part of the title is used (`..., 96"W, Navy` → blue). The method is stored in `colour_method` (field, title, placeholder, unmapped, missing).
5. A word that maps to nothing (`Midnight`, `Lagoon`) is left empty and logged (rule K08). It is never guessed.

## 4. Sizes

| Scale | Values | Used by |
|---|---|---|
| Apparel | XXS, XS, S, M, L, XL, XXL, 3XL (`Medium` → M, `x-large` → XL) | apparel template |
| Shoes | EU size (UK and US converted: UK 8 → 42; US men = UK + 1; US women = UK + 2) | shoes template |
| Bed | Single, Twin, Double, Full, Queen, King, California King | bedding template |

Sizes are read from the size field or, failing that, from the title (`11 M US`, `Size L`). A size is kept only for categories whose template uses one.

## 5. Brands

- A **reference table** is built from the brands seen at least 3 times in the trusted sources (ABO, Open Food Facts): 492 brands in the current build.
- Every raw spelling is cleaned (`Amazon Brand - ` prefix removed, legal suffixes `Inc.`, `Ltd` removed, capitals fixed, Latin name inside brackets kept: `Amazonベーシック(AmazonBasics)` → `AmazonBasics`) and keyed (folded, spaces removed).
- Same key → the most frequent spelling (`variant`); otherwise a fuzzy match with ratio ≥ 90 on keys of 5+ characters (`fuzzy`); otherwise the brand is kept as `new`.
- The full mapping is published in `taxonomy/brand_mapping.csv`.

## 6. Languages

Titles are kept in their language; `language` stores the code (en, es, fr, de, it, ja...). 4,383 SKUs have a non-English title (rule V07, warning). Translation is out of scope: a non-English title is a fact about the source, not an error to hide.

## 7. Duplicates

Two listings are the **same product** when:

1. they share a GTIN, or the same brand + model number + colour + size; or
2. they are in the same brand × department block, the token-sort similarity of their title keys (brand, colour words, sizes and stop words removed, numbers kept) is **≥ 94**, and no attribute conflicts: the numbers in both titles agree, colours agree, sizes agree, lengths are within 10 %.

The threshold was chosen on **50 candidate pairs checked by hand** (`taxonomy/dedupe_manual_check.csv`): at 94, precision 80 % and recall 89 % on that sample; at 90 the precision falls to 44 %. Typical false matches: same family with another capacity (12.5 oz vs 10.8 oz, now blocked by the number rule), colour variants with unmapped colour words.

Pairs are merged into clusters. The **survivor** is a trusted-source record first (ABO, Open Food Facts), then the most complete one. Its empty fields are filled from the other members; stock is summed.

## 8. Variants

Listings of the same brand, same leaf category and same **family key** (title key without colours, sizes and numbers) that differ in colour or size become **variants of one parent**. A variant group with two different brands or categories fails rule K07.

## 9. Quality rules and score

26 rules in four dimensions (`rules.yaml`): completeness (C01-C07), validity (V01-V08), consistency (K01-K08), uniqueness (U01-U03). Severity weights: error 3, warning 2, info 1.

**Quality score of a SKU** = 1 − (weight of failed rules / weight of applicable rules). A rule that does not apply (no barcode for V04, not a food for C07) is left out of both.

| Rule | What it checks |
|---|---|
| C05 | every attribute the category template requires is filled |
| K01 | price within 3.5 robust z-scores (log scale) of its leaf category |
| K02 | size and weight plausible for the leaf category (same method) |
| K04 | brand equals a reference spelling exactly |
| K05 | the text classifier does not place the product elsewhere with ≥ 80 % confidence |
| U02 / U03 | not a duplicate of another SKU / not a split variant |

**Quality gate**: a SKU with a missing or non-positive price (C04, V01), a price outlier (K01) or an inconsistent stock flag (K06) is published with `listing_status = held for review` and does not appear in the shop.

Every failure is written to `data/outputs/issues_log.csv` (SKU, rule, severity, status).

## 10. Injected errors (evaluation only)

2,400 SIMULATED errors of 9 types are injected into a copy of the raw data; the answer key (`data/_hidden_truth.csv`, not published, rebuilt by the pipeline) is read only by `src/evaluate_detection.py`. Results per type are in `data/outputs/detection_by_type.csv`.
