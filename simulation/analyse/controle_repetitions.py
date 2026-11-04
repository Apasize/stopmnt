#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
controle_repetitions.py

Consignes v4, point 4 : regle des repetitions. 5 repetitions pour les balayages
exploratoires ; pour chaque chiffre annonce, repeter jusqu'a ce que la
demi-largeur de l'IC 95 % passe sous 1 point de livraison (ou 5 % du rayon),
avec un minimum de 10 (methode.regle_repetitions du config).

Ce script lit les tableaux de points deja produits et rapporte, par point :
nombre de repetitions obtenu, demi-largeur, critere, respect, et le nombre de
repetitions qu'il faudrait (n x (demi-largeur / cible)^2, la demi-largeur
decroissant en 1 / racine(n)). Il ne relance rien.

Sortie : controle_repetitions.csv (une ligne par point) et un resume.
"""
import argparse
import csv
import json
import math
import os


def ajoute(out, exp, point, n, hw, cible, unite, n_min):
    if hw is None or (isinstance(hw, float) and math.isnan(hw)):
        return
    besoin = max(n_min, math.ceil(n * (hw / cible) ** 2)) if hw > cible else max(n_min, n)
    out.append({"experience": exp, "point": point, "repetitions": n, "demi_largeur": round(hw, 4),
                "cible": cible, "unite": unite, "respecte": n >= n_min and hw <= cible,
                "repetitions_necessaires_estimees": besoin})


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    rg = cfg["methode"]["regle_repetitions"]
    n_min, c_pdr, c_ray = int(rg["minimum_chiffre_annonce"]), float(rg["demi_largeur_max_livraison"]), float(rg["demi_largeur_max_rayon_relative"])
    out = []
    P = a.prod
    # Rayon fiable (probit) : demi-largeur relative = (IC haut - IC bas) / 2 / rayon a 95 %.
    for exp, n in (("portee", 20), ("portee_v4", 100), ("portee_v5", 100), ("portee_v6", 100), ("portee_interieur_v6", 20), ("portee_sensibilite_v6", 20)):
        ch = os.path.join(P, exp, "rayon_fiable_probit", "rayon_fiable_probit.csv")
        if not os.path.exists(ch):
            continue
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            hw = (int(r["rayon_95_ic_haut_m"]) - int(r["rayon_fiable_m"])) / 2 / max(1, int(r["rayon_95_m"]))
            ajoute(out, f"{exp} (rayon fiable)", r["groupe"], n, hw, c_ray, "fraction du rayon", n_min)
    # Capacite : livraison de routine par point.
    for exp in ("capacite_modes_5dBi", "capacite_cadence", "sensibilite_rx2_nbtrans", "reglementaire_rx2_14dbm",
                "delai_rx1_5s", "capacite_longue_v4", "capacite_v5", "capacite_rx2_14dbm_descendante", "capacite_v6", "capacite_recap_v6",
                "remontee_v6", "alertes_rares_v6", "continuite_interieur_v6", "capacite_rx2_14dbm_v6"):
        ch = os.path.join(P, exp, "capacite_points_production.csv")
        if not os.path.exists(ch):
            ch = os.path.join(P, exp, "capacite_points_7j.csv")
        if not os.path.exists(ch):
            continue
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            ajoute(out, exp, f"{r['zone']} | {r['variante']} | n={r['nDevices']}", int(r["repetitions"]),
                   f(r["pdr_routine_ic95"]), c_pdr, "livraison", n_min)
    # Multi-passerelles : livraison globale par point.
    ch = os.path.join(P, "multi_passerelles", "multi_passerelles_production.csv")
    for r in csv.DictReader(open(ch, encoding="utf-8")):
        ajoute(out, "multi_passerelles", f"{r['zone']} | {r.get('variante', '')} | {r['espacement_m']} m",
               int(r["repetitions"]), f(r["taux_livraison_ic95"]), c_pdr, "livraison", n_min)
    # Robustesse : part de patients servis.
    for ch in (os.path.join(P, "robustesse_panne", "robustesse_panne.csv"),
               os.path.join(P, "robustesse_panne_v5", "robustesse_panne.csv"),
               os.path.join(P, "robustesse_v6", "robustesse_panne.csv")):
        if not os.path.exists(ch):
            continue
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            ajoute(out, os.path.basename(os.path.dirname(ch)), f"{r['zone']} | {r['espacement_facteur']} | {r['passerelle_centrale']}",
                   int(r["repetitions"]), f(r["part_servie_ic95"]), c_pdr, "part servie", n_min)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    par = {}
    for o in out:
        e = par.setdefault(o["experience"], [0, 0, 0, 0])
        e[0] += 1
        e[1] += o["respecte"]
        e[2] = max(e[2], o["repetitions_necessaires_estimees"])
        e[3] = o["repetitions"] if not e[3] else min(e[3], o["repetitions"])
    print(f"{'experience':<26} points  respectes  repetitions  max necessaires")
    for k, (n, ok, mx, rep) in par.items():
        print(f"{k:<26} {n:>6}  {ok:>9}  {rep:>11}  {mx:>15}")


if __name__ == "__main__":
    main()
