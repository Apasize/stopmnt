# Relance à 8 dBi des expériences du chapitre 3 (4 novembre 2026)

Scripts : `orchestrateur/campagne_8dbi.sh`, `orchestrateur/campagne_8dbi_suite.sh`. Gain lu dans `config/config.json` (8,0 dBi), vérifié dans chaque instantané de configuration.

| Résultat (mémoire) | 5 dBi | 8 dBi | Source 8 dBi |
|---|---|---|---|
| Accusés tardifs, RX1 = 1 s, 5 % de retards (3.1.3) | 15,3 % | 15,3 (urbain) à 15,4 % (rural) | `remontee_v6/capacite_points_production.csv` |
| Même chose, RX1 = 5 s | 1,2 % | 1,2 % | idem |
| Garde-et-renvoi, sans / avec (tableau 3.3) | 97,9 / 99,7 % | 97,3 / 99,6 % | `mobilite_interieur/mobilite_interieur.csv` |
| Patients fixes au-dessus de 95 %, récapitulatif (3.1.4) | 97,45 à 99,95 % | 97,45 à 99,95 % | `exigences_continuite/exigences_v6.csv` |
| Alertes, cellule isolée, 200 patients (3.2.1) | 97,5 à 98,5 % | 97,4 à 98,5 % | `exigences_cellule/exigences_v6.csv` |
| Alertes, réseau pavé à 2 rayons (3.2.1) | 99,50 à 99,68 % | 99,50 à 99,68 % | `exigences_reseau/exigences_v6.csv` |
| Patients en ombre persistante | 1,4 à 3,4 % | 1,4 à 3,4 % | `exigences_reseau/secours_lora.csv` |
| Alertes avec secours cellulaire | 99,85 à 99,94 % | 99,85 à 99,94 % | idem |
| Seuils de corrélation lacustre / urbain | 0,26 / 0,70 | 0,26 / 0,70 | calcul à partir des parts en ombre (inchangées) |
| Panne : patients servis à l'espacement de routine (3.2.2) | 92,0 à 97,3 % | 92,5 à 97,3 % | `robustesse_v6/robustesse_panne.csv` |
| Seuil de 90 % : arboré / urbain | 3,2 / 8,8 rayons | 3,2 / 8,8 rayons | idem |
| Espacement tenu (corrélation 0,5), 5 zones | 6 / 3,5 / 3 / 3 / 4 | identique | `multi_passerelles_v6/multi_passerelles_synthese_production.csv` |
| Rayon fiable extérieur (figure 3.1) : rural, urbain, lacustre | 6,08 / 4,83 / 14,07 km | 8,07 / 7,84 / 20,16 km (division par 4 à 8 avec les murs) | `portee_interieur_8dbi/rayon_fiable_probit/` |
| Énergie du pont LoRa, jusqu'à 200 patients (3.3.3) | texte : 0,47 à 1,13 J/j | 0,45 à 1,16 J/j | `../capacite_8dbi`, `../capacite_recap_8dbi` |
| Variante en réseau dense | 112 passerelles (anciennes capacités) | 113, 35,82 €/patient/an | `optimisation_rayon_diversite/optimum_scenarios.csv` |

Pourquoi les résultats bougent si peu : avec une loi log-distance, un gain de G dB multiplie toutes les distances par un même facteur. Des résultats exprimés en rayons fiables sont donc invariants, sauf là où cette homothétie est brisée (plancher à 100 m, végétation, horizon), ce qui explique les petits écarts en zones arborée et lacustre.

Erreur d'étiquette corrigée : les 99,54 à 99,65 % du texte étaient la livraison de routine de l'expérience multi-passerelles (20 répétitions), pas celle des alertes. Le texte donne maintenant les alertes du réseau pavé (99,50 à 99,68 %, 10 répétitions).

Figures régénérées : `figures/robustesse_indisponibilite_passerelle.png` (figure 3.6), `figures/g3_accuses.png` (figure 3.5, zone urbaine, comme l'originale).
