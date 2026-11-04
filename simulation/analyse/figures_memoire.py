#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
figures_memoire.py

Deux figures du memoire qui ne sortent pas directement d'une analyse :
  g4_cout.png : cout par patient et par commune, du scenario bas au scenario
                haut, avec la part des tirages favorables au LoRaWAN ;
  prototype_chaine.png : chaine logicielle du prototype.
Usage : figures_memoire.py --central <sorties convention_v63> --out <dossier>
"""
import argparse
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams.update({"font.family": "STIXGeneral", "mathtext.fontset": "stix", "font.size": 11})
NOMS = {"abomey_calavi": "Abomey-Calavi", "allada": "Allada", "kpomasse": "Kpomassè", "ouidah": "Ouidah",
        "so_ava": "Sô-Ava", "toffo": "Toffo", "tori_bossito": "Tori-Bossito", "ze": "Zè"}
ORANGE, BLEU, ENCRE, GRIS = "#b4561c", "#2c6491", "#14213d", "#5f6773"


def fr(x, d=0):
    return f"{x:.{d}f}".replace(".", ",")


def cout(central, config, out):
    cfg = json.load(open(config, encoding="utf-8"))["cout"]["communes"]
    lignes = list(csv.DictReader(open(os.path.join(central, "cout_communes_v63.csv"), encoding="utf-8")))
    parts = list(csv.DictReader(open(os.path.join(central, "choix_communes_v63.csv"), encoding="utf-8")))

    def val(c, src, opt):
        return next(float(r["eur_patient_an"]) for r in lignes if r["commune"] == c and r["source"] == src
                    and r["option"] == opt and r["k"] == "1.0" and r["f_global_fcfa_an"] == "10000000")

    def part(c, src):
        r = next(r for r in parts if r["commune"] == c and r["source"] == src and r["k"] == "1.0"
                 and r["f_global_fcfa_an"] == "10000000")
        return float(r["part_lora_sans_convention"]) + float(r["part_lora_sous_convention"])
    dens = {c: cfg[c]["population_2013"] * 0.02 / cfg[c]["superficie_km2"] for c in NOMS}
    ordre = sorted(NOMS, key=lambda c: -dens[c])
    fig, ax = plt.subplots(figsize=(10, 5.4))
    for i, c in enumerate(ordre):
        y = len(ordre) - i
        lo = (val(c, "scénario bas", "LoRa sous convention"), val(c, "scénario haut", "LoRa sous convention"))
        ce = (val(c, "scénario bas", "cellulaire sous convention"), val(c, "scénario haut", "cellulaire sous convention"))
        ax.barh(y + 0.15, lo[1] - lo[0], left=lo[0], height=0.24, color=ORANGE, label="LoRaWAN privé avec secours" if i == 0 else None)
        ax.barh(y - 0.15, ce[1] - ce[0], left=ce[0], height=0.24, color=BLEU, label="cellulaire avec secours" if i == 0 else None)
        d, k = part(c, "Monte-Carlo, scénario bas détaillé"), part(c, "Monte-Carlo, Kerlink 10 %")
        ax.text(116, y, f"{fr(100 * d)} % | {fr(100 * k)} %", va="center", color=ORANGE if d >= 0.5 else BLEU, fontweight="bold")
        ax.text(-2, y + 0.1, NOMS[c], ha="right", va="center", color=ENCRE, fontweight="bold")
        ax.text(-2, y - 0.22, f"{fr(dens[c], 1)} patients/km²", ha="right", va="center", color=GRIS, fontsize=9)
    ax.text(116, len(ordre) + 0.72, "Tirages favorables au LoRaWAN\nstructure détaillée | Kerlink", color=GRIS, fontsize=9, va="center")
    ax.set_yticks([])
    ax.set_xlim(0, 112)
    ax.set_ylim(0.4, len(ordre) + 1.0)
    ax.set_xlabel("coût par patient et par an (€), du scénario bas au scénario haut")
    for s_ in ("top", "right", "left"):
        ax.spines[s_].set_visible(False)
    ax.tick_params(axis="x", direction="in")
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, 1.09), ncol=2, frameon=False)
    fig.subplots_adjust(left=0.17, right=0.76, top=0.92, bottom=0.11)
    fig.savefig(os.path.join(out, "g4_cout.png"), dpi=220)
    plt.close(fig)


def boite(ax, x, y, l, h, titre, sous, coul):
    ax.add_patch(FancyBboxPatch((x, y), l, h, boxstyle="round,pad=0.02,rounding_size=0.12", fc="white", ec=coul, lw=1.6))
    ax.text(x + l / 2, y + h * 0.66, titre, ha="center", va="center", fontweight="bold", color=coul, fontsize=11.5)
    ax.text(x + l / 2, y + h * 0.28, sous, ha="center", va="center", color=ENCRE, fontsize=9.5)


def fleche(ax, a, b, coul=ENCRE, txt=None, dy=0.13):
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="-|>", color=coul, lw=1.6))
    if txt:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + dy, txt, ha="center", color=coul, fontsize=9)


def chaine(out):
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.set_xlim(0, 14.2)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    boite(ax, 0.1, 3.5, 2.5, 1.2, "Capteurs BLE", "appareils compatibles", BLEU)
    boite(ax, 0.1, 1.9, 2.5, 1.2, "Health Connect", "données autorisées", BLEU)
    boite(ax, 3.5, 2.6, 2.6, 1.5, "Application Android", "Flutter, jeton JWT,\nfile locale par patient", ENCRE)
    boite(ax, 7.3, 2.6, 2.5, 1.5, "Serveur", "Nginx, API FastAPI,\nRedis", ENCRE)
    boite(ax, 11.2, 3.5, 2.8, 1.2, "PostgreSQL", "comptes, mesures, alertes", "#2f7d4f")
    boite(ax, 11.2, 1.9, 2.8, 1.2, "Restitution", "interface web, Grafana", "#2f7d4f")
    boite(ax, 3.5, 0.2, 2.6, 1.1, "Simulateur Python", "publication MQTT", ORANGE)
    boite(ax, 7.3, 0.2, 2.5, 1.1, "Mosquitto, worker", "chemin distinct", ORANGE)
    boite(ax, 11.2, 0.2, 2.8, 1.1, "InfluxDB", "séries temporelles", ORANGE)
    fleche(ax, (2.65, 4.05), (3.45, 3.6))
    fleche(ax, (2.65, 2.55), (3.45, 3.1))
    fleche(ax, (6.15, 3.35), (7.25, 3.35), txt="HTTPS/REST")
    fleche(ax, (9.85, 3.6), (11.15, 4.05))
    fleche(ax, (9.85, 3.1), (11.15, 2.55))
    fleche(ax, (6.15, 0.75), (7.25, 0.75), ORANGE)
    fleche(ax, (9.85, 0.75), (11.15, 0.75), ORANGE)
    fig.savefig(os.path.join(out, "prototype_chaine.png"), dpi=220, bbox_inches="tight")
    plt.close(fig)



ZONES = [("urbain_dense", "Urbain dense", "#2a78d6"), ("peri_urbain", "Péri-urbain", "#eb6834"), ("rural_degage", "Rural dégagé", "#1baf7a"),
         ("rural_arbore", "Rural arboré", "#d99a00"), ("lacustre", "Lacustre", "#c2478a")]


def _style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, color="#e6e8ec", linewidth=.8)
    ax.set_axisbelow(True)


def portee(rep, out):
    """Taux de livraison selon la distance : les cinq zones sur un seul graphe."""
    lignes = list(csv.DictReader(open(rep, encoding="utf-8")))
    bandes = [k for k in lignes[0] if k.startswith("bande_")]
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    for z, lib, c in ZONES:
        xs, m, sd = [], [], []
        for b in bandes:
            v = [float(r[b]) for r in lignes if r["zone"] == z and r[b] != ""]
            if len(v) >= 20:
                xs.append(float(b.split("_km_")[1])); m.append(sum(v) / len(v))
                sd.append((sum((x - m[-1]) ** 2 for x in v) / (len(v) - 1)) ** 0.5)
        hi = [min(100, a + b) for a, b in zip(m, sd)]
        lo = [a - b for a, b in zip(m, sd)]
        ax.fill_between(xs, lo, hi, color=c, alpha=0.13, linewidth=0)
        ax.plot(xs, m, color=c, lw=1.8, label=lib)
    ax.axhline(95, color=ENCRE, ls=(0, (4, 3)), lw=1)
    ax.text(0.062, 95.6, "seuil de 95 %", fontsize=9, color=ENCRE)
    ax.set_xscale("log")
    ax.set_xticks([0.1, 0.2, 0.5, 1, 2, 5, 8])
    ax.set_xticklabels(["0,1", "0,2", "0,5", "1", "2", "5", "8"])
    ax.set_xlim(0.06, 9)
    ax.set_ylim(60, 101)
    ax.set_xlabel("distance à la passerelle (km, échelle logarithmique)")
    ax.set_ylabel("mesures livrées (%)")
    ax.legend(frameon=False, loc="lower left", ncol=1)
    _style(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "taux_livraison_distance.png"), dpi=220)
    plt.close(fig)


def robustesse(rep, out):
    """Panne de la passerelle centrale : un seul graphe, seuil de 90 %."""
    lignes = list(csv.DictReader(open(rep, encoding="utf-8")))
    cols = [k for k in lignes[0] if k.startswith("esp_")]
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    for z, lib, c in ZONES:
        for etat, ls in (("service", "-"), ("panne", "--")):
            xs, m, sd = [], [], []
            for k in cols:
                v = [float(r[k]) for r in lignes if r["zone"] == z and r["centrale"] == etat and r[k] != ""]
                if len(v) >= 10:
                    xs.append(float(k[4:])); m.append(sum(v) / len(v))
                    sd.append((sum((x - m[-1]) ** 2 for x in v) / (len(v) - 1)) ** 0.5)
            if etat == "panne":
                ax.fill_between(xs, [a - b for a, b in zip(m, sd)], [min(100, a + b) for a, b in zip(m, sd)], color=c, alpha=0.13, linewidth=0)
            ax.plot(xs, m, color=c, lw=1.6, ls=ls, label=lib if etat == "service" else None)
    ax.axhline(90, color=ENCRE, ls=(0, (1, 2)), lw=1.2)
    ax.text(1.05, 90.5, "seuil de 90 %", fontsize=9, color=ENCRE)
    ax.plot([], [], color=GRIS, ls="-", label="centrale en service")
    ax.plot([], [], color=GRIS, ls="--", label="centrale en panne")
    ax.set_xlim(1, 6)
    ax.set_ylim(70, 100.5)
    ax.set_xlabel("espacement entre passerelles (en rayons)")
    ax.set_ylabel("patients servis (%)")
    ax.legend(frameon=False, loc="lower left", ncol=2)
    _style(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "robustesse_indisponibilite_passerelle.png"), dpi=220)
    plt.close(fig)


def carte(mailles, out, nom="carte_optimisation.png"):
    """Choix maille par maille sur le departement."""
    import numpy as np
    d = np.genfromtxt(mailles, delimiter=",", names=True)
    fig, ax = plt.subplots(figsize=(7.4, 6.2))
    t = d["patients"] / d["patients"].max()
    tailles = 2 + 40 * t ** 0.5
    for v, c, lab in ((0, BLEU, "mailles servies en cellulaire"), (1, ORANGE, "mailles servies en LoRaWAN")):
        k = d["lora"] == v
        ax.scatter(d["x_m"][k] / 1000, d["y_m"][k] / 1000, s=tailles[k], c=c, alpha=0.45, linewidths=0, label=lab)
    k = d["site"] == 1
    ax.scatter(d["x_m"][k] / 1000, d["y_m"][k] / 1000, s=28, marker="^", c=ENCRE, linewidths=0, label="passerelles ouvertes")
    ax.set_aspect("equal")
    ax.set_xlabel("ouest-est (km)")
    ax.set_ylabel("nord-sud (km)")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    _style(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(out, nom), dpi=220)
    plt.close(fig)


def _action(ax, x, y, txt, l=2.6, h=0.62, c=ENCRE, fc="white"):
    ax.add_patch(FancyBboxPatch((x - l / 2, y - h / 2), l, h, boxstyle="round,pad=0.01,rounding_size=0.16", fc=fc, ec=c, lw=1.3))
    ax.text(x, y, txt, ha="center", va="center", fontsize=9.5, color=ENCRE)


def _losange(ax, x, y, txt, l=1.75, h=0.9, c=ORANGE):
    ax.fill([x - l / 2, x, x + l / 2, x], [y, y + h / 2, y, y - h / 2], fc="#fdf3ea", ec=c, lw=1.3)
    ax.text(x, y, txt, ha="center", va="center", fontsize=8.5, color=ENCRE)


def _fl(ax, a, b, txt=None, c=ENCRE, dx=0.1, dy=0.0):
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="-|>", color=c, lw=1.2, shrinkA=0, shrinkB=0))
    if txt:
        ax.text((a[0] + b[0]) / 2 + dx, (a[1] + b[1]) / 2 + dy, txt, fontsize=8.5, color=c)


def activites(out):
    """Diagramme d'activites : routine et alerte, sans technologie de transport."""
    fig, ax = plt.subplots(figsize=(9.6, 7.6))
    ax.set_xlim(0, 10.2); ax.set_ylim(0, 8.4); ax.axis("off")
    for x, t in ((1.75, "Patient et capteur"), (5.1, "Intermédiaire"), (8.5, "Centre et soignant")):
        ax.text(x, 8.15, t, ha="center", fontweight="bold", color=ENCRE, fontsize=10.5)
    for x in (3.4, 6.8):
        ax.plot([x, x], [0.2, 8.0], color="#c9ced6", lw=1)
    ax.scatter([1.75], [7.65], s=70, c=ENCRE)
    _action(ax, 1.75, 6.9, "Prendre la mesure")
    _action(ax, 5.1, 6.9, "Recevoir, horodater\net identifier")
    _action(ax, 5.1, 5.95, "Conserver localement")
    _losange(ax, 5.1, 4.85, "Valeur\ncritique ?")
    _losange(ax, 5.1, 3.45, "Réseau\ndisponible ?")
    _action(ax, 5.1, 2.25, "Attendre et réessayer", c=GRIS)
    _action(ax, 8.5, 3.45, "Enregistrer la mesure\nune seule fois")
    _action(ax, 8.5, 2.25, "Confirmer ce qui\nest enregistré")
    _action(ax, 5.1, 1.1, "Effacer ce qui est confirmé,\nrenvoyer ce qui manque")
    _action(ax, 8.5, 5.5, "Prévenir l'agent,\npuis le soignant", c=ORANGE)
    _action(ax, 1.75, 4.85, "Alarme locale si\npas de confirmation", c=ORANGE)
    _fl(ax, (1.75, 7.6), (1.75, 7.22))
    _fl(ax, (3.05, 6.9), (3.8, 6.9))
    _fl(ax, (5.1, 6.58), (5.1, 6.27))
    _fl(ax, (5.1, 5.63), (5.1, 5.31))
    _fl(ax, (5.1, 4.39), (5.1, 3.91), "non")
    _fl(ax, (5.98, 4.85), (7.2, 5.5), "oui : envoi prioritaire", c=ORANGE, dx=-0.5, dy=0.3)
    _fl(ax, (4.22, 4.85), (3.06, 4.85), c=ORANGE)
    _fl(ax, (5.1, 3.0), (5.1, 2.57), "non")
    _fl(ax, (5.98, 3.45), (7.2, 3.45), "oui", dx=-0.1, dy=0.07)
    _fl(ax, (8.5, 3.13), (8.5, 2.57))
    ax.annotate("", xy=(5.8, 1.42), xytext=(8.0, 1.93), arrowprops=dict(arrowstyle="-|>", color=ENCRE, lw=1.2))
    ax.annotate("", xy=(3.65, 3.45), xytext=(3.8, 2.25), arrowprops=dict(arrowstyle="-", color=GRIS, lw=1.1))
    ax.annotate("", xy=(4.23, 3.45), xytext=(3.65, 3.45), arrowprops=dict(arrowstyle="-|>", color=GRIS, lw=1.1))
    ax.add_patch(FancyBboxPatch((4.05, 2.88), 2.1, 1.14, boxstyle="round,pad=0.02", fc="none", ec=ORANGE, lw=1.2, ls="--"))
    ax.text(6.25, 4.08, "point de blocage", fontsize=8.5, color=ORANGE, ha="left")
    fig.savefig(os.path.join(out, "activites_flux.png"), dpi=220, bbox_inches="tight")
    plt.close(fig)


def architecture_initiale(out):
    """Architecture de depart : le transport longue portee reste a choisir."""
    fig, ax = plt.subplots(figsize=(10.4, 3.5))
    ax.set_xlim(0, 13); ax.set_ylim(0, 4); ax.axis("off")
    B = [(1.2, "Capteur ou\nmontre", "mesure"), (4.0, "Intermédiaire", "conserve et\nidentifie"), (9.2, "Centre", "enregistre,\nsécurise, alerte"), (12.0, "Soignant", "consulte\net agit")]
    for x, t, st in B:
        boite(ax, x - 1.05, 1.3, 2.1, 1.6, t, st, ENCRE)
    ax.add_patch(FancyBboxPatch((5.75, 1.15), 1.9, 1.9, boxstyle="round,pad=0.02,rounding_size=0.12", fc="#fdf3ea", ec=ORANGE, lw=1.6, ls="--"))
    ax.text(6.7, 2.25, "Réseau\nlongue portée", ha="center", va="center", fontweight="bold", color=ORANGE)
    ax.text(6.7, 1.6, "à choisir", ha="center", va="center", color=ORANGE, fontsize=10)
    fleche(ax, (2.3, 2.1), (2.92, 2.1), txt="courte\nportée", dy=0.2)
    fleche(ax, (5.08, 2.1), (5.7, 2.1))
    fleche(ax, (7.7, 2.1), (8.1, 2.1))
    fleche(ax, (10.28, 2.1), (10.92, 2.1))
    ax.text(6.5, 0.45, "Identité et droits, sécurité des échanges, supervision et sauvegarde sur toute la chaîne", ha="center", color=GRIS, fontsize=10)
    fig.savefig(os.path.join(out, "architecture_initiale.png"), dpi=220, bbox_inches="tight")
    plt.close(fig)


def architecture_logique(out):
    """Architecture logique finale, par couches."""
    fig, ax = plt.subplots(figsize=(10.4, 5.6))
    ax.set_xlim(0, 13); ax.set_ylim(0, 7); ax.axis("off")
    C = [("Acquisition", ["Capteurs BLE", "Health Connect"], BLEU),
         ("Intermédiaire", ["Smartphone (application)", "Pont LoRaWAN", "Pont cellulaire"], ENCRE),
         ("Transport", ["Cellulaire ou Wi-Fi, HTTPS", "LoRaWAN, ChirpStack", "4G/2G, MQTT sur TLS"], ORANGE),
         ("Ingestion", ["API FastAPI", "Courtier et worker"], ENCRE),
         ("Stockage", ["PostgreSQL : comptes, mesures, alertes", "InfluxDB : séries temporelles"], "#2f7d4f"),
         ("Restitution", ["Interface web", "Grafana", "Notifications"], "#2f7d4f")]
    y = 6.0
    for t, its, c in C:
        ax.text(0.1, y + 0.3, t, fontweight="bold", color=c, fontsize=11, va="center")
        l = 9.4 / len(its)
        for k, it in enumerate(its):
            ax.add_patch(FancyBboxPatch((1.95 + k * l + 0.05, y + 0.02), l - 0.15, 0.56, boxstyle="round,pad=0.01,rounding_size=0.1", fc="white", ec=c, lw=1.2))
            ax.text(1.95 + k * l + l / 2 - 0.02, y + 0.3, it, ha="center", va="center", fontsize=9.2, color=ENCRE)
        y -= 0.95
    ax.add_patch(FancyBboxPatch((11.5, 1.25), 1.35, 5.3, boxstyle="round,pad=0.01,rounding_size=0.1", fc="#f4f5f7", ec=GRIS, lw=1.1))
    ax.text(12.17, 3.9, "Identité et droits\nSécurité\nSupervision\nSauvegarde", ha="center", va="center", fontsize=9, color=ENCRE, rotation=90)
    fig.savefig(os.path.join(out, "architecture_logique.png"), dpi=220, bbox_inches="tight")
    plt.close(fig)


def architecture_hybride(out):
    """Architecture retenue : trois voies selon le patient et la zone."""
    fig, ax = plt.subplots(figsize=(10.8, 5.2))
    ax.set_xlim(0, 14); ax.set_ylim(0, 6.6); ax.axis("off")
    boite(ax, 0.1, 2.5, 2.1, 1.6, "Capteur\nou montre", "BLE", ENCRE)
    V_ = [(5.3, "Smartphone du patient", "application, file locale", BLEU), (3.3, "Pont cellulaire", "journal local, zones dispersées", ENCRE), (1.3, "Pont LoRaWAN", "journal local, zones groupées", ORANGE)]
    R_ = [(5.3, "Cellulaire ou Wi-Fi", "HTTPS", BLEU), (3.3, "4G avec repli 2G", "MQTT sur TLS", ENCRE), (1.3, "Passerelles partagées", "LoRaWAN puis 4G", ORANGE)]
    for (y, t, st, c), (y2, t2, st2, c2) in zip(V_, R_):
        boite(ax, 3.1, y - 0.6, 3.0, 1.2, t, st, c)
        boite(ax, 6.9, y2 - 0.6, 2.7, 1.2, t2, st2, c2)
        fleche(ax, (2.25, 3.3), (3.05, y))
        fleche(ax, (6.15, y), (6.85, y2), c)
        fleche(ax, (9.65, y2), (10.35, 3.3), c)
    boite(ax, 10.4, 2.4, 1.75, 1.8, "Centre", "enregistre une fois,\nrécapitule, alerte", "#2f7d4f")
    boite(ax, 12.5, 2.5, 1.4, 1.6, "Soignant", "consulte", "#2f7d4f")
    fleche(ax, (12.17, 3.3), (12.47, 3.3))
    ax.text(4.6, 0.25, "Le patient équipé utilise son smartphone ; pour les autres, le pont dépend de la zone.", ha="center", color=GRIS, fontsize=10)
    fig.savefig(os.path.join(out, "architecture_hybride.png"), dpi=220, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--central", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cout(a.central, a.config, a.out)
    D = os.path.join(os.path.dirname(a.central), "..", "v62", "figures")
    portee(os.path.join(D, "repetitions_portee.csv"), a.out)
    robustesse(os.path.join(D, "repetitions_robustesse.csv"), a.out)
