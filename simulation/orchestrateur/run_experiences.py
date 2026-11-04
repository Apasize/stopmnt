#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_experiences.py

Orchestrateur Monte-Carlo de la simulation LoRaWAN STOP-MNT.

Role : lire le config.json (la source de verite), balayer le nombre de noeuds
par type de zone, repeter chaque point plusieurs fois avec une graine
differente, appeler le modele ns-3, recuperer la ligne CSV et les lignes par
noeud de chaque run, et tout ecrire dans des fichiers de resultats. Le modele
ns-3 ne connait rien de tout ca : il recoit des parametres, il rend des lignes.
Toute la logique d'experience vit ici.

Principe de separation :
  config.json      -> les valeurs
  modele ns-3      -> une cellule, un run, des lignes
  cet orchestrateur-> quels runs lancer, dans quel ordre, quand s'arreter
  scripts d'analyse-> moyennes, intervalles, courbes (dossier analyse/)

Propagation par zone (depuis le 2026-10-25) : chaque zone porte son ancrage
(distance_reference_m, perte_reference_db), son exposant, son ombrage et
eventuellement un terme de vegetation UIT-R P.833. Tout est passe au modele.

Deux bras :
  'avec'  -> ombrage au sigma de la zone
  'sans'  -> meme binaire, ombrage a 0 (controle). Le binaire historique
             lorawan-cell ne connait pas l'ancrage par zone et n'est plus appele.

Experiences (voir config, bloc experiences) :
  capacite                 balayage du nombre de noeuds, une passerelle
  portee                   placement jusqu'au-dela de la portee, analyse par bande
  multi_passerelles        plusieurs passerelles, diversite et deduplication
  sensibilite_propagation  exposant ou perte de reference balayes sur la plage
                           de chaque zone, a partir d'une experience de base

Les resultats sont ecrits au fur et a mesure, un run par ligne, pour qu'une
interruption ne fasse pas tout perdre.

Usage typique :
  python3 run_experiences.py --config ../config/config.json \\
      --ns3-dir ~/ns-3.48 --shadow-bin lorawan-cell-shadow-confirmed \\
      --exp portee --repetitions 5 --out ../resultats/essai
"""

import argparse
import copy
import csv
import json
import math
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from statistics import NormalDist

CSV_PREFIX = "CSV;"
NODE_PREFIX = "NODE;"

COLONNES = [
    "bras", "exp", "zone", "variante", "nDevices", "pathLossExp", "refDist", "refLoss",
    "excessLossDb", "shadowingSigma", "radius", "gwPositions", "runNumber",
    "sent", "received", "pdr",
    "phyTotal", "phyRecv", "phyInterf", "phyNoRecv", "phyUnderSens", "phyLostTx",
    "confirmed", "nbTrans", "acked", "cpsr",
    "nGateways", "gwReceptions", "multiGwPackets", "nsArrivals",
]

COLONNES_NOEUDS = [
    "bras", "exp", "zone", "variante", "nDevices", "runNumber", "confirmed", "radius",
    "pathLossExp", "refDist", "refLoss", "excessLossDb",
    "nodeId", "distance_m", "sf", "newSent", "txTotal", "received", "acked",
    "airtime_s", "gwNearest", "gwReceptions", "multiGw", "latencyMean_s", "latencyMax_s",
    "rxNearest", "profile", "genRoutine", "genAlert", "alertNew", "alertDelivered",
    "alertAcked", "alertLatUpMax_s", "alertRttMean_s", "alertRttMax_s",
    "mobile", "readingsGen", "readingsDelivered", "readingsDropped", "readingLatMean_s", "readingLatMax_s",
    "confRoutineGen", "confRoutineAcked", "confRoutineFail", "confRoutineDelayMean_s", "confRoutineDelayMax_s",
    "energy_J",
    # Consignes v6 (fin de ligne NODE) : exigences 72 h et 15 min, alarmes, recapitulatif.
    "readingsEligible", "readingsOk72h", "alertsCounted", "alertsOk15", "alarms", "falseAlarms",
    "unconfirmedNoAlarm", "alertsIndoor", "alertsIndoorOk15", "recapAttempts", "recapOk", "techAlarms", "resent",
    "alertsOk5", "trueAlarms", "detectSum_s", "detectMax_s",
]

COLONNES_ACK = [
    "bras", "exp", "zone", "variante", "nDevices", "runNumber", "type", "nConf", "nAcked", "nFail", "nOpen",
    "p50_s", "p95_s", "p99_s", "p95Acquittees_s", "max_s", "gardes", "remisEnFile",
]
ACK_PREFIX = "ACK;"


def charger_config(chemin):
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


# -----------------------------------------------------------------------------
# Propagation par zone, lue dans le config.
# -----------------------------------------------------------------------------

def densite_vegetation(zone):
    """Densite de vegetation de la zone (variante balayee, sinon densite centrale), 0 si aucune."""
    veg = zone.get("vegetation")
    if not veg or not veg.get("actif", True):
        return 0.0
    return float(veg.get("densite", veg.get("densite_centrale", 1.0)))


def params_vegetation(cfg, zone):
    """(Am, coef, exposant f, exposant d) du terme de vegetation, Am deja multiplie
    par la densite ; Am = 0 si la zone n'a pas de vegetation."""
    veg = zone.get("vegetation")
    k = densite_vegetation(zone)
    if k <= 0.0:
        return 0.0, 0.0, 0.3, 0.6
    f_mhz = float(cfg["radio"]["frequence_mhz"])
    am = k * float(veg["A1_db"]) * f_mhz ** float(veg["alpha"])
    return am, k * float(veg["coef_croissance_db"]), float(veg["exposant_frequence"]), float(veg["exposant_distance"])


def perte_vegetation_db(cfg, zone, d_m=None):
    """Terme de vegetation a la distance d (comptage unique) :
    A(d) = Am [1 - exp(-c f^a d^b / Am)], meme formule que VegetationLossModel.
    Sans distance, rend la saturation Am."""
    am, coef, fa, db = params_vegetation(cfg, zone)
    if am <= 0.0:
        return 0.0
    if d_m is None:
        return am
    a0 = coef * float(cfg["radio"]["frequence_mhz"]) ** fa * max(d_m, 0.0) ** db
    return am * (1.0 - math.exp(-a0 / am))


def p2109_mediane_db(f_ghz, cfg=None):
    """Perte d'entree dans un batiment, mediane (P = 0,5), incidence horizontale,
    UIT-R P.2109 (coefficients repris dans 3GPP TR 38.811 tableau 6.6.3-1) :
      L_h = r + s log f + t (log f)^2 ; mu1 = L_h (theta = 0) ;
      mu2 = w + x log f ; a la mediane A = mu1, B = mu2 ;
      L = 10 log10(10^(A/10) + 10^(B/10) + 10^(C/10)), C = -3 dB.
    Coefficients du config (batiment traditionnel par defaut)."""
    c = (cfg or {}).get("noeud", {}).get("interieur", {}).get("p2109_traditionnel",
                                                               {"r": 12.64, "s": 3.72, "t": 0.96, "w": 9.1, "x": -3.0})
    lf = math.log10(f_ghz)
    a = c["r"] + c["s"] * lf + c["t"] * lf * lf
    b = c["w"] + c["x"] * lf
    return 10.0 * math.log10(10 ** (a / 10.0) + 10 ** (b / 10.0) + 10 ** (-3.0 / 10.0))


def perte_interieur_db(cfg, zone):
    """Perte en interieur prise dans le dimensionnement : variante portee par la
    zone (balayage), sinon valeur du config (consignes v6, point 2)."""
    if "interieur_perte_db" in zone:
        return float(zone["interieur_perte_db"])
    it = cfg.get("noeud", {}).get("interieur", {})
    return float(it.get("perte_dimensionnement_db", 0.0))


def reference_effective(cfg, zone):
    """(d0, PL(d0)) passes au log-distance de ns-3, qui garde la perte constante
    sous d0. Consignes v6 : avec la perte en interieur, des cellules passent
    sous 1 km ; la loi de la zone est extrapolee jusqu'a
    radio.distance_reference_extrapolee_m (meme pente, hors du domaine mesure
    par les campagnes sources : PROPOSITION a valider). Sans cette cle : d0 de
    la zone (comportement v5)."""
    d0 = float(zone["distance_reference_m"])
    pl0 = float(zone["perte_reference_db"])
    dx = cfg.get("radio", {}).get("distance_reference_extrapolee_m")
    if dx and float(dx) < d0:
        return float(dx), pl0 - 10.0 * float(zone["path_loss_exponent"]) * math.log10(d0 / float(dx))
    return d0, pl0


def perte_moyenne_db(cfg, zone, d_m):
    """Perte moyenne (sans ombrage) a la distance d, vegetation et interieur
    compris. Sous d0 (effectif) le log-distance de ns-3 reste a PL(d0)."""
    d0, pl0 = reference_effective(cfg, zone)
    return (pl0
            + 10.0 * float(zone["path_loss_exponent"]) * math.log10(max(d_m, d0) / d0)
            + perte_vegetation_db(cfg, zone, d_m)
            + perte_interieur_db(cfg, zone)
            - float(cfg.get("radio", {}).get("correction_hauteur_db", 0.0)))


def distance_pour_perte(cfg, zone, perte_db):
    """Inverse de perte_moyenne_db (croissante en d) : plus grande distance ou la
    perte moyenne vaut perte_db, par dichotomie sur une echelle logarithmique."""
    lo, hi = 1.0, 1e6
    if perte_moyenne_db(cfg, zone, lo) > perte_db:
        return 0.0
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        if perte_moyenne_db(cfg, zone, mid) <= perte_db:
            lo = mid
        else:
            hi = mid
    return lo


def gain_passerelle_dbi(cfg, zone=None):
    """Gain d'antenne de la passerelle en reception : variante balayee portee par
    la zone, sinon valeur centrale du config."""
    if zone is not None and "gain_passerelle_dbi" in zone:
        return float(zone["gain_passerelle_dbi"])
    return float(cfg["passerelle"].get("gain_antenne_dbi", 0.0))


def budget_sf12_db(cfg, zone="sans"):
    """Perte maximale tolerable en SF12 : puissance - sensibilite passerelle
    (MCL, d'antenne a antenne). Avec une zone, le gain d'antenne de la
    passerelle est ajoute (bilan de la simulation)."""
    mcl = (float(cfg["radio"]["puissance_emission_dbm"])
           - float(cfg["passerelle"]["sensibilite_dbm_sf7_a_sf12"][-1]))
    return mcl if zone == "sans" else mcl + gain_passerelle_dbi(cfg, zone)


def rayon_fiable_theorique(cfg, zone):
    """Distance ou la probabilite de reception SF12 vaut le seuil de qualite,
    par bilan de liaison avec ombrage log-normal : marge = quantile(seuil) x sigma.
    Sert a dimensionner les experiences, pas a produire un resultat."""
    seuil = float(cfg["methode"]["seuil_acceptabilite_pdr"])
    marge = NormalDist().inv_cdf(seuil) * float(zone["shadowing_sigma_db"])
    return distance_pour_perte(cfg, zone, budget_sf12_db(cfg, zone) - marge)


def rayon_descendant_rx2(cfg, zone, p_dbm):
    """Rayon ou un accuse RX2 (SF12, p_dbm, sans gain d'antenne en emission,
    comme dans le modele) atteint le noeud avec la probabilite du seuil."""
    seuil = float(cfg["methode"]["seuil_acceptabilite_pdr"])
    marge = NormalDist().inv_cdf(seuil) * float(zone["shadowing_sigma_db"])
    budget = float(p_dbm) - float(cfg["noeud"]["sensibilite_dbm_sf7_a_sf12"][-1])
    return min(distance_pour_perte(cfg, zone, budget - marge), distance_horizon_m(cfg))


def rayon_dimensionnement(cfg, zone):
    """Rayon fiable theorique borne par l'horizon radio : la geometrie des
    experiences ne doit pas compter sur une portee au-dela de l'horizon."""
    return min(rayon_fiable_theorique(cfg, zone), distance_horizon_m(cfg))


def distance_horizon_m(cfg):
    """Horizon radio en metres, ou l'infini si l'horizon n'est pas pris en compte."""
    hz = cfg["radio"].get("horizon_radio", {})
    if not hz.get("actif", False):
        return float("inf")
    h_gw = float(cfg["passerelle"]["hauteur_antenne_m"])
    h_ed = float(cfg["noeud"]["hauteur_antenne_m"])
    return 1000.0 * float(hz["coefficient_km"]) * (h_gw ** 0.5 + h_ed ** 0.5)


# -----------------------------------------------------------------------------
# Geometrie des experiences.
# -----------------------------------------------------------------------------

def espacement_m(cfg, exp, zone, ctx):
    """Espacement des passerelles : facteur (variante ou bloc) x rayon de dimensionnement."""
    bloc = exp["passerelles"]
    f = ctx.get("espacement_facteur", bloc.get("espacement_facteur_rayon_fiable"))
    if f is None:
        sys.exit("Espacement des passerelles non defini (bloc ou balayage).")
    return float(f) * rayon_dimensionnement(cfg, zone)


def passerelles_xy(cfg, exp, zone, ctx=None):
    """Positions des passerelles [(x, y), ...] en metres.

    Par defaut une passerelle au centre. Avec un bloc 'passerelles' :
      ligne      : nb passerelles sur l'axe x, centrees, espacees de s ;
      hexagonale : une centrale et six voisines a distance s (pavage).
    """
    ctx = ctx or {}
    bloc = (exp or {}).get("passerelles")
    if not bloc:
        return [(0.0, 0.0)]
    s = espacement_m(cfg, exp, zone, ctx)
    disp = bloc.get("disposition", "ligne")
    if disp == "ligne":
        k = int(bloc["nombre"])
        return [((i - (k - 1) / 2.0) * s, 0.0) for i in range(k)]
    if disp == "hexagonale":
        if int(bloc["nombre"]) != 7:
            sys.exit("La disposition hexagonale attend 7 passerelles.")
        pts = [(0.0, 0.0)]
        for k in range(6):
            a = math.radians(60.0 * k)
            pts.append((s * math.cos(a), s * math.sin(a)))
        # Robustesse (consignes v4, point 1) : la passerelle centrale tombe,
        # les patients de la cellule centrale ne comptent plus que sur les six
        # voisines.
        if ctx.get("panne_centrale", bloc.get("passerelle_centrale_en_panne", False)):
            pts = pts[1:]
        return pts
    sys.exit(f"Disposition inconnue : {disp}")


def rayon_experience(cfg, exp, zone, ctx=None):
    """Rayon de placement des noeuds autour de l'origine.

    - portee : facteur x rayon fiable theorique (decision L) ;
    - capacite avec rayon_placement = rayon_fiable_theorique : rayon de
      dimensionnement (cellule isolee) ;
    - multi-passerelles en ligne : demi-etendue + rayon de dimensionnement ;
      hexagonale : cellule centrale, s / racine(3) ;
    - sinon : rayon de cellule de la zone.
    """
    exp = exp or {}
    ctx = ctx or {}
    if "rayon_test_facteur_rayon_fiable" in exp:
        return float(exp["rayon_test_facteur_rayon_fiable"]) * rayon_fiable_theorique(cfg, zone)
    if exp.get("passerelles"):
        if exp["passerelles"].get("disposition") == "hexagonale":
            return espacement_m(cfg, exp, zone, ctx) / math.sqrt(3.0)
        xs = [x for x, _ in passerelles_xy(cfg, exp, zone, ctx)]
        return (max(xs) - min(xs)) / 2.0 + rayon_dimensionnement(cfg, zone)
    if exp.get("rayon_placement") == "descendant_rx2":
        return rayon_descendant_rx2(cfg, zone, exp.get("puissance_rx2_dbm", 14.0))
    if exp.get("rayon_placement") == "rayon_fiable_theorique":
        return rayon_dimensionnement(cfg, zone)
    return float(zone["rayon_cellule_m"])


def resoudre_experience(cfg, nom):
    """Experience complete : les cles absentes sont reprises de experience_de_base."""
    exp = copy.deepcopy(cfg["experiences"][nom])
    base = exp.get("experience_de_base")
    vus = {nom}
    while base and base not in vus:
        # Heritage en chaine : les cles absentes sont reprises de la base, puis
        # de la base de la base, etc.
        vus.add(base)
        b = cfg["experiences"][base]
        for k, v in b.items():
            if k not in exp and not k.startswith("_") and k not in ("description", "actif", "experience_de_base"):
                exp[k] = copy.deepcopy(v)
        base = b.get("experience_de_base")
    return exp


def variantes_zone(cfg, exp, zone_cle):
    """Liste de (etiquette, zone, ctx) a simuler pour une zone.

    Les dimensions balayees se combinent :
      - parametre de propagation (sensibilite) : nb_points valeurs sur la plage ;
      - balayage_espacement_facteur_rayon_fiable (multi-passerelles) ;
      - balayage_fraction_intensif (capacite sur melange de profils).
    ctx porte les valeurs non propagatives (espacement, fraction intensive).
    """
    base = cfg["zones"][zone_cle]
    variantes = [("", base, {})]
    param = exp.get("parametre")
    if param:
        plage = base.get(f"{param}_plage")
        if not plage:
            print(f"  [sensibilite] zone {zone_cle} : pas de plage pour {param}, ignoree.")
            return []
        k = int(exp["nb_points"])
        lo, hi = float(plage[0]), float(plage[1])
        valeurs = [lo] if k == 1 else [lo + i * (hi - lo) / (k - 1) for i in range(k)]
        variantes = []
        for v in valeurs:
            z = copy.deepcopy(base)
            z[param] = round(v, 4)
            variantes.append((f"{param}={z[param]}", z, {}))
    veg = base.get("vegetation")
    if exp.get("balayer_densite_vegetation") and veg and veg.get("actif", True) and veg.get("balayage_densite"):
        nouvelles = []
        for lab, z, ctx in variantes:
            for k in veg["balayage_densite"]:
                z2 = copy.deepcopy(z)
                z2["vegetation"]["densite"] = float(k)
                nouvelles.append(((lab + " " if lab else "") + f"vegetation={k}", z2, dict(ctx)))
        variantes = nouvelles
    if exp.get("balayage_interieur_perte_db") is not None and exp.get("balayage_interieur_perte_db") != []:
        nouvelles = []
        for lab, z, ctx in variantes:
            for v in exp["balayage_interieur_perte_db"]:
                z2 = copy.deepcopy(z)
                z2["interieur_perte_db"] = float(v)
                nouvelles.append(((lab + " " if lab else "") + f"interieur={v:g}", z2, dict(ctx)))
        variantes = nouvelles
    if exp.get("balayage_gain_antenne_dbi"):
        nouvelles = []
        for lab, z, ctx in variantes:
            for g in exp["balayage_gain_antenne_dbi"]:
                z2 = copy.deepcopy(z)
                z2["gain_passerelle_dbi"] = float(g)
                nouvelles.append(((lab + " " if lab else "") + f"gain={g:g}", z2, dict(ctx)))
        variantes = nouvelles
    for cle_bal, cle_ctx, nom in (("balayage_espacement_facteur_rayon_fiable", "espacement_facteur", "espacement"),
                                  ("balayage_correlation_sites", "correlation_sites", "correlation"),
                                  ("balayage_modes_confirmation", "mode_confirmation", "mode"),
                                  ("balayage_messages_par_jour", "messages_par_jour", "messages"),
                                  ("balayage_marge_rx1_db", "marge_rx1_db", "marge"),
                                  ("balayage_nbtrans_routine", "nbtrans_routine", "nbtrans"),
                                  ("balayage_rx1_delai_s", "rx1_delai_s", "rx1"),
                                  ("balayage_panne_centrale", "panne_centrale", "panne"),
                                  ("balayage_interieur_fraction", "interieur_fraction", "frac_int"),
                                  ("balayage_decalage_sensibilite_db", "decalage_sensibilite_db", "sens"),
                                  ("balayage_pic_remontee", "pic_remontee", "pic"),
                                  ("balayage_recap_periode_h", "recap_periode_h", "recap"),
                                  ("balayage_alertes_par_jour", "alertes_par_jour", "alertes"),
                                  ("balayage_alarme_deux_temps", "alarme_deux_temps", "deuxtemps"),
                                  ("balayage_interieur_simule_db", "interieur_simule_db", "int_sim"),
                                  ("balayage_puissance_rx2_dbm", "puissance_rx2_dbm", "rx2dbm"),
                                  ("balayage_fraction_intensif", "fraction_intensif", "intensif")):
        if exp.get(cle_bal):
            nouvelles = []
            for lab, z, ctx in variantes:
                for v in exp[cle_bal]:
                    c2 = dict(ctx)
                    c2[cle_ctx] = v if isinstance(v, str) else float(v)
                    nouvelles.append(((lab + " " if lab else "") + f"{nom}={v}", z, c2))
            variantes = nouvelles
    return [(lab or "base", z, ctx) for lab, z, ctx in variantes]


def melange_profils(cfg, ctx):
    """Fractions par profil. La fraction du profil intensif peut etre imposee
    (ctx), le reste est reparti au prorata du melange de base."""
    pp = cfg["profils_patients"]
    base = dict(pp["melange_base"])
    if "fraction_intensif" not in ctx:
        return base
    fi = ctx["fraction_intensif"]
    nom_i = pp["profil_intensif"]
    reste = sum(v for k, v in base.items() if k != nom_i)
    return {k: (fi if k == nom_i else (1.0 - fi) * v / reste) for k, v in base.items()}


def args_profils(cfg, n_noeuds, ctx, mic):
    """Arguments --profiles et --alert* pour le modele, depuis le config."""
    pp = cfg["profils_patients"]
    frac = melange_profils(cfg, ctx)
    noms = list(pp["profils"].keys())
    # Repartition entiere des noeuds (plus grands restes).
    brut = [frac.get(nm, 0.0) * n_noeuds for nm in noms]
    nb = [int(math.floor(b)) for b in brut]
    for i in sorted(range(len(noms)), key=lambda i: brut[i] - nb[i], reverse=True)[: n_noeuds - sum(nb)]:
        nb[i] += 1
    # Cadence imposee (messages par patient et par jour, alerte comprise) :
    # toutes les cadences de profil sont multipliees par le meme facteur.
    facteur = 1.0
    if ctx.get("messages_par_jour"):
        al0 = pp.get("alerte", {})
        n_al = float(al0.get("alertes_par_jour", 0)) if al0.get("actif", False) else 0.0
        base = sum(frac.get(nm, 0.0) * float(pp["profils"][nm]["uplinks_par_jour"]) for nm in noms)
        facteur = (float(ctx["messages_par_jour"]) - n_al) / base
    morceaux = []
    for nm, k in zip(noms, nb):
        pr = pp["profils"][nm]
        periode = 86400.0 / (float(pr["uplinks_par_jour"]) * facteur)
        morceaux.append(f"{periode:.1f}:{int(pr['octets_charge']) + mic}:{k}")
    out = {"profiles": ";".join(morceaux)}
    al = pp.get("alerte", {})
    if al.get("actif", False):
        concernes = set(al["profils_concernes"])
        out.update({
            "alertPerDay": float(al["alertes_par_jour"]),
            "alertSize": int(al["octets_charge"]) + mic,
            "alertNbTrans": int(al["nb_transmissions_max"]),
            "alertProfiles": ",".join("1" if nm in concernes else "0" for nm in noms),
            "deferDuringAlert": 1 if al.get("differer_routine_pendant_alerte", True) else 0,
        })
    return out, dict(zip(noms, nb))


# -----------------------------------------------------------------------------
# Appel du modele.
# -----------------------------------------------------------------------------

def construire_args(cfg, zone_cle, zone, n_noeuds, run, exp_label, sigma,
                    confirmed=False, nb_trans=8, exp=None, ctx=None):
    """Assemble les arguments du binaire ns-3. Toutes les valeurs viennent du config."""
    radio = cfg["radio"]
    trafic = cfg["trafic"]
    passerelle = cfg["passerelle"]
    noeud = cfg["noeud"]
    methode = cfg["methode"]

    # Le module ajoute lui-meme son en-tete mais pas le MIC : on lui passe
    # charge + MIC, pour que la trame a l'antenne fasse charge + en-tete LoRaWAN.
    entete = int(trafic["entete_lorawan_octets"])
    ajoute = int(trafic["entete_ajoute_par_module_octets"])
    mic = int(trafic["mic_non_modelise_octets"])
    if ajoute + mic != entete:
        sys.exit(f"Config incoherent : {ajoute} + {mic} != entete LoRaWAN {entete}.")
    pkt = int(trafic["octets_par_mesure"]) + mic

    ctx = ctx or {}
    radius = rayon_experience(cfg, exp, zone, ctx)
    gws = passerelles_xy(cfg, exp, zone, ctx)
    args = {
        "nDevices": n_noeuds,
        "radius": round(radius, 1),
        "pathLossExp": float(zone["path_loss_exponent"]),
        "refDist": reference_effective(cfg, zone)[0],
        "refLoss": round(reference_effective(cfg, zone)[1], 4),
        "excessLossDb": 0.0,
        "gwGainDb": gain_passerelle_dbi(cfg, zone),
        "appPeriod": float(trafic["periode_emission_s"]),
        "pktSize": pkt,
        "simTime": float(methode["duree_simulee_jours"]) * 86400.0,
        "gwHeight": float(passerelle["hauteur_antenne_m"]),
        "edHeight": float(noeud["hauteur_antenne_m"]),
        "runNumber": run,
        "zoneLabel": zone_cle,
        "expLabel": exp_label,
        "shadowingSigma": sigma,
        "gwPositions": ";".join(f"{x:.1f},{y:.1f}" for x, y in gws),
        "adr": 1 if radio.get("adr_actif", False) else 0,
        "splitChannel": 1 if radio.get("canaux_separes", False) else 0,
        "shadowSiteCorr": float(ctx.get("correlation_sites", radio.get("correlation_ombrage_entre_sites", 0.0))),
        "shadowCorrDist": float(zone.get("distance_decorrelation_ombrage_m", 0.0)),
    }
    # Par defaut l'horizon s'applique en analyse, pas en simulation.
    hz = radio.get("horizon_radio", {})
    multi = len(gws) > 1 and hz.get("en_simulation_multi_passerelles", False)
    actif = hz.get("actif", False) and (hz.get("en_simulation", False) or multi)
    args["horizonCoefKm"] = float(hz["coefficient_km"]) if actif else 0.0
    if actif:
        args["horizonLossDb"] = float(hz["perte_au_dela_db"])
    placement = (exp or {}).get("placement", "disque_uniforme")
    args["placement"] = {"disque_uniforme": "disque", "distance_uniforme": "distance"}[placement]
    am, coef, fa, db = params_vegetation(cfg, zone)
    if am > 0.0:
        args.update({"vegAm": round(am, 4), "vegCoef": round(coef, 5), "vegFExp": fa, "vegDExp": db,
                     "freqMHz": float(radio["frequence_mhz"])})
    if (exp or {}).get("duree_simulee_jours"):
        args["simTime"] = float(exp["duree_simulee_jours"]) * 86400.0
    if confirmed:
        args["confirmed"] = 1
        args["nbTrans"] = nb_trans
    # Fenetres et remontee (consignes v4, points 10 et 13). Valeurs du config,
    # surchargees par l'experience ou par un balayage.
    fen = cfg["passerelle"].get("fenetres_reception", {})
    for cle, arg, defaut in (("rx1_delai_s", "rx1Delay", None), ("puissance_rx2_dbm", "rx2PowerDbm", None),
                             ("latence_remontee_ms", "backhaulDelayMs", None)):
        v = ctx.get(cle, (exp or {}).get(cle, fen.get(cle, defaut)))
        if v is not None:
            args[arg] = float(v)
    # Consignes v6. Sensibilite de la passerelle (config), decalage balaye.
    sens = passerelle.get("sensibilite_dbm_sf7_a_sf12")
    if sens:
        args["gwSens"] = ",".join(f"{float(x):g}" for x in sens)
    off = ctx.get("decalage_sensibilite_db", (exp or {}).get("decalage_sensibilite_db"))
    if off is not None:
        args["gwSensOffsetDb"] = float(off)
    # Interieur : perte (zone ou config) et part du temps (contexte, experience, config).
    it = noeud.get("interieur", {})
    l_int = perte_interieur_db(cfg, zone)
    f_int = float(ctx.get("interieur_fraction", (exp or {}).get("interieur_fraction", it.get("fraction_temps", 1.0))))
    # v6.2 : perte simulee differente de celle du dimensionnement (parade :
    # antenne du pont pres d'une ouverture), la geometrie restant la meme.
    l_sim = ctx.get("interieur_simule_db", (exp or {}).get("interieur_simule_db"))
    if l_sim is not None:
        l_int = float(l_sim)
    if l_int > 0.0 and f_int > 0.0:
        args["indoorLossDb"] = round(l_int, 3)
        args["indoorFraction"] = f_int
    # Remontee realiste (module), si active dans le config ou l'experience.
    rm = dict(passerelle.get("remontee_modele", {}))
    rm.update((exp or {}).get("remontee_modele", {}))
    if rm.get("actif"):
        args.update({"bhModel": 1, "bhMedianMs": float(rm["latence_mediane_aller_ms"]),
                     "bhSigma": float(rm["ecart_type_log"]),
                     "bhSpikeProb": float(ctx.get("pic_remontee", rm["probabilite_pic"])),
                     "bhSpikeMinS": float(rm["pic_s"][0]), "bhSpikeMaxS": float(rm["pic_s"][1]),
                     "bhLossProb": float(rm["perte_tcp"]), "bhRtoMs": float(rm["rto_min_ms"]),
                     "dedupMs": float(rm["deduplication_ms"]), "tooLateMs": float(rm["too_late_ms"])})
    if (exp or {}).get("exclure_dernieres_s") is not None:
        args["evalExcludeLastS"] = float(exp["exclure_dernieres_s"])
    if (exp or {}).get("profils"):
        a_prof, _ = args_profils(cfg, n_noeuds, ctx, mic)
        args.update(a_prof)
        # Mode de confirmation (decision U), a trafic identique.
        mode = ctx.get("mode_confirmation", (exp or {}).get("mode_confirmation", "mixte"))
        conf = cfg["profils_patients"].get("confirmation", {})
        if mode == "tout_non_confirme":
            args["alertConfirmed"] = 0
            args.pop("confirmed", None)
        elif mode in ("tout_confirme", "tout_confirme_rx2", "mixte_rx2"):
            pass
        if mode in ("tout_confirme", "tout_confirme_rx2"):
            args["confirmed"] = 1
            args["nbTrans"] = int(ctx.get("nbtrans_routine", conf.get("nb_transmissions_routine_confirmee", nb_trans)))
            args["confGuard"] = float(conf.get("garde_routine_confirmee_s", 7200))
        if mode.endswith("_rx2"):
            # Serveur : accuse en RX2 (27 dBm) quand RX1 (14 dBm) ne porte pas.
            args["rx1Check"] = 1
            args["rx1MarginDb"] = float(ctx.get("marge_rx1_db", conf.get("marge_rx1_db", 0.0)))
        if mode == "mixte_recap_rx2":
            # Consignes v6, point 7 : routine sans accuse, recapitulatif quotidien.
            rc = cfg["profils_patients"].get("recapitulatif", {})
            if ctx.get("alarme_deux_temps", (exp or {}).get("alarme_deux_temps")):
                args["alarmTwoStage"] = 1
                args["alarmPendingMaxH"] = float(rc.get("attente_alarme_max_h", 6))
            args.update({"recap": 1, "recapPeriodH": float(ctx.get("recap_periode_h", rc.get("echeance_h", 24))),
                         "recapRequestH": float(rc.get("demande_pont_h", 26)),
                         "recapAlarmH": float(rc.get("alarme_h", 48)),
                         "recapBufferH": float(rc.get("tampon_h", 72)),
                         "confGuard": float(conf.get("garde_routine_confirmee_s", 7200))})
        if ctx.get("alertes_par_jour") is not None and "alertPerDay" in args:
            args["alertPerDay"] = float(ctx["alertes_par_jour"])
        if mode not in ("tout_non_confirme", "mixte", "tout_confirme", "tout_confirme_rx2", "mixte_rx2",
                        "mixte_recap_rx2"):
            sys.exit(f"Mode de confirmation inconnu : {mode}")
    if (exp or {}).get("mesure_energie"):
        en = cfg["noeud"]["energie"]
        args.update({"energy": 1, "enVoltage": en["tension_v"], "enSleepA": en["courant_sommeil_a"],
                     "enStandbyA": en["courant_attente_a"], "enRxA": en["courant_reception_a"],
                     "enTxEta": en["emission_rendement_ampli"], "enTxBaseA": en["emission_courant_base_a"]})
    return args, radius


def lire_lignes_noeuds(stdout):
    """Extrait les lignes NODE d'un run, une liste de dicts."""
    noeuds = []
    for l in stdout.splitlines():
        if not l.startswith(NODE_PREFIX):
            continue
        c = l[len(NODE_PREFIX):].split(";")
        nd = {
            "exp": c[0], "zone": c[1], "nDevices": int(c[2]),
            "runNumber": int(c[3]), "confirmed": int(c[4]), "nodeId": int(c[5]),
            "distance_m": float(c[6]), "sf": int(c[7]), "newSent": int(c[8]),
            "txTotal": int(c[9]), "received": int(c[10]), "acked": int(c[11]),
            "airtime_s": float(c[12]),
        }
        if len(c) >= 18:
            nd.update({"gwNearest": int(c[13]), "gwReceptions": int(c[14]),
                       "multiGw": int(c[15]), "latencyMean_s": float(c[16]),
                       "latencyMax_s": float(c[17])})
        if len(c) >= 19:
            nd["rxNearest"] = int(c[18])
        if len(c) >= 28:
            nd.update({"profile": int(c[19]), "genRoutine": int(c[20]), "genAlert": int(c[21]),
                       "alertNew": int(c[22]), "alertDelivered": int(c[23]), "alertAcked": int(c[24]),
                       "alertLatUpMax_s": float(c[25]), "alertRttMean_s": float(c[26]),
                       "alertRttMax_s": float(c[27])})
        if len(c) >= 34:
            nd.update({"mobile": int(c[28]), "readingsGen": int(c[29]), "readingsDelivered": int(c[30]),
                       "readingsDropped": int(c[31]), "readingLatMean_s": float(c[32]),
                       "readingLatMax_s": float(c[33])})
        if len(c) >= 40:
            nd.update({"confRoutineGen": int(c[34]), "confRoutineAcked": int(c[35]),
                       "confRoutineFail": int(c[36]), "confRoutineDelayMean_s": float(c[37]),
                       "confRoutineDelayMax_s": float(c[38]), "energy_J": float(c[39])})
        if len(c) >= 53:
            for k, nom in enumerate(("readingsEligible", "readingsOk72h", "alertsCounted", "alertsOk15", "alarms",
                                     "falseAlarms", "unconfirmedNoAlarm", "alertsIndoor", "alertsIndoorOk15",
                                     "recapAttempts", "recapOk", "techAlarms", "resent")):
                nd[nom] = int(c[40 + k])
        if len(c) >= 54:
            nd["alertsOk5"] = int(c[53])
        if len(c) >= 57:
            nd.update({"trueAlarms": int(c[54]), "detectSum_s": float(c[55]), "detectMax_s": float(c[56])})
        noeuds.append(nd)
    return noeuds


def lire_lignes_ack(stdout):
    """Lignes ACK (percentiles du delai d'acquittement par type de trame)."""
    out = []
    for l in stdout.splitlines():
        if l.startswith(ACK_PREFIX):
            c = l[len(ACK_PREFIX):].split(";")
            out.append(dict(zip(["exp", "zone", "nDevices", "runNumber", "type", "nConf", "nAcked", "nFail",
                                 "nOpen", "p50_s", "p95_s", "p99_s", "p95Acquittees_s", "max_s", "gardes",
                                 "remisEnFile"], c)))
    return out


def lancer_un_run(ns3_dir, binaire, args, timeout_s):
    """Appelle ns-3 une fois, renvoie (dict de la ligne CSV, liste des noeuds),
    ou (None, []) si echec."""
    chaine = binaire + " " + " ".join(f"--{k}={v}" for k, v in args.items())
    cmd = [os.path.join(ns3_dir, "ns3"), "run", "--no-build", chaine]
    try:
        res = subprocess.run(cmd, cwd=ns3_dir, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        print(f"    [timeout] {chaine}", file=sys.stderr)
        return None, []
    if res.returncode != 0:
        print(f"    [echec ns-3 code {res.returncode}] {chaine}", file=sys.stderr)
        print(res.stderr[-500:], file=sys.stderr)
        return None, []

    ligne = next((l for l in res.stdout.splitlines() if l.startswith(CSV_PREFIX)), None)
    if ligne is None:
        print(f"    [pas de ligne CSV] {chaine}", file=sys.stderr)
        return None, []
    champs = ligne[len(CSV_PREFIX):].split(";")
    if len(champs) < 15:
        print(f"    [ligne CSV trop courte] {ligne}", file=sys.stderr)
        return None, []

    noms = ["exp", "zone", "nDevices", "pathLossExp", "shadowingSigma", "runNumber",
            "sent", "received", "pdr", "phyTotal", "phyRecv", "phyInterf", "phyNoRecv",
            "phyUnderSens", "phyLostTx", "confirmed", "nbTrans", "acked", "cpsr",
            "nGateways", "gwReceptions", "multiGwPackets", "nsArrivals"]
    types = {"exp": str, "zone": str, "pathLossExp": float, "shadowingSigma": float,
             "pdr": float, "cpsr": float}
    d = {}
    for nom, val in zip(noms, champs):
        d[nom] = types.get(nom, int)(val)
    d["_ack"] = lire_lignes_ack(res.stdout)
    return d, lire_lignes_noeuds(res.stdout)


# -----------------------------------------------------------------------------
# Programme principal.
# -----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Orchestrateur Monte-Carlo LoRaWAN STOP-MNT")
    ap.add_argument("--config", required=True, help="Chemin du config.json")
    ap.add_argument("--ns3-dir", required=True, help="Racine de ns-3 (ou vit ./ns3)")
    ap.add_argument("--out", default="./resultats", help="Dossier de sortie")
    ap.add_argument("--exp", default="capacite", help="Nom de l'experience a lancer")
    ap.add_argument("--bras", choices=["sans", "avec", "les-deux"], default="avec",
                    help="sans ombrage (controle), avec ombrage, ou les deux")
    ap.add_argument("--shadow-bin", default="lorawan-cell-shadow",
                    help="Nom du binaire du modele dans scratch")
    ap.add_argument("--confirme", choices=["0", "1", "both"], default="0",
                    help="non confirme (0), confirme (1), ou les deux pour comparer")
    ap.add_argument("--nbTrans", type=int, default=8, help="Nb max de transmissions en confirme")
    ap.add_argument("--repetitions", type=int, default=None,
                    help="Forcer le nombre de repetitions (sinon celui du config)")
    ap.add_argument("--max-nodes", type=int, default=None,
                    help="Plafonner le balayage du nombre de noeuds")
    ap.add_argument("--timeout", type=int, default=1800, help="Delai max par run en secondes")
    ap.add_argument("--zones", nargs="+", default=None,
                    help="Restreindre aux zones donnees (parmi celles de l'experience)")
    ap.add_argument("--jobs", type=int, default=1,
                    help="Runs ns-3 simultanes (repetitions d'un meme palier en parallele)")
    ap.add_argument("--validation", action="store_true",
                    help="Utiliser methode.repetitions_validation (10) au lieu de repetitions (20)")
    ap.add_argument("--nb-noeuds", type=int, nargs="+", default=None,
                    help="Remplacer la liste balayage_nb_noeuds de l'experience")
    ap.add_argument("--modes", nargs="+", default=None,
                    help="Remplacer la liste balayage_modes_confirmation de l'experience")
    ap.add_argument("--duree-jours", type=float, default=None,
                    help="Remplacer la duree simulee (jours)")
    ap.add_argument("--reprendre", action="store_true",
                    help="Sauter les runs deja presents dans les resultats_<exp>_*.csv du dossier de sortie")
    ap.add_argument("--smoke", action="store_true",
                    help="Essai rapide : 2 repetitions, paliers <= 400")
    args = ap.parse_args()

    ns3_dir = os.path.abspath(os.path.expanduser(args.ns3_dir))
    cfg = charger_config(os.path.expanduser(args.config))

    if args.exp not in cfg["experiences"]:
        sys.exit(f"Experience '{args.exp}' absente du config.")
    exp = resoudre_experience(cfg, args.exp)
    if not exp.get("actif", False):
        print(f"Attention : l'experience '{args.exp}' est marquee inactive dans le config.")

    if args.modes:
        exp["balayage_modes_confirmation"] = list(args.modes)
    if args.duree_jours:
        exp["duree_simulee_jours"] = float(args.duree_jours)
    ap_rep = args.repetitions
    if args.validation and not ap_rep:
        ap_rep = int(cfg["methode"]["repetitions_validation"])
    repetitions = ap_rep if ap_rep else int(exp.get("repetitions", cfg["methode"]["repetitions"]))
    plancher_arret = float(exp.get("arret_adaptatif_pdr", 0.0))
    paliers = list(exp["balayage_nb_noeuds"])
    zones_exp = exp["zones"]
    if args.zones:
        inconnues = [z for z in args.zones if z not in zones_exp]
        if inconnues:
            sys.exit(f"Zones absentes de l'experience '{args.exp}' : {inconnues}")
        zones_exp = [z for z in zones_exp if z in args.zones]
    if args.smoke:
        repetitions = 2
        paliers = [p for p in paliers if p <= 400] or [paliers[0]]
    if args.max_nodes:
        paliers = [p for p in paliers if p <= args.max_nodes]
    if args.nb_noeuds:
        paliers = list(args.nb_noeuds)

    bras_list = ["sans", "avec"] if args.bras == "les-deux" else [args.bras]
    confirme_list = [False, True] if args.confirme == "both" else [args.confirme == "1"]

    out = os.path.expanduser(args.out)
    os.makedirs(out, exist_ok=True)
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    chemin_res = os.path.join(out, f"resultats_{args.exp}_{horodatage}.csv")
    chemin_noeuds = os.path.join(out, f"noeuds_{args.exp}_{horodatage}.csv")
    with open(os.path.join(out, f"config_{args.exp}_{horodatage}.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"Resultats -> {chemin_res}")
    print(f"Par noeud -> {chemin_noeuds}")
    print(f"Bras={bras_list}  zones={zones_exp}  paliers={paliers}  repetitions={repetitions}  jobs={args.jobs}",
          flush=True)
    t0 = time.time()
    n_runs = 0

    chemin_ack = os.path.join(out, f"ack_{args.exp}_{horodatage}.csv")
    from concurrent.futures import as_completed
    with open(chemin_res, "w", newline="", encoding="utf-8") as fres, \
         open(chemin_noeuds, "w", newline="", encoding="utf-8") as fnoeuds, \
         open(chemin_ack, "w", newline="", encoding="utf-8") as fack, \
         ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        writer = csv.DictWriter(fres, fieldnames=COLONNES)
        writer.writeheader()
        writer_n = csv.DictWriter(fnoeuds, fieldnames=COLONNES_NOEUDS)
        writer_n.writeheader()
        writer_a = csv.DictWriter(fack, fieldnames=COLONNES_ACK)
        writer_a.writeheader()

        # Tous les runs sont independants : on les soumet d'un bloc (les
        # coeurs restent occupes) et on ecrit chaque resultat des qu'il arrive.
        futs = {}
        deja = set()
        if args.reprendre:
            import glob
            for ch in glob.glob(os.path.join(out, f"resultats_{args.exp}_*.csv")):
                if ch == chemin_res:
                    continue
                for r in csv.DictReader(open(ch, encoding="utf-8")):
                    deja.add((r["bras"], r["zone"], r["variante"], int(r["nDevices"]), int(r["runNumber"])))
            print(f"Reprise : {len(deja)} runs deja faits, sautes", flush=True)
        for bras in bras_list:
            for confirmed in confirme_list:
                for zone_cle in zones_exp:
                    for variante, zone, ctx in variantes_zone(cfg, exp, zone_cle):
                        sigma = float(zone["shadowing_sigma_db"]) if bras == "avec" else 0.0
                        rayon = rayon_experience(cfg, exp, zone, ctx)
                        print(f"  planifie : bras={bras} zone={zone_cle} {variante} "
                              f"(n={zone['path_loss_exponent']}, veg Am={perte_vegetation_db(cfg, zone):.1f} dB, "
                              f"sigma={sigma}, rayon={rayon:.0f} m, "
                              f"passerelles={len(passerelles_xy(cfg, exp, zone, ctx))})", flush=True)
                        for n in paliers:
                            for run in range(1, repetitions + 1):
                                if (bras, zone_cle, variante, n, run) in deja:
                                    continue
                                # Le nombre de transmissions de la routine n'a de sens qu'en tout confirme.
                                if ctx.get("nbtrans_routine") not in (None, 8, 8.0) and \
                                        not str(ctx.get("mode_confirmation", "")).startswith("tout_confirme"):
                                    continue
                                pmax = exp.get("palier_max_par_mode", {}).get(ctx.get("mode_confirmation"))
                                if pmax is not None and n > pmax:
                                    continue
                                a, radius = construire_args(cfg, zone_cle, zone, n, run, args.exp,
                                                            sigma, confirmed=confirmed,
                                                            nb_trans=args.nbTrans, exp=exp, ctx=ctx)
                                f = pool.submit(lancer_un_run, ns3_dir, args.shadow_bin, a, args.timeout)
                                futs[f] = (bras, variante, a, radius)
        total = len(futs)
        print(f"{total} runs planifies", flush=True)
        echecs = 0
        for f in as_completed(futs):
            bras, variante, a, radius = futs.pop(f)
            d, noeuds = f.result()
            n_runs += 1
            if d is None:
                echecs += 1
                continue
            commun = {"bras": bras, "variante": variante, "radius": radius,
                      "refDist": a["refDist"], "refLoss": a["refLoss"],
                      "excessLossDb": a.get("vegAm", 0.0)}
            for ak in d.pop("_ack", []):
                ak.update({k: commun[k] for k in ("bras", "variante")})
                writer_a.writerow({c: ak.get(c, "") for c in COLONNES_ACK})
            fack.flush()
            d.update(commun)
            d["gwPositions"] = a["gwPositions"]
            writer.writerow({c: d.get(c, "") for c in COLONNES})
            fres.flush()
            for nd in noeuds:
                nd.update(commun)
                nd["pathLossExp"] = a["pathLossExp"]
                writer_n.writerow({c: nd.get(c, "") for c in COLONNES_NOEUDS})
            fnoeuds.flush()
            if n_runs % 20 == 0 or n_runs == total:
                el = (time.time() - t0) / 60
                print(f"  {n_runs}/{total} runs ({echecs} echecs), {el:.1f} min, "
                      f"reste estime {el * (total - n_runs) / n_runs:.0f} min", flush=True)

    dt = time.time() - t0
    print(f"\nTermine. {n_runs} runs en {dt / 60:.1f} min. Resultats dans {chemin_res}")


if __name__ == "__main__":
    main()
