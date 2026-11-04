#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
figure_rx2_rx1.py

Consignes v4, points 10 et 13 : effet de RX2 a 14 dBm (au lieu de 27) et d'un
delai RX1 de 5 s (au lieu de 1) sur le tout confirme RX2, a tirage identique.
Lit capacite_points_production.csv de reglementaire_rx2_14dbm et de
delai_rx1_5s. Trois vignettes : taux d'accuses de routine et energie radio du
pont (RX2), delai d'accuse p95 (RX1). Moyenne et IC 95 % sur 10 repetitions.
"""
import argparse
import csv
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ZONES = {"urbain_dense": ("Urbain dense", "#2a78d6"), "rural_degage": ("Rural dégagé", "#1baf7a")}


def lire(chemin, cle):
    out = {}
    for r in csv.DictReader(open(chemin, encoding="utf-8")):
        if r["mode"] != "tout_confirme_rx2":
            continue
        v = float(re.search(cle + r"=([\d.]+)", r["variante"]).group(1))
        out.setdefault((r["zone"], v), []).append(r)
    for k in out:
        out[k].sort(key=lambda r: int(r["nDevices"]))
    return out


def trace(ax, d, champ, echelle, styles, lab_val):
    for (z, v), rows in sorted(d.items()):
        x = [int(r["nDevices"]) for r in rows]
        y = [echelle * float(r[champ]) for r in rows]
        e = [echelle * float(r[champ + "_ic95"]) if r[champ + "_ic95"] not in ("nan", "inf", "") else 0 for r in rows]
        lib, c = ZONES[z]
        ax.fill_between(x, [a - b for a, b in zip(y, e)], [a + b for a, b in zip(y, e)], color=c, alpha=0.15, linewidth=0)
        ax.plot(x, y, styles[v], color=c, linewidth=2, marker="o", markersize=4, label=f"{lib}, {lab_val(v)}")
    ax.set_xscale("log")
    ax.set_xlabel("patients par passerelle", fontsize=8)
    ax.grid(True, color="#e4e3df", linewidth=0.6)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.tick_params(labelsize=8)
    ax.set_facecolor("#fcfcfb")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--sortie", required=True)
    a = ap.parse_args()
    rx2 = lire(os.path.join(a.prod, "reglementaire_rx2_14dbm", "capacite_points_production.csv"), "rx2dbm")
    rx1 = lire(os.path.join(a.prod, "delai_rx1_5s", "capacite_points_production.csv"), "rx1")
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), facecolor="#fcfcfb")
    trace(axes[0], rx2, "routine_taux_acquit", 100, {27.0: "-", 14.0: "--"}, lambda v: f"RX2 {v:g} dBm")
    axes[0].set_ylabel("trames de routine acquittées (%)", fontsize=8)
    axes[0].set_title("RX2 : accusés reçus", fontsize=10, loc="left")
    trace(axes[1], rx2, "energie_j_jour", 1, {27.0: "-", 14.0: "--"}, lambda v: f"RX2 {v:g} dBm")
    axes[1].set_ylabel("énergie radio du pont (J par jour)", fontsize=8)
    axes[1].set_title("RX2 : énergie du pont", fontsize=10, loc="left")
    trace(axes[2], rx1, "routine_p95_acquit_s", 1, {1.0: "-", 5.0: "--"}, lambda v: f"RX1 à {v:g} s")
    axes[2].axhline(60, color="#52514e", linewidth=1, linestyle=(0, (4, 3)))
    axes[2].set_yscale("log")
    axes[2].set_ylabel("délai d'accusé, 95e centile (s)", fontsize=8)
    axes[2].set_title("RX1 : délai d'accusé", fontsize=10, loc="left")
    for ax in axes:
        ax.legend(fontsize=7, frameon=False)
    fig.text(0.01, 0.01, "Tout confirmé RX2, 10 messages par patient et par jour, antenne 5 dBi, 10 répétitions, mêmes tirages "
             "d'un réglage à l'autre. Zone ombrée : IC 95 %. Tirets horizontaux : critère de 60 s.", fontsize=7.5, color="#52514e")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(f"{a.sortie}.{ext}", dpi=200, facecolor="#fcfcfb")


if __name__ == "__main__":
    main()
