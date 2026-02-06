# -*- coding: utf-8 -*-
"""
run_sensitivity_analysis.py
==========================
Two separate electricity-mix sensitivity charts:

1) EV:      EV_2022, EV_2050, EV_COAL100, EV_LNG100, EV_NUCLEAR100, EV_WWS100
2) E-GAS:   E_GAS_2022, E_GAS_2050, E_GAS_COAL100, E_GAS_LNG100, E_GAS_NUCLEAR100, E_GAS_WWS100

Outputs:
- sens_ev_mix_recipe18_results.csv
- sens_ev_mix_recipe18_markers.png
- sens_egas_mix_recipe18_results.csv
- sens_egas_mix_recipe18_markers.png
- sens_recipe18_methods_selected.csv
"""

from typing import Dict, Tuple, List
import csv
import ast
import os

import brightway2 as bw
import matplotlib.pyplot as plt

import param as P
from build_wtw import build_and_get_fu


# -------------------------------------------------
# ReCiPe 2018 method picker (EXACT match)
# -------------------------------------------------
def _load_recipe18_methods_exact(
    methods_csv: str = "methods_recipe.csv",
    project: str | None = None,
) -> Dict[str, Tuple]:
    if not os.path.exists(methods_csv):
        raise FileNotFoundError(
            f"methods CSV not found: {methods_csv}. "
            "Export it first using list_lcia_methods_v2.py."
        )

    out: Dict[str, Tuple] = {}
    with open(methods_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tup = ast.literal_eval(row["method_key_repr"])
            if project and str(tup[0]) != str(project):
                continue
            out[str(tup[2])] = tup
    return out


def _pick_recipe18_methods(methods_csv: str = "methods_recipe.csv") -> List[Tuple]:
    current_project = str(bw.projects.current)
    m_by_name = _load_recipe18_methods_exact(
        methods_csv=methods_csv, project=current_project
    )

    alias = {
        "Human toxicity, carcinogenic": "Human carcinogenic toxicity",
        "Human toxicity, non-carcinogenic": "Human non-carcinogenic toxicity",
    }

    picked: List[Tuple] = []
    missing: List[str] = []

    for _abbr, _name, _kw in P.RECIPE18:
        key = alias.get(_name, _name)
        m = m_by_name.get(key)
        if not m:
            missing.append(_name)
        else:
            picked.append(m)

    if missing:
        raise RuntimeError(
            f"Missing ReCiPe categories: {missing}\n"
            f"Available: {sorted(m_by_name.keys())}"
        )

    return picked


# -------------------------------------------------
# USER SETTINGS
# -------------------------------------------------
MIX_2050 = {
    "coal": 0.00,
    "lng": 0.05,
    "nuclear": 0.07,
    "renew": 0.88,
    "other": 0.0,
}

OUT_METHODS = "sens_recipe18_methods_selected.csv"

OUT_EV_CSV = "sens_ev_mix_recipe18_results.csv"
OUT_EV_PNG = "sens_ev_mix_recipe18_markers.png"

OUT_EGAS_CSV = "sens_egas_mix_recipe18_results.csv"
OUT_EGAS_PNG = "sens_egas_mix_recipe18_markers.png"

Y_SCALE = "symlog"
LINTHRESH = 1e-12

# Marker overlap 제거용 x-offset
BASE_MARKERS = {
    "2022": "o",
    "2050": "s",
    "COAL100": "x",
    "LNG100": "^",
    "NUCLEAR100": "D",
    "WWS100": ">",
}
BASE_OFFSETS = {
    "2022": -0.20,
    "2050": -0.10,
    "COAL100": 0.00,
    "LNG100": 0.10,
    "NUCLEAR100": 0.20,
    "WWS100": 0.30,
}


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def _set_project_if_needed() -> None:
    for attr in ("BW_PROJECT", "PROJECT_NAME", "PROJECT"):
        if hasattr(P, attr):
            try:
                bw.projects.set_current(getattr(P, attr))
            except Exception:
                pass
            return


def _set_mix(mix: Dict[str, float]) -> None:
    """
    build_wtw/build_process 쪽이 ELEC_SHARE_2022_KR를 참조하는 구조라서,
    여기서 '현재 선택된 전력믹스'를 이 변수로 주입한다.
    """
    P.ELEC_SHARE_2022_KR = {
        "coal": float(mix.get("coal", 0.0)),
        "lng": float(mix.get("lng", 0.0)),
        "nuclear": float(mix.get("nuclear", 0.0)),
        "renew": float(mix.get("renew", 0.0)),
        "other": float(mix.get("other", 0.0)),
    }


def _default_2022_mix() -> Dict[str, float]:
    return {"coal": 0.34, "lng": 0.27, "nuclear": 0.29, "renew": 0.08, "other": 0.02}


def _run_scores(fu_key: Tuple[str, str], methods18: List[Tuple]) -> List[float]:
    fu = {bw.get_activity(fu_key): 1.0}
    scores: List[float] = []
    for m in methods18:
        lca = bw.LCA(fu, m)
        lca.lci()
        lca.lcia()
        scores.append(float(lca.score))
    return scores


def _write_results_csv(path: str, scenarios: List[Tuple[str, Dict[str, float]]], results: Dict[str, List[float]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category"] + [n for n, _ in scenarios])
        for i, (abbr, _, _) in enumerate(P.RECIPE18):
            w.writerow([abbr] + [results[n][i] for n, _ in scenarios])


def _plot_marker_chart(path: str, title: str, scenarios: List[Tuple[str, Dict[str, float]]], results: Dict[str, List[float]]) -> None:
    cats = [abbr for (abbr, _, _) in P.RECIPE18]
    x = list(range(len(cats)))

    fig = plt.figure(figsize=(14, 6))
    ax = fig.add_subplot(111)

    for sc_name, _ in scenarios:
        # suffix 기반으로 marker/offset 선택 (예: EV_2022, E_GAS_COAL100)
        suffix = sc_name.split("_")[-1] if "_" in sc_name else sc_name
        x_shifted = [xi + BASE_OFFSETS.get(suffix, 0.0) for xi in x]
        ax.plot(
            x_shifted,
            results[sc_name],
            linestyle="None",
            marker=BASE_MARKERS.get(suffix, "o"),
            label=sc_name,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(cats, rotation=45, ha="right")
    ax.set_ylabel("Impact")
    ax.set_title(title)
    ax.legend()
    ax.set_yscale(Y_SCALE, linthresh=LINTHRESH)

    # 기존 스크립트와 동일한 축 범위 (필요하면 네가 조정)
    ax.set_ylim(-1e-12, 1e3)

    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


# -------------------------------------------------
# MAIN
# -------------------------------------------------
def main() -> None:
    _set_project_if_needed()
    methods18 = _pick_recipe18_methods()

    # Export selected methods (sanity check)
    with open(OUT_METHODS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "method_tuple"])
        for i, m in enumerate(methods18):
            w.writerow([P.RECIPE18[i][0], " | ".join(str(x) for x in m)])

    mix_2022 = getattr(P, "ELEC_SHARE_2022_KR", None) or _default_2022_mix()

    # --------------------------
    # Chart 1) EV electricity mix
    # --------------------------
    ev_scenarios: List[Tuple[str, Dict[str, float]]] = [
        ("EV_2022", mix_2022),
        ("EV_2050", MIX_2050),
        ("EV_COAL100", {"coal": 1.0}),
        ("EV_LNG100", {"lng": 1.0}),
        ("EV_NUCLEAR100", {"nuclear": 1.0}),
        ("EV_WWS100", {"renew": 1.0}),
    ]

    ev_results: Dict[str, List[float]] = {}
    for sc_name, mix in ev_scenarios:
        _set_mix(mix)
        fu_keys = build_and_get_fu()
        ev_key = fu_keys["EV_1KM"]
        ev_results[sc_name] = _run_scores(ev_key, methods18)
        print(f"[OK] {sc_name}: computed {len(methods18)} scores")

    _write_results_csv(OUT_EV_CSV, ev_scenarios, ev_results)
    _plot_marker_chart(
        OUT_EV_PNG,
        "EV electricity mix sensitivity (2022/2050 + coal/lng/nuclear/wws)",
        ev_scenarios,
        ev_results,
    )

    # -----------------------------
    # Chart 2) E-GAS electricity mix
    # -----------------------------
    egas_scenarios: List[Tuple[str, Dict[str, float]]] = [
        ("E_GAS_2022", mix_2022),
        ("E_GAS_2050", MIX_2050),
        ("E_GAS_COAL100", {"coal": 1.0}),
        ("E_GAS_LNG100", {"lng": 1.0}),
        ("E_GAS_NUCLEAR100", {"nuclear": 1.0}),
        ("E_GAS_WWS100", {"renew": 1.0}),
    ]

    egas_results: Dict[str, List[float]] = {}
    for sc_name, mix in egas_scenarios:
        _set_mix(mix)
        fu_keys = build_and_get_fu()
        # 기존 모델 키 이름 (e-fuel은 E_GASOLINE_1KM을 사용)
        egas_key = fu_keys["E_GASOLINE_1KM"]
        egas_results[sc_name] = _run_scores(egas_key, methods18)
        print(f"[OK] {sc_name}: computed {len(methods18)} scores")

    _write_results_csv(OUT_EGAS_CSV, egas_scenarios, egas_results)
    _plot_marker_chart(
        OUT_EGAS_PNG,
        "E-gasoline electricity mix sensitivity (2022/2050 + coal/lng/nuclear/wws)",
        egas_scenarios,
        egas_results,
    )

    print(f"Saved: {OUT_METHODS}")
    print(f"Saved: {OUT_EV_CSV}")
    print(f"Saved: {OUT_EV_PNG}")
    print(f"Saved: {OUT_EGAS_CSV}")
    print(f"Saved: {OUT_EGAS_PNG}")


if __name__ == "__main__":
    main()
