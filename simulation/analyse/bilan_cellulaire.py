#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bilan_cellulaire.py

Couverture par site, LoRa contre 4G (et NB-IoT en perspective), par bilan de
liaison (decision O de l'auteur, 2026-10-26). Meme propagation par zone et
meme ombrage que les simulations LoRa (fonctions de run_experiences.py), pour
comparer a bases egales.

Pour chaque famille :
  perte tolerable = MCL + gain d'antenne du site + gain du terminal
  rayon median    : perte moyenne = perte tolerable (borne par l'horizon)
  rayon fiable    : perte moyenne + q(seuil) x sigma = perte tolerable
  sites / 100 km2 : pavage hexagonal d'une cellule isolee de rayon r,
                    espacement r racine(3), densite 2 / (racine(3) s^2)
4G : la propagation calibree a 868 MHz est corrigee de 20 log10(f / 868) pour
chaque bande testee (hypothese d'espace libre, bande beninoise a sourcer).

Les MCL ne comprennent pas les gains d'antenne (3GPP TR 36.888, tableau
5.2.1.2-2 : MCL = puissance - sensibilite, d'antenne a antenne).

Sortie : bilan_cellulaire.csv et un resume a l'ecran.
"""

import argparse
import csv
import math
import os
import sys
from statistics import NormalDist

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "orchestrateur"))
import run_experiences as R  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Bilan de liaison LoRa contre 4G par zone")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default="./resultats/cellulaire")
    a = ap.parse_args()
    cfg = R.charger_config(os.path.expanduser(a.config))
    cel = cfg["cellulaire"]
    seuil = float(cfg["methode"]["seuil_acceptabilite_pdr"])
    q = NormalDist().inv_cdf(seuil)
    g_term = float(cel["gain_antenne_terminal_dbi"])
    mcl_lora = R.budget_sf12_db(cfg)
    familles = [("LoRa privé (SF12)", mcl_lora, R.gain_passerelle_dbi(cfg), 868.0)]
    for f in cel["bandes_4g_mhz_a_tester"]:
        familles.append((f"4G PUSCH, {f} MHz", float(cel["mcl_pusch_db"]), float(cel["gain_antenne_enb_dbi"]), float(f)))
    # Variante Cat-1 (MCL 142,7 dB, livre blanc LTE-M 2017) a la bande beninoise.
    if cel.get("mcl_cat1_db"):
        fb = float(cel.get("bande_4g_benin_mhz", 1800))
        familles.append((f"4G Cat-1, {fb:g} MHz", float(cel["mcl_cat1_db"]), float(cel["gain_antenne_enb_dbi"]), fb))
    # Consignes v6, point 9 : 2G a 900 MHz (MCL 3GPP TR 45.820, annexe B.2),
    # gain de site repris de l'eNodeB (hypothese).
    if cel.get("mcl_2g_db"):
        f2 = float(cel.get("bande_2g_benin_mhz", 900))
        familles.append((f"2G, {f2:g} MHz", float(cel["mcl_2g_db"]), float(cel["gain_antenne_enb_dbi"]), f2))
    familles.append(("NB-IoT (perspective), 800 MHz", float(cel["mcl_nbiot_db"]),
                     float(cel["gain_antenne_enb_dbi"]), 800.0))
    dh = R.distance_horizon_m(cfg)

    lignes = []
    for zcle, zone in cfg["zones"].items():
        if zcle.startswith("_"):
            continue
        sigma = float(zone["shadowing_sigma_db"])
        for (nom, mcl, g_site0, f), gains in [(fm, gn) for gn in (False, True) for fm in familles]:
            # Deux conventions : sans gains d'antenne (comme les simulations LoRa
            # actuelles) et avec les gains de la decision O.
            g_site = g_site0 if gains else 0.0
            corr = 20.0 * math.log10(f / float(cfg["radio"]["frequence_mhz"]))
            # Perte en interieur : celle du dimensionnement LoRa (comprise dans la
            # propagation de la zone a 868 MHz), corrigee a la frequence de la
            # famille par UIT-R P.2109 (consignes v6).
            if R.perte_interieur_db(cfg, zone) > 0.0:
                corr += R.p2109_mediane_db(f / 1000.0, cfg) - R.p2109_mediane_db(float(cfg["radio"]["frequence_mhz"]) / 1000.0, cfg)
            tol = mcl + g_site + (g_term if gains else 0.0) - corr
            r50 = min(R.distance_pour_perte(cfg, zone, tol), dh)
            r95 = R.distance_pour_perte(cfg, zone, tol - q * sigma)
            r95h = min(r95, dh)
            s = r95h * math.sqrt(3)
            dens = 2.0 / (math.sqrt(3) * (s / 1000.0) ** 2) * 100.0 if s > 0 else float("inf")
            lignes.append({"zone": zcle, "convention": "avec gains" if gains else "sans gains",
                           "famille": nom, "mcl_db": round(mcl, 1), "gain_site_dbi": g_site,
                           "correction_frequence_db": round(corr, 2), "perte_tolerable_db": round(tol, 1),
                           "rayon_median_km": round(r50 / 1000, 2), "rayon_fiable_km": round(r95h / 1000, 2),
                           "borne_horizon": r95 > dh,
                           "sous_d0_hors_domaine": r95 < R.reference_effective(cfg, zone)[0],
                           "extrapole_sous_1km": r95 < float(zone["distance_reference_m"]), "sites_par_100km2_cellule_isolee": round(dens, 3)})

    os.makedirs(a.out, exist_ok=True)
    chemin = os.path.join(a.out, "bilan_cellulaire.csv")
    with open(chemin, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)
    print(f"Fiabilite {100 * seuil:.0f} % (marge {q:.3f} sigma), horizon {dh / 1000:.1f} km, "
          f"terminal {g_term} dBi. Fichier : {chemin}")
    for l in lignes:
        print(f"  {l['zone']:<13} {l['convention']:<10} {l['famille']:<30} tolere {l['perte_tolerable_db']:6.1f} dB  "
              f"r50 {l['rayon_median_km']:6.2f} km  r95 {l['rayon_fiable_km']:6.2f} km"
              f"{' (horizon)' if l['borne_horizon'] else ''}"
              f"{' (sous d0, hors domaine du modele)' if l['sous_d0_hors_domaine'] else ''}  "
              f"sites/100 km2 {l['sites_par_100km2_cellule_isolee']:7.2f}")


if __name__ == "__main__":
    main()
