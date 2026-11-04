#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyse_sfw_longue.py

Retour de l'auteur sur la v4 (2026-10-28, point 6) : tampon de 72 h du
store-and-forward en charge (sortie de orchestrateur/run_sfw_longue.py).

Par zone, patients fixes, pause hors couverture et store-and-forward (0/1),
moyenne et IC 95 % sur les repetitions :
  - mobiles : part des mesures produites qui arrivent au serveur, mesures
    perdues par debordement du tampon, retard moyen et maximal d'une mesure ;
  - fixes : livraison des mesures (effet de la charge et des lots de vidage).
Sorties : sfw_longue.csv et figure sfw_longue.png/pdf.
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
from scipy.stats import t as student


def ic95(v):
    return student.ppf(0.975, len(v) - 1) * st.stdev(v) / math.sqrt(len(v)) if len(v) > 1 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brut", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    acc = defaultdict(lambda: defaultdict(list))
    for ch in glob.glob(os.path.join(a.brut, "brut_*.txt")):
        m = re.search(r"brut_(.+)_n(\d+)_pause([\d.]+)h_sfw(\d)_run(\d+)", os.path.basename(ch))
        cle = (m.group(1), int(m.group(2)), float(m.group(3)), int(m.group(4)))
        mg = md = mdrop = 0
        lat_max = []
        lat_moy = []
        fs = fr = 0
        for l in open(ch, encoding="utf-8"):
            if not l.startswith("NODE;"):
                continue
            c = l[5:].strip().split(";")
            if int(c[28]) == 1:
                mg += int(c[29])
                md += int(c[30])
                mdrop += int(c[31])
                if int(c[30]) > 0:
                    lat_moy.append(float(c[32]))
                    lat_max.append(float(c[33]))
            else:
                fs += int(c[29])
                fr += int(c[30])
        d = acc[cle]
        d["mobiles_livrees"].append(md / mg if mg else float("nan"))
        d["mobiles_perdues_tampon"].append(mdrop / mg if mg else float("nan"))
        d["retard_moyen_h"].append(st.mean(lat_moy) / 3600 if lat_moy else float("nan"))
        d["retard_max_h"].append(max(lat_max) / 3600 if lat_max else float("nan"))
        d["fixes_livrees"].append(fr / fs if fs else float("nan"))
    lignes = []
    for (z, n, p, s), d in sorted(acc.items()):
        l = {"zone": z, "patients_fixes": n, "pause_hors_couverture_h": p, "store_and_forward": s,
             "repetitions": len(d["mobiles_livrees"])}
        for k, v in d.items():
            v = [x for x in v if not math.isnan(x)]
            l[k] = round(st.mean(v), 4) if v else ""
            l[k + "_ic95"] = round(ic95(v), 4) if len(v) > 1 else ""
        lignes.append(l)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "sfw_longue.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)
    for l in lignes:
        print({k: l[k] for k in ("zone", "patients_fixes", "pause_hors_couverture_h", "store_and_forward", "repetitions",
                                  "mobiles_livrees", "mobiles_perdues_tampon", "retard_max_h", "fixes_livrees")})

    groupes = sorted({(l["zone"], l["patients_fixes"]) for l in lignes})
    fig, ax = plt.subplots(figsize=(10, 4), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    larg = 0.2
    lib = {"urbain_dense": "urbain", "rural_degage": "rural"}
    for j, (p, s, coul, lab) in enumerate(((48.0, 0, "#9ec5f4", "48 h, sans S&F"), (48.0, 1, "#2a78d6", "48 h, avec S&F"),
                                            (96.0, 0, "#f6b896", "96 h, sans S&F"), (96.0, 1, "#eb6834", "96 h, avec S&F"))):
        for i, g in enumerate(groupes):
            l = next((x for x in lignes if (x["zone"], x["patients_fixes"]) == g
                      and x["pause_hors_couverture_h"] == p and x["store_and_forward"] == s), None)
            if not l or l["mobiles_livrees"] == "":
                continue
            ax.bar(i + (j - 1.5) * larg, 100 * l["mobiles_livrees"], width=larg - 0.02, color=coul,
                   yerr=100 * (l["mobiles_livrees_ic95"] or 0), ecolor="#52514e", capsize=2,
                   label=lab if i == 0 else None)
    ax.set_xticks(range(len(groupes)))
    ax.set_xticklabels([f"{lib.get(z, z)}, {n} patients fixes" for z, n in groupes], fontsize=9)
    ax.set_ylabel("mesures des patients mobiles livrées (%)", fontsize=8)
    ax.set_ylim(0, 105)
    ax.grid(True, axis="y", color="#e4e3df", linewidth=0.6)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.legend(fontsize=8, frameon=False, ncol=4, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    fig.text(0.01, 0.01, "10 patients mobiles qui sortent de la couverture (au-delà de l'horizon) pendant la pause indiquée, "
             "sur fond de patients fixes\nà 10 messages par jour, mode mixte RX2, 10 jours simulés, 5 répétitions. Tampon : 72 h. S&F : store-and-forward.",
             fontsize=7.5, color="#52514e")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(a.out, f"sfw_longue.{ext}"), dpi=200, facecolor="#fcfcfb")


if __name__ == "__main__":
    main()
