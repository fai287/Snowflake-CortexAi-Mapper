"""Render PNG images for the README/docs from code (no external services).

Produces:
  docs/images/architecture.png       – medallion data-flow diagram
  docs/images/star_schema.png        – ANALYTICS star schema
  docs/images/dashboard_overview.png – preview charts from the sample dataset

Run:  python docs/diagrams/render_images.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
IMG = ROOT / "docs" / "images"
SAMPLE = ROOT / "data" / "sample"
BLUE, DARK, GREY, GREEN, AMBER, RED = "#1f6feb", "#0d419d", "#8b949e", "#2ecc71", "#f1c40f", "#e74c3c"


def _box(ax, x, y, w, h, text, fc, tc="white", fs=10):
    ax.add_patch(mpatches.FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
        linewidth=1.2, edgecolor=DARK, facecolor=fc))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            color=tc, fontsize=fs, weight="bold")


def _arrow(ax, x1, y1, x2, y2, label=""):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=GREY, lw=1.8))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, label, ha="center",
                va="bottom", fontsize=7.5, color="#444", style="italic")


def architecture() -> None:
    fig, ax = plt.subplots(figsize=(13, 6.2))
    ax.set_xlim(0, 13); ax.set_ylim(0, 6.2); ax.axis("off")
    ax.set_title("AI-Powered Insurance Data Platform — Architecture",
                 fontsize=14, weight="bold", color=DARK, pad=12)

    # Brokers
    _box(ax, 0.2, 4.6, 2.1, 0.6, "Broker Alpha · CSV", "#5b8def")
    _box(ax, 0.2, 3.7, 2.1, 0.6, "Broker Beta · JSON", "#5b8def")
    _box(ax, 0.2, 2.8, 2.1, 0.6, "Broker Gamma · PSV", "#5b8def")
    _box(ax, 3.0, 3.55, 1.6, 1.0, "Apache\nKafka", "#7d4cdb")
    _box(ax, 5.0, 3.55, 1.7, 1.0, "Snowpipe\nStreaming", "#7d4cdb")

    # Medallion
    _box(ax, 7.2, 5.2, 5.4, 0.66, "RAW  ·  VARIANT landing (lossless)", BLUE)
    _box(ax, 7.2, 4.3, 5.4, 0.66, "STAGING  ·  canonical + Cortex header mapping", BLUE)
    _box(ax, 7.2, 3.4, 5.4, 0.66, "ANALYTICS  ·  star schema + enrich + anomaly", BLUE)
    _box(ax, 7.2, 2.5, 5.4, 0.66, "SEMANTIC  ·  business views + Analyst model", BLUE)
    _box(ax, 7.2, 1.5, 5.4, 0.66, "GOVERNANCE  ·  DQ audit · logs · Cortex audit", "#475569")

    # Consumers
    _box(ax, 7.7, 0.4, 2.0, 0.7, "Streamlit\nDashboard", GREEN, "white", 9)
    _box(ax, 10.1, 0.4, 2.3, 0.7, "AI Agent\nNL → SQL", GREEN, "white", 9)

    for y in (4.85, 3.95, 3.05):
        _arrow(ax, 2.3, y + 0.05, 3.0, 4.05)
    _arrow(ax, 4.6, 4.05, 5.0, 4.05)
    _arrow(ax, 6.7, 4.05, 7.2, 5.4, "stream")
    _arrow(ax, 9.9, 5.2, 9.9, 4.96, "sp_raw_to_staging")
    _arrow(ax, 9.9, 4.3, 9.9, 4.06, "validate + enrich")
    _arrow(ax, 9.9, 3.4, 9.9, 3.16, "promote")
    _arrow(ax, 8.6, 2.5, 8.7, 1.1)
    _arrow(ax, 11.0, 2.5, 11.2, 1.1)
    _arrow(ax, 7.6, 2.1, 7.0, 1.85)  # governance -> dashboard hint

    ax.text(9.9, 0.05, "Kafka → Snowpipe Streaming → Snowflake (medallion) → Cortex → Streamlit",
            ha="center", fontsize=8.5, color="#555")
    fig.tight_layout()
    fig.savefig(IMG / "architecture.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def star_schema() -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.set_xlim(0, 11); ax.set_ylim(0, 6); ax.axis("off")
    ax.set_title("ANALYTICS — Star Schema", fontsize=14, weight="bold", color=DARK, pad=10)

    _box(ax, 4.3, 2.5, 2.4, 1.0, "FACT_PREMIUM\nFACT_CLAIM", BLUE, fs=10)
    dims = [
        (0.4, 4.6, "DIM_BROKER"), (8.2, 4.6, "DIM_CUSTOMER"),
        (0.4, 0.8, "DIM_PRODUCT"), (8.2, 0.8, "DIM_POLICY"),
    ]
    for x, y, name in dims:
        _box(ax, x, y, 2.4, 0.8, name, "#475569", fs=10)
        _arrow(ax, x + 1.2, y + (0.0 if y > 3 else 0.8), 5.5, 3.0)
    fig.tight_layout()
    fig.savefig(IMG / "star_schema.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def dashboard_overview() -> None:
    pol = pd.read_csv(SAMPLE / "policies.csv")
    clm = pd.read_csv(SAMPLE / "claims.csv")
    bp = pd.read_csv(SAMPLE / "broker_performance.csv")
    ing = pd.read_csv(SAMPLE / "ingestion_health.csv")

    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    fig.suptitle("Dashboard preview (generated from data/sample)", fontsize=14,
                 weight="bold", color=DARK)

    by_line = pol.groupby("PRODUCT_LINE")["PREMIUM_AMOUNT"].sum().sort_values(ascending=False)
    axes[0, 0].bar(by_line.index, by_line.values, color=BLUE)
    axes[0, 0].set_title("Premium revenue by product line")
    axes[0, 0].tick_params(axis="x", rotation=30)

    by_status = clm["CLAIM_STATUS"].value_counts()
    axes[0, 1].pie(by_status.values, labels=by_status.index, autopct="%1.0f%%",
                   colors=plt.cm.Blues(range(60, 220, 26)))
    axes[0, 1].set_title("Claims by status")

    axes[1, 0].bar(bp["BROKER_NAME"], bp["LOSS_RATIO"], color=[GREEN, AMBER, RED])
    axes[1, 0].set_title("Loss ratio by broker")
    axes[1, 0].tick_params(axis="x", rotation=15)

    cmap = {"HEALTHY": GREEN, "LAGGING": AMBER, "STALE": RED}
    axes[1, 1].barh(ing["BROKER_CODE"] + " / " + ing["RECORD_TYPE"],
                    ing["SECONDS_SINCE_LAST"],
                    color=[cmap[s] for s in ing["INGEST_STATUS"]])
    axes[1, 1].set_title("Ingestion lag (seconds since last message)")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(IMG / "dashboard_overview.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    architecture()
    star_schema()
    dashboard_overview()
    print(f"wrote images to {IMG}")


if __name__ == "__main__":
    main()
