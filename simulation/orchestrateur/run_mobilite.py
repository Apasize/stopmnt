#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_mobilite.py

Lance les trois scenarios de mobilite definis dans config.json
(experiences.mobilite.scenarios) et range la sortie brute de chaque run
(lignes CSV, NODE, PKT, DL, RD) pour analyse/analyse_mobilite.py.

  a_trajet       patient qui traverse une zone couverte, par politique de SF ;
  b_equidistant  patient a egale distance de deux passerelles, alertes
                 confirmees : qui acquitte ;
  c_debordement  patient qui sort de la zone couverte puis revient, sans et
                 avec store-and-forward.

Les trajets sont donnes en rayons fiables theoriques de la zone, pour rester
valables quelle que soit la calibration. Les arguments communs (propagation,
profils de fond, tailles, ADR, canaux) viennent de run_experiences.py, donc du
meme config.

Usage :
  python3 run_mobilite.py --config ../config/config.json --ns3-dir ~/ns-3.48 \\
      --bin lorawan-cell-shadow-confirmed --out ../resultats/mobilite --repetitions 3
"""

import argparse
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_experiences as R  # noqa: E402


def points(liste, r95):
    return ";".join(f"{x * r95:.1f},{y * r95:.1f}" for x, y in liste)


def lancer(ns3, binaire, args, chemin):
    chaine = binaire + " " + " ".join(f"--{k}={v}" for k, v in args.items())
    r = subprocess.run([os.path.join(ns3, "ns3"), "run", "--no-build", chaine], cwd=ns3,
                       capture_output=True, text=True)
    if r.returncode != 0:
        return f"echec {chemin} : {r.stderr[-400:]}"
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(r.stdout)
    return f"ok {chemin}"


def main():
    ap = argparse.ArgumentParser(description="Scenarios de mobilite STOP-MNT")
    ap.add_argument("--config", required=True)
    ap.add_argument("--ns3-dir", required=True)
    ap.add_argument("--bin", default="lorawan-cell-shadow-confirmed")
    ap.add_argument("--out", default="./resultats/mobilite")
    ap.add_argument("--repetitions", type=int, default=None, help="Defaut : experiences.mobilite.repetitions")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--scenarios", nargs="+", default=None, help="a_trajet b_equidistant c_debordement d_trajet_reseau")
    ap.add_argument("--fractions-interieur", type=float, nargs="+", default=None,
                    help="Consignes v6 : parts du temps a l'interieur a balayer (pont porte par le patient)")
    ap.add_argument("--alertes-mobiles", action="store_true", help="les mobiles emettent aussi des alertes")
    ap.add_argument("--duree-jours", type=float, default=None)
    a = ap.parse_args()

    cfg = R.charger_config(os.path.expanduser(a.config))
    ns3 = os.path.abspath(os.path.expanduser(a.ns3_dir))
    mob = cfg["experiences"]["mobilite"]
    if a.repetitions is None:
        a.repetitions = int(mob.get("repetitions", 1))
    sfw = cfg["store_and_forward"]
    base_exp = R.resoudre_experience(cfg, "capacite")   # profils de fond
    os.makedirs(a.out, exist_ok=True)
    taches = []
    for nom, sc in mob["scenarios"].items():
        if a.scenarios and nom not in a.scenarios:
            continue
        zcle = sc["zone"]
        zone = cfg["zones"][zcle]
        r95 = R.rayon_dimensionnement(cfg, zone)
        sigma = float(zone["shadowing_sigma_db"])
        variantes = [{}]
        if "politiques_sf" in sc:
            # "adr" : ADR reel du module (SF de depart fixe, puis commandes du
            # serveur) ; les autres : politique de SF de l'application.
            variantes = [({"mobileSf": "fixe", "adr": 1} if p == "adr" else {"mobileSf": p})
                         for p in sc["politiques_sf"]]
        if "store_and_forward" in sc:
            variantes = [{"sfw": 1 if v else 0} for v in sc["store_and_forward"]]
        fis = a.fractions_interieur or [None]
        for v, fi in [(v, fi) for v in variantes for fi in fis]:
            for run in range(1, a.repetitions + 1):
                args, _ = R.construire_args(cfg, zcle, zone, int(mob["noeuds_fixes"]), run, f"mobilite_{nom}",
                                            sigma, exp=base_exp, ctx={})
                args.update({
                    "simTime": float(mob["duree_simulee_jours"]) * 86400.0,
                    "shadowCorrDist": float(zone["distance_decorrelation_ombrage_m"]),
                    "mobileSf": cfg["radio"].get("politique_sf_mobiles", "fixe"),
                    "mobileCount": int(sc["mobiles"]),
                    "mobModel": "trajet",
                    "mobPath": points(sc["trajet_en_rayons_fiables"], r95),
                    "mobSpeed": float(mob["vitesse_m_s"]),
                    "mobStart": 600,
                    "mobStagger": float(sc["decalage_s"]),
                    "mobileProfile": f"{float(mob['cadence_instrumentation_s']):.0f}:"
                                     f"{int(cfg['profils_patients']['profils']['routine']['octets_charge'])}",
                    "sfw": 1 if sfw.get("actif") else 0,
                    "sfwProbeEvery": int(sfw["sonde_toutes_les_k_routines"]),
                    # Decision S : tampon dimensionne par l'autonomie de coupure visee.
                    "sfwBuffer": int(math.ceil(float(sfw["autonomie_coupure_h"]) * 3600.0
                                               / float(mob["cadence_instrumentation_s"]))),
                    "sfwFlush": float(sfw["espacement_lots_s"]),
                    "sfwNbTrans": int(sfw["nb_transmissions_max"]),
                    "maxMacPayload": ",".join(str(x) for x in sfw["charge_mac_max_octets_par_dr"]),
                    "micBytes": int(cfg["trafic"]["mic_non_modelise_octets"]),
                })
                if "passerelles_espacement_facteur_rayon_fiable" in sc:
                    s = float(sc["passerelles_espacement_facteur_rayon_fiable"]) * r95
                    args["gwPositions"] = f"{-s / 2:.1f},0;{s / 2:.1f},0"
                if "pavage_espacement_facteur_rayon_fiable" in sc:
                    # Hexagone de 7 passerelles centre sur le trajet.
                    s = float(sc["pavage_espacement_facteur_rayon_fiable"]) * r95
                    pos = [(0.0, 0.0)] + [(s * math.cos(math.radians(60 * k)), s * math.sin(math.radians(60 * k))) for k in range(6)]
                    args["gwPositions"] = ";".join(f"{x:.1f},{y:.1f}" for x, y in pos)
                if "alertes_par_jour_instrumentation" in sc:
                    args["alertPerDay"] = float(sc["alertes_par_jour_instrumentation"])
                args.update(v)
                etiquette = "_".join(f"{k}{val}" for k, val in v.items() if k != "adr") or "base"
                if v.get("adr"):
                    etiquette = "mobileSfadr"
                if fi is not None:
                    args["indoorFraction"] = fi
                    etiquette += f"_fi{fi:g}"
                if a.alertes_mobiles:
                    args["mobileAlert"] = 1
                if a.duree_jours:
                    args["simTime"] = a.duree_jours * 86400.0
                    args["evalExcludeLastS"] = min(108000.0, a.duree_jours * 86400.0 / 3)
                chemin = os.path.join(a.out, f"brut_{nom}_{etiquette}_run{run}.txt")
                taches.append((ns3, a.bin, args, chemin))
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        for res in pool.map(lambda t: lancer(*t), taches):
            print(res, flush=True)


if __name__ == "__main__":
    main()
