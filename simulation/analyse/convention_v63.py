#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convention_v63.py

Consignes v6.3 : couche de connexion seule, aucune nouvelle simulation radio.
Passerelles (placement v6.2), patients, volumes par message et tirages
Monte-Carlo sont ceux de la v6.2 ; seule la connexion cellulaire change :

  C_connexion = somme_l V_l x p_Go x (1 + m)   volume majore
              + k x F_global                    une fois pour le projet
              + 12 x N_L x f_ligne              part par ligne

Entrees : les postes hors connexion par commune, ecrits par
couche_cout.py --composantes (kits, passerelles hors remontee, parts de
secours, serveur LoRaWAN), et le bloc cout.convention du config.

Familles (a exigence egale, comme en v6.2) :
  LoRa sans convention : LoRa + secours cellulaire ; passerelles et cartes SIM
      du secours au forfait public ; pas de F_global ;
  LoRa sous convention : memes equipements, passerelles et cartes SIM du
      secours dans la convention ;
  cellulaire           : cellulaire + secours LoRa, sous convention (cartes SIM
      des ponts et passerelles du secours).
Structure Kerlink : la remontee des passerelles est dans les 90 % hors materiel,
elle n'est ni ajoutee ni comptee comme ligne.

Vue A (departement) : somme des couts / somme des patients ; choix par commune
par enumeration des 2^8 affectations x 2 options de connexion LoRa, F_global
paye une fois des qu'une ligne est dans la convention.
Vue B (commune) : cout par patient de chaque option pour une commune, les
autres gardant leur choix optimal de la vue A ; F_global reparti au prorata
des lignes de la convention.

Tirages : les 500 tirages v6.2 (graine 1, monte_carlo_cout.py --choix
--placement placement_v62), regeneres a l'identique ; f_ligne et forfait public
recales lineairement depuis les valeurs v6.2 ; marge et receptions par trame
tirees (graine 63).

Sorties dans --out : cout_departement_v63.csv, cout_communes_v63.csv,
choix_communes_v63.csv, seuils_convention_v63.csv, monte_carlo_resume_v63.csv,
tirages_v63.csv, controles_v63.txt, fig_carte_convention_v63.png/pdf,
fig_cout_par_commune_v63.png/pdf.
"""
import argparse
import copy
import csv
import itertools
import json
import os
import random
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import tornade_cout as T  # noqa: E402

COMMUNES = ["abomey_calavi", "allada", "kpomasse", "ouidah", "so_ava", "toffo", "tori_bossito", "ze"]
NOMS = {"abomey_calavi": "Abomey-Calavi", "allada": "Allada", "kpomasse": "Kpomassè", "ouidah": "Ouidah",
        "so_ava": "Sô-Ava", "toffo": "Toffo", "tori_bossito": "Tori-Bossito", "ze": "Zè"}
OPTIONS = ["LoRa sans convention", "LoRa sous convention", "cellulaire sous convention"]
ARCHS = ["tout LoRa sans convention", "tout LoRa sous convention", "tout cellulaire sous convention",
         "choix par commune"]
CLASSES = ["tout LoRaWAN sans convention", "tout LoRaWAN sous convention", "choix mixte par commune", "tout cellulaire"]
MASQUES = np.array(list(itertools.product([0, 1], repeat=len(COMMUNES))), dtype=float)  # 1 = cellulaire
STRUCT = {"bas": "Structure détaillée", "haut": "Structure Kerlink"}


# --------------------------------------------------------------- composantes
def composantes(cfg, prod, placement, cad, fr):
    """Postes hors connexion par commune (niveaux bas et haut) pour un config."""
    with tempfile.TemporaryDirectory() as tmp:
        ch = os.path.join(tmp, "config.json")
        json.dump(cfg, open(ch, "w", encoding="utf-8"), ensure_ascii=False)
        subprocess.run([sys.executable, os.path.join(ICI, "couche_cout.py"), "--config", ch, "--prod", prod,
                        "--out", tmp, "--sans-figure", "--composantes", "--placement", placement],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        out = {}
        for r in csv.DictReader(open(os.path.join(tmp, "composantes.csv"), encoding="utf-8")):
            if float(r["messages_par_jour"]) == cad and float(r["fraction_suivie"]) == fr:
                out.setdefault(r["niveau"], {})[r["commune"]] = {k: (v if k in ("commune", "zone", "niveau") else float(v))
                                                                for k, v in r.items()}
        return out


def empiler(liste):
    """Liste (tirages) de {commune: dict} -> {champ: tableau (tirages, communes)}."""
    champs = [k for k in liste[0][COMMUNES[0]] if k not in ("commune", "zone", "niveau")]
    return {k: np.array([[d[c][k] for c in COMMUNES] for d in liste]) for k in champs}


# ------------------------------------------------------------------- couts
def couts(K, P, cfg, kerlink):
    """Couts annuels (EUR) par tirage et commune, hors F_global et hors part par
    ligne (lineaire en f_ligne : cout = base + 12 f_ligne / fcfa x lignes).
    K : composantes empilees ; P : parametres (tableaux (tirages, 1))."""
    fcfa = float(cfg["cout"]["fcfa_par_eur"])
    rp = cfg["cout"]["remontee_passerelle"]
    n, f, u = K["patients"], K["part_ombre_lora"], K["part_sans_couverture"]
    ngw, g = K["passerelles"], K["passerelles_secours_cell"]
    kL, kC, gwH = K["kit_lora_eur_an"], K["kit_cell_eur_an"], K["passerelle_hors_remontee_eur_an"]
    pb = P["p_go"] * (1 + P["m"]) / 1024 ** 3 / fcfa                      # EUR par octet
    v_pat = K["octets_patient_mois_mqtt"] * 12
    v_tr = (K["trames_passerelle_par_patient_jour"] * rp["octets_par_trame"] * P["r"]
            + K["accuses_par_patient_jour"] * rp["octets_par_accuse"]) * 365
    v_m = rp["octets_maintien_par_jour"] * 365
    pub = P["fpub"] * 12 / fcfa
    kg = 0.0 if kerlink else 1.0
    nl = u * n
    o = {}
    o["Ls"] = n * (1 - f) * kL + n * f * (kC + pub) + ngw * (gwH + kg * pub)
    o["vol_L"] = n * f * v_pat + ngw * v_m + n * (1 - f) * v_tr
    o["Lc"] = n * (1 - f) * kL + n * f * (kC + v_pat * pb) + ngw * gwH + kg * (ngw * v_m + n * (1 - f) * v_tr) * pb
    o["Ll"] = n * f + kg * ngw
    o["vol_C"] = (n - nl) * v_pat + g * v_m + nl * v_tr
    o["Cc"] = (n - nl) * (kC + v_pat * pb) + nl * kL + g * gwH + kg * (g * v_m + nl * v_tr) * pb
    o["Cl"] = (n - nl) + kg * g
    o["n"] = n
    o["lns"] = K["lns_departement_eur_an"][:, :1]
    return o


def avec_ligne(o, fl, fcfa):
    """Ajoute la part par ligne (fl FCFA/mois, tableau diffusable)."""
    s = 12 * fl / fcfa
    return o["Ls"] + 0 * s, o["Lc"] + s * o["Ll"], o["Cc"] + s * o["Cl"]


def enumerer(Ls, Lc, Ll, Cc, Cl, kF):
    """Choix par commune, enumeration complete : 256 affectations x 2 options.
    Rend (cout total hors serveur, indice d'affectation, option, lignes totales)."""
    M = MASQUES                                           # (256, 8)
    best = None
    for opt, (L, LL) in enumerate(((Ls, np.zeros_like(Ll)), (Lc, Ll))):
        tot = Cc @ M.T + L @ (1 - M).T                    # (D, 256)
        lig = Cl @ M.T + LL @ (1 - M).T
        tot = tot + kF * (lig > 0)
        i = np.argmin(tot, axis=1)
        t = tot[np.arange(len(i)), i]
        l_ = lig[np.arange(len(i)), i]
        if best is None:
            best = [t, i, np.zeros_like(i), l_]
        else:
            m = t < best[0]
            best = [np.where(m, t, best[0]), np.where(m, i, best[1]), np.where(m, 1, best[2]), np.where(m, l_, best[3])]
    return best


def decomposer(Ls, Lc, Cc, kF):
    """Meme optimum que enumerer(), en forme fermee (pour la carte) ; rend le
    cout et la classe (indice dans CLASSES)."""
    s_sans = Ls.sum(-1)
    b_conv = np.minimum(Cc, Lc).sum(-1)
    d = Cc - Ls
    b_mix = np.minimum(Cc, Ls).sum(-1) + np.where((d < 0).any(-1), 0.0, d.min(-1))
    conv = kF + np.minimum(b_conv, b_mix)
    tot = np.minimum(s_sans, conv)
    n_cell_conv = (Cc < Lc).sum(-1)
    n_cell_mix = np.maximum((Cc < Ls).sum(-1), 1)
    ncell = np.where(b_conv <= b_mix, n_cell_conv, n_cell_mix)
    cl = np.where(s_sans <= conv, 0,
                  np.where(ncell == len(COMMUNES), 3, np.where((ncell == 0) & (b_conv <= b_mix), 1, 2)))
    return tot, cl


def vue_b(o, fl, kF, fcfa):
    """Cout par patient et par an de chaque option, par commune (tirages, communes, 3)."""
    Ls, Lc, Cc = avec_ligne(o, fl, fcfa)
    Ll, Cl, n = o["Ll"], o["Cl"], o["n"]
    t, i, opt, lig = enumerer(Ls, Lc, Ll, Cc, Cl, kF)
    M = MASQUES[i]                                        # (D, 8)
    lig_c = M * Cl + (1 - M) * Ll * opt[:, None]          # lignes de chaque commune dans l'optimum
    autres = lig[:, None] - lig_c
    N = n.sum(-1, keepdims=True)
    serv = o["lns"] * n / N
    res = []
    for cost, li in ((Ls, np.zeros_like(Ll)), (Lc, Ll), (Cc, Cl)):
        part = np.where(li > 0, kF * li / np.maximum(autres + li, 1e-9), 0.0)
        res.append((cost + part + serv) / n)
    return np.stack(res, -1), (t, i, opt, lig)


def libelle_affectation(i, opt):
    m = MASQUES[i]
    lora = [NOMS[c] for c, x in zip(COMMUNES, m) if x == 0]
    if not lora:
        return "tout cellulaire"
    cl = "LoRa " + ("sous convention" if opt else "sans convention") + " : "
    return cl + ("toutes les communes" if len(lora) == len(COMMUNES) else ", ".join(lora) + " ; cellulaire ailleurs")


def q(x, p, axis=0):
    return np.percentile(x, p, axis=axis)


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--placement", default="placement_v62")
    ap.add_argument("--v62", default="resultats/production/cout_v62", help="sorties v6.2 (controles)")
    ap.add_argument("--tirages", type=int, default=500)
    ap.add_argument("--graine", type=int, default=1, help="graine des tirages v6.2")
    ap.add_argument("--graine-v63", type=int, default=63)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--fraction", type=float, default=0.02)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cfg0 = json.load(open(a.config, encoding="utf-8"))
    C = cfg0["cout"]
    CV = C["convention"]
    fcfa = float(C["fcfa_par_eur"])
    cad = float(cfg0["trafic"]["messages_par_jour_cible"])
    prod = os.path.abspath(a.prod)
    journal = []

    def dire(*x):
        s = " ".join(str(y) for y in x)
        print(s, flush=True)
        journal.append(s)

    # --- Scenarios deterministes bas / haut (config tel quel) ---
    det = composantes(cfg0, prod, a.placement, cad, a.fraction)
    Kd = {niv: empiler([det[niv]]) for niv in ("bas", "haut")}
    Pd = {}
    for niv, j in (("bas", 0), ("haut", 1)):
        Pd[niv] = {"p_go": np.array([[CV["fcfa_par_go"][j]]], float), "m": np.array([[CV["marge_operateur"][j]]], float),
                   "fl": np.array([[CV["f_ligne_fcfa_par_mois"][j]]], float),
                   "fpub": np.array([[CV["forfait_public_passerelle_fcfa_par_mois"][j]]], float),
                   "r": np.array([[CV["receptions_par_trame"][j]]], float)}

    # --- Tirages v6.2 regeneres a l'identique (monte_carlo_cout.py) ---
    rnd = random.Random(a.graine)
    centre = copy.deepcopy(cfg0)

    def milieux(d):
        for k, v in d.items():
            if isinstance(v, dict):
                milieux(v)
            elif (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)
                  and not isinstance(v[0], bool)):
                mm = (float(v[0]) + float(v[1])) / 2
                d[k] = [mm, mm]
    milieux(centre["cout"])
    tir = []
    for _ in range(a.tirages):
        cf = copy.deepcopy(centre)
        val = {}
        for lab, ch, b, _ in T.PARAMS:
            lo, hi = T.bornes(cfg0, ch, b)
            v = rnd.choice([0.3, 0.5, 0.7]) if ch == "radio.correlation_ombrage_entre_sites" else rnd.uniform(lo, hi)
            val[lab] = v
            T.poser(cf, ch, [v, v] if isinstance(T.obtenir(cfg0, ch), list) else v)
        tir.append((cf, val))
    dire(f"Evaluation des postes hors connexion pour {len(tir)} tirages v6.2 ...")
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        comps = list(pool.map(lambda t: composantes(t[0], prod, a.placement, cad, a.fraction), tir))
    Km = {niv: empiler([c[niv] for c in comps]) for niv in ("bas", "haut")}
    # Parametres de connexion par tirage.
    r63 = random.Random(a.graine_v63)
    lab_fr = next(l for l, ch, *_ in T.PARAMS if ch.endswith("offre_machine_negociee.frais_fcfa_par_mois"))
    lab_go = next(l for l, ch, *_ in T.PARAMS if ch.endswith("offre_machine_negociee.fcfa_par_go"))
    lab_rem = next(l for l, ch, *_ in T.PARAMS if ch.endswith("remontee_fcfa_par_mois"))
    b_fr = T.bornes(cfg0, "cout.abonnement_cellulaire.scenarios.offre_machine_negociee.frais_fcfa_par_mois", None)
    b_rem = next(b for l, ch, b, _ in T.PARAMS if l == lab_rem)

    def recaler(v, b, c):
        return c[0] + (v - b[0]) / (b[1] - b[0]) * (c[1] - c[0])
    lignes_t = []
    for k, (_, val) in enumerate(tir):
        lignes_t.append({"tirage": k, "p_go": val[lab_go],
                         "fl": recaler(val[lab_fr], b_fr, CV["f_ligne_fcfa_par_mois"]),
                         "fpub": recaler(val[lab_rem], b_rem, CV["forfait_public_passerelle_fcfa_par_mois"]),
                         "m": r63.uniform(*CV["marge_operateur"]), "r": r63.uniform(*CV["receptions_par_trame"]),
                         "frais_v62": val[lab_fr], "remontee_v62": val[lab_rem]})
    Pm = {k: np.array([[l[k]] for l in lignes_t]) for k in ("p_go", "fl", "fpub", "m", "r")}
    ecrire(os.path.join(a.out, "tirages_v63.csv"), [{k: round(v, 4) if isinstance(v, float) else v for k, v in l.items()}
                                                   for l in lignes_t])

    N = float(Kd["bas"]["patients"].sum())
    Fs = [float(x) for x in CV["f_global_fcfa_par_an"]]
    ks = [float(x) for x in CV["facteur_prudence_k"]]

    # ================================================== controles
    ctrl = []
    # Controle 0 : les composantes redonnent la v6.2 (formule v6.2).
    v62_arch = {}
    for r in csv.DictReader(open(os.path.join(a.v62, "cout_architectures.csv"), encoding="utf-8")):
        if float(r["fraction_suivie"]) == a.fraction and float(r["messages_par_jour"]) == cad:
            v62_arch[(r["architecture"], r["mode_ou_abonnement"], r["niveau"])] = float(r["keur_an"])

    def formule_v62(K, ab_override=None, gw_pub=None):
        n, f, u, g, ngw = K["patients"], K["part_ombre_lora"], K["part_sans_couverture"], K["passerelles_secours_cell"], K["passerelles"]
        kL, kC = K["kit_lora_eur_an"], K["kit_cell_eur_an"]
        gw = K["passerelle_hors_remontee_eur_an"] + (K["remontee_v62_eur_an"] if gw_pub is None else gw_pub)
        ab = K["abonnement_machine_v62_eur_an"] if ab_override is None else ab_override
        lns = K["lns_departement_eur_an"][:, :1]
        Nn = n.sum(-1, keepdims=True)
        lora_pp = (1 - f) * (kL + (gw * ngw + lns * n / Nn) / n) + f * (kC + ab)
        nl = u * n
        cell_pp = ((n - nl) * (kC + ab) + nl * kL + g * gw) / n
        # Le bloc 'choix par commune' de la v6.2 pondere le reseau LoRa par
        # (1 - f) (erreur relevee en v6.3) ; l'architecture 'LoRa + secours'
        # de la v6.2 le compte en entier.
        lora_hyb = (n * (1 - f) * kL + n * f * (kC + ab) + gw * ngw).sum(-1) + lns[:, 0]
        return ((np.minimum(lora_pp, cell_pp) * n).sum(-1), lora_hyb, (cell_pp * n).sum(-1) + lns[:, 0])
    dire("\nControle 0 : formule v6.2 appliquee aux composantes contre sorties v6.2 (k EUR/an)")
    for niv in ("bas", "haut"):
        ch_, lo_, ce_ = (x[0] / 1000 for x in formule_v62(Kd[niv]))
        ref = (v62_arch[("choix par commune", "famille la moins chère", niv)],
               v62_arch[("LoRa + secours cellulaire", "mixte à récapitulatif", niv)],
               v62_arch[("cellulaire + secours LoRa", "offre machine négociée", niv)])
        for nom, x, y in zip(("choix par commune", "LoRa + secours", "cellulaire + secours"), (ch_, lo_, ce_), ref):
            dire(f"  {niv:<4} {nom:<22} recalcule {x:8.1f}  v6.2 {y:8.1f}  ecart {x - y:+.1f}")
            ctrl.append({"controle": "0 composantes", "niveau": niv, "grandeur": nom, "v63": round(x, 1),
                         "v62": y, "ecart": round(x - y, 1)})
    mc62 = list(csv.DictReader(open(os.path.join(a.v62, "monte_carlo_cout.csv"), encoding="utf-8")))
    for niv, col in (("bas", "scenario_bas"), ("haut", "kerlink")):
        ch_, _, ce_ = formule_v62(Km[niv])
        # Controle sur les tirages communs avec la v6.2 (500) : au-dela, la suite se prolonge.
        ch_, ce_ = ch_[:len(mc62)], ce_[:len(mc62)]
        e1 = np.abs(ch_ / 1000 - np.array([float(r[f"lora_{col}"]) for r in mc62[:len(ch_)]]))
        e2 = np.abs(ce_ / 1000 - np.array([float(r[f"cell_{col}"]) for r in mc62[:len(ce_)]]))
        dire(f"  tirages v6.2 regeneres, {STRUCT[niv]} : ecart maximal {e1.max():.2f} (choix) et {e2.max():.2f} "
             f"(cellulaire + secours) k EUR/an sur {len(e1)} tirages")
        ctrl.append({"controle": "0 tirages", "niveau": niv, "grandeur": "ecart max choix / cellulaire (k EUR)",
                     "v63": round(float(e1.max()), 2), "v62": 0, "ecart": round(float(e2.max()), 2)})

    # Controle 1 : F = 0, m = 0, f_ligne = 55 / 500.
    dire("\nControle 1 : F_global = 0, m = 0, f_ligne = 55 (bas) / 500 (haut) FCFA, prix du Go 1 228 / 2 048")
    for niv, fl, pgo in (("bas", 55.0, 1228.0), ("haut", 500.0, 2048.0)):
        P = dict(Pd[niv]); P["m"] = np.array([[0.0]]); P["p_go"] = np.array([[pgo]])
        o = couts(Kd[niv], P, cfg0, niv == "haut")
        Ls, Lc, Cc = avec_ligne(o, fl, fcfa)
        # (a) memes conventions que la v6.2 : passerelles au forfait public v6.2,
        # secours en convention, serveur au prorata ; seule la pile change (MQTT).
        ab_mqtt = (Kd[niv]["octets_patient_mois_mqtt"] * 12 * pgo / 1024 ** 3 + 12 * fl) / fcfa
        ch_a, lo_a, ce_a = (x[0] / 1000 for x in formule_v62(Kd[niv], ab_override=ab_mqtt))
        # (b) v6.3 : passerelles dans la convention (asymetrie corrigee).
        lns = float(o["lns"][0, 0])
        t, i, opt, _ = enumerer(Ls, Lc, o["Ll"], Cc, o["Cl"], 0.0)
        res_b = {"choix par commune": (t[0] + lns) / 1000, "LoRa + secours": (Lc.sum() + lns) / 1000,
                 "cellulaire + secours": (Cc.sum() + lns) / 1000}
        ref = {"choix par commune": v62_arch[("choix par commune", "famille la moins chère", niv)],
               "LoRa + secours": v62_arch[("LoRa + secours cellulaire", "mixte à récapitulatif", niv)],
               "cellulaire + secours": v62_arch[("cellulaire + secours LoRa", "offre machine négociée", niv)]}
        for nom, xa in zip(ref, (ch_a, lo_a, ce_a)):
            xb = res_b[nom]
            dire(f"  {niv:<4} {nom:<22} v6.2 {ref[nom]:8.1f} | (a) conventions v6.2, pile MQTT {xa:8.1f} ({xa - ref[nom]:+.1f}) "
                 f"| (b) v6.3, passerelles en convention {xb:8.1f} ({xb - ref[nom]:+.1f})")
            ctrl.append({"controle": "1 reproduction", "niveau": niv, "grandeur": nom, "v62": ref[nom],
                         "v63_conventions_v62": round(xa, 1), "v63": round(xb, 1), "ecart": round(xb - ref[nom], 1)})
        dire(f"       affectation v6.3 (b) : {libelle_affectation(i[0], opt[0])}")

    # Controle 2 : volume annuel.
    dire("\nControle 2 : volume annuel du departement (scenario central : milieu des plages)")
    Pc = {k: (Pd["bas"][k] + Pd["haut"][k]) / 2 for k in Pd["bas"]}
    o = couts(Kd["bas"], Pc, cfg0, False)
    eur_go = float(Pc["p_go"][0, 0]) * (1 + float(Pc["m"][0, 0])) / fcfa
    for nom, v in (("tout LoRa (passerelles + secours)", o["vol_L"].sum()), ("tout cellulaire (ponts + passerelles du secours)", o["vol_C"].sum())):
        go = v / 1024 ** 3
        dire(f"  {nom:<48} {go:7.0f} Go/an, {go * eur_go / 1000:6.2f} k EUR/an au prix du Go majore")
        ctrl.append({"controle": "2 volume", "niveau": "centre", "grandeur": nom, "v63": round(go, 1),
                     "v62": "", "ecart": round(go * eur_go, 0)})
    for nom, vv in (("dont maintien des passerelles", Kd["bas"]["passerelles"].sum() * cfg0["cout"]["remontee_passerelle"]["octets_maintien_par_jour"] * 365),
                    ("dont ponts cellulaires (tous les patients)", (Kd["bas"]["patients"] * Kd["bas"]["octets_patient_mois_mqtt"] * 12).sum())):
        dire(f"    {nom:<46} {vv / 1024 ** 3:7.0f} Go/an")

    # ================================================== vue A
    dep, resume, comm, choixc = [], [], [], []
    dire("\nVue A, departement (EUR par patient et par an)")
    for niv in ("bas", "haut"):
        for src, K, P in (("scénario " + niv, Kd[niv], Pd[niv]), ("Monte-Carlo, " + STRUCT[niv], Km[niv], Pm)):
            o = couts(K, P, cfg0, niv == "haut")
            Ls, Lc, Cc = avec_ligne(o, P["fl"], fcfa)
            lns = o["lns"][:, 0]
            for F in Fs:
                for k in ks:
                    kF = k * F / fcfa
                    t, i, opt, lig = enumerer(Ls, Lc, o["Ll"], Cc, o["Cl"], kF)
                    t2, cl = decomposer(Ls, Lc, Cc, kF)
                    assert np.allclose(t, t2, rtol=1e-9, atol=1e-6), "enumeration et forme fermee divergent"
                    tots = {ARCHS[0]: Ls.sum(-1) + lns, ARCHS[1]: Lc.sum(-1) + kF + lns,
                            ARCHS[2]: Cc.sum(-1) + kF + lns, ARCHS[3]: t + lns}
                    affs = [libelle_affectation(x, y) for x, y in zip(i, opt)]
                    vals, cnt = np.unique(affs, return_counts=True)
                    j = int(np.argmax(cnt))
                    for arch, tot in tots.items():
                        pp = tot / N
                        l = {"source": src, "f_global_fcfa_an": int(F), "k": k, "architecture": arch,
                             "patients": round(N), "eur_patient_an": round(float(np.median(pp)), 2)}
                        if len(pp) > 1:
                            l.update({"moyenne": round(float(pp.mean()), 2), "p2_5": round(float(q(pp, 2.5)), 2),
                                      "p97_5": round(float(q(pp, 97.5)), 2)})
                        l["keur_an"] = round(float(np.median(tot)) / 1000, 1)
                        if arch == "choix par commune":
                            l["affectation_la_plus_frequente"] = vals[j]
                            l["frequence"] = round(cnt[j] / len(affs), 3)
                        dep.append(l)
                    if len(t) > 1 and F == 10e6 and k == 1.0:
                        # Couts par tirage, pour le controle de convergence (analyse/convergence_mc.py).
                        np.savez(os.path.join(a.out, f"tirages_couts_{niv}.npz"), N=N, cl=cl, **{x.replace(" ", "_").replace(",", ""): v for x, v in tots.items()})
                    if len(t) > 1:
                        best_lora = np.minimum(tots[ARCHS[0]], tots[ARCHS[1]])
                        resume.append({"structure": STRUCT[niv], "f_global_fcfa_an": int(F), "k": k, "tirages": len(t),
                                       "p_tout_lora_moins_cher_que_tout_cellulaire": round(float((best_lora < tots[ARCHS[2]]).mean()), 3),
                                       "p_choix_egal_tout_lora_sans_convention": round(float((cl == 0).mean()), 3),
                                       "p_choix_tout_lora_sous_convention": round(float((cl == 1).mean()), 3),
                                       "p_choix_mixte": round(float((cl == 2).mean()), 3),
                                       "p_choix_tout_cellulaire": round(float((cl == 3).mean()), 3),
                                       "economie_choix_vs_meilleure_famille_unique_keur_mediane":
                                           round(float(np.median(np.minimum(best_lora, tots[ARCHS[2]]) - tots[ARCHS[3]])) / 1000, 1),
                                       "affectation_la_plus_frequente": vals[j], "frequence": round(cnt[j] / len(affs), 3)})
                    # Vue B
                    vb, _ = vue_b(o, P["fl"], kF, fcfa)
                    for ci, c in enumerate(COMMUNES):
                        for oi, op in enumerate(OPTIONS):
                            x = vb[:, ci, oi]
                            l = {"source": src, "f_global_fcfa_an": int(F), "k": k, "commune": c, "zone": det["bas"][c]["zone"],
                                 "patients": round(float(K["patients"][0, ci])), "option": op,
                                 "eur_patient_an": round(float(np.median(x)), 2)}
                            if len(x) > 1:
                                l.update({"moyenne": round(float(x.mean()), 2), "p2_5": round(float(q(x, 2.5)), 2),
                                          "p97_5": round(float(q(x, 97.5)), 2)})
                            comm.append(l)
                        win = np.argmin(vb[:, ci, :], axis=1)
                        fam = np.where(win == 2, "cellulaire", "LoRa")
                        vv, cc = np.unique(fam, return_counts=True)
                        jj = int(np.argmax(cc))
                        choixc.append({"source": src, "f_global_fcfa_an": int(F), "k": k, "commune": c,
                                       "gagnant": vv[jj], "part_des_tirages": round(cc[jj] / len(fam), 3),
                                       "part_lora_sans_convention": round(float((win == 0).mean()), 3),
                                       "part_lora_sous_convention": round(float((win == 1).mean()), 3),
                                       "part_cellulaire": round(float((win == 2).mean()), 3)})
    # gagnants v6.2
    g62 = {}
    for r in csv.DictReader(open(os.path.join(a.v62, "choix_communes.csv"), encoding="utf-8")):
        if float(r["fraction_suivie"]) == a.fraction and float(r["messages_par_jour"]) == cad:
            g62[(r["commune"], r["niveau"])] = "LoRa" if r["choix"].startswith("LoRa") else "cellulaire"
    for l in choixc:
        niv = "haut" if ("haut" in l["source"] or "Kerlink" in l["source"]) else "bas"
        l["gagnant_v62_" + "scenario"] = g62.get((l["commune"], niv), "")
    ecrire(os.path.join(a.out, "cout_departement_v63.csv"), dep)
    ecrire(os.path.join(a.out, "cout_communes_v63.csv"), comm)
    ecrire(os.path.join(a.out, "choix_communes_v63.csv"), choixc)
    ecrire(os.path.join(a.out, "monte_carlo_resume_v63.csv"), resume)
    for l in dep:
        if l["k"] == 1.0 and l["f_global_fcfa_an"] in (0, 10000000, 50000000):
            dire(f"  {l['source']:<34} F={l['f_global_fcfa_an'] / 1e6:4.0f} M  {l['architecture']:<34} "
                 f"{l['eur_patient_an']:7.2f}" + (f" [{l['p2_5']}-{l['p97_5']}]" if "p2_5" in l else "")
                 + (f"  {l['affectation_la_plus_frequente']} ({l['frequence']:.0%})" if "frequence" in l else ""))

    # ================================================== seuils
    seuils = []
    dire("\nSeuils")
    for niv in ("bas", "haut"):
        for src, K, P in (("scénario " + niv, Kd[niv], Pd[niv]), ("Monte-Carlo, " + STRUCT[niv], Km[niv], Pm)):
            o = couts(K, P, cfg0, niv == "haut")
            Ls, Lc, Cc = avec_ligne(o, P["fl"], fcfa)
            s_sans = Ls.sum(-1)
            d = Cc - Ls
            b_mix = np.minimum(Cc, Ls).sum(-1) + np.where((d < 0).any(-1), 0.0, d.min(-1))
            b = np.minimum(np.minimum(Cc, Lc).sum(-1), b_mix)
            for k in ks:
                fst = np.maximum(0.0, (s_sans - b) / k) * fcfa
                l = {"seuil": "F_global*", "source": src, "k": k, "commune": "département",
                     "f_global_fcfa_an": "", "valeur_fcfa": round(float(np.median(fst))),
                     "valeur_fcfa_par_patient_mois": round(float(np.median(fst)) / N / 12, 1)}
                if len(fst) > 1:
                    l.update({"p2_5": round(float(q(fst, 2.5))), "p97_5": round(float(q(fst, 97.5))),
                              "part_tirages_f_nul": round(float((fst == 0).mean()), 3)})
                seuils.append(l)
                dire(f"  F* {src:<34} k={k:<3} {l['valeur_fcfa'] / 1e6:6.1f} M FCFA/an ({l['valeur_fcfa_par_patient_mois']} FCFA/patient/mois)"
                     + (f" [{l['p2_5'] / 1e6:.1f}-{l['p97_5'] / 1e6:.1f}]" if "p2_5" in l else ""))
            # f_ligne* par commune.
            grille = np.arange(0, 5001, 5.0)
            for F in (0.0, 10e6):
                kF = F / fcfa
                gagne = np.zeros((len(grille), Ls.shape[0], len(COMMUNES)), bool)
                for gi, fl in enumerate(grille):
                    vb, _ = vue_b(o, np.full_like(P["fl"], fl), kF, fcfa)
                    gagne[gi] = np.minimum(vb[..., 0], vb[..., 1]) <= vb[..., 2]
                for ci, c in enumerate(COMMUNES):
                    g_ = gagne[:, :, ci]
                    first = np.where(g_.any(0), np.argmax(g_, axis=0), -1)
                    fst = np.where(first >= 0, grille[np.maximum(first, 0)], np.inf)
                    l = {"seuil": "f_ligne*", "source": src, "k": 1.0, "commune": c, "f_global_fcfa_an": int(F),
                         "valeur_fcfa": med_txt(fst), "valeur_fcfa_par_patient_mois": ""}
                    if len(fst) > 1:
                        l.update({"p2_5": med_txt(fst, 2.5), "p97_5": med_txt(fst, 97.5),
                                  "part_tirages_f_nul": round(float((fst == 0).mean()), 3)})
                    seuils.append(l)
            dire(f"  f_ligne* {src}: " + " ; ".join(f"{NOMS[l['commune']]} {l['valeur_fcfa']}" for l in seuils[-16:-8])
                 + "  (F=0) | F=10 M : " + " ; ".join(f"{NOMS[l['commune']]} {l['valeur_fcfa']}" for l in seuils[-8:]))
    ecrire(os.path.join(a.out, "seuils_convention_v63.csv"), seuils)
    ecrire(os.path.join(a.out, "controles_v63.csv"), ctrl)

    # Controle 3 : somme / somme contre moyenne des couts par commune.
    o = couts(Kd["bas"], Pd["bas"], cfg0, False)
    Ls, Lc, Cc = avec_ligne(o, Pd["bas"]["fl"], fcfa)
    lns = float(o["lns"][0, 0])
    som = (Cc.sum() + lns) / N
    moy = float(np.mean((Cc + lns * o["n"] / N) / o["n"]))
    dire(f"\nControle 3 : tout cellulaire, scenario bas, F = 0 : somme des couts / somme des patients {som:.2f} EUR ; "
         f"moyenne simple des couts par patient des communes {moy:.2f} EUR (non utilisee)")
    open(os.path.join(a.out, "controles_v63.txt"), "w", encoding="utf-8").write("\n".join(journal) + "\n")

    # ================================================== figures
    figures(cfg0, Km, Pm, N, fcfa, a.out)


def med_txt(x, p=50):
    v = float(np.percentile(np.where(np.isinf(x), 1e12, x), p))
    return "> 5000" if v > 1e11 else round(v)


def ecrire(chemin, lignes):
    if lignes:
        champs = []
        for l in lignes:
            for k in l:
                if k not in champs:
                    champs.append(k)
        with open(chemin, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=champs)
            w.writeheader()
            w.writerows(lignes)


def style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "STIXGeneral", "mathtext.fontset": "stix", "xtick.direction": "in",
                         "ytick.direction": "in", "xtick.top": True, "ytick.right": True, "font.size": 9})
    return plt


def figures(cfg, Km, Pm, N, fcfa, out):
    plt = style()
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    COUL = ["#b4561c", "#e7b58f", "#d9dee6", "#2c6491"]
    ks = [float(x) for x in cfg["cout"]["convention"]["facteur_prudence_k"]]
    Fg = np.arange(0, 300.01e6, 5e6)
    fg = np.arange(0, 3000.1, 50)
    fig, axes = plt.subplots(2, len(ks), figsize=(10.5, 7), sharex=True, sharey=True)
    for ri, niv in enumerate(("bas", "haut")):
        o = couts(Km[niv], Pm, cfg, niv == "haut")
        for ci, k in enumerate(ks):
            ax = axes[ri, ci]
            mode = np.zeros((len(fg), len(Fg)), int)
            accord = np.zeros((len(fg), len(Fg)))
            for yi, fl in enumerate(fg):
                Ls, Lc, Cc = avec_ligne(o, np.full_like(Pm["fl"], fl), fcfa)
                for xi, F in enumerate(Fg):
                    _, cl = decomposer(Ls, Lc, Cc, k * F / fcfa)
                    cnt = np.bincount(cl, minlength=4)
                    mode[yi, xi] = int(np.argmax(cnt))
                    accord[yi, xi] = cnt.max() / len(cl)
            ax.pcolormesh(Fg / 1e6, fg, mode, cmap=ListedColormap(COUL), vmin=-0.5, vmax=3.5, shading="nearest")
            ax.contourf(Fg / 1e6, fg, (accord < 0.95).astype(float), levels=[0.5, 1.5], colors="none",
                        hatches=["////"])
            ax.contour(Fg / 1e6, fg, accord, levels=[0.95], colors="#0b0b0b", linewidths=0.8)
            ax.axhspan(66, 800, xmin=0, xmax=0.015, color="#0b0b0b")
            ax.axvline(50, color="#0b0b0b", linewidth=0.8, linestyle=(0, (4, 3)))
            ax.set_title(f"{STRUCT[niv]}, k = {k:g}", fontsize=12, loc="left")
            if ri == 1:
                ax.set_xlabel("forfait global annuel (millions de FCFA)", fontsize=12)
            if ci == 0:
                ax.set_ylabel("redevance mensuelle par ligne (FCFA)", fontsize=12)
    hs = [Patch(color=c, label=l) for c, l in zip(COUL, CLASSES)]
    hs.append(Patch(facecolor="white", edgecolor="#0b0b0b", hatch="////",
                    label="moins de 95 % des tirages d'accord"))
    fig.legend(handles=hs, loc="lower center", ncol=3, frameon=False, fontsize=12)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(out, f"fig_carte_convention_v63.{ext}"), dpi=200)
    plt.close(fig)

    # Cout par commune en fonction de F_global (vue B), k = 1, scenario bas detaille.
    o = couts(Km["bas"], Pm, cfg, False)
    Fl = np.arange(0, 50.01e6, 2.5e6)
    res = np.stack([vue_b(o, Pm["fl"], F / fcfa, fcfa)[0] for F in Fl])  # (F, D, 8, 3)
    COUL3 = ["#2a78d6", "#1baf7a", "#eb6834"]
    fig, axes = plt.subplots(2, 4, figsize=(12, 6.2), sharex=True)
    for ci, (c, ax) in enumerate(zip(COMMUNES, axes.flat)):
        for oi, op in enumerate(OPTIONS):
            x = res[:, :, ci, oi]
            ax.fill_between(Fl / 1e6, q(x, 2.5, 1), q(x, 97.5, 1), color=COUL3[oi], alpha=0.15, linewidth=0)
            ax.plot(Fl / 1e6, x.mean(1), color=COUL3[oi], linewidth=1.6, label=op)
        ax.set_title(NOMS[c], fontsize=9, loc="left")
        if ci >= 4:
            ax.set_xlabel("F_global (M FCFA/an)")
        if ci % 4 == 0:
            ax.set_ylabel("€ par patient et par an")
    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, frameon=False, fontsize=8.5)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(out, f"fig_cout_par_commune_v63.{ext}"), dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    main()
