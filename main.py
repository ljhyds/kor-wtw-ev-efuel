# -*- coding: utf-8 -*-
"""
main.py
=======
End-to-end runner:
1) build foreground database (WTW_foreground)
2) run ReCiPe 2016 Midpoint (H) LCIA for EV / gasoline / diesel per 1 km
3) export CSVs + chart png

Usage:
  python main.py
"""

import brightway2 as bw

import param as P
from build_wtw import build_and_get_fu
from run_lcia import run_lcia


def main():
    bw.projects.set_current(P.PROJECT_NAME)

    fu_keys = build_and_get_fu()
    run_lcia(fu_keys, out_prefix="out")


if __name__ == "__main__":
    main()
