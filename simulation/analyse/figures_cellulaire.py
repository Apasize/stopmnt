#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
figures_cellulaire.py

Consignes v4, point 3 : graphes cellulaires.
  (a) portee_site_lora_4g : rayon fiable par site et par zone, 4G a la bande
      beninoise (cellulaire.bande_4g_benin_mhz, bilan de liaison) contre LoRa
      (bilan de liaison et simulation, methode probit) ;
  (b) energie_ponts : energie radio par jour et jours entre deux recharges des
      deux ponts, a la cadence cible. LoRa : energie simulee (capacite_cadence,
      10 repetitions) ; cellulaire : calcul a la main (couche cout,
      energie_cellulaire.csv), le module LTE de ns-3 ne modelisant que l'etat
      connecte.
Le cout contre la densite, cellulaire superpose au LoRa, est trace par
couche_cout.py (cout_par_patient.png).
"""
import argparse
import csv
import json
import math
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURFACE, ENCRE, ENCRE2, GRILLE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
LIB = {"urbain_dense": "Urbain dense", "peri_urbain": "Péri-urbain", "rural_degage": "Rural dégagé",
       "rural_arbore": "Rural arboré", "lacustre": "Lacustre"}


def style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(True, axis="y", color=GRILLE, linewidth=0.6)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.tick_params(colors=ENCRE2, labelsize=8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rayons", default="resultats/production/rayons_v5/rayon_fiable_probit.csv",
                    help="rayons fiables simules (probit), groupes 'zone | gain=G'")
    ap.add_argument("--repetitions", default="100")
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    bande = float(cfg["cellulaire"]["bande_4g_benin_mhz"])
    gain = float(cfg["passerelle"]["gain_antenne_dbi"])
    dens = cfg["zones"]["rural_arbore"]["vegetation"]["densite_centrale"]
    os.makedirs(a.out, exist_ok=True)

    # (a) portee par site
    bil = {}
    for r in csv.DictReader(open(os.path.join(a.prod, "cellulaire", "bilan_cellulaire.csv"), encoding="utf-8")):
        if r["convention"] == "avec gains":
            bil[(r["zone"], r["famille"])] = float(r["rayon_fiable_km"])
    sim = {}
    for r in csv.DictReader(open(a.rayons, encoding="utf-8")):
        sim[r["groupe"]] = int(r["rayon_fiable_m"]) / 1000
    lignes = []
    for z in LIB:
        g = f"{z} | vegetation={dens} gain={gain:g}" if z == "rural_arbore" else f"{z} | gain={gain:g}"
        lignes.append({"zone": z, "lora_simule_km": sim.get(g, sim.get(f"{z} | gain={gain:g}")), "lora_bilan_km": bil[(z, "LoRa privé (SF12)")],
                       "lte_bilan_km": bil[(z, f"4G PUSCH, {bande:g} MHz")]})
    with open(os.path.join(a.out, "portee_site_lora_4g.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)
    fig, ax = plt.subplots(figsize=(9, 4.2), facecolor=SURFACE)
    style(ax)
    x = range(len(lignes))
    larg = 0.26
    for k, (cle, lab, coul) in enumerate((("lora_simule_km", f"LoRa, simulé ({a.repetitions} répétitions, probit, borne basse IC 95 %)", "#2a78d6"),
                                          ("lora_bilan_km", "LoRa, bilan de liaison", "#9ec5f4"),
                                          ("lte_bilan_km", f"4G {bande:g} MHz, bilan de liaison (PUSCH)", "#eb6834"))):
        v = [l[cle] or 0 for l in lignes]
        bars = ax.bar([i + (k - 1) * larg for i in x], v, width=larg - 0.03, color=coul, label=lab)
        for b, val in zip(bars, v):
            ax.text(b.get_x() + b.get_width() / 2, val + 0.2, f"{val:.1f}".replace(".", ","), ha="center",
                    fontsize=7, color=ENCRE2)
    ax.set_xticks(list(x))
    ax.set_xticklabels([LIB[l["zone"]] for l in lignes], fontsize=9)
    ax.set_ylabel("rayon fiable par site (km)", fontsize=9, color=ENCRE2)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.text(0.01, 0.01, f"Même propagation et même ombrage par zone. Passerelle LoRa {gain:g} dBi ; eNodeB 17 dBi, "
             f"MCL PUSCH 140,7 dB (3GPP TR 36.888), propagation corrigée de 20 log10(f/868).",
             fontsize=7.5, color=ENCRE2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(a.out, f"portee_site_lora_4g.{ext}"), dpi=200, facecolor=SURFACE)
    plt.close(fig)

    # (b) energie des ponts
    cad = float(cfg["trafic"]["messages_par_jour_cible"])
    en = cfg["cout"]["energie_cellulaire"]
    bat_j = en["pile"]["capacite_mah"] / 1000 * 3600 * en["pile"]["tension_v"]
    barres = []
    for r in csv.DictReader(open(os.path.join(a.prod, "cout", "energie_cellulaire.csv"), encoding="utf-8")):
        if float(r["messages_par_jour"]) == cad:
            barres.append((f"cellulaire, {r['strategie']}", float(r["energie_j_par_jour_bas"]),
                           float(r["energie_j_par_jour_haut"]), "calcul (fiche Quectel EG915U + hypothèses)"))
    for mode, lab in (("tout_confirme_rx2", "LoRa, tout confirmé RX2"), ("mixte_rx2", "LoRa, mixte RX2"),
                      ("tout_non_confirme", "LoRa, sans accusé")):
        vals = []
        for r in csv.DictReader(open(os.path.join(a.prod, "capacite_cadence", "capacite_points_production.csv"),
                                     encoding="utf-8")):
            m = re.search(r"messages=([\d.]+)", r["variante"])
            if r["mode"] == mode and m and float(m.group(1)) == cad and int(r["nDevices"]) <= 200:
                vals.append(float(r["energie_j_jour"]))
        if vals:
            barres.append((lab, min(vals), max(vals), "simulé (ns-3, 10 répétitions, 50 à 200 patients)"))
    with open(os.path.join(a.out, "energie_ponts.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pont", "energie_j_jour_bas", "energie_j_jour_haut", "jours_entre_recharges_bas",
                    "jours_entre_recharges_haut", "statut"])
        for lab, lo, hi, st in barres:
            w.writerow([lab, round(lo, 3), round(hi, 3), round(bat_j / hi), round(bat_j / lo), st])
    fig, ax = plt.subplots(figsize=(9, 3.8), facecolor=SURFACE)
    style(ax)
    ax.grid(True, axis="x", color=GRILLE, linewidth=0.6)
    ax.grid(False, axis="y")
    for i, (lab, lo, hi, st) in enumerate(barres):
        coul = "#eb6834" if lab.startswith("cellulaire") else "#2a78d6"
        ax.barh(i, hi - lo if hi > lo else lo * 0.04, left=lo, height=0.5, color=coul)
        jmin, jmax = bat_j / hi, bat_j / lo
        txt = (f"{jmin:.0f} à {jmax:.0f} jours entre recharges" if jmax < 730
               else f"{jmin / 365:.0f} à {jmax / 365:.0f} ans (radio seule)")
        ax.text(hi * 1.15, i, txt, va="center", fontsize=8, color=ENCRE2)
    ax.set_yticks(range(len(barres)))
    ax.set_yticklabels([b[0] for b in barres], fontsize=8)
    ax.set_xscale("log")
    ax.set_xlim(0.3, 2e4)
    ax.set_xlabel("énergie radio par jour (J), échelle logarithmique", fontsize=8, color=ENCRE2)
    fig.text(0.01, 0.01, f"{cad:.0f} messages par jour, batterie Li-ion {en['pile']['capacite_mah']} mAh à "
             f"{en['pile']['tension_v']} V ({bat_j / 1000:.1f} kJ).\nRadio seule : microcontrôleur et BLE, communs aux deux "
             "ponts, non comptés ; les durées LoRa sont donc des plafonds.", fontsize=7.5, color=ENCRE2)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(a.out, f"energie_ponts.{ext}"), dpi=200, facecolor=SURFACE)
    plt.close(fig)
    for b in barres:
        print(b, round(bat_j / b[2]), round(bat_j / b[1]))
    for l in lignes:
        print(l)


if __name__ == "__main__":
    main()
