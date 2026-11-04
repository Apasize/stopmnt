#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyse_multi_passerelles.py

Analyse de l'experience multi_passerelles : diversite de reception et
deduplication au serveur.

Entrees : resultats_multi_passerelles_*.csv (une ligne par run) et
noeuds_multi_passerelles_*.csv (une ligne par noeud et par run), config.json.

Indicateurs par zone, moyenne et IC 95 % (Student) sur les repetitions :
  taux_livraison        trames livrees au serveur apres deduplication / nouvelles
  taux_plus_proche      trames recues par la seule passerelle la plus proche /
                        nouvelles : ce qu'on aurait sans diversite
  gain_diversite        difference des deux, en points
  frac_multi            trames entendues par au moins deux passerelles
  facteur_duplication   receptions passerelles / trames livrees : charge de
                        doublons que le serveur deduplique
  patients_sous_seuil   fraction de noeuds sous le seuil de qualite, avec
                        diversite et sans (plus proche seule)
  latence_moy_s         emission -> premiere reception passerelle
Controle : arrivees au serveur == receptions passerelles (aucune perte entre
passerelle et serveur), trames livrees == compte du traceur du module.

Sortie : multi_passerelles_<etiquette>.csv dans --out et une vue texte.
"""

import argparse
import csv
import json
import math
import os
import statistics as st
from collections import defaultdict


def ic95(valeurs):
    n = len(valeurs)
    if n < 2:
        return float("nan")
    from scipy.stats import t
    return t.ppf(0.975, n - 1) * st.stdev(valeurs) / math.sqrt(n)


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser(description="Analyse multi-passerelles")
    ap.add_argument("--config", required=True)
    ap.add_argument("--resultats", required=True, help="resultats_multi_passerelles_*.csv")
    ap.add_argument("--noeuds", required=True, help="noeuds_multi_passerelles_*.csv")
    ap.add_argument("--out", default="./resultats")
    ap.add_argument("--etiquette", default="multi_passerelles")
    a = ap.parse_args()

    cfg = json.load(open(os.path.expanduser(a.config), encoding="utf-8"))
    seuil = float(cfg["methode"]["seuil_acceptabilite_pdr"])
    runs = lire(a.resultats)
    noeuds_tous = lire(a.noeuds)
    # Masquage horizon, comme pour la portee : un noeud au-dela de l'horizon de
    # sa passerelle la plus proche n'a pas de sens physique dans ce modele.
    hz = cfg["radio"].get("horizon_radio", {})
    d_hz = (1000.0 * float(hz["coefficient_km"])
            * (math.sqrt(float(cfg["passerelle"]["hauteur_antenne_m"]))
               + math.sqrt(float(cfg["noeud"]["hauteur_antenne_m"])))) if hz.get("actif") else float("inf")
    noeuds = [n for n in noeuds_tous if float(n["distance_m"]) <= d_hz]
    masques = len(noeuds_tous) - len(noeuds)

    # Controles de coherence, run par run.
    anomalies = []
    for r in runs:
        if int(r["nsArrivals"]) != int(r["gwReceptions"]):
            anomalies.append(f"{r['zone']} run {r['runNumber']} : arrivees serveur "
                             f"{r['nsArrivals']} != receptions passerelles {r['gwReceptions']}")
    # Groupe = zone et variante (espacement balaye) ; cle de run = groupe + numero.
    def groupe(r):
        v = r.get("variante", "base") or "base"
        return r["zone"] if v == "base" else f"{r['zone']} | {v}"
    par_run = defaultdict(list)
    for nd in noeuds:
        par_run[(groupe(nd), nd["runNumber"])].append(nd)
    par_run_tous = defaultdict(list)
    for nd in noeuds_tous:
        par_run_tous[(groupe(nd), nd["runNumber"])].append(nd)
    for r in runs:
        nds = par_run_tous[(groupe(r), r["runNumber"])]
        if sum(int(n["received"]) for n in nds) != int(r["received"]):
            anomalies.append(f"{r['zone']} run {r['runNumber']} : somme par noeud != traceur")

    # Indicateurs par run, puis moyenne et IC par zone.
    indic = defaultdict(lambda: defaultdict(list))
    for (zone, run), nds in par_run.items():
        nouv = sum(int(n["newSent"]) for n in nds)
        recu = sum(int(n["received"]) for n in nds)
        proche = sum(int(n["rxNearest"]) for n in nds)
        recep = sum(int(n["gwReceptions"]) for n in nds)
        multi = sum(int(n["multiGw"]) for n in nds)
        lats = [float(n["latencyMean_s"]) for n in nds if float(n["latencyMean_s"]) >= 0]
        actifs = [n for n in nds if int(n["newSent"]) > 0]
        z = indic[zone]
        z["taux_livraison"].append(recu / nouv)
        z["taux_plus_proche"].append(proche / nouv)
        z["gain_diversite_pts"].append(100 * (recu - proche) / nouv)
        z["frac_multi"].append(multi / recu if recu else 0.0)
        z["facteur_duplication"].append(recep / recu if recu else 0.0)
        z["patients_sous_seuil"].append(
            sum(1 for n in actifs if int(n["received"]) / int(n["newSent"]) < seuil) / len(actifs))
        z["patients_sous_seuil_sans_diversite"].append(
            sum(1 for n in actifs if int(n["rxNearest"]) / int(n["newSent"]) < seuil) / len(actifs))
        z["latence_moy_s"].append(st.mean(lats) if lats else float("nan"))
        tp = sorted(int(n["received"]) / int(n["newSent"]) for n in actifs)
        z["patient_p5"].append(tp[int(0.05 * (len(tp) - 1))] if tp else float("nan"))
        z["_runs"].append(run)

    ordre_z = cfg["experiences"]["multi_passerelles"]["zones"]
    zones_ordre = sorted(indic, key=lambda g: (ordre_z.index(g.split(" | ")[0]), g))
    lignes = []
    noms = ["taux_livraison", "taux_plus_proche", "gain_diversite_pts", "frac_multi",
            "facteur_duplication", "patients_sous_seuil", "patients_sous_seuil_sans_diversite",
            "latence_moy_s", "patient_p5"]
    for zone in zones_ordre:
        z = indic[zone]
        rr = next(r for r in runs if groupe(r) == zone)
        gws = [tuple(map(float, p.split(","))) for p in rr["gwPositions"].split(";")]
        # Espacement = distance de la passerelle centrale a la plus proche voisine.
        esp = min(math.hypot(x - gws[0][0], y - gws[0][1]) for x, y in gws[1:]) if len(gws) > 1 else float("nan")
        l = {"zone": zone, "repetitions": len(z["_runs"]), "gwPositions": rr["gwPositions"],
             "nDevices": rr["nDevices"], "espacement_m": round(esp, 1),
             # Pavage hexagonal : une passerelle par hexagone d'aire (racine(3)/2) s^2.
             "passerelles_par_100km2": round(100.0 * 2.0 / (math.sqrt(3.0) * (esp / 1000.0) ** 2), 3)
             if len(gws) == 7 else ""}
        for nm in noms:
            l[nm] = round(st.mean(z[nm]), 4)
            l[nm + "_ic95"] = round(ic95(z[nm]), 4)
        lignes.append(l)

    os.makedirs(a.out, exist_ok=True)
    chemin = os.path.join(a.out, f"multi_passerelles_{a.etiquette}.csv")
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)

    def fmt(l, nm, pct=True):
        v, h = l[nm], l[nm + "_ic95"]
        if pct:
            return f"{100 * v:5.1f} %" + ("" if math.isnan(h) else f" ± {100 * h:.1f}")
        return f"{v:5.2f}" + ("" if math.isnan(h) else f" ± {h:.2f}")

    print(f"Controles : {'OK' if not anomalies else str(len(anomalies)) + ' anomalie(s)'}"
          f"   (noeuds masques au-dela de l'horizon {d_hz / 1000:.1f} km : {masques})")
    for an in anomalies:
        print("  " + an)
    for l in lignes:
        print(f"\n== {l['zone']}  ({l['nDevices']} noeuds, espacement {l['espacement_m'] / 1000:.2f} km"
              + (f", {l['passerelles_par_100km2']} passerelles / 100 km2" if l['passerelles_par_100km2'] != "" else "")
              + f", {l['repetitions']} repetitions)")
        print(f"   livraison avec diversite      : {fmt(l, 'taux_livraison')}")
        print(f"   livraison plus proche seule   : {fmt(l, 'taux_plus_proche')}")
        print(f"   gain de diversite             : {l['gain_diversite_pts']:.1f} points"
              + ("" if math.isnan(l['gain_diversite_pts_ic95']) else f" ± {l['gain_diversite_pts_ic95']:.1f}"))
        print(f"   trames entendues par >= 2 GW  : {fmt(l, 'frac_multi')}")
        print(f"   facteur de duplication        : {fmt(l, 'facteur_duplication', pct=False)}")
        print(f"   patients sous {100 * seuil:.0f} %         : {fmt(l, 'patients_sous_seuil')} "
              f"(sans diversite {fmt(l, 'patients_sous_seuil_sans_diversite')})")
        print(f"   latence moyenne               : {fmt(l, 'latence_moy_s', pct=False)} s")
    # Synthese (decision U, corrigee apres la revue du 2026-10-27) : un espacement
    # tient si la borne basse IC 95 % de la livraison globale >= seuil ET si la
    # borne haute IC 95 % de la fraction de patients sous le seuil <= 1 - seuil
    # (moins de 5 % de patients mal servis). Le 5e percentile par patient,
    # moyenne des percentiles par run, est montre a cote.
    import re
    synth = defaultdict(list)
    for l in lignes:
        zone = l["zone"].split(" | ")[0]
        v = l["zone"].split(" | ")[1] if " | " in l["zone"] else ""
        m_e = re.search(r"espacement=([0-9.]+)", v)
        m_c = re.search(r"correlation=([0-9.]+)", v)
        if not m_e:
            continue
        synth[(zone, m_c.group(1) if m_c else "-")].append(
            (float(m_e.group(1)), l["taux_livraison"] - (0 if math.isnan(l["taux_livraison_ic95"]) else l["taux_livraison_ic95"]),
             l["patient_p5"], l["espacement_m"], l["passerelles_par_100km2"],
             l["patients_sous_seuil"] + (0 if math.isnan(l["patients_sous_seuil_ic95"]) else l["patients_sous_seuil_ic95"])))
    lignes_s = []
    print(f"\nSynthese : espacement maximal tenu (livraison globale, borne basse IC 95 >= {seuil}, "
          f"patients sous le seuil, borne haute IC 95 <= {1 - seuil:.2f}, 5e percentile patient >= {cfg['qualite_service'].get('plancher_p5_patient_espacement', 0)}, cellule sous l'horizon)")
    # Ajouts de la revue (point 5) : plancher sur le 5e percentile par patient,
    # et exclusion des espacements dont la cellule (rayon s / racine(3)) depasse
    # l'horizon radio : au-dela, les patients sont masques et la mesure n'a plus
    # de sens (plateau observe en lacustre).
    plancher = float(cfg["qualite_service"].get("plancher_p5_patient_espacement", 0.0))
    for (zone, rho), pts in synth.items():
        pts.sort()
        tenu = None
        limite = "critere"
        for f, bas, p5, esp, dens, sous_haut in pts:
            if esp / math.sqrt(3) > d_hz:
                limite = "horizon radio"
                break
            if bas >= seuil and sous_haut <= 1 - seuil + 1e-9 and p5 >= plancher:
                tenu = (f, esp, dens, p5)
            else:
                break
        lignes_s.append({"zone": zone, "correlation_sites": rho,
                         "espacement_max_tenu_rayons_fiables": tenu[0] if tenu else "",
                         "espacement_max_tenu_km": round(tenu[1] / 1000, 2) if tenu else "",
                         "passerelles_par_100km2": tenu[2] if tenu else "",
                         "p5_patient_a_cet_espacement": round(tenu[3], 3) if tenu else "",
                         "borne": ">=" if tenu and tenu[0] == pts[-1][0] else "",
                         "limite": limite})
        print(f"  {zone:<13} rho={rho:<4} " + (f"{lignes_s[-1]['borne']}{tenu[0]} r95 = {tenu[1] / 1000:.2f} km, "
              f"{tenu[2]} passerelles / 100 km2, p5 patient {100 * tenu[3]:.0f} %" if tenu else "aucun espacement tenu"))
    if lignes_s:
        with open(os.path.join(a.out, f"multi_passerelles_synthese_{a.etiquette}.csv"), "w", newline="",
                  encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(lignes_s[0].keys()))
            w.writeheader()
            w.writerows(lignes_s)
    print(f"\nFichier : {chemin}")


if __name__ == "__main__":
    main()
