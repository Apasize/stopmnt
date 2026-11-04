#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
couche_cout.py

Couche cout et bascule (section 5.5), de bout en bout et a bases egales :
du patient (montre BLE + intermediaire) jusqu'au serveur.

Familles et intermediaires compares :
  LoRa       : montre BLE + pont LoRa -> passerelle -> remontee de la passerelle
               -> serveur reseau LoRaWAN -> serveur de sante
  cellulaire : montre BLE + pont cellulaire -> reseau operateur -> serveur de sante
  telephone  : montre BLE + smartphone (celui du patient ou fourni) -> reseau
               operateur -> serveur de sante (surcouche cellulaire du cadrage)
Le serveur de sante est commun et n'est pas compte.

Entrees : config.json (bloc cout, trafic.messages_par_jour_cible et _majore),
capacites simulees (capacite_modes_5dBi a 7 messages par jour, corrigees par
capacite_cadence a 10 et 15), densite de passerelles (multi-passerelles),
energie LoRa mesuree (capacite_longue_7j).

Sorties dans --out : besoin_donnees.csv, kit_patient.csv, cout_communes.csv,
cout_departement.csv, cout_bascule.csv, energie_cellulaire.csv,
remontee_passerelle.csv, cout_par_patient.png/.pdf, et un resume a l'ecran.
"""

import argparse
import csv
import glob
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "orchestrateur"))
import run_experiences as R  # noqa: E402

MODES = ["tout_non_confirme", "mixte_rx2", "mixte_recap_rx2", "tout_confirme_rx2"]
# Consignes v4, point 12 : montres qui annoncent une tension arterielle estimee
# par algorithme (non mesuree au brassard) ; principe rejete par Brian et Ogore
# (2025, reference donnee par l'auteur dans les consignes v4). Chiffrees, mais
# hors du classement principal.
HORS_CLASSEMENT = {"cellulaire, montre 4G directe": "tension estimee, non mesuree",
                   "LoRa, montre LoRaWAN directe": "tension par montre sans brassard, methode non documentee"}
LIB_MODE = {"tout_non_confirme": "sans accusé", "mixte": "mixte", "mixte_rx2": "mixte RX2",
            "mixte_recap_rx2": "mixte à récapitulatif",
            "tout_confirme": "tout confirmé", "tout_confirme_rx2": "tout confirmé RX2"}


def val(x):
    if x in (None, "", "None"):
        return None, False
    if str(x).startswith(">"):
        return float(str(x)[1:]), True
    return float(x), False


def capacites(chemin):
    """Capacite par (zone, mode, messages) : croisement le plus contraignant."""
    out = {}
    if not os.path.exists(chemin):
        return out
    for r in csv.DictReader(open(chemin, encoding="utf-8")):
        m = re.search(r"mode=([a-z_0-9]+)", r["variante"])
        mode = m.group(1) if m else "mixte"
        mm = re.search(r"messages=([0-9.]+)", r["variante"])
        msg = float(mm.group(1)) if mm else 7.0
        base = mode.replace("_rx2", "")
        crit = {"tout_non_confirme": ["capacite_interpolee_livraison"],
                "mixte": ["capacite_interpolee_livraison", "capacite_interpolee_delai_alerte"],
                "mixte_recap": ["capacite_interpolee_livraison", "capacite_interpolee_delai_alerte"],
                "tout_confirme": ["capacite_interpolee_delai_routine", "capacite_interpolee_delai_alerte"]}[base]
        vs = [v for v in (val(r[c]) for c in crit) if v[0] is not None]
        if vs:
            out[(r["zone"], mode, msg)] = min(vs, key=lambda v: v[0])
    return out


def capacite(caps, zone, mode, msg):
    """Capacite a la cadence msg : mesuree si disponible, sinon capacite a 7
    messages corrigee par le rapport moyen mesure sur les zones simulees."""
    if (zone, mode, msg) in caps:
        return caps[(zone, mode, msg)]
    base = caps.get((zone, mode, 7.0))
    if base is None:
        return None, False
    rapports = [caps[(z, m, g)][0] / caps[(z, m, 7.0)][0] for (z, m, g) in caps
                if m == mode and g == msg and (z, m, 7.0) in caps and caps[(z, m, 7.0)][0] > 0]
    if not rapports:
        return base
    r = sum(rapports) / len(rapports)
    return base[0] * r, base[1]


def bas_haut(x):
    return (float(x[0]), float(x[1])) if isinstance(x, list) else (float(x), float(x))


def messages(cfg, cible):
    """(messages de donnees, octets) par profil, a la cadence cible (alerte comprise)."""
    pp = cfg["profils_patients"]
    al = pp.get("alerte", {})
    n_al = float(al.get("alertes_par_jour", 0)) if al.get("actif") else 0.0
    mel = dict(pp["melange_base"])
    base = sum(mel[k] * float(pp["profils"][k]["uplinks_par_jour"]) for k in mel)
    f = (cible - n_al) / base
    prof = {k: [(float(p["uplinks_par_jour"]) * f, int(p["octets_charge"])), (n_al, int(al.get("octets_charge", 0)))]
            for k, p in pp["profils"].items()}
    return prof, mel


def besoin(cfg, cible):
    ab = cfg["cout"]["abonnement_cellulaire"]
    prof, mel = messages(cfg, cible)
    out = []
    for pile, P in ab["besoin"]["piles"].items():
        for arr in ab["besoin"]["arrondi_facturation_octets"]:
            pp = {}
            for nom, flux in prof.items():
                j = float(P["fixe_par_jour"])
                for n, o in flux:
                    m = P["montant_par_message"] + o + P["descendant_par_message"]
                    j += n * (math.ceil(m / arr) * arr if arr else m)
                pp[nom] = 30 * j
            pp["melange_base"] = sum(mel[k] * pp[k] for k in mel)
            for nom, o in pp.items():
                out.append({"messages_par_jour": cible, "pile": pile, "libelle": P["libelle"], "arrondi_octets": arr,
                            "profil": nom, "ko_par_mois": round(o / 1024, 1)})
    return out


def main():
    ap = argparse.ArgumentParser(description="Couche cout de bout en bout")
    ap.add_argument("--config", required=True)
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--out", default="resultats/production/cout")
    ap.add_argument("--espacement-alerte", action="store_true",
                    help="espacement des passerelles fixe par l'exigence d'alerte (consignes v6)")
    ap.add_argument("--mat", choices=["neuf", "partage"], default=None, help="variante 30 m : cout du mat")
    ap.add_argument("--population-variante", action="store_true", help="totaux WorldPop 2021 (So-Ava recale)")
    ap.add_argument("--melange", default=None,
                    help="dossier des parts arborees (couvert_arbore_*.csv) : pavage en melange de zones")
    ap.add_argument("--placement", default=None,
                    help="dossier des placements PLNE (placement_plne_*.csv) : remplace le pavage, commune par commune")
    ap.add_argument("--sans-figure", action="store_true", help="ne pas tracer (appels repetes : tornade, Monte-Carlo)")
    ap.add_argument("--composantes", action="store_true",
                    help="v6.3 : ecrit composantes.csv (postes hors connexion, par commune) pour analyse/convention_v63.py")
    ap.add_argument("--scenario-rx2-14dbm", action="store_true",
                    help="RX2 a 14 dBm : tout confirme en cellules dimensionnees sur la voie descendante")
    a = ap.parse_args()
    cfg = R.charger_config(os.path.expanduser(a.config))
    C = cfg["cout"]
    if a.population_variante:
        for k, v in C["population_variante_2021"].items():
            if not k.startswith("_"):
                C["communes"][k]["population_2013"] = v
    usd, fcfa, A = float(C["eur_par_usd"]), float(C["fcfa_par_eur"]), float(C["amortissement_ans"])
    cadences = [float(cfg["trafic"]["messages_par_jour_cible"]), float(cfg["trafic"]["messages_par_jour_majore"])]
    os.makedirs(a.out, exist_ok=True)
    go = 1024 ** 3

    # --- Kit patient (bas, haut), euros ---
    K = C["kit_patient"]
    pl, pc = K["pont_lora"], K["pont_cellulaire_en_plus"]
    montre = bas_haut(K["montre_ble_eur"])
    boit, antl, piles = bas_haut(pl["boitier_eur"]), bas_haut(pl["antenne_eur"]), bas_haut(pl["piles_eur"])
    coeur = (pl["module_usd"] + pl["carte_base_usd"]) * usd
    pont_lora = tuple(coeur + boit[i] + antl[i] + piles[i] for i in (0, 1))
    sim = bas_haut(pc["carte_sim_fcfa"])
    antc = bas_haut(pc["antenne_lte_eur"])
    pont_cell = tuple(coeur + boit[i] + piles[i] + pc["module_lte_eur"] + antc[i] + sim[i] / fcfa for i in (0, 1))
    tel_fourni = bas_haut(K["telephone_relais_usd"])[1] * usd
    remp = bas_haut(K["remplacement_annuel"])
    kits = {"LoRa": tuple(montre[i] + pont_lora[i] for i in (0, 1)),
            "cellulaire": tuple(montre[i] + pont_cell[i] for i in (0, 1)),
            "téléphone du patient": montre,
            "téléphone fourni": tuple(montre[i] + tel_fourni for i in (0, 1))}
    # Equipements finis du commerce (remarque de l'auteur) : architectures
    # alternatives, a cote du pont fabrique a partir de composants.
    EQ = C.get("equipements_commerce", {})
    if EQ:
        # Seuls les equipements utilisables au Benin entrent dans la comparaison
        # (bandes, frequences, operateurs : disponibilite_benin du config).
        kits["LoRa, montre BLE + pont du commerce (EU868 à confirmer)"] = tuple(montre[i] + EQ["pont_lora_commerce_usd"] * usd for i in (0, 1))
        kits["LoRa, montre LoRaWAN directe"] = (EQ["montre_lorawan_directe_usd"] * usd,) * 2
        kits["cellulaire, montre 4G directe"] = tuple(x * usd for x in EQ["montre_4g_directe_usd"])
        print("Exclus (non utilisables au Benin) : tensiometre 4G americain, hub cellulaire americain.")
    kit_an = {k: (v[0] / A + v[0] * remp[0], v[1] / A + v[1] * remp[1]) for k, v in kits.items()}
    # Ponts autonomes sur pile : remplacements de piles par an d'apres l'energie
    # radio a la cadence cible (MCU et BLE communs, non comptes).
    en0 = C["energie_cellulaire"]
    pile_j0 = en0["pile"]["capacite_mah"] / 1000 * 3600 * en0["pile"]["tension_v"]
    cad0 = float(cfg["trafic"]["messages_par_jour_cible"])
    eteint0 = en0["courant_eteint_a"] * en0["tension_v"] * 86400
    e_cell = (eteint0 + cad0 * en0["energie_rattachement_j"][0], eteint0 + cad0 * en0["energie_rattachement_j"][1])
    lora_mes = energie_lora_mesuree(a.prod)
    e_lora = max(lora_mes.values()) * cad0 / 7.0 if lora_mes else 1.0
    piles_eur = bas_haut(K["pont_lora"]["piles_eur"])
    piles_an = {"cellulaire": (e_cell[0] * 365 / pile_j0 * piles_eur[0], e_cell[1] * 365 / pile_j0 * piles_eur[1]),
                "LoRa": (e_lora * 365 / pile_j0 * piles_eur[0], e_lora * 365 / pile_j0 * piles_eur[1])}
    # Batteries rechargeables : pas de cout de remplacement, on rapporte
    # l'intervalle entre deux recharges (radio seule).
    veille0 = en0["courant_veille_enregistre_a"] * en0["tension_v"] * 86400
    e_reg = (veille0 + cad0 * en0["energie_par_message_connecte_j"][0], veille0 + cad0 * en0["energie_par_message_connecte_j"][1])
    print(f"Jours entre deux recharges (batterie {pile_j0 / 1000:.1f} kJ, radio seule, {cad0:.0f} msg/j) : "
          f"pont cellulaire eteint entre deux messages {pile_j0 / e_cell[1]:.0f} a {pile_j0 / e_cell[0]:.0f} ; "
          f"pont cellulaire reste enregistre {pile_j0 / e_reg[1]:.0f} a {pile_j0 / e_reg[0]:.0f} ; "
          f"pont LoRa {pile_j0 / e_lora / 365:.0f} ans")
    ecrire(os.path.join(a.out, "kit_patient.csv"),
           [{"famille": k, "kit_eur_bas": round(v[0], 2), "kit_eur_haut": round(v[1], 2),
             "eur_par_an_bas": round(kit_an[k][0], 2), "eur_par_an_haut": round(kit_an[k][1], 2)} for k, v in kits.items()])

    # --- Besoin en donnees et abonnement (bas, haut) par patient et par an ---
    bes = []
    abon = {}
    sc = C["abonnement_cellulaire"]["scenarios"]
    for cad in cadences:
        b = besoin(cfg, cad)
        bes += b
        mel = [x["ko_par_mois"] * 1024 for x in b if x["profil"] == "melange_base"]
        omin, omax = min(mel), max(mel)
        # Consignes v6 : plage du forfait grand public (2 500 FCFA, borne basse
        # non verifiee apres aout 2026 ; 15 100 FCFA, plus petite offre MTN).
        fp = sc["forfait_grand_public"].get("fcfa_par_mois_plage",
                                            [sc["forfait_grand_public"]["fcfa_par_mois"]] * 2)
        f_bh = (float(fp[0]) * 12 / fcfa, float(fp[1]) * 12 / fcfa)
        mg = sc["offre_machine_negociee"]
        abon[cad] = {"forfait grand public": f_bh,
                     "offre machine négociée": ((mg["frais_fcfa_par_mois"][0] + omin / go * mg["fcfa_par_go"][0]) * 12 / fcfa,
                                                (mg["frais_fcfa_par_mois"][1] + omax / go * mg["fcfa_par_go"][1]) * 12 / fcfa),
                     "forfait déjà payé par le patient": (0.0, 0.0),
                     "zéro-rating payé par l'État": (omin / go * sc["zero_rating_etat"]["fcfa_par_go"][0] * 12 / fcfa,
                                                     omax / go * sc["zero_rating_etat"]["fcfa_par_go"][1] * 12 / fcfa),
                     "_octets": (omin, omax)}
    ecrire(os.path.join(a.out, "besoin_donnees.csv"), bes)

    # --- Passerelle, serveur reseau ---
    gw = C["passerelle"]
    hw = [x * usd for x in gw["materiel_usd"]]
    # Consignes v4, point 5 : passerelle avec alimentation de secours (solaire
    # et batterie), prix catalogue ; remplace le materiel seul dans le scenario
    # bas si active. Le scenario haut (Kerlink) part du materiel seul : ses
    # 90 % hors materiel couvrent deja le site, l'energie et l'exploitation.
    sec = gw.get("alimentation_secours", {})
    hw_bas = [x * usd for x in sec["materiel_avec_secours_usd"]] if sec.get("appliquer") else hw
    sb = gw["scenario_bas"]
    gw_an = {"bas": (hw_bas[0] + gw["antenne_eur"] + sb["installation_eur_hypothese"]
                     + sb["remontee_fcfa_par_mois"] * 12 * A / fcfa) / A,
             "haut": (hw[1] + gw["antenne_eur"]) / gw["scenario_haut"]["part_materiel_dans_cout_total"] / A}
    # Consignes v6.3, point 6 : passerelle sur secteur (variante sans
    # alimentation de secours) : consommation x 8 760 h x tarif SBEE. Les
    # passerelles retenues (alimentation de secours) sont solaires autonomes :
    # cout electrique nul. Le scenario haut (Kerlink) compte deja l'energie.
    ali = gw.get("alimentation_secteur", {})
    if ali and not sec.get("appliquer"):
        e_an = float(ali["puissance_w"][0]) * 8.76 * float(ali["tarif_fcfa_kwh"][0]) / fcfa
        gw_an["bas"] += e_an
        print(f"Passerelle sur secteur : + {e_an:.1f} EUR par an (electricite)")
    remontee_an = {"bas": sb["remontee_fcfa_par_mois"] * 12 / fcfa, "haut": 0.0}
    lns_an = [x * 12 for x in C["serveur_lns_eur_par_mois"]]
    # Complement v6.2, point 1 : mat de 30 m (variante), neuf ou partage.
    if a.mat:
        mt = C["mat_30m"]
        if a.mat == "neuf":
            sup = [x / float(mt["amortissement_mat_ans"]) for x in mt["mat_neuf_eur"]]
        else:
            sup = [12 * x for x in mt["partage_site_eur_par_mois"]]
        gw_an = {"bas": gw_an["bas"] + sup[0], "haut": gw_an["haut"] + sup[1]}
        print(f"Mat ({a.mat}) : + {sup[0]:.0f} a {sup[1]:.0f} EUR par passerelle et par an")
    # Retour v4 (2026-10-28, point 8) : exploitation du reseau prive, scenario
    # bas seulement (Kerlink la compte deja). Visites : par passerelle ;
    # administration : pour le departement, repartie par patient comme le serveur.
    ex = C.get("exploitation_reseau", {})
    if ex.get("appliquer"):
        visites_an = [ex["visites_par_passerelle_par_an"][i] * ex["cout_visite_eur"][i] for i in (0, 1)]
        admin_an = [ex["administration_etp"][i] * ex["salaire_mensuel_charge_fcfa"][i] * 12 / fcfa for i in (0, 1)]
        gw_an["bas"] += visites_an[0]
        lns_an = [lns_an[i] + (admin_an[i] if i == 0 else 0.0) for i in (0, 1)]
        print(f"Exploitation (scenario bas) : visites {visites_an[0]:.0f} EUR par passerelle et par an, "
              f"administration {admin_an[0]:.0f} EUR par an (haut : {visites_an[1]:.0f} et {admin_an[1]:.0f}, via la tornade)")

    rho = float(cfg["radio"]["correlation_ombrage_entre_sites"])
    couv = {}
    # Synthese multi-passerelles : celle de la v4, completee par la v5 pour les
    # zones recalibrees (retour de l'auteur du 2026-10-28).
    syntheses = (sorted(glob.glob(os.path.join(a.prod, "multi_passerelles", "*synthese*.csv")))[-1:]
                 + sorted(glob.glob(os.path.join(a.prod, "multi_passerelles_v5", "*synthese*.csv")))[-1:]
                 + sorted(glob.glob(os.path.join(a.prod, "multi_passerelles_v6", "*synthese*.csv")))[-1:]
                 + sorted(glob.glob(os.path.join(a.prod, "multi_passerelles_v6_fusion", "*synthese*.csv")))[-1:])
    for ch in syntheses:
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            if r["correlation_sites"] and abs(float(r["correlation_sites"]) - rho) < 1e-6 and r["passerelles_par_100km2"]:
                # Densite recalculee depuis l'espacement tenu (en rayons fiables)
                # et le rayon fiable courant de la zone : suit tout changement de
                # rayon (densite de vegetation, gain d'antenne).
                f_esp = float(r["espacement_max_tenu_rayons_fiables"])
                s_km = f_esp * R.rayon_dimensionnement(cfg, cfg["zones"][r["zone"]]) / 1000
                couv[r["zone"]] = 2 / (math.sqrt(3) * s_km ** 2)
    # Consignes v6 : espacement fixe par l'exigence d'alerte (99 % en 15 min)
    # au lieu du critere de routine.
    if a.espacement_alerte:
        ea = C["espacement_exigence_alerte"]
        couv = {z: 2 / (math.sqrt(3) * (float(ea[z]) * R.rayon_dimensionnement(cfg, cfg["zones"][z]) / 1000) ** 2)
                for z in ea if not z.startswith("_")}
        print("Espacement fixe par l'exigence d'alerte : " + " ; ".join(f"{z} {ea[z]}" for z in couv))
    isole = {z: 1 / (1.5 * math.sqrt(3) * (R.rayon_dimensionnement(cfg, zz) / 1000) ** 2)
             for z, zz in cfg["zones"].items() if not z.startswith("_")}
    # Consignes v4, point 1 : marge de robustesse (panne de la passerelle
    # centrale) sur la densite de passerelles, par zone.
    mr = C.get("marge_robustesse", {})
    marge = {}
    if mr.get("appliquer"):
        fichiers = mr["fichier"] if isinstance(mr["fichier"], list) else [mr["fichier"]]
        for f_m in fichiers:
            ch = os.path.join(a.prod, f_m)
            if not os.path.exists(ch):
                continue
            for r in csv.DictReader(open(ch, encoding="utf-8")):
                if r["marge_retenue"]:
                    marge[r["zone"]] = float(r["marge_retenue"])
        if "plafond" in mr:
            marge = {z: min(m, float(mr["plafond"])) for z, m in marge.items()}
        couv = {z: d * marge.get(z, 1.0) for z, d in couv.items()}
        print("Marge de robustesse appliquee (passerelles) : " + " ; ".join(f"{z} {m:.2f}" for z, m in marge.items()))
    f_cap = float(C.get("facteur_capacite", 1.0))
    # Complement v6.2, point 2 : chaque commune en melange de zones, au prorata
    # de la part arboree de sa surface habitee (WorldCover), pour le pavage.
    melange = {}
    if a.melange:
        for ch in glob.glob(os.path.join(a.prod, a.melange, "couvert_arbore_*.csv")):
            for r in csv.DictReader(open(ch, encoding="utf-8")):
                melange[r["commune"]] = float(r["part_arboree_surface_habitee"])
    caps = capacites(os.path.join(a.prod, "capacite_modes_5dBi", "capacite_production.csv"))
    caps.update(capacites(os.path.join(a.prod, "capacite_cadence", "capacite_production.csv")))
    caps.update(capacites(os.path.join(a.prod, "capacite_v5", "capacite_production.csv")))
    # Consignes v6 : capacites des cinq zones simulees (lacustre compris), mixte
    # a recapitulatif compris ; elles remplacent les precedentes.
    caps.update(capacites(os.path.join(a.prod, "capacite_v6", "capacite_production.csv")))
    caps.update(capacites(os.path.join(a.prod, "capacite_recap_v6", "capacite_production.csv")))
    n_min_com = int(C.get("passerelles_min_par_commune", 1))
    # Complement v6.1, point 1 : passerelles du placement PLNE sur les zones
    # habitees (couverture), par commune ; critere d'alerte si --espacement-alerte.
    plne = {}
    if a.placement:
        crit = "alerte" if a.espacement_alerte else "routine"
        base_pl = os.path.join(a.prod if not os.path.isabs(a.placement) else "", a.placement)
        fichiers_pl = glob.glob(os.path.join(base_pl, "placement_v62_*.csv")) or glob.glob(os.path.join(base_pl, "placement_plne_*.csv"))
        for ch in fichiers_pl:
            for r in csv.DictReader(open(ch, encoding="utf-8")):
                if r["critere"] == crit and r["commune"] not in C["placement_plne"].get("communes_exclues", []):
                    plne[r["commune"]] = (int(r["passerelles_plne"]), int(r["passerelles_avec_capacite"]))
        print(f"Placement PLNE ({crit}) : " + " ; ".join(f"{k} {v[0]}" for k, v in sorted(plne.items())))
    # Retour v4 (point 7) : RX2 limitee a 14 dBm. Le tout confirme passe a des
    # cellules isolees dimensionnees sur la voie descendante, avec la capacite
    # simulee dans ces cellules. Les autres modes restent inchanges.
    dens_dl = {}
    if a.scenario_rx2_14dbm:
        p_dl = float(cfg["passerelle"]["fenetres_reception"].get("puissance_rx2_scenario_dbm", 14.0))
        dens_dl = {z: 1 / (1.5 * math.sqrt(3) * (R.rayon_descendant_rx2(cfg, zz, p_dl) / 1000) ** 2)
                   for z, zz in cfg["zones"].items() if not z.startswith("_")}
        c14 = capacites(os.path.join(a.prod, "capacite_rx2_14dbm_descendante", "capacite_production.csv"))
        c14.update(capacites(os.path.join(a.prod, "capacite_rx2_14dbm_v6", "capacite_production.csv")))
        for (z, m, g), v in c14.items():
            caps[(z, m, g)] = v
        print("Scenario RX2 14 dBm : rayon descendant (km) " + " ; ".join(
            f"{z} {R.rayon_descendant_rx2(cfg, cfg['zones'][z], p_dl) / 1000:.2f}" for z in dens_dl)
              + " ; capacites " + " ; ".join(f"{z} {v[0]:.0f}" for (z, m, g), v in c14.items()))

    # --- Communes et departement ---
    com, dep = [], []
    for cad in cadences:
        for fr in C["fraction_population_suivie"]:
            tot = {}
            n_tot = sum(cm["population_2013"] * fr for k, cm in C["communes"].items() if not k.startswith("_"))
            for nom, cm in C["communes"].items():
                if nom.startswith("_"):
                    continue
                z = cm["zone"]
                n = cm["population_2013"] * fr
                for mode in MODES:
                    dens = dens_dl[z] if (dens_dl and mode == "tout_confirme_rx2") else couv.get(z, isole[z])
                    if nom in melange and not (dens_dl and mode == "tout_confirme_rx2"):
                        zb = "rural_degage" if z == "rural_arbore" else z
                        pa = melange[nom] if z != "lacustre" else 0.0
                        dens = pa * couv.get("rural_arbore", isole["rural_arbore"]) + (1 - pa) * couv.get(zb, isole[zb])
                    cap, _ = capacite(caps, z, mode, cad)
                    if not cap or cap <= 0:
                        continue
                    cap *= f_cap
                    # Retour v4 : au moins n_min_com passerelles par commune.
                    n_calc = math.ceil(max(cm["superficie_km2"] * dens, n / cap))
                    if nom in plne and not (dens_dl and mode == "tout_confirme_rx2"):
                        # Couverture du placement ; capacite : densification du
                        # PLNE (tout confirme) ou plafond global (autres modes).
                        n_calc = plne[nom][1] if mode == "tout_confirme_rx2" else max(plne[nom][0], math.ceil(n / cap))
                    n_gw = max(n_min_com, n_calc)
                    for niv, i in (("bas", 0), ("haut", 1)):
                        lora = kit_an["LoRa"][i] + (gw_an[niv] * n_gw + lns_an[i] * n / n_tot) / n
                        l = {"messages_par_jour": cad, "fraction_suivie": fr, "commune": nom, "zone": z,
                             "patients": round(n), "patients_par_km2": round(n / cm["superficie_km2"], 2),
                             "mode_lora": mode, "niveau": niv, "capacite_par_passerelle": round(cap),
                             "passerelles": n_gw, "passerelles_sans_minimum": n_calc,
                             "minimum_applique": n_calc < n_min_com,
                             "limite": ("minimum de passerelles" if n_calc < n_min_com else
                                        ("couverture" if cm["superficie_km2"] * dens >= n / cap else "capacite")),
                             "lora_eur_patient_an": round(lora, 2)}
                        for ab in ("forfait grand public", "offre machine négociée"):
                            l[f"cellulaire_{ab}"] = round(kit_an["cellulaire"][i] + abon[cad][ab][i], 2)
                        l["telephone_du_patient"] = round(kit_an["téléphone du patient"][i], 2)
                        l["telephone_du_patient_zero_rating"] = round(kit_an["téléphone du patient"][i]
                                                                      + abon[cad]["zéro-rating payé par l'État"][i], 2)
                        l["cellulaire_zero_rating"] = round(kit_an["cellulaire"][i]
                                                            + abon[cad]["zéro-rating payé par l'État"][i], 2)
                        l["telephone_fourni_offre_machine"] = round(kit_an["téléphone fourni"][i]
                                                                    + abon[cad]["offre machine négociée"][i], 2)
                        com.append(l)
                        t = tot.setdefault((mode, niv), {"patients": 0, "passerelles": 0, "lora": 0, "cf": 0, "cm": 0,
                                                         "tp": 0, "tm": 0})
                        t["patients"] += n
                        t["passerelles"] += n_gw
                        t["lora"] += lora * n
                        t["cf"] += l["cellulaire_forfait grand public"] * n
                        t["cm"] += l["cellulaire_offre machine négociée"] * n
                        t["tp"] += l["telephone_du_patient"] * n
                        t.setdefault("zr_vol", 0.0)
                        t["zr_vol"] += abon[cad]["zéro-rating payé par l'État"][i] * n
                        t.setdefault("cz", 0.0)
                        t["cz"] += l["cellulaire_zero_rating"] * n
                        t["tm"] += l["telephone_fourni_offre_machine"] * n
            for (mode, niv), t in tot.items():
                dep.append({"messages_par_jour": cad, "fraction_suivie": fr, "mode_lora": mode, "niveau": niv,
                            "patients": round(t["patients"]), "passerelles": t["passerelles"],
                            "lora_keur_an": round(t["lora"] / 1000, 1),
                            "cellulaire_forfait_keur_an": round(t["cf"] / 1000, 1),
                            "cellulaire_machine_keur_an": round(t["cm"] / 1000, 1),
                            "telephone_du_patient_keur_an": round(t["tp"] / 1000, 1),
                            "zero_rating_volume_etat_keur_an": round(t["zr_vol"] / 1000, 2),
                            "cellulaire_zero_rating_keur_an": round(t["cz"] / 1000, 1),
                            "telephone_fourni_machine_keur_an": round(t["tm"] / 1000, 1)})
    ecrire(os.path.join(a.out, "cout_communes.csv"), com)
    # Toutes les architectures, departement : kit + reseau. Reseau LoRa = part
    # passerelles + serveur (tire du calcul par commune, mode tout confirme RX2) ;
    # reseau cellulaire = abonnement selon le scenario.
    arch = []
    for cad in cadences:
        for fr in C["fraction_population_suivie"]:
            for niv, i in (("bas", 0), ("haut", 1)):
                ls = [l for l in com if l["messages_par_jour"] == cad and l["fraction_suivie"] == fr and l["niveau"] == niv]
                n_tot = sum(l["patients"] for l in ls if l["mode_lora"] == "tout_confirme_rx2")
                if not n_tot:
                    continue
                for mode in MODES:
                    lm = [l for l in ls if l["mode_lora"] == mode]
                    reseau_lora = sum((l["lora_eur_patient_an"] - kit_an["LoRa"][i]) * l["patients"] for l in lm)
                    for k in kits:
                        if not k.startswith("LoRa"):
                            continue
                        arch.append({"messages_par_jour": cad, "fraction_suivie": fr, "niveau": niv, "architecture": k,
                                     "mode_ou_abonnement": LIB_MODE[mode], "patients": n_tot,
                                     "classement_principal": k not in HORS_CLASSEMENT,
                                     "statut_mesure": HORS_CLASSEMENT.get(k, "mesure par dispositif medical BLE"),
                                     "keur_an": round((kit_an[k][i] * n_tot + reseau_lora) / 1000, 1)})
                for k in kits:
                    if not k.startswith("cellulaire"):
                        continue
                    for ab in ("offre machine négociée", "zéro-rating payé par l'État", "forfait grand public"):
                        arch.append({"messages_par_jour": cad, "fraction_suivie": fr, "niveau": niv, "architecture": k,
                                     "mode_ou_abonnement": ab, "patients": n_tot,
                                     "classement_principal": k not in HORS_CLASSEMENT,
                                     "statut_mesure": HORS_CLASSEMENT.get(k, "mesure par dispositif medical BLE"),
                                     "keur_an": round((kit_an[k][i] + abon[cad][ab][i]) * n_tot / 1000, 1)})
                for k in ("téléphone du patient",):
                    arch.append({"messages_par_jour": cad, "fraction_suivie": fr, "niveau": niv, "architecture": k,
                                 "mode_ou_abonnement": "zéro-rating payé par l'État", "patients": n_tot,
                                 "classement_principal": True, "statut_mesure": "mesure par dispositif medical BLE",
                                 "keur_an": round((kit_an[k][i] + abon[cad]["zéro-rating payé par l'État"][i]) * n_tot / 1000, 1)})
    # Complement v6.1, point 2 : voies de secours, a exigence egale.
    #  - LoRa + secours cellulaire : les patients en ombre profonde (part f de
    #    la zone, simulee dans le reseau pave) passent sur un pont cellulaire
    #    avec repli 2G (offre machine) ; les autres restent en LoRa ;
    #  - cellulaire + secours LoRa : les patients sans couverture interieure
    #    (part u de la commune, atlas ARCEP : 1 - max(4G, 2G) 'bonne') passent
    #    en LoRa, avec les passerelles qui couvrent cette part de la surface.
    hy = C.get("hybrides", {})
    if hy:
        f_z = {k: float(v) for k, v in hy["part_ombre_lora"].items() if not k.startswith("_")}
        u_c = {}
        chc = os.path.join(a.prod, hy["fichier_couverture"])
        if os.path.exists(chc):
            for r in csv.DictReader(open(chc, encoding="utf-8")):
                u_c[r["commune"]] = max(0.0, 1 - max(float(r["4g_bonne_meilleur"]), float(r["2g_bonne_meilleure"])) / 100)
        hyb_rows = []
        for cad in cadences:
            for fr in C["fraction_population_suivie"]:
                for niv, i in (("bas", 0), ("haut", 1)):
                    ls = [l for l in com if l["messages_par_jour"] == cad and l["fraction_suivie"] == fr and l["niveau"] == niv]
                    n_tot = sum(l["patients"] for l in ls if l["mode_lora"] == "tout_confirme_rx2")
                    if not n_tot:
                        continue
                    ab = abon[cad]["offre machine négociée"][i]
                    for mode in ("tout_confirme_rx2", "mixte_recap_rx2"):
                        lm = [l for l in ls if l["mode_lora"] == mode]
                        if not lm:
                            continue
                        reseau = sum((l["lora_eur_patient_an"] - kit_an["LoRa"][i]) * l["patients"] for l in lm)
                        n_cell = sum(f_z.get(l["zone"], 0.0) * l["patients"] for l in lm)
                        tot = reseau + (n_tot - n_cell) * kit_an["LoRa"][i] + n_cell * (kit_an["cellulaire"][i] + ab)
                        arch.append({"messages_par_jour": cad, "fraction_suivie": fr, "niveau": niv,
                                     "architecture": "LoRa + secours cellulaire", "mode_ou_abonnement": LIB_MODE[mode],
                                     "patients": n_tot, "classement_principal": True,
                                     "statut_mesure": f"{n_cell / n_tot:.1%} des patients au cellulaire",
                                     "keur_an": round(tot / 1000, 1)})
                    # Cellulaire + secours LoRa.
                    tot, gws, n_l = 0.0, 0, 0.0
                    for nom, cm in C["communes"].items():
                        if nom.startswith("_"):
                            continue
                        z = cm["zone"]
                        n = cm["population_2013"] * fr
                        u = u_c.get(nom, 0.0)
                        nl = u * n
                        g = 0
                        if nl >= 1:
                            dens = couv.get(z, isole[z])
                            cap, _ = capacite(caps, z, "tout_confirme_rx2", cad)
                            g = max(1, math.ceil(max(u * cm["superficie_km2"] * dens, nl / (cap * f_cap) if cap else 0)))
                        gws += g
                        n_l += nl
                        tot += (n - nl) * (kit_an["cellulaire"][i] + ab) + nl * kit_an["LoRa"][i] + g * gw_an[niv]
                    if gws:
                        tot += lns_an[i]
                    arch.append({"messages_par_jour": cad, "fraction_suivie": fr, "niveau": niv,
                                 "architecture": "cellulaire + secours LoRa", "mode_ou_abonnement": "offre machine négociée",
                                 "patients": n_tot, "classement_principal": True,
                                 "statut_mesure": f"{n_l / n_tot:.1%} des patients en LoRa, {gws} passerelles",
                                 "keur_an": round(tot / 1000, 1)})
    # Complement v6.2, point 5 : famille la moins chere commune par commune, a
    # exigence egale (LoRa + secours cellulaire en mixte a recapitulatif, contre
    # cellulaire + secours LoRa avec offre machine), prix de bascule de
    # l'abonnement et densite de bascule.
    compo = []
    # v6.3 : volume du pont MQTT/TLS sans arrondi de facturation (octets par mois).
    pq = C["abonnement_cellulaire"]["besoin"]["piles"]["mqtt_tls"]
    vol_mqtt = {}
    for cad in cadences:
        prof_, mel_ = messages(cfg, cad)
        vol_mqtt[cad] = sum(mel_[k] * 30 * (pq["fixe_par_jour"] + sum(
            nb * (pq["montant_par_message"] + o + pq["descendant_par_message"]) for nb, o in prof_[k])) for k in mel_)
    if hy:
        choix_rows = []
        for cad in cadences:
            for fr in C["fraction_population_suivie"]:
                for niv, i in (("bas", 0), ("haut", 1)):
                    ab = abon[cad]["offre machine négociée"][i]
                    tot, n_tot, lora_com = 0.0, 0.0, []
                    for l in com:
                        if (l["messages_par_jour"], l["fraction_suivie"], l["niveau"], l["mode_lora"]) != (cad, fr, niv, "mixte_recap_rx2"):
                            continue
                        nom, z, n = l["commune"], l["zone"], l["patients"]
                        cm = C["communes"][nom]
                        f = f_z.get(z, 0.0)
                        lora_pp = (1 - f) * l["lora_eur_patient_an"] + f * (kit_an["cellulaire"][i] + ab)
                        u = u_c.get(nom, 0.0)
                        nl = u * n
                        g = 0
                        if nl >= 1:
                            dens = couv.get(z, isole[z])
                            g = max(1, math.ceil(u * cm["superficie_km2"] * dens))
                        cell_pp = ((n - nl) * (kit_an["cellulaire"][i] + ab) + nl * kit_an["LoRa"][i] + g * gw_an[niv]) / n
                        # Prix de bascule : abonnement mensuel (FCFA) qui egalise les deux.
                        # cell_pp depend de ab par (1 - u) ; lora_pp par f.
                        a_c = (1 - u) - f
                        reste = lora_pp - f * ab - (cell_pp - (1 - u) * ab)
                        f_bascule = (reste / a_c) * fcfa / 12 if a_c > 0 else float("nan")
                        # Densite de bascule (reseau LoRa limite par la couverture) :
                        # patients par km2 au-dela desquels le LoRa est moins cher.
                        reseau_pp = l["lora_eur_patient_an"] - kit_an["LoRa"][i]
                        ecart_kit = kit_an["cellulaire"][i] + ab - kit_an["LoRa"][i]
                        d_bascule = (reseau_pp * n / cm["superficie_km2"]) / ecart_kit if ecart_kit > 0 else float("nan")
                        al_j = float(cfg["profils_patients"].get("alerte", {}).get("alertes_par_jour", 0))
                        compo.append({"messages_par_jour": cad, "fraction_suivie": fr, "niveau": niv, "commune": nom,
                                      "zone": z, "patients": cm["population_2013"] * fr,
                                      "superficie_km2": cm["superficie_km2"], "passerelles": l["passerelles"],
                                      "part_ombre_lora": f, "part_sans_couverture": u, "passerelles_secours_cell": g,
                                      "kit_lora_eur_an": kit_an["LoRa"][i], "kit_cell_eur_an": kit_an["cellulaire"][i],
                                      "passerelle_hors_remontee_eur_an": gw_an[niv] - remontee_an[niv],
                                      "remontee_v62_eur_an": remontee_an[niv], "lns_departement_eur_an": lns_an[i],
                                      "abonnement_machine_v62_eur_an": ab,
                                      "octets_patient_mois_mqtt": vol_mqtt[cad],
                                      "trames_passerelle_par_patient_jour": cad, "accuses_par_patient_jour": al_j + 1.0})
                        choix = "LoRa + secours" if lora_pp < cell_pp else "cellulaire + secours"
                        tot += min(lora_pp, cell_pp) * n
                        n_tot += n
                        if choix.startswith("LoRa"):
                            lora_com.append(nom)
                        choix_rows.append({"messages_par_jour": cad, "fraction_suivie": fr, "niveau": niv, "commune": nom,
                                           "zone": z, "patients": n, "patients_par_km2": round(n / cm["superficie_km2"], 2),
                                           "lora_secours_eur_patient_an": round(lora_pp, 2),
                                           "cellulaire_secours_eur_patient_an": round(cell_pp, 2), "choix": choix,
                                           "abonnement_bascule_fcfa_mois": round(f_bascule),
                                           "densite_bascule_patients_km2": round(d_bascule, 2)})
                    if n_tot:
                        arch.append({"messages_par_jour": cad, "fraction_suivie": fr, "niveau": niv,
                                     "architecture": "choix par commune", "mode_ou_abonnement": "famille la moins chère",
                                     "patients": round(n_tot), "classement_principal": True,
                                     "statut_mesure": "LoRa : " + (", ".join(lora_com) if lora_com else "aucune"),
                                     "keur_an": round(tot / 1000, 1)})
        ecrire(os.path.join(a.out, "choix_communes.csv"), choix_rows)
        if a.composantes:
            ecrire(os.path.join(a.out, "composantes.csv"), compo)
    ecrire(os.path.join(a.out, "cout_architectures.csv"), arch)
    print("\nToutes architectures, departement, 2 % suivis, 10 msg/j (k EUR/an, bas - haut) :")
    vus = set()
    for r in arch:
        if r["fraction_suivie"] != 0.02 or r["messages_par_jour"] != cadences[0] or r["niveau"] != "bas":
            continue
        h = next(x for x in arch if x["fraction_suivie"] == 0.02 and x["messages_par_jour"] == cadences[0]
                 and x["niveau"] == "haut" and x["architecture"] == r["architecture"] and x["mode_ou_abonnement"] == r["mode_ou_abonnement"])
        print(f"  {r['architecture']:<42} {r['mode_ou_abonnement']:<28} {r['keur_an']:>7} - {h['keur_an']:<7}"
              + ("" if r["classement_principal"] else f"  [hors classement : {r['statut_mesure']}]"))
    ecrire(os.path.join(a.out, "cout_departement.csv"), dep)

    # --- Bascule par zone (cadence cible) ---
    cad = cadences[0]
    bas_rows = []
    for z in isole:
        dens = couv.get(z, isole[z])
        for mode in MODES:
            cap, _ = capacite(caps, z, mode, cad)
            if not cap:
                continue
            for ab in ("forfait grand public", "offre machine négociée"):
                for niv, i in (("bas", 0), ("haut", 1)):
                    ecart = kit_an["cellulaire"][i] + abon[cad][ab][i] - kit_an["LoRa"][i]
                    g = gw_an[niv]
                    if ecart <= 0 or g / cap >= ecart:
                        d, v = "", "le LoRa n'est jamais moins cher"
                    else:
                        d, v = round(g * dens / ecart, 4), "le LoRa est moins cher au-dessus de D*"
                    bas_rows.append({"messages_par_jour": cad, "zone": z, "mode_lora": mode, "abonnement": ab,
                                     "niveau": niv, "capacite": round(cap), "densite_bascule_patients_km2": d,
                                     "verdict": v})
    ecrire(os.path.join(a.out, "cout_bascule.csv"), bas_rows)

    # --- Remontee de la passerelle ---
    rp = C["remontee_passerelle"]
    rem = []
    for cad in cadences:
        for mode in MODES:
            caps_m = [capacite(caps, z, mode, cad)[0] for z in isole]
            if not any(caps_m):
                continue
            cmax = max(c for c in caps_m if c)
            # Consignes v6 : accuses descendants et TxAck en plus pour les trames confirmees.
            al_j = float(cfg["profils_patients"].get("alerte", {}).get("alertes_par_jour", 0))
            acc_j = {"tout_non_confirme": 0.0, "mixte_rx2": al_j, "tout_confirme_rx2": cad,
                     "mixte_recap_rx2": al_j + 1.0}.get(mode, 0.0)
            mo = (rp["octets_maintien_par_jour"] + cmax * cad * rp["octets_par_trame"]
                  + cmax * acc_j * rp.get("octets_par_accuse", 0)) * 30 / 1024 ** 2
            rem.append({"messages_par_jour": cad, "mode_lora": mode, "patients_par_passerelle_max": round(cmax),
                        "mo_par_mois": round(mo, 1)})
    ecrire(os.path.join(a.out, "remontee_passerelle.csv"), rem)

    # --- Energie du pont cellulaire ---
    en = C["energie_cellulaire"]
    pile_j = en["pile"]["capacite_mah"] / 1000 * 3600 * en["pile"]["tension_v"]
    veille = en["courant_veille_enregistre_a"] * en["tension_v"] * 86400
    eteint = en["courant_eteint_a"] * en["tension_v"] * 86400
    tau = 24 * 60 / en["tau_periodique_min"]
    el = []
    for cad in cadences:
        for strat, base, pm, sig in (("reste enregistre (veille LTE)", veille, en["energie_par_message_connecte_j"], (8, tau)),
                                     ("eteint entre deux messages", eteint, en["energie_rattachement_j"], (20, 0))):
            lo, hi = base + cad * pm[0], base + cad * pm[1]
            el.append({"messages_par_jour": cad, "strategie": strat, "energie_j_par_jour_bas": round(lo, 1),
                       "energie_j_par_jour_haut": round(hi, 1), "autonomie_jours_bas": round(pile_j / hi),
                       "autonomie_jours_haut": round(pile_j / lo),
                       "messages_signalisation_par_jour": round(cad * sig[0] + sig[1])})
    ecrire(os.path.join(a.out, "energie_cellulaire.csv"), el)

    # --- Resume ---
    print("Kit par patient (EUR, bas-haut) : " + " ; ".join(f"{k} {v[0]:.0f}-{v[1]:.0f}" for k, v in kits.items()))
    print("Kit par patient et par an, remplacement compris (EUR) : "
          + " ; ".join(f"{k} {v[0]:.1f}-{v[1]:.1f}" for k, v in kit_an.items()))
    for cad in cadences:
        o = abon[cad]["_octets"]
        print(f"{cad:.0f} messages/jour : besoin {o[0] / 1024:.0f} ko a {o[1] / 1024:.0f} ko par mois ; "
              f"offre machine {abon[cad]['offre machine négociée'][0]:.2f}-{abon[cad]['offre machine négociée'][1]:.2f} EUR/an")
    print(f"Passerelle par an : {gw_an['bas']:.0f}-{gw_an['haut']:.0f} EUR ; serveur reseau LoRaWAN (+ administration dans le scenario bas) {lns_an[0]:.0f}-{lns_an[1]:.0f} EUR/an")
    print("Capacites utilisees (patients par passerelle) :")
    for cad in [7.0] + cadences:
        print(f"  {cad:.0f} msg/j : " + " ; ".join(
            f"{LIB_MODE[m]} " + "/".join(f"{(capacite(caps, z, m, cad)[0] or 0):.0f}" for z in isole) for m in MODES))
    print("Remontee de la passerelle (Mo/mois, passerelle la plus chargee) : "
          + " ; ".join(f"{r['messages_par_jour']:.0f} msg/j {LIB_MODE[r['mode_lora']]} {r['mo_par_mois']}" for r in rem))
    print("\nDepartement, 2 % suivis (k EUR/an, bas | haut) :")
    for cad in cadences:
        for mode in MODES:
            r = {d["niveau"]: d for d in dep if d["messages_par_jour"] == cad and d["fraction_suivie"] == 0.02 and d["mode_lora"] == mode}
            if not r:
                continue
            f = lambda k: f"{r['bas'][k]}-{r['haut'][k]}"
            print(f"  {cad:.0f} msg/j, LoRa {LIB_MODE[mode]:<18} LoRa {f('lora_keur_an')} ({r['bas']['passerelles']} passerelles) | "
                  f"cellulaire forfait {f('cellulaire_forfait_keur_an')}, machine {f('cellulaire_machine_keur_an')} | "
                  f"telephone du patient {f('telephone_du_patient_keur_an')} (+ zero-rating Etat {f('zero_rating_volume_etat_keur_an')}), "
                  f"pont cellulaire zero-rating {f('cellulaire_zero_rating_keur_an')}, telephone fourni (machine) {f('telephone_fourni_machine_keur_an')}")
    # Architecture mixte : les patients equipes d'un smartphone passent par leur
    # telephone (zero-rating paye par l'Etat), les autres par un pont.
    ps = C.get("part_patients_avec_smartphone", [0, 0])
    mix = []
    for d in dep:
        for p_tel in ps:
            mix.append({"messages_par_jour": d["messages_par_jour"], "fraction_suivie": d["fraction_suivie"],
                        "mode_lora": d["mode_lora"], "niveau": d["niveau"], "part_smartphone": p_tel,
                        "lora_plus_telephone_keur_an": round((1 - p_tel) * d["lora_keur_an"]
                                                             + p_tel * (d["telephone_du_patient_keur_an"] + d["zero_rating_volume_etat_keur_an"]), 1),
                        "cellulaire_machine_plus_telephone_keur_an": round((1 - p_tel) * d["cellulaire_machine_keur_an"]
                                                                           + p_tel * (d["telephone_du_patient_keur_an"] + d["zero_rating_volume_etat_keur_an"]), 1)})
    ecrire(os.path.join(a.out, "cout_architecture_mixte.csv"), mix)
    print("\nArchitecture mixte (patients equipes par leur telephone), 2 % suivis, k EUR/an :")
    for m in mix:
        if m["fraction_suivie"] == 0.02 and m["messages_par_jour"] == cadences[0]:
            print(f"  {LIB_MODE[m['mode_lora']]:<18} {m['niveau']:<4} smartphone {m['part_smartphone']:.0%} : "
                  f"LoRa + telephone {m['lora_plus_telephone_keur_an']} ; cellulaire machine + telephone {m['cellulaire_machine_plus_telephone_keur_an']}")
    if not a.sans_figure:
        tracer(cfg, couv, isole, caps, gw_an, kit_an, abon, cadences[0], a.out)
    print(f"\nFichiers dans {a.out}")


def energie_lora_mesuree(prod):
    """Energie radio moyenne par jour du pont LoRa (simulation de 7 jours, 7 msg/j)."""
    ch = os.path.join(prod, "capacite_longue_7j", "capacite_points_7j.csv")
    out = {}
    if os.path.exists(ch):
        for r in csv.DictReader(open(ch, encoding="utf-8")):
            try:
                out.setdefault(r["mode"], []).append(float(r["energie_j_jour"]))
            except ValueError:
                pass
    return {k: sum(v) / len(v) for k, v in out.items() if v}


def ecrire(chemin, lignes):
    if lignes:
        with open(chemin, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
            w.writeheader()
            w.writerows(lignes)


def tracer(cfg, couv, isole, caps, gw_an, kit_an, abon, cad, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    SURFACE, ENCRE, ENCRE2, GRILLE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    COUL = ["#2a78d6", "#eb6834", "#6250d6", "#1baf7a"]
    zones = list(isole)
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 8), facecolor=SURFACE)
    axes = list(axes.flat)
    Ds = [10 ** (k / 20.0) for k in range(-60, 61)]
    for ax, z in zip(axes, zones):
        ax.set_facecolor(SURFACE)
        dens = couv.get(z, isole[z])
        for i, mode in enumerate(MODES):
            cap, _ = capacite(caps, z, mode, cad)
            if not cap:
                continue
            y = {n: [kit_an["LoRa"][j] + gw_an[n] * max(dens, D / cap) / D for D in Ds] for n, j in (("bas", 0), ("haut", 1))}
            ax.fill_between(Ds, y["bas"], y["haut"], color=COUL[i], alpha=0.12, linewidth=0)
            ax.plot(Ds, y["haut"], color=COUL[i], linewidth=2, label=f"LoRa, {LIB_MODE[mode]}")
        k = kit_an["cellulaire"]
        ax.axhline(k[1] + abon[cad]["forfait grand public"][1], color=ENCRE2, linewidth=1.5, linestyle=(0, (5, 3)),
                   label="pont cellulaire, forfait grand public")
        ax.axhspan(k[0] + abon[cad]["offre machine négociée"][0], k[1] + abon[cad]["offre machine négociée"][1],
                   color="#6250d6", alpha=0.16, linewidth=0, label="pont cellulaire, offre machine négociée")
        t = kit_an["téléphone du patient"]
        ax.axhspan(t[0], t[1], color="#e87ba4", alpha=0.18, linewidth=0,
                   label="téléphone du patient (son forfait)")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_ylim(3, 1e4)
        ax.set_title(cfg["zones"][z]["libelle"].split(" (")[0], fontsize=10, color=ENCRE, loc="left")
        ax.grid(True, color=GRILLE, linewidth=0.6)
        for s_ in ("top", "right"):
            ax.spines[s_].set_visible(False)
        ax.tick_params(colors=ENCRE2, labelsize=8)
        ax.set_xlabel("patients suivis par km²", fontsize=8, color=ENCRE2)
        ax.set_ylabel("coût par patient et par an (€)", fontsize=8, color=ENCRE2)
    h, l = axes[0].get_legend_handles_labels()
    axes[-1].axis("off")
    axes[-1].legend(h, l, fontsize=9, frameon=False, loc="center left")
    fig.text(0.01, 0.01, f"Kit complet (montre BLE + intermédiaire), remplacement compris, {cad:.0f} messages par jour. "
             "Trait plein : passerelle au coût haut ; bande : jusqu'au coût bas.", fontsize=8, color=ENCRE2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(out, f"cout_par_patient.{ext}"), dpi=200, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    main()
