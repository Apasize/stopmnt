#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyse_robustesse.py

Consignes v4, point 1 (retour des encadrants) : marge de robustesse du reseau.
Pavage hexagonal a 7 passerelles ; patients places dans la cellule centrale ;
meme tirage avec la passerelle centrale en service (panne=0) et en panne
(panne=1, six voisines seules).

Par zone, espacement et etat :
  - part de patients servis = fraction des patients dont la livraison propre
    atteint le seuil de qualite (methode.seuil_acceptabilite_pdr) ; moyenne et
    IC 95 % (Student) sur les repetitions ;
  - livraison globale, moyenne et IC 95 %.
Espacement tenu en panne = plus grand facteur dont la borne basse IC 95 % de la
part servie reste >= qualite_service.part_servie_min_panne (0,90).
Marge sur le nombre de passerelles = (espacement nominal / espacement tenu en
panne)^2, la densite de passerelles variant en 1 / s^2. L'espacement nominal
est lu dans la synthese multi-passerelles (--synthese).

Sorties : robustesse_panne.csv (une ligne par zone, espacement, etat),
robustesse_marge.csv (une ligne par zone), figure robustesse_panne.png/pdf.
"""
import argparse
import csv
import json
import math
import os
import re
import statistics as st
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import t as student

LIB = {"urbain_dense": "Urbain dense", "peri_urbain": "Péri-urbain", "rural_degage": "Rural dégagé",
       "rural_arbore": "Rural arboré", "lacustre": "Lacustre"}
COUL = {"urbain_dense": "#2a78d6", "peri_urbain": "#eb6834", "rural_degage": "#1baf7a",
        "rural_arbore": "#eda100", "lacustre": "#e87ba4"}


def ic95(v):
    if len(v) < 2:
        return float("nan")
    return student.ppf(0.975, len(v) - 1) * st.stdev(v) / math.sqrt(len(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--noeuds", required=True, nargs="+")
    ap.add_argument("--synthese", required=True, help="multi_passerelles_synthese_production.csv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    seuil = float(cfg["methode"]["seuil_acceptabilite_pdr"])
    part_min = float(cfg["qualite_service"]["part_servie_min_panne"])

    # (zone, facteur, panne) -> run -> [servis, total, recus, emis]
    acc = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
    for r in (r for ch in a.noeuds for r in csv.DictReader(open(ch, encoding="utf-8"))):
        n = int(r["newSent"])
        if n <= 0:
            continue
        m = re.search(r"espacement=([\d.]+).*panne=([\d.]+)", r["variante"])
        k = (r["zone"], float(m.group(1)), int(float(m.group(2))))
        c = acc[k][r["runNumber"]]
        rec = int(r["received"])
        c[0] += rec / n >= seuil
        c[1] += 1
        c[2] += rec
        c[3] += n

    lignes = []
    for (z, f, p) in sorted(acc):
        runs = acc[(z, f, p)].values()
        part = [c[0] / c[1] for c in runs]
        livr = [c[2] / c[3] for c in runs]
        lignes.append({"zone": z, "espacement_facteur": f, "passerelle_centrale": "en panne" if p else "en service",
                       "repetitions": len(part), "part_servie": round(st.mean(part), 4),
                       "part_servie_ic95": round(ic95(part), 4), "livraison": round(st.mean(livr), 4),
                       "livraison_ic95": round(ic95(livr), 4)})

    nominal = {}
    for r in csv.DictReader(open(a.synthese, encoding="utf-8")):
        if abs(float(r["correlation_sites"]) - 0.5) < 1e-9:
            nominal[r["zone"]] = float(r["espacement_max_tenu_rayons_fiables"])
    marges = []
    for z in LIB:
        pts = sorted((l for l in lignes if l["zone"] == z and l["passerelle_centrale"] == "en panne"),
                     key=lambda l: l["espacement_facteur"])
        tenu = None
        for l in pts:
            if l["part_servie"] - l["part_servie_ic95"] >= part_min:
                tenu = l["espacement_facteur"]
            else:
                break
        # Croisement interpole de la borne basse avec le seuil, entre le
        # dernier point tenu et le premier qui echoue (indicatif).
        interp = tenu
        suiv = [l for l in pts if tenu is not None and l["espacement_facteur"] > tenu]
        if tenu is not None and suiv:
            l0 = next(l for l in pts if l["espacement_facteur"] == tenu)
            l1 = suiv[0]
            y0 = l0["part_servie"] - l0["part_servie_ic95"]
            y1 = l1["part_servie"] - l1["part_servie_ic95"]
            if y0 > y1:
                interp = tenu + (y0 - part_min) / (y0 - y1) * (l1["espacement_facteur"] - tenu)
        nom = nominal.get(z)
        marge = (nom / tenu) ** 2 if (nom and tenu) else float("nan")
        marges.append({"zone": z, "espacement_nominal": nom, "espacement_tenu_en_panne": tenu,
                       "espacement_tenu_en_panne_interpole": round(interp, 3) if interp else "",
                       "pas_de_grille_en_panne": round(min((b["espacement_facteur"] - a_["espacement_facteur"]
                                                            for a_, b in zip(pts, pts[1:])), default=0), 2),
                       "marge_passerelles": round(marge, 3) if not math.isnan(marge) else "",
                       "marge_retenue": round(max(1.0, marge), 3) if not math.isnan(marge) else "",
                       "critere": f"borne basse IC 95 % de la part de patients a livraison >= {seuil} doit rester >= {part_min}"})

    os.makedirs(a.out, exist_ok=True)
    for nom_f, rows in (("robustesse_panne.csv", lignes), ("robustesse_marge.csv", marges)):
        with open(os.path.join(a.out, nom_f), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    fig, axes = plt.subplots(1, 5, figsize=(15, 3.6), sharey=True, facecolor="#fcfcfb")
    for ax, z in zip(axes, LIB):
        ax.set_facecolor("#fcfcfb")
        for p, sty, lab in (("en service", "-", "centrale en service"), ("en panne", "--", "centrale en panne")):
            pts = sorted((l for l in lignes if l["zone"] == z and l["passerelle_centrale"] == p),
                         key=lambda l: l["espacement_facteur"])
            x = [l["espacement_facteur"] for l in pts]
            y = [100 * l["part_servie"] for l in pts]
            e = [100 * l["part_servie_ic95"] for l in pts]
            ax.fill_between(x, [a_ - b_ for a_, b_ in zip(y, e)], [min(100, a_ + b_) for a_, b_ in zip(y, e)],
                            color=COUL[z], alpha=0.18 if p == "en service" else 0.30, linewidth=0)
            ax.plot(x, y, sty, color=COUL[z], linewidth=2, marker="o", markersize=4, label=lab)
        ax.axhline(100 * part_min, color="#52514e", linewidth=1, linestyle=(0, (4, 3)))
        m = next(mm for mm in marges if mm["zone"] == z)
        if m["espacement_nominal"]:
            ax.axvline(m["espacement_nominal"], color="#0b0b0b", linewidth=1)
            ax.text(m["espacement_nominal"], 3, " nominal", fontsize=8)
        ax.set_title(LIB[z], fontsize=10, loc="left")
        ax.set_xlabel("espacement (x rayon de dimensionnement)", fontsize=8)
        ax.grid(True, color="#e4e3df", linewidth=0.6)
        for s_ in ("top", "right"):
            ax.spines[s_].set_visible(False)
        ax.tick_params(labelsize=8)
        ax.set_ylim(0, 101)
    axes[0].set_ylabel("patients servis (%)", fontsize=9)
    axes[0].legend(fontsize=8, frameon=False, loc="lower left")
    fig.text(0.01, 0.01, f"Pavage hexagonal à 7 passerelles, 200 patients dans la cellule centrale, corrélation entre sites 0,5. "
             f"Servi : livraison propre ≥ {100 * seuil:.0f} %. Tirets : seuil de {100 * part_min:.0f} % de patients servis.",
             fontsize=8, color="#52514e")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(a.out, f"robustesse_panne.{ext}"), dpi=200, facecolor="#fcfcfb")
    for m in marges:
        print(m)


if __name__ == "__main__":
    main()
