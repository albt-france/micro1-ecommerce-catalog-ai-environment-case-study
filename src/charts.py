"""Report charts (matplotlib -> inline SVG). House style: light card background, blue = the data, grey = the
comparison, red = errors, dashed lines = thresholds, Segoe UI, one y-axis only."""
from __future__ import annotations

import io
import re

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, BLUE_L, BLUE_D = "#2A78D6", "#86B6EF", "#1C5CAB"
GRAY, GRAY_D, RED = "#C9C7BF", "#898781", "#D03B3B"
INK, INK2, GRID, CARD = "#0B0B0B", "#52514E", "#E1E0D9", "#FCFCFB"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 9.5, "text.color": INK2,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.facecolor": CARD, "figure.facecolor": CARD,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "axes.grid.axis": "x", "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": GRAY_D, "ytick.color": INK2, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False, "legend.fontsize": 9,
    "svg.fonttype": "none", "axes.axisbelow": True,
})


def fig(w_px, h_px):
    return plt.subplots(figsize=(w_px / 96, h_px / 96), dpi=96)


def svg(f) -> str:
    buf = io.StringIO()
    f.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.05)
    plt.close(f)
    s = buf.getvalue()
    s = s[s.find("<svg"):]
    s = re.sub(r'width="[\d.]+pt" height="[\d.]+pt"', 'width="100%" height="100%" preserveAspectRatio="xMidYMid meet"', s, 1)
    return re.sub(r"<metadata>.*?</metadata>", "", s, flags=re.S)


def hbar(labels, values, w=560, h=260, fmt="{:,.0f}", color=None, highlight=None, xlabel=""):
    f, ax = fig(w, h)
    y = np.arange(len(labels))[::-1]
    cols = [RED if (highlight and highlight(l, v)) else (color or BLUE) for l, v in zip(labels, values)]
    ax.barh(y, values, color=cols, height=0.62)
    mx = max(values) if len(values) else 1
    for yi, v in zip(y, values):
        ax.text(v + mx * 0.012, yi, fmt.format(v), va="center", fontsize=8.5, color=INK2)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, mx * 1.18)
    ax.set_xlabel(xlabel)
    return svg(f)




# ---------------------------------------------------------------- case-study charts
def grouped_hbar(labels, series: dict, w=560, h=280, fmt="{:.0%}", colors=None, xmax=None, legend=True):
    """Horizontal bars, one group per label, one bar per series (e.g. before / after)."""
    f, ax = fig(w, h)
    k = len(series)
    y = np.arange(len(labels))[::-1]
    bh = 0.8 / k
    colors = colors or [GRAY, BLUE, BLUE_D][:k]
    for j, (name, vals) in enumerate(series.items()):
        yy = y + (k - 1 - 2 * j) * bh / 2
        ax.barh(yy, vals, height=bh * 0.92, color=colors[j], label=name)
        for yi, v in zip(yy, vals):
            ax.text(v + (xmax or max(max(s) for s in series.values())) * 0.01, yi, fmt.format(v), va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, (xmax or max(max(s) for s in series.values())) * 1.15)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0)) if "%" in fmt else None
    if legend:
        ax.legend(loc="lower right", ncol=k)
    return svg(f)


def overlay_hist(a, b, w=520, h=240, bins=None, labels=("before", "after"), xlabel=""):
    f, ax = fig(w, h)
    bins = bins if bins is not None else np.linspace(0.4, 1.0, 25)
    ax.hist(a, bins=bins, color=GRAY, alpha=0.9, label=labels[0])
    ax.hist(b, bins=bins, color=BLUE, alpha=0.75, label=labels[1])
    ax.grid(axis="y"); ax.grid(axis="x", visible=False)
    ax.set_xlabel(xlabel)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k" if v >= 1000 else f"{v:.0f}"))
    ax.legend(loc="upper left")
    return svg(f)


def vbars(labels, values, w=480, h=230, fmt="{:.0%}", color=None, highlight=None, ylabel="", rotate=0):
    f, ax = fig(w, h)
    x = np.arange(len(labels))
    cols = [BLUE_D if (highlight is not None and i in highlight) else (color or BLUE) for i in range(len(labels))]
    ax.bar(x, values, color=cols, width=0.65)
    for xi, v in zip(x, values):
        ax.text(xi, v + max(values) * 0.02, fmt.format(v), ha="center", fontsize=8.5, color=INK2)
    ax.set_xticks(x, labels, rotation=rotate, ha="right" if rotate else "center")
    ax.grid(axis="y"); ax.grid(axis="x", visible=False)
    ax.set_ylim(0, max(values) * 1.18)
    ax.set_ylabel(ylabel)
    if "%" in fmt:
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    return svg(f)


def staircase(views, series: dict, w=560, h=270):
    """Success rate by catalogue version (x) for each agent (bars)."""
    f, ax = fig(w, h)
    x = np.arange(len(views))
    k = len(series)
    bw = 0.8 / k
    for j, ((name, vals), c) in enumerate(zip(series.items(), [GRAY, BLUE])):
        xx = x - 0.4 + bw * (j + 0.5)
        ax.bar(xx, vals, width=bw * 0.92, color=c, label=name)
        for xi, v in zip(xx, vals):
            ax.text(xi, v + 0.012, f"{v:.0%}", ha="center", fontsize=8.5, color=INK2)
    ax.set_xticks(x, views)
    ax.grid(axis="y"); ax.grid(axis="x", visible=False)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_ylim(0, max(max(v) for v in series.values()) * 1.2)
    ax.legend(loc="upper left")
    return svg(f)
