#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyse_mobilite_interieur.py

Complement aux consignes v6, point 1 : pont porte par le patient, part du temps
a l'interieur combinee aux scenarios de mobilite (politiques de SF, store-and-
forward). Lit les sorties brutes de run_mobilite.py (fichiers
brut_<scenario>_<variante>_fi<fraction>_run<k>.txt) et rapporte, pour les
patients MOBILES seulement, moyenne et IC 95 % sur les repetitions :
  - routine : part des mesures livrees en 72 h au plus (absorbee par le tampon
    quand le store-and-forward est actif) ;
  - alertes : part livree en 15 min, toutes et emises a l'interieur (cas critique).
Sortie : mobilite_interieur.csv.
"""
import argparse
import csv
import glob
import math
import os
import re
import statistics as st
from collections import defaultdict

from scipy.stats import t as student


def ic(v):
    return student.ppf(0.975, len(v) - 1) * st.stdev(v) / math.sqrt(len(v)) if len(v) > 1 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brut", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    acc = defaultdict(lambda: defaultdict(list))
    for ch in glob.glob(os.path.join(a.brut, "brut_*_fi*_run*.txt")):
        m = re.match(r"brut_([a-z]_[a-z_]+?)_((?:mobile|sfw|base).*)_fi([\d.]+)_run(\d+)\.txt", os.path.basename(ch))
        cle = (m.group(1), m.group(2), float(m.group(3)))
        el = ok = na = ok15 = ni = okin = 0
        for l in open(ch, encoding="utf-8"):
            if not l.startswith("NODE;"):
                continue
            c = l[5:].strip().split(";")
            if len(c) < 53 or int(c[28]) != 1:
                continue
            el += int(c[40]); ok += int(c[41]); na += int(c[42]); ok15 += int(c[43])
            ni += int(c[47]); okin += int(c[48])
        d = acc[cle]
        if el:
            d["routine_72h"].append(ok / el)
        if na:
            d["alerte_15min"].append(ok15 / na)
        if ni:
            d["alerte_interieur_15min"].append(okin / ni)
    lignes = []
    for (sc, var, fi), d in sorted(acc.items()):
        l = {"scenario": sc, "variante": var, "fraction_interieur": fi,
             "repetitions": max(len(v) for v in d.values()) if d else 0}
        for k in ("routine_72h", "alerte_15min", "alerte_interieur_15min"):
            v = d.get(k, [])
            l[k] = round(st.mean(v), 4) if v else ""
            l[k + "_ic95"] = round(ic(v), 4) if len(v) > 1 else ""
        lignes.append(l)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "mobilite_interieur.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)
    for l in lignes:
        print(l)


if __name__ == "__main__":
    main()
