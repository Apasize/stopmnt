#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
optimisation_cout.py

Localisation de passerelles au moindre cout, sur tout le departement. Chaque
maille habitee choisit entre LoRaWAN et cellulaire ; une passerelle n'est
ouverte que si les patients qu'elle sert remboursent son cout.

  min  somme_j g y_j + somme_i n_i (c_L,i z_i + c_C,i (1 - z_i))
  s.c. z_i <= somme_{j couvrant i} y_j,   y_j binaire,   0 <= z_i <= 1

  n_i   : patients de la maille i servis par un pont (hors smartphones) ;
  g     : cout annuel d'une passerelle, connexion comprise ;
  c_L,i : cout annuel d'un patient en LoRaWAN, secours cellulaire compris ;
  c_C,i : cout annuel d'un patient en cellulaire, secours LoRaWAN compris.

Couverture : rayon de dimensionnement d'une passerelle seule, zone par zone.
Capacite : une passerelle chargee au-dela de sa capacite est doublee sur place. Population : WorldPop, recalee sur
le recensement de 2013 commune par commune. So-Ava : version non contrainte.

Sorties dans --out : optimisation_scenarios.csv, optimisation_communes.csv,
sites_<scenario>.csv, mailles_<scenario>.csv.
"""
import argparse
import copy
import csv
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import highspy
import numpy as np
import rasterio
from scipy.spatial import cKDTree
from shapely.geometry import shape

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
sys.path.insert(0, os.path.join(ICI, "..", "orchestrateur"))
import convention_v63 as V  # noqa: E402
import placement_plne_v62 as P  # noqa: E402
import run_experiences as R  # noqa: E402


def mailles(cfg, a):
    """Mailles du departement : position (m), patients pour 1 % suivi, commune, zone."""
    C = cfg["cout"]
    op = C["optimisation"]
    g = float(op["maille_m"])
    pc = C["placement_plne"]
    ids = cfg["cellulaire"]["atlas_arcep"]["identifiants"]
    villes = {c["id"]: c for c in json.load(open(a.villes, encoding="utf-8"))["data"]}
    rast = rasterio.open(a.raster)
    rast2 = rasterio.open(op["raster_so_ava"])
    wc = rasterio.open(a.worldcover)
    rho = float(cfg["radio"]["correlation_ombrage_entre_sites"])
    esp = {r["zone"]: float(r["espacement_max_tenu_rayons_fiables"])
           for r in csv.DictReader(open(a.synthese, encoding="utf-8"))
           if abs(float(r["correlation_sites"]) - rho) < 1e-9 and r["espacement_max_tenu_rayons_fiables"]}
    seuil = float(pc.get("seuil_maille_arboree", 0.5))
    lat0, lon0 = 6.6, 2.25
    X, Y, W, COM, Ri, RiD, ZON = [], [], [], [], [], [], []
    for nom, (cle, id_) in ids.items():
        if cle != "city":
            continue
        cm = C["communes"][nom]
        base = cm["zone"]
        geom = shape(villes[id_]["area_feature"])
        lon, lat, pop = P.pixels(rast2 if nom == "so_ava" else rast, geom)
        tf, _ = P.parts_arborees(wc, geom, lon, lat, rast.res[0] / 2)
        x = (lon - lon0) * 111320.0 * math.cos(math.radians(lat0))
        y = (lat - lat0) * 110574.0
        _, inv = np.unique(np.stack([np.floor(x / g), np.floor(y / g)], 1).astype(int), axis=0, return_inverse=True)
        inv = inv.ravel()
        w = np.bincount(inv, weights=pop)
        cx, cy = np.bincount(inv, weights=pop * x) / w, np.bincount(inv, weights=pop * y) / w
        ctf = np.bincount(inv, weights=tf) / np.bincount(inv)
        b = "lacustre" if base == "lacustre" else ("rural_degage" if base == "rural_arbore" else base)
        zi = np.where(ctf > seuil, "rural_arbore", b)
        rd = {z: R.rayon_dimensionnement(cfg, cfg["zones"][z]) for z in set(zi)}
        RiD.append(np.array([esp[z] * rd[z] / math.sqrt(3) for z in zi]))
        Ri.append(np.array([float(op["facteur_rayon"]) * rd[z] for z in zi]))
        ZON += list(zi)
        X.append(cx); Y.append(cy)
        W.append(w / w.sum() * cm["population_2013"] * 0.01)
        COM += [nom] * len(w)
    return np.concatenate(X), np.concatenate(Y), np.concatenate(W), np.array(COM), np.concatenate(Ri), np.concatenate(RiD), np.array(ZON)


def milieux(d):
    for k, v in d.items():
        if isinstance(v, dict):
            milieux(v)
        elif isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v) and not isinstance(v[0], bool):
            m = (float(v[0]) + float(v[1])) / 2
            d[k] = [m, m]


def couts(cfg, comp, j, fr, fl=None, fpub=None, mult_g=1.0, s=0.0):
    """Couts unitaires par commune pour un jeu de parametres (j : 0 bas, 1 haut, None milieu)."""
    C = cfg["cout"]
    CV, rp = C["convention"], C["remontee_passerelle"]
    fc = float(C["fcfa_par_eur"])
    pick = lambda v: float(v[j]) if j is not None else (float(v[0]) + float(v[1])) / 2
    pb = pick(CV["fcfa_par_go"]) * (1 + pick(CV["marge_operateur"])) / 1024 ** 3 / fc
    f = fl if fl is not None else pick(CV["f_ligne_fcfa_par_mois"])
    r = pick(CV["receptions_par_trame"])
    ligne12 = 12 * f / fc
    out = {}
    for c, K in comp.items():
        kerl = K["niveau"] == "haut"
        vp = K["octets_patient_mois_mqtt"] * 12
        vt = (K["trames_passerelle_par_patient_jour"] * rp["octets_par_trame"] * r
              + K["accuses_par_patient_jour"] * rp["octets_par_accuse"]) * 365
        vm = rp["octets_maintien_par_jour"] * 365
        ph = K["part_ombre_lora"]; u = K["part_sans_couverture"]
        lp = vp * pb + ligne12
        g = (K["passerelle_hors_remontee_eur_an"] + (0 if kerl else vm * pb + ligne12)) * mult_g
        n = K["patients"] * (1 - s)
        cL = (1 - ph) * (K["kit_lora_eur_an"] + (0 if kerl else vt * pb)) + ph * (K["kit_cell_eur_an"] + lp)
        sec = K["passerelles_secours_cell"] * g / max(n, 1e-9)
        cC = (1 - u) * (K["kit_cell_eur_an"] + lp) + u * K["kit_lora_eur_an"] + sec
        out[c] = dict(g=g, cL=cL, cC=cC, n=n, lns=K["lns_departement_eur_an"],
                      passerelles=K["passerelles"])
    A = float(C["amortissement_ans"])
    KP = C["kit_patient"]
    tel = pick(KP["montre_ble_eur"]) * (1 / A + pick(KP["remplacement_annuel"])) + next(iter(comp.values()))["octets_patient_mois_mqtt"] * 12 * pb
    return out, tel


def resoudre(pts, Ri, n, c_L, c_C, g, lim, fils, gap=0.001, k=1):
    """k : nombre de passerelles ouvertes exigees a portee d'une maille servie en LoRaWAN (1 : couverture simple ; 2 : double couverture, tolerante a la panne d'une passerelle)."""
    m = len(n)
    arbre = cKDTree(pts)
    vois = [arbre.query_ball_point(pts[i], Ri[i]) for i in range(m)]
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", float(lim))
    h.setOptionValue("threads", int(fils))
    h.setOptionValue("mip_rel_gap", float(gap))
    lp = highspy.HighsLp()
    lp.num_col_ = 2 * m
    lp.num_row_ = m
    constante = float((n * c_C).sum())
    lp.col_cost_ = np.concatenate([np.full(m, g), n * (c_L - c_C)])
    lp.col_lower_ = np.zeros(2 * m)
    lp.col_upper_ = np.ones(2 * m)
    lp.row_lower_ = np.full(m, -highspy.kHighsInf)
    lp.row_upper_ = np.zeros(m)
    starts, idx, val = [0], [], []
    for i in range(m):
        for j in vois[i]:
            idx.append(j); val.append(-1.0)
        idx.append(m + i); val.append(float(k))
        starts.append(len(idx))
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.start_ = np.array(starts, dtype=np.int32)
    lp.a_matrix_.index_ = np.array(idx, dtype=np.int32)
    lp.a_matrix_.value_ = np.array(val)
    lp.integrality_ = [highspy.HighsVarType.kInteger] * m + [highspy.HighsVarType.kContinuous] * m
    h.passModel(lp)
    h.run()
    info = h.getInfo()
    x = np.array(h.getSolution().col_value)
    return x[:m] > 0.5, x[m:] > 0.5, constante + info.objective_function_value, constante + info.mip_dual_bound, h.modelStatusToString(h.getModelStatus())


def un(t):
    sc, a, cfg0, prod = t
    X, Y, W, COM, Ri, RiD, ZON = mailles(cfg0, a)
    if sc.get("diversite"):
        Ri = RiD
    cfg = copy.deepcopy(cfg0)
    C = cfg["cout"]
    j = sc.get("j")
    if j is None:
        milieux(cfg["cout"])
    niv = sc["structure"]
    comp = V.composantes(cfg, prod, a.placement, float(cfg["trafic"]["messages_par_jour_cible"]), sc["fraction"])[niv]
    cu, tel = couts(cfg0, comp, j, sc["fraction"], sc.get("fl"), None, sc.get("mult_g", 1.0), sc.get("s", 0.0))
    fc = float(C["fcfa_par_eur"])
    F = 10e6 / fc
    gv = next(iter(cu.values()))["g"]
    n = W * sc["fraction"] * 100 * (1 - sc.get("s", 0.0))
    cL = np.array([cu[c]["cL"] for c in COM]); cC = np.array([cu[c]["cC"] for c in COM])
    pts = np.stack([X, Y], 1)
    y, z, obj, borne, statut = resoudre(pts, Ri, n, cL, cC, gv, a.limite, a.fils, a.gap, a.couverture)
    Ntot = float(W.sum() * sc["fraction"] * 100)
    lns = next(iter(cu.values()))["lns"]
    nb_ph = Ntot * sc.get("s", 0.0)
    # Charge par passerelle (mode a recapitulatif).
    charges = np.bincount(cKDTree(pts[y]).query(pts[z])[1], weights=n[z], minlength=int(y.sum())) if y.any() and z.any() else np.array([0.0])
    cap = C["optimisation"]["capacite_recap_par_zone"]
    caps = np.array([float(cap[q]) for q in ZON[y]]) if y.any() else np.array([1.0])
    sup = int(np.maximum(0, np.ceil(charges / caps) - 1).sum()) if y.any() else 0
    obj = obj + sup * gv
    total = obj + F + lns + nb_ph * tel
    tout_cell = (n * cC).sum() + F + lns + nb_ph * tel
    ref = sum(cu[c]["passerelles"] for c in cu) * gv + (n * cL).sum() + F + lns + nb_ph * tel
    ch_com = sum(min((n[COM == c] * cL[COM == c]).sum() + cu[c]["passerelles"] * gv, (n[COM == c] * cC[COM == c]).sum()) for c in cu) + F + lns + nb_ph * tel
    ligne = {"scenario": sc["nom"], "structure": "Kerlink" if niv == "haut" else "detaillee", "fraction": sc["fraction"],
             "part_smartphone": sc.get("s", 0.0), "f_ligne": sc.get("fl", ""), "mult_passerelle": sc.get("mult_g", 1.0),
             "patients": round(Ntot), "cout_passerelle_eur_an": round(gv, 1),
             "cout_keur_an": round(total / 1000, 1), "eur_patient_an": round(total / Ntot, 2),
             "borne_inf_eur_patient_an": round((borne + F + lns + nb_ph * tel) / Ntot, 2),
             "passerelles": int(y.sum()) + sup, "doublees_capacite": sup, "part_patients_lora": round(float(n[z].sum() / n.sum()), 3),
             "charge_max_passerelle": round(float(charges.max())), "statut": statut,
             "tout_cellulaire_eur": round(tout_cell / Ntot, 2), "couverture_complete_lora_eur": round(ref / Ntot, 2),
             "choix_commune_eur": round(ch_com / Ntot, 2)}
    com = []
    sites_com = COM[y]
    for c in cu:
        mk = COM == c
        com.append({"scenario": sc["nom"], "commune": c, "patients_ponts": round(float(n[mk].sum())),
                    "part_lora": round(float(n[mk & z].sum() / max(n[mk].sum(), 1e-9)), 3),
                    "passerelles": int((sites_com == c).sum()), "reference_couverture": int(cu[c]["passerelles"])})
    os.makedirs(a.out, exist_ok=True)
    np.savetxt(os.path.join(a.out, f"mailles_{sc['nom']}.csv"), np.column_stack([X, Y, n, z.astype(int), y.astype(int)]),
               delimiter=",", fmt=["%.0f", "%.0f", "%.3f", "%d", "%d"], header="x_m,y_m,patients,lora,site", comments="")
    return ligne, com


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--placement", default="placement_v62")
    ap.add_argument("--raster", default="donnees/worldpop/ben_pop_2021_CN_100m_R2024B_v1.tif")
    ap.add_argument("--worldcover", default="donnees/worldcover/ESA_WorldCover_10m_2021_v200_N06E000_Map.tif")
    ap.add_argument("--villes", default="donnees/arcep/cities.json")
    ap.add_argument("--synthese", default="resultats/production/multi_passerelles_v6_fusion/multi_passerelles_synthese_production.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--limite", type=float, default=None)
    ap.add_argument("--seul", default=None)
    ap.add_argument("--gap", type=float, default=0.001)
    ap.add_argument("--fils", type=int, default=None)
    ap.add_argument("--couverture", type=int, default=None, help="passerelles exigees a portee d'une maille LoRaWAN (defaut : cout.optimisation.couverture_minimale)")
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    op = cfg["cout"]["optimisation"]
    a.limite = a.limite or op["limite_resolution_s"]
    a.fils = a.fils or op["fils"]
    a.couverture = a.couverture or int(op.get("couverture_minimale", 1))
    prod = os.path.abspath(a.prod)
    s1 = op["part_smartphone"][1]
    S = [dict(nom="centre_detaille", structure="bas", j=None, fraction=.02),
         dict(nom="centre_kerlink", structure="haut", j=None, fraction=.02),
         dict(nom="bas", structure="bas", j=0, fraction=.02),
         dict(nom="haut", structure="haut", j=1, fraction=.02),
         dict(nom="smartphone_detaille", structure="bas", j=None, fraction=.02, s=s1),
         dict(nom="smartphone_kerlink", structure="haut", j=None, fraction=.02, s=s1),
         dict(nom="fligne66_detaille", structure="bas", j=None, fraction=.02, fl=66.0),
         dict(nom="fligne800_detaille", structure="bas", j=None, fraction=.02, fl=800.0),
         dict(nom="passerelle_x05", structure="bas", j=None, fraction=.02, mult_g=.5),
         dict(nom="passerelle_x2", structure="bas", j=None, fraction=.02, mult_g=2.0),
         dict(nom="suivi_0_5pc", structure="bas", j=None, fraction=.005),
         dict(nom="suivi_5pc", structure="bas", j=None, fraction=.05),
         dict(nom="rayon_diversite", structure="bas", j=None, fraction=.02, diversite=True)]
    if a.seul:
        S = [s for s in S if s["nom"] in a.seul.split(",")]
    with ProcessPoolExecutor(max_workers=a.jobs) as pool:
        res = list(pool.map(un, [(s, a, cfg, prod) for s in S]))
    V.ecrire(os.path.join(a.out, "optimisation_scenarios.csv" if not a.seul else "optimum_scenarios.csv"), [r[0] for r in res])
    V.ecrire(os.path.join(a.out, "optimisation_communes.csv" if not a.seul else "optimum_communes.csv"), [x for r in res for x in r[1]])
    for r in res:
        print(r[0], flush=True)


if __name__ == "__main__":
    main()
