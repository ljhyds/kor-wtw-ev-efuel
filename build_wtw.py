# -*- coding: utf-8 -*-
"""
build_wtw.py
===========
Convenience wrapper that ensures the foreground DB is built and returns the FU activities.
"""

from __future__ import annotations

from typing import Dict, Tuple

import brightway2 as bw

import param as P
from build_process import build_foreground_db


def build_and_get_fu() -> Dict[str, Tuple[str, str]]:
    keys = build_foreground_db()
    return {
        "GASOLINE_1KM": keys["op_gasoline_1km"],
        "DIESEL_1KM":   keys["op_diesel_1km"],
        "EV_1KM":       keys["op_ev_1km"],
        "E_GASOLINE_1KM": keys["op_e_gasoline_1km"],
    }
