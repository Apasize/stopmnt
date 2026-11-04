#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convergence des 500 tirages de Monte-Carlo : mediane et frequences selon le nombre de tirages, intervalle bootstrap."""
import argparse
import csv
import os

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dossier", default="resultats/production/final/convergence")
    ap.add_argument("--bootstrap", type=int, default=2000)
    a = ap.parse_args()
    rng = np.random.default_rng(1)
    out = []
    for niv in ("bas", "haut"):
        d = np.load(os.path.join(a.dossier, f"tirages_couts_{niv}.npz"))
        N = float(d["N"])
        choix = d["choix_par_commune"] / N
        cell = d["tout_cellulaire_sous_convention"] / N
        lora = np.minimum(d["tout_LoRa_sans_convention"], d["tout_LoRa_sous_convention"]) / N
        mixte = d["cl"] == 2
        n = len(choix)
        st = {"mediane_choix": lambda i: np.median(choix[i]), "p_mixte": lambda i: mixte[i].mean(),
              "p_lora_moins_cher": lambda i: (lora[i] < cell[i]).mean(),
              "economie_mediane_pct": lambda i: 100 * np.median((np.minimum(lora[i], cell[i]) - choix[i]) / np.minimum(lora[i], cell[i]))}
        for nom, f in st.items():
            tout = np.arange(n)
            v = f(tout)
            bs = np.array([f(rng.integers(0, n, n)) for _ in range(a.bootstrap)])
            sous = {m: f(np.arange(m)) for m in (100, 200, 300, 400)}
            out.append({"structure": niv, "indicateur": nom, "valeur_500": round(float(v), 4),
                        "ic95_bas": round(float(np.percentile(bs, 2.5)), 4), "ic95_haut": round(float(np.percentile(bs, 97.5)), 4),
                        **{f"premiers_{m}": round(float(x), 4) for m, x in sous.items()}})
    with open(os.path.join(a.dossier, "convergence_mc.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    for r in out:
        print(r)


if __name__ == "__main__":
    main()
