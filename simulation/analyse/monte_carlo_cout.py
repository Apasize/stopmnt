#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
monte_carlo_cout.py

Retour de l'auteur sur la v4 (2026-10-28, point 9) : en plus de la tornade,
tirage simultane de tous les parametres dans leurs plages (Monte-Carlo sur le
cout departemental). Grandeur : probabilite que le LoRa tout confirme RX2 reste
moins cher que le pont cellulaire avec offre machine, a appareil comparable.

Tirage : chaque parametre de tornade_cout.PARAMS uniforme sur [bas, haut]
(correlation entre sites tiree parmi les valeurs simulees 0,3 / 0,5 / 0,7) ;
toutes les autres plages du bloc cout au milieu ; marge de robustesse et
secours actives (decision de l'auteur). La structure du cout de passerelle
(scenario bas detaille ou Kerlink 10 %) est rapportee separement, puis
melangee a parts egales. Graine fixe.

Sorties : monte_carlo_cout.csv (un tirage par ligne), monte_carlo_resume.csv,
figure monte_carlo_cout.png/pdf.
"""
import argparse
import copy
import csv
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import tornade_cout as T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--fraction", type=float, default=0.02)
    ap.add_argument("--tirages", type=int, default=500)
    ap.add_argument("--graine", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--suffixe", default="")
    ap.add_argument("--scenario-rx2-14dbm", action="store_true")
    ap.add_argument("--espacement-alerte", action="store_true")
    ap.add_argument("--hybrides", action="store_true")
    ap.add_argument("--choix", action="store_true")
    ap.add_argument("--options-cout", nargs="*", default=[])
    ap.add_argument("--placement", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    T.RX2_14 = a.scenario_rx2_14dbm
    T.EXTRA = (["--espacement-alerte"] if a.espacement_alerte else []) + (["--placement", a.placement] if a.placement else [])
    if a.hybrides:
        T.LORA_ARCH = ("LoRa + secours cellulaire", "mixte à récapitulatif")
        T.CELL_ARCH = ("cellulaire + secours LoRa", "offre machine négociée")
    if a.choix:
        T.LORA_ARCH = ("choix par commune", "famille la moins chère")
        T.CELL_ARCH = ("cellulaire + secours LoRa", "offre machine négociée")
    T.EXTRA += ["--" + o for o in a.options_cout]
    cfg0 = json.load(open(a.config, encoding="utf-8"))
    cad = float(cfg0["trafic"]["messages_par_jour_cible"])
    prod = os.path.abspath(a.prod)
    rnd = random.Random(a.graine)
    centre = copy.deepcopy(cfg0)

    def milieux(d):
        for k, v in d.items():
            if isinstance(v, dict):
                milieux(v)
            elif (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)
                  and not isinstance(v[0], bool)):
                m = (float(v[0]) + float(v[1])) / 2
                d[k] = [m, m]
    milieux(centre["cout"])
    tirages = []
    for k in range(a.tirages):
        cf = copy.deepcopy(centre)
        val = {}
        for lab, ch, b, _ in T.PARAMS:
            lo, hi = T.bornes(cfg0, ch, b)
            v = rnd.choice([0.3, 0.5, 0.7]) if ch == "radio.correlation_ombrage_entre_sites" else rnd.uniform(lo, hi)
            val[lab] = v
            T.poser(cf, ch, [v, v] if isinstance(T.obtenir(cfg0, ch), list) else v)
        tirages.append((cf, val))

    def un(t):
        cf, val = t
        r_bas = T.evaluer(cf, prod, a.fraction, cad, "bas")
        r_haut = T.evaluer(cf, prod, a.fraction, cad, "haut")
        return val, r_bas, r_haut

    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        res = list(pool.map(un, tirages))
    os.makedirs(a.out, exist_ok=True)
    lignes = []
    for val, rb, rh in res:
        lignes.append({**{k: round(v, 4) for k, v in val.items()},
                       "lora_scenario_bas": rb["lora"], "cell_scenario_bas": rb["cell"], "ecart_scenario_bas": round(rb["ecart"], 1),
                       "lora_kerlink": rh["lora"], "cell_kerlink": rh["cell"], "ecart_kerlink": round(rh["ecart"], 1),
                       "communes_lora_scenario_bas": rb.get("statut", ""), "communes_lora_kerlink": rh.get("statut", "")})
    with open(os.path.join(a.out, f"monte_carlo_cout{a.suffixe}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)
    eb = sorted(l["ecart_scenario_bas"] for l in lignes)
    eh = sorted(l["ecart_kerlink"] for l in lignes)
    n = len(lignes)
    q = lambda v, p: v[min(len(v) - 1, int(p * len(v)))]
    resume = []
    for nom, e in (("scenario bas detaille", eb), ("Kerlink 10 %", eh), ("melange a parts egales", sorted(eb + eh))):
        p = sum(1 for x in e if x < 0) / len(e)
        se = (p * (1 - p) / len(e)) ** 0.5
        resume.append({"structure_cout_passerelle": nom, "tirages": len(e), "proba_lora_moins_cher": round(p, 4),
                       "ic95_binomial": round(1.96 * se, 4), "ecart_median_keur": q(e, 0.5),
                       "ecart_p5_keur": q(e, 0.05), "ecart_p95_keur": q(e, 0.95)})
    with open(os.path.join(a.out, f"monte_carlo_resume{a.suffixe}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(resume[0].keys()))
        w.writeheader()
        w.writerows(resume)
    for r in resume:
        print(r)
    fig, ax = plt.subplots(figsize=(9, 4), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    bins = 40
    ax.hist(eb, bins=bins, color="#2a78d6", alpha=0.75, label=f"passerelle, scénario bas détaillé : P(LoRa moins cher) = {resume[0]['proba_lora_moins_cher']:.0%}")
    ax.hist(eh, bins=bins, color="#eb6834", alpha=0.65, label=f"passerelle, Kerlink 10 % : P = {resume[1]['proba_lora_moins_cher']:.0%}")
    ax.axvline(0, color="#0b0b0b", linewidth=1.2)
    ax.set_xlabel("écart LoRa (tout confirmé RX2) - pont cellulaire (offre machine), k€ par an ; négatif : LoRa moins cher", fontsize=8)
    ax.set_ylabel("tirages", fontsize=8)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=8, frameon=False)
    fig.text(0.01, 0.01, f"{n} tirages simultanés de tous les paramètres dans leurs plages (uniformes), département, "
             f"{100 * a.fraction:g} % suivis, {cad:.0f} messages par jour.", fontsize=7.5, color="#52514e")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(a.out, f"monte_carlo_cout{a.suffixe}.{ext}"), dpi=200, facecolor="#fcfcfb")


if __name__ == "__main__":
    main()
