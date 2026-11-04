# Simulation du réseau de collecte

Code et résultats du volet réseau du mémoire de master de Phoris Andy AGBOZOGNIGBE (IFRI, Université d'Abomey-Calavi, 2026) : *Conception d'une architecture IoMT pour la collecte des données utiles à la prévention des MNT en environnement à ressources limitées : application au projet STOP-MNT*.

Le dépôt contient la simulation LoRaWAN (ns-3.48, module `lorawan` 0.3.7), les bilans cellulaires, le modèle de coût, l'optimisation du placement des passerelles et les tests du prototype.

## Contenu

| Dossier | Rôle |
|---|---|
| `config/config.json` | Source unique de toutes les valeurs (radio, zones, trafic, coûts, expériences). |
| `model/` | Modèle ns-3 en C++ (`lorawan-cell-shadow.cc`, compilé sous le nom `stopmnt-production`) et modifications du module `lorawan`. |
| `orchestrateur/` | Lancement des campagnes : `run_experiences.py`, `run_mobilite.py`, scripts `campagne_*.sh` (dont `campagne_8dbi.sh`). |
| `analyse/` | Des résultats aux tableaux et figures : portée, capacité, coût, Monte-Carlo, optimisation (HiGHS), convergence, registre des chiffres. |
| `resultats/syntheses/` | Registre des chiffres du chapitre 3 (`REGISTRE_CHIFFRES.md`), synthèse de la relance à 8 dBi, CSV finaux (coûts, optimisation, convergence). Les résultats bruts ne sont pas versionnés (volume). |
| `donnees/` | Contours ARCEP. WorldPop 2021 (100 m, version contrainte R2024B) et ESA WorldCover 2021 (tuile N06E000) sont à télécharger depuis leurs sites, trop volumineux pour le dépôt. |

Le fonctionnement détaillé est décrit dans `GUIDE_DU_CODE.md`.

## Reproduire

```bash
cp model/lorawan-cell-shadow.cc ~/ns-3.48/scratch/stopmnt-production.cc
cp model/stopmnt-propagation.h ~/ns-3.48/scratch/
cd ~/ns-3.48 && ./ns3 build
cd -  # retour au dépôt
python3 orchestrateur/run_experiences.py --config config/config.json --ns3-dir ~/ns-3.48 \
  --shadow-bin stopmnt-production --exp capacite_recap_8dbi --out resultats/production/final/capacite_recap_8dbi
python3 analyse/convention_v63.py --config config/config_final.json --v62 resultats/production/cout_v62 \
  --out resultats/production/final/central
python3 analyse/optimisation_cout.py --config config/config.json --out resultats/production/final/optimisation
```

Chaque répétition porte un numéro de tirage enregistré avec ses résultats ; le modèle de coût fixe ses tirages par une graine.
