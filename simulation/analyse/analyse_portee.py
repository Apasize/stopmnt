#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyse_portee.py

Analyse de l'experience de portee (section 5.4 du memoire).

Entree : un ou plusieurs fichiers noeuds_portee_*.csv ecrits par
l'orchestrateur (une ligne par noeud et par run), et le config.json.

Sorties, dans --out :
  - portee_bandes_<etiquette>.csv : par zone et par bande de distance, nombre de
    noeuds, taux moyen par noeud, intervalle de confiance a 95 % sur les
    repetitions, 5e percentile, fraction de noeuds sous le seuil, et une colonne
    au_dela_horizon (bandes masquees, gardees dans le CSV pour transparence).
  - portee_rayon_fiable_<etiquette>.csv : rayon fiable par zone.
  - portee_courbe_<etiquette>.png et .pdf : taux contre distance, un panneau
    par zone, arretee a l'horizon radio.

Definitions.
  Horizon radio        = limite geometrique, calculee ici et non simulee :
                         d_horizon_km = coef * (sqrt(h_passerelle_m) + sqrt(h_noeud_m)),
                         coef = 4,12 (refraction standard, Terre 4/3).
                         Coefficient et hauteurs lus dans le config.
  Masquage             = toute bande dont le bord exterieur depasse l'horizon est
                         ecartee avant le calcul du rayon fiable et le trace :
                         la simulation (log-distance + ombrage, sans horizon) y
                         fait recevoir des noeuds par extrapolation, ce qui est
                         non physique. Les noeuds au-dela ne sont pas traces.
  Taux d'un noeud      = trames recues / trames nouvelles.
  Taux moyen de bande  = moyenne des taux des noeuds de la bande (point de vue
                         patient : chaque patient compte pareil).
  Intervalle a 95 %    = intervalle de Student sur les moyennes de bande de
                         chaque repetition.
  Rayon fiable         = min(distance ou la borne basse de l'IC 95 % passe sous
                         le seuil, d_horizon). La distance retenue est le bord
                         interieur de la premiere bande, depuis la passerelle,
                         dont la borne basse est sous le seuil. Avec une seule
                         repetition il n'y a pas d'IC : on retombe sur la moyenne
                         et le CSV le signale.
  Controle du facteur  = taux moyen de la premiere bande au-dela de l'horizon,
  de rayon de test       avant masquage. S'il est encore haut, la portee radio
                         depasse l'horizon : c'est bien l'horizon qui limite.

Toutes les valeurs (seuil, nombre de bandes, coefficient, hauteurs) viennent du
config.
"""

import argparse
import csv
import json
import math
import os
import statistics as st
import sys
from collections import defaultdict


def d_horizon_m(cfg):
    """Horizon radio en metres, ou l'infini si l'horizon n'est pas pris en compte."""
    hz = cfg["radio"].get("horizon_radio", {})
    if not hz.get("actif", False):
        return float("inf")
    h_gw = float(cfg["passerelle"]["hauteur_antenne_m"])
    h_ed = float(cfg["noeud"]["hauteur_antenne_m"])
    return 1000.0 * float(hz["coefficient_km"]) * (math.sqrt(h_gw) + math.sqrt(h_ed))


def lire_noeuds(chemins):
    lignes = []
    for ch in chemins:
        with open(ch, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if int(r["newSent"]) == 0:
                    continue
                r["distance_m"] = float(r["distance_m"])
                r["radius"] = float(r["radius"])
                r["taux"] = int(r["received"]) / int(r["newSent"])
                r["runNumber"] = int(r["runNumber"])
                # Experience de sensibilite : une courbe par zone et par variante.
                r["zone_cle"] = r["zone"]
                v = r.get("variante", "base") or "base"
                if v != "base":
                    r["zone"] = f"{r['zone']} | {v}"
                lignes.append(r)
    return lignes


def percentile(valeurs, p):
    """Percentile par interpolation lineaire (methode usuelle, comme numpy)."""
    v = sorted(valeurs)
    if not v:
        return float("nan")
    k = (len(v) - 1) * p / 100.0
    i, frac = int(math.floor(k)), k - math.floor(k)
    return v[i] if i + 1 >= len(v) else v[i] + frac * (v[i + 1] - v[i])


def ic95(moyennes_par_run):
    """Demi-largeur de l'intervalle de Student a 95 % sur les repetitions."""
    n = len(moyennes_par_run)
    if n < 2:
        return float("nan")
    from scipy.stats import t
    return t.ppf(0.975, n - 1) * st.stdev(moyennes_par_run) / math.sqrt(n)


def analyser(lignes, cfg, zones_ordre):
    seuil = float(cfg["methode"]["seuil_acceptabilite_pdr"])
    nb_bandes = int(cfg["experiences"]["portee"]["nb_bandes_distance"])
    dh = d_horizon_m(cfg)
    tol = 1e-6 * (dh if math.isfinite(dh) else 1.0)  # bords de bande calcules en flottants
    bandes, rayons = [], []
    par_zone = defaultdict(list)
    for r in lignes:
        par_zone[r["zone"]].append(r)
    for zone in [z for z in zones_ordre if z in par_zone]:
        zl = par_zone[zone]
        rayon_test = max(r["radius"] for r in zl)
        largeur = rayon_test / nb_bandes
        runs = sorted({r["runNumber"] for r in zl})
        lignes_zone = []
        for b in range(nb_bandes):
            lo, hi = b * largeur, (b + 1) * largeur
            dans = [r for r in zl if lo <= r["distance_m"] < hi or (b == nb_bandes - 1 and r["distance_m"] == hi)]
            taux = [r["taux"] for r in dans]
            moy_runs = []
            for run in runs:
                tr = [r["taux"] for r in dans if r["runNumber"] == run]
                if tr:
                    moy_runs.append(st.mean(tr))
            moy = st.mean(taux) if taux else float("nan")
            demi = ic95(moy_runs)
            lignes_zone.append({
                "zone": zone, "bande": b, "d_min_m": round(lo, 1), "d_max_m": round(hi, 1),
                "d_centre_m": round((lo + hi) / 2, 1), "noeuds": len(taux), "repetitions": len(moy_runs),
                "taux_moyen": moy, "ic95_demi": demi,
                "ic95_bas": (moy - demi) if not math.isnan(demi) else float("nan"),
                "p5": percentile(taux, 5),
                "frac_sous_seuil": (sum(1 for x in taux if x < seuil) / len(taux)) if taux else float("nan"),
                "au_dela_horizon": hi > dh + tol,
            })
        bandes.extend(lignes_zone)

        # Masquage, puis rayon fiable sur la borne basse de l'IC.
        gardees = [l for l in lignes_zone if not l["au_dela_horizon"] and l["noeuds"] > 0]
        avec_ic = all(not math.isnan(l["ic95_bas"]) for l in gardees)
        critere = "borne basse IC 95" if avec_ic else "moyenne (une repetition, pas d'IC)"
        cassure = None
        for l in gardees:
            valeur = l["ic95_bas"] if avec_ic else l["taux_moyen"]
            if valeur < seuil:
                cassure = l["d_min_m"]
                break
        portee_radio = cassure if cassure is not None else float("inf")
        fiable = min(portee_radio, dh)
        if cassure is not None and cassure <= dh:
            limite = "propagation"
        elif math.isfinite(dh) and dh <= rayon_test:
            limite = "horizon"
        else:
            limite = "au moins (pas de cassure dans le rayon de test)"
            fiable = max(l["d_max_m"] for l in gardees)
        apres = [l for l in lignes_zone if l["au_dela_horizon"] and l["noeuds"] > 0]
        rayons.append({
            "zone": zone, "rayon_test_m": round(rayon_test, 1), "largeur_bande_m": round(largeur, 1),
            "repetitions": len(runs), "seuil": seuil, "critere": critere,
            "d_horizon_m": round(dh, 1) if math.isfinite(dh) else "",
            "rayon_fiable_m": round(fiable, 1), "limite": limite,
            "taux_premiere_bande_au_dela_horizon": round(apres[0]["taux_moyen"], 4) if apres else "",
        })
    return bandes, rayons


def tracer(bandes, rayons, lignes, cfg, zones_ordre, chemin_base):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Palette de reference (skill dataviz) : encre et serie 1, surface claire.
    SURFACE, ENCRE, ENCRE2, GRILLE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    SERIE, POINTS = "#2a78d6", "#a8a7a2"
    seuil = float(cfg["methode"]["seuil_acceptabilite_pdr"])
    dh = d_horizon_m(cfg)
    zones = [z for z in zones_ordre if any(b["zone"] == z for b in bandes)]

    ncol = min(3, len(zones))
    nlig = math.ceil(len(zones) / ncol)
    fig, axes = plt.subplots(nlig, ncol, figsize=(4.4 * ncol, 3.8 * nlig), sharey=True,
                             facecolor=SURFACE, squeeze=False)
    axes = list(axes.flat)
    for ax in axes[len(zones):]:
        ax.set_visible(False)

    for ax, zone in zip(axes, zones):
        ax.set_facecolor(SURFACE)
        zb = [b for b in bandes if b["zone"] == zone and b["noeuds"] > 0 and not b["au_dela_horizon"]]
        zr = next(r for r in rayons if r["zone"] == zone)
        # Pas de donnees tracees au-dela de l'horizon.
        zl = [r for r in lignes if r["zone"] == zone and r["distance_m"] <= dh]
        horizon_visible = math.isfinite(dh) and dh <= zr["rayon_test_m"]
        xmax = (dh if horizon_visible else zr["rayon_test_m"]) / 1000.0 * 1.04

        ax.scatter([r["distance_m"] / 1000 for r in zl], [100 * r["taux"] for r in zl],
                   s=6, color=POINTS, alpha=0.5, linewidths=0, zorder=2)
        x = [b["d_centre_m"] / 1000 for b in zb]
        y = [100 * b["taux_moyen"] for b in zb]
        if zb and all(not math.isnan(b["ic95_demi"]) for b in zb):
            ax.fill_between(x, [100 * b["ic95_bas"] for b in zb],
                            [min(100.0, 100 * (b["taux_moyen"] + b["ic95_demi"])) for b in zb],
                            color=SERIE, alpha=0.18, linewidth=0, zorder=3)
        ax.plot(x, y, color=SERIE, linewidth=2, marker="o", markersize=4, zorder=4)

        ax.axhline(100 * seuil, color=ENCRE2, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
        ax.text(0.02 * xmax, 100 * seuil - 7, f"seuil {100 * seuil:.0f} %", color=ENCRE2, fontsize=8)
        if horizon_visible:
            ax.axvline(dh / 1000, color=ENCRE, linewidth=1.4, linestyle=(0, (1, 2)), zorder=5)
            ax.text(dh / 1000 - 0.01 * xmax, 45, "horizon radio,\nlimite géométrique",
                    color=ENCRE, fontsize=8, ha="right", va="center",
                    bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1.5))
        rf = zr["rayon_fiable_m"] / 1000.0
        if zr["limite"] != "horizon":
            ax.axvline(rf, color=ENCRE, linewidth=1.2, zorder=1)

        cle, _, variante = zone.partition(" | ")
        libelle = cfg["zones"][cle]["libelle"].split(" (")[0] + (f", {variante}" if variante else "")
        prefixe = "rayon fiable >= " if zr["limite"].startswith("au moins") else "rayon fiable "
        suffixe = ", limité par l'horizon" if zr["limite"] == "horizon" else ""
        ax.set_title(f"{libelle}\n{prefixe}{rf:.1f} km{suffixe}", fontsize=10, color=ENCRE, loc="left")
        ax.set_xlim(0, xmax)
        ax.set_ylim(-3, 103)
        ax.grid(True, color=GRILLE, linewidth=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRILLE)
        ax.tick_params(colors=ENCRE2, labelsize=8)
        ax.set_xlabel("distance à la passerelle (km)", fontsize=8, color=ENCRE2)
    for i, ax in enumerate(axes[:len(zones)]):
        if i % ncol == 0:
            ax.set_ylabel("taux de livraison par patient (%)", fontsize=8, color=ENCRE2)

    reps = max(r["repetitions"] for r in rayons)
    note = ("Points gris : un patient. Courbe : moyenne par bande. "
            + (f"Bande bleue : IC 95 % sur {reps} répétitions." if reps > 1 else "Une seule répétition, pas d'IC.")
            + "\nTrait plein : rayon fiable. Aucune donnée tracée au-delà de l'horizon.")
    fig.text(0.01, 0.005, note, fontsize=8, color=ENCRE2)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(f"{chemin_base}.{ext}", dpi=200, facecolor=SURFACE)
    plt.close(fig)


def ecrire_csv(chemin, lignes):
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)


def main():
    ap = argparse.ArgumentParser(description="Analyse de l'experience de portee")
    ap.add_argument("--config", required=True)
    ap.add_argument("--noeuds", required=True, nargs="+", help="Fichier(s) noeuds_portee_*.csv")
    ap.add_argument("--out", default="./resultats")
    ap.add_argument("--etiquette", default="portee")
    a = ap.parse_args()

    cfg = json.load(open(os.path.expanduser(a.config), encoding="utf-8"))
    # Ordre des groupes : ordre des zones du config, puis ordre d'apparition des variantes.
    ordre_cfg = [z for z in cfg["zones"] if not z.startswith("_")]
    vus = list(dict.fromkeys(r["zone"] for r in lire_noeuds(a.noeuds)))
    zones_ordre = sorted(vus, key=lambda g: (ordre_cfg.index(g.split(" | ")[0]), vus.index(g)))
    lignes = lire_noeuds(a.noeuds)
    if not lignes:
        sys.exit("Aucune ligne exploitable.")
    bandes, rayons = analyser(lignes, cfg, zones_ordre)
    os.makedirs(a.out, exist_ok=True)
    ecrire_csv(os.path.join(a.out, f"portee_bandes_{a.etiquette}.csv"), bandes)
    ecrire_csv(os.path.join(a.out, f"portee_rayon_fiable_{a.etiquette}.csv"), rayons)
    tracer(bandes, rayons, lignes, cfg, zones_ordre, os.path.join(a.out, f"portee_courbe_{a.etiquette}"))

    # Vue texte.
    dh = d_horizon_m(cfg)
    print(f"Horizon radio : {dh / 1000:.2f} km")
    for r in rayons:
        print(f"\n== {r['zone']}  rayon de test {r['rayon_test_m'] / 1000:.1f} km, bandes de "
              f"{r['largeur_bande_m'] / 1000:.2f} km, {r['repetitions']} repetition(s), critere : {r['critere']}")
        print(f"   rayon fiable : {r['rayon_fiable_m'] / 1000:.2f} km, limite : {r['limite']}")
        if r["taux_premiere_bande_au_dela_horizon"] != "":
            print(f"   controle F : taux de la 1re bande au-dela de l'horizon, avant masquage = "
                  f"{100 * r['taux_premiere_bande_au_dela_horizon']:.1f} %")
        print("   bande (km)      noeuds  taux moyen  IC95 bas    p5     sous seuil")
        for b in bandes:
            if b["zone"] != r["zone"]:
                continue
            masque = "  [masquee]" if b["au_dela_horizon"] else ""
            if b["noeuds"] == 0:
                print(f"   {b['d_min_m'] / 1000:5.1f} - {b['d_max_m'] / 1000:5.1f}       0{masque}")
                continue
            bas = "   -   " if math.isnan(b["ic95_bas"]) else f"{100 * b['ic95_bas']:6.1f} %"
            print(f"   {b['d_min_m'] / 1000:5.1f} - {b['d_max_m'] / 1000:5.1f}  {b['noeuds']:6d}   "
                  f"{100 * b['taux_moyen']:6.1f} %  {bas}  {100 * b['p5']:5.1f} %  "
                  f"{100 * b['frac_sous_seuil']:5.1f} %{masque}")
    print(f"\nFichiers dans {a.out} : portee_bandes_{a.etiquette}.csv, "
          f"portee_rayon_fiable_{a.etiquette}.csv, portee_courbe_{a.etiquette}.png/.pdf")


if __name__ == "__main__":
    main()
