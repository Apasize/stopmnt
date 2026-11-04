#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
secours_lora.py

Complement v6.1, point 2 (cote LoRa) : patients en ombre profonde dans le reseau
pave a l'espacement de routine, servis par un pont cellulaire avec repli 2G.

Le serveur repere un patient mal desservi a son historique (taux de reception
de sa routine). Pour un seuil tau, un patient est 'marque' si sa livraison de
routine est inferieure a tau. Par zone et par seuil, sur les repetitions :
  - part de patients marques f ;
  - part des alertes des patients NON marques livrees en 15 min (a) ;
  - alertes de l'ensemble si les patients marques passent au cellulaire avec
    une probabilite c de livrer l'alerte en 15 min :  (1 - f) a + f c,
    c = couverture interieure approchee (meilleure part 4G ou 2G de l'atlas
    ARCEP, departement) : HYPOTHESE (independance entre ombre LoRa et
    couverture cellulaire, livraison cellulaire = couverture).
Entree : noeuds d'exigences_pavage_v61 (tout confirme, RX2 27 dBm), espacement
de routine de la zone (le plus proche teste). Sortie : secours_lora.csv.
"""
import argparse
import csv
import glob
import os
import re
import statistics as st
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--noeuds", required=True)
    ap.add_argument("--couverture", required=True, help="couverture_arcep_communes.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--espacements", default="urbain_dense:4.0,peri_urbain:3.0,rural_degage:3.0,rural_arbore:3.0,lacustre:4.0")
    a = ap.parse_args()
    esp = {k: float(v) for k, v in (x.split(":") for x in a.espacements.split(","))}
    dep = next(r for r in csv.DictReader(open(a.couverture, encoding="utf-8")) if r["commune"] == "departement_atlantique")
    c = max(float(dep["4g_bonne_meilleur"]), float(dep["2g_bonne_meilleure"])) / 100
    seuils = [0.5, 0.8, 0.9, 0.95]
    runs = defaultdict(lambda: defaultdict(list))
    for ch in glob.glob(a.noeuds):
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            v = r["variante"]
            if "tout_confirme_rx2" not in v or "rx2dbm=27" not in v:
                continue
            e = float(re.search(r"espacement=([\d.]+)", v).group(1))
            if abs(e - esp.get(r["zone"], -1)) > 1e-9:
                continue
            runs[(r["zone"], e)][r["runNumber"]].append(r)
    lignes = []
    for (z, e), rr in sorted(runs.items()):
        for tau in seuils:
            fs, aa, tot = [], [], []
            for nds in rr.values():
                marq = [n for n in nds if int(n["newSent"]) > 0 and int(n["received"]) / int(n["newSent"]) < tau]
                ok = [n for n in nds if n not in marq]
                na = sum(int(n["alertsCounted"]) for n in ok)
                fs.append(len(marq) / len(nds))
                aa.append(sum(int(n["alertsOk15"]) for n in ok) / na if na else float("nan"))
                tot.append((1 - fs[-1]) * aa[-1] + fs[-1] * c)
            lignes.append({"zone": z, "espacement": e, "seuil_livraison_routine": tau, "repetitions": len(fs),
                           "part_patients_au_cellulaire": round(st.mean(fs), 4),
                           "alertes_15min_lora_non_marques": round(st.mean(aa), 4),
                           "couverture_cellulaire_supposee": round(c, 3),
                           "alertes_15min_ensemble": round(st.mean(tot), 4)})
            print(lignes[-1])
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "secours_lora.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)


if __name__ == "__main__":
    main()
