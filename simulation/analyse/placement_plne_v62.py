#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
placement_plne_v62.py

Complement v6.2, points 2 et 3 : placement des passerelles sur les zones
habitees, chaque maille dans sa propre zone de propagation, avec le pavage
comme solution de depart.

Donnees :
  - WorldPop 2021, 100 m, version contrainte (population, mailles habitees) ;
  - ESA WorldCover 10 m 2021 v200 (classe 10 = couvert arbore), tuile N06E000 ;
  - contours des communes de l'atlas ARCEP.

Pour chaque commune :
  1. pixels habites (WorldPop) ; part arboree de chaque pixel = part des
     pixels WorldCover de classe 10 dans le carre de 100 m ;
  2. part arboree de la commune : sur la surface habitee et sur toute la surface ;
  3. mailles de g metres ; une maille est 'arboree' si sa part arboree
     (moyenne de ses pixels habites) depasse le seuil du config, sinon elle est
     dans la zone de base de la commune (rural degage pour les communes classees
     arborees) ;
  4. couverture : un site j couvre la maille i si d_ij <= R_i, avec
     R_i = espacement(zone i) x rayon de dimensionnement(zone i) / racine(3) :
     meme critere que le pavage, diversite comprise ;
  5. solution de depart : pavage hexagonal a l'espacement de la zone de base,
     chaque noeud du pavage ramene a la maille habitee la plus proche, puis
     mailles non couvertes reparees par glouton ; le solveur (HiGHS via
     highspy, solution de depart fournie) ne peut donc pas faire pire ;
  6. PLNE : min somme y, couverture de chaque maille, plancher (2 par commune,
     patients / capacite) ; limite de temps du config ; ecart a l'optimum publie ;
  7. capacite : passerelle surchargee doublee sur place.
Pavage de reference (comme la v6) : superficie x densite, en melange des zones
au prorata de la surface habitee arboree / non arboree.

Sorties : placement_v62_<commune>.csv, sites_v62_<commune>_<critere>.csv,
couvert_arbore_<commune>.csv.
"""
import argparse
import csv
import json
import math
import os
import sys
import time

import highspy
import numpy as np
import rasterio
import rasterio.mask
from scipy.spatial import cKDTree
from shapely.geometry import shape

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "orchestrateur"))
import run_experiences as R  # noqa: E402


def pixels(raster, geom):
    img, tr = rasterio.mask.mask(raster, [geom], crop=True, nodata=raster.nodata, filled=True)
    a = img[0]
    rows, cols = np.where(a > 0)
    xs, ys = rasterio.transform.xy(tr, rows, cols)
    return np.array(xs), np.array(ys), a[rows, cols].astype(float)


def parts_arborees(wc, geom, lon, lat, half_deg):
    """Part de classe 10 dans le carre de cote 2 x half_deg autour de chaque point,
    et part arboree sur toute la commune."""
    img, tr = rasterio.mask.mask(wc, [geom], crop=True, nodata=0, filled=True)
    a = img[0]
    arbre = (a == 10).astype(np.float32)
    valide = (a > 0).astype(np.float32)
    part_commune = float(arbre.sum() / max(1.0, valide.sum()))
    # Somme cumulee 2D pour des moyennes de carres rapides.
    cs = np.pad(arbre.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    cv = np.pad(valide.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    inv = ~tr
    c0, r0 = inv * (lon - half_deg, lat + half_deg)
    c1, r1 = inv * (lon + half_deg, lat - half_deg)
    r0 = np.clip(np.floor(r0).astype(int), 0, a.shape[0])
    r1 = np.clip(np.ceil(r1).astype(int), 0, a.shape[0])
    c0 = np.clip(np.floor(c0).astype(int), 0, a.shape[1])
    c1 = np.clip(np.ceil(c1).astype(int), 0, a.shape[1])
    s = cs[r1, c1] - cs[r0, c1] - cs[r1, c0] + cs[r0, c0]
    v = cv[r1, c1] - cv[r0, c1] - cv[r1, c0] + cv[r0, c0]
    return np.where(v > 0, s / np.maximum(v, 1), 0.0), part_commune


def resoudre(A_cols, n, plancher, depart, limite_s):
    """PLNE de couverture par HiGHS, solution de depart fournie."""
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", float(limite_s))
    h.setOptionValue("mip_rel_gap", 0.0)
    h.setOptionValue("threads", 1)
    lp = highspy.HighsLp()
    lp.num_col_ = n
    lp.num_row_ = n + 1
    lp.col_cost_ = np.ones(n)
    lp.col_lower_ = np.zeros(n)
    lp.col_upper_ = np.ones(n)
    lp.row_lower_ = np.concatenate([np.ones(n), [float(plancher)]])
    lp.row_upper_ = np.full(n + 1, highspy.kHighsInf)
    starts, idx = [0], []
    for j in range(n):
        rows = list(A_cols[j]) + [n]
        idx.extend(rows)
        starts.append(len(idx))
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_ = np.array(starts, dtype=np.int32)
    lp.a_matrix_.index_ = np.array(idx, dtype=np.int32)
    lp.a_matrix_.value_ = np.ones(len(idx))
    lp.integrality_ = [highspy.HighsVarType.kInteger] * n
    h.passModel(lp)
    sol = highspy.HighsSolution()
    x0 = np.zeros(n)
    x0[list(depart)] = 1.0
    sol.col_value = list(x0)
    h.setSolution(sol)
    t0 = time.time()
    h.run()
    dt = time.time() - t0
    info = h.getInfo()
    x = np.array(h.getSolution().col_value)
    ouverts = np.where(x > 0.5)[0]
    if len(ouverts) == 0 or len(ouverts) > len(depart):
        ouverts = np.array(sorted(depart))
    borne = info.mip_dual_bound
    return ouverts, borne, dt, h.modelStatusToString(h.getModelStatus())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--raster", default="donnees/worldpop/ben_pop_2021_CN_100m_R2024B_v1.tif")
    ap.add_argument("--worldcover", default="donnees/worldcover/ESA_WorldCover_10m_2021_v200_N06E000_Map.tif")
    ap.add_argument("--villes", default="donnees/arcep/cities.json")
    ap.add_argument("--synthese", default="resultats/production/multi_passerelles_v6_fusion/multi_passerelles_synthese_production.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--communes", nargs="*", default=None)
    ap.add_argument("--criteres", nargs="*", default=["routine", "alerte"])
    ap.add_argument("--fraction", type=float, default=0.02)
    ap.add_argument("--limite-s", type=float, default=None)
    a = ap.parse_args()
    cfg = R.charger_config(a.config)
    pc = cfg["cout"]["placement_plne"]
    lim = a.limite_s or float(pc.get("limite_resolution_s", 1800))
    g = float(pc.get("maille_m_v62", 250))
    seuil_arbre = float(pc.get("seuil_maille_arboree", 0.5))
    ids = cfg["cellulaire"]["atlas_arcep"]["identifiants"]
    villes = {c["id"]: c for c in json.load(open(a.villes, encoding="utf-8"))["data"]}
    rho = float(cfg["radio"]["correlation_ombrage_entre_sites"])
    esp = {"routine": {r["zone"]: float(r["espacement_max_tenu_rayons_fiables"])
                       for r in csv.DictReader(open(a.synthese, encoding="utf-8"))
                       if abs(float(r["correlation_sites"]) - rho) < 1e-9 and r["espacement_max_tenu_rayons_fiables"]},
           "alerte": {k: float(v) for k, v in cfg["cout"]["espacement_exigence_alerte"].items() if not k.startswith("_")}}
    caps = pc.get("capacite_par_zone", {})
    n_min = int(cfg["cout"].get("passerelles_min_par_commune", 1))
    rast = rasterio.open(a.raster)
    wc = rasterio.open(a.worldcover)
    os.makedirs(a.out, exist_ok=True)
    for nom, (cle, id_) in ids.items():
        if cle != "city" or (a.communes and nom not in a.communes):
            continue
        cm = cfg["cout"]["communes"][nom]
        base = cm["zone"]
        base_non_arbore = "rural_degage" if base == "rural_arbore" else base
        geom = shape(villes[id_]["area_feature"])
        lon, lat, pop = pixels(rast, geom)
        tf, part_commune = parts_arborees(wc, geom, lon, lat, rast.res[0] / 2)
        part_hab = float(tf.mean())
        lat0, lon0 = float(np.mean(lat)), float(np.mean(lon))
        x = (lon - lon0) * 111320.0 * math.cos(math.radians(lat0))
        y = (lat - lat0) * 110574.0
        patients = cm["population_2013"] * a.fraction
        ix = np.floor(x / g).astype(int)
        iy = np.floor(y / g).astype(int)
        _, inv = np.unique(np.stack([ix, iy], 1), axis=0, return_inverse=True)
        inv = inv.ravel()
        w = np.bincount(inv, weights=pop)
        cx = np.bincount(inv, weights=pop * x) / w
        cy = np.bincount(inv, weights=pop * y) / w
        cnt = np.bincount(inv)
        ctf = np.bincount(inv, weights=tf) / cnt
        n = len(w)
        zone_i = np.where(ctf > seuil_arbre, "rural_arbore", base_non_arbore)
        if base == "lacustre":
            zone_i = np.where(ctf > seuil_arbre, "rural_arbore", "lacustre")
        pts = np.stack([cx, cy], 1)
        part_maille_arboree = float(np.mean(zone_i == "rural_arbore"))
        with open(os.path.join(a.out, f"couvert_arbore_{nom}.csv"), "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["commune", "zone_config", "part_arboree_surface_totale", "part_arboree_surface_habitee",
                         "part_mailles_arborees", "mailles", "maille_m"])
            wr.writerow([nom, base, round(part_commune, 3), round(part_hab, 3), round(part_maille_arboree, 3), n, g])
        lignes = []
        for crit in a.criteres:
            rdim = {z: R.rayon_dimensionnement(cfg, cfg["zones"][z]) for z in set(zone_i)}
            Ri = np.array([esp[crit][z] * rdim[z] / math.sqrt(3) for z in zone_i])
            arbre = cKDTree(pts)
            # A_cols[j] : mailles couvertes par le site j (d_ij <= R_i).
            voisins_i = [arbre.query_ball_point(pts[i], Ri[i]) for i in range(n)]
            A_cols = [[] for _ in range(n)]
            for i, vs in enumerate(voisins_i):
                for j in vs:
                    A_cols[j].append(i)
            cap = min(float(caps[z]) for z in set(zone_i) if z in caps) if caps else None
            plancher = max(n_min, math.ceil(patients / cap)) if cap else n_min
            # Depart : pavage a l'espacement de la zone de base, ramene aux mailles habitees.
            s_base = esp[crit][zone_i[0] if base == "rural_arbore" and False else base_non_arbore] * rdim.get(base_non_arbore, R.rayon_dimensionnement(cfg, cfg["zones"][base_non_arbore]))
            s_arb = esp[crit]["rural_arbore"] * R.rayon_dimensionnement(cfg, cfg["zones"]["rural_arbore"])
            s_pav = s_arb if part_maille_arboree > 0.5 else s_base
            xmin, xmax, ymin, ymax = cx.min(), cx.max(), cy.min(), cy.max()
            lat_pts = []
            dy = s_pav * math.sqrt(3) / 2
            k = 0
            yy = ymin
            while yy <= ymax + dy:
                xx = xmin + (s_pav / 2 if k % 2 else 0)
                while xx <= xmax + s_pav:
                    lat_pts.append((xx, yy))
                    xx += s_pav
                yy += dy
                k += 1
            _, near = arbre.query(np.array(lat_pts))
            depart = set(int(v) for v in near)
            couvert = np.zeros(n, bool)
            for j in depart:
                couvert[A_cols[j]] = True
            n_pav_snap = len(depart)
            while not couvert.all():
                uncov = np.where(~couvert)[0]
                best, bestgain = None, -1
                for i in uncov[:200]:
                    for j in voisins_i[i]:
                        gn = int((~couvert[A_cols[j]]).sum())
                        if gn > bestgain:
                            best, bestgain = j, gn
                depart.add(best)
                couvert[A_cols[best]] = True
            while len(depart) < plancher:
                depart.add(int(np.setdiff1d(np.arange(n), list(depart))[0]))
            ouverts, borne, dt, statut = resoudre(A_cols, n, plancher, depart, lim)
            n_cap = len(ouverts)
            if cap and len(ouverts):
                t2 = cKDTree(pts[ouverts])
                _, kk = t2.query(pts)
                charges = np.bincount(kk, weights=w / w.sum() * patients, minlength=len(ouverts))
                n_cap = int(sum(max(1, math.ceil(c_ / cap)) for c_ in charges))
            # Pavage de reference (v6) en melange de zones, sur la superficie du config.
            dens = lambda z: 2.0 / (math.sqrt(3) * (esp[crit][z] * R.rayon_dimensionnement(cfg, cfg["zones"][z]) / 1000) ** 2)
            pav_mel = math.ceil(cm["superficie_km2"] * (part_hab * dens("rural_arbore") + (1 - part_hab) * dens(base_non_arbore)))
            pav_v6 = math.ceil(cm["superficie_km2"] * dens(base))
            gap = (len(ouverts) - borne) / len(ouverts) if len(ouverts) and borne == borne else float("nan")
            lignes.append({"commune": nom, "zone_config": base, "critere": crit, "part_arboree_habitee": round(part_hab, 3),
                           "part_mailles_arborees": round(part_maille_arboree, 3), "mailles": n,
                           "depart_pavage_ramene": n_pav_snap, "depart_apres_reparation": len(depart),
                           "passerelles_plne": len(ouverts), "borne_inferieure": round(borne, 1),
                           "ecart_optimum": round(gap, 4), "statut": statut, "duree_s": round(dt),
                           "passerelles_avec_capacite": n_cap, "pavage_v6_zone_unique": max(n_min, pav_v6),
                           "pavage_melange_zones": max(n_min, pav_mel), "patients": round(patients)})
            print(lignes[-1], flush=True)
            with open(os.path.join(a.out, f"sites_v62_{nom}_{crit}.csv"), "w", newline="", encoding="utf-8") as f:
                wr = csv.writer(f)
                wr.writerow(["lon", "lat", "zone"])
                for j in ouverts:
                    wr.writerow([round(lon0 + cx[j] / (111320.0 * math.cos(math.radians(lat0))), 6),
                                 round(lat0 + cy[j] / 110574.0, 6), zone_i[j]])
        with open(os.path.join(a.out, f"placement_v62_{nom}.csv"), "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
            wr.writeheader()
            wr.writerows(lignes)


if __name__ == "__main__":
    main()
