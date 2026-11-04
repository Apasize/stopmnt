#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
comparaison_homogene.py

Meme grille, memes populations, meme solveur pour toutes les references :
couverture complete et choix par commune, avec le rayon d'une passerelle seule et
avec le rayon du reseau pave. Remplace le total de 537, qui melangeait deux methodes.
Sortie : comparaison_homogene.csv, seuils_passerelle.csv.
"""
import copy, csv, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimisation_cout as O
import convention_v63 as V


class A:
    config = "config/config.json"
    raster = "donnees/worldpop/ben_pop_2021_CN_100m_R2024B_v1.tif"
    worldcover = "donnees/worldcover/ESA_WorldCover_10m_2021_v200_N06E000_Map.tif"
    villes = "donnees/arcep/cities.json"
    synthese = "resultats/production/multi_passerelles_v6_fusion/multi_passerelles_synthese_production.csv"


cfg = json.load(open(A.config, encoding="utf-8"))
out = "resultats/production/final/optimisation"
prod = os.path.abspath("resultats/production")
X, Y, W, COM, Ri, RiD, ZON = O.mailles(cfg, A)
pts = np.stack([X, Y], 1)
n0 = W * 2.0
fc = float(cfg["cout"]["fcfa_par_eur"])
F = 10e6 / fc


def couverture(args):
    """Couverture complete d'une commune : minimum de passerelles, sans terme de cout."""
    c, R_, lim = args
    import highspy
    from scipy.spatial import cKDTree
    k = COM == c
    p = pts[k]; r = R_[k]; m = len(p)
    t = cKDTree(p)
    h = highspy.Highs()
    h.setOptionValue("output_flag", False); h.setOptionValue("time_limit", float(lim)); h.setOptionValue("threads", 1)
    h.setOptionValue("mip_rel_gap", 0.0)
    lp = highspy.HighsLp()
    lp.num_col_ = m; lp.num_row_ = m
    lp.col_cost_ = np.ones(m); lp.col_lower_ = np.zeros(m); lp.col_upper_ = np.ones(m)
    lp.row_lower_ = np.ones(m); lp.row_upper_ = np.full(m, highspy.kHighsInf)
    st_, idx = [0], []
    for i in range(m):
        idx += t.query_ball_point(p[i], r[i]); st_.append(len(idx))
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.start_ = np.array(st_, dtype=np.int32); lp.a_matrix_.index_ = np.array(idx, dtype=np.int32); lp.a_matrix_.value_ = np.ones(len(idx))
    lp.integrality_ = [highspy.HighsVarType.kInteger] * m
    h.passModel(lp); h.run()
    x = np.array(h.getSolution().col_value); info = h.getInfo()
    return str(c), int((x > .5).sum()), round(float(info.mip_dual_bound), 1), h.modelStatusToString(h.getModelStatus())


from concurrent.futures import ProcessPoolExecutor
gw = {}
det = []
for nom, R_ in (("passerelle_seule", Ri), ("reseau_pave", RiD)):
    with ProcessPoolExecutor(4) as pool:
        r_ = list(pool.map(couverture, [(c, R_, 480) for c in sorted(set(COM))]))
    gw[nom] = {np.str_(a_): b_ for a_, b_, _, _ in r_}
    for a_, b_, c_, d_ in r_:
        det.append({"rayon": nom, "commune": a_, "passerelles": b_, "borne_inferieure": c_, "statut": d_})
    print(nom, sum(gw[nom].values()), r_, flush=True)
V.ecrire(os.path.join(out, "couverture_homogene.csv"), det)
lig, sl = [], []
for nom, niv, j in (("centre_detaille", "bas", None), ("centre_kerlink", "haut", None), ("bas", "bas", 0), ("haut", "haut", 1)):
    c2 = copy.deepcopy(cfg)
    if j is None:
        O.milieux(c2["cout"])
    comp = V.composantes(c2, prod, "placement_v62", float(cfg["trafic"]["messages_par_jour_cible"]), .02)[niv]
    cu, _ = O.couts(cfg, comp, j, .02)
    N = float(n0.sum())
    lns = next(iter(cu.values()))["lns"]
    for r, g_ in gw.items():
        tot, lora = F + lns, []
        for c in cu:
            k = COM == c
            L = (n0[k] * cu[c]["cL"]).sum() + g_[c] * cu[c]["g"]
            C = (n0[k] * cu[c]["cC"]).sum()
            tot += min(L, C)
            if L < C:
                lora.append(str(c))
        tl = sum((n0[COM == c] * cu[c]["cL"]).sum() + g_[c] * cu[c]["g"] for c in cu) + F + lns
        tc = sum((n0[COM == c] * cu[c]["cC"]).sum() for c in cu) + F + lns
        lig.append({"scenario": nom, "rayon": r, "passerelles_couverture": sum(g_.values()), "tout_lora": round(tl / N, 2), "tout_cellulaire": round(tc / N, 2), "choix_commune": round(tot / N, 2), "communes_lora": " ".join(lora)})
    K = comp["abomey_calavi"]
    c = cu["abomey_calavi"]
    sl.append({"scenario": nom, "kit_lora": round(K["kit_lora_eur_an"], 2), "kit_cellulaire": round(K["kit_cell_eur_an"], 2), "cout_patient_lora": round(c["cL"], 2), "cout_patient_cellulaire": round(c["cC"], 2), "cout_passerelle": round(c["g"], 1), "patients_pour_rembourser": round(c["g"] / max(c["cC"] - c["cL"], 1e-9), 1)})
    print(sl[-1], flush=True)
V.ecrire(os.path.join(out, "comparaison_homogene.csv"), lig)
V.ecrire(os.path.join(out, "seuils_passerelle.csv"), sl)
for l in lig:
    print(l)
