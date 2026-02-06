# -*- coding: utf-8 -*-
"""
run_lcia.py
===========
Exports:
1) ReCiPe18 results table per scenario
2) KR vs non-KR split (based on activity location == "KR")
3) Top contributing activities (all DBs)
4) Top contributing FOREGROUND activities
5) Aggregated FOREGROUND contribution table
6) Selected ReCiPe method tuples (sanity-check)
7) NEW: Stage breakdown (raw_material / transport / refining_or_power / vehicle_operation / other)
   saved as: <out_prefix>_recipe18_stage_breakdown.csv
"""

from typing import Dict, Tuple, List, Any
import csv

import brightway2 as bw
import matplotlib.pyplot as plt

import param as P

TOP_N_ALL = 30
TOP_N_FG  = 30

STAGES = [
    "raw_material",
    "transport",
    "refining_or_power",
    "vehicle_operation",
    "other",
]


def _is_recipe2016_midpoint_h(method: Tuple) -> bool:
    s = " ".join(str(x).lower() for x in method)
    has_recipe = "recipe" in s and "2016" in s and "midpoint" in s
    is_h = ("midpoint (h)" in s) or ("hierarchist" in s)
    is_i = ("midpoint (i)" in s) or ("individualist" in s)
    return has_recipe and is_h and (not is_i)


def _load_recipe18_methods_exact(methods_csv: str = "methods_recipe.csv", project: str = None) -> Dict[str, Tuple]:
    """Load exact ReCiPe 2016 Midpoint (H) methods from a CSV exported by list_lcia_methods."""
    import os, ast, csv as _csv
    if not os.path.exists(methods_csv):
        raise FileNotFoundError(
            f"methods CSV not found: {methods_csv}. Run list_lcia_methods_v2.py to export it."
        )
    out = {}
    with open(methods_csv, newline="", encoding="utf-8") as f:
        reader = _csv.DictReader(f)
        if "method_key_repr" not in reader.fieldnames:
            raise RuntimeError(f"CSV missing 'method_key_repr' column: {methods_csv}")
        for row in reader:
            tup = ast.literal_eval(row["method_key_repr"])
            if project and str(tup[0]) != str(project):
                continue
            out[str(tup[2])] = tup

    if project and not out:
        raise RuntimeError(
            f"No methods loaded for project={project} from {methods_csv}. "
            "Check the CSV was exported from the same BW project."
        )
    if len(out) < 18:
        print(f"[WARN] Loaded only {len(out)} methods from {methods_csv}. Expected 18 for ReCiPe midpoint set.")
    return out


def _pick_recipe18_methods(methods_csv: str = "methods_recipe.csv") -> List[Tuple]:
    """Pick one method per entry in P.RECIPE18 using an *exact* match (no keywords)."""
    current_project = str(bw.projects.current)
    m_by_name = _load_recipe18_methods_exact(methods_csv=methods_csv, project=current_project)

    alias = {
        "Human toxicity, carcinogenic": "Human carcinogenic toxicity",
        "Human toxicity, non-carcinogenic": "Human non-carcinogenic toxicity",
    }

    missing = []
    picked = []
    for _abbr, _name, _keywords in P.RECIPE18:
        key = str(_name)
        m = m_by_name.get(alias.get(key, key))
        if not m:
            missing.append(key)
            continue
        picked.append(m)

    if missing:
        available = sorted(m_by_name.keys())
        raise RuntimeError(
            "Exact ReCiPe method match failed for some categories.\n"
            f"Current project: {current_project}\n"
            f"Missing ({len(missing)}): {missing}\n"
            f"Available in CSV ({len(available)}): {available}\n"
            "Fix by ensuring P.RECIPE18 category names exactly match tuple[2] names in methods_recipe.csv."
        )
    return picked


def _act_obj(act_key):
    return act_key if hasattr(act_key, "get") else bw.get_activity(act_key)


def _act_meta(act_key: Any) -> Dict[str, str]:
    try:
        a = _act_obj(act_key)
        db, code = a.key
        return {
            "db": str(db),
            "code": str(code),
            "name": str(a.get("name") or ""),
            "location": str(a.get("location") or ""),
            "unit": str(a.get("unit") or ""),
            "reference_product": str(a.get("reference product") or a.get("reference_product") or ""),
            "stage": str(a.get("stage") or ""),  # custom FG tag (if present)
        }
    except Exception:
        return {
            "db": "",
            "code": str(act_key),
            "name": str(act_key),
            "location": "",
            "unit": "",
            "reference_product": "",
            "stage": "",
        }


def _is_domestic(act_key) -> bool:
    try:
        a = _act_obj(act_key)
        loc = (a.get("location") or "").upper()
        return loc == "KR"
    except Exception:
        return False


def _stage_of(meta: Dict[str, str]) -> str:
    """Heuristic stage classifier with foreground override via meta['stage']."""
    # 1) Foreground tag wins
    st = (meta.get("stage") or "").strip().lower()
    if st in STAGES:
        return st
    if st in ("raw", "material"):
        return "raw_material"
    if st in ("transportation", "shipping"):
        return "transport"
    if st in ("refining", "power_generation", "power"):
        return "refining_or_power"
    if st in ("operation", "vehicle_operation"):
        return "vehicle_operation"

    # 2) Heuristics for background activities
    name = (meta.get("name") or "").lower()
    unit = (meta.get("unit") or "").lower()
    refp = (meta.get("reference_product") or "").lower()

    # transport
    if "transport" in name or "ocean" in name or "freighter" in name or unit == "ton kilometer" or "tkm" in unit or "tkm" in refp:
        return "transport"

    # refining / power
    if "refiner" in name or "refinery" in name or "petroleum refinery" in name:
        return "refining_or_power"
    if "electricity" in name or "power plant" in name or "generation" in name:
        return "refining_or_power"

    # vehicle operation / driving (rare in background)
    if "operation" in name or "driving" in name or unit == "kilometer":
        return "vehicle_operation"

    # raw material / extraction / processing
    raw_hits = ["extraction", "processing", "mine", "mining", "crude oil", "natural gas", "coal", "uranium", "ore", "well"]
    if any(h in name for h in raw_hits):
        return "raw_material"

    return "other"


def run_lcia(fu_keys: Dict[str, Tuple[str, str]], out_prefix: str = "out") -> None:
    methods18 = _pick_recipe18_methods()

    scenarios = [
        ("EV_1KM", fu_keys["EV_1KM"]),
        ("GASOLINE_1KM", fu_keys["GASOLINE_1KM"]),
        ("DIESEL_1KM", fu_keys["DIESEL_1KM"]),
        ("E_GASOLINE_1KM", fu_keys["E_GASOLINE_1KM"]),
    ]

    results = {sc: [] for sc, _ in scenarios}
    split_dom = {sc: [] for sc, _ in scenarios}
    split_for = {sc: [] for sc, _ in scenarios}

    top_rows_all: List[Dict[str, Any]] = []
    top_rows_fg: List[Dict[str, Any]] = []
    fg_agg_rows: List[Dict[str, Any]] = []
    method_rows: List[Dict[str, Any]] = []
    stage_rows: List[Dict[str, Any]] = []

    for sc_name, sc_key in scenarios:
        fu = {bw.get_activity(sc_key): 1.0}

        for i, m in enumerate(methods18):
            label = P.RECIPE18[i][0]
            method_rows.append({
                "category": label,
                "method_tuple": " | ".join(str(x) for x in m),
            })

            lca = bw.LCA(fu, m)
            lca.lci()
            lca.lcia()

            total = float(lca.score)

            cf = lca.characterization_matrix
            inv = lca.inventory
            contrib = (cf @ inv).sum(axis=0)
            contrib = contrib.A1 if hasattr(contrib, "A1") else contrib

            act_rev = {v: k for k, v in lca.activity_dict.items()}

            dom = 0.0
            foreign = 0.0

            nz_all = []
            fg_sum: Dict[Tuple[str, str], float] = {}

            # Stage totals (all DBs, categorized heuristically)
            stage_sum = {s: 0.0 for s in STAGES}

            for col, val in enumerate(contrib):
                if val == 0:
                    continue
                act_key = act_rev.get(col)
                if act_key is None:
                    continue
                v = float(val)

                nz_all.append((v, act_key))

                if _is_domestic(act_key):
                    dom += v
                else:
                    foreign += v

                meta = _act_meta(act_key)

                # stage accumulation (all DBs)
                st = _stage_of(meta)
                stage_sum[st] = stage_sum.get(st, 0.0) + v

                # foreground aggregation
                if meta["db"] == P.FG_DB_NAME:
                    fg_sum[(meta["db"], meta["code"])] = fg_sum.get((meta["db"], meta["code"]), 0.0) + v

            results[sc_name].append(total)
            split_dom[sc_name].append(dom)
            split_for[sc_name].append(foreign)

            # Save stage breakdown rows (one row per stage)
            denom = sum(abs(stage_sum[s]) for s in STAGES) or 0.0
            for st in STAGES:
                vv = stage_sum.get(st, 0.0)
                stage_rows.append({
                    "category": label,
                    "scenario": sc_name,
                    "stage": st,
                    "contribution": vv,
                    "abs_contribution": abs(vv),
                    "share_of_abs_total": (abs(vv) / denom) if denom else 0.0,
                })

            # --- All DB top contributors ---
            nz_all.sort(key=lambda x: abs(x[0]), reverse=True)
            for rank, (v, act_key) in enumerate(nz_all[:TOP_N_ALL], start=1):
                meta = _act_meta(act_key)
                top_rows_all.append({
                    "category": label,
                    "scenario": sc_name,
                    "rank": rank,
                    "contribution": v,
                    "abs_contribution": abs(v),
                    "activity_db": meta["db"],
                    "activity_code": meta["code"],
                    "activity_name": meta["name"],
                    "activity_location": meta["location"],
                    "activity_unit": meta["unit"],
                    "activity_reference_product": meta["reference_product"],
                })

            # --- Foreground-only top contributors ---
            fg_items = [ (abs(v), v, db, code) for (db, code), v in fg_sum.items() ]
            fg_items.sort(reverse=True)
            for rank, (abs_v, v, db, code) in enumerate(fg_items[:TOP_N_FG], start=1):
                a = bw.get_activity((db, code))
                top_rows_fg.append({
                    "category": label,
                    "scenario": sc_name,
                    "rank": rank,
                    "contribution": v,
                    "abs_contribution": abs_v,
                    "activity_db": db,
                    "activity_code": code,
                    "activity_name": a.get("name") or "",
                    "activity_location": a.get("location") or "",
                    "activity_unit": a.get("unit") or "",
                    "activity_reference_product": a.get("reference product") or a.get("reference_product") or "",
                })

            # --- Full foreground aggregated table ---
            for (db, code), v in sorted(fg_sum.items(), key=lambda kv: abs(kv[1]), reverse=True):
                a = bw.get_activity((db, code))
                fg_agg_rows.append({
                    "category": label,
                    "scenario": sc_name,
                    "contribution": v,
                    "abs_contribution": abs(v),
                    "activity_db": db,
                    "activity_code": code,
                    "activity_name": a.get("name") or "",
                    "activity_location": a.get("location") or "",
                    "activity_unit": a.get("unit") or "",
                    "activity_reference_product": a.get("reference product") or a.get("reference_product") or "",
                })

    # ---- CSV outputs ----
    res_csv = f"{out_prefix}_recipe18_results.csv"
    with open(res_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category"] + [sc for sc, _ in scenarios])
        for i, _m in enumerate(methods18):
            label = P.RECIPE18[i][0]
            w.writerow([label] + [results[sc][i] for sc, _ in scenarios])

    split_csv = f"{out_prefix}_recipe18_split_KR_vs_nonKR.csv"
    with open(split_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "scenario", "KR", "non_KR", "KR_share"])
        for i, _m in enumerate(methods18):
            label = P.RECIPE18[i][0]
            for sc, _ in scenarios:
                kr = split_dom[sc][i]
                nk = split_for[sc][i]
                share = kr / (kr + nk) if (kr + nk) else 0.0
                w.writerow([label, sc, kr, nk, share])

    top_all_csv = f"{out_prefix}_top_contributors_ALL_by_category_and_vehicle.csv"
    with open(top_all_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "category", "scenario", "rank",
            "contribution", "abs_contribution",
            "activity_db", "activity_code", "activity_name",
            "activity_location", "activity_unit", "activity_reference_product",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in top_rows_all:
            w.writerow(r)

    top_fg_csv = f"{out_prefix}_top_contributors_FOREGROUND_by_category_and_vehicle.csv"
    with open(top_fg_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "category", "scenario", "rank",
            "contribution", "abs_contribution",
            "activity_db", "activity_code", "activity_name",
            "activity_location", "activity_unit", "activity_reference_product",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in top_rows_fg:
            w.writerow(r)

    fg_agg_csv = f"{out_prefix}_foreground_contribution_table.csv"
    with open(fg_agg_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "category", "scenario",
            "contribution", "abs_contribution",
            "activity_db", "activity_code", "activity_name",
            "activity_location", "activity_unit", "activity_reference_product",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in fg_agg_rows:
            w.writerow(r)

    stage_csv = f"{out_prefix}_recipe18_stage_breakdown.csv"
    with open(stage_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["category", "scenario", "stage", "contribution", "abs_contribution", "share_of_abs_total"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in stage_rows:
            w.writerow(r)

    method_csv = f"{out_prefix}_recipe18_methods_selected.csv"
    seen = set()
    with open(method_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["category", "method_tuple"])
        w.writeheader()
        for r in method_rows:
            if r["category"] in seen:
                continue
            seen.add(r["category"])
            w.writerow(r)

    # ---- Plot (marker style) ----
    cats = [abbr for (abbr, _name, _kw) in P.RECIPE18]
    x = list(range(len(cats)))

    fig = plt.figure(figsize=(14, 6))
    ax = fig.add_subplot(111)

    markers = {"EV_1KM": "o", "GASOLINE_1KM": "x", "DIESEL_1KM": "s"}
    pretty = {"EV_1KM": "EV", "GASOLINE_1KM": "Gasoline ICE", "DIESEL_1KM": "Diesel ICE"}

    for sc, _ in scenarios:
        ax.plot(x, results[sc], marker=markers.get(sc, "o"), linestyle="None", label=pretty.get(sc, sc))

    ax.set_xticks(x)
    ax.set_xticklabels(cats, rotation=45, ha="right")
    ax.set_ylabel("Impact (log scale)")
    ax.set_title(P.CHART_TITLE)
    ax.legend()
    ax.set_yscale("symlog", linthresh=1e-12)
    ax.set_ylim(-1e-11, 1e10)

    fig.tight_layout()
    fig.savefig(P.CHART_OUT_PNG, dpi=200)
    plt.close(fig)

    print(f"Saved: {res_csv}")
    print(f"Saved: {split_csv}")
    print(f"Saved: {top_all_csv}")
    print(f"Saved: {top_fg_csv}")
    print(f"Saved: {fg_agg_csv}")
    print(f"Saved: {stage_csv}")
    print(f"Saved: {method_csv}")
    print(f"Saved: {P.CHART_OUT_PNG}")
