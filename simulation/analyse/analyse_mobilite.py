#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyse_mobilite.py

Analyse des scenarios de mobilite a partir des traces des patients mobiles
emises par le modele (sortie brute d'un run, lignes PKT, DL et RD) :

  PKT;noeud;t;x;y;dPlusProche;gwPlusProche;sf;type;nMesures;livree;latence;nGw
      type : 0 routine, 1 alerte, 2 sonde, 3 lot de store-and-forward
  DL;t;noeud;passerelle            descendante vers un mobile (acquittement)
  RD;noeud;numero;tProduction;x;y;livree;tLivraison;perdueTampon

Trois analyses, une par scenario :
  trajet      taux de livraison et latence par bande de distance a la
              passerelle la plus proche, le long du trajet (scenario a) ;
  equidistant alertes d'un patient a egale distance de deux passerelles :
              entendues par une ou deux passerelles, acquittees, passerelle
              choisie pour l'acquittement et nombre de bascules (scenario b) ;
  debordement mesures produites en sortant puis en revenant de la zone
              couverte : livrees, perdues, delai, duree du trou, delai de
              reprise apres le retour en couverture (scenario c, avec ou sans
              store-and-forward).

Usage :
  analyse_mobilite.py trajet --runs fixe=f1.txt oracle=f2.txt --out dossier
  analyse_mobilite.py equidistant --runs b=f.txt --out dossier
  analyse_mobilite.py debordement --runs sans=f0.txt avec=f1.txt --rayon 4289 --out dossier
"""

import argparse
import math
import os
import statistics as st
from collections import defaultdict

SURFACE, ENCRE, ENCRE2, GRILLE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COUL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # palette validee, ordre fixe
MARQ = ["o", "s", "^", "D"]


def lire(chemin):
    pkt, dl, rd = [], [], []
    for l in open(chemin, encoding="utf-8"):
        f = l.strip().split(";")
        if f[0] == "PKT":
            pkt.append({"node": int(f[1]), "t": float(f[2]), "x": float(f[3]), "y": float(f[4]),
                        "d": float(f[5]), "gw": int(f[6]), "sf": int(f[7]), "type": int(f[8]),
                        "n": int(f[9]), "livree": int(f[10]), "lat": float(f[11]), "ngw": int(f[12])})
        elif f[0] == "DL":
            dl.append({"t": float(f[1]), "node": int(f[2]), "gw": int(f[3])})
        elif f[0] == "RD":
            rd.append({"node": int(f[1]), "seq": int(f[2]), "t": float(f[3]), "x": float(f[4]),
                       "y": float(f[5]), "livree": int(f[6]), "tl": float(f[7]), "perdue": int(f[8])})
    return pkt, dl, rd


def axe(ax, titre, xl, yl):
    ax.set_facecolor(SURFACE)
    ax.set_title(titre, fontsize=10, color=ENCRE, loc="left")
    ax.grid(True, color=GRILLE, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRILLE)
    ax.tick_params(colors=ENCRE2, labelsize=8)
    ax.set_xlabel(xl, fontsize=8, color=ENCRE2)
    ax.set_ylabel(yl, fontsize=8, color=ENCRE2)


def figure(n=1, larg=6.5):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, n, figsize=(larg * n, 3.8), facecolor=SURFACE, squeeze=False)
    return plt, fig, list(axes.flat)


def sauver(plt, fig, base, note):
    fig.text(0.01, 0.005, note, fontsize=8, color=ENCRE2)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    for ext in ("png", "pdf"):
        fig.savefig(f"{base}.{ext}", dpi=200, facecolor=SURFACE)
    plt.close(fig)


def trajet(runs, out, pas_km):
    print("Scenario a : livraison le long du trajet (trames de routine des mobiles)")
    plt, fig, (ax,) = figure()
    for i, (nom, ch) in enumerate(runs):
        pkt, _, _ = lire(ch)
        bandes = defaultdict(list)
        for p in pkt:
            if p["type"] in (0, 2, 3):
                bandes[int(p["d"] // (pas_km * 1000))].append(p)
        xs = sorted(bandes)
        taux = [st.mean(p["livree"] for p in bandes[b]) for b in xs]
        lats = [st.mean([p["lat"] for p in bandes[b] if p["livree"]] or [float("nan")]) for b in xs]
        sfs = [st.median(p["sf"] for p in bandes[b]) for b in xs]
        print(f"  {nom}: {len(pkt)} trames")
        print("    bande (km)    " + " ".join(f"{b * pas_km:4.0f}" for b in xs))
        print("    livraison (%) " + " ".join(f"{100 * t:4.0f}" for t in taux))
        print("    latence (s)   " + " ".join(f"{l:4.1f}" for l in lats))
        print("    SF median     " + " ".join(f"{s:4.0f}" for s in sfs))
        ax.plot([(b + 0.5) * pas_km for b in xs], [100 * t for t in taux], color=COUL[i % 4],
                marker=MARQ[i % 4], markersize=5, linewidth=2, label=nom)
    axe(ax, "Patient en déplacement : livraison selon la distance à la passerelle",
        "distance à la passerelle la plus proche (km)", "trames livrées (%)")
    ax.set_ylim(0, 103)
    ax.legend(fontsize=8, frameon=False, title="politique de SF", title_fontsize=8)
    sauver(plt, fig, os.path.join(out, "mobilite_trajet"),
           "Trames de routine des patients mobiles, toutes positions du trajet confondues.")


def equidistant(runs, out):
    print("Scenario b : patient a egale distance de deux passerelles, alertes confirmees")
    for nom, ch in runs:
        pkt, dl, _ = lire(ch)
        alertes = [p for p in pkt if p["type"] == 1]
        par_noeud = defaultdict(list)
        for d in dl:
            par_noeud[d["node"]].append(d)
        choix = []
        for a in alertes:
            # Acquittement : premiere descendante vers ce noeud dans les fenetres
            # de reception qui suivent l'emission (RX1 a 1 s, RX2 a 2 s apres la
            # fin ; on laisse 5 s de marge, une retransmission eventuelle plus tard
            # est comptee aussi tant qu'elle precede l'alerte suivante).
            suivantes = [d for d in par_noeud[a["node"]] if a["t"] <= d["t"] <= a["t"] + 5.0]
            choix.append(suivantes[0]["gw"] if suivantes else None)
        ent2 = sum(1 for a in alertes if a["ngw"] >= 2)
        livr = sum(a["livree"] for a in alertes)
        ack = [c for c in choix if c is not None]
        bascules = 0
        for node in {a["node"] for a in alertes}:
            seq = [c for a, c in zip(alertes, choix) if a["node"] == node and c is not None]
            bascules += sum(1 for u, v in zip(seq, seq[1:]) if u != v)
        print(f"  {nom}: {len(alertes)} alertes de mobiles ; livrees {100 * livr / len(alertes):.1f} % ; "
              f"entendues par 2 passerelles {100 * ent2 / len(alertes):.1f} % ; acquittement a la 1re "
              f"fenetre {100 * len(ack) / len(alertes):.1f} %")
        for g in sorted(set(ack)):
            print(f"    acquittements envoyes par la passerelle {g} : {100 * ack.count(g) / len(ack):.1f} %")
        print(f"    bascules de passerelle d'acquittement entre alertes successives d'un meme patient : "
              f"{bascules} sur {len(ack)} acquittements")
        plt, fig, (ax,) = figure()
        for g in sorted(set(ack)):
            pts = [(a["y"] / 1000, a["t"] / 3600) for a, c in zip(alertes, choix) if c == g]
            ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=10, color=COUL[g % 4], marker=MARQ[g % 4],
                       label=f"acquittée par la passerelle {g}")
        pts = [(a["y"] / 1000, a["t"] / 3600) for a, c in zip(alertes, choix) if c is None]
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=10, color=ENCRE2, marker="x",
                   label="pas d'acquittement")
        axe(ax, "Patient à égale distance de deux passerelles : qui acquitte l'alerte",
            "position le long de la médiatrice (km)", "instant (h)")
        ax.legend(fontsize=8, frameon=False)
        sauver(plt, fig, os.path.join(out, f"mobilite_equidistant_{nom}"),
               "Chaque point est une alerte confirmée d'un patient mobile. Le serveur choisit la passerelle "
               "qui a reçu le plus fort, parmi celles libres.")


def debordement(runs, out, rayon):
    print(f"Scenario c : sortie de couverture et retour (rayon fiable theorique {rayon / 1000:.1f} km)")
    plt, fig, axes = figure(len(runs), larg=5.5)
    for i, ((nom, ch), ax) in enumerate(zip(runs, axes)):
        _, _, rd = lire(ch)
        n = len(rd)
        livr = [r for r in rd if r["livree"]]
        perdues = [r for r in rd if not r["livree"]]
        tampon = sum(r["perdue"] for r in rd)
        delais = [r["tl"] - r["t"] for r in livr]
        # Trou : plus longue suite de mesures non livrees, par patient.
        trous = []
        reprises = []
        for node in sorted({r["node"] for r in rd}):
            seq = sorted([r for r in rd if r["node"] == node], key=lambda r: r["seq"])
            cur, best = 0, 0
            for r in seq:
                cur = cur + 1 if not r["livree"] else 0
                best = max(best, cur)
            trous.append(best)
            # Reprise : apres le retour sous le rayon fiable, delai jusqu'a la
            # premiere livraison d'une mesure.
            sortie = next((r for r in seq if math.hypot(r["x"], r["y"]) > rayon), None)
            if sortie:
                retour = next((r for r in seq if r["t"] > sortie["t"] and math.hypot(r["x"], r["y"]) <= rayon), None)
                if retour:
                    tl = min([r["tl"] for r in seq if r["livree"] and r["tl"] >= retour["t"]] or [float("nan")])
                    reprises.append(tl - retour["t"])
        print(f"  {nom}: {n} mesures produites ; livrees {100 * len(livr) / n:.1f} % ; non livrees "
              f"{100 * len(perdues) / n:.1f} % (dont perdues par debordement du tampon {tampon})")
        if delais:
            print(f"    delai de livraison : median {st.median(delais):.1f} s, 95e percentile "
                  f"{sorted(delais)[int(0.95 * (len(delais) - 1))]:.0f} s, max {max(delais):.0f} s")
        print(f"    plus long trou par patient (mesures consecutives non livrees) : median "
              f"{st.median(trous):.0f}, max {max(trous)}")
        if reprises:
            rep = [x for x in reprises if not math.isnan(x)]
            if rep:
                print(f"    reprise apres retour en couverture : median {st.median(rep):.0f} s, max {max(rep):.0f} s")
        d = [math.hypot(r["x"], r["y"]) / 1000 for r in rd]
        ok = [1 if r["livree"] else 0 for r in rd]
        ax.scatter([t["t"] / 3600 for t, o in zip(rd, ok) if o], [x for x, o in zip(d, ok) if o],
                   s=6, color=COUL[0], label="livrée")
        ax.scatter([t["t"] / 3600 for t, o in zip(rd, ok) if not o], [x for x, o in zip(d, ok) if not o],
                   s=10, color=COUL[1], marker="x", label="jamais livrée")
        ax.axhline(rayon / 1000, color=ENCRE2, linewidth=1, linestyle=(0, (4, 3)))
        axe(ax, f"{nom}", "instant de la mesure (h)", "distance du patient à la passerelle (km)")
        ax.legend(fontsize=8, frameon=False, loc="upper right")
    sauver(plt, fig, os.path.join(out, "mobilite_debordement"),
           "Chaque point est une mesure produite par un patient mobile. Tirets : rayon fiable théorique.")


def main():
    ap = argparse.ArgumentParser(description="Analyse des scenarios de mobilite")
    ap.add_argument("scenario", choices=["trajet", "equidistant", "debordement"])
    ap.add_argument("--runs", nargs="+", required=True, help="etiquette=fichier_sortie_brute")
    ap.add_argument("--out", default="./resultats")
    ap.add_argument("--pas-km", type=float, default=1.0)
    ap.add_argument("--rayon", type=float, default=None, help="Rayon fiable theorique (m), scenario c")
    a = ap.parse_args()
    runs = [tuple(r.split("=", 1)) for r in a.runs]
    os.makedirs(a.out, exist_ok=True)
    if a.scenario == "trajet":
        trajet(runs, a.out, a.pas_km)
    elif a.scenario == "equidistant":
        equidistant(runs, a.out)
    else:
        debordement(runs, a.out, a.rayon)


if __name__ == "__main__":
    main()
