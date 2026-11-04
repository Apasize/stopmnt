#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
couverture_arcep.py

Complement aux consignes v6, point 2 : couverture cellulaire declaree par
l'ARCEP Benin (atlas.arcep.bj), croisee avec le bilan de liaison.

Pour chaque commune de l'Atlantique et pour le departement :
  - part de la surface en 4G 'bonne' (RSRP >= -90 dBm, mesure dehors) par
    operateur (MTN, MOOV, CELTIIS) et meilleur operateur ;
  - meilleure part de la surface en 2G 'bonne' (seuil -87 dBm de l'atlas) ;
  - approximation de la couverture en interieur : la part 'bonne' (avec 14 dB
    de perte en interieur, -90 dBm dehors donne environ -104 dBm dedans) ;
  - rayon fiable par site du bilan de liaison (4G 1 800 MHz et 2G 900 MHz, pont
    a l'interieur) pour la zone de la commune.
Limites : parts de surface et non de population ; couverture de 2023
(coverage_day de l'atlas).

Les reponses brutes de l'API sont gardees (--brut), datees du releve.
Usage : couverture_arcep.py --config config/config.json --bilan .../bilan_cellulaire.csv
        --out dossier [--hors-ligne]
"""
import argparse
import csv
import json
import os
import urllib.request
from datetime import date

API = "https://atlas.arcep.bj/api/qos-data/{}/{}"
OPS = ("MTN", "MOOV", "CELTIIS")


def lire(cle, id_, brut, hors_ligne):
    ch = os.path.join(brut, f"{cle}_{id_}.json")
    if not hors_ligne:
        with urllib.request.urlopen(API.format(cle, id_), timeout=60) as r:
            data = r.read()
        open(ch, "wb").write(data)
    return json.load(open(ch, encoding="utf-8"))["data"]


def part(d, techno, seuil):
    try:
        return float(d[f"{techno}_coverage"]["geo"][seuil])
    except (KeyError, TypeError):
        return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--bilan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hors-ligne", action="store_true", help="relire les reponses deja gardees")
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    ids = cfg["cellulaire"]["atlas_arcep"]["identifiants"]
    brut = os.path.join(a.out, "atlas_arcep_brut")
    os.makedirs(brut, exist_ok=True)
    bil = {}
    for r in csv.DictReader(open(a.bilan, encoding="utf-8")):
        if r["convention"] == "avec gains":
            bil[(r["zone"], r["famille"])] = float(r["rayon_fiable_km"])
    communes = cfg["cout"]["communes"]
    lignes = []
    for nom, (cle, id_) in ids.items():
        d = lire(cle, id_, brut, a.hors_ligne)
        p4 = {op: part(d.get(op, {}), "4g", "-90") for op in OPS}
        p2 = {op: part(d.get(op, {}), "2g", "-87") for op in OPS}
        meilleur = max(p4, key=p4.get)
        zone = communes.get(nom, {}).get("zone", "")
        lignes.append({
            "commune": nom, "zone": zone,
            "4g_bonne_MTN": p4["MTN"], "4g_bonne_MOOV": p4["MOOV"], "4g_bonne_CELTIIS": p4["CELTIIS"],
            "meilleur_operateur_4g": meilleur, "4g_bonne_meilleur": p4[meilleur],
            "2g_bonne_meilleure": max(p2.values()),
            "interieur_approx_4g": p4[meilleur], "interieur_approx_2g": max(p2.values()),
            "part_sans_4g_interieur_approx": round(100 - p4[meilleur], 1),
            "part_sans_4g_ni_2g_interieur_approx": round(100 - max(p4[meilleur], max(p2.values())), 1),
            "bilan_4g_1800_rayon_site_interieur_km": bil.get((zone, "4G PUSCH, 1800 MHz"), ""),
            "bilan_2g_900_rayon_site_interieur_km": bil.get((zone, "2G, 900 MHz"), ""),
            "bilan_lora_rayon_interieur_km": bil.get((zone, "LoRa privé (SF12)"), ""),
            "couverture_au": d.get("MTN", {}).get("coverage_day", ""),
            "releve_le": date.today().isoformat(),
        })
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "couverture_arcep_communes.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)
    for l in lignes:
        print(f"{l['commune']:<14} 4G MTN/MOOV/CELTIIS {l['4g_bonne_MTN']:5.1f}/{l['4g_bonne_MOOV']:5.1f}/{l['4g_bonne_CELTIIS']:5.1f}"
              f"  meilleur {l['meilleur_operateur_4g']:<8} 2G {l['2g_bonne_meilleure']:5.1f}  bilan 4G {l['bilan_4g_1800_rayon_site_interieur_km']} km, 2G {l['bilan_2g_900_rayon_site_interieur_km']} km")


if __name__ == "__main__":
    main()
