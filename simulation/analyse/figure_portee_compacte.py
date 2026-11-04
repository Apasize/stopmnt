#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
figure_portee_compacte.py

Figure de portee pour le memoire (revue du 2026-10-27) : une vignette par zone,
antenne centrale (gain=5), arbore a la densite centrale du config. Dans chaque
vignette :
  - points : livraison moyenne par bande (20 bandes), zone ombree : IC 95 %
    sur les repetitions (consignes v4, point 2) ;
  - courbe : ajustement probit p(d) = pmax Phi((a - log10 d) / s) sur les
    donnees par noeud (analyse/rayon_fiable.py) ;
  - trait plein : rayon fiable retenu (borne basse IC 95 % du rayon a 95 %,
    bootstrap) ; tirets horizontaux : seuil de 95 %.

Usage : figure_portee_compacte.py --config config/config.json
        --noeuds resultats/production/portee/noeuds_portee_*.csv
        --bandes .../rayon_fiable_20bandes/rayon_fiable_bandes.csv
        --rayons .../rayon_fiable_probit/rayon_fiable_probit.csv --sortie fichier
"""
import argparse
import csv
import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import norm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rayon_fiable as RF  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--config", required=True)
ap.add_argument("--noeuds", required=True, nargs="+")
ap.add_argument("--bandes", required=True)
ap.add_argument("--rayons", required=True)
ap.add_argument("--sortie", required=True)
ap.add_argument("--gain", default="5")
ap.add_argument("--repetitions", default="20")
ap.add_argument("--arbore-sans-densite", action="store_true",
                help="etiquette de groupe sans la densite (experience sans balayage de vegetation)")
a = ap.parse_args()
cfg = json.load(open(a.config, encoding="utf-8"))
dens = cfg["zones"]["rural_arbore"]["vegetation"]["densite_centrale"]
LIB = {"urbain_dense": "Urbain dense", "peri_urbain": "Péri-urbain", "rural_degage": "Rural dégagé",
       "rural_arbore": f"Rural arboré (densité {str(dens).replace('.', ',')})", "lacustre": "Lacustre"}
COUL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]


def groupe(z):
    if z == "rural_arbore" and not a.arbore_sans_densite:
        return f"rural_arbore | vegetation={dens} gain={a.gain}"
    return f"{z} | gain={a.gain}"


ray = {r["groupe"]: r for r in csv.DictReader(open(a.rayons, encoding="utf-8"))}
bandes = [b for b in csv.DictReader(open(a.bandes, encoding="utf-8"))]
pts = {}
for ch in a.noeuds:
    for r in csv.DictReader(open(ch, encoding="utf-8")):
        g = f"{r['zone']} | {r['variante']}"
        if int(r["newSent"]) > 0 and float(r["distance_m"]) <= 21002.6:
            pts.setdefault(g, []).append((float(r["distance_m"]), int(r["received"]), int(r["newSent"])))

fig, axes = plt.subplots(2, 3, figsize=(13, 7.5), facecolor="#fcfcfb")
axes = list(axes.flat)
axes[-1].axis("off")
for i, (z, ax) in enumerate(zip(LIB, axes)):
    g = groupe(z)
    ax.set_facecolor("#fcfcfb")
    bs = [b for b in bandes if b["groupe"] == g]
    x = [(float(b["d_min_m"]) + float(b["d_max_m"])) / 2000 for b in bs]
    moy = [100 * float(b["taux_moyen"]) for b in bs]
    bas = [100 * float(b["ic95_bas"]) for b in bs]
    # IC 95 % symetrique (Student sur les repetitions) : haut = 2 x moyenne - bas.
    ax.fill_between(x, bas, [min(100.0, 2 * m - b) for m, b in zip(moy, bas)], color=COUL[i], alpha=0.22,
                    linewidth=0, label="IC 95 % par bande")
    ax.plot(x, moy, "o", color=COUL[i], markersize=4, label="moyenne par bande")
    pm, aa, s = RF.ajuste_probit(pts[g])
    xd = np.linspace(0.2, max(x) if x else 1, 200)
    ax.plot(xd, 100 * pm * norm.cdf((aa - np.log10(xd * 1000)) / s), color=COUL[i], linewidth=2, label="ajustement probit")
    rf = int(ray[g]["rayon_fiable_m"]) / 1000
    ax.axvline(rf, color="#0b0b0b", linewidth=1.3)
    ax.axhline(95, color="#52514e", linewidth=1, linestyle=(0, (4, 3)))
    ax.text(rf, 61, f" {rf:.1f} km".replace(".", ","), fontsize=9, color="#0b0b0b")
    ax.set_ylim(60, 101)
    ax.set_title(LIB[z], fontsize=10, loc="left")
    ax.grid(True, color="#e4e3df", linewidth=0.6)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.tick_params(labelsize=8)
    ax.set_xlabel("distance à la passerelle (km)", fontsize=8)
    ax.set_ylabel("mesures livrées (%)", fontsize=8)
h, l = axes[0].get_legend_handles_labels()
axes[-1].legend(h, l, fontsize=9, frameon=False, loc="center left")
fig.text(0.01, 0.01, f"Antenne de passerelle {a.gain} dBi, 400 patients, {a.repetitions} répétitions. Trait vertical : rayon fiable = "
         "borne basse (2,5 %) du rayon où la courbe ajustée vaut 95 %, par bootstrap sur les répétitions.",
         fontsize=8, color="#52514e")
fig.tight_layout(rect=(0, 0.03, 1, 1))
for ext in ("png", "pdf"):
    fig.savefig(f"{a.sortie}.{ext}", dpi=200, facecolor="#fcfcfb")
print(a.sortie)
