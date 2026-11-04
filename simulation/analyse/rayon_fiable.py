#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rayon_fiable.py

Rayon fiable d'une passerelle, recalcule depuis les donnees par noeud de
l'experience portee (revue critique du 2026-10-27).

Methode, par zone et variante :
  1. bandes de distance de largeur egale sur le rayon de test (--bandes) ;
  2. dans chaque bande et pour chaque repetition, taux moyen des patients de la
     bande ; puis moyenne sur les repetitions et demi-largeur de l'IC 95 %
     (Student, n-1 degres de liberte) ;
  3. borne basse = moyenne - demi-largeur ;
  4. rayon fiable = premier croisement descendant de la borne basse avec le
     seuil, interpole lineairement entre les centres des deux bandes qui
     l'encadrent ; rayon moyen = meme chose sur la moyenne ;
  5. bandes au-dela de l'horizon radio masquees ; si aucun croisement, le
     rayon est borne par l'horizon ou par le rayon de test.
L'ancienne valeur (debut de la premiere bande qui echoue, sans interpolation)
est rapportee a cote.

Sorties : rayon_fiable_interpole.csv (une ligne par zone et variante) et
rayon_fiable_bandes.csv (une ligne par bande : distance, noeuds, moyenne,
borne basse).
"""

import argparse
import csv
import math
import os
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "orchestrateur"))
import run_experiences as R  # noqa: E402


def ic95(v):
    if len(v) < 2:
        return float("nan")
    from scipy.stats import t
    return t.ppf(0.975, len(v) - 1) * st.stdev(v) / math.sqrt(len(v))


def croisement(xs, ys, seuil):
    """Premier croisement descendant de ys sous seuil, interpole ; None si aucun."""
    for i, y in enumerate(ys):
        if y < seuil:
            if i == 0:
                return xs[0]
            x0, y0, x1, y1 = xs[i - 1], ys[i - 1], xs[i], y
            return x0 + (y0 - seuil) / (y0 - y1) * (x1 - x0)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--noeuds", required=True, nargs="+")
    ap.add_argument("--bandes", type=int, default=40)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bootstrap", type=int, default=1000)
    a = ap.parse_args()
    cfg = R.charger_config(a.config)
    seuil = float(cfg["methode"]["seuil_acceptabilite_pdr"])
    dh = R.distance_horizon_m(cfg)

    taux = defaultdict(lambda: defaultdict(list))   # groupe -> run -> [(d, taux)]
    rayon_test = {}
    for ch in a.noeuds:
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            v = r.get("variante", "base") or "base"
            g = r["zone"] if v == "base" else f"{r['zone']} | {v}"
            sent = int(r["newSent"])
            if sent <= 0:
                continue
            taux[g][r["runNumber"]].append((float(r["distance_m"]), int(r["received"]) / sent))
            rayon_test[g] = max(rayon_test.get(g, 0.0), float(r["radius"]))

    lignes, bandes_out = [], []
    for g in sorted(taux):
        rt = rayon_test[g]
        w = rt / a.bandes
        xs, moy, bas = [], [], []
        for b in range(a.bandes):
            lo, hi = b * w, (b + 1) * w
            if hi > dh + 1e-6:
                break
            par_run = [st.mean([t for d, t in pts if lo <= d < hi]) for pts in taux[g].values()
                       if any(lo <= d < hi for d, _ in pts)]
            n = sum(1 for pts in taux[g].values() for d, _ in pts if lo <= d < hi)
            if not par_run:
                continue
            m = st.mean(par_run)
            h = ic95(par_run)
            xs.append((lo + hi) / 2)
            moy.append(m)
            bas.append(m - h)
            bandes_out.append({"groupe": g, "bandes": a.bandes, "d_min_m": round(lo), "d_max_m": round(hi),
                               "noeuds": n, "repetitions": len(par_run), "taux_moyen": round(m, 4),
                               "ic95_bas": round(m - h, 4)})
        # Bootstrap sur les repetitions : on retire les runs avec remise, on
        # recalcule la courbe moyenne par bande et son croisement a 95 %. La
        # borne basse a 2,5 % de cette distribution est le rayon fiable retenu
        # (independant de la largeur des bandes, contrairement a la borne
        # basse de l'IC par bande).
        import random
        rnd = random.Random(1)
        runs = list(taux[g].values())
        sommes = []   # par run : par bande (somme des taux, nb)
        for pts in runs:
            sb = [[0.0, 0] for _ in xs]
            for d, t in pts:
                b = int(d // w)
                if b < len(xs):
                    sb[b][0] += t
                    sb[b][1] += 1
            sommes.append(sb)
        boots = []
        for _ in range(a.bootstrap):
            tir = [sommes[rnd.randrange(len(sommes))] for _ in sommes]
            ys = []
            for b in range(len(xs)):
                tot = sum(x[b][0] for x in tir)
                nb = sum(x[b][1] for x in tir)
                ys.append(tot / nb if nb else float("nan"))
            c = croisement(xs, ys, seuil)
            boots.append(c if c is not None else min(dh, rt))
        boots.sort()
        r_boot_bas = boots[int(0.025 * len(boots))]
        r_boot_med = boots[len(boots) // 2]
        r_bas = croisement(xs, bas, seuil)
        r_moy = croisement(xs, moy, seuil)
        lim = "propagation"
        if r_bas is None:
            r_bas = min(dh, rt)
            lim = "horizon" if dh <= rt else "pas de croisement dans le rayon de test"
        # Ancienne methode : debut de la premiere bande dont la borne basse echoue.
        anc = next((xs[i] - w / 2 for i, y in enumerate(bas) if y < seuil), None)
        lignes.append({"groupe": g, "rayon_test_m": round(rt), "largeur_bande_m": round(w),
                       "rayon_fiable_retenu_m": round(r_boot_bas), "rayon_95_median_bootstrap_m": round(r_boot_med),
                       "rayon_fiable_borne_basse_m": round(r_bas), "rayon_moyenne_95_m": round(r_moy) if r_moy else "",
                       "ancienne_methode_m": round(anc) if anc is not None else "", "limite": lim})
    os.makedirs(a.out, exist_ok=True)
    for nom, rows in (("rayon_fiable_interpole.csv", lignes), ("rayon_fiable_bandes.csv", bandes_out)):
        with open(os.path.join(a.out, nom), "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            wr.writeheader()
            wr.writerows(rows)
    for l in lignes:
        print(f"{l['groupe']:<42} RETENU {l['rayon_fiable_retenu_m'] / 1000:6.2f} km (mediane {l['rayon_95_median_bootstrap_m'] / 1000:5.2f}) | borne basse IC {l['rayon_fiable_borne_basse_m'] / 1000:6.2f} km | "
              f"moyenne {(l['rayon_moyenne_95_m'] or 0) / 1000:6.2f} km | ancienne {(l['ancienne_methode_m'] or 0) / 1000:6.2f} km | {l['limite']}")


if __name__ == "__main__" and "--probit" not in sys.argv:
    main()


# -----------------------------------------------------------------------------
# Methode retenue apres la revue (2026-10-27) : ajustement probit sur les
# donnees par noeud, sans decoupage en bandes.
#   p(d) = pmax * Phi((a - log10 d) / s)
# pmax : plafond (pertes par collision, proche de 1) ; a et s : position et
# pente (ombrage log-normal en dB / 10n). Ajustement par maximum de
# vraisemblance binomiale (trames recues / emises par noeud). Rayon a 95 % =
# distance ou p(d) = 0,95 ; IC par bootstrap sur les repetitions.
# -----------------------------------------------------------------------------
def ajuste_probit(pts):
    import numpy as np
    from scipy.optimize import minimize
    from scipy.stats import norm
    d = np.array([max(p[0], 1.0) for p in pts])
    k = np.array([p[1] for p in pts], dtype=float)
    n = np.array([p[2] for p in pts], dtype=float)
    x = np.log10(d)

    def nll(th):
        pm = 1 / (1 + np.exp(-th[0]))
        a, s = th[1], np.exp(th[2])
        p = np.clip(pm * norm.cdf((a - x) / s), 1e-9, 1 - 1e-9)
        return -np.sum(k * np.log(p) + (n - k) * np.log(1 - p))
    th0 = [4.0, float(np.median(x)) + 0.3, np.log(0.2)]
    r = minimize(nll, th0, method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-6, "fatol": 1e-6})
    return 1 / (1 + np.exp(-r.x[0])), r.x[1], float(np.exp(r.x[2]))


def rayon_probit(pm, a, s, seuil):
    from scipy.stats import norm
    if pm <= seuil:
        return 0.0
    return 10 ** (a - s * norm.ppf(seuil / pm))


def main_probit():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--noeuds", required=True, nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bootstrap", type=int, default=200)
    a = ap.parse_args()
    import random
    cfg = R.charger_config(a.config)
    seuil = float(cfg["methode"]["seuil_acceptabilite_pdr"])
    dh = R.distance_horizon_m(cfg)
    donnees = defaultdict(lambda: defaultdict(list))
    rt = {}
    for ch in a.noeuds:
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            v = r.get("variante", "base") or "base"
            g = r["zone"] if v == "base" else f"{r['zone']} | {v}"
            n = int(r["newSent"])
            d = float(r["distance_m"])
            if n > 0 and d <= dh:
                donnees[g][r["runNumber"]].append((d, int(r["received"]), n))
            rt[g] = max(rt.get(g, 0.0), float(r["radius"]))
    lignes = []
    rnd = random.Random(1)
    for g in sorted(donnees):
        runs = list(donnees[g].values())
        tous = [p for pts in runs for p in pts]
        pm, aa, s = ajuste_probit(tous)
        r0 = min(rayon_probit(pm, aa, s, seuil), dh)
        boots = []
        for _ in range(a.bootstrap):
            tir = [p for _ in runs for p in runs[rnd.randrange(len(runs))]]
            b = ajuste_probit(tir)
            boots.append(min(rayon_probit(*b, seuil), dh))
        boots.sort()
        lignes.append({"groupe": g, "rayon_test_m": round(rt[g]), "plafond_livraison": round(pm, 4),
                       "rayon_95_m": round(r0), "rayon_fiable_m": round(boots[int(0.025 * len(boots))]),
                       "rayon_95_ic_haut_m": round(boots[int(0.975 * len(boots)) - 1]),
                       "limite": "horizon" if r0 >= dh - 1 else ("plafond sous 95 %" if pm <= seuil else "propagation")})
        l = lignes[-1]
        print(f"{g:<42} rayon fiable {l['rayon_fiable_m'] / 1000:6.2f} km | rayon 95 % {l['rayon_95_m'] / 1000:6.2f} km "
              f"(IC {l['rayon_fiable_m'] / 1000:.2f} a {l['rayon_95_ic_haut_m'] / 1000:.2f}) | plafond {pm:.3f} | {l['limite']}", flush=True)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "rayon_fiable_probit.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)


if __name__ == "__main__" and "--probit" in sys.argv:
    sys.argv.remove("--probit")
    main_probit()
