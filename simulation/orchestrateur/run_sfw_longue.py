#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_sfw_longue.py

Retour de l'auteur sur la v4 (2026-10-28, point 6) : simulation longue avec
store-and-forward, pour tester le tampon de 72 h en charge.

Montage (experiences.sfw_longue du config) :
  - une passerelle, patients fixes au palier de charge donne (profils de base
    a 10 messages par jour, mode mixte RX2 : alertes confirmees), store-and-
    forward actif sur tous les ponts (sonde confirmee une routine sur k) ;
  - des patients mobiles au meme profil qui quittent la couverture : aller
    jusqu'a une distance au-dela de l'horizon radio, pause, retour. La pause
    est balayee pour encadrer l'autonomie du tampon (en deca et au-dela de
    72 h). L'horizon est applique en simulation (coupure franche), pour que
    la sortie de couverture soit nette quelle que soit la zone ;
  - meme tirage avec et sans store-and-forward.
Le tampon est dimensionne comme en mobilite (decision S) : autonomie x 3600 /
periode de mesure.

Sortie brute par run (lignes CSV, NODE...) pour analyse/analyse_sfw_longue.py.
"""
import argparse
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_experiences as R  # noqa: E402
from run_mobilite import lancer  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--ns3-dir", required=True)
    ap.add_argument("--bin", default="stopmnt-production")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=1)
    a = ap.parse_args()
    cfg = R.charger_config(os.path.expanduser(a.config))
    ns3 = os.path.abspath(os.path.expanduser(a.ns3_dir))
    E = cfg["experiences"]["sfw_longue"]
    sfw = cfg["store_and_forward"]
    base = R.resoudre_experience(cfg, E["experience_de_base"])
    hz = cfg["radio"]["horizon_radio"]
    dh = R.distance_horizon_m(cfg)
    os.makedirs(a.out, exist_ok=True)
    taches = []
    for zcle in E["zones"]:
        zone = cfg["zones"][zcle]
        sigma = float(zone["shadowing_sigma_db"])
        r95 = R.rayon_dimensionnement(cfg, zone)
        for n in E["patients_fixes"]:
            for pause_h in E["pause_hors_couverture_h"]:
                for s in (0, 1):
                    for run in range(1, int(E["repetitions"]) + 1):
                        ctx = {"messages_par_jour": float(E["messages_par_jour"]),
                               "mode_confirmation": E["mode_confirmation"]}
                        args, _ = R.construire_args(cfg, zcle, zone, n, run, "sfw_longue", sigma, exp=base, ctx=ctx)
                        prof = args["profiles"].split(";")[0].split(":")
                        periode = float(prof[0])
                        d_loin = float(E["distance_hors_couverture_facteur_horizon"]) * dh
                        d_pres = 0.3 * r95
                        args.update({
                            "simTime": float(E["duree_simulee_jours"]) * 86400.0,
                            "horizonCoefKm": float(hz["coefficient_km"]),
                            "horizonLossDb": float(hz["perte_au_dela_db"]),
                            "mobileCount": int(E["mobiles"]),
                            "mobileSf": cfg["radio"].get("politique_sf_mobiles", "fixe"),
                            "mobModel": "trajet",
                            "mobPath": f"{d_pres:.1f},0;{d_loin:.1f},0;{d_pres:.1f},0",
                            "mobSpeed": float(cfg["experiences"]["mobilite"]["vitesse_m_s"]),
                            "mobPause": float(pause_h) * 3600.0,
                            "mobStart": 600,
                            "mobStagger": float(E["decalage_mobiles_s"]),
                            "mobileProfile": f"{periode:.0f}:{int(prof[1]) - int(cfg['trafic']['mic_non_modelise_octets'])}",
                            "mobileAlert": 0,
                            "sfw": s,
                            "sfwProbeEvery": int(sfw["sonde_toutes_les_k_routines"]),
                            "sfwBuffer": int(math.ceil(float(sfw["autonomie_coupure_h"]) * 3600.0 / periode)),
                            "sfwFlush": float(sfw["espacement_lots_s"]),
                            "sfwNbTrans": int(sfw["nb_transmissions_max"]),
                            "maxMacPayload": ",".join(str(x) for x in sfw["charge_mac_max_octets_par_dr"]),
                            "micBytes": int(cfg["trafic"]["mic_non_modelise_octets"]),
                        })
                        chemin = os.path.join(a.out, f"brut_{zcle}_n{n}_pause{pause_h:g}h_sfw{s}_run{run}.txt")
                        if os.path.exists(chemin):
                            continue
                        taches.append((ns3, a.bin, args, chemin))
    print(f"{len(taches)} runs", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        for res in pool.map(lambda t: lancer(*t), taches):
            print(res, flush=True)


if __name__ == "__main__":
    main()
