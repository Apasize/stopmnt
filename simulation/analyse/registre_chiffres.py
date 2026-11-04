"""Relie les chiffres du mémoire à leur fichier source et vérifie leur présence dans le texte."""
import argparse
import csv
import os


def lire(*p):
    with open(os.path.join(*p), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def fr(v, n=1):
    """Arrondi au plus proche, la moitie vers le haut, comme dans le memoire (28,15 -> 28,2)."""
    from decimal import Decimal, ROUND_HALF_UP
    q = Decimal(1).scaleb(-n)
    return str(Decimal(str(v)).quantize(q, rounding=ROUND_HALF_UP)).replace(".", ",")


def entier(v):
    v = int(float(v))
    return f"{v // 1000}~{v % 1000:03d}" if v >= 1000 else str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resultats", default="resultats/production/final")
    ap.add_argument("--memoire", required=True)
    ap.add_argument("--out", default="resultats/syntheses/REGISTRE_CHIFFRES.md")
    a = ap.parse_args()
    d = os.path.join(a.resultats, "optimisation")
    with open(os.path.join(a.memoire, "3-partie/1-fichier.tex"), encoding="utf-8") as f:
        tex = f.read()
    sc = {r["scenario"]: r for r in lire(d, "optimisation_scenarios.csv")}
    ho = {(r["scenario"], r["rayon"]): r for r in lire(d, "comparaison_homogene.csv")}
    se = {r["scenario"]: r for r in lire(d, "seuils_passerelle.csv")}
    lignes = []

    def note(nom, val, fichier):
        lignes.append((nom, val, fichier, val in tex))

    noms = {"bas": "Bas", "centre_detaille": "Central détaillé", "centre_kerlink": "Central Kerlink", "haut": "Haut"}
    for s, n in noms.items():
        note(f"{n}, par maille, €/patient/an", fr(sc[s]["eur_patient_an"]), "optimisation/optimisation_scenarios.csv")
        note(f"{n}, par maille, passerelles", sc[s]["passerelles"], "optimisation/optimisation_scenarios.csv")
        h = ho[(s, "passerelle_seule")]
        note(f"{n}, tout cellulaire", fr(h["tout_cellulaire"]), "optimisation/comparaison_homogene.csv")
        note(f"{n}, par commune, rayon passerelle seule", fr(h["choix_commune"]), "optimisation/comparaison_homogene.csv")
        note(f"{n}, patients pour rembourser une passerelle", str(round(float(se[s]["patients_pour_rembourser"]))), "optimisation/seuils_passerelle.csv")
    for s, r in sc.items():
        if s not in noms and s != "smartphone_kerlink":
            note(f"Variante {s}, €/patient/an", fr(r["eur_patient_an"]), "optimisation/optimisation_scenarios.csv")
            note(f"Variante {s}, passerelles", r["passerelles"], "optimisation/optimisation_scenarios.csv")
    note("Couverture complète, réseau dense", ho[("centre_detaille", "reseau_pave")]["passerelles_couverture"], "optimisation/comparaison_homogene.csv")
    note("Couverture complète, passerelle seule", entier(ho[("centre_detaille", "passerelle_seule")]["passerelles_couverture"]), "optimisation/comparaison_homogene.csv")

    # Capacite a 8 dBi
    for n, f in (("capacite_8dbi", "capacite_8dbi/capacite_production.csv"), ("recap", "capacite_recap_8dbi/capacite_production.csv")):
        for r in lire(a.resultats, f):
            v = []
            for k in ("capacite_interpolee_livraison", "capacite_interpolee_delai_routine", "capacite_interpolee_delai_alerte"):
                try:
                    v.append(float(r[k]))
                except ValueError:
                    pass
            if v:
                note(f"Capacité {r['zone']}, {r['mode']}", entier(min(v) + .5), f)
    # Rayons
    for f, g in (("portee_v6", "gain=5"), ("portee_gain_v61", "gain=8"), ("portee_gain_v61", "gain=9")):
        for r in lire(a.resultats, "..", f, "rayon_fiable_probit", "rayon_fiable_probit.csv"):
            if r["groupe"].endswith(g):
                note(f"Rayon fiable {r['groupe']}", fr(float(r["rayon_fiable_m"]) / 1000, 2), f)
    # Couverture ARCEP
    for r in lire(a.resultats, "..", "cellulaire", "couverture_arcep_communes.csv"):
        for k in ("4g_bonne_MTN", "4g_bonne_MOOV", "4g_bonne_CELTIIS", "2g_bonne_meilleure"):
            x = float(r[k]) * (100 if float(r[k]) <= 1 else 1)
            v = fr(x, 1)
            note(f"ARCEP {r['commune']} {k}", "100" if v == "100,0" else v, "cellulaire/couverture_arcep_communes.csv")
    # Mobilite
    M = lire(a.resultats, "mobilite_reseau", "mobilite_interieur.csv")
    for scn in ("a_trajet", "d_trajet_reseau"):
        for var in ("mobileSfsf12", "mobileSforacle", "mobileSfadr"):
            for champ in ("routine_72h", "alerte_15min"):
                v = [100 * float(r[champ]) for r in M if r["scenario"] == scn and r["variante"] == var]
                if v:
                    note(f"Mobilité {scn} {var} {champ}", f"{min(v):.0f} -- {max(v):.0f}", "mobilite_reseau/mobilite_interieur.csv")
    # Couts par commune et Monte-Carlo
    C = "central/cout_communes_v63.csv"
    for r in lire(a.resultats, C):
        if r["f_global_fcfa_an"] == "10000000" and r["k"] == "1.0" and r["source"] in ("scénario bas", "scénario haut") and "sous convention" in r["option"]:
            note(f"Coût {r['commune']} {r['source']} {r['option']}", fr(r["eur_patient_an"]), C)
    D = "central/cout_departement_v63.csv"
    for r in lire(a.resultats, D):
        if r["f_global_fcfa_an"] == "10000000" and r["k"] == "1.0" and r["source"].startswith("Monte"):
            note(f"Monte-Carlo {r['source']} {r['architecture']}", f"{fr(r['eur_patient_an'])} [{fr(r['p2_5'])} ; {fr(r['p97_5'])}]", D)
    gains = [100 * (float(ho[(s, "passerelle_seule")]["choix_commune"]) - float(sc[s]["eur_patient_an"])) / float(ho[(s, "passerelle_seule")]["choix_commune"]) for s in noms]
    absents = [l for l in lignes if not l[3]]

    def motif(n):
        if n.startswith("ARCEP departement"):
            return "total départemental, non cité ; le tableau 3.6 donne les valeurs par commune"
        return "à vérifier"
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("# Registre des chiffres de l'optimisation\n\n")
        f.write(f"Fichier produit par `analyse/registre_chiffres.py`. {len(lignes) - len(absents)} valeurs sur {len(lignes)} retrouvées au chiffre près dans le chapitre 3.\n\n")
        f.write(f"Gain du choix par maille sur le choix par commune, à rayon égal : {min(gains):.1f} à {max(gains):.1f} %.\n\n")
        f.write("Les valeurs absentes du texte sont expliquées dans la dernière colonne.\n\n")
        f.write("| Chiffre | Valeur | Source (sous `resultats/production/final/`) | Dans le texte |\n|---|---|---|---|\n")
        for n, v, s, ok in lignes:
            f.write(f"| {n} | {v.replace('~', ' ')} | `{s}` | {'oui' if ok else 'non : ' + motif(n)} |\n")
    print(len(lignes), "valeurs,", len(absents), "absentes", [(l[0], l[1]) for l in absents], [round(g, 1) for g in gains])


if __name__ == "__main__":
    main()
