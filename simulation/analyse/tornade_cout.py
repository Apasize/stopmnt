#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tornade_cout.py

Consignes v4, point 11 : analyse de sensibilite en tornade sur le cout
departemental (fraction suivie et cadence centrales du config).

Cas central : chaque plage [bas, haut] de la liste PARAMS ramenee a son
milieu ; passerelle au scenario 'bas' de la couche cout (installation +
remontee, alimentation de secours si active). Puis chaque parametre est varie
seul a sa borne basse et a sa borne haute, les autres au centre.

Grandeurs suivies (k EUR par an, departement) :
  LoRa      : montre BLE + pont LoRa, tout confirme RX2 ;
  cellulaire: montre BLE + pont cellulaire, offre machine negociee ;
  ecart     : LoRa - cellulaire. Le verdict bascule si l'ecart change de signe.
La couche cout est relancee telle quelle (analyse/couche_cout.py) sur une copie
du config modifiee : aucune valeur n'est recopiee ici, seules les cles et les
bornes des hypotheses sans plage dans le config (marquees HYPOTHESE) le sont.

Sorties : tornade_cout.csv, tornade_cout.png/pdf.
"""
import argparse
import copy
import csv
import json
import os
import subprocess
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ICI = os.path.dirname(os.path.abspath(__file__))
RX2_14 = False  # scenario RX2 a 14 dBm (option --scenario-rx2-14dbm)
EXTRA = []      # options supplementaires passees a la couche cout
# Architectures comparees (architecture, mode ou abonnement). Par defaut : LoRa
# tout confirme contre pont cellulaire avec offre machine ; --hybrides :
# LoRa + secours cellulaire (mixte a recapitulatif) contre cellulaire + secours LoRa.
LORA_ARCH = ("LoRa", "tout confirmé RX2")
CELL_ARCH = ("cellulaire", "offre machine négociée")

# (libelle, chemin dans le config, bornes ou None = plage [bas, haut] du config, statut)
PARAMS = [
    ("Remplacement annuel des kits (10 à 20 %)", "cout.kit_patient.remplacement_annuel", None, "hypothèse bornée"),
    ("Montre BLE (29 à 40 €)", "cout.kit_patient.montre_ble_eur", None, "catalogue"),
    ("Boîtier du pont (5 à 35,9 €)", "cout.kit_patient.pont_lora.boitier_eur", None, "hypothèse / catalogue"),
    ("Offre machine : frais (55 à 500 FCFA/mois)", "cout.abonnement_cellulaire.scenarios.offre_machine_negociee.frais_fcfa_par_mois", None, "1NCE / hypothèse"),
    ("Offre machine : prix du Go (1 228 à 2 048 FCFA)", "cout.abonnement_cellulaire.scenarios.offre_machine_negociee.fcfa_par_go", None, "ARCEP mars 2026"),
    ("Serveur LoRaWAN (3,79 à 7,99 €/mois)", "cout.serveur_lns_eur_par_mois", None, "catalogue"),
    ("Passerelle avec secours (830 à 1 279 $)", "cout.passerelle.alimentation_secours.materiel_avec_secours_usd", None, "catalogue"),
    ("Installation passerelle (250 à 1 000 €)", "cout.passerelle.scenario_bas.installation_eur_hypothese", [250.0, 1000.0], "hypothèse bornée"),
    ("Remontée passerelle (1 000 à 5 000 FCFA/mois)", "cout.passerelle.scenario_bas.remontee_fcfa_par_mois", [1000.0, 5000.0], "hypothèse bornée"),
    ("Amortissement (3 à 7 ans)", "cout.amortissement_ans", [3.0, 7.0], "hypothèse bornée"),
    ("Taux de change (0,85 à 1,00 € par $)", "cout.eur_par_usd", [0.85, 1.0], "hypothèse bornée"),
    ("Capacité par passerelle (x 0,70 à x 1,25)", "cout.facteur_capacite", [0.70, 1.25], "simulé (marge RX1, nbTrans)"),
    ("Corrélation entre sites (0,3 à 0,7)", "radio.correlation_ombrage_entre_sites", [0.3, 0.7], "décision P, balayée"),
    ("Exploitation : administration (0,25 à 1 ETP)", "cout.exploitation_reseau.administration_etp", None, "hypothèse bornée"),
    ("Exploitation : salaire chargé (300 000 à 600 000 FCFA/mois)", "cout.exploitation_reseau.salaire_mensuel_charge_fcfa", None, "hypothèse bornée"),
    ("Exploitation : visites par passerelle (1 à 2 par an)", "cout.exploitation_reseau.visites_par_passerelle_par_an", None, "hypothèse bornée"),
    ("Exploitation : coût d'une visite (25 à 100 €)", "cout.exploitation_reseau.cout_visite_eur", None, "hypothèse bornée"),
]
# Variantes a deux etats (sans / avec), autour du cas central.
BASCULES = [
    ("Marge de robustesse (sans / avec)", "cout.marge_robustesse.appliquer", [False, True], "simulé (panne centrale)"),
    ("Alimentation de secours (sans / avec)", "cout.passerelle.alimentation_secours.appliquer", [False, True], "catalogue"),
]


def obtenir(d, chemin):
    for k in chemin.split("."):
        d = d[k]
    return d


def poser(d, chemin, v):
    ks = chemin.split(".")
    for k in ks[:-1]:
        d = d[k]
    d[ks[-1]] = v


def bornes(cfg, chemin, b):
    if b is not None:
        return b
    v = obtenir(cfg, chemin)
    return [float(v[0]), float(v[1])]


def evaluer(cfg, prod, fr, cad, niveau="bas"):
    with tempfile.TemporaryDirectory() as tmp:
        ch = os.path.join(tmp, "config.json")
        json.dump(cfg, open(ch, "w", encoding="utf-8"), ensure_ascii=False)
        out = os.path.join(tmp, "cout")
        subprocess.run([sys.executable, os.path.join(ICI, "couche_cout.py"), "--config", ch, "--prod", prod,
                        "--out", out, "--sans-figure"] + (["--scenario-rx2-14dbm"] if RX2_14 else []) + EXTRA, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        res = {}
        for r in csv.DictReader(open(os.path.join(out, "cout_architectures.csv"), encoding="utf-8")):
            if (float(r["fraction_suivie"]) == fr and float(r["messages_par_jour"]) == cad and r["niveau"] == niveau):
                if (r["architecture"], r["mode_ou_abonnement"]) == LORA_ARCH:
                    res["lora"] = float(r["keur_an"])
                    res["statut"] = r.get("statut_mesure", "")
                if (r["architecture"], r["mode_ou_abonnement"]) == CELL_ARCH:
                    res["cell"] = float(r["keur_an"])
        res["ecart"] = res["lora"] - res["cell"]
        return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--fraction", type=float, default=0.02)
    ap.add_argument("--suffixe", default="")
    ap.add_argument("--scenario-rx2-14dbm", action="store_true")
    ap.add_argument("--espacement-alerte", action="store_true")
    ap.add_argument("--hybrides", action="store_true")
    ap.add_argument("--choix", action="store_true", help="reseau choisi commune par commune contre cellulaire + secours")
    ap.add_argument("--placement", default=None)
    ap.add_argument("--options-cout", nargs="*", default=[], help="options supplementaires de couche_cout (sans tirets initiaux)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    global RX2_14, EXTRA, LORA_ARCH, CELL_ARCH
    RX2_14 = a.scenario_rx2_14dbm
    if a.hybrides:
        LORA_ARCH = ("LoRa + secours cellulaire", "mixte à récapitulatif")
        CELL_ARCH = ("cellulaire + secours LoRa", "offre machine négociée")
    if a.choix:
        LORA_ARCH = ("choix par commune", "famille la moins chère")
        CELL_ARCH = ("cellulaire + secours LoRa", "offre machine négociée")
    EXTRA = (["--espacement-alerte"] if a.espacement_alerte else []) + (["--placement", a.placement] if a.placement else [])
    EXTRA += ["--" + o for o in a.options_cout]
    cfg0 = json.load(open(a.config, encoding="utf-8"))
    cad = float(cfg0["trafic"]["messages_par_jour_cible"])
    prod = os.path.abspath(a.prod)
    centre = copy.deepcopy(cfg0)
    # Toute plage [bas, haut] du bloc cout ramenee a son milieu, pour que le
    # cas central ne melange pas les bornes des parametres non varies.
    def milieux(d):
        for k, v in d.items():
            if isinstance(v, dict):
                milieux(v)
            elif (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)
                  and not isinstance(v[0], bool)):
                m = (float(v[0]) + float(v[1])) / 2
                d[k] = [m, m]
    milieux(centre["cout"])
    for _, ch, b, _ in PARAMS:
        lo, hi = bornes(cfg0, ch, b)
        v = obtenir(cfg0, ch)
        m = (lo + hi) / 2
        poser(centre, ch, [m, m] if isinstance(v, list) else m)
    c = evaluer(centre, prod, a.fraction, cad)
    lignes = []
    for lab, ch, b, st in PARAMS + BASCULES:
        vals = b if ch in [x[1] for x in BASCULES] else bornes(cfg0, ch, b)
        res = []
        for v in vals:
            cf = copy.deepcopy(centre)
            if isinstance(obtenir(cfg0, ch), list):
                v = [v, v]
            poser(cf, ch, v)
            res.append(evaluer(cf, prod, a.fraction, cad))
        lignes.append({"parametre": lab, "statut": st, "borne_basse": vals[0], "borne_haute": vals[1],
                       "lora_bas": res[0]["lora"], "lora_haut": res[1]["lora"],
                       "cell_bas": res[0]["cell"], "cell_haut": res[1]["cell"],
                       "ecart_bas": round(res[0]["ecart"], 1), "ecart_haut": round(res[1]["ecart"], 1),
                       "bascule_verdict": (res[0]["ecart"] > 0) != (c["ecart"] > 0) or (res[1]["ecart"] > 0) != (c["ecart"] > 0)})
        print(lignes[-1], flush=True)
    # Passerelle : scenario 'haut' (Kerlink, materiel = 10 % du cout total).
    k = evaluer(centre, prod, a.fraction, cad, niveau="haut")
    lignes.append({"parametre": "Coût total de la passerelle (installation + secours / Kerlink 10 %)", "statut": "hypothèse / constructeur",
                   "borne_basse": "scénario bas", "borne_haute": "Kerlink", "lora_bas": c["lora"], "lora_haut": k["lora"],
                   "cell_bas": c["cell"], "cell_haut": k["cell"], "ecart_bas": round(c["ecart"], 1),
                   "ecart_haut": round(k["ecart"], 1), "bascule_verdict": (k["ecart"] > 0) != (c["ecart"] > 0)})
    lignes.sort(key=lambda l: abs(l["ecart_haut"] - l["ecart_bas"]))
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, f"tornade_cout{a.suffixe}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cas_central_lora_keur", "cas_central_cell_keur", "cas_central_ecart_keur"]
                           + list(lignes[0].keys()))
        w.writeheader()
        for l in lignes:
            w.writerow({"cas_central_lora_keur": c["lora"], "cas_central_cell_keur": c["cell"],
                        "cas_central_ecart_keur": round(c["ecart"], 1), **l})

    fig, ax = plt.subplots(figsize=(10, 6), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for i, l in enumerate(lignes):
        lo, hi = l["ecart_bas"], l["ecart_haut"]
        ax.barh(i, hi - c["ecart"], left=c["ecart"], color="#eb6834", height=0.6)
        ax.barh(i, lo - c["ecart"], left=c["ecart"], color="#2a78d6", height=0.6)
        if l["bascule_verdict"]:
            ax.text(max(lo, hi) + 15, i, "bascule", va="center", fontsize=8, color="#0b0b0b", fontweight="bold")
    ax.axvline(c["ecart"], color="#0b0b0b", linewidth=1)
    ax.axvline(0, color="#52514e", linewidth=1, linestyle=(0, (4, 3)))
    ax.set_yticks(range(len(lignes)))
    ax.set_yticklabels([l["parametre"] for l in lignes], fontsize=8)
    ax.set_xlabel("écart LoRa (tout confirmé RX2) - pont cellulaire (offre machine), k€ par an ; "
                  "négatif : LoRa moins cher", fontsize=8)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.grid(True, axis="x", color="#e4e3df", linewidth=0.6)
    ax.tick_params(labelsize=8)
    fig.text(0.01, 0.01, f"Département, {100 * a.fraction:g} % de la population suivie, {cad:.0f} messages par jour. "
             f"Cas central : LoRa {c['lora']:.0f} k€/an, pont cellulaire {c['cell']:.0f} k€/an. "
             "Bleu : borne basse du paramètre ; orange : borne haute.", fontsize=7.5, color="#52514e")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(a.out, f"tornade_cout{a.suffixe}.{ext}"), dpi=200, facecolor="#fcfcfb")
    print("central", c)


if __name__ == "__main__":
    main()
