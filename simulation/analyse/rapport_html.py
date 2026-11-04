#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rapport_html.py

Page de resultats lisible (tableaux et courbes) a partir des sorties de
production deja analysees. Se relance a chaque etape terminee :

  .venv/bin/python analyse/rapport_html.py --prod resultats/production \
      --out resultats/production/rapport.html

Lit : portee/portee_bandes_*.csv et portee_rayon_fiable_*.csv,
capacite_modes/capacite_points_production.csv et capacite_production.csv,
cellulaire/bilan_cellulaire.csv, multi_passerelles/*synthese*.csv s'il existe,
journal.txt (avancement). Les nombres affiches sont ceux de ces fichiers.
"""

import argparse
import csv
import glob
import json
import math
import os
import re
from datetime import datetime


def lire(ch):
    return list(csv.DictReader(open(ch, encoding="utf-8"))) if ch and os.path.exists(ch) else []


def dernier(motif):
    f = sorted(glob.glob(motif))
    return f[-1] if f else None


def num(x):
    try:
        v = float(x)
        return None if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return None


LIB_ZONE = {"urbain_dense": "Urbain dense", "peri_urbain": "Péri-urbain", "rural_degage": "Rural dégagé",
            "rural_arbore": "Rural arboré", "lacustre": "Lacustre"}
LIB_MODE = {"tout_non_confirme": "Sans accusé", "mixte": "Alerte seule", "mixte_rx2": "Alerte seule, RX2",
            "tout_confirme": "Tout confirmé", "tout_confirme_rx2": "Tout confirmé, RX2"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", default="resultats/production")
    ap.add_argument("--out", default="resultats/production/rapport.html")
    a = ap.parse_args()
    P = a.prod

    # Avancement
    journal = open(os.path.join(P, "journal.txt"), encoding="utf-8").read().splitlines() \
        if os.path.exists(os.path.join(P, "journal.txt")) else []
    etapes = [l for l in journal if l.startswith("=== ")]
    prog = [l for l in journal if re.search(r"\d+/\d+ runs", l)]
    avancement = prog[-1].strip() if prog else ""

    # Portee
    bandes = lire(dernier(os.path.join(P, "portee", "portee_bandes_*.csv")))
    # Rayons fiables corriges apres la revue (ajustement probit), sinon anciens.
    probit = lire(os.path.join(P, "portee", "rayon_fiable_probit", "rayon_fiable_probit.csv"))
    rayons = [{"zone": r["groupe"], "rayon_fiable_m": r["rayon_fiable_m"]} for r in probit] \
        or lire(dernier(os.path.join(P, "portee", "portee_rayon_fiable_*.csv")))
    dens_c = str(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "config.json"),
                                encoding="utf-8"))["zones"]["rural_arbore"]["vegetation"]["densite_centrale"])
    portee = {}
    for b in bandes:
        z = b["zone"]
        if " | " in z and ("gain=5" not in z or ("vegetation=" in z and f"vegetation={dens_c} " not in z)):
            continue
        zc = z.split(" | ")[0]
        if b["au_dela_horizon"] == "True":
            continue
        portee.setdefault(zc, []).append([float(b["d_centre_m"]) / 1000, 100 * float(b["taux_moyen"]),
                                          100 * float(b["ic95_bas"])])
    t_portee = {}
    t_arbore = []
    for r in rayons:
        z = r["zone"]
        zc = z.split(" | ")[0]
        mg = re.search(r"gain=([0-9.]+)", z)
        mv = re.search(r"vegetation=([0-9.]+)", z)
        g = mg.group(1) if mg else "0"
        km = float(r["rayon_fiable_m"]) / 1000
        if mv and mv.group(1) != dens_c:
            if g == "5":
                t_arbore.append((mv.group(1), km))
            continue
        t_portee.setdefault(zc, {})[g] = km

    # Capacite trois modes
    pts = lire(os.path.join(P, "capacite_modes_5dBi", "capacite_points_production.csv")) \
        or lire(os.path.join(P, "capacite_modes", "capacite_points_production.csv"))
    cap = {}
    for r in pts:
        z, m = r["zone"], r["mode"]
        cap.setdefault(z, {}).setdefault(m, []).append({
            "n": int(r["nDevices"]), "rep": int(r["repetitions"]),
            "livr": num(r["pdr_routine"]), "livr_ic": num(r["pdr_routine_ic95"]),
            "p5": num(r["patient_p5"]),
            "acq": num(r["routine_taux_acquit"]) if m.startswith("tout_confirme") else num(r["alerte_taux_acquit"]),
            "delai": num(r["routine_p95_acquit_s"]) if m.startswith("tout_confirme") else num(r["alerte_p95_acquit_s"]),
            "delai_ic": num(r["routine_p95_acquit_s_ic95"]) if m.startswith("tout_confirme") else num(r["alerte_p95_acquit_s_ic95"]),
            "p50": num(r["routine_p50_s"]) if m.startswith("tout_confirme") else num(r["alerte_p50_s"]),
            "e": num(r["energie_j_jour"]), "emj": num(r["energie_mj_par_trame_livree"]),
            "tient": r["tient"] == "True"})
    for z in cap:
        for m in cap[z]:
            cap[z][m].sort(key=lambda d: d["n"])

    cel = lire(os.path.join(P, "cellulaire", "bilan_cellulaire.csv"))
    t_cel = {}
    for r in cel:
        if r["convention"] != "avec gains" or "NB-IoT" in r["famille"]:
            continue
        t_cel.setdefault(r["zone"], {})[r["famille"]] = float(r["rayon_fiable_km"])

    multi = lire(dernier(os.path.join(P, "multi_passerelles", "*synthese*.csv")))

    # Mobilite (sorties texte de analyse_mobilite.py)
    mob = {}
    fa = os.path.join(P, "mobilite", "analyse_a.txt")
    if os.path.exists(fa):
        nom = None
        bandes_km = []
        for l in open(fa, encoding="utf-8"):
            m = re.match(r"\s{2}(\S.*): \d+ trames", l)
            if m:
                nom = m.group(1)
            elif "bande (km)" in l:
                bandes_km = [float(x) + 1 for x in l.split()[2:]]
            elif "livraison (%)" in l and nom:
                mob[nom] = [[k, float(v)] for k, v in zip(bandes_km, l.split()[2:])]
    texte_bc = []
    for f in ("analyse_b.txt", "analyse_c.txt"):
        ch = os.path.join(P, "mobilite", f)
        if os.path.exists(ch):
            texte_bc += [l.rstrip() for l in open(ch, encoding="utf-8") if l.strip()]

    donnees = {"portee": portee, "cap": cap, "libz": LIB_ZONE, "libm": LIB_MODE, "mob": mob}
    html = MODELE
    html = html.replace("__DONNEES__", json.dumps(donnees, ensure_ascii=False))
    html = html.replace("__DATE__", datetime.now().strftime("%d/%m/%Y à %H h %M"))
    html = html.replace("__AVANCEMENT__", avancement.replace("runs", "simulations").replace("echecs", "échecs")
                        .replace("reste estime", "reste estimé") or "aucune simulation en cours")
    en_cours = next((l for l in reversed(etapes) if "debut" in l), "")
    html = html.replace("__ETAPE__", en_cours.split("debut ")[-1] if en_cours else "")
    fk = lambda v: "–" if v is None else f"{v:.1f} km".replace(".", ",")
    html = html.replace("__T_PORTEE__", "".join(
        f"<tr><td>{LIB_ZONE.get(z, z)}{(' (densité ' + dens_c.replace('.', ',') + ')') if z == 'rural_arbore' else ''}</td>"
        f"<td class='n'>{fk(g.get('3'))}</td><td class='n'><b>{fk(g.get('5'))}</b></td><td class='n'>{fk(g.get('8'))}</td></tr>"
        for z, g in t_portee.items()))
    html = html.replace("__T_ARBORE__", ", ".join(f"densité {d.replace('.', ',')} : {fk(k)}" for d, k in sorted(t_arbore)))
    lignes_cel = []
    for z, f in t_cel.items():
        lo = f.get("LoRa privé (SF12)")
        g8 = next((v for k, v in f.items() if "800" in k), None)
        g18 = next((v for k, v in f.items() if "1800" in k), None)
        lignes_cel.append(f"<tr><td>{LIB_ZONE.get(z, z)}</td><td class='n'>{lo:.1f} km</td>"
                          f"<td class='n'>{g8:.1f} km</td><td class='n'>{g18:.1f} km</td></tr>")
    html = html.replace("__T_CEL__", "".join(lignes_cel))
    if multi:
        html = html.replace("__T_MULTI__", "".join(
            f"<tr><td>{LIB_ZONE.get(r['zone'], r['zone'])}</td><td class='n'>{r['correlation_sites']}</td>"
            f"<td class='n'>{r['borne']}{r['espacement_max_tenu_rayons_fiables']}</td>"
            f"<td class='n'>{r['passerelles_par_100km2']}</td></tr>" for r in multi))
        html = html.replace("__MULTI_ETAT__", "Production, 20 répétitions.")
    else:
        html = html.replace("__T_MULTI__", "<tr><td colspan='4'>Production pas encore lancée : chiffres de validation "
                            "ci-dessous.</td></tr>")
        html = html.replace("__MULTI_ETAT__", "En attente de la production (elle suit la capacité).")
    import html as H
    html = html.replace("__T_BC__", "\n".join(H.escape(l) for l in texte_bc) or "pas encore de données")
    import base64
    cout = lire(os.path.join(P, "cout", "cout_communes.csv"))
    lc = []
    for r in cout:
        if r["fraction_suivie"] != "0.02" or r["niveau"] != "haut" or r["messages_par_jour"] != "10.0" \
                or r["mode_lora"] != "tout_confirme_rx2":
            continue
        b = next(x for x in cout if x["commune"] == r["commune"] and x["mode_lora"] == r["mode_lora"]
                 and x["fraction_suivie"] == "0.02" and x["niveau"] == "bas" and x["messages_par_jour"] == "10.0")
        lc.append(f"<tr><td>{r['commune'].replace('_', '-').title()}</td><td>{LIB_MODE.get(r['mode_lora'], r['mode_lora'])}</td>"
                  f"<td class='n'>{r['patients_par_km2']}</td><td class='n'>{b['passerelles']}</td>"
                  f"<td class='n'>{b['lora_eur_patient_an']} à {r['lora_eur_patient_an']}</td>"
                  f"<td class='n'>{b['cellulaire_forfait grand public']} à {r['cellulaire_forfait grand public']}</td>"
                  f"<td class='n'>{b['cellulaire_offre machine négociée']} à {r['cellulaire_offre machine négociée']}</td></tr>")
    html = html.replace("__T_COUT__", "".join(lc) or "<tr><td colspan='7'>pas encore calculé</td></tr>")
    png = os.path.join(P, "cout", "cout_par_patient.png")
    html = html.replace("__IMG_COUT__", ("data:image/png;base64," + base64.b64encode(open(png, "rb").read()).decode())
                        if os.path.exists(png) else "")
    def tab_csv(ch, cols, filtre=lambda r: True, noms=None):
        rs = [r for r in lire(ch) if filtre(r)]
        if not rs:
            return "<tr><td>pas encore calculé</td></tr>"
        t = "<thead><tr>" + "".join(f"<th>{n}</th>" for n in (noms or cols)) + "</tr></thead><tbody>"
        for r in rs:
            t += "<tr>" + "".join(f"<td class='n'>{H.escape(str(r[c]))}</td>" for c in cols) + "</tr>"
        return t + "</tbody>"
    html = html.replace("__T_BESOIN__", tab_csv(os.path.join(P, "cout", "besoin_donnees.csv"),
                        ["libelle", "arrondi_octets", "profil", "ko_par_mois"],
                        lambda r: r["profil"] in ("melange_base", "intensif"),
                        ["Pile protocolaire", "Arrondi de facturation (octets)", "Profil", "ko par mois"]))
    arch = lire(os.path.join(P, "cout", "cout_architectures.csv"))
    ta = "<thead><tr><th>Architecture</th><th>Mode LoRa ou abonnement</th><th>k€ par an (bas à haut)</th></tr></thead><tbody>"
    for r in arch:
        if r["fraction_suivie"] != "0.02" or r["messages_par_jour"] != "10.0" or r["niveau"] != "bas":
            continue
        h = next(x for x in arch if x["fraction_suivie"] == "0.02" and x["messages_par_jour"] == "10.0" and x["niveau"] == "haut"
                 and x["architecture"] == r["architecture"] and x["mode_ou_abonnement"] == r["mode_ou_abonnement"])
        ta += (f"<tr><td>{H.escape(r['architecture'])}</td><td>{H.escape(r['mode_ou_abonnement'])}</td>"
               f"<td class='n'>{r['keur_an']} à {h['keur_an']}</td></tr>")
    html = html.replace("__T_DEPT__", ta + "</tbody>")
    html = html.replace("__T_ENERGIE__", tab_csv(os.path.join(P, "cout", "energie_cellulaire.csv"),
                        ["messages_par_jour", "strategie", "energie_j_par_jour_bas", "energie_j_par_jour_haut", "autonomie_jours_bas",
                         "autonomie_jours_haut", "messages_signalisation_par_jour"],
                        lambda r: True,
                        ["Messages/jour", "Pont cellulaire", "J/jour (bas)", "J/jour (haut)", "Jours entre deux recharges (bas)", "Jours entre deux recharges (haut)",
                         "Signalisation (messages/jour)"]))
    resume = os.path.join(P, "cout", "resume.txt")
    html = html.replace("__COUT_HYP__", H.escape("".join(open(resume, encoding="utf-8").readlines()[:4])) if os.path.exists(resume) else "")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(html)
    print(a.out)


MODELE = r"""<title>STOP-MNT, résultats réseau</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400&display=swap">
<style>
/* Mise en page : une colonne de lecture, figures pleine largeur, tableaux compacts. */
:root{
  --bg:#f7f8f6; --surface:#ffffff; --fg:#17201b; --muted:#56615a; --line:#dde3de; --accent:#1f6f54;
  --ok:#1f7a3f; --ko:#b3361f; --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4;
  --display:"Source Serif 4", Georgia, serif; --body:"IBM Plex Sans", system-ui, sans-serif; --mono:"IBM Plex Mono", ui-monospace, monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#121614; --surface:#1a1f1c; --fg:#e9eeea; --muted:#a8b3ab; --line:#2c3530; --accent:#5cc49b;
  --ok:#5cc47e; --ko:#ef7d63; --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#121614; --surface:#1a1f1c; --fg:#e9eeea; --muted:#a8b3ab; --line:#2c3530; --accent:#5cc49b;
  --ok:#5cc47e; --ko:#ef7d63; --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; color-scheme:dark}
body{background:var(--bg);color:var(--fg);font-family:var(--body);font-size:15px;line-height:1.55}
.page{max-width:980px;margin:0 auto;padding-block:28px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:36px}
h1,h2{font-family:var(--display);font-weight:600;text-wrap:balance;margin:0}
h1{font-size:1.9rem} h2{font-size:1.35rem;margin-bottom:8px} h3{font-size:1rem;margin:14px 0 6px}
p{margin:6px 0;max-width:72ch} .muted{color:var(--muted)} .small{font-size:.85rem}
.etat{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:14px 16px;display:grid;gap:4px}
.etat b{font-family:var(--mono);font-weight:400}
ul.cles{margin:6px 0;padding-left:20px;display:grid;gap:6px;max-width:80ch}
.tab{overflow-x:auto} table{border-collapse:collapse;width:100%;font-size:.9rem;background:var(--surface)}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}
td.n{font-variant-numeric:tabular-nums;font-family:var(--mono);font-size:.85rem;white-space:nowrap}
.ok{color:var(--ok);font-weight:600} .ko{color:var(--ko);font-weight:600}
.fig{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 12px;min-width:0}
.grille{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
svg{width:100%;height:auto;display:block} svg text{fill:var(--muted);font-family:var(--body);font-size:11px}
.axe{stroke:var(--line)} .ref{stroke:var(--muted);stroke-dasharray:4 3}
.legende{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.85rem;margin:4px 0}
.legende span{display:inline-flex;align-items:center;gap:6px}
.legende i{width:14px;height:3px;border-radius:2px;display:inline-block}
.onglets{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.onglets button{font:inherit;font-size:.85rem;border:1px solid var(--line);background:var(--surface);color:var(--fg);border-radius:999px;padding:4px 12px;cursor:pointer}
.onglets button[aria-pressed="true"]{border-color:var(--accent);color:var(--accent);font-weight:600}
.onglets button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
</style>

<div class="page">
<header>
  <h1>STOP-MNT, résultats réseau</h1>
  <p class="muted">Simulation ns-3 du transport des mesures : LoRaWAN privé contre cellulaire opérateur. Page générée le __DATE__ à partir des fichiers de <code>resultats/production/</code>. Toutes les valeurs sont provisoires (calibration publiée, non béninoise).</p>
</header>

<section class="etat">
  <div class="small">Capacité : antenne 5 dBi, cinq modes (dont les deux options RX2), 20 répétitions. La version à 0 dBi reste dans <code>resultats/production/capacite_modes/</code>.</div>
  <div>Étape en cours : <b>__ETAPE__</b></div>
  <div>Avancement : <b>__AVANCEMENT__</b></div>
  <div class="small muted">Ordre de la chaîne : capacité en trois modes, puis plusieurs passerelles, mobilité, sensibilité, capacité selon la part de patients intensifs.</div>
</section>

<section>
  <h2>À quoi servent ces simulations</h2>
  <p>Départager les deux familles de transport par le coût, à qualité de service égale. Pour cela il faut, par type de terrain : la portée fiable d'une passerelle LoRa, le nombre de patients qu'elle tient, et ce que coûte l'accusé de réception. L'accusé de réception pour toutes les mesures (« tout confirmé ») est l'expérience centrale : on cherche dans quelles conditions il est utilisable et à quel prix, et on le compare aux deux autres modes.</p>
</section>

<section>
  <h2>Ce qu'on peut déjà retenir</h2>
  <ul class="cles">
    <li><b>Portée fiable d'une passerelle</b> (95 % des mesures livrées, antenne 5 dBi, méthode corrigée après la revue) : 6,3 km en urbain dense, 9,2 km en péri-urbain, 7,0 km en rural dégagé, 3,9 km en arboré (densité 0,2 ; 2,6 km à 0,35, choix de l'auteur en attente), 16,4 km en lacustre. Ils coïncident à 1 à 7 % près avec le bilan de liaison.</li>
    <li><b>Réglementation (revue critique)</b> : la décision ARCEP n° 2020-320 ouvre 863 à 870 MHz aux réseaux IoT indépendants mais ne fixe ni puissance ni cycle de service (article 5 : « réglementation en vigueur »). Les 27 dBm de la seconde fenêtre, dont dépend le tout confirmé, sont à confirmer. Sinon : environ 4 fois plus de passerelles pour le tout confirmé, coût en hausse de 15 à 30 %.</li>
    <li><b>Sensibilités du tout confirmé</b> (10 messages par jour) : marge de 6 à 10 dB sur le choix de la fenêtre, 15 à 30 % de capacité en moins ; routine à 2 ou 3 transmissions, 10 à 25 % en plus. Fourchette : 150 à 340 patients par passerelle.</li>
    <li><b>Capacité d'une passerelle selon le mode d'accusé</b> (antenne 5 dBi, 20 répétitions) : sans accusé, plus de 6400 patients ; alerte seule confirmée avec choix RX2, environ 1600 à 1900 ; <b>tout confirmé avec choix RX2, environ 280 à 430</b>. Avec le serveur par défaut (accusé toujours tenté en RX1 à 14 dBm), le mixte ne tient pas au-delà de 50 patients et le tout confirmé à aucune charge.</li>
    <li><b>Ce qui rend le tout confirmé utilisable</b> : renvoyer l'accusé en RX2 (27 dBm) quand RX1 (14 dBm) ne peut pas atteindre le patient. Avec l'antenne de 5 dBi, la montée porte environ 11 dB plus loin que la descente en RX1. C'est une option de serveur, pas un changement de matériel.</li>
    <li><b>Livraison en tout confirmé</b> : environ 97 % à toutes les charges. Les 3 % manquants sont des patients jamais couverts (bord de cellule dimensionnée à 95 %). Retransmettre n'y change rien, une passerelle voisine si.</li>
    <li><b>Plusieurs passerelles</b> (critère renforcé après la revue) : espacement de 4,0 rayons fiables en urbain, 3,0 en péri-urbain, rural et arboré, 2,0 en lacustre (limité par l'horizon), au lieu de 1,73 en cellule isolée.</li>
    <li><b>Patients mobiles</b> : SF recalculé avant chaque envoi, 88 % de livraison à 8 km (borne haute) ; l'ADR réel du module échoue (43 % dès 2 km) ; le store-and-forward fait passer un patient qui sort de couverture de 65,7 % à 98,0 %.</li>
    <li><b>Coût de bout en bout</b> (département, 2 % suivis, 10 messages par jour, kit complet) : LoRa tout confirmé 586 à 1 415 k€ par an ; pont cellulaire 1 955 à 2 725 k€ au forfait grand public, 676 à 1 706 k€ avec une offre négociée par l'État ; montre 4G directe 278 à 757 k€ avec offre négociée ; téléphone du patient 243 à 451 k€. Avec les offres actuelles, le LoRa gagne ; si l'État négocie, la montre 4G directe devient la moins chère, sous conditions (homologation, mesure non médicale, recharge tous les 2 à 3 jours, pas de store-and-forward documenté).</li>
    <li><b>Recharge des appareils autonomes</b> (radio seule, 10 messages par jour) : pont cellulaire éteint entre deux messages, 300 à 1 090 jours ; resté connecté, environ 2 mois ; montre 4G, 2 à 3 jours ; pont LoRa, la radio ne pèse presque rien.</li>
    <li><b>La 4G béninoise est en bande 3 (1800 MHz) : par site, le LoRa porte 2,7 à 4,4 fois plus loin que la 4G</b> (bilan de liaison, antenne LoRa 5 dBi, eNodeB 17 dBi). L'avantage du cellulaire est son réseau de sites déjà installé, pas sa portée.</li>
  </ul>
</section>

<section>
  <h2>1. Portée d'une passerelle</h2>
  <p>Part des mesures livrées selon la distance à la passerelle, antenne de passerelle de 5 dBi, 20 répétitions, 400 patients. Arboré : cas central (densité de végétation 0,1). Le tableau donne le rayon fiable mesuré pour les trois antennes.</p>
  <div class="fig"><div class="legende" id="leg-portee"></div><svg id="g-portee" viewBox="0 0 640 300" role="img" aria-label="Livraison selon la distance par zone"></svg></div>
  <div class="tab"><table><thead><tr><th>Zone</th><th>Antenne 3 dBi</th><th>5 dBi (central)</th><th>8 dBi</th></tr></thead><tbody>__T_PORTEE__</tbody></table></div>
  <p class="small muted">Rayon fiable (méthode corrigée après la revue critique) : ajustement probit de la livraison en fonction du logarithme de la distance sur les données par patient, puis borne basse (2,5 %) par bootstrap sur les 20 répétitions de la distance où la livraison ajustée vaut 95 %. L'ancienne méthode, quantifiée par bandes, sous-estimait de 25 à 30 % en urbain, péri-urbain et lacustre. Antennes : 5 dBi RAK RAKARG18 (fiche officielle), 3 dBi Dragino (annonce revendeur), 8 dBi Taoglas OMB.868.B08F21 (fiche officielle). Le gain ne s'applique qu'à la réception par la passerelle. Arboré à 5 dBi selon la densité de végétation : __T_ARBORE__. Au-delà de la densité 0,5, le rayon tombe sous 1 km, hors du domaine du modèle de base.</p>
</section>

<section>
  <h2>2. Capacité d'une passerelle selon le mode d'accusé (antenne 5 dBi)</h2>
  <p>Même trafic dans les trois modes (mélange de base : 75 % routine, 15 % intermédiaire, 10 % intensif, plus une alerte par patient et par jour). Une cellule, patients répartis dans le rayon fiable. 20 répétitions par point. Choisir la zone :</p>
  <div class="onglets" id="onglets"></div>
  <div class="legende" id="leg-modes"></div>
  <div class="grille">
    <div class="fig"><h3>Mesures de routine livrées (%)</h3><svg id="g-livr" viewBox="0 0 420 260"></svg><p class="small muted">Tirets : seuil de 95 %.</p></div>
    <div class="fig"><h3>Accusés reçus par le capteur (%)</h3><svg id="g-acq" viewBox="0 0 420 260"></svg><p class="small muted">Tout confirmé : toutes les trames ; mixte : les alertes.</p></div>
    <div class="fig"><h3>Délai d'accusé, 95e percentile (s)</h3><svg id="g-delai" viewBox="0 0 420 260"></svg><p class="small muted">Tirets : plafond de 60 s. Trames acquittées.</p></div>
    <div class="fig"><h3>Énergie radio du capteur (J par jour)</h3><svg id="g-e" viewBox="0 0 420 260"></svg><p class="small muted">Modèle d'énergie du module ns-3 (courants SX1272).</p></div>
  </div>
  <div class="tab" style="margin-top:12px"><table id="t-cap"></table></div>
  <p class="small muted">« Tient » : livraison de la routine ≥ 95 % (borne basse IC 95 %) et, pour les modes avec accusé, délai au 95e percentile ≤ 60 s (borne haute IC 95 %). Zones sans données : simulation pas encore arrivée à cette zone.</p>
</section>

<section>
  <h2>3. LoRa contre 4G, portée par site</h2>
  <p>Bilan de liaison avec la même propagation et le même ombrage par zone, fiabilité de 95 %, gains d'antenne : passerelle 5 dBi (RAK, sourcé), antenne opérateur 17 dBi (valeur de la décision O, à sourcer).</p>
  <div class="tab"><table><thead><tr><th>Zone</th><th>LoRa SF12</th><th>4G 800 MHz</th><th>4G 1800 MHz</th></tr></thead><tbody>__T_CEL__</tbody></table></div>
  <p class="small muted">La 4G béninoise est en bande 3, 1800 MHz (MTN, Celtiis) : c'est la colonne qui s'applique. 800 MHz : perspective.</p>
</section>

<section>
  <h2>4. Plusieurs passerelles voisines</h2>
  <p>__MULTI_ETAT__ Pavage hexagonal de 7 passerelles, antenne 5 dBi, 200 patients dans la cellule centrale. Espacement maximal entre passerelles qui garde 95 % de livraison (borne basse IC 95 %), en rayons fiables (une cellule isolée se pave à 1,73), selon la corrélation de l'ombrage entre sites.</p>
  <div class="tab"><table><thead><tr><th>Zone</th><th>Corrélation entre sites</th><th>Espacement tenu</th><th>Passerelles / 100 km²</th></tr></thead><tbody>__T_MULTI__</tbody></table></div>
  <p class="small">Lecture : avec la diversité, on peut espacer les passerelles de 2,5 à 4 rayons fiables au lieu de 1,73, soit 2 à 5 fois moins de passerelles. Plus la corrélation entre sites est forte, moins la diversité aide. Lacustre : le rayon fiable (17,6 km) est proche de l'horizon de 21 km, donc les grands espacements y sont dominés par l'horizon et le résultat est irrégulier, à lire avec prudence. Le 5e percentile par patient (garde-fou) est dans le fichier <code>multi_passerelles_synthese_production.csv</code>.</p>
</section>

<section>
  <h2>5. Patients mobiles</h2>
  <p>5 répétitions, antenne 5 dBi, rural dégagé pour a et b, arboré pour c. Scénario a : patient qui traverse la cellule à pied, part des mesures livrées selon la distance à la passerelle, par façon de choisir le facteur d'étalement (SF).</p>
  <div class="fig"><div class="legende" id="leg-mob"></div><svg id="g-mob" viewBox="0 0 640 280" role="img" aria-label="Livraison des patients mobiles selon la distance"></svg>
  <p class="small muted">« oracle » : SF recalculé avant chaque envoi d'après le bilan de liaison, borne haute d'un ADR idéal. « adr » : ADR réel du module. « fixe » : SF du départ (le trajet part de loin, donc SF12). Tirets : 95 %.</p></div>
  <h3>Scénarios b (deux passerelles) et c (sortie de couverture, avec et sans store-and-forward)</h3>
  <pre class="small" style="white-space:pre-wrap;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px;font-family:var(--mono)">__T_BC__</pre>
  <p class="small muted">Store-and-forward : tampon dimensionné pour 72 h de coupure, une sonde confirmée toutes les 4 mesures, lots confirmés espacés de 300 s.</p>
</section>

<section>
  <h2>6. Coût par patient et densité de bascule (section 5.5)</h2>
  <p>Coût annuel par patient, amorti sur 5 ans. LoRa : module du pont plus la part des passerelles (assez pour couvrir la commune, ou pour tenir la charge si la capacité limite). Cellulaire : module du pont, surcoût du module LTE et abonnement.</p>
  <h3>Ce qu'un patient envoie vraiment par mois</h3>
  <p>Un patient envoie environ <b>10 messages par jour</b>, majorés à 15 pour les aléas et le store-and-forward (décision de l'auteur). Selon la pile protocolaire et l'arrondi de facturation de l'opérateur, cela fait <b>63 ko à 3,9 Mo par mois</b> à 10 messages par jour. Le plus petit forfait mensuel grand public (2,5 Go pour 2 500 FCFA) représente des centaines à des dizaines de milliers de fois ce besoin : le patient paierait du volume qu'il n'utilise jamais.</p>
  <div class="tab"><table>__T_BESOIN__</table></div>
  <h3>Trois structures tarifaires</h3>
  <ul class="cles">
    <li><b>Forfait grand public</b> (existe) : 2 500 FCFA par mois, soit 45,7 € par an.</li>
    <li><b>Offre machine négociée par l'État</b> (à construire) : carte SIM machine avec frais fixe et volume mutualisé sur tout le parc. Bas : niveau de l'offre internationale 1NCE (10 € pour 10 ans et 500 Mo, soit 55 FCFA par mois, couverture du Bénin non confirmée), qui couvre largement le besoin de 10 ans d'un patient. Haut : un cinquième du forfait grand public (hypothèse). Leviers : Celtiis (opérateur de la SBIN, société d'État), le fonds de service universel prévu par le Code du numérique, la numérotation machine ouverte en 2024, un APN santé ou des données gratuites vers le serveur de santé.</li>
    <li><b>Gratuité des données vers les serveurs du projet, payée par l'État</b> (proposition de l'auteur, sur le modèle des offres gratuites vers certains sites) : au plancher, le volume au prix public du Go (ARCEP, mars 2026), soit 0,04 à 4 k€ par an pour tout le département. Le vrai coût est le forfait que l'opérateur négociera.</li>
  </ul>
  <h3>Équipements vérifiés pour le Bénin</h3>
  <p>La 4G béninoise est en bande 3 (1800 MHz : MTN, Celtiis). Retenus : pont fabriqué par le projet (composants RAK et Quectel), pont MOKO LW003-B (EU868 confirmé, 98 $), montre LoRaWAN ED20W (EU868, 158 $), montre 4G pour personnes âgées (bande 3 gérée, 36 à 48 $, homologation à vérifier, tension estimée par algorithme, recharge tous les 2 à 3 jours). Exclus : tensiomètres 4G américains (SIM liée aux opérateurs américains), hub cellulaire américain (sur secteur). <b>Aucun produit du commerce ne documente le store-and-forward</b> : ce mécanisme, comme le renvoi de l'accusé à 27 dBm, suppose de maîtriser le logiciel de l'appareil, ce qui plaide pour le pont fabriqué par le projet.</p>
  <h3>Ce que cela coûte pour le département (2 % de la population suivie, environ 28 000 patients, 10 messages par jour)</h3>
  <div class="tab"><table>__T_DEPT__</table></div>
  <p class="small">Kit complet (montre et intermédiaire, remplacement compris) et réseau jusqu'au serveur. Lecture : avec les offres actuelles, le LoRa est le moins cher, même en tout confirmé. Si l'État négocie avec les opérateurs, LoRa et pont cellulaire sont à égalité, et la montre 4G directe devient la moins chère, sous conditions (homologation, envoi vers le serveur du projet, tension estimée, recharge fréquente, pas de store-and-forward documenté). Le téléphone du patient est le relais le moins cher pour les patients équipés.</p>
  <h3>Énergie et signalisation du pont cellulaire</h3>
  <div class="tab"><table>__T_ENERGIE__</table></div>
  <p class="small muted">Module LTE Cat-1 Quectel EG915U : 1,5 mA en veille enregistrée, 32 µA éteint (fiche produit). L'énergie par message et par rattachement est une hypothèse en fourchette : aucune mesure Cat-1 trouvée. Pile : deux AA lithium Energizer L91 (3000 mAh). Le pont LoRa consomme 0,47 à 0,66 J par jour mesurés en simulation (7 jours), négligeable pour la pile : un pont cellulaire sur pile doit être rechargé ou branché, un pont LoRa non.</p>
  <pre class="small" style="white-space:pre-wrap;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px;font-family:var(--mono)">__COUT_HYP__</pre>
  <div class="fig"><img src="__IMG_COUT__" alt="Coût par patient et par an selon la densité de patients, par zone, LoRa par mode d'accusé contre cellulaire"></div>
  <h3>Communes de l'Atlantique, 2 % de la population suivie (RGPH4 2013), 10 messages par jour, €/patient/an, kit complet</h3>
  <div class="tab"><table><thead><tr><th>Commune</th><th>Mode LoRa</th><th>Patients / km²</th><th>Passerelles</th><th>LoRa €/patient/an</th><th>Pont cellulaire, forfait grand public</th><th>Pont cellulaire, offre machine négociée</th></tr></thead><tbody>__T_COUT__</tbody></table></div>
  <p class="small muted">Fichiers : <code>resultats/production/cout/</code> (cout_bascule.csv, cout_communes.csv avec 0,5, 2 et 5 % de population suivie). Limite : la densité de passerelles vient du pavage avec diversité ; dans une commune qui n'en demande que 1 à 3, ce gain est optimiste. Affectation des communes aux zones : proposition à valider.</p>
</section>

<section>
  <h2>7. Décisions et ce qu'elles ont changé</h2>
  <div class="tab"><table>
    <thead><tr><th>Décision</th><th>Ce qui a changé</th><th>Où</th></tr></thead>
    <tbody>
      <tr><td>U. Critère de capacité</td><td>Routine jugée sur la livraison globale (≥ 95 %). Modes avec accusé jugés sur le délai d'accusé (≤ 60 s). Trois modes comparés à trafic égal. Vue par patient à côté.</td><td><code>config.json</code> (qualite_service, capacite_modes), <code>analyse_capacite.py</code></td></tr>
      <tr><td>U. Mesure du tout confirmé</td><td>Le capteur attend l'accusé avant d'envoyer la mesure suivante (file d'attente). Délai mesuré trame par trame. Énergie mesurée par patient.</td><td><code>lorawan-cell-shadow.cc</code></td></tr>
      <tr><td>V. Végétation de l'arboré</td><td>Plus de double compte : terrain découvert plus un terme de végétation qui croît avec la distance puis sature. Densité balayée, cas central 0,1.</td><td><code>config.json</code> (zones.rural_arbore), <code>stopmnt-propagation.h</code></td></tr>
      <tr><td>O. Couverture cellulaire</td><td>Calculée par bilan de liaison, pas dans ns-3.</td><td><code>bilan_cellulaire.py</code>, <code>config.json</code> (cellulaire)</td></tr>
      <tr><td>P. Corrélation entre sites</td><td>Balayée à 0,3, 0,5 et 0,7 pour plusieurs passerelles.</td><td><code>config.json</code> (multi_passerelles)</td></tr>
      <tr><td>R. SF des patients mobiles</td><td>Recalcul avant chaque envoi, présenté comme borne haute. ADR réel ajouté en variante.</td><td><code>run_mobilite.py</code></td></tr>
      <tr><td>S. Store-and-forward</td><td>Tampon dimensionné pour 72 h de coupure.</td><td><code>run_mobilite.py</code>, <code>config.json</code></td></tr>
      <tr><td>Correctif technique</td><td>Mise à jour d'énergie toutes les secondes par nœud : résultats identiques, simulation 19 fois plus rapide une fois corrigée.</td><td><code>lorawan-cell-shadow.cc</code></td></tr>
      <tr><td>Levier du tout confirmé (option RX2)</td><td>Option ajoutée au serveur du module, désactivée par défaut : répondre en RX2 (27 dBm) quand RX1 (14 dBm) ne porte pas, d'après la puissance reçue en montée. Deux modes en plus : mixte RX2 et tout confirmé RX2.</td><td><code>ns-3.48/contrib/lorawan/model/network-scheduler.cc/.h</code> (copie d'origine gardée), <code>lorawan-cell-shadow.cc</code>, <code>run_experiences.py</code>, <code>config.json</code></td></tr>
      <tr><td>Délai de rédaction</td><td>Tout confirmé mesuré jusqu'à 2400 patients, mixte jusqu'à 3200 (au-delà ils sont déjà saturés).</td><td><code>config.json</code> (palier_max_par_mode)</td></tr>
      <tr><td>Antenne de passerelle (validée)</td><td>5 dBi sourcés (RAK RAKARG18), 3 et 8 dBi en sensibilité, en réception passerelle seulement. Appliqué à la portée, au bilan 4G et aux étapes suivantes. La capacité en trois modes, lancée avant, reste à 0 dBi : chaque cellule y est dimensionnée à sa propre portée.</td><td><code>config.json</code> (passerelle), <code>stopmnt-propagation.h</code>, <code>run_experiences.py</code></td></tr>
    </tbody>
  </table></div>
</section>
</div>

<script>
const D = __DONNEES__;
const COUL = ["var(--s1)","var(--s2)","var(--s3)","var(--s4)","var(--s5)"];
const MODES = ["tout_non_confirme","mixte","mixte_rx2","tout_confirme","tout_confirme_rx2"];
const NS = "http://www.w3.org/2000/svg";
function el(t,a,p){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e}
function courbe(svg,series,o){
  svg.innerHTML="";const W=+svg.viewBox.baseVal.width,H=+svg.viewBox.baseVal.height,m={l:46,r:12,t:10,b:34};
  const pts=series.flatMap(s=>s.p.filter(q=>q[1]!=null));if(!pts.length){el("text",{x:W/2,y:H/2,"text-anchor":"middle"},svg).textContent="pas encore de données";return}
  const lx=o.logx,fx=v=>lx?Math.log10(v):v;
  let x0=fx(Math.min(...pts.map(q=>q[0]))),x1=fx(Math.max(...pts.map(q=>q[0])));if(x1===x0)x1=x0+1;
  let y0=o.y0!=null?o.y0:Math.min(...pts.map(q=>q[1])),y1=o.y1!=null?o.y1:Math.max(...pts.map(q=>q[1]));
  if(o.ref!=null){y1=Math.max(y1,o.ref);y0=Math.min(y0,o.ref)} if(y1===y0)y1=y0+1;
  const X=v=>m.l+(fx(v)-x0)/(x1-x0)*(W-m.l-m.r),Y=v=>H-m.b-(v-y0)/(y1-y0)*(H-m.t-m.b);
  for(let i=0;i<=4;i++){const v=y0+i*(y1-y0)/4;el("line",{x1:m.l,x2:W-m.r,y1:Y(v),y2:Y(v),class:"axe"},svg);
    el("text",{x:m.l-6,y:Y(v)+4,"text-anchor":"end"},svg).textContent=(Math.abs(v)>=100?v.toFixed(0):v.toFixed(o.dec??1)).replace(".",",")}
  const xt=o.xt||[...new Set(pts.map(q=>q[0]))].sort((a,b)=>a-b);
  xt.forEach(v=>{el("text",{x:X(v),y:H-m.b+16,"text-anchor":"middle"},svg).textContent=String(v).replace(".",",")});
  el("text",{x:(W+m.l)/2,y:H-4,"text-anchor":"middle"},svg).textContent=o.xl;
  if(o.ref!=null)el("line",{x1:m.l,x2:W-m.r,y1:Y(o.ref),y2:Y(o.ref),class:"ref"},svg);
  series.forEach(s=>{const q=s.p.filter(z=>z[1]!=null);if(!q.length)return;
    el("path",{d:q.map((z,i)=>(i?"L":"M")+X(z[0]).toFixed(1)+" "+Y(z[1]).toFixed(1)).join(" "),fill:"none",stroke:s.c,"stroke-width":2},svg);
    q.forEach(z=>{const c=el("circle",{cx:X(z[0]),cy:Y(z[1]),r:4,fill:s.c,stroke:"var(--surface)","stroke-width":1.5},svg);
      el("title",{},c).textContent=s.n+" : "+String(z[0]).replace(".",",")+" → "+z[1].toFixed(o.dec??1).replace(".",",")+(o.u||"")})});
}
function legende(id,items){const d=document.getElementById(id);d.innerHTML=items.map(([n,c])=>`<span><i style="background:${c}"></i>${n}</span>`).join("")}
// Portee
const zp=Object.keys(D.portee);
courbe(document.getElementById("g-portee"),zp.map((z,i)=>({n:D.libz[z]||z,c:COUL[i%5],p:D.portee[z].map(q=>[+q[0].toFixed(2),q[1]])})),
  {xl:"distance à la passerelle (km)",ref:95,dec:0,u:" %",xt:[0,2,4,6,8,10,12,14,16,18,20]});
legende("leg-portee",zp.map((z,i)=>[D.libz[z]||z,COUL[i%5]]));
// Mobilite
const mk=Object.keys(D.mob||{});
if(mk.length){courbe(document.getElementById("g-mob"),mk.map((k,i)=>({n:k,c:COUL[i%5],p:D.mob[k]})),{xl:"distance à la passerelle (km, milieu de bande)",ref:95,dec:0,u:" %",xt:[1,3,5,7,9,11,13,15]});
  legende("leg-mob",mk.map((k,i)=>[k,COUL[i%5]]))}
// Capacite
legende("leg-modes",MODES.map((m,i)=>[D.libm[m],COUL[i]]));
const zones=Object.keys(D.libz).filter(z=>D.cap[z]);
const og=document.getElementById("onglets");
function montre(z){
  og.querySelectorAll("button").forEach(b=>b.setAttribute("aria-pressed",b.dataset.z===z));
  const c=D.cap[z]||{};const ser=f=>MODES.filter(m=>c[m]).map((m,i)=>({n:D.libm[m],c:COUL[MODES.indexOf(m)],p:c[m].map(d=>[d.n,f(d,m)])}));
  const xt=[50,200,800,3200];
  courbe(document.getElementById("g-livr"),ser(d=>d.livr!=null?100*d.livr:null),{logx:1,xl:"patients par passerelle",ref:95,dec:1,u:" %",xt});
  courbe(document.getElementById("g-acq"),ser((d,m)=>m==="tout_non_confirme"||d.acq==null?null:100*d.acq),{logx:1,xl:"patients par passerelle",y1:100,dec:0,u:" %",xt});
  courbe(document.getElementById("g-delai"),ser((d,m)=>m==="tout_non_confirme"?null:d.delai),{logx:1,xl:"patients par passerelle",ref:60,y0:0,dec:0,u:" s",xt});
  courbe(document.getElementById("g-e"),ser(d=>d.e),{logx:1,xl:"patients par passerelle",y0:0,dec:1,u:" J",xt});
  const ns=[...new Set(MODES.flatMap(m=>(c[m]||[]).map(d=>d.n)))].sort((a,b)=>a-b);
  const f=(v,k=1,u="")=>v==null?"–":(v*k).toFixed(k===100?1:(u===" s"?0:2)).replace(".",",")+u;
  let h="<thead><tr><th>Patients</th>"+MODES.map(m=>`<th>${D.libm[m]}</th>`).join("")+"</tr></thead><tbody>";
  ns.forEach(n=>{h+=`<tr><td class="n">${n}</td>`+MODES.map(m=>{const d=(c[m]||[]).find(x=>x.n===n);if(!d)return"<td class='n'>–</td>";
    return `<td class="n">livré ${f(d.livr,100," %")}${m!=="tout_non_confirme"?`<br>accusés ${f(d.acq,100," %")}<br>délai p95 ${f(d.delai,1," s")}`:""}<br>${f(d.e,1," J/j")}<br><span class="${d.tient?"ok":"ko"}">${d.tient?"tient":"ne tient pas"}</span></td>`}).join("")+"</tr>"});
  document.getElementById("t-cap").innerHTML=h+"</tbody>";
}
zones.forEach(z=>{const b=document.createElement("button");b.textContent=D.libz[z];b.dataset.z=z;b.onclick=()=>montre(z);og.appendChild(b)});
if(zones.length)montre(zones[0]);
</script>
"""

if __name__ == "__main__":
    main()
