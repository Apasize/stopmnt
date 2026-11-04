#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convergence selon le nombre de tirages (500, 1 000, 2 000, 5 000) : memes graines, suite prolongee.
Entree : tirages_couts_{bas,haut}.npz de convention_v63.py --tirages 5000. Sortie : convergence_n.csv."""
import argparse, csv, os
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--dossier", default="resultats/production/final/convergence_5000")
ap.add_argument("--reference", default="resultats/production/final/convergence")
a = ap.parse_args()
out = []
for niv in ("bas", "haut"):
    d = np.load(os.path.join(a.dossier, f"tirages_couts_{niv}.npz"))
    ref = np.load(os.path.join(a.reference, f"tirages_couts_{niv}.npz"))
    N = float(d["N"])
    choix = d["choix_par_commune"] / N
    cell = d["tout_cellulaire_sous_convention"] / N
    lora = np.minimum(d["tout_LoRa_sans_convention"], d["tout_LoRa_sous_convention"]) / N
    mixte = d["cl"] == 2
    ecart_ref = float(np.abs(d["choix_par_commune"][:500] - ref["choix_par_commune"]).max())
    for n in (500, 1000, 2000, 5000):
        i = slice(0, n)
        best = np.minimum(lora[i], cell[i])
        out.append({"structure": niv, "tirages": n, "ecart_max_500_reference_eur": round(ecart_ref, 6),
                    "mediane_choix": round(float(np.median(choix[i])), 2),
                    "p2_5_choix": round(float(np.percentile(choix[i], 2.5)), 2),
                    "p97_5_choix": round(float(np.percentile(choix[i], 97.5)), 2),
                    "mediane_cellulaire": round(float(np.median(cell[i])), 2),
                    "p_mixte": round(float(mixte[i].mean()), 4),
                    "p_lora_moins_cher": round(float((lora[i] < cell[i]).mean()), 4),
                    "economie_mediane_pct": round(float(100 * np.median((best - choix[i]) / best)), 2)})
with open(os.path.join(a.dossier, "convergence_n.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
for r in out: print(r)
