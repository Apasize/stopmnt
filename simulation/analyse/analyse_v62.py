#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyse_v62.py

Complement v6.2 :
  - point 7, alarme en deux temps (experience alarme_deux_temps_v62) : par zone,
    espacement et variante (alarme immediate / en deux temps), moyenne et
    ecart-type sur les repetitions de :
      fausses alarmes = alarmes sur alertes livrees / alertes comptees ;
      detection des vrais echecs = alarmes sur alertes non livrees / alertes non
      livrees (non livrees = comptees - livrees en 15 min) ;
      delai de detection d'un vrai echec (production -> alarme), moyen et maximal ;
  - point 4, parade sans cellulaire (experience parade_ouverture_v62) : patients
    en ombre profonde a 14,2 dB (livraison < 50 %), suivis par (repetition,
    numero de noeud) a 5 et 0 dB : part de ces patients qui retrouvent une
    livraison d'au moins 95 %.
Sorties : alarme_deux_temps.csv, parade_ouverture.csv.
"""
import argparse
import csv
import glob
import math
import os
import re
import statistics as st
from collections import defaultdict


def ms(v):
    v = [x for x in v if not math.isnan(x)]
    return (round(st.mean(v), 4) if v else "", round(st.stdev(v), 4) if len(v) > 1 else "", len(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    # Alarme en deux temps.
    acc = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for ch in glob.glob(os.path.join(a.prod, "alarme_deux_temps_v62", "noeuds_*.csv")):
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            e = re.search(r"espacement=([\d.]+)", r["variante"]).group(1)
            d = re.search(r"deuxtemps=([\d.]+)", r["variante"]).group(1)
            k = (r["zone"], float(e), int(float(d)))
            c = acc[k][r["runNumber"]]
            for f in ("alertsCounted", "alertsOk15", "falseAlarms", "trueAlarms", "detectSum_s"):
                c[f] += float(r[f])
            c["detectMax_s"] = max(c["detectMax_s"], float(r["detectMax_s"]))
    lignes = []
    for (z, e, d), runs in sorted(acc.items()):
        fa, det, dmoy, dmax = [], [], [], []
        for c in runs.values():
            fa.append(c["falseAlarms"] / c["alertsCounted"] if c["alertsCounted"] else float("nan"))
            nl = c["alertsCounted"] - c["alertsOk15"]
            det.append(c["trueAlarms"] / nl if nl > 0 else float("nan"))
            dmoy.append(c["detectSum_s"] / c["trueAlarms"] / 3600 if c["trueAlarms"] else float("nan"))
            dmax.append(c["detectMax_s"] / 3600 if c["trueAlarms"] else float("nan"))
        l = {"zone": z, "espacement": e, "alarme": "deux temps" if d else "immediate"}
        for nom, v in (("fausses_alarmes", fa), ("detection_vrais_echecs", det),
                       ("delai_detection_moyen_h", dmoy), ("delai_detection_max_h", dmax)):
            m, s, n = ms(v)
            l[nom], l[nom + "_et"] = m, s
        l["repetitions"] = len(runs)
        lignes.append(l)
    with open(os.path.join(a.out, "alarme_deux_temps.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)
    for l in lignes:
        print(l)
    # Parade.
    taux = defaultdict(dict)   # (zone, espacement, run, node) -> {int_sim: taux}
    for ch in glob.glob(os.path.join(a.prod, "parade_ouverture_v62", "noeuds_*.csv")):
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            if int(r["newSent"]) <= 0 or int(r["mobile"]) == 1:
                continue
            e = float(re.search(r"espacement=([\d.]+)", r["variante"]).group(1))
            si = float(re.search(r"int_sim=([\d.]+)", r["variante"]).group(1))
            taux[(r["zone"], e, r["runNumber"], r["nodeId"])][si] = int(r["received"]) / int(r["newSent"])
    par = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
    for (z, e, run, node), t in taux.items():
        ref = t.get(14.219)
        if ref is None:
            continue
        c = par[(z, e)][run]
        c[0] += 1
        if ref < 0.5:
            c[1] += 1
            c[2] += t.get(5.0, 0) >= 0.95
            c[3] += t.get(0.0, 0) >= 0.95
    lp = []
    for (z, e), runs in sorted(par.items()):
        ombre = [c[1] / c[0] for c in runs.values()]
        r5 = [c[2] / c[1] for c in runs.values() if c[1]]
        r0 = [c[3] / c[1] for c in runs.values() if c[1]]
        lp.append({"zone": z, "espacement": e, "repetitions": len(runs),
                   "part_ombre_14dB": ms(ombre)[0], "part_ombre_14dB_et": ms(ombre)[1],
                   "recuperes_a_5dB": ms(r5)[0], "recuperes_a_5dB_et": ms(r5)[1],
                   "recuperes_a_0dB": ms(r0)[0], "recuperes_a_0dB_et": ms(r0)[1]})
    with open(os.path.join(a.out, "parade_ouverture.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lp[0].keys()))
        w.writeheader()
        w.writerows(lp)
    for l in lp:
        print(l)


if __name__ == "__main__":
    main()
