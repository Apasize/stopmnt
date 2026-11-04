#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figures de resultats du memoire, dans un style commun, relues depuis les fichiers de resultats."""
import argparse
import csv
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

plt.rcParams.update({"font.family": "STIXGeneral", "mathtext.fontset": "stix", "font.size": 12,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": "#e6e8ec", "grid.linewidth": .8, "axes.axisbelow": True})
ORANGE, BLEU, ENCRE, GRIS, VERT = "#b4561c", "#2c6491", "#14213d", "#5f6773", "#2e7d4f"
ZONES = [("urbain_dense", "Urbain dense", BLEU), ("peri_urbain", "Péri-urbain", ORANGE), ("rural_degage", "Rural dégagé", VERT),
         ("rural_arbore", "Rural arboré", "#c08a10"), ("lacustre", "Lacustre", "#a8437a")]


def fr(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


def lire(*p):
    with open(os.path.join(*p), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def murs(prod, out):
    """Rayon fiable a 8 dBi, emetteur dehors (20 repetitions) et a l'interieur (100 repetitions)."""
    deh = {r["groupe"].split(" | ")[0]: float(r["rayon_fiable_m"]) / 1000
           for r in lire(prod, "final/8dbi/portee_interieur_8dbi/rayon_fiable_probit/rayon_fiable_probit.csv") if "interieur=0 gain=8" in r["groupe"]}
    ded = {r["groupe"].split(" | ")[0]: float(r["rayon_fiable_m"]) / 1000
           for r in lire(prod, "portee_gain_v61/rayon_fiable_probit/rayon_fiable_probit.csv") if r["groupe"].endswith("gain=8")}
    fig, ax = plt.subplots(figsize=(9, 3.9))
    for i, (z, n, _) in enumerate(reversed(ZONES)):
        ax.plot([ded[z], deh[z]], [i, i], color="#d9d3c7", lw=6, solid_capstyle="round", zorder=1)
        ax.scatter(ded[z], i, s=90, color=ORANGE, zorder=3, label="à l'intérieur (perte de 14,2 dB)" if i == 0 else None)
        ax.scatter(deh[z], i, s=90, color=GRIS, zorder=3, label="à l'extérieur" if i == 0 else None)
        ax.text(ded[z], i + .24, fr(ded[z]) + " km", ha="center", color=ORANGE, fontweight="bold")
        ax.text(deh[z] + .25, i, fr(deh[z]) + " km", va="center", color=GRIS)
    ax.set_yticks(range(5), [n for _, n, _ in reversed(ZONES)])
    ax.set_xlabel("rayon fiable (km)")
    ax.set_xlim(0, 23)
    ax.set_ylim(-.5, 4.7)
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "g1_murs.png"), dpi=220)
    plt.close(fig)
    return {z: (deh[z], ded[z]) for z in deh}


def accuses(pointes, out):
    d = {}
    for r in lire(pointes):
        m = re.search(r"rx1=(\d+) pic=([\d.]+)", r["variante"])
        if m and r["mode"] == "tout_confirme_rx2" and int(float(r["nDevices"])) == 200:
            d[(int(m.group(1)), float(m.group(2)))] = r
    cle = "remontee_trop_tard"
    fig, ax = plt.subplots(figsize=(8.2, 3.7))
    for rx1, c, lab in ((1, ENCRE, "délai RX1 de 1 s"), (5, ORANGE, "délai RX1 de 5 s")):
        p = sorted(k[1] for k in d if k[0] == rx1)
        y = [100 * float(d[(rx1, q)][cle]) for q in p]
        e = [100 * float(d[(rx1, q)].get(cle + "_ic95") or 0) for q in p]
        x = [100 * q for q in p]
        ax.fill_between(x, [a_ - b for a_, b in zip(y, e)], [a_ + b for a_, b in zip(y, e)], color=c, alpha=.16, linewidth=0)
        ax.plot(x, y, marker="o", color=c, lw=2.2, label=lab)
        ax.annotate(fr(y[-1], 1) + " %", (x[-1], y[-1]), xytext=(9, -4), textcoords="offset points", color=c, fontweight="bold")
    ax.set_xlabel("part des messages retardés de 1 à 6 s sur la liaison 4G de la passerelle (%)")
    ax.set_ylabel("accusés arrivés trop tard (%)")
    ax.set_xlim(-.1, 5.8)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "g3_accuses.png"), dpi=220)
    plt.close(fig)


def points(prod):
    L = lire(prod, "final/capacite_8dbi/capacite_points_production.csv")
    f = os.path.join(prod, "final/capacite_recap_8dbi/capacite_points_production.csv")
    if os.path.exists(f):
        L += lire(f)
    return L


def val(r, k):
    try:
        return float(r[k])
    except (KeyError, ValueError):
        return float("nan")


def capacite(prod, out):
    """Decrochage du tout confirme : memes seuils, toutes zones sur un meme graphe, un panneau par mode."""
    L = points(prod)
    M = [("tout_confirme_rx2", "Tout confirmé"), ("mixte_rx2", "Mixte"), ("mixte_recap_rx2", "Mixte à récapitulatif")]
    fig, ax = plt.subplots(2, 3, figsize=(10.6, 6.2), sharex=True, sharey="row")
    for j, (m, t) in enumerate(M):
        for z, n, c in ZONES:
            R = sorted((r for r in L if r["mode"] == m and r["zone"] == z), key=lambda r: float(r["nDevices"]))
            x = [float(r["nDevices"]) for r in R]
            k = "livraison_72h" if m == "mixte_recap_rx2" else "pdr_routine"
            y0 = [100 * val(r, k) for r in R]
            e0 = [100 * val(r, k + "_ic95") for r in R]
            y1 = [val(r, "alerte_p95_acquit_s") for r in R]
            e1 = [val(r, "alerte_p95_acquit_s_ic95") for r in R]
            ax[0, j].fill_between(x, [a_ - b for a_, b in zip(y0, e0)], [a_ + b for a_, b in zip(y0, e0)], color=c, alpha=.14, linewidth=0)
            ax[0, j].plot(x, y0, marker="o", ms=4, lw=1.8, color=c, label=n)
            ax[1, j].fill_between(x, [max(a_ - b, 1) for a_, b in zip(y1, e1)], [a_ + b for a_, b in zip(y1, e1)], color=c, alpha=.14, linewidth=0)
            ax[1, j].plot(x, y1, marker="o", ms=4, lw=1.8, color=c)
        ax[0, j].set_title(t, fontsize=13, fontweight="bold", color=ENCRE)
        ax[0, j].axhline(95, color=ENCRE, ls=(0, (4, 3)), lw=1)
        ax[1, j].axhline(60, color=ENCRE, ls=(0, (4, 3)), lw=1)
        ax[1, j].set_xlabel("patients par passerelle")
        ax[1, j].set_xscale("log")
        ax[1, j].set_xticks([50, 100, 200, 400, 800, 1600, 3200], ["50", "100", "200", "400", "800", "1 600", "3 200"], rotation=40)
        ax[1, j].minorticks_off()
        ax[1, j].set_yscale("log")
    ax[0, 0].set_ylabel("mesures de routine livrées (%)")
    ax[1, 0].set_ylabel("délai d'accusé d'alerte, 95$^e$ centile (s)")
    ax[0, 0].text(52, 94.2, "seuil de 95 %", fontsize=10.5, color=ENCRE)
    ax[1, 0].text(52, 66, "seuil de 60 s", fontsize=10.5, color=ENCRE)
    ax[0, 0].set_ylim(90, 100.5)
    h, l = ax[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=5, frameon=False)
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(os.path.join(out, "capacite_modes.png"), dpi=220)
    plt.close(fig)


def energie(prod, out):
    L = points(prod)
    fig, ax = plt.subplots(figsize=(8.2, 3.8))
    for m, n, c in (("tout_confirme_rx2", "Tout confirmé", ORANGE), ("mixte_recap_rx2", "Mixte à récapitulatif", BLEU), ("tout_non_confirme", "Sans accusé", VERT)):
        R = sorted((r for r in L if r["mode"] == m and r["zone"] == "rural_degage"), key=lambda r: float(r["nDevices"]))
        R = [r for r in R if 100 <= float(r["nDevices"]) <= 1600]
        x = [float(r["nDevices"]) for r in R]
        y = [val(r, "energie_j_jour") for r in R]
        e = [val(r, "energie_j_jour_ic95") for r in R]
        ax.fill_between(x, [a_ - b for a_, b in zip(y, e)], [a_ + b for a_, b in zip(y, e)], color=c, alpha=.16, linewidth=0)
        ax.plot(x, y, marker="o", lw=2, color=c, label=n)
    ax.set_xscale("log")
    ax.set_xticks([100, 200, 400, 800, 1600], ["100", "200", "400", "800", "1 600"])
    ax.minorticks_off()
    ax.set_ylim(bottom=0)
    ax.set_xlabel("patients par passerelle")
    ax.set_ylabel("énergie radio par patient (J/jour)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "g2_energie.png"), dpi=220)
    plt.close(fig)
    return {(r["mode"], int(float(r["nDevices"]))): (val(r, "energie_j_jour"), val(r, "livraison_72h"), val(r, "pdr_routine"), val(r, "patients_72h_ok"), val(r, "alerte_15min"))
            for r in L if r["zone"] == "rural_degage"}


def carte(cfg, mailles, out):
    import optimisation_cout as O

    class A:
        raster = "donnees/worldpop/ben_pop_2021_CN_100m_R2024B_v1.tif"
        worldcover = "donnees/worldcover/ESA_WorldCover_10m_2021_v200_N06E000_Map.tif"
        villes = "donnees/arcep/cities.json"
        synthese = "resultats/production/multi_passerelles_v6_fusion/multi_passerelles_synthese_production.csv"
    X, Y, W, COM, *_ = O.mailles(cfg, A())
    d = np.genfromtxt(mailles, delimiter=",", names=True)
    NOMS = {"abomey_calavi": "Abomey-Calavi", "allada": "Allada", "kpomasse": "Kpomassè", "ouidah": "Ouidah", "so_ava": "Sô-Ava",
            "toffo": "Toffo", "tori_bossito": "Tori-Bossito", "ze": "Zè"}
    fig, ax = plt.subplots(figsize=(8, 7.1))
    t = (d["patients"] / d["patients"].max()) ** .5
    for v, c, lab in ((0, BLEU, "mailles servies en cellulaire"), (1, ORANGE, "mailles servies en LoRaWAN")):
        k = d["lora"] == v
        ax.scatter(d["x_m"][k] / 1000, d["y_m"][k] / 1000, s=2 + 34 * t[k], c=c, alpha=.42, linewidths=0, label=lab)
    k = d["site"] == 1
    ax.scatter(d["x_m"][k] / 1000, d["y_m"][k] / 1000, s=26, marker="^", c=ENCRE, linewidths=0, label="passerelles ouvertes")
    for c, n in NOMS.items():
        m = COM == c
        ax.text(np.average(X[m], weights=np.sqrt(W[m])) / 1000, np.average(Y[m], weights=np.sqrt(W[m])) / 1000, n, ha="center", va="center", fontsize=12.5,
                fontweight="bold", color=ENCRE, bbox=dict(boxstyle="round,pad=.22", fc="white", ec="none", alpha=.82))
    ax.set_aspect("equal")
    ax.set_xlabel("ouest-est (km)")
    ax.set_ylabel("nord-sud (km)")
    ax.grid(False)
    leg = ax.legend(frameon=False, loc="upper left", markerscale=1.4)
    for h in leg.legend_handles:
        h.set_alpha(1)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "carte_optimisation.png"), dpi=220)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--config", default="config/config.json")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    v = murs(a.prod, a.out)
    print({k: tuple(round(x, 2) for x in w) for k, w in v.items()})
    capacite(a.prod, a.out)
    for k, w in sorted(energie(a.prod, a.out).items()):
        print(k, [round(x, 4) for x in w])
    accuses(os.path.join(a.prod, "final/8dbi/remontee_v6/capacite_points_production.csv"), a.out)
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    carte(cfg, os.path.join(a.prod, "final/optimisation/mailles_centre_detaille.csv"), a.out)


if __name__ == "__main__":
    main()
