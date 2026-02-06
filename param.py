# -*- coding: utf-8 -*-
"""
param.py
========
WTW (Well-to-Wheel) model parameters, based on assumptions.txt.

Key rule (per your note):
- biosphere3 keys are UUID strings, so we use them directly as (BIO_DB_NAME, uuid)
  without reading any json mapping.

Functional unit (FU): 1 km vehicle driving distance
LCIA: ReCiPe 2016 Midpoint (H), 18 categories (log chart)
"""

# -----------------------------
# Brightway context
# -----------------------------
PROJECT_NAME = "WTW_KOR_1"
BG_DB_NAME   = "USLCI_openLCA"   # background DB (imported already in your BW project)
BIO_DB_NAME  = "biosphere3"
FG_DB_NAME   = "WTW_foreground"

# -----------------------------
# Activity UUIDs (background, USLCI)
# -----------------------------
# 1) Crude mix (weights from assumptions.txt, normalized: Middle East : Americas = 77 : 23,
# and within US ~ onshore/offshore share approximated by the selected weights in assumptions)
CRUDE_EXTRACTION = {
    "crude_us_onshore":  {"uuid": "3dd5638d-cb25-4e78-90c7-8dd98188f733", "w": 0.20},
    "crude_us_offshore": {"uuid": "76048c3b-d6d3-4f3b-8215-87ece218b4a2", "w": 0.03},
    "crude_me_onshore":  {"uuid": "fcbe548c-bcd5-40b2-979c-53df809835f9", "w": 0.77},
}
# If you later want to add more regions, add here.

# Uranium (for nuclear upstream if you choose to model it as technosphere)
URANIUM_FUEL_GRADE_UUID = "a626a6b9-3877-36f5-ac98-f5844b6348dd"

# Power plant construction (USLCI; used as proxy, wrapped into KR-located foreground acts)
PJM_COAL_CONST_UUID = "3ab6cce4-0eae-3fd5-93be-eb5048cfad8c"
PJM_NGCC_CONST_UUID = "e3284a39-e499-35dc-b27c-81a78eecdcc8"
PJM_WIND_CONST_UUID = "f9727f7b-03a5-3c3c-8b1a-80540ca6f36e"
PJM_SOLAR_PV_CONST_UUID = "2a02a37f-8433-3b6e-92c9-94818013f9da"


# -----------------------------
# Sea transport (assumption only)
# -----------------------------
SEA_DISTANCE_KM_CRUDE = 15000.0  # weighted average (assumptions.txt)
SEA_DISTANCE_KM_COAL  = 5500.0

# -----------------------------
# Refinery product yields (kg product / kg crude)
#
# We treat ~5% of refinery output as *non-energy* co-products (e.g., bitumen/
# asphalt, lubricants, specialty materials) that are outside the fuel-use
# system boundary. The remaining 95% is treated as *energy products* and used
# for LHV-based allocation among gasoline/diesel/LPG/naphtha.
# -----------------------------
NON_ENERGY_FRACTION = 0.05  # 5% by mass (default)

YIELD_GASOLINE = 0.44
YIELD_DIESEL   = 0.28
YIELD_LPG      = 0.05
YIELD_NAPHTHA  = 0.18  # petrochemical naphtha (treated as energy product here)

# -----------------------------
# Vehicle operation (tailpipe) CAPSS intensities, g/km (assumptions.txt)
# -----------------------------
TAILPIPE_G_PER_KM = {
    "gasoline": {
        "CO": 0.393262,
        "NOx": 0.0263592,
        "SOx": 0.000628156,
        "PM10": 0.000805704,
        "PM2_5": 0.00074109,
        "VOC": 0.0853883,
        "NH3": 0.00761912,
        # CO2 handled separately (below)
    },
    "diesel": {
        "CO": 0.0598509,
        "NOx": 1.0806,
        "SOx": 0.000514737,
        "PM10": 0.00519266,
        "PM2_5": 0.00477742,
        "VOC": 0.0212984,
        "NH3": 0.00192206,
    },
}

# CO2 (kg/km) from assumptions.txt (fuel economy-based)
CO2_KG_PER_KM = {
    "gasoline": 0.1925,
    "diesel":   0.1760,
}

# -----------------------------
# Fuel consumption (kg fuel / km) derived from:
#  - Gasoline FE: 12 km/L, 1 kg ≈ 1.35 L  -> (1/12)/1.35 = 0.061728... kg/km
#  - Diesel   FE: 15 km/L, 1 kg ≈ 1.19 L  -> (1/15)/1.19 = 0.056022... kg/km
# -----------------------------
FUEL_KG_PER_KM = {
    "gasoline": 1.0/12.0/1.35,
    "diesel":   1.0/15.0/1.19,
}

# EV energy use
EV_KM_PER_KWH = 5.0
EV_KWH_PER_KM = 1.0 / EV_KM_PER_KWH  # 0.2 kWh/km
# -----------------------------
# Grid losses & charging losses
# -----------------------------
# Transmission & distribution loss fraction (share of generation lost before delivery).
# Korea is around ~3% in recent years (use your preferred source/assumption).
TD_LOSS_FRACTION = 0.03

# Charging efficiency (grid-to-battery). Set to 1.0 if you don't want to model charging loss yet.
CHARGE_EFFICIENCY = 0.9

# Grid electricity required per km (kWh/km) to supply EV use-phase demand
EV_GRID_KWH_PER_KM = EV_KWH_PER_KM / ((1.0 - TD_LOSS_FRACTION) * CHARGE_EFFICIENCY)


# -----------------------------
# Refinery CAPSS intensities, g/kg-fuel (assumptions.txt)
# -----------------------------
REFINERY_G_PER_KG_FUEL = {
    "gasoline": {
        "CO": 0.0205004,
        "NOx": 0.188065,
        "SOx": 0.0349523,
        "PM10": 0.00502245,
        "PM2_5": 0.00274899,
        "VOC": 0.0117645,
        "NH3": 0.00372445,
    },
    "diesel": {
        "CO": 0.032215,
        "NOx": 0.29553,
        "SOx": 0.054925,
        "PM10": 0.00789242,
        "PM2_5": 0.00431985,
        "VOC": 0.0184871,
        "NH3": 0.00585271,
    },
}

# -----------------------------
# Refinery direct CO2 (refining step only)
# -----------------------------
# Default refinery CO2 intensity at refinery gate (g CO2 per MJ product).
# This is a tunable assumption; literature often reports a few gCO2/MJ for gasoline/diesel at gate.
REFINERY_CO2_G_PER_MJ_PRODUCT = {
    "gasoline": 6.0,
    "diesel":  6.0,
    "lpg":     6.0,
    "naphtha": 6.0,
}

# -----------------------------
# Power generation CAPSS intensities, g/kWh (assumptions.txt)
# -----------------------------
GEN_G_PER_KWH = {
    "coal": {
        "CO": 0.112155,
        "NOx": 0.122709,
        "SOx": 0.127947,
        "PM10": 0.00924402,
        "PM2_5": 0.00732975,
        "VOC": 0.0139988,
        "NH3": 0.000125345,
    },
    "lng": {
        "CO": 0.304493,
        "NOx": 0.107728,
        "SOx": 0.00269455,
        "PM10": 0.00687902,
        "PM2_5": 0.00687902,
        "VOC": 0.0412533,
        "NH3": 0.0100187,
    },
    # Nuclear operational air pollutants typically low; not provided as g/kWh in assumptions.txt.
    # We'll model nuclear as zero direct CAPSS emissions (foreground) unless you add factors later.
    "nuclear": {},
}

# Electricity generation amounts (GWh/yr, assumptions.txt) -> used for mix shares
GEN_GWH_2022 = {
    "coal":    186_748.0,
    "lng":     125_061.0,
    "nuclear": 176_054.0,
}

# -----------------------------
# 2022 KR electricity generation shares (assumptions #8)
# We explicitly include renewables (8%).
# 'other' (2%) is folded into coal/lng/nuclear proportionally (i.e., scaled into the remaining 92%).
# -----------------------------
ELEC_SHARE_2022_KR = {
    "coal": 0.34,
    "lng": 0.27,
    "nuclear": 0.29,
    "renew": 0.08,
    "other": 0.02,
}

# -----------------------------
# Electricity upstream (assumptions.txt 8~11)
# Fuel requirement per kWh

# Nuclear uranium requirement per kWh (20–25 tU/TWh -> 2.0e-5–2.5e-5 kg/kWh)
NUCLEAR_U_KG_PER_KWH = 2.5e-5

# Average ocean transport distances (km)
SEA_DISTANCE_KM_COAL = 5500.0
SEA_DISTANCE_KM_LNG  = 7000.0

# Background (USLCI) activities for fuel supply chains / transport
# Coal
UUID_COAL_EXTRACTION_IMPORT_BIT_SURFACE = "faa6de27-3440-399a-b88c-1d9789120283"
UUID_COAL_TRANSPORT_OCEAN_VESSEL_TKM    = "6e463512-53f4-3faf-96b0-f347be22ff1c"

# LNG / natural gas
UUID_NG_PROCESSING_CONVENTIONAL_KG      = "8dcef86f-cf2c-4207-91aa-1398401fe8b7"
UUID_OCEAN_FREIGHTER_AVG_FUEL_MIX_TKM   = "1e2429d8-8d91-328f-85c3-18d39bdebfa7"

# Uranium (fuel grade, regional storage)
UUID_URANIUM_FUEL_GRADE_STORAGE_KG      = "a626a6b9-3877-36f5-ac98-f5844b6348dd"

# -----------------------------
# Electricity direct CO2 (stack) using generic IPCC default emission factors (Tier 1)
# EF are on a Net Calorific Value basis.
# - Natural gas: 56.1 kg CO2 / GJ (IPCC default; commonly cited)
# - Hard/bituminous coal: 94.6 kg CO2 / GJ (IPCC default)
# We combine with LHV (MJ/kg) and fuel use (kg/kWh) to estimate kg CO2/kWh.
# -----------------------------
IPCC_EF_CO2_KG_PER_GJ = {
    "coal": 94.6,
    "lng": 56.1,
}

# Representative lower heating values (MJ/kg)
# coal: 20–24 MJ/kg -> use midpoint 23
# LNG: ~50 MJ/kg
LHV_MJ_PER_KG = {
    # Power-generation fuels
    "coal": 23.0,
    "lng":  50.0,

    # Refinery energy products (approx. LHV, MJ/kg)
    "gasoline": 44.0,
    "diesel":   43.0,
    "lpg":      46.0,
    "naphtha":  44.0,
}

# -----------------------------
# E-gasoline (synthetic gasoline / e-fuel) parameters
# -----------------------------
# We model e-gasoline production as two foreground steps:
#  1) DAC_CO2_1kg: captures 1 kg CO2 from air (as a *resource* flow) using electricity only
#  2) PTL_synthesis_1kg: converts CO2 + H2 to e-gasoline with a synthesis+upgrading efficiency
#
# Key conventions (as agreed):
# - CO2 taken from air is modeled as a *resource* (CO2_RESOURCE) so it does not receive emission CFs.
# - Tailpipe CO2 for e-gasoline is also modeled as CO2_RESOURCE (so it doesn't get emission CFs).
#
# DAC electricity demand (electric-only): 1.8 GJ/tCO2 = 0.5 kWh/kgCO2
DAC_KWH_PER_KGCO2 = 0.5

# CO2 required per kg e-gasoline (kg CO2 / kg fuel)
E_GASOLINE_CO2_KG_PER_KG = 3.10

# Water resource consumption (kg/kg) — keep as simple placeholder unless you want to refine
E_GASOLINE_WATER_KG_PER_KG = 2.0

# H2 + CO2 -> e-gasoline synthesis+upgrading efficiency (dimensionless)
# IMPORTANT: Electrolysis efficiency is already embedded in the USLCI PEM dataset used for H2.
PTL_SYNTH_EFF = 0.60

# H2 LHV (MJ/kg) used for deriving energy-basis H2 requirement
H2_LHV_MJ_PER_KG_PTL = 120.0

# H2 required per kg e-gasoline (kg H2 / kg fuel), derived from energy balance:
#   H2_LHV * m_H2 * PTL_SYNTH_EFF = LHV_fuel * 1 kg
E_GASOLINE_H2_KG_PER_KG = float(LHV_MJ_PER_KG["gasoline"]) / (PTL_SYNTH_EFF * H2_LHV_MJ_PER_KG_PTL)

# -----------------------------
# Power generation efficiencies (used to scale fuel required per kWh)
# NOTE: CAPSS pollutants are already per kWh (actual efficiencies embedded),
# but CO2 is computed from fuel combustion and must scale with efficiency.
# -----------------------------
EFF_POWER = {
    "coal": 1/2.15565,  # steam turbine average efficiency (Korean mainland)
    "lng":  1/3.07353,  # weighted average (steam turbine / combined cycle / fuel cell)
}

def _fuel_kg_per_kwh(fuel: str) -> float:
    """kg fuel required to generate 1 kWh electricity (LHV basis) with efficiency."""
    eta = float(EFF_POWER[fuel])
    lhv = float(LHV_MJ_PER_KG[fuel])  # MJ/kg
    return 3.6 / (eta * lhv)

# Fuel required per kWh (kg/kWh) — efficiency-adjusted
COAL_KG_PER_KWH = _fuel_kg_per_kwh("coal")
LNG_KG_PER_KWH  = _fuel_kg_per_kwh("lng")
def _co2_kg_per_kg_fuel(fuel: str) -> float:
    # kg CO2/kg = (kg CO2/GJ) * (MJ/kg) / 1000
    return IPCC_EF_CO2_KG_PER_GJ[fuel] * LHV_MJ_PER_KG[fuel] / 1000.0

# Direct stack CO2 per kWh from fuel combustion (kg CO2/kWh)
GEN_CO2_KG_PER_KWH = {
    "coal": COAL_KG_PER_KWH * _co2_kg_per_kg_fuel("coal"),
    "lng":  LNG_KG_PER_KWH  * _co2_kg_per_kg_fuel("lng"),
    "nuclear": 0.0,
}

def electricity_mix_share():
    total = sum(GEN_GWH_2022.values())
    return {k: v/total for k, v in GEN_GWH_2022.items()}


# -----------------------------
# Hydrogen (for zero-carbon gas turbine) — user-provided USLCI UUIDs
# -----------------------------
# PEM electrolysis (USLCI) — reference dataset outputs 1 kg H2 at plant
UUID_H2_PEM_ELECTROLYSIS_US = "f00a298a-295f-4fbc-b463-45f8e96f018b"

# Sub-processes used by the PEM dataset (kept for transparency / future replacement)
UUID_H2_PEM_STACK_1MW = "0052bd8e-51b1-4f8e-b128-53f9ab55469d"
UUID_H2_PEM_PLANT_CONSTRUCTION = "743e231a-2d7f-4fbe-ad20-bf0687bf50e1"
UUID_WATER_DEIONIZED_PROCESS = "82f8b155-a9c4-3e4b-ac66-1e33af2f8f54"

# Output/product flows (if you later want to model them explicitly)
UUID_H2_PRODUCT_FLOW = "f842f7d2-426a-44e0-ae4c-d1c96a977f84"
UUID_OXYGEN_FLOW = "22144b1f-4fc0-3643-953b-ede9a14e9ed4"

# PEM electricity requirement shown in openLCA screenshot: 198 MJ per kg H2
H2_PEM_ELECTRICITY_MJ_PER_KG = 198.0
H2_PEM_ELECTRICITY_KWH_PER_KG = H2_PEM_ELECTRICITY_MJ_PER_KG / 3.6  # 55.0 kWh/kg-H2

# Ocean shipping distance for imported hydrogen (assumption)
SEA_DISTANCE_KM_H2 = 8000.0

# "Greywash" electricity mix (worst-case exporting country proxy) — adjustable
# Intentionally fossil-heavy. Must sum to <= 1; residual treated like 'other' and folded.
ELEC_SHARE_GREYWASH = {
    "coal": 0.70,
    "lng": 0.25,
    "nuclear": 0.00,
    "renew": 0.05,
    "other": 0.00,
    "zero_carbon_gt": 0.00,
}

# Zero-carbon gas turbine (H2 turbine) performance — placeholder
H2_LHV_MJ_PER_KG = 120.0
EFF_ZCGT = 0.55  # electrical efficiency (LHV basis), placeholder
H2_KG_PER_KWH_ZCGT = 3.6 / (EFF_ZCGT * H2_LHV_MJ_PER_KG)

# -----------------------------
# biosphere3 elementary flows (UUIDs; key == uuid)
# -----------------------------
BIO_UUID = {
    "CO":    "187c525c-3715-388c-b303-a0671524a615",
    "NOx":   "4382ba18-dd21-3837-80b2-94283ef5490e",
    "SOx":   "42e4c3cb-8468-3004-bd4b-19e6cbb81687",
    "PM10":  "5a939c2b-cebf-3060-8862-4a8650caf6dd",
    "PM2_5": "49a9c581-7c83-36b0-b1bd-455ea4c665a6",
    "VOC":   "6f861846-1c4c-3fc9-a198-56b2d9abd83b",
    "NH3":   "65b5d5dd-95b5-36b2-8cb0-7c5501ff1e32",
    "CO2":   "b6f010fb-a764-3063-af2d-bcb8309a97b7",
    # Resources (for e-fuels etc.)
    "CO2_RESOURCE": "58b5cd90-8ba4-32ea-b4aa-3a3438ba8419",  # Carbon dioxide (resource/air)
    "WATER_RESOURCE": "e2eb491c-78ff-3123-9e42-494c7d199b44", # Water (resource)
    "WATER_FRESH": "8ba7dd57-b502-397b-944a-f63c6615f754",
    "WATER_BRACKISH": "a95bae36-325b-3da7-8a47-00ba98b61cfe",
    "WATER_SALINE": "67297f72-511b-3e86-b7e4-676437a75dbf",
    "WATER_RESOURCE_GENERIC": "e2eb491c-78ff-3123-9e42-494c7d199b44",
}

# -----------------------------
# ReCiPe 2016 Midpoint (H) expected shortnames (18)
# (we will discover actual BW methods by fuzzy matching in run_lcia.py)
# -----------------------------
RECIPE18 = [
    ("TAP\n(kg SO2-eq)", "Terrestrial acidification", ["terrestrial", "acidification"]),
    ("GWP\n(kg CO2-eq)", "Global warming", ["global", "warming"]),
    ("FETP\n(kg 1,4-DCB-eq)", "Freshwater ecotoxicity", ["freshwater", "ecotoxicity"]),
    ("METP\n(kg 1,4-DCB-eq)", "Marine ecotoxicity", ["marine", "ecotoxicity"]),
    ("TETP\n(kg 1,4-DCB-eq)", "Terrestrial ecotoxicity", ["terrestrial", "ecotoxicity"]),
    ("FFP\n(kg oil-eq)", "Fossil resource scarcity", ["fossil", "resource", "scarcity"]),
    ("FEP\n(kg P-eq)", "Freshwater eutrophication", ["freshwater", "eutrophication"]),
    ("MEP\n(kg N-eq)", "Marine eutrophication", ["marine", "eutrophication"]),
    ("HTPc\n(kg 1,4-DCB-eq)", "Human carcinogenic toxicity", ["human", "toxicity", "carcinogenic"]),
    ("HTPnc\n(kg 1,4-DCB-eq)", "Human non-carcinogenic toxicity", ["human", "toxicity", "non-carcinogenic"]),
    ("IRP\n(kBq Co-60-eq)", "Ionizing radiation", ["ionizing", "radiation"]),
    ("LOP\n(m2·a crop-eq)", "Land use", ["land", "use"]),
    ("SOP\n(kg Cu-eq)", "Mineral resource scarcity", ["mineral", "resource", "scarcity"]),
    ("ODPinf\n(kg CFC-11-eq)", "Stratospheric ozone depletion", ["stratospheric", "ozone", "depletion"]),
    ("PMFP\n(kg PM2.5-eq)", "Fine particulate matter formation", ["fine", "particulate", "matter", "formation"]),
    ("HOFP\n(kg NOx-eq)", "Ozone formation, Human health", ["ozone", "formation", "human", "health"]),
    ("EOFP\n(kg NOx-eq)", "Ozone formation, Terrestrial ecosystems", ["ozone", "formation", "terrestrial", "ecosystems"]),
    ("WCP\n(m3)", "Water consumption", ["water", "consumption"]),
]

CHART_OUT_PNG = "recipe18_logchart.png"
CHART_TITLE   = "EV vs Gasoline vs Diesel — ReCiPe 2016 Midpoint (H), per vehicle-km"
