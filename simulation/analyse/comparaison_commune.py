#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
comparaison_commune.py

Compare, avec le meme rayon de couverture (passerelle seule), le choix maille par
maille et le choix commune par commune : couverture complete de chaque commune par
le LoRaWAN (meme solveur, cellulaire rendu tres cher), puis commune attribuee a la
famille la moins chere. Sortie : comparaison_commune.csv.
"""
import copy, csv, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimisation_cout as O
import convention_v63 as V


def main():
    class A: pass
    a = A()
    a.config = "config/config.json"; a.raster = "donnees/worldpop/ben_pop_2021_CN_100m_R2024B_v1.tif"
    a.worldcover = "donnees/worldcover/ESA_WorldCover_10m_2021_v200_N06E000_Map.tif"; a.villes = "donnees/arcep/cities.json"
    a.synthese = "resultats/production/multi_passerelles_v6_fusion/multi_passerelles_synthese_production.csv"
    out = "resultats/production/final/optimisation"
    cfg = json.load(open(a.config, encoding="utf-8"))
    prod = os.path.abspath("resultats/production")
    X, Y, W, COM, Ri, RiD, ZON = O.mailles(cfg, a)
    pts = np.stack([X, Y], 1)
    # Couverture complete : le cellulaire devient prohibitif.
    n0 = W * 2.0
    y, z, _, _, st = O.resoudre(pts, Ri, n0, np.zeros_like(n0), np.full_like(n0, 1e4), 1.0, 900, 1)
    gw = {c: int((COM[y] == c).sum()) for c in set(COM)}
    print("couverture complete", sum(gw.values()), st, gw, "mailles non couvertes", int((~z).sum()), flush=True)
    res = []
    fc = float(cfg["cout"]["fcfa_par_eur"])
    F = 10e6 / fc
    ref = {r["scenario"]: r for r in csv.DictReader(open(os.path.join(out, "optimisation_scenarios.csv"), encoding="utf-8"))}
    for nom, niv, j in (("centre_detaille", "bas", None), ("centre_kerlink", "haut", None), ("bas", "bas", 0), ("haut", "haut", 1)):
        c2 = copy.deepcopy(cfg)
        if j is None:
            O.milieux(c2["cout"])
        comp = V.composantes(c2, prod, "placement_v62", float(cfg["trafic"]["messages_par_jour_cible"]), .02)[niv]
        cu, _ = O.couts(cfg, comp, j, .02)
        N = float(n0.sum())
        lns = next(iter(cu.values()))["lns"]
        tot, lora = F + lns, []
        for c in cu:
            k = COM == c
            L = (n0[k] * cu[c]["cL"]).sum() + gw[c] * cu[c]["g"]
            C = (n0[k] * cu[c]["cC"]).sum()
            tot += min(L, C)
            if L < C:
                lora.append(c)
        tout_l = sum((n0[COM == c] * cu[c]["cL"]).sum() + gw[c] * cu[c]["g"] for c in cu) + F + lns
        r = ref[nom]
        res.append({"scenario": nom, "couverture_complete_passerelles": sum(gw.values()), "tout_lora_eur": round(tout_l / N, 2),
                    "tout_cellulaire_eur": r["tout_cellulaire_eur"], "choix_commune_eur": round(tot / N, 2),
                    "communes_lora": " ".join(lora), "choix_maille_eur": r["eur_patient_an"], "passerelles_maille": r["passerelles"],
                    "gain_maille_vs_commune_pct": round(100 * (tot / N - float(r["eur_patient_an"])) / (tot / N), 1)})
        print(res[-1], flush=True)
    V.ecrire(os.path.join(out, "comparaison_commune.csv"), res)


main()
