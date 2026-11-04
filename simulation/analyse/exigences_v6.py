#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
exigences_v6.py

Consignes v6, point 6 : verification des exigences.
  - routine : au moins 95 % des mesures livrees en moins de 72 h, par patient ;
  - alertes : au moins 99 % livrees en moins de 15 min cote reseau ;
  - 100 % des alertes non confirmees detectees par le pont (alarme technique) ;
  - distribution du delai d'alerte : mediane, 95e et 99e centiles, IC par
    bootstrap sur les repetitions (moyenne des centiles par run, 2 000
    reechantillonnages). Le maximum observe n'est donne qu'a titre indicatif.
  - nombre d'essais d'alerte possibles en 15 min au bord de cellule (SF12)
    sous le cycle de service de 1 %, calcule (temps d'antenne LoRa, fiche
    Semtech AN1200.13 / formule du module).

Entrees : dossiers d'experiences (noeuds_*.csv et ack_*.csv). Sorties :
exigences_v6.csv (une ligne par zone, variante, palier) et essais_alerte_sf12.csv.
"""
import argparse
import csv
import glob
import json
import math
import os
import random
import re
from collections import defaultdict


def toa_s(payload, sf, bw=125000, cr=1, preamble=8, header=True, crc=True):
    """Temps d'antenne LoRa (formule Semtech, reprise par LoraPhy::GetTimeOnAir)."""
    ts = (2 ** sf) / bw
    de = 1 if (sf >= 11 and bw == 125000) else 0
    ih = 0 if header else 1
    n = 8 + max(math.ceil((8 * payload - 4 * sf + 28 + 16 * crc - 20 * ih) / (4 * (sf - 2 * de))) * (cr + 4), 0)
    return (preamble + 4.25) * ts + n * ts


def boot(vals, rnd, n=2000):
    """IC 95 % par bootstrap de la moyenne ; inf si un run a un centile infini."""
    if not vals:
        return (float("nan"),) * 3
    if any(math.isinf(v) for v in vals):
        k = sum(1 for v in vals if math.isinf(v))
        return float("inf"), float("inf"), float(k)   # k runs a centile infini
    m = sum(vals) / len(vals)
    bs = sorted(sum(rnd.choice(vals) for _ in vals) / len(vals) for _ in range(n))
    return m, bs[int(0.025 * n)], bs[int(0.975 * n) - 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--dossiers", required=True, nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    ex = cfg["qualite_service"]["exigences_v6"]
    rnd = random.Random(1)
    acc = defaultdict(lambda: defaultdict(list))
    for d in a.dossiers:
        exp = os.path.basename(os.path.normpath(d))
        for ch in glob.glob(os.path.join(d, "ack_*.csv")):
            for r in csv.DictReader(open(ch, encoding="utf-8")):
                k = (exp, r["zone"], r["variante"], int(r["nDevices"]))
                if r["type"] == "alerte_reseau":
                    for q in ("p50_s", "p95_s", "p99_s"):
                        acc[k]["alerte_" + q].append(float(r[q]))
                    acc[k]["alerte_max_s"].append(float(r["max_s"]))
                    n = int(r["nConf"])
                    if n:
                        acc[k]["alerte_15min"].append(int(r["nAcked"]) / n)
                    al, unc = int(r["nFail"]), int(r["gardes"])
                    if al + unc:
                        acc[k]["alarmes_detectees"].append(al / (al + unc))
                elif r["type"] == "alerte_interieur" and int(r["nConf"]):
                    acc[k]["alerte_interieur_15min"].append(int(r["nAcked"]) / int(r["nConf"]))
                elif r["type"] == "remontee" and int(r["nConf"]):
                    acc[k]["remontee_trop_tard"].append(int(r["nFail"]) / int(r["nConf"]))
        for ch in glob.glob(os.path.join(d, "noeuds_*.csv")):
            cur, el, ok, pat = None, 0, 0, []
            a5 = [0, 0]
            def ferme():
                if cur is None:
                    return
                if a5[0]:
                    acc[cur]["alerte_5min"].append(a5[1] / a5[0])
                acc[cur]["routine_72h"].append(ok / el if el else float("nan"))
                acc[cur]["patients_72h_ok"].append(sum(1 for x in pat if x >= ex["routine_livree_72h_par_patient"]) / len(pat)
                                                   if pat else float("nan"))
            run_cour = None
            for r in csv.DictReader(open(ch, encoding="utf-8")):
                if not r.get("readingsEligible"):
                    break
                k = (exp, r["zone"], r["variante"], int(r["nDevices"]))
                rk = (k, r["runNumber"])
                if rk != run_cour:
                    ferme()
                    cur, run_cour, el, ok, pat = k, rk, 0, 0, []
                    a5 = [0, 0]
                if r.get("alertsOk5") not in (None, ""):
                    a5[0] += int(r["alertsCounted"])
                    a5[1] += int(r["alertsOk5"])
                e, o = int(r["readingsEligible"]), int(r["readingsOk72h"])
                el += e
                ok += o
                if e > 0:
                    pat.append(o / e)
            ferme()
    lignes = []
    for k in sorted(acc):
        exp, zone, var, n = k
        d = acc[k]
        l = {"experience": exp, "zone": zone, "variante": var, "nDevices": n,
             "repetitions": len(d.get("alerte_p50_s", d.get("routine_72h", [])))}
        for nom in ("routine_72h", "patients_72h_ok", "alerte_15min", "alerte_5min", "alerte_interieur_15min",
                    "alarmes_detectees", "remontee_trop_tard"):
            v = [x for x in d.get(nom, []) if not math.isnan(x)]
            l[nom] = round(sum(v) / len(v), 4) if v else ""
        for q in ("p50_s", "p95_s", "p99_s"):
            m, lo, hi = boot(d.get("alerte_" + q, []), rnd)
            l[f"alerte_{q}"] = m if math.isinf(m) else round(m, 2)
            l[f"alerte_{q}_ic_bas"] = "" if math.isinf(m) else round(lo, 2)
            l[f"alerte_{q}_ic_haut"] = f"{int(hi)} runs infinis" if math.isinf(m) else round(hi, 2)
        mx = [x for x in d.get("alerte_max_s", []) if x >= 0]
        l["alerte_max_indicatif_s"] = round(max(mx), 1) if mx else ""
        l["exigence_routine_72h"] = (l["patients_72h_ok"] != "" and l["patients_72h_ok"] >= 0.95)
        l["exigence_alerte_15min"] = (l["alerte_15min"] != "" and l["alerte_15min"] >= ex["alerte_livree_15min"])
        l["exigence_alarme"] = (l["alarmes_detectees"] == "" or l["alarmes_detectees"] >= ex["alarme_technique_alerte_non_confirmee"])
        lignes.append(l)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "exigences_v6.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)

    # Essais possibles en 15 min au bord de cellule (SF12), cycle de service 1 %.
    al = cfg["profils_patients"]["alerte"]
    phy = int(al["octets_charge"]) + 4 + 13   # charge + MIC + en-tetes LoRaWAN (MHDR 1, FHDR 7, FPort 1, MIC compte a part)
    rows = []
    for sf in (7, 9, 10, 11, 12):
        t = toa_s(phy, sf)
        attente = t * (1 / 0.01 - 1)
        # Entre deux essais : la fenetre RX2 (RX1 + 1 s) doit se fermer et le
        # cycle de service impose 99 x temps d'antenne dans la sous-bande.
        ecart = max(attente, float(cfg["passerelle"]["fenetres_reception"]["rx1_delai_s"]) + 1 + t)
        n15 = 1 + int((900 - t) // ecart)
        rows.append({"sf": sf, "octets_phy": phy, "temps_antenne_s": round(t, 3), "attente_cycle_1pc_s": round(attente, 1),
                     "essais_en_15_min": n15, "essais_max_config": int(al["nb_transmissions_max"])})
    with open(os.path.join(a.out, "essais_alerte_sf12.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
