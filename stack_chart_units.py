# stack_chart_v2.py
#
# 1) Reads stage breakdown CSV (default: out_recipe18_stage_breakdown.csv)
#    and aggregates stages into 3 buckets: upstream / power / operation.
# 2) Reads KR vs non-KR split CSV (default: out_recipe18_split_KR_vs_nonKR.csv).
# 3) For each target indicator (GWP, PM2.5, HOFP), creates a grouped chart:
#       per scenario: 3 bars
#         - a stacked bar (upstream/power/operation)
#         - KR total (single bar)
#         - non-KR total (single bar)
#
# NOTE: This script DOES NOT output share(%) charts.
#
# Run:
#   python stack_chart_v2.py
#   python stack_chart_v2.py --stage-csv out_recipe18_stage_breakdown.csv --split-csv out_recipe18_split_KR_vs_nonKR.csv

import argparse
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

DEFAULT_STAGE_CSV = "out_recipe18_stage_breakdown.csv"
DEFAULT_SPLIT_CSV = "out_recipe18_split_KR_vs_nonKR.csv"

# 원하는 시나리오 순서 (없으면 CSV에 있는 순서로)
SCENARIOS_ORDER = ["EV_1KM", "GASOLINE_1KM", "DIESEL_1KM", "E_GASOLINE_1KM"]

# 지표 선택: category 문자열에 포함될 토큰 (대소문자 무시)

# Units per indicator (ReCiPe 2016 Midpoint (H))
UNITS = {
    "GWP": "kg CO2-eq",
    "PM2.5": "kg PM2.5-eq",
    "HOFP": "kg NOx-eq",
}

TARGETS = {
    "GWP": ["GWP"],
    "PM2.5": ["PMFP", "PM2.5"],
    "HOFP": ["HOFP"],
}

# ------------------------------------------------------------
# stage mapping -> 3 buckets
# ------------------------------------------------------------
UPSTREAM_STAGES = {"raw_material", "transport", "other", "upstream"}
POWER_STAGES = {"refining_or_power", "refining", "power_generation", "power"}
OP_STAGES = {"vehicle_operation", "operation"}


def norm_stage3(stage: str) -> str:
    s = (stage or "").strip().lower()
    if s in UPSTREAM_STAGES:
        return "upstream"
    if s in POWER_STAGES:
        return "power"
    if s in OP_STAGES:
        return "operation"
    # 애매한 background/market류는 upstream으로 흡수
    return "upstream"


def pick_rows_by_tokens(df: pd.DataFrame, tokens: list[str]) -> pd.DataFrame:
    pat = "(" + "|".join(re.escape(t) for t in tokens) + ")"
    mask = df["category"].astype(str).str.contains(pat, case=False, na=False, regex=True)
    return df[mask].copy()


def build_stage_matrix(df_metric: pd.DataFrame, scenarios: list[str]) -> pd.DataFrame:
    """Return dataframe indexed by scenario with columns [upstream, power, operation]."""
    tmp = df_metric.copy()
    tmp["stage3"] = tmp["stage"].map(norm_stage3)
    tmp["contribution"] = pd.to_numeric(tmp["contribution"], errors="coerce").fillna(0.0)

    p = (
        tmp.groupby(["scenario", "stage3"], as_index=False)["contribution"]
        .sum()
        .pivot(index="scenario", columns="stage3", values="contribution")
        .fillna(0.0)
    )

    for col in ["upstream", "power", "operation"]:
        if col not in p.columns:
            p[col] = 0.0
    p = p[["upstream", "power", "operation"]]
    return p.reindex(scenarios)


def build_split_vectors(df_split_metric: pd.DataFrame, scenarios: list[str]) -> pd.DataFrame:
    """Return dataframe indexed by scenario with columns [KR, non_KR]."""
    tmp = df_split_metric.copy()
    for c in ["KR", "non_KR"]:
        tmp[c] = pd.to_numeric(tmp[c], errors="coerce").fillna(0.0)

    p = tmp.set_index("scenario")[["KR", "non_KR"]]
    return p.reindex(scenarios).fillna(0.0)


def plot_grouped(stage_mat: pd.DataFrame, split_vec: pd.DataFrame, title: str, out_png: str, unit: str) -> None:
    scenarios = list(stage_mat.index)
    n = len(scenarios)
    x = np.arange(n)

    width = 0.26
    x_stack = x - width
    x_kr = x
    x_non = x + width

    fig, ax = plt.subplots(figsize=(11, 4.2))

    # --- stacked bar (stage breakdown) ---
    upstream = stage_mat["upstream"].values
    power = stage_mat["power"].values
    operation = stage_mat["operation"].values

    b1 = ax.bar(x_stack, upstream, width, label="stack: upstream")
    b2 = ax.bar(x_stack, power, width, bottom=upstream, label="stack: power")
    b3 = ax.bar(x_stack, operation, width, bottom=upstream + power, label="stack: operation")

    # --- KR / non-KR bars (totals) ---
    kr = split_vec["KR"].values
    non = split_vec["non_KR"].values
    ax.bar(x_kr, kr, width, label="KR total")
    ax.bar(x_non, non, width, label="non-KR total")

    ax.set_title(f"{title} — stacked(stage) vs KR/non-KR totals")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=0)
    ax.set_xlabel("scenario")
    ax.set_ylabel(unit)

    # light grid for readability
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.5)

    # Legend: keep it compact
    ax.legend(ncol=2, fontsize=9, frameon=True)

    plt.tight_layout()
    plt.savefig(out_png, dpi=220)
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage-csv", default=DEFAULT_STAGE_CSV, help="Stage breakdown CSV")
    ap.add_argument("--split-csv", default=DEFAULT_SPLIT_CSV, help="KR vs non-KR split CSV")
    ap.add_argument("--out-prefix", default="stage3", help="Output prefix")
    args = ap.parse_args()

    df_stage = pd.read_csv(args.stage_csv)
    df_split = pd.read_csv(args.split_csv)

    # Validate required columns
    req_stage = {"category", "scenario", "stage", "contribution"}
    miss_stage = req_stage - set(df_stage.columns)
    if miss_stage:
        raise ValueError(f"[stage CSV] missing columns: {miss_stage}. Found: {list(df_stage.columns)}")

    req_split = {"category", "scenario", "KR", "non_KR"}
    miss_split = req_split - set(df_split.columns)
    if miss_split:
        raise ValueError(f"[split CSV] missing columns: {miss_split}. Found: {list(df_split.columns)}")

    # Scenario order
    available = list(df_stage["scenario"].astype(str).unique())
    scenarios = [s for s in SCENARIOS_ORDER if s in available] or available

    out_paths = []

    for label, tokens in TARGETS.items():
        d_stage = pick_rows_by_tokens(df_stage, tokens)
        d_split = pick_rows_by_tokens(df_split, tokens)

        if d_stage.empty:
            print(f"[SKIP] {label}: not found in stage CSV (tokens={tokens})")
            continue
        if d_split.empty:
            print(f"[SKIP] {label}: not found in split CSV (tokens={tokens})")
            continue

        stage_mat = build_stage_matrix(d_stage, scenarios)
        split_vec = build_split_vectors(d_split, scenarios)

        out_png = f"{args.out_prefix}_{label}_stack_vs_KR_nonKR.png"
        plot_grouped(stage_mat, split_vec, label, out_png, UNITS.get(label, ''))
        out_paths.append(out_png)

        print(f"[OK] Saved: {out_png}")

    print("\nDone. Outputs:")
    for pth in out_paths:
        print(" -", pth)


if __name__ == "__main__":
    main()
