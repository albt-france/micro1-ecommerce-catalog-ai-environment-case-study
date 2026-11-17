# Workflow: from raw sources to a graded environment

Each step reads the files of the previous one and writes its own. `python src/run_all.py` runs them all (about 25 minutes; `--skip-download` reuses `data/raw/`).

```
download_data ─► build_catalog ─► build_taxonomy ─► build_schema ─► evaluate_detection
                       │                                                  (opens the answer key)
                       └──────────► build_scenarios ─► pytest ─► run_baselines ─► dashboard · notebook · PDF
```

| Step | Script | Reads | Writes |
|---|---|---|---|
| 1 Download | `src/download_data.py` | official files and APIs | `data/raw/` (not published): ABO listings, Open Food Facts products, Google taxonomy, Online Retail II |
| 2 Catalogue | `src/build_catalog.py` | `data/raw/`, `taxonomy/*.yaml`, `rules.yaml` | `data/processed/catalog.parquet`, `listings_raw_view.parquet`, quality outputs, `taxonomy/brand_mapping.csv`, the hidden answer key |
| 3 Taxonomy | `src/build_taxonomy.py` | catalogue, hand labels | `taxonomy/*.csv`, classification accuracy, confusion, errors |
| 4 Schemas | `src/build_schema.py` | catalogue | DuckDB database (local), `catalog_documents.jsonl`, `mongo_validator.json`, integrity checks |
| 5 Detection | `src/evaluate_detection.py` | answer key, pipeline trace, flags | caught and fixed rates per error type |
| 6 Scenarios | `src/build_scenarios.py` | catalogue, raw view, Online Retail II | `scenarios/S001-S150.json`, calibration |
| 7 Tests | `pytest` | everything above | pass / fail |
| 8 Agents | `env/run_baselines.py` | scenarios, catalogue versions | `agent_results.csv`, episode examples |
| 9 Outputs | `src/build_dashboard.py`, `build_notebook.py`, `build_pdf.py` | outputs | dashboard, notebook, PDF and page images |

## Inside step 2

1. **Ingest** (`catalog/ingest.py`, `catalog/sources.py`): ABO JSON lines flattened (English value preferred, language kept); 13,000 listings sampled with seed 42 and per-type caps (phone cases are 44 % of ABO); Open Food Facts products; the SIMULATED other-platform export; SIMULATED prices and stock.
2. **Inject** (`catalog/inject.py`): 9 error types, 100 each, plus the 1,600 cross-platform duplicates by construction; the answer key is written and not read again.
3. **Normalise** (`catalog/enrich.py`, `catalog/normalize.py`): brands, colours, units, sizes, gender, device, quantities, pack counts.
4. **Classify** (`catalog/classify.py`, `catalog/taxonomy.py`): mapping, keywords, text model, overrides, Other.
5. **Match** (`catalog/dedupe.py`): duplicates → clusters → survivors; then variants → parents.
6. **Check** (`catalog/quality.py`): 26 rules on the raw view (before) and on the clean catalogue (after), scores, issues log, quality gate.

## Who does what in a real team

| Moment | Catalogue specialist | AI team |
|---|---|---|
| Before | agree taxonomy, templates, the fields agents may filter on | say which tasks and skills the environment must train |
| Each source | write the mapping (categories, brands, colours), check samples by hand | — |
| Each release | run the pipeline, read the quality report, clear the review queue, re-measure on the hand sets | rerun agents; compare scores to the previous catalogue version |
| Scenarios | write templates, review a sample by hand, keep the traps documented | define grading weights and step limits |

## Reproducibility

- One seed (42) for every sample and simulation; same inputs → same outputs.
- Every number in the report is read from `data/outputs/`; none is typed by hand.
- Raw downloads are not published; `download_data.py` rebuilds them from the official sources.
