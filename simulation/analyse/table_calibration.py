#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
table_calibration.py

Consignes v4, point 8 : table de calibration unique par zone, lue dans le
config (source de verite) : exposant, perte a 1 km, ombrage, gain, hauteurs,
vegetation, decorrelation, source ; plus le rayon fiable theorique (bilan de
liaison SF12) et le rayon fiable simule (probit, borne basse IC 95 %).
Ajoute la perte calculee a 5 et 10 km, qui montre d'ou vient l'ecart entre
zones (par exemple peri-urbain contre rural degage).

Usage : table_calibration.py --config config/config.json
        --probit .../rayon_fiable_probit.csv --out fichier.csv
"""
import argparse
import csv
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "orchestrateur"))
import run_experiences as R  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--probit", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cfg = R.charger_config(a.config)
    gain = float(cfg["passerelle"]["gain_antenne_dbi"])
    probit = {r["groupe"]: r for r in csv.DictReader(open(a.probit, encoding="utf-8"))}
    lignes = []
    for zc, z in cfg["zones"].items():
        if not isinstance(z, dict):
            continue
        am, _, _, _ = R.params_vegetation(cfg, z)
        veg = z.get("vegetation")
        dens = R.densite_vegetation(z) if veg else 0.0
        g = f"{zc} | vegetation={dens} gain={gain:g}" if am > 0 else f"{zc} | gain={gain:g}"
        n, pl0, d0 = float(z["path_loss_exponent"]), float(z["perte_reference_db"]), float(z["distance_reference_m"])
        pl = lambda d: pl0 + 10 * n * math.log10(d / d0) + R.perte_vegetation_db(cfg, z, d)
        lignes.append({
            "zone": zc, "exposant_n": n, "plage_n": z.get("path_loss_exponent_plage"),
            "perte_1km_db": pl0, "sigma_ombrage_db": float(z["shadowing_sigma_db"]),
            "decorrelation_ombrage_m": z.get("distance_decorrelation_ombrage_m"),
            "vegetation_densite": dens, "vegetation_saturation_db": round(am, 2),
            "gain_passerelle_dbi": gain, "hauteur_passerelle_m": float(cfg["passerelle"]["hauteur_antenne_m"]),
            "hauteur_noeud_m": float(cfg["noeud"]["hauteur_antenne_m"]),
            "perte_5km_db": round(pl(5000), 1), "perte_10km_db": round(pl(10000), 1),
            "rayon_theorique_km": round(R.rayon_fiable_theorique(cfg, z) / 1000, 2),
            "rayon_fiable_simule_km": next((round(int(probit[k]["rayon_fiable_m"]) / 1000, 2) for k in (g, f"{zc} | gain={gain:g}") if k in probit), ""),
            "source": z.get("_source", ""),
        })
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)
    for l in lignes:
        print({k: v for k, v in l.items() if k != "source"})


if __name__ == "__main__":
    main()
