#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyse_capacite.py

Capacite d'une passerelle a qualite de service egale, et cout du mode confirme
(decision U de l'auteur, 2026-10-26). Entree du cout par patient (section 5.5).

Entrees : noeuds_<exp>_*.csv (une ligne par noeud et par run), ack_<exp>_*.csv
(percentiles du delai d'acquittement par run), config.json.

Criteres (bloc qualite_service du config) :
  routine (non confirmee) : taux de livraison GLOBAL du reseau sur la routine
      (trames recues / produites, tous patients), borne basse IC 95 % >= seuil.
      Garde-fou montre a cote : 5e percentile du taux par patient.
  confirme : 95e percentile du delai d'acquittement (production -> acquittement)
      sous le plafond, borne haute IC 95 %. Calcule sur les trames acquittees ;
      le taux d'acquittement est rapporte a cote. La version ou une trame non
      acquittee compte comme delai infini est aussi rapportee (p95_inf) : elle
      melange couverture et capacite (voir RETOUR_PROJET.md).
  Par mode :
      tout_non_confirme : critere routine ;
      mixte             : critere routine ET critere confirme sur l'alerte ;
      tout_confirme     : critere confirme sur la routine et l'alerte.
Capacite = plus grand palier tenu tel que tous les paliers inferieurs tiennent,
plus le croisement interpole (logarithmique) du critere principal.

Vue par patient, a cote du global : mediane, 5e percentile, pire patient,
courbe cumulative des taux par patient, taux par tranche de distance ; pour le
confirme, delai moyen et maximal par patient ; energie par patient et par jour.

Sorties dans --out : capacite_points_<etiq>.csv, capacite_<etiq>.csv,
capacite_distance_<etiq>.csv, figures capacite_*_<etiq>.png/.pdf.
"""

import argparse
import csv
import json
import math
import os
import statistics as st
from collections import defaultdict

INF = float("inf")


def ic95(v):
    v = [x for x in v if not math.isnan(x) and not math.isinf(x)]
    if len(v) < 2:
        return float("nan")
    from scipy.stats import t
    return t.ppf(0.975, len(v) - 1) * st.stdev(v) / math.sqrt(len(v))


def moy(v):
    v = [x for x in v if not math.isnan(x)]
    if not v:
        return float("nan")
    if any(math.isinf(x) for x in v):
        return INF
    return st.mean(v)


def pct(v, p):
    v = sorted(v)
    if not v:
        return float("nan")
    k = (len(v) - 1) * p / 100.0
    i = int(k)
    if i + 1 >= len(v) or math.isinf(v[i + 1]):
        return v[min(len(v) - 1, math.ceil(k))]
    return v[i] + (k - i) * (v[i + 1] - v[i])


def mode_de(variante):
    import re
    m = re.search(r"mode=([a-z_0-9]+)", variante)
    return m.group(1) if m else "mixte"


def famille(mode):
    """Mode de base, sans l'option de fenetre d'accuse (_rx2)."""
    return mode.replace("_rx2", "")


def fval(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def main():
    ap = argparse.ArgumentParser(description="Analyse de capacite et du cout du confirme")
    ap.add_argument("--config", required=True)
    ap.add_argument("--noeuds", required=True, nargs="+")
    ap.add_argument("--ack", nargs="*", default=[])
    ap.add_argument("--out", default="./resultats")
    ap.add_argument("--etiquette", default="capacite")
    ap.add_argument("--jours", type=float, default=None,
                    help="Duree simulee en jours si elle differe du config (ex. simulation longue de 7 jours)")
    ap.add_argument("--palier-cdf", type=int, default=1600,
                    help="Nombre de patients pour la courbe cumulative par patient")
    a = ap.parse_args()

    cfg = json.load(open(os.path.expanduser(a.config), encoding="utf-8"))
    qs = cfg["qualite_service"]
    seuil = float(qs.get("seuil_livraison_reseau", qs["seuil_taux_patient"]))
    plafond = float(qs.get("plafond_delai_acquittement_s", 60.0))
    nb_bandes = 5

    acks = defaultdict(dict)
    for ch in a.ack:
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            acks[(r["zone"], r["variante"], int(r["nDevices"]), r["runNumber"])][r["type"]] = r

    def jours(exp_nom):
        if a.jours:
            return a.jours
        e = cfg["experiences"].get(exp_nom, {})
        base = cfg["experiences"].get(e.get("experience_de_base", ""), {})
        return float(e.get("duree_simulee_jours", base.get("duree_simulee_jours",
                                                             cfg["methode"]["duree_simulee_jours"])))

    pts = defaultdict(lambda: defaultdict(list))
    patients = defaultdict(list)          # (zone, var, n) -> taux par patient, au palier de la CDF
    distance = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # (zone, var, n) -> bande -> [recu, produit]

    def traiter(cle, nds):
        zone, var, n, run = cle
        rayon = float(nds[0]["radius"])
        mode = mode_de(var)
        nj = jours(nds[0]["exp"])
        prod_r = recu_r = 0
        taux_p, e_p, dmoy_p, dmax_p = [], [], [], []
        for r in nds:
            g = int(r["genRoutine"])
            rec = int(r["received"]) - int(r["alertDelivered"])
            prod_r += g
            recu_r += rec
            if g > 0:
                taux_p.append(rec / g)
            e = fval(r.get("energy_J"))
            if not math.isnan(e) and e >= 0:
                e_p.append(e / nj)
            if famille(mode) == "tout_confirme" and int(r.get("confRoutineAcked") or 0) > 0:
                dmoy_p.append(fval(r["confRoutineDelayMean_s"]))
                dmax_p.append(fval(r["confRoutineDelayMax_s"]))
            b = min(nb_bandes - 1, int(nb_bandes * float(r["distance_m"]) / max(rayon, 1.0)))
            distance[(zone, var, n)][b][0] += rec
            distance[(zone, var, n)][b][1] += g
        ga = sum(int(r["genAlert"]) for r in nds)
        p = pts[(zone, var, n)]
        p["pdr_routine"].append(recu_r / prod_r if prod_r else float("nan"))
        p["patient_mediane"].append(pct(taux_p, 50))
        p["patient_p5"].append(pct(taux_p, 5))
        p["patient_min"].append(min(taux_p) if taux_p else float("nan"))
        p["alerte_livree"].append(sum(int(r["alertDelivered"]) for r in nds) / ga if ga else float("nan"))
        p["energie_j_jour"].append(st.mean(e_p) if e_p else float("nan"))
        p["energie_j_jour_p95"].append(pct(e_p, 95) if e_p else float("nan"))
        p["energie_mj_par_trame_livree"].append(
            1000.0 * sum(e_p) * nj / recu_r if e_p and recu_r else float("nan"))
        p["delai_patient_moy_s"].append(st.mean(dmoy_p) if dmoy_p else float("nan"))
        p["delai_patient_max_p95_s"].append(pct(dmax_p, 95) if dmax_p else float("nan"))
        for typ in ("routine", "alerte"):
            ak = acks.get(cle, {}).get(typ)
            if ak:
                p[f"{typ}_taux_acquit"].append(int(ak["nAcked"]) / int(ak["nConf"]) if int(ak["nConf"]) else float("nan"))
                p[f"{typ}_p95_acquit_s"].append(fval(ak["p95Acquittees_s"]))
                p[f"{typ}_p95_inf_s"].append(fval(ak["p95_s"]))
                p[f"{typ}_p50_s"].append(fval(ak["p50_s"]))
        # Consignes v6 : exigences de 72 h (routine, par patient) et de 15 min
        # (alertes), alarmes du pont, remontee, recapitulatif.
        if "readingsEligible" in nds[0] and nds[0]["readingsEligible"] not in ("", None):
            el = [int(r["readingsEligible"]) for r in nds]
            ok = [int(r["readingsOk72h"]) for r in nds]
            p["livraison_72h"].append(sum(ok) / sum(el) if sum(el) else float("nan"))
            pat = [o / e for o, e in zip(ok, el) if e > 0]
            p["patients_72h_ok"].append(sum(1 for x in pat if x >= 0.95) / len(pat) if pat else float("nan"))
            na = sum(int(r["alertsCounted"]) for r in nds)
            p["alerte_15min"].append(sum(int(r["alertsOk15"]) for r in nds) / na if na else float("nan"))
            ni = sum(int(r["alertsIndoor"]) for r in nds)
            p["alerte_interieur_15min"].append(sum(int(r["alertsIndoorOk15"]) for r in nds) / ni if ni else float("nan"))
            al = sum(int(r["alarms"]) for r in nds)
            unc = sum(int(r["unconfirmedNoAlarm"]) for r in nds)
            p["alarmes_detectees"].append(al / (al + unc) if (al + unc) else float("nan"))
            p["fausses_alarmes"].append(sum(int(r["falseAlarms"]) for r in nds) / na if na else float("nan"))
            ra = sum(int(r["recapAttempts"]) for r in nds)
            p["recap_reussis"].append(sum(int(r["recapOk"]) for r in nds) / ra if ra else float("nan"))
            p["alarmes_techniques_par_patient_jour"].append(
                sum(int(r["techAlarms"]) for r in nds) / (len(nds) * nj))
        ar = acks.get(cle, {}).get("alerte_reseau")
        if ar:
            p["alerte_delai_p50_s"].append(fval(ar["p50_s"]))
            p["alerte_delai_p95_s"].append(fval(ar["p95_s"]))
            p["alerte_delai_p99_s"].append(fval(ar["p99_s"]))
        rm = acks.get(cle, {}).get("remontee")
        if rm and int(rm["nConf"]):
            p["remontee_trop_tard"].append(int(rm["nFail"]) / int(rm["nConf"]))
            p["remontee_rx1"].append(int(rm["nAcked"]) / int(rm["nConf"]))
        if n == a.palier_cdf:
            patients[(zone, var, n)].extend(taux_p)

    # Lecture en flux : les lignes d'un run sont contigues dans le fichier (ecrites
    # d'un bloc par l'orchestrateur). On traite chaque run puis on le libere.
    for ch in a.noeuds:
        cle_cour, bloc = None, []
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            cle = (r["zone"], r["variante"], int(r["nDevices"]), r["runNumber"])
            if cle != cle_cour:
                if bloc:
                    traiter(cle_cour, bloc)
                cle_cour, bloc = cle, []
            bloc.append(r)
        if bloc:
            traiter(cle_cour, bloc)

    noms = ["pdr_routine", "patient_mediane", "patient_p5", "patient_min", "alerte_livree",
            "routine_taux_acquit", "routine_p95_acquit_s", "routine_p95_inf_s", "routine_p50_s",
            "alerte_taux_acquit", "alerte_p95_acquit_s", "alerte_p95_inf_s", "alerte_p50_s",
            "delai_patient_moy_s", "delai_patient_max_p95_s",
            "energie_j_jour", "energie_j_jour_p95", "energie_mj_par_trame_livree",
            "livraison_72h", "patients_72h_ok", "alerte_15min", "alerte_interieur_15min", "alarmes_detectees",
            "fausses_alarmes", "recap_reussis", "alarmes_techniques_par_patient_jour",
            "alerte_delai_p50_s", "alerte_delai_p95_s", "alerte_delai_p99_s", "remontee_trop_tard", "remontee_rx1"]
    lignes = []
    for (zone, var, n), p in sorted(pts.items()):
        l = {"zone": zone, "variante": var, "mode": mode_de(var), "nDevices": n,
             "repetitions": len(p["pdr_routine"])}
        for nm in noms:
            l[nm] = moy(p.get(nm, []))
            l[nm + "_ic95"] = ic95(p.get(nm, []))
        bas = lambda nm: l[nm] - (0 if math.isnan(l[nm + "_ic95"]) else l[nm + "_ic95"])
        haut = lambda nm: l[nm] + (0 if math.isnan(l[nm + "_ic95"]) else l[nm + "_ic95"])
        crit_routine = bas("pdr_routine") >= seuil
        if famille(l["mode"]) == "mixte_recap" and not math.isnan(l.get("livraison_72h", float("nan"))):
            # Recapitulatif : la routine est jugee sur la livraison en 72 h.
            crit_routine = bas("livraison_72h") >= seuil
        crit_alerte = not (haut("alerte_p95_acquit_s") > plafond)    # nan (pas d'alerte confirmee) = tenu
        crit_conf_routine = not (haut("routine_p95_acquit_s") > plafond)
        if famille(l["mode"]) == "tout_non_confirme":
            l["tient"] = crit_routine
        elif famille(l["mode"]) in ("mixte", "mixte_recap"):
            l["tient"] = crit_routine and crit_alerte
        else:
            l["tient"] = crit_conf_routine and crit_alerte
        l["critere_routine"], l["critere_delai_alerte"], l["critere_delai_routine"] = \
            crit_routine, crit_alerte, crit_conf_routine
        lignes.append(l)

    # Capacite par zone et variante.
    capa = []
    groupes = defaultdict(list)
    for l in lignes:
        groupes[(l["zone"], l["variante"])].append(l)
    ordre = [z for z in cfg["zones"] if not z.startswith("_")]
    for (zone, var), ls in sorted(groupes.items(), key=lambda kv: (ordre.index(kv[0][0]), kv[0][1])):
        ls.sort(key=lambda l: l["nDevices"])
        cap, borne = 0, ""
        for l in ls:
            if l["tient"]:
                cap = l["nDevices"]
            else:
                break
        if ls and cap == ls[-1]["nDevices"] and ls[-1]["tient"]:
            borne = ">="
        if not ls[0]["tient"]:
            borne = "<"
            cap = ls[0]["nDevices"]
        mode = ls[0]["mode"]
        capa.append({"zone": zone, "variante": var, "mode": mode, "capacite_palier": cap, "borne": borne,
                     "capacite_interpolee_livraison": croisement(
                         ls, "livraison_72h" if famille(mode) == "mixte_recap" else "pdr_routine", seuil, monte=False),
                     "capacite_interpolee_delai_routine": croisement(ls, "routine_p95_acquit_s", plafond, monte=True),
                     "capacite_interpolee_delai_alerte": croisement(ls, "alerte_p95_acquit_s", plafond, monte=True),
                     "paliers": " ".join(str(l["nDevices"]) for l in ls),
                     "repetitions": ls[0]["repetitions"]})

    dist_rows = []
    for (zone, var, n), bandes in sorted(distance.items()):
        for b in range(nb_bandes):
            rec, prod = bandes[b]
            dist_rows.append({"zone": zone, "variante": var, "nDevices": n,
                              "bande_rayon": f"{b / nb_bandes:.1f}-{(b + 1) / nb_bandes:.1f}",
                              "taux_routine": round(rec / prod, 4) if prod else ""})

    os.makedirs(a.out, exist_ok=True)
    for nom, rows in ((f"capacite_points_{a.etiquette}.csv", lignes), (f"capacite_{a.etiquette}.csv", capa),
                      (f"capacite_distance_{a.etiquette}.csv", dist_rows)):
        with open(os.path.join(a.out, nom), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    tracer(lignes, patients, cfg, seuil, plafond, a.palier_cdf, a.out, a.etiquette)

    print(f"Criteres : livraison routine globale >= {seuil} (borne basse IC 95) ; "
          f"p95 du delai d'acquittement (trames acquittees) <= {plafond:.0f} s (borne haute IC 95)")
    for c in capa:
        def fi(x):
            return "-" if x is None else (f">{x[1:]}" if isinstance(x, str) else f"{x:.0f}")
        print(f"  {c['zone']:<13} {c['variante']:<34} capacite {c['borne']}{c['capacite_palier']:>5}"
              f" | croisements : livraison {fi(c['capacite_interpolee_livraison'])}, "
              f"delai routine {fi(c['capacite_interpolee_delai_routine'])}, "
              f"delai alerte {fi(c['capacite_interpolee_delai_alerte'])}")
    print("\nDetail par palier :")
    for l in lignes:
        def f(nm, pc=True, d=1):
            v, h = l[nm], l[nm + "_ic95"]
            if math.isnan(v):
                return "-"
            if math.isinf(v):
                return "inf"
            s = f"{100 * v:.{d}f}" if pc else f"{v:.{d}f}"
            return s + ("" if math.isnan(h) else f"±{(100 * h if pc else h):.{d}f}")
        print(f"  {l['zone']:<13} {l['variante']:<34} n={l['nDevices']:>5} livr.routine {f('pdr_routine')}% "
              f"p5 patient {f('patient_p5')}% min {f('patient_min', d=0)}% | "
              f"acq.routine {f('routine_taux_acquit')}% p95 {f('routine_p95_acquit_s', False, 0)} s | "
              f"acq.alerte {f('alerte_taux_acquit')}% p95 {f('alerte_p95_acquit_s', False, 0)} s | "
              f"E {f('energie_j_jour', False, 3)} J/j  {f('energie_mj_par_trame_livree', False, 1)} mJ/trame  "
              f"{'TIENT' if l['tient'] else 'ne tient pas'}")


def croisement(ls, nm, cible, monte):
    """Nombre de patients ou la moyenne de nm croise la cible, interpolation
    lineaire en log(n). monte : la metrique croit avec la charge (delai).
    Renvoie None si pas de croisement, '>n' si jamais franchi."""
    pts = [(l["nDevices"], l[nm]) for l in ls if not math.isnan(l[nm])]
    if not pts:
        return None
    mauvais = (lambda v: v > cible) if monte else (lambda v: v < cible)
    if mauvais(pts[0][1]):
        return 0
    for (n1, v1), (n2, v2) in zip(pts, pts[1:]):
        if mauvais(v2):
            if math.isinf(v2):
                return n1
            t = (cible - v1) / (v2 - v1)
            return math.exp(math.log(n1) + t * (math.log(n2) - math.log(n1)))
    return f">{pts[-1][0]}"


def tracer(lignes, patients, cfg, seuil, plafond, palier_cdf, out, etiq):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    SURFACE, ENCRE, ENCRE2, GRILLE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    COUL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
    MARQ = ["o", "s", "^", "D", "v"]
    zones = [z for z in cfg["zones"] if not z.startswith("_") and any(l["zone"] == z for l in lignes)]
    variantes = sorted({l["variante"] for l in lignes},
                       key=lambda v: (["tout_non_confirme", "mixte", "mixte_recap", "tout_confirme"].index(famille(mode_de(v))), v))
    lib = lambda v: (v.replace("mode=", "").replace("_rx2", ", choix RX2").replace("tout_non_confirme", "tout non confirmé")
                     .replace("tout_confirme", "tout confirmé").replace("intensif=", "intensifs ")
                     .replace("0.", "0,"))

    def cadre(ax, titre):
        ax.set_facecolor(SURFACE)
        ax.set_title(titre, fontsize=10, color=ENCRE, loc="left")
        ax.grid(True, color=GRILLE, linewidth=0.6)
        ax.set_axisbelow(True)
        for s_ in ("top", "right"):
            ax.spines[s_].set_visible(False)
        for s_ in ("left", "bottom"):
            ax.spines[s_].set_color(GRILLE)
        ax.tick_params(colors=ENCRE2, labelsize=8)

    def grille(nb):
        ncol = min(3, nb)
        nlig = math.ceil(nb / ncol)
        fig, axes = plt.subplots(nlig, ncol, figsize=(4.4 * ncol, 3.6 * nlig), facecolor=SURFACE, squeeze=False)
        axes = list(axes.flat)
        for ax in axes[nb:]:
            ax.set_visible(False)
        return fig, axes

    def courbes(nom_fig, metrique, ylabel, ligne_ref, en_pct, logy=False, filtre=None, note=""):
        fig, axes = grille(len(zones))
        trace = False
        for ax, zone in zip(axes, zones):
            cadre(ax, cfg["zones"][zone]["libelle"].split(" (")[0])
            for i, var in enumerate(variantes):
                if filtre and not filtre(var):
                    continue
                ls = sorted([l for l in lignes if l["zone"] == zone and l["variante"] == var
                             and not math.isnan(l[metrique]) and not math.isinf(l[metrique])],
                            key=lambda l: l["nDevices"])
                if not ls:
                    continue
                trace = True
                k = 100 if en_pct else 1
                x = [l["nDevices"] for l in ls]
                y = [k * l[metrique] for l in ls]
                ax.plot(x, y, color=COUL[i % 5], marker=MARQ[i % 5], markersize=5, linewidth=2, label=lib(var))
                h = [l[metrique + "_ic95"] for l in ls]
                if all(not math.isnan(v) for v in h):
                    ax.fill_between(x, [k * (l[metrique] - l[metrique + "_ic95"]) for l in ls],
                                    [k * (l[metrique] + l[metrique + "_ic95"]) for l in ls],
                                    color=COUL[i % 5], alpha=0.15, linewidth=0)
            if ligne_ref is not None:
                ax.axhline(ligne_ref, color=ENCRE2, linewidth=1, linestyle=(0, (4, 3)))
            ax.set_xscale("log")
            if logy:
                ax.set_yscale("log")
            ax.set_xlabel("patients par passerelle", fontsize=8, color=ENCRE2)
            ax.set_ylabel(ylabel, fontsize=8, color=ENCRE2)
        if not trace:
            plt.close(fig)
            return
        axes[0].legend(fontsize=7, frameon=False)
        fig.text(0.01, 0.005, note + " Bandes : IC 95 % sur les répétitions. Cellule isolée, patients dans le "
                 "rayon fiable théorique.", fontsize=8, color=ENCRE2)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        for ext in ("png", "pdf"):
            fig.savefig(os.path.join(out, f"{nom_fig}_{etiq}.{ext}"), dpi=200, facecolor=SURFACE)
        plt.close(fig)

    courbes("capacite_livraison", "pdr_routine", "livraison globale de la routine (%)", 100 * seuil, True,
            note=f"Tirets : seuil {100 * seuil:.0f} %.")
    courbes("capacite_p5_patient", "patient_p5", "5e percentile du taux par patient (%)", 100 * seuil, True,
            note="Garde-fou par patient.")
    courbes("capacite_delai_acquittement", "routine_p95_acquit_s", "p95 délai d'acquittement routine (s)",
            plafond, False, logy=True, filtre=lambda v: famille(mode_de(v)) == "tout_confirme",
            note=f"Tirets : plafond {plafond:.0f} s. Trames acquittées.")
    courbes("capacite_delai_alerte", "alerte_p95_acquit_s", "p95 délai d'acquittement alerte (s)", plafond, False,
            logy=True, filtre=lambda v: mode_de(v) != "tout_non_confirme",
            note=f"Tirets : plafond {plafond:.0f} s. Trames acquittées.")
    courbes("capacite_energie", "energie_j_jour", "énergie radio par patient (J/jour)", None, False,
            note="Modèle d'énergie du module (courants SX1272).")

    # Courbe cumulative des taux par patient, au palier choisi.
    fig, axes = grille(len(zones))
    trace = False
    for ax, zone in zip(axes, zones):
        cadre(ax, cfg["zones"][zone]["libelle"].split(" (")[0] + f", {palier_cdf} patients")
        for i, var in enumerate(variantes):
            v = sorted(patients.get((zone, var, palier_cdf), []))
            if not v:
                continue
            trace = True
            y = [(j + 1) / len(v) for j in range(len(v))]
            ax.step([100 * x for x in v], y, where="post", color=COUL[i % 5], linewidth=2, label=lib(var))
        ax.axvline(100 * seuil, color=ENCRE2, linewidth=1, linestyle=(0, (4, 3)))
        ax.set_xlabel("taux de livraison de la routine par patient (%)", fontsize=8, color=ENCRE2)
        ax.set_ylabel("fraction cumulée des patients", fontsize=8, color=ENCRE2)
    if trace:
        axes[0].legend(fontsize=7, frameon=False)
        fig.text(0.01, 0.005, "Toutes répétitions confondues. Fenêtre de 2 jours : le taux par patient est "
                 "quantifié (environ 8 trames de routine).", fontsize=8, color=ENCRE2)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        for ext in ("png", "pdf"):
            fig.savefig(os.path.join(out, f"capacite_cdf_patients_{etiq}.{ext}"), dpi=200, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    main()
