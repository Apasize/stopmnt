#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
figures_v6.py

Deux figures des consignes v6 :
  (a) rayon_interieur : rayon fiable (probit, 20 repetitions) en fonction de la
      perte en interieur 0, 10, 14, 20, 25 dB, par zone (portee_interieur_v6) ;
  (b) exigences_pavage : part des alertes livrees en 15 min et part des
      patients a 95 % de routine en 72 h, selon l'espacement des passerelles
      dans le reseau pave (exigences_v6.csv, experience exigences_pavage_v6,
      tout confirme RX2).
"""
import argparse
import csv
import os
import re
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

LIB = {"urbain_dense": "Urbain dense", "peri_urbain": "Péri-urbain", "rural_degage": "Rural dégagé",
       "rural_arbore": "Rural arboré (0,35)", "lacustre": "Lacustre"}
COUL = {"urbain_dense": "#2a78d6", "peri_urbain": "#eb6834", "rural_degage": "#1baf7a",
        "rural_arbore": "#eda100", "lacustre": "#e87ba4"}


def style(ax):
    ax.set_facecolor("#fcfcfb")
    ax.grid(True, color="#e4e3df", linewidth=0.6)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.tick_params(labelsize=8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    # (a)
    pts = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(a.prod, "portee_interieur_v6", "rayon_fiable_probit",
                                              "rayon_fiable_probit.csv"), encoding="utf-8")):
        m = re.match(r"(\w+) \| interieur=([\d.]+)", r["groupe"])
        pts[m.group(1)].append((float(m.group(2)), int(r["rayon_fiable_m"]) / 1000))
    fig, ax = plt.subplots(figsize=(8, 4.2), facecolor="#fcfcfb")
    style(ax)
    for z in LIB:
        v = sorted(pts.get(z, []))
        if v:
            ax.plot([x for x, _ in v], [y for _, y in v], "-o", color=COUL[z], linewidth=2, markersize=4, label=LIB[z])
    ax.axvline(14.2, color="#0b0b0b", linewidth=1)
    ax.text(14.4, ax.get_ylim()[1] * 0.6 if ax.get_yscale() == "linear" else 10, " P.2109, 14,2 dB", fontsize=8)
    ax.set_yscale("log")
    ax.set_xlabel("perte en intérieur (dB), montée et descente", fontsize=8)
    ax.set_ylabel("rayon fiable (km), échelle log", fontsize=8)
    ax.legend(fontsize=8, frameon=False)
    fig.text(0.01, 0.01, "Pont à l'intérieur en permanence, sensibilité SX1302, antenne 5 dBi, 20 répétitions, méthode probit.",
             fontsize=7.5, color="#52514e")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(a.out, f"rayon_interieur.{ext}"), dpi=200, facecolor="#fcfcfb")
    plt.close(fig)
    # (b)
    ex = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(a.out, "exigences_v6.csv"), encoding="utf-8")):
        if r["experience"] != "exigences_pavage_v6" or "tout_confirme" not in r["variante"]:
            continue
        e = float(re.search(r"espacement=([\d.]+)", r["variante"]).group(1))
        ex[r["zone"]].append((e, 100 * float(r["alerte_15min"]), 100 * float(r["patients_72h_ok"])))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), facecolor="#fcfcfb")
    for ax, k, tit, seuil in ((axes[0], 1, "Alertes livrées en 15 min (%)", 99),
                              (axes[1], 2, "Patients à 95 % de routine en 72 h (%)", 95)):
        style(ax)
        for z in LIB:
            v = sorted(ex.get(z, []))
            if v:
                ax.plot([p[0] for p in v], [p[k] for p in v], "-o", color=COUL[z], linewidth=2, markersize=4, label=LIB[z])
        ax.axhline(seuil, color="#52514e", linewidth=1, linestyle=(0, (4, 3)))
        ax.set_title(tit, fontsize=10, loc="left")
        ax.set_xlabel("espacement des passerelles (rayons de dimensionnement)", fontsize=8)
        ax.set_xticks([2, 3, 4])
    axes[0].legend(fontsize=8, frameon=False, loc="lower left")
    fig.text(0.01, 0.01, "Réseau pavé à 7 passerelles, 200 patients dans la cellule centrale, tout confirmé RX2, pont à l'intérieur, "
             "4 jours, 10 répétitions. Tirets : exigence.", fontsize=7.5, color="#52514e")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(a.out, f"exigences_pavage.{ext}"), dpi=200, facecolor="#fcfcfb")


if __name__ == "__main__":
    main()
