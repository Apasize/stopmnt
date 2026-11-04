#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
placement_plne.py

Complement v6.1, point 1 : placement des passerelles sur les zones habitees,
par programme lineaire en nombres entiers (PLNE), compare au pavage de la v6.

Donnees :
  - population WorldPop 2021, 100 m, version contrainte (R2024B), raster
    donnees/worldpop/ben_pop_2021_CN_100m_R2024B_v1.tif ;
  - contours des communes : atlas ARCEP (/api/cities), donnees/arcep/cities.json.

Pour chaque commune :
  1. pixels habites (population > 0) dans le contour ; projection locale en
     metres (equirectangulaire autour du centre de la commune) ;
  2. agregation en mailles de cote g (config) : chaque maille habitee est un
     point de demande (centroide pondere par la population) et un site candidat ;
  3. patients d'une maille = part de la population WorldPop de la commune x
     population du config x fraction suivie ;
  4. PLNE de couverture (scipy.optimize.milp, HiGHS) :
       min  somme_j y_j                       (cout : une passerelle = un cout)
       s.c. somme_{j a moins de R de i} y_j >= 1   pour toute maille i
            somme_j y_j >= max(nb_min, plafond(patients / capacite))
            y_j binaire ;
     R = espacement x rayon de dimensionnement / racine(3) (rayon circonscrit
     de la cellule du pavage tenu : la diversite y est comprise) ;
  5. verification de capacite : chaque maille est rattachee a la passerelle
     ouverte la plus proche ; on rapporte la charge maximale ;
  6. pavage v6 : superficie totale x densite 2 / (racine(3) s^2), et le meme
     pavage restreint a la surface habitee (mailles habitees x g^2).
Criteres : 'routine' (espacement tenu de la synthese multi-passerelles v6),
'alerte' (cout.espacement_exigence_alerte).

Sorties : placement_plne.csv, population_communes.csv, sites_<commune>_<critere>.csv,
figure placement_<commune>.png pour les communes demandees.
"""
import argparse
import csv
import json
import math
import os
import sys
import time

import numpy as np
import rasterio
import rasterio.mask
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix
from shapely.geometry import shape

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "orchestrateur"))
import run_experiences as R  # noqa: E402


def pixels(raster, geom):
    img, tr = rasterio.mask.mask(raster, [geom], crop=True, nodata=raster.nodata, filled=True)
    a = img[0]
    rows, cols = np.where(a > 0)
    xs, ys = rasterio.transform.xy(tr, rows, cols)
    return np.array(xs), np.array(ys), a[rows, cols].astype(float)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--raster", default="donnees/worldpop/ben_pop_2021_CN_100m_R2024B_v1.tif")
    ap.add_argument("--villes", default="donnees/arcep/cities.json")
    ap.add_argument("--synthese", default="resultats/production/multi_passerelles_v6_fusion/multi_passerelles_synthese_production.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fraction", type=float, default=0.02)
    ap.add_argument("--figures", nargs="*", default=["ze", "so_ava"])
    ap.add_argument("--limite-s", type=float, default=600)
    ap.add_argument("--communes", nargs="*", default=None, help="restreindre (calcul en parallele)")
    a = ap.parse_args()
    cfg = R.charger_config(a.config)
    pc = cfg["cout"].get("placement_plne", {})
    g_def = float(pc.get("maille_m", 300))
    ids = cfg["cellulaire"]["atlas_arcep"]["identifiants"]
    villes = {c["id"]: c for c in json.load(open(a.villes, encoding="utf-8"))["data"]}
    rho = float(cfg["radio"]["correlation_ombrage_entre_sites"])
    esp_routine = {r["zone"]: float(r["espacement_max_tenu_rayons_fiables"])
                   for r in csv.DictReader(open(a.synthese, encoding="utf-8"))
                   if abs(float(r["correlation_sites"]) - rho) < 1e-9 and r["espacement_max_tenu_rayons_fiables"]}
    esp_alerte = {k: float(v) for k, v in cfg["cout"]["espacement_exigence_alerte"].items() if not k.startswith("_")}
    n_min = int(cfg["cout"].get("passerelles_min_par_commune", 1))
    rast = rasterio.open(a.raster)
    os.makedirs(a.out, exist_ok=True)
    pop_rows, rows = [], []
    for nom, (cle, id_) in ids.items():
        if cle != "city" or (a.communes and nom not in a.communes):
            continue
        cm = cfg["cout"]["communes"][nom]
        zcle = cm["zone"]
        zone = cfg["zones"][zcle]
        geom = shape(villes[id_]["area_feature"])
        lon, lat, pop = pixels(rast, geom)
        lat0, lon0 = float(np.mean(lat)), float(np.mean(lon))
        x = (lon - lon0) * 111320.0 * math.cos(math.radians(lat0))
        y = (lat - lat0) * 110574.0
        px_km2 = (rast.res[0] * 111320.0 * math.cos(math.radians(lat0))) * (rast.res[1] * 110574.0) / 1e6
        pop_tot = float(pop.sum())
        r_dim = R.rayon_dimensionnement(cfg, zone)
        patients_tot = cm["population_2013"] * a.fraction
        pop_rows.append({"commune": nom, "zone": zcle, "population_worldpop_2021": round(pop_tot),
                         "population_config_2013": cm["population_2013"], "superficie_config_km2": cm["superficie_km2"],
                         "pixels_habites": len(pop), "surface_habitee_100m_km2": round(len(pop) * px_km2, 1),
                         "part_surface_habitee": round(len(pop) * px_km2 / cm["superficie_km2"], 3)})
        for crit, esp in (("routine", esp_routine), ("alerte", esp_alerte)):
            if zcle not in esp:
                continue
            s_m = esp[zcle] * r_dim
            rc = s_m / math.sqrt(3)
            g = min(max(g_def, rc / 6.0), 1000.0) if pc.get("maille_adaptative", True) else g_def
            ix = np.floor(x / g).astype(int)
            iy = np.floor(y / g).astype(int)
            cles, inv = np.unique(np.stack([ix, iy], 1), axis=0, return_inverse=True)
            inv = inv.ravel()
            w = np.bincount(inv, weights=pop)
            cx = np.bincount(inv, weights=pop * x) / w
            cy = np.bincount(inv, weights=pop * y) / w
            n = len(w)
            pts = np.stack([cx, cy], 1)
            # Voisinage : sites a moins de rc de chaque maille (grille de recherche).
            from scipy.spatial import cKDTree
            arbre = cKDTree(pts)
            voisins = arbre.query_ball_point(pts, rc)
            ri, ci = [], []
            for i, vs in enumerate(voisins):
                ri.extend([i] * len(vs))
                ci.extend(vs)
            A = csr_matrix((np.ones(len(ri)), (ri, ci)), shape=(n, n))
            cap_cfg = None
            plancher = n_min
            # Capacite : la plus contraignante des capacites simulees de la zone (tout confirme).
            caps = cfg["cout"].get("placement_plne", {}).get("capacite_par_zone", {})
            if zcle in caps:
                cap_cfg = float(caps[zcle])
                plancher = max(n_min, math.ceil(patients_tot / cap_cfg))
            cons = [LinearConstraint(A, lb=np.ones(n), ub=np.inf),
                    LinearConstraint(np.ones((1, n)), lb=plancher, ub=np.inf)]
            t0 = time.time()
            res = milp(c=np.ones(n), constraints=cons, integrality=np.ones(n), bounds=Bounds(0, 1),
                       options={"time_limit": a.limite_s, "mip_rel_gap": 0.02})
            dt = time.time() - t0
            ouverts = np.where(res.x > 0.5)[0] if res.x is not None else np.array([], int)
            # Glouton de couverture (borne haute rapide) : si le solveur s'arrete
            # a la limite de temps avec une solution mediocre, on garde la
            # meilleure des deux.
            couvert = np.zeros(n, bool)
            glou = []
            Acsc = A.tocsc()
            while not couvert.all():
                gains = np.asarray(A[~couvert].sum(axis=0)).ravel()
                j = int(np.argmax(gains))
                glou.append(j)
                couvert[Acsc[:, j].nonzero()[0]] = True
            while len(glou) < plancher:
                glou.append(int(np.setdiff1d(np.arange(n), glou)[0]))
            source = "PLNE"
            if len(ouverts) == 0 or len(glou) < len(ouverts):
                ouverts, source = np.array(glou), "glouton"
            # Charge : chaque maille a la passerelle ouverte la plus proche.
            charge_max = 0.0
            n_cap = len(ouverts)
            if len(ouverts):
                t2 = cKDTree(pts[ouverts])
                _, k = t2.query(pts)
                charges = np.bincount(k, weights=w / pop_tot * patients_tot, minlength=len(ouverts))
                charge_max = float(charges.max())
                # Capacite : une passerelle surchargee est doublee sur place
                # (plafond(charge / capacite) passerelles au site).
                if cap_cfg:
                    n_cap = int(sum(max(1, math.ceil(c_ / cap_cfg)) for c_ in charges))
            dens = 2.0 / (math.sqrt(3) * (s_m / 1000.0) ** 2)
            hab_km2 = n * (g / 1000.0) ** 2
            rows.append({"commune": nom, "zone": zcle, "critere": crit, "espacement_rayons": esp[zcle],
                         "rayon_dimensionnement_m": round(r_dim), "rayon_couverture_m": round(rc), "maille_m": round(g),
                         "mailles_habitees": n, "surface_habitee_maille_km2": round(hab_km2, 1),
                         "patients": round(patients_tot), "passerelles_plne": len(ouverts), "solution": source,
                         "passerelles_glouton": len(glou), "passerelles_avec_capacite": n_cap,
                         "borne_basse_lp": round(res.mip_dual_bound, 1) if hasattr(res, "mip_dual_bound") and res.mip_dual_bound is not None else "",
                         "statut": res.message[:60], "duree_s": round(dt, 1),
                         "charge_max_patients": round(charge_max), "capacite_tout_confirme": cap_cfg or "",
                         "pavage_surface_totale": max(n_min, math.ceil(cm["superficie_km2"] * dens)),
                         "pavage_surface_habitee": max(n_min, math.ceil(hab_km2 * dens))})
            print({k: rows[-1][k] for k in ("commune", "critere", "mailles_habitees", "passerelles_plne",
                                             "pavage_surface_totale", "pavage_surface_habitee", "duree_s", "statut")}, flush=True)
            with open(os.path.join(a.out, f"sites_{nom}_{crit}.csv"), "w", newline="", encoding="utf-8") as f:
                wr = csv.writer(f)
                wr.writerow(["x_m", "y_m", "lon", "lat"])
                for j in ouverts:
                    wr.writerow([round(cx[j]), round(cy[j]),
                                 round(lon0 + cx[j] / (111320.0 * math.cos(math.radians(lat0))), 6),
                                 round(lat0 + cy[j] / 110574.0, 6)])
            if nom in a.figures:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                fig, ax = plt.subplots(figsize=(7, 7), facecolor="#fcfcfb")
                ax.set_facecolor("#fcfcfb")
                ax.scatter(x / 1000, y / 1000, s=0.3, c=np.log10(pop + 1), cmap="Greys", alpha=0.6, linewidths=0)
                for j in ouverts:
                    ax.add_patch(plt.Circle((cx[j] / 1000, cy[j] / 1000), rc / 1000, fill=False, color="#2a78d6", linewidth=0.6))
                ax.plot(cx[ouverts] / 1000, cy[ouverts] / 1000, "^", color="#eb6834", markersize=5)
                bx, by = geom.exterior.xy if geom.geom_type == "Polygon" else max(geom.geoms, key=lambda p: p.area).exterior.xy
                ax.plot((np.array(bx) - lon0) * 111320 * math.cos(math.radians(lat0)) / 1000,
                        (np.array(by) - lat0) * 110574 / 1000, color="#52514e", linewidth=0.8)
                ax.set_aspect("equal")
                ax.set_xlabel("km", fontsize=8)
                ax.set_ylabel("km", fontsize=8)
                ax.set_title(f"{nom.replace('_', '-').title()} : {len(ouverts)} passerelles (PLNE, critère {crit}) "
                             f"contre {rows[-1]['pavage_surface_totale']} au pavage", fontsize=9, loc="left")
                fig.text(0.01, 0.01, f"Gris : population WorldPop 2021 (100 m). Triangles : passerelles ; cercles : rayon de couverture "
                         f"{rc / 1000:.2f} km (espacement {esp[zcle]} rayons de {r_dim / 1000:.2f} km).", fontsize=7, color="#52514e")
                fig.tight_layout(rect=(0, 0.03, 1, 1))
                fig.savefig(os.path.join(a.out, f"placement_{nom}_{crit}.png"), dpi=200, facecolor="#fcfcfb")
                plt.close(fig)
    suf = ("_" + "_".join(a.communes)) if a.communes else ""
    for nom_f, rws in ((f"population_communes{suf}.csv", pop_rows), (f"placement_plne{suf}.csv", rows)):
        if not rws:
            continue
        with open(os.path.join(a.out, nom_f), "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(rws[0].keys()))
            wr.writeheader()
            wr.writerows(rws)


if __name__ == "__main__":
    main()
