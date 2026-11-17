"""Shared paths and constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"              # large downloads, never published (see .gitignore)
PROCESSED = ROOT / "data" / "processed"  # catalogue built by the pipeline (published, ODbL 1.0)
OUT = ROOT / "data" / "outputs"          # results of checks, models and agent runs (published)
HIDDEN = ROOT / "data" / "_hidden_truth.csv"  # answer key of injected errors, read only by the final evaluation
TAXO = ROOT / "taxonomy"
SCHEMA = ROOT / "schema"
SCEN = ROOT / "scenarios"
DOCS = ROOT / "docs"
DASH = ROOT / "dashboard"
SEED = 42
N_ABO = 13_000      # ABO listings sampled into the unified catalogue
N_OTHER = 2_400     # rows in the SIMULATED "other platform" export (overlaps ABO on purpose)

# Neutral client name: no personal contact in any request.
USER_AGENT = "catalog-env-study/1.0 (research script)"

FOOTER = "Independent case study based on public data · not affiliated with or endorsed by micro1"
SEEN_ON = "17 November 2026"


def ai_note() -> str:
    """The AI-use statement is written once, in the README (Methods); the PDF quotes it from there."""
    for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("- **AI-assisted workflow**"):
            return line.split("**: ", 1)[1].strip()
    raise ValueError("AI note not found in README.md")


for _p in (RAW, PROCESSED, OUT):
    _p.mkdir(parents=True, exist_ok=True)
