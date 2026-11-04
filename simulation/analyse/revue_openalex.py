#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
revue_openalex.py

Controle reproductible de la recherche documentaire : la requete Scopus d'origine
n'ayant pas ete conservee, on interroge OpenAlex avec des requetes ecrites ici et
on mesure combien d'articles du corpus retenu elles retrouvent.
Usage : revue_openalex.py --tri <tri.xlsx> --extraction <extraction.xlsx> --out <dossier>
"""
import argparse, csv, json, os, time, urllib.parse, urllib.request
import openpyxl

Q = {"iomt_mnt": '("internet of medical things" OR IoMT OR "remote patient monitoring" OR telemonitoring) AND (hypertension OR diabetes OR "chronic disease" OR "non-communicable" OR cardiovascular) AND (architecture OR framework OR system)',
     "lpwan_sante": '(LoRaWAN OR LoRa OR LPWAN OR NB-IoT) AND ("remote patient monitoring" OR "health monitoring" OR healthcare OR telemedicine)',
     "afrique": '("remote patient monitoring" OR mHealth OR IoT OR IoMT) AND (hypertension OR "non-communicable" OR "chronic disease") AND (Africa OR Benin OR "low-income" OR "resource-limited")',
     "cout_transport": '(LoRaWAN OR LoRa OR LPWAN) AND (cellular OR 4G OR LTE OR NB-IoT) AND (cost OR "total cost of ownership") AND (health OR healthcare OR patient)'}
MAIL = os.environ.get("OPENALEX_MAILTO", "")  # adresse facultative du « polite pool » d'OpenAlex


def get(q, cur):
    u = "https://api.openalex.org/works?" + urllib.parse.urlencode({"filter": f"title_and_abstract.search:{q},from_publication_date:2019-01-01", "per-page": 200, "page": cur, "select": "id,doi,title,publication_year,cited_by_count"})
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'stopmnt-memoire/1.0'}), timeout=60))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tri"); ap.add_argument("--extraction"); ap.add_argument("--out")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tri = {str(r[0]): r for r in list(openpyxl.load_workbook(a.tri, read_only=True)["Tri"].iter_rows(values_only=True))[1:]}
    ids = [str(r[1]) for r in list(openpyxl.load_workbook(a.extraction, read_only=True).active.iter_rows(values_only=True))[1:] if r[1]]
    corpus = {i: tri[i] for i in ids if i in tri}
    doi = lambda s: (s or "").lower().replace("https://doi.org/", "").strip()
    cdoi = {doi(r[7]): i for i, r in corpus.items() if r[7]}
    res, trouves, lignes = {}, set(), []
    for nom, q in Q.items():
        n, vus = None, []
        for pg in range(1, 6):
            d = get(q, pg)
            n = d["meta"]["count"]
            vus += d["results"]
            if len(d["results"]) < 200:
                break
            time.sleep(1.0)
        t = {cdoi[doi(w.get("doi"))] for w in vus if doi(w.get("doi")) in cdoi}
        trouves |= t
        res[nom] = {"requete": q, "resultats": n, "lus": len(vus), "corpus_retrouve": len(t)}
        for w in vus[:200]:
            lignes.append({"requete": nom, "annee": w.get("publication_year"), "citations": w.get("cited_by_count"), "doi": w.get("doi"), "titre": w.get("title")})
    res["bilan"] = {"corpus": len(corpus), "avec_doi": len(cdoi), "retrouves": len(trouves), "manquants": [corpus[i][5] for i in corpus if i not in trouves]}
    json.dump(res, open(os.path.join(a.out, "revue_openalex.json"), "w"), ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, "revue_openalex_resultats.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0]))
        w.writeheader(); w.writerows(lignes)
    print(json.dumps({k: {x: v[x] for x in v if x != "requete"} if k != "bilan" else v for k, v in res.items()}, ensure_ascii=False, indent=0)[:1800])


main()
