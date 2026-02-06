# -*- coding: utf-8 -*-
"""
build_process.py
================
Clean, indentation-safe builder for the WTW foreground database.

Stage-aware foreground (for stage breakdown in run_lcia.py):
- raw_material: extraction / processing / supply (crude, coal, LNG, uranium)
- transport: ocean transport services (modeled as separate foreground "per kg transported" activities)
- refining: refinery (CAPSS refinery emissions) producing 1 kg fuel
- power_generation: electricity generation mix and source-specific generation (CAPSS direct)
- vehicle_operation: vehicle operation per 1 km

NOTE:
- biosphere3 key == uuid, so we use (BIO_DB_NAME, uuid) directly.
"""

from __future__ import annotations

from typing import Dict, Tuple

import brightway2 as bw

import param as P


def set_project() -> None:
    bw.projects.set_current(P.PROJECT_NAME)


def reset_fg_db() -> bw.Database:
    """Delete and recreate the foreground DB."""
    if P.FG_DB_NAME in bw.databases:
        del bw.databases[P.FG_DB_NAME]
    fg = bw.Database(P.FG_DB_NAME)
    fg.register()
    return fg


def _act(db: str, code: str):
    return bw.get_activity((db, code))

def _act_safe(db: str, code: str, label: str = ""):
    """Safe activity getter: returns None if not found (prevents hard crash)."""
    try:
        return bw.get_activity((db, code))
    except Exception:
        print(f"[WARN] Missing activity: {label} | db={db}, code={code} -> skipped")
        return None



def bio_flow(pollutant: str):
    uuid = P.BIO_UUID[pollutant]
    return _act(P.BIO_DB_NAME, uuid)


def add_production(act, amount: float = 1.0) -> None:
    act.new_exchange(input=act, amount=float(amount), type="production").save()


def add_tech(act, input_act, amount: float) -> None:
    act.new_exchange(input=input_act, amount=float(amount), type="technosphere").save()

def add_tech_if(act, input_act, amount: float, label: str = "") -> None:
    """Add technosphere exchange only if provider exists; otherwise warn and skip."""
    if input_act is None:
        print(f"[WARN] Skip technosphere (missing provider): {label}")
        return
    act.new_exchange(input=input_act, amount=float(amount), type="technosphere").save()


def add_bio(act, flow, amount: float) -> None:
    act.new_exchange(input=flow, amount=float(amount), type="biosphere").save()


def _new_fg_activity(fg: bw.Database, *, code: str, name: str, unit: str, location: str, stage: str) -> bw.Activity:
    a = fg.new_activity(
        code=code,
        name=name,
        unit=unit,
        location=location,
        type="process",
    )
    # Custom metadata (safe to store)
    a["stage"] = stage
    a.save()
    add_production(a, 1.0)
    return a


def build_foreground_db() -> Dict[str, Tuple[str, str]]:
    """Build foreground DB and return activity keys."""
    set_project()

    if P.BG_DB_NAME not in bw.databases:
        raise KeyError(f"Background DB '{P.BG_DB_NAME}' not found. Available: {list(bw.databases)}")
    if P.BIO_DB_NAME not in bw.databases:
        raise KeyError(f"Biosphere DB '{P.BIO_DB_NAME}' not found. Available: {list(bw.databases)}")

    fg = reset_fg_db()

    # ------------------------------------------------------------
    # 1) Crude extraction mix (raw material), 1 kg crude
    # ------------------------------------------------------------
    crude_extraction = _new_fg_activity(
        fg,
        code="crude_extraction_mix_1kg",
        name="Crude oil extraction mix (domestic+import), 1 kg crude",
        unit="kg",
        location="GLO",
        stage="raw_material",
    )

    for _, spec in P.CRUDE_EXTRACTION.items():
        bg = _act(P.BG_DB_NAME, spec["uuid"])
        add_tech(crude_extraction, bg, spec["w"])

    # ------------------------------------------------------------
    # 2) Crude ocean transport service (transport), per kg crude transported
    # ------------------------------------------------------------
    crude_transport = _new_fg_activity(
        fg,
        code="crude_ocean_transport_1kg",
        name="Crude oil ocean transport, per kg crude transported",
        unit="kg",
        location="GLO",
        stage="transport",
    )
    crude_ship = _act(P.BG_DB_NAME, P.UUID_OCEAN_FREIGHTER_AVG_FUEL_MIX_TKM)
    crude_ship_tkm = (1.0 / 1000.0) * float(P.SEA_DISTANCE_KM_CRUDE)  # ton-km per kg crude
    add_tech(crude_transport, crude_ship, crude_ship_tkm)

    # ------------------------------------------------------------
    # 3) Refinery outputs (refining), 1 kg fuel (CAPSS refinery emissions)
    #    Inputs are split into:
    #      - crude extraction mix (raw_material)
    #      - crude ocean transport (transport)
    # ------------------------------------------------------------
    def build_refinery(fuel: str, code: str) -> bw.Activity:
        """Build an *allocated* refinery process for 1 kg of product.

        IMPORTANT: Crude oil refining is multifunctional. To keep the foreground
        model square/invertible in Brightway, we represent gasoline, diesel, and
        an aggregated 'other products' stream as *separately allocated* unit
        processes. This effectively assigns each product its yield-based share
        of crude supply and refinery emissions.

        - Gasoline yield: P.YIELD_GASOLINE
        - Diesel yield:   P.YIELD_DIESEL
        - Other yield:    1 - (gasoline + diesel)
        """
        a = _new_fg_activity(
            fg,
            code=code,
            name=f"Refinery (allocated), {fuel}, 1 kg",
            unit="kg",
            location="KR",
            stage="refining",
        )

        yg = float(P.YIELD_GASOLINE)
        yd = float(P.YIELD_DIESEL)
        yo = max(0.0, 1.0 - (yg + yd))  # aggregate all other refinery products

        total = yg + yd + yo
        if total <= 0:
            raise ValueError("Invalid refinery yields: sum(yields) must be > 0")

        if fuel == "gasoline":
            y = yg
        elif fuel == "diesel":
            y = yd
        elif fuel == "other":
            y = yo
        else:
            raise ValueError(f"Unknown fuel: {fuel}")

        if y <= 0:
            raise ValueError(f"Invalid yield for {fuel}: {y}")

        # Allocation factor (mass-based by default)
        alloc = y / total

        # Allocated crude requirement and emissions per 1 kg product
        crude_needed = (1.0 / y) * alloc

        # Split upstream burdens explicitly
        add_tech(a, crude_extraction, crude_needed)
        add_tech(a, crude_transport, crude_needed)

        for pol, g in P.REFINERY_G_PER_KG_FUEL.get(fuel, {}).items():
            add_bio(a, bio_flow(pol), (float(g) / 1000.0) * alloc)  # kg/kg-product (allocated)

        # Refinery direct CO2 (gCO2/MJ-product -> kgCO2/kg-product), allocated consistently with other CAPSS pollutants
        co2_g_per_mj = float(P.REFINERY_CO2_G_PER_MJ_PRODUCT.get(fuel, 0.0))
        if co2_g_per_mj > 0:
            co2_kg_per_kg = (co2_g_per_mj * float(P.LHV_MJ_PER_KG[fuel])) / 1000.0
            add_bio(a, bio_flow("CO2"), co2_kg_per_kg * alloc)

        return a

    refinery_gas = build_refinery("gasoline", "refinery_gasoline_1kg")
    refinery_dsl = build_refinery("diesel", "refinery_diesel_1kg")
    refinery_oth = build_refinery("other", "refinery_other_1kg")

    # ------------------------------------------------------------
    # 4) Upstream fuel supply chains for power generation (raw + transport)
    # ------------------------------------------------------------
    # Coal extraction (raw material), 1 kg
    coal_extraction = _new_fg_activity(
        fg,
        code="coal_extraction_1kg",
        name="Coal extraction and processing (import, BIT, surface), 1 kg",
        unit="kg",
        location="GLO",
        stage="raw_material",
    )
    coal_up = _act(P.BG_DB_NAME, P.UUID_COAL_EXTRACTION_IMPORT_BIT_SURFACE)
    add_tech(coal_extraction, coal_up, 1.0)

    # Coal ocean transport service (transport), per kg transported
    coal_transport = _new_fg_activity(
        fg,
        code="coal_ocean_transport_1kg",
        name="Coal ocean transport, per kg transported",
        unit="kg",
        location="GLO",
        stage="transport",
    )
    coal_ship = _act(P.BG_DB_NAME, P.UUID_OCEAN_FREIGHTER_AVG_FUEL_MIX_TKM)
    coal_ship_tkm = (1.0 / 1000.0) * float(P.SEA_DISTANCE_KM_COAL)  # ton-km per kg
    add_tech(coal_transport, coal_ship, coal_ship_tkm)

    # Natural gas processing (raw material), 1 kg
    ng_processing = _new_fg_activity(
        fg,
        code="ng_processing_1kg",
        name="Natural gas processing (conventional), 1 kg",
        unit="kg",
        location="GLO",
        stage="raw_material",
    )
    ng_up = _act(P.BG_DB_NAME, P.UUID_NG_PROCESSING_CONVENTIONAL_KG)
    add_tech(ng_processing, ng_up, 1.0)

    # LNG ocean transport service (transport), per kg transported
    lng_transport = _new_fg_activity(
        fg,
        code="lng_ocean_transport_1kg",
        name="LNG ocean transport, per kg transported",
        unit="kg",
        location="GLO",
        stage="transport",
    )
    ng_ship = _act(P.BG_DB_NAME, P.UUID_OCEAN_FREIGHTER_AVG_FUEL_MIX_TKM)
    ng_ship_tkm = (1.0 / 1000.0) * float(P.SEA_DISTANCE_KM_LNG)  # ton-km per kg
    add_tech(lng_transport, ng_ship, ng_ship_tkm)

    # Uranium supply (raw material proxy), 1 kg
    uranium_supply = _new_fg_activity(
        fg,
        code="uranium_supply_1kg",
        name="Fuel grade uranium supply (storage proxy), 1 kg",
        unit="kg",
        location="GLO",
        stage="raw_material",
    )
    u_up = _act(P.BG_DB_NAME, P.UUID_URANIUM_FUEL_GRADE_STORAGE_KG)
    add_tech(uranium_supply, u_up, 1.0)

    
    # ------------------------------------------------------------
    # 5) Electricity generation (power generation)
    #    - Source-specific generation (CAPSS direct + upstream fuel)
    #    - Mix (KR 2022) built from shares
    #    - Extra mixes used for H2 electrolysis scenarios (renew100 / greywash)
    #    - Zero-carbon gas turbine (H2 turbine) with 3 H2 supply scenarios
    # ------------------------------------------------------------
    # ---- Mix activity (will be filled after source acts are created) ----
    elec_mix = _new_fg_activity(
        fg,
        code="elec_mix_1kwh",
        name="Electricity mix (KR 2022), 1 kWh",
        unit="kilowatt hour",
        location="KR",
        stage="power_generation",
    )

    # Shares (KR 2022): include renewables explicitly.
    s = P.ELEC_SHARE_2022_KR
    renew_share = float(s.get("renew", 0.0))
    renew_share = max(0.0, min(1.0, renew_share))

    base_keys = ["coal", "lng", "nuclear", "zero_carbon_gt"]
    base_sum = sum(float(s.get(k, 0.0)) for k in base_keys)
    remaining = max(0.0, 1.0 - renew_share)  # includes 'other' by design

    if base_sum <= 0.0:
        shares = {k: 0.0 for k in base_keys}
        shares["renew"] = renew_share + remaining  # == 1.0
    else:
        shares = {
            "coal": remaining * float(s.get("coal", 0.0)) / base_sum,
            "lng": remaining * float(s.get("lng", 0.0)) / base_sum,
            "nuclear": remaining * float(s.get("nuclear", 0.0)) / base_sum,
            "zero_carbon_gt": remaining * float(s.get("zero_carbon_gt", 0.0)) / base_sum,
            "renew": renew_share,
        }

    
    # ---- Power plant construction (proxy; background is USLCI, foreground wrapper is KR) ----
    # Note: we do NOT edit background process locations. Instead, we create KR-located wrapper
    # activities that reference the USLCI processes 1:1, so reporting shows "KR" while inventory
    # comes from USLCI proxies.
    bg_coal_const = _act_safe(P.BG_DB_NAME, P.PJM_COAL_CONST_UUID, label="PJM coal_const")
    bg_ngcc_const = _act_safe(P.BG_DB_NAME, P.PJM_NGCC_CONST_UUID, label="PJM ngcc_const")
    bg_wind_const = _act_safe(P.BG_DB_NAME, P.PJM_WIND_CONST_UUID, label="PJM wind_const")
    bg_solar_const = _act_safe(P.BG_DB_NAME, P.PJM_SOLAR_PV_CONST_UUID, label="PJM solar_pv_const")

    const_coal = None
    const_ngcc = None
    const_wind = None
    const_solar = None

    if bg_coal_const:
        const_coal = _new_fg_activity(
            fg,
            code="pp_const_coal_proxy_1item",
            name="power plant construction - coal_const - KR proxy (from USLCI PJM)",
            unit="Item(s)",
            location="KR",
            stage="power_generation",
        )
        add_production(const_coal, 1.0)
        add_tech(const_coal, bg_coal_const, 1.0)

    if bg_ngcc_const:
        const_ngcc = _new_fg_activity(
            fg,
            code="pp_const_ngcc_proxy_1item",
            name="power plant construction - ngcc_const - KR proxy (from USLCI PJM)",
            unit="Item(s)",
            location="KR",
            stage="power_generation",
        )
        add_production(const_ngcc, 1.0)
        add_tech(const_ngcc, bg_ngcc_const, 1.0)

    if bg_wind_const:
        const_wind = _new_fg_activity(
            fg,
            code="pp_const_wind_proxy_1item",
            name="power plant construction - wind_const - KR proxy (from USLCI PJM)",
            unit="Item(s)",
            location="KR",
            stage="power_generation",
        )
        add_production(const_wind, 1.0)
        add_tech(const_wind, bg_wind_const, 1.0)

    if bg_solar_const:
        const_solar = _new_fg_activity(
            fg,
            code="pp_const_solar_pv_proxy_1item",
            name="power plant construction - solar_pv_const - KR proxy (from USLCI PJM)",
            unit="Item(s)",
            location="KR",
            stage="power_generation",
        )
        add_production(const_solar, 1.0)
        add_tech(const_solar, bg_solar_const, 1.0)

    # Water biosphere flows for power generation (resource/water; UUIDs must exist in biosphere3)
    water_fresh = bio_flow("WATER_FRESH") if "WATER_FRESH" in P.BIO_UUID else bio_flow("WATER_RESOURCE")
    water_brackish = bio_flow("WATER_BRACKISH") if "WATER_BRACKISH" in P.BIO_UUID else bio_flow("WATER_RESOURCE")
    water_saline = bio_flow("WATER_SALINE") if "WATER_SALINE" in P.BIO_UUID else bio_flow("WATER_RESOURCE")
    water_generic = bio_flow("WATER_RESOURCE")  # generic water (resource)

    # Inputs are provided per 1 MJ electricity output; convert to 1 kWh (3.6 MJ)
    MJ_TO_KWH = 3.6
    # Renewables split inside "renew": solar:wind = 8:1
    SOLAR_SHARE = 8.0 / 9.0
    WIND_SHARE = 1.0 / 9.0

# ---- Source-specific electricity acts ----
    elec_src: Dict[str, bw.Activity] = {}

    for src in ["coal", "lng", "nuclear", "renew"]:
        a = _new_fg_activity(
            fg,
            code=f"elec_{src}_1kwh",
            name=f"Electricity, {src} (CAPSS direct), 1 kWh",
            unit="kilowatt hour",
            location="KR",
            stage="power_generation",
        )

        # CAPSS direct emissions (g/kWh -> kg/kWh)
        for pol, g in P.GEN_G_PER_KWH.get(src, {}).items():
            add_bio(a, bio_flow(pol), float(g) / 1000.0)

        # Direct CO2 from combustion (kg/kWh); 0 for non-combustion
        add_bio(a, bio_flow("CO2"), float(P.GEN_CO2_KG_PER_KWH.get(src, 0.0)))

        # Upstream fuel supply chain (kg fuel per kWh), split raw vs transport
        if src == "coal":
            add_tech(a, coal_extraction, float(P.COAL_KG_PER_KWH))
            add_tech(a, coal_transport, float(P.COAL_KG_PER_KWH))
        elif src == "lng":
            add_tech(a, ng_processing, float(P.LNG_KG_PER_KWH))
            add_tech(a, lng_transport, float(P.LNG_KG_PER_KWH))
        elif src == "nuclear":
            add_tech(a, uranium_supply, float(P.NUCLEAR_U_KG_PER_KWH))
        elif src == "renew":
            # Infrastructure/manufacturing not included in this scope.
            pass


        # Power plant construction + operational water consumption (per 1 kWh output)
        # Values from your note (per 1 MJ output) converted by * 3.6.
        if src == "lng":
            # gas: coal_const + ngcc_const + fresh/brackish water
            if const_coal:
                add_tech(a, const_coal, 3.54891e-11 * MJ_TO_KWH)
            if const_ngcc:
                add_tech(a, const_ngcc, 5.16262e-8 * MJ_TO_KWH)
            add_bio(a, water_fresh, 0.93331 * MJ_TO_KWH)
            add_bio(a, water_brackish, 0.06330 * MJ_TO_KWH)

        elif src == "coal":
            if const_coal:
                add_tech(a, const_coal, 8.31275e-8 * MJ_TO_KWH)
            if const_ngcc:
                add_tech(a, const_ngcc, 9.66851e-10 * MJ_TO_KWH)
            add_bio(a, water_fresh, 0.51801 * MJ_TO_KWH)
            add_bio(a, water_saline, 0.00069 * MJ_TO_KWH)
            add_bio(a, water_brackish, 0.51801 * MJ_TO_KWH)

        elif src == "renew":
            # wind and solar are mixed inside "renew"
            if const_wind:
                add_tech(a, const_wind, (0.00028 * MJ_TO_KWH) * WIND_SHARE)
            if const_solar:
                add_tech(a, const_solar, (0.00028 * MJ_TO_KWH) * SOLAR_SHARE)

            # wind water
            add_bio(a, water_generic, (4.61612e-6 * MJ_TO_KWH) * WIND_SHARE)
            add_bio(a, water_fresh, (18.67 * MJ_TO_KWH) * WIND_SHARE)
            add_bio(a, water_saline, (0.00026 * MJ_TO_KWH) * WIND_SHARE)

            # solar water
            add_bio(a, water_generic, (0.01388 * MJ_TO_KWH) * SOLAR_SHARE)
            add_bio(a, water_fresh, (2.68802 * MJ_TO_KWH) * SOLAR_SHARE)
            add_bio(a, water_saline, (4.48176e-5 * MJ_TO_KWH) * SOLAR_SHARE)

        elif src == "nuclear":
            # only water provided in your note
            add_bio(a, water_fresh, 2.68802 * MJ_TO_KWH)
            add_bio(a, water_brackish, 0.19368 * MJ_TO_KWH)
        elec_src[src] = a

    # ---- Extra mix acts used for H2 electrolysis scenarios ----
    elec_mix_renew100 = _new_fg_activity(
        fg,
        code="elec_mix_renew100_1kwh",
        name="Electricity mix (renewables 100%), 1 kWh",
        unit="kilowatt hour",
        location="GLO",
        stage="power_generation",
    )
    add_tech(elec_mix_renew100, elec_src["renew"], 1.0)

    # Greywash worst-case mix (proxy exporting country grid)
    elec_mix_greywash = _new_fg_activity(
        fg,
        code="elec_mix_greywash_1kwh",
        name="Electricity mix (greywash worst-case proxy), 1 kWh",
        unit="kilowatt hour",
        location="GLO",
        stage="power_generation",
    )
    sg = getattr(P, "ELEC_SHARE_GREYWASH", {"coal": 0.7, "lng": 0.25, "renew": 0.05, "nuclear": 0.0, "other": 0.0})
    # Normalize if needed (ignore 'other' here)
    total_g = sum(float(sg.get(k, 0.0)) for k in ["coal", "lng", "nuclear", "renew"])
    if total_g <= 0:
        sg_norm = {"renew": 1.0}
    else:
        sg_norm = {k: float(sg.get(k, 0.0)) / total_g for k in ["coal", "lng", "nuclear", "renew"]}
    for k, v in sg_norm.items():
        if v > 0:
            add_tech(elec_mix_greywash, elec_src[k], v)

    # ---- Hydrogen ocean transport service (transport), per kg transported ----
    h2_transport = _new_fg_activity(
        fg,
        code="h2_ocean_transport_1kg",
        name="Hydrogen ocean transport, per kg H2 transported",
        unit="kg",
        location="GLO",
        stage="transport",
    )
    h2_ship = _act(P.BG_DB_NAME, P.UUID_OCEAN_FREIGHTER_AVG_FUEL_MIX_TKM)
    h2_ship_tkm = (1.0 / 1000.0) * float(getattr(P, "SEA_DISTANCE_KM_H2", 8000.0))  # ton-km per kg
    add_tech(h2_transport, h2_ship, h2_ship_tkm)

    # ---- Hydrogen production & import (3 scenarios) ----
    # Background reference dataset (USLCI) — outputs 1 kg H2 at plant
    h2_avg_bg = _act(P.BG_DB_NAME, P.UUID_H2_PEM_ELECTROLYSIS_US)

    # 1) H2_USLCI: use the imported USLCI PEM electrolysis dataset as-is (incl. its own electricity provider mix)
    h2_uslci = _new_fg_activity(
        fg,
        code="h2_uslci_1kg",
        name="Hydrogen, PEM electrolysis (USLCI as-is), 1 kg at plant",
        unit="kg",
        location="US",
        stage="raw_material",
    )
    add_tech(h2_uslci, h2_avg_bg, 1.0)

    # Helper: clone the H2_avg dataset structure into foreground, but override the electricity provider
    # This avoids hard-coding UUIDs for plant/stack/water and prevents missing-UUID crashes.
    def _clone_h2_avg_with_electricity(code: str, name: str, elec_provider: bw.Activity) -> bw.Activity:
        a = _new_fg_activity(
            fg,
            code=code,
            name=name,
            unit="kg",
            location="GLO",
            stage="raw_material",
        )

        # Copy all non-electric technosphere inputs from the background H2_avg dataset
        for exc in h2_avg_bg.technosphere():
            inp = exc.input
            inp_name = (inp.get("name", "") or "").lower()
            inp_prod = (inp.get("product", "") or "").lower()
            if ("electricity" in inp_name) or ("electricity" in inp_prod):
                continue
            add_tech(a, inp, float(exc["amount"]))

        # Electricity input: enforce 198 MJ = 55 kWh per kg H2 (as per your openLCA screenshot)
        add_tech(a, elec_provider, float(P.H2_PEM_ELECTRICITY_KWH_PER_KG))
        return a

    # 2) H2_GREEN: H2_avg structure, electricity forced to renew100
    h2_green = _clone_h2_avg_with_electricity(
        "h2_green_1kg",
        "Hydrogen, PEM electrolysis (GREEN: renew100 electricity), 1 kg at plant",
        elec_mix_renew100,
    )

    # 3) H2_GREYWASH: H2_avg structure, electricity forced to worst-case mix
    h2_greywash = _clone_h2_avg_with_electricity(
        "h2_greywash_1kg",
        "Hydrogen, PEM electrolysis (GREYWASH electricity), 1 kg at plant",
        elec_mix_greywash,
    )

    # ---- Hydrogen import (ocean transport + production) ----
    def _build_h2_import(code: str, name: str, h2_prod: bw.Activity) -> bw.Activity:
        a = _new_fg_activity(
            fg,
            code=code,
            name=name,
            unit="kg",
            location="KR",
            stage="transport",
        )
        add_tech(a, h2_prod, 1.0)
        add_tech(a, h2_transport, 1.0)
        return a

    h2_import_uslci = _build_h2_import("h2_import_uslci_1kg", "Hydrogen import (USLCI), 1 kg delivered", h2_uslci)
    h2_import_green = _build_h2_import("h2_import_green_1kg", "Hydrogen import (GREEN), 1 kg delivered", h2_green)
    h2_import_grey  = _build_h2_import("h2_import_greywash_1kg", "Hydrogen import (GREYWASH), 1 kg delivered", h2_greywash)

    def _build_zcgt(code: str, name: str, h2_import: bw.Activity) -> bw.Activity:
        a = _new_fg_activity(
            fg,
            code=code,
            name=name,
            unit="kilowatt hour",
            location="KR",
            stage="power_generation",
        )

        # CAPSS proxy for air pollutants: use LNG g/kWh
        for pol, g in P.GEN_G_PER_KWH.get("lng", {}).items():
            add_bio(a, bio_flow(pol), float(g) / 1000.0)

        # CO2 cut-off (combustion CO2 = 0)
        add_bio(a, bio_flow("CO2"), 0.0)

        # H2 requirement (kg/kWh), delivered to Korea
        add_tech(a, h2_import, float(P.H2_KG_PER_KWH_ZCGT))

        return a

    elec_zcgt_uslci = _build_zcgt(
        "elec_zero_carbon_gt_uslci_1kwh",
        "Electricity, zero-carbon GT (H2 import, USLCI), 1 kWh",
        h2_import_uslci,
    )
    elec_zcgt_green = _build_zcgt(
        "elec_zero_carbon_gt_green_1kwh",
        "Electricity, zero-carbon GT (H2 import, GREEN), 1 kWh",
        h2_import_green,
    )
    elec_zcgt_grey = _build_zcgt(
        "elec_zero_carbon_gt_greywash_1kwh",
        "Electricity, zero-carbon GT (H2 import, GREYWASH), 1 kWh",
        h2_import_grey,
    )

    # Default zero-carbon GT source used in mixes (choose USLCI by default)
    elec_src["zero_carbon_gt"] = elec_zcgt_uslci

    # ---- Fill KR 2022 mix ----
    for src in ["coal", "lng", "nuclear", "zero_carbon_gt", "renew"]:
        v = float(shares.get(src, 0.0))
        if v <= 0:
            continue
        add_tech(elec_mix, elec_src[src], v)


# ------------------------------------------------------------
    # 5b) E-gasoline (synthetic gasoline) production (refining_or_power)
    #     - DAC: CO2 from air as *resource* + electricity
    #     - PTL synthesis: CO2 + H2 -> e-gasoline, with PTL_SYNTH_EFF applied via H2 requirement
    # ------------------------------------------------------------

    # (1) Hydrogen for e-gasoline: clone the USLCI PEM structure but force electricity to KR 2022 mix
    h2_krgrid = _clone_h2_avg_with_electricity(
        "h2_krgrid_1kg",
        "Hydrogen, PEM electrolysis (KR grid electricity), 1 kg at plant",
        elec_mix,
    )

    # (2) DAC CO2 capture: 1 kg CO2 captured from air
    dac_co2 = _new_fg_activity(
        fg,
        code="dac_co2_1kg",
        name="Direct air capture (electric-only), 1 kg CO2 captured",
        unit="kg",
        location="KR",
        stage="refining_or_power",
    )
    # Electricity demand (kWh per kg CO2)
    add_tech(dac_co2, elec_mix, float(P.DAC_KWH_PER_KGCO2))
    # CO2 uptake from air as *resource* (kg)
    add_bio(dac_co2, bio_flow("CO2_RESOURCE"), 1.0)

    # (3) PTL synthesis to e-gasoline: 1 kg fuel
    e_gasoline_prod = _new_fg_activity(
        fg,
        code="e_gasoline_prod_1kg",
        name="E-gasoline production (PtL synthesis), 1 kg",
        unit="kg",
        location="KR",
        stage="refining_or_power",
    )

    # Technosphere inputs
    # - H2 (kg/kg-fuel) derived from energy balance + PTL_SYNTH_EFF
    add_tech(e_gasoline_prod, h2_krgrid, float(P.E_GASOLINE_H2_KG_PER_KG))

    # - CO2 feedstock supplied by DAC (kg/kg-fuel)
    add_tech(e_gasoline_prod, dac_co2, float(P.E_GASOLINE_CO2_KG_PER_KG))

    # Biosphere resource inputs (kept as simple placeholders)
    add_bio(e_gasoline_prod, bio_flow("WATER_RESOURCE"), float(P.E_GASOLINE_WATER_KG_PER_KG))


    # ------------------------------------------------------------
    # 6) Vehicle operation (vehicle operation), 1 km
    # ------------------------------------------------------------
    def build_op_ice(fuel: str, code: str, refinery_act) -> bw.Activity:
        a = _new_fg_activity(
            fg,
            code=code,
            name=f"Operation, {fuel}, 1 km",
            unit="kilometer",
            location="KR",
            stage="vehicle_operation",
        )

        add_tech(a, refinery_act, float(P.FUEL_KG_PER_KM[fuel]))

        # Tailpipe CAPSS pollutants (g/km -> kg/km)
        for pol, g in P.TAILPIPE_G_PER_KM.get(fuel, {}).items():
            add_bio(a, bio_flow(pol), float(g) / 1000.0)

        # CO2 (kg/km)
        add_bio(a, bio_flow("CO2"), float(P.CO2_KG_PER_KM[fuel]))

        return a

    build_op_ice("gasoline", "op_gasoline_1km", refinery_gas)
    build_op_ice("diesel", "op_diesel_1km", refinery_dsl)

    # E-gasoline (tailpipe assumed same as gasoline; upstream differs)
    op_egas = _new_fg_activity(
        fg,
        code="op_e_gasoline_1km",
        name="Operation, E-gasoline ICE, 1 km",
        unit="kilometer",
        location="KR",
        stage="vehicle_operation",
    )
    add_tech(op_egas, e_gasoline_prod, float(P.FUEL_KG_PER_KM["e_gasoline"]))
    for pol, g in P.TAILPIPE_G_PER_KM.get("e_gasoline", P.TAILPIPE_G_PER_KM["gasoline"]).items():
        add_bio(op_egas, bio_flow(pol), float(g) / 1000.0)
    add_bio(op_egas, bio_flow("CO2_RESOURCE"), float(P.CO2_KG_PER_KM.get("e_gasoline", P.CO2_KG_PER_KM["gasoline"])))

    op_ev = _new_fg_activity(
        fg,
        code="op_ev_1km",
        name="Operation, EV, 1 km",
        unit="kilometer",
        location="KR",
        stage="vehicle_operation",
    )
    add_tech(op_ev, elec_mix, float(getattr(P, 'EV_GRID_KWH_PER_KM', P.EV_KWH_PER_KM)))

    return {
        # Keep original keys used by build_wtw.py/main.py
        "refinery_gasoline_1kg": (P.FG_DB_NAME, "refinery_gasoline_1kg"),
        "refinery_diesel_1kg": (P.FG_DB_NAME, "refinery_diesel_1kg"),
        "elec_mix_1kwh": (P.FG_DB_NAME, "elec_mix_1kwh"),
        "op_gasoline_1km": (P.FG_DB_NAME, "op_gasoline_1km"),
        "op_diesel_1km": (P.FG_DB_NAME, "op_diesel_1km"),
        "op_ev_1km": (P.FG_DB_NAME, "op_ev_1km"),
        "op_e_gasoline_1km": (P.FG_DB_NAME, "op_e_gasoline_1km"),
        # Expose stage nodes for debugging if you want
        "crude_extraction_mix_1kg": (P.FG_DB_NAME, "crude_extraction_mix_1kg"),
        "crude_ocean_transport_1kg": (P.FG_DB_NAME, "crude_ocean_transport_1kg"),
        "coal_extraction_1kg": (P.FG_DB_NAME, "coal_extraction_1kg"),
        "coal_ocean_transport_1kg": (P.FG_DB_NAME, "coal_ocean_transport_1kg"),
        "ng_processing_1kg": (P.FG_DB_NAME, "ng_processing_1kg"),
        "lng_ocean_transport_1kg": (P.FG_DB_NAME, "lng_ocean_transport_1kg"),
        "uranium_supply_1kg": (P.FG_DB_NAME, "uranium_supply_1kg"),
    }