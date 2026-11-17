# Metadata specification

Every field of the clean catalogue (`data/processed/catalog.parquet`), with its type, unit, allowed values and where it comes from. The relational columns are in `schema/schema.sql`, the document fields in `schema/product.schema.json`.

## Product and variant fields

| Field | Type | Unit / allowed values | Required | Source → rule |
|---|---|---|---|---|
| `sku` | string | `ABO-…`, `OFF-…`, `MKB-…` | yes | source id with prefix; unique (U01) |
| `parent_id` | string | `P-…` | yes | variant grouping (catalogue standards §8) |
| `source`, `source_id` | string | abo, off, mkb | yes | ingestion |
| `title` | string | 10-200 characters recommended | yes | source title, spaces collapsed, all-capitals titles put in title case |
| `brand` | string | a reference spelling when known | yes (C02) | brand mapping table |
| `category_id` | string | `C` + 6 digits, a leaf of the taxonomy | yes (C03) | classification |
| `category_path` | string | `Department > Group > Leaf` | yes | taxonomy |
| `department` | string | 14 values | yes | taxonomy |
| `colour` | enum | black, white, grey, silver, gold, brown, beige, red, pink, orange, yellow, green, blue, purple, multicolour, clear | by template | colour normalisation (V02, K03, K08) |
| `size` | string | apparel XXS-3XL · EU shoe size (`42`, `40.5`) · bed size | by template | size normalisation (V03) |
| `material` | string | wood, metal, fabric, cotton, plastic, glass, ceramic, leather, faux leather, wool, gold, silver, rubber, or the source term | by template | material mapping |
| `gender` | enum | men, women, unisex, kids | shoes | title and browse path |
| `compatible_device` | string | device model, e.g. `Samsung Galaxy M31` | phone cases | title (`for …`) |
| `length_cm`, `width_cm`, `height_cm` | number | cm, > 0, ≤ 5,000 | furniture, rugs | source dimensions converted (K02) |
| `weight_g` | number | g, > 0, ≤ 5,000,000 | no | source weight converted (K02) |
| `net_qty`, `net_unit` | number, enum | g or ml; both or neither | food, health | source quantity or title (C07) |
| `capacity_ml` | number | ml | no | title (`1.5 L`, `16 oz`) |
| `pack_count` | integer | ≥ 1 | no | title (`pack of 4`, `6 ct`) |
| `labels` | list of strings | organic, vegan, vegetarian, gluten-free, fair-trade, no-added-sugar, palm-oil-free | no | Open Food Facts labels |
| `nutriscore` | enum | a-e | no | Open Food Facts |
| `allergens` | list of strings | Open Food Facts allergen tags | no | Open Food Facts |
| `style`, `pattern` | string | free text from the source | no | ABO |
| `description` | string | first 3 English bullet points | no (C06) | ABO bullet points |
| `keywords` | string | source search keywords | no | ABO |
| `gtin` | string | 8, 12, 13 or 14 digits, valid check digit | no | Open Food Facts barcode (V04) |
| `model_number` | string | source value | no | ABO, used for duplicate matching |
| `language` | string | ISO 639-1 code | yes | source locale of the title (V07) |
| `price`, `currency` | number, string | USD, ≥ 0, 2 decimals | yes (C04) | **SIMULATED** |
| `stock_qty`, `in_stock` | integer, boolean | `in_stock = stock_qty > 0` | yes (K06) | **SIMULATED** |
| `listing_status` | enum | active, held for review | yes | quality gate |
| `quality_score` | number | 0-1 | yes | rules engine |
| `category_method`, `brand_method`, `colour_method` | string | how the value was obtained | yes | pipeline trace |
| `duplicates_merged`, `is_variant_group` | integer, boolean | | yes | matching |

"By template" means required by the attribute template of the leaf category (`taxonomy/category_attributes.yaml`), checked by rule C05. The fill rate of each attribute per leaf is in `taxonomy/category_attributes.csv`.

## Attribute templates

| Template | Required | Optional |
|---|---|---|
| furniture | colour, material, length_cm | width_cm, height_cm, weight_g, style |
| textile | colour, material | length_cm, width_cm, pattern |
| rug | colour, length_cm | width_cm, material, pattern, style |
| decor, lighting | colour | material, style, dimensions |
| bedding | colour, size (bed) | material, pattern |
| cookware | material | colour, length_cm, weight_g |
| tableware | material | colour, capacity_ml, pack_count |
| appliance | colour | capacity_ml, weight_g, material |
| shoes | size (EU), colour, gender | material |
| apparel | size, colour | material, gender |
| accessory, bag | colour | material, gender / dimensions, capacity |
| jewelry | material | colour, gender |
| phone_case | compatible_device | colour, material |
| food, health | net_qty | labels, nutriscore, allergens, pack_count |
| electronics, household, office, sports, tools, pet, generic | (none) | colour, material, net_qty, pack_count… |

## Where attributes are stored

- **Relational**: filterable attributes are **columns** of `variant` with CHECK constraints (colour list, positive measures, `net_qty` and `net_unit` together). Long-tail attributes (`compatible_device`, `style`, `pattern`, `labels`, `nutriscore`, `allergens`) go to the attribute-value table `variant_attribute`. EAV is kept to that long tail because every EAV filter needs one join per attribute and stores values as text.
- **Document**: the same attributes are nested: shared ones at product level (`brand`, `category`, `gender`, `attributes`), variant-specific ones in `variants[]` (`colour`, `size`, `price`, `stock`, `dimensions_cm`, `net_quantity`, `sources`).

## Mapping to schema.org/Product

| Catalogue | schema.org |
|---|---|
| title | `name` |
| brand | `brand` (Brand.name) |
| category_path | `category` |
| colour, size, material | `color`, `size`, `material` |
| gtin | `gtin13` / `gtin` |
| weight_g, length/width/height | `weight`, `depth` / `width` / `height` (QuantitativeValue, unitCode GRM / CMT) |
| price, currency, in_stock | `offers` (Offer.price, priceCurrency, availability InStock / OutOfStock) |
| parent_id | `isVariantOf` (ProductGroup) |
