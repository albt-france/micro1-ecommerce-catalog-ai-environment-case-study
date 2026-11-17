"""Download the public sources into data/raw/ (not published). Polite: official files and APIs, one request
at a time, a pause between API calls, neutral user agent. Usage: python src/download_data.py
"""
from __future__ import annotations

import io
import json
import sys
import tarfile
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RAW, USER_AGENT  # noqa: E402

H = {"User-Agent": USER_AGENT}
ABO_URL = "https://amazon-berkeley-objects.s3.amazonaws.com/archives/abo-listings.tar"  # CC BY 4.0
GPT_URL = "https://www.google.com/basepages/producttype/taxonomy-with-ids.en-US.txt"
ORII_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"  # CC BY 4.0
OFF_URL = "https://search.openfoodfacts.org/search"  # ODbL 1.0
OFF_CATEGORIES = ["breakfast-cereals", "biscuits", "chocolates", "crisps", "breads", "cheeses", "yogurts",
                  "fruit-juices", "sodas", "waters", "coffees", "teas", "pastas", "rices", "tomato-sauces",
                  "jams", "olive-oils", "honeys", "nuts", "dried-fruits", "sandwiches", "fresh-fruits"]
OFF_FIELDS = ["code", "product_name", "product_name_en", "brands", "categories_tags", "quantity",
              "product_quantity", "product_quantity_unit", "labels_tags", "countries_tags", "lang",
              "nutriscore_grade", "allergens_tags", "serving_size"]


def fetch(url, dest: Path):
    if dest.exists() and dest.stat().st_size > 0:
        print("exists", dest.name)
        return
    print("downloading", url)
    with requests.get(url, headers=H, stream=True, timeout=120) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        tmp.replace(dest)


def abo():
    tar = RAW / "abo-listings.tar"
    fetch(ABO_URL, tar)
    out = RAW / "abo_listings.jsonl"
    if out.exists():
        return
    with tarfile.open(tar) as t, open(out, "w", encoding="utf-8") as fh:
        for m in t.getmembers():
            if m.name.endswith(".json.gz"):
                import gzip
                fh.write(gzip.decompress(t.extractfile(m).read()).decode("utf-8"))
    print("ABO listings ->", out.name)


def orii():
    z = RAW / "online_retail_ii.zip"
    fetch(ORII_URL, z)
    out = RAW / "online_retail_ii.parquet"
    if out.exists():
        return
    with zipfile.ZipFile(z) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".xlsx"))
        sheets = pd.read_excel(io.BytesIO(zf.read(name)), sheet_name=None, dtype={"Invoice": str, "StockCode": str})
    df = pd.concat(sheets.values(), ignore_index=True)
    df["Description"] = df.Description.astype("string")
    df["Invoice"], df["StockCode"] = df.Invoice.astype(str), df.StockCode.astype(str)
    df.to_parquet(out, index=False)
    print("Online Retail II ->", out.name, len(df))


def off(pages=3, size=100):
    out = RAW / "off_products.jsonl"
    if out.exists():
        return
    rows = []
    for cat in OFF_CATEGORIES:
        for p in range(1, pages + 1):
            q = f'categories_tags:"en:{cat}" AND (countries_tags:"en:united-kingdom" OR countries_tags:"en:united-states")'
            for attempt in range(3):
                r = requests.get(OFF_URL, params={"q": q, "page": p, "page_size": size, "fields": ",".join(OFF_FIELDS)},
                                 headers=H, timeout=60)
                if r.status_code == 200:
                    break
                time.sleep(20)
            r.raise_for_status()
            hits = r.json().get("hits", [])
            for h in hits:
                h["_query_category"] = cat
            rows += hits
            time.sleep(6)
            if len(hits) < size:
                break
        print(f"OFF {cat}: {sum(r_['_query_category'] == cat for r_ in rows)}")
    with open(out, "w", encoding="utf-8") as fh:
        for r_ in rows:
            fh.write(json.dumps(r_, ensure_ascii=False) + "\n")


def main():
    fetch(GPT_URL, RAW / "google_product_taxonomy.txt")
    abo()
    orii()
    off()
    print("done")


if __name__ == "__main__":
    main()
