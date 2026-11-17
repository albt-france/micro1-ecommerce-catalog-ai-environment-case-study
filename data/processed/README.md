# data/processed: licence

These files are built by `src/build_catalog.py` and `src/build_schema.py`.

- They contain data derived from **Open Food Facts** (© Open Food Facts contributors, https://world.openfoodfacts.org).
  As a derivative database they are made available under the **Open Database License (ODbL 1.0)**:
  https://opendatacommons.org/licenses/odbl/1-0/ . Individual contents: Database Contents License.
- They also contain data derived from **Amazon Berkeley Objects** listings, credit Amazon.com, licensed **CC BY 4.0**
  (https://creativecommons.org/licenses/by/4.0/).
- Prices, stock levels, the `mkb` ("other platform") rows and the injected errors are **SIMULATED**.

| File | Content |
|---|---|
| `catalog.parquet` | clean catalogue, one row per SKU |
| `listings_raw_view.parquet` | every raw listing as delivered, with its canonical SKU and normalised values |
| `catalog_documents.jsonl` | one JSON document per parent product (validated by `schema/product.schema.json`) |
