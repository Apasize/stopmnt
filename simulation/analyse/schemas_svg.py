#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schemas du memoire en SVG, dans le style de l'architecture d'origine (archi_vue.png), rendus par Chrome."""
import argparse
import os
import subprocess
from html import escape

ENCRE, ORANGE, BLEU, ROUGE, VERT, GRIS = "#14213d", "#b45518", "#2f6690", "#b00a0a", "#2e7d4f", "#5a6478"
FOND_O, FOND_B, FOND_V = "#fdf3ea", "#eef4f9", "#edf6f0"


def texte(x, y, t, taille=20, c=ENCRE, g=False, ancre="middle", it=False):
    """Texte sur plusieurs lignes : les lignes sont separees par \\n."""
    L = t.split("\n")
    s = ""
    for i, l in enumerate(L):
        s += (f'<text x="{x}" y="{y + i * taille * 1.25:.1f}" font-size="{taille}" fill="{c}" text-anchor="{ancre}"'
              f'{" font-weight=\"700\"" if g else ""}{" font-style=\"italic\"" if it else ""}>{escape(l)}</text>')
    return s


def fleche(pts, c=ENCRE, tirets=False, ep=3.4):
    d = " ".join(f"{x},{y}" for x, y in pts)
    m = {ENCRE: "e", ORANGE: "o", BLEU: "b", ROUGE: "r", VERT: "v", GRIS: "g"}[c]
    return (f'<polyline points="{d}" fill="none" stroke="{c}" stroke-width="{ep}" stroke-linejoin="round" '
            f'{"stroke-dasharray=\"11 7\" " if tirets else ""}marker-end="url(#f{m})"/>')


DEFS = "<defs>" + "".join(
    f'<marker id="f{k}" markerWidth="16" markerHeight="14" refX="13" refY="6.5" orient="auto" markerUnits="userSpaceOnUse">'
    f'<path d="M0,0 L15,6.5 L0,13 L3.5,6.5 z" fill="{c}"/></marker>'
    for k, c in {"e": ENCRE, "o": ORANGE, "b": BLEU, "r": ROUGE, "v": VERT, "g": GRIS}.items()) + (
    f'<marker id="fB" markerWidth="5.5" markerHeight="4.6" refX="4.6" refY="2.2" orient="auto"><path d="M0,0 L5,2.2 L0,4.4 L1.2,2.2 z" fill="{BLEU}"/></marker>') + "</defs>"


def personne(x, y, c, croix=False, e=1.0):
    s = f'<g transform="translate({x},{y}) scale({e})"><circle cx="0" cy="-48" r="29" fill="{c}"/><rect x="-46" y="-14" width="92" height="94" rx="30" fill="{c}"/>'
    if croix:
        s += '<rect x="-7" y="6" width="14" height="44" fill="#fff"/><rect x="-22" y="21" width="44" height="14" fill="#fff"/>'
    return s + "</g>"


def capteur(x, y, e=1.0):
    return (f'<g transform="translate({x},{y}) scale({e})"><rect x="-56" y="-36" width="112" height="72" rx="10" fill="#fff" stroke="{ENCRE}" stroke-width="4"/>'
            f'<rect x="-40" y="-26" width="80" height="30" rx="4" fill="#e3edf6"/><text x="0" y="-4" font-size="20" font-weight="700" fill="{ROUGE}" text-anchor="middle">182/121</text><circle cx="0" cy="20" r="7" fill="{ENCRE}"/></g>')


def pont(x, y, e=1.0):
    return (f'<g transform="translate({x},{y}) scale({e})"><rect x="-27" y="-90" width="54" height="180" fill="{GRIS}"/><rect x="-58" y="-58" width="116" height="116" rx="20" fill="{ENCRE}"/>'
            f'<rect x="-41" y="-41" width="82" height="82" rx="12" fill="#22305c"/><polyline points="-28,0 -10,0 -2,-16 10,14 28,0" fill="none" stroke="#f0a35e" stroke-width="4"/></g>')


def tel(x, y, c=BLEU, e=1.0):
    return (f'<g transform="translate({x},{y}) scale({e})"><rect x="-38" y="-72" width="76" height="144" rx="12" fill="{c}"/><rect x="-30" y="-58" width="60" height="110" rx="3" fill="#fff"/>'
            f'<polyline points="-22,0 -8,0 -2,-14 8,12 22,0" fill="none" stroke="{ROUGE}" stroke-width="3.5"/><circle cx="0" cy="62" r="5" fill="#fff"/></g>')


def serveur(x, y, e=1.0):
    s = f'<g transform="translate({x},{y}) scale({e})">'
    for dy in (-78, -26, 26):
        s += f'<rect x="-92" y="{dy}" width="184" height="44" rx="7" fill="{ENCRE}"/><circle cx="66" cy="{dy + 22}" r="7" fill="{VERT}"/>'
    return s + "</g>"


def passerelle(x, y, c=ORANGE, e=1.0):
    return (f'<g transform="translate({x},{y}) scale({e})"><path d="M-62,-54 A78,78 0 0 1 62,-54" fill="none" stroke="{c}" stroke-width="5"/><path d="M-34,-32 A44,44 0 0 1 34,-32" fill="none" stroke="{c}" stroke-width="5"/>'
            f'<rect x="-5" y="-14" width="10" height="130" fill="{c}"/><path d="M-38,110 L0,56 L38,110 z" fill="{c}"/></g>')


def barres(x, y, c=BLEU, e=1.0):
    s = f'<g transform="translate({x},{y}) scale({e})">'
    for i, h in enumerate((44, 76, 108, 142)):
        s += f'<rect x="{-70 + i * 36}" y="{70 - h}" width="26" height="{h}" fill="{c}"/>'
    return s + "</g>"


def cadenas(x, y, c=ENCRE):
    return f'<g transform="translate({x},{y})"><path d="M-12,-2 V-11 A12,12 0 0 1 12,-11 V-2" fill="none" stroke="{c}" stroke-width="4"/><rect x="-18" y="-2" width="36" height="26" fill="{c}"/></g>'


def cylindre(x, y, c=ENCRE, e=1.0):
    return (f'<g transform="translate({x},{y}) scale({e})"><path d="M-80,-52 V52 A80,16 0 0 0 80,52 V-52" fill="#fff" stroke="{c}" stroke-width="4"/><ellipse cx="0" cy="-52" rx="80" ry="16" fill="#fff" stroke="{c}" stroke-width="4"/></g>')


def page(l, h, corps):
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;background:#fff}}text{{font-family:"DejaVu Sans",sans-serif}}</style></head>'
            f'<body><svg xmlns="http://www.w3.org/2000/svg" width="{l}" height="{h}" viewBox="0 0 {l} {h}">{DEFS}{corps}</svg></body></html>')


def action(x, y, t, l=360, h=74, c=ENCRE, fond="#fff", taille=20):
    n = t.count("\n")
    return (f'<rect x="{x - l / 2}" y="{y - h / 2}" width="{l}" height="{h}" rx="{h / 2 if n == 0 else 26}" fill="{fond}" stroke="{c}" stroke-width="3"/>'
            + texte(x, y + taille * 0.36 - n * taille * 0.625, t, taille, c if c != ENCRE else ENCRE))


def losange(x, y, t, l=250, h=118, c=ENCRE, fond="#fff"):
    n = t.count("\n")
    return (f'<path d="M{x - l / 2},{y} L{x},{y - h / 2} L{x + l / 2},{y} L{x},{y + h / 2} z" fill="{fond}" stroke="{c}" stroke-width="3"/>'
            + texte(x, y + 7 - n * 12, t, 19, c))


def note(x, y, l, h, t, c=GRIS):
    return (f'<path d="M{x},{y} H{x + l - 22} L{x + l},{y + 22} V{y + h} H{x} z M{x + l - 22},{y} V{y + 22} H{x + l}" fill="#fffef6" stroke="{c}" stroke-width="2"/>'
            + texte(x + 14, y + 30, t, 17, ENCRE, ancre="start", it=True))


def initiale():
    s = capteur(310, 240) + personne(100, 240, ROUGE) + texte(100, 360, "Patient", 22, ENCRE, True) + texte(310, 318, "capteur ou\nmontre", 21, ENCRE, True)
    s += pont(610, 240, .85) + texte(610, 360, "intermédiaire", 21, ENCRE, True) + texte(610, 392, "conserve et identifie", 18, GRIS)
    s += f'<rect x="830" y="80" width="340" height="320" rx="26" fill="{FOND_O}" stroke="{ORANGE}" stroke-width="4" stroke-dasharray="14 9"/>'
    s += texte(1000, 215, "?", 110, ORANGE, True) + texte(1000, 290, "réseau longue portée", 22, ORANGE, True) + texte(1000, 322, "à choisir", 20, ORANGE)
    s += serveur(1380, 240, .9) + texte(1380, 360, "centre", 22, ENCRE, True) + texte(1380, 392, "enregistre, sécurise, alerte", 18, GRIS)
    s += personne(1690, 240, BLEU, True) + texte(1690, 360, "soignant", 22, ENCRE, True)
    for a, b in (((160, 240), (248, 240)), ((372, 240), (540, 240)), ((678, 240), (822, 240)), ((1178, 240), (1282, 240)), ((1482, 240), (1630, 240))):
        s += fleche([a, b])
    s += cadenas(455, 208) + cadenas(750, 208) + cadenas(1228, 208) + cadenas(1555, 208)
    s += texte(455, 268, "courte portée", 17, GRIS) + texte(860, 460, "Identité et droits, sécurité des échanges, supervision et sauvegarde sur toute la chaîne", 19, GRIS)
    return page(1790, 490, s)


def activites():
    L = [(40, 500, "Patient et capteur"), (540, 500, "Intermédiaire"), (1040, 500, "Centre et soignant")]
    s = ""
    for x, l, t in L:
        s += f'<rect x="{x}" y="20" width="{l}" height="1120" fill="none" stroke="{GRIS}" stroke-width="2"/><rect x="{x}" y="20" width="{l}" height="54" fill="#f1f3f7" stroke="{GRIS}" stroke-width="2"/>' + texte(x + l / 2, 55, t, 22, ENCRE, True)
    s += f'<circle cx="290" cy="120" r="15" fill="{ENCRE}"/>' + fleche([(290, 135), (290, 180)])
    s += action(290, 220, "Prendre la mesure", 330, 70) + fleche([(455, 220), (610, 220)]) + action(790, 220, "Recevoir, horodater\net identifier", 360, 84)
    s += fleche([(790, 262), (790, 306)]) + action(790, 342, "Écrire au journal local", 360, 66) + fleche([(790, 375), (790, 420)])
    s += action(790, 462, "Repérer une alerte\net la mettre en priorité", 360, 84) + fleche([(790, 504), (790, 556)])
    s += losange(790, 630, "Réseau\ndisponible ?", 280, 140)
    s += fleche([(930, 630), (1110, 630)]) + texte(1020, 620, "oui", 19, ENCRE, True) + action(1290, 630, "Enregistrer la mesure\nune seule fois", 360, 84)
    s += fleche([(790, 700), (790, 790)]) + texte(816, 770, "non", 19, ENCRE, True) + action(790, 826, "Attendre et réessayer", 340, 66)
    s += fleche([(620, 826), (582, 826), (582, 630), (650, 630)], GRIS)
    s += fleche([(620, 840), (430, 840)], ROUGE, True) + action(290, 840, "Alarme locale", 280, 66, ROUGE) + texte(500, 874, "alerte non\nconfirmée", 17, ROUGE)
    s += fleche([(1290, 672), (1290, 716)]) + losange(1290, 770, "Alerte ?", 220, 104)
    s += fleche([(1290, 822), (1290, 866)]) + texte(1316, 852, "oui", 19, ENCRE, True) + action(1290, 900, "Prévenir l'agent,\npuis le soignant", 330, 80)
    s += fleche([(1400, 770), (1500, 770), (1500, 1010), (1466, 1010)]) + texte(1440, 760, "non", 19, ENCRE, True)
    s += fleche([(1290, 940), (1290, 974)]) + action(1290, 1010, "Confirmer ce qui\nest enregistré", 350, 74)
    s += fleche([(1115, 1010), (970, 1010)]) + action(790, 1010, "Effacer le confirmé,\nrenvoyer le manquant", 360, 84)
    s += fleche([(790, 1052), (790, 1090)]) + f'<circle cx="790" cy="1108" r="16" fill="#fff" stroke="{ENCRE}" stroke-width="3"/><circle cx="790" cy="1108" r="9" fill="{ENCRE}"/>'
    s += note(70, 960, 420, 120, "Une coupure de réseau retarde\nla mesure sans la perdre, tant\nque le journal n'est pas plein.")
    return page(1560, 1160, s)


def logique():
    C = [("Acquisition", ["Capteurs BLE", "Health Connect"], BLEU), ("Intermédiaire", ["Smartphone (application)", "Pont LoRaWAN", "Pont cellulaire"], ENCRE),
         ("Transport", ["Cellulaire ou Wi-Fi, HTTPS", "LoRaWAN, ChirpStack", "4G/2G, MQTT sur TLS"], ORANGE), ("Ingestion", ["API FastAPI", "Courtier et worker"], ENCRE),
         ("Stockage", ["PostgreSQL : comptes, mesures, alertes", "InfluxDB : séries temporelles"], VERT), ("Restitution", ["Interface web", "Grafana", "Notifications"], VERT)]
    s = ""
    x0, lt, y = 220, 1130, 20
    for nom, B, c in C:
        fond = {BLEU: FOND_B, ORANGE: FOND_O, VERT: FOND_V, ENCRE: "#f1f3f7"}[c]
        s += f'<rect x="20" y="{y}" width="1330" height="96" rx="14" fill="{fond}"/>' + texte(40, y + 55, nom, 22, c, True, "start")
        l = (lt - 16 * (len(B) + 1)) / len(B)
        for i, b in enumerate(B):
            xb = x0 - 12 + 16 + i * (l + 16)
            s += f'<rect x="{xb}" y="{y + 17}" width="{l}" height="62" rx="10" fill="#fff" stroke="{c}" stroke-width="2.6"/>' + texte(xb + l / 2, y + 55, b, 19 if len(b) < 34 else 17, ENCRE)
        if nom != "Restitution":
            s += fleche([(790, y + 96), (790, y + 118)], GRIS, ep=3)
        y += 118
    s += f'<rect x="1372" y="20" width="168" height="686" rx="14" fill="#f1f3f7" stroke="{GRIS}" stroke-width="2.4"/>'
    for i, t in enumerate(("Identité\net droits", "Sécurité", "Supervision", "Sauvegarde")):
        s += texte(1456, 130 + i * 160, t, 20, ENCRE, True)
    return page(1560, 726, s)


def prototype():
    s = ""
    def boite(x, y, l, h, t, st, c, fond):
        return (f'<rect x="{x}" y="{y}" width="{l}" height="{h}" rx="14" fill="{fond}" stroke="{c}" stroke-width="3"/>' + texte(x + l / 2, y + 42, t, 22, c if c != ENCRE else ENCRE, True) + texte(x + l / 2, y + 76, st, 18, GRIS))
    s += boite(20, 50, 300, 118, "Capteurs BLE", "appareils compatibles", BLEU, FOND_B) + boite(20, 200, 300, 118, "Health Connect", "données autorisées", BLEU, FOND_B)
    s += tel(520, 150, BLEU, 1.05) + texte(520, 258, "Application Android", 22, ENCRE, True) + texte(520, 290, "Flutter, jeton JWT,\nfile locale par patient", 18, GRIS)
    s += fleche([(324, 110), (470, 140)]) + fleche([(324, 258), (470, 180)])
    s += serveur(910, 150, .9) + texte(910, 258, "Serveur", 22, ENCRE, True) + texte(910, 290, "Nginx, API FastAPI, Redis", 18, GRIS)
    s += fleche([(568, 150), (812, 150)]) + texte(690, 136, "HTTPS / REST", 18, ENCRE, True) + cadenas(690, 170)
    s += boite(1200, 50, 320, 118, "PostgreSQL", "comptes, mesures, alertes", VERT, FOND_V) + boite(1200, 200, 320, 118, "Restitution", "interface web, Grafana", VERT, FOND_V)
    s += fleche([(1006, 130), (1196, 110)]) + fleche([(1006, 170), (1196, 258)])
    s += f'<line x1="20" x2="1520" y1="362" y2="362" stroke="{GRIS}" stroke-dasharray="6 7" stroke-width="2"/>' + texte(20, 396, "Chemin destiné aux futurs ponts autonomes", 18, ORANGE, True, "start")
    s += boite(360, 420, 320, 118, "Simulateur Python", "publication MQTT", ORANGE, FOND_O) + boite(780, 420, 320, 118, "Mosquitto, worker", "TLS, certificat par dispositif", ORANGE, FOND_O) + boite(1200, 420, 320, 118, "InfluxDB", "séries temporelles", ORANGE, FOND_O)
    s += fleche([(684, 479), (776, 479)], ORANGE) + fleche([(1104, 479), (1196, 479)], ORANGE)
    return page(1540, 560, s)


def hybride(fond):
    """Architecture d'origine de l'auteur, conservee telle quelle, completee par la voie du smartphone."""
    H = 300
    s = f'<image href="{fond}" x="0" y="{H}" width="2400" height="1050"/>'
    s += f'<rect x="1040" y="{H + 12}" width="330" height="44" fill="#fff"/>' + texte(1230, H + 44, "selon la zone", 27, ORANGE, True)
    # voie du smartphone, au-dessus
    s += fleche([(372, H + 462), (150, H + 345), (150, 225)], BLEU, ep=5)
    s += tel(150, 125, BLEU, 1.0) + texte(270, 96, "smartphone du patient équipé", 27, BLEU, True, "start") + texte(270, 132, "application, file locale", 24, BLEU, False, "start")
    s += fleche([(212, 170), (1120, 170)], BLEU, ep=5) + cadenas(760, 128, BLEU)
    s += barres(1230, 150, BLEU, .72) + texte(1230, 232, "cellulaire ou Wi-Fi", 27, BLEU, True)
    s += fleche([(1345, 170), (1640, H + 310)], BLEU, ep=5) + cadenas(1500, 300, BLEU)
    s = s.replace("url(#fb)", "url(#fB)")
    return page(2400, H + 1050, s)


def rendre(html, png, l, h, chrome):
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", "--force-device-scale-factor=2", "--allow-file-access-from-files",
                    f"--window-size={l},{h}", f"--screenshot={png}", "file://" + os.path.abspath(html)], check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--src", default="analyse/schemas")
    ap.add_argument("--chrome", default="google-chrome")
    ap.add_argument("--origine", default=None, help="archi_vue.png, base de l'architecture hybride")
    a = ap.parse_args()
    for nom, fn, l, h in (("architecture_initiale", initiale, 1790, 490), ("activites_flux", activites, 1560, 1160),
                          ("architecture_logique", logique, 1560, 726), ("prototype_chaine", prototype, 1540, 560)):
        p = os.path.join(a.src, nom + ".html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(fn())
        rendre(p, os.path.join(a.out, nom + ".png"), l, h, a.chrome)
    if a.origine:
        p = os.path.join(a.src, "architecture_hybride.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(hybride("file://" + os.path.abspath(a.origine)))
        rendre(p, os.path.join(a.out, "architecture_hybride.png"), 2400, 1350, a.chrome)


if __name__ == "__main__":
    main()
