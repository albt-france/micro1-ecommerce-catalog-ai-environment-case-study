"""Shopping behaviour from real transactions (UCI Online Retail II, CC BY 4.0) used to calibrate the SIMULATED
personas and scenarios: basket size, units per line, cancellations, monthly seasonality, repeat buyers.
Only aggregates are kept (no customer identifiers). Usage: imported by build_scenarios.py, or run alone.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT, RAW  # noqa: E402


def calibrate() -> dict:
    df = pd.read_parquet(RAW / "online_retail_ii.parquet")
    df = df.rename(columns={"Customer ID": "customer"})
    df["InvoiceDate"] = pd.to_datetime(df.InvoiceDate)
    cancelled = df.Invoice.astype(str).str.startswith("C")
    sales = df[~cancelled & (df.Quantity > 0) & (df.Price > 0)].assign(line_value=lambda d: d.Price * d.Quantity)
    inv = sales.groupby("Invoice").agg(lines=("StockCode", "nunique"), units=("Quantity", "sum"),
                                       value=("line_value", "sum"),
                                       month=("InvoiceDate", "first"), customer=("customer", "first"))
    inv["month"] = inv.month.dt.month
    # retail-like baskets: the shop sells mostly to wholesalers; keep invoices a consumer could plausibly place
    small = inv[(inv.units <= 24) & (inv.lines <= 10)]
    lines_dist = small.lines.value_counts(normalize=True).sort_index()
    units_per_line = sales.Quantity.clip(upper=24)
    month = inv.groupby("month").size()
    cust = inv.dropna(subset=["customer"]).groupby("customer").size()
    res = {
        "invoices": int(len(inv)), "lines": int(len(sales)), "customers": int(cust.size),
        "period": f"{df.InvoiceDate.min():%Y-%m} to {df.InvoiceDate.max():%Y-%m}",
        "cancelled_line_share": round(float(cancelled.mean()), 4),
        "median_lines_per_invoice": float(inv.lines.median()),
        "median_lines_small_baskets": float(small.lines.median()),
        "share_small_baskets": round(len(small) / len(inv), 4),
        "small_basket_lines_dist": {int(k): round(float(v), 4) for k, v in lines_dist.items()},
        "median_units_per_line": float(sales.Quantity.median()),
        "share_lines_qty1": round(float((sales.Quantity == 1).mean()), 4),
        "units_per_line_dist": {int(k): round(float(v), 4) for k, v in units_per_line.value_counts(normalize=True).sort_index().head(12).items()},
        "month_share": {int(k): round(float(v / month.sum()), 4) for k, v in month.items()},
        "repeat_customer_share": round(float((cust > 1).mean()), 4),
        "median_basket_value_small": round(float(small.value.median()), 2),
    }
    (OUT / "basket_calibration.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    print(json.dumps(calibrate(), indent=1)[:1500])
