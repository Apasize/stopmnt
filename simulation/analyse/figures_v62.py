#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
figures_v62.py

Complement v6.2, point 9 : figures finales du memoire. Pour chaque figure, un CSV
avec une ligne par repetition (valeurs de la courbe pour cette repetition),
puis la figure : moyenne et zone ombree de +/- 1 ecart-type entre repetitions
(fill_between, alpha 0,15), police serif STIX, graduations vers l'interieur.

Figures :
  portee        : mesures livrees par bande de distance (20 bandes), par zone,
                  antenne de 8 dBi (portee_gain_v61, gain=8 : reference v6.2) ;
  robustesse    : patients servis selon l'espacement, centrale en service ou en
                  panne (robustesse_v6 + robustesse_ext_v6) ;
  exigences     : alertes livrees en 5 min et patients a 95 % de routine en
                  72 h, selon l'espacement (exigences_pavage_v61, tout confirme,
                  RX2 27 dBm) ;
  capacite      : livraison de routine et delai d'accuse p95 selon le nombre de
                  patients, par mode (capacite_v6 et capacite_recap_v6).
"""
import argparse
import csv
import glob
import math
import os
import re
import statistics as st
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.family": "serif", "font.serif": ["STIXGeneral", "STIX Two Text", "DejaVu Serif"],
                     "mathtext.fontset": "stix", "xtick.direction": "in", "ytick.direction": "in",
                     "xtick.top": True, "ytick.right": True, "font.size": 9})
LIB = {"urbain_dense": "Urbain dense", "peri_urbain": "Péri-urbain", "rural_degage": "Rural dégagé",
       "rural_arbore": "Rural arboré", "lacustre": "Lacustre"}
COUL = {"urbain_dense": "#2a78d6", "peri_urbain": "#eb6834", "rural_degage": "#1baf7a",
        "rural_arbore": "#eda100", "lacustre": "#e87ba4"}
MODES = {"tout_non_confirme": ("sans accusé", "#52514e"), "mixte_rx2": ("mixte", "#2a78d6"),
         "mixte_recap_rx2": ("mixte à récapitulatif", "#1baf7a"), "tout_confirme_rx2": ("tout confirmé", "#eb6834")}


def ecrire(chemin, lignes):
    champs = []
    for l in lignes:
        for k in l:
            if k not in champs:
                champs.append(k)
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs, restval="")
        w.writeheader()
        w.writerows(lignes)


def bande(ax, x, series, coul, lab, style="-"):
    """series : liste (une par repetition) de listes alignees sur x."""
    m = [st.mean([s[i] for s in series if not math.isnan(s[i])]) for i in range(len(x))]
    e = [st.stdev([s[i] for s in series if not math.isnan(s[i])]) if len(series) > 1 else 0 for i in range(len(x))]
    ax.fill_between(x, [a - b for a, b in zip(m, e)], [a + b for a, b in zip(m, e)], color=coul, alpha=0.15, linewidth=0)
    ax.plot(x, m, style, color=coul, linewidth=1.5, label=lab)


def sauver(fig, out, nom, n_rep):
    fig.text(0.01, 0.005, f"zone ombrée : ± 1 écart-type, {n_rep} répétitions", fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(out, f"{nom}.{ext}"), dpi=200)
    plt.close(fig)


def portee(prod, out):
    nb = 20
    par = defaultdict(lambda: defaultdict(lambda: [[0, 0] for _ in range(nb)]))
    rayon = {}
    for ch in glob.glob(os.path.join(prod, "portee_gain_v61", "noeuds_*.csv")):
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            if "gain=8" not in r["variante"] or int(r["newSent"]) <= 0:
                continue
            z = r["zone"]
            rt = float(r["radius"])
            rayon[z] = rt
            b = min(nb - 1, int(nb * float(r["distance_m"]) / rt))
            c = par[z][r["runNumber"]][b]
            c[0] += int(r["received"])
            c[1] += int(r["newSent"])
    lignes = []
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.5))
    axes = list(axes.flat)
    axes[-1].axis("off")
    n_rep = 0
    for ax, z in zip(axes, LIB):
        x = [(b + 0.5) * rayon[z] / nb / 1000 for b in range(nb)]
        series = []
        for run, bs in sorted(par[z].items(), key=lambda kv: int(kv[0])):
            s = [100 * c[0] / c[1] if c[1] else float("nan") for c in bs]
            series.append(s)
            lignes.append({"zone": z, "repetition": run, **{f"bande_{b + 1}_km_{x[b]:.3f}": round(s[b], 3) for b in range(nb)}})
        n_rep = len(series)
        bande(ax, x, series, COUL[z], "moyenne")
        ax.axhline(95, color="k", linewidth=0.8, linestyle=(0, (4, 3)))
        ax.set_title(LIB[z], loc="left", fontsize=10)
        ax.set_xlabel("distance à la passerelle (km)")
        ax.set_ylabel("mesures livrées (%)")
        ax.set_ylim(60, 101)
    ecrire(os.path.join(out, "repetitions_portee.csv"), lignes)
    sauver(fig, out, "fig_portee_v62", n_rep)


def robustesse(prod, out):
    par = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for ch in glob.glob(os.path.join(prod, "robustesse_v6", "noeuds_*.csv")) + glob.glob(os.path.join(prod, "robustesse_ext_v6", "noeuds_*.csv")):
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            n = int(r["newSent"])
            if n <= 0:
                continue
            e = float(re.search(r"espacement=([\d.]+)", r["variante"]).group(1))
            p = int(float(re.search(r"panne=([\d.]+)", r["variante"]).group(1)))
            c = par[(r["zone"], p, e)][r["runNumber"]]
            c[0] += int(r["received"]) / n >= 0.95
            c[1] += 1
    lignes = []
    fig, axes = plt.subplots(1, 5, figsize=(14, 3.6), sharey=True)
    n_rep = 0
    for ax, z in zip(axes, LIB):
        for p, sty, lab in ((0, "-", "centrale en service"), (1, "--", "centrale en panne")):
            xs = sorted({e for (zz, pp, e) in par if zz == z and pp == p})
            runs = sorted({r for e in xs for r in par[(z, p, e)]}, key=int)
            series = []
            for run in runs:
                s = [100 * par[(z, p, e)][run][0] / par[(z, p, e)][run][1] if par[(z, p, e)][run][1] else float("nan") for e in xs]
                series.append(s)
                lignes.append({"zone": z, "centrale": "panne" if p else "service", "repetition": run,
                               **{f"esp_{e}": round(v, 2) for e, v in zip(xs, s)}})
            n_rep = len(series)
            bande(ax, xs, series, COUL[z], lab, sty)
        ax.axhline(90, color="k", linewidth=0.8, linestyle=(0, (4, 3)))
        ax.set_title(LIB[z], loc="left", fontsize=10)
        ax.set_xlabel("espacement (rayons)")
    axes[0].set_ylabel("patients servis (%)")
    axes[0].legend(fontsize=8, frameon=False, loc="lower left")
    ecrire(os.path.join(out, "repetitions_robustesse.csv"), lignes)
    sauver(fig, out, "fig_robustesse_v62", n_rep)


def exigences(prod, out):
    par = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
    for ch in glob.glob(os.path.join(prod, "exigences_pavage_v61", "noeuds_*.csv")):
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            v = r["variante"]
            if "tout_confirme_rx2" not in v or "rx2dbm=27" not in v:
                continue
            e = float(re.search(r"espacement=([\d.]+)", v).group(1))
            c = par[(r["zone"], e)][r["runNumber"]]
            c[0] += int(r["alertsCounted"])
            c[1] += int(r["alertsOk5"])
            el, ok = int(r["readingsEligible"]), int(r["readingsOk72h"])
            c[2] += 1 if el and ok / el >= 0.95 else 0
            c[3] += 1 if el else 0
    lignes = []
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    n_rep = 0
    for z in LIB:
        xs = sorted({e for (zz, e) in par if zz == z})
        runs = sorted({r for e in xs for r in par[(z, e)]}, key=int)
        sa, sp = [], []
        for run in runs:
            a = [100 * par[(z, e)][run][1] / par[(z, e)][run][0] if par[(z, e)][run][0] else float("nan") for e in xs]
            p = [100 * par[(z, e)][run][2] / par[(z, e)][run][3] if par[(z, e)][run][3] else float("nan") for e in xs]
            sa.append(a)
            sp.append(p)
            lignes.append({"zone": z, "repetition": run, **{f"alertes_5min_esp_{e}": round(v, 2) for e, v in zip(xs, a)},
                           **{f"patients_72h_esp_{e}": round(v, 2) for e, v in zip(xs, p)}})
        n_rep = len(sa)
        bande(axes[0], xs, sa, COUL[z], LIB[z], "-o")
        bande(axes[1], xs, sp, COUL[z], LIB[z], "-o")
    for ax, t, s in ((axes[0], "Alertes livrées en 5 min (%)", 99), (axes[1], "Patients à 95 % de routine en 72 h (%)", 95)):
        ax.axhline(s, color="k", linewidth=0.8, linestyle=(0, (4, 3)))
        ax.set_title(t, loc="left", fontsize=10)
        ax.set_xlabel("espacement des passerelles (rayons)")
        ax.set_xticks([2, 3, 4])
    axes[0].legend(fontsize=8, frameon=False, loc="lower left")
    ecrire(os.path.join(out, "repetitions_exigences.csv"), lignes)
    sauver(fig, out, "fig_exigences_v62", n_rep)


def capacite(prod, out):
    acks = {}
    for d in ("capacite_v6", "capacite_recap_v6"):
        for ch in glob.glob(os.path.join(prod, d, "ack_*.csv")):
            for r in csv.DictReader(open(ch, encoding="utf-8")):
                if r["type"] == "alerte":
                    acks[(r["zone"], r["variante"], int(r["nDevices"]), r["runNumber"])] = float(r["p95Acquittees_s"])
    par = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for d in ("capacite_v6", "capacite_recap_v6"):
        for ch in glob.glob(os.path.join(prod, d, "noeuds_*.csv")):
            for r in csv.DictReader(open(ch, encoding="utf-8")):
                m = re.search(r"mode=([a-z_0-9]+)", r["variante"]).group(1)
                k = (r["zone"], m, r["variante"], int(r["nDevices"]))
                c = par[k][r["runNumber"]]
                el = int(r["readingsEligible"]) if r.get("readingsEligible") else 0
                c[0] += int(r["readingsOk72h"]) if el else 0
                c[1] += el
    lignes = []
    fig, axes = plt.subplots(2, 5, figsize=(15, 6), sharex=True)
    n_rep = 0
    for col, z in enumerate(LIB):
        for m, (lab, coul) in MODES.items():
            ks = sorted({k for k in par if k[0] == z and k[1] == m}, key=lambda k: k[3])
            if not ks:
                continue
            xs = [k[3] for k in ks]
            runs = sorted({r for k in ks for r in par[k]}, key=int)
            sl, sd = [], []
            for run in runs:
                l_ = [100 * par[k][run][0] / par[k][run][1] if par[k][run][1] else float("nan") for k in ks]
                d_ = [acks.get((z, k[2], k[3], run), float("nan")) for k in ks]
                d_ = [x if not math.isinf(x) and x >= 0 else float("nan") for x in d_]
                sl.append(l_)
                sd.append(d_)
                lignes.append({"zone": z, "mode": m, "repetition": run, **{f"livraison_72h_n{n}": round(v, 3) for n, v in zip(xs, l_)},
                               **{f"accuse_alerte_p95_s_n{n}": round(v, 2) if not math.isnan(v) else "" for n, v in zip(xs, d_)}})
            n_rep = max(n_rep, len(sl))
            bande(axes[0][col], xs, sl, coul, lab, "-o")
            if m != "tout_non_confirme":
                ok = [s for s in sd if not any(math.isnan(v) for v in s)]
                if ok:
                    bande(axes[1][col], xs, ok, coul, lab, "-o")
        axes[0][col].set_title(LIB[z], loc="left", fontsize=10)
        axes[0][col].axhline(95, color="k", linewidth=0.8, linestyle=(0, (4, 3)))
        axes[1][col].axhline(60, color="k", linewidth=0.8, linestyle=(0, (4, 3)))
        axes[1][col].set_yscale("log")
        axes[1][col].set_xscale("log")
        axes[1][col].set_xlabel("patients par passerelle")
    axes[0][0].set_ylabel("mesures livrées en 72 h (%)")
    axes[1][0].set_ylabel("délai d'accusé d'alerte, p95 (s)")
    axes[0][0].legend(fontsize=7, frameon=False, loc="lower left")
    ecrire(os.path.join(out, "repetitions_capacite.csv"), lignes)
    sauver(fig, out, "fig_capacite_v62", n_rep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for f in (portee, robustesse, exigences, capacite):
        f(a.prod, a.out)
        print("fait", f.__name__, flush=True)


if __name__ == "__main__":
    main()
