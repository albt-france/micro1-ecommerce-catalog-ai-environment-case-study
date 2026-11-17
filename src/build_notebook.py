"""Build and execute the single analysis notebook (notebooks/catalog_environment.ipynb). It reads the pipeline
outputs and shows small, aggregated tables only. Usage: python src/build_notebook.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import ROOT  # noqa: E402

NB = ROOT / "notebooks" / "catalog_environment.ipynb"
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

CELLS = [
    md("# A realistic e-commerce environment for AI shopping agents\n"
       "Unified catalogue, navigation taxonomy, SQL and document schemas, 150 graded shopping scenarios.\n\n"
       "*Independent case study based on public data · not affiliated with or endorsed by micro1.* Real products are "
       "**PUBLIC DATA** (Amazon Berkeley Objects, Open Food Facts); the other-platform export, injected errors, prices, "
       "stock and personas are **SIMULATED**. This notebook reads the outputs of the pipeline (see README, *How to rerun*)."),
    code("import json\nfrom pathlib import Path\nimport pandas as pd\n"
         "ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\n"
         "OUT, PROC = ROOT / 'data' / 'outputs', ROOT / 'data' / 'processed'\npd.set_option('display.width', 140)\n"
         "stats = json.loads((OUT / 'catalog_stats.json').read_text())\ncat = pd.read_parquet(PROC / 'catalog.parquet')\n"
         "{k: stats[k] for k in ('raw_listings', 'by_source', 'clean_skus', 'parents', 'duplicates_merged', 'held_for_review')}"),
    md("## 1. Source profile\nHow each source fills the fields the shop needs (share of SKUs with a value, clean catalogue)."),
    code("fields = ['brand', 'colour', 'size', 'material', 'length_cm', 'weight_g', 'net_qty', 'description']\n"
         "cat.groupby('source')[fields].apply(lambda g: g.notna().mean()).round(2)"),
    code("pd.Series(stats['colour_methods']).rename('listings').to_frame().T  # where the clean colour comes from"),
    md("## 2. Quality before and after\n26 rules (completeness, validity, consistency, uniqueness), weighted score per SKU."),
    code("r = pd.read_csv(OUT / 'quality_rules_before_after.csv')\n"
         "r.assign(fail_before=(1 - r.pass_rate_before).round(3), fail_after=(1 - r.pass_rate_after).round(3))"
         "[['id', 'severity', 'description', 'fail_before', 'fail_after']]"),
    code("pd.read_csv(OUT / 'quality_by_category.csv').sort_values('quality').head(8)"),
    md("## 3. SIMULATED errors: caught and fixed\nThe answer key is opened only here, after the pipeline ran."),
    code("pd.read_csv(OUT / 'detection_by_type.csv')[['label', 'injected', 'caught_rate', 'fixed_rate']]"),
    code("json.loads((OUT / 'detection_summary.json').read_text())"),
    md("## 4. Taxonomy coverage and classification accuracy"),
    code("pd.read_csv(OUT / 'taxonomy_coverage.csv').sort_values('skus', ascending=False)"),
    code("ev = json.loads((OUT / 'classification_eval.json').read_text())\n"
         "pd.DataFrame(ev['precision_by_method'])"),
    code("{k: ev[k] for k in ('final_accuracy', 'final_accuracy_unambiguous', 'department_accuracy', 'rules_precision', "
         "'model_precision_proba_0.8', 'other_share_catalogue')}"),
    code("pd.read_csv(OUT / 'classification_errors.csv')[['manual_category', 'predicted_category', 'category_method', 'ambiguous_note']].head(10)"),
    md("## 5. Schemas"),
    code("sc = json.loads((OUT / 'schema_checks.json').read_text())\npd.DataFrame(sc['checks'])"),
    code("{k: sc[k] for k in ('documents', 'documents_invalid', 'avg_variants_per_document', 'row_counts')}"),
    md("## 6. Scenarios and calibration on real baskets (UCI Online Retail II)"),
    code("cal = json.loads((OUT / 'basket_calibration.json').read_text())\n"
         "{k: cal[k] for k in ('invoices', 'period', 'share_small_baskets', 'median_lines_small_baskets', 'share_lines_qty1', 'cancelled_line_share')}"),
    code("pd.read_csv(OUT / 'scenario_summary.csv').groupby('type').agg(n=('id', 'size'), difficulty=('difficulty', 'first'), "
         "median_acceptable=('n_acceptable', 'median'), with_trap=('has_trap', 'mean')).round(2)"),
    md("## 7. Reference agents in the environment"),
    code("res = pd.read_csv(OUT / 'agent_results.csv')\nres.groupby(['agent', 'view']).agg(success=('success', 'mean'), score=('score', 'mean'), steps=('steps', 'mean')).round(3)"),
    code("res[res.view == '4 clean'].pivot_table(index='type', columns='agent', values='success').round(2)"),
    code("f = res[(res.view == '4 clean') & ~res.success].failure.str.split('; ').explode().str.replace(r':.*', '', regex=True)\nf.value_counts().head(10)"),
    md("**Reading**: the same simple agent succeeds far more often on the clean catalogue than on the raw listings: "
       "normalised attributes make filters work, the taxonomy makes category queries work, and merging duplicates and "
       "holding price errors removes wrong answers. What is left fails on reasoning (ambiguous requests, baskets), "
       "which is what a training environment should isolate."),
]


def main():
    nb = nbf.v4.new_notebook()
    nb.cells = CELLS
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    ExecutePreprocessor(timeout=600, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(NB.parent)}})
    NB.parent.mkdir(exist_ok=True)
    nbf.write(nb, NB)
    print("notebook:", NB.relative_to(ROOT))


if __name__ == "__main__":
    main()
