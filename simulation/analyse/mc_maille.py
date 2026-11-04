#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monte-Carlo du choix maille par maille : chaque tirage fixe tous les parametres de cout dans leur plage, puis resout le probleme."""
import argparse
import copy
import csv
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimisation_cout as O

CACHE = {}


def tirer(d, rnd):
    for k, v in d.items():
        if isinstance(v, dict):
            tirer(v, rnd)
        elif isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v) and not isinstance(v[0], bool):
            x = rnd.uniform(float(v[0]), float(v[1]))
            d[k] = [x, x]


def _mailles(cfg, a):
    return CACHE["m"]


def init(m):
    CACHE["m"] = m
    O.mailles = _mailles


def un(t):
    k, niv, a, cfg, prod = t
    sc = dict(nom=f"mc{k}_{niv}", structure=niv, j=None, fraction=.02)
    r = O.un((sc, a, cfg, prod))[0]
    os.remove(os.path.join(a.out, f"mailles_mc{k}_{niv}.csv"))
    r["tirage"] = k
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.json")
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--placement", default="placement_v62")
    ap.add_argument("--raster", default="donnees/worldpop/ben_pop_2021_CN_100m_R2024B_v1.tif")
    ap.add_argument("--worldcover", default="donnees/worldcover/ESA_WorldCover_10m_2021_v200_N06E000_Map.tif")
    ap.add_argument("--villes", default="donnees/arcep/cities.json")
    ap.add_argument("--synthese", default="resultats/production/multi_passerelles_v6_fusion/multi_passerelles_synthese_production.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tirages", type=int, default=60)
    ap.add_argument("--graine", type=int, default=2026)
    ap.add_argument("--jobs", type=int, default=9)
    ap.add_argument("--limite", type=float, default=240)
    ap.add_argument("--gap", type=float, default=0.005)
    ap.add_argument("--fils", type=int, default=1)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    rnd = random.Random(a.graine)
    prod = os.path.abspath(a.prod)
    m = O.mailles(cfg, a)
    T = []
    for k in range(a.tirages):
        c = copy.deepcopy(cfg)
        tirer(c["cout"], rnd)
        for niv in ("bas", "haut"):
            T.append((k, niv, a, c, prod))
    champs = ["tirage", "structure", "eur_patient_an", "borne_inf_eur_patient_an", "tout_cellulaire_eur", "passerelles", "part_patients_lora", "charge_max_passerelle", "doublees_capacite", "statut"]
    with open(os.path.join(a.out, "mc_maille.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore")
        w.writeheader()
        with ProcessPoolExecutor(max_workers=a.jobs, initializer=init, initargs=(m,)) as pool:
            for i, r in enumerate(pool.map(un, T)):
                w.writerow(r)
                f.flush()
                print(i + 1, len(T), r["structure"], r["eur_patient_an"], r["tout_cellulaire_eur"], r["passerelles"], flush=True)


if __name__ == "__main__":
    main()
