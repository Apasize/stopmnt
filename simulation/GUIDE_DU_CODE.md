# Guide du code, simulation réseau STOP-MNT

Ce guide sert à expliquer et à modifier soi-même la chaîne de simulation. État du 29 octobre 2026 (complément v6.2). **La simulation est gelée** : seules des erreurs sont à corriger, pas de nouvelle expérience.

## 1. Le principe en une phrase

Trois couches séparées :
- **`config/config.json`** porte toutes les valeurs ;
- **l'orchestrateur Python** décide quels runs lancer et lit leurs résultats ;
- **le modèle ns-3 en C++** simule une cellule pendant un run et rend des lignes de texte.

Les scripts d'analyse transforment ensuite ces lignes en tableaux et en figures. Aucune valeur numérique ne vit en dur dans le code : on change le config, pas le code.

## 2. Architecture des dossiers

```
stopmnt-sim/
├── GUIDE_DU_CODE.md          ce guide
├── config/config.json        LA source de vérité : radio, zones, trafic, coût, expériences
├── donnees/                  données externes téléchargées (non modifiées) : WorldPop 2021, ESA WorldCover 2021 (tuile N06E000), contours ARCEP
├── model/                    code C++ du modèle ns-3
│   ├── lorawan-cell-shadow.cc   modèle principal (copié dans ns-3 sous le nom stopmnt-production.cc)
│   ├── stopmnt-propagation.h    maillons de propagation propres au projet
│   ├── lorawan-cell.cc          ancien modèle de référence, sans ombrage (plus utilisé)
│   ├── lte-cell.cc              essai 4G avec le module LTE de ns-3 (abandonné, voir § 8)
│   └── patch_module_lorawan/    modifications du module lorawan, sauvegardées (§ 5)
├── orchestrateur/            lancement des campagnes
│   ├── run_experiences.py       orchestrateur générique (toutes les expériences du config)
│   ├── run_mobilite.py          scénarios de patients mobiles
│   ├── run_sfw_longue.py        test du tampon de 72 h en charge
│   └── campagne_v4.sh, _v5.sh, _v6.sh   enchaînements d'expériences
├── analyse/                  des CSV aux tableaux et aux figures (§ 7)
└── resultats/
    ├── production/<expérience>/ sorties brutes et analysées, un dossier par expérience
    └── syntheses/               registre des chiffres, synthèses et CSV finaux
```

Le module ns-3 vit hors du dossier, dans `~/ns-3.48/` (ns-3.48, module lorawan 0.3.7 dans `contrib/lorawan`).

## 3. Rôle de chaque fichier

### Configuration

**`config/config.json`** contient les blocs suivants :

| Bloc | Contenu |
|---|---|
| `radio` | Fréquence, puissance du nœud, horizon radio, corrélation de l'ombrage entre sites, extrapolation sous 1 km |
| `trafic` | Tailles de trame, cadences cibles (10 et 15 messages par jour) |
| `passerelle` | Hauteur, gain d'antenne, sensibilité par SF (SX1302), fenêtres de réception (RX1, RX2), modèle de remontée |
| `noeud` | Hauteur, sensibilité, énergie (SX1272 du module), perte en intérieur (P.2109) |
| `zones` | Cinq terrains : exposant, perte à 1 km, ombrage, végétation, sources |
| `methode` | Répétitions, durée simulée, seuil de qualité, règle des répétitions |
| `qualite_service` | Seuils (95 %, 60 s, part servie en panne, exigences v6) |
| `profils_patients` | Mélange de profils, alerte, confirmation, récapitulatif |
| `store_and_forward` | Paramètres du tampon |
| `cellulaire` | MCL 4G et 2G, bandes, module Cat-1 |
| `cout` | Prix, sources, scénarios d'abonnement, communes, marge de robustesse, exploitation |
| `experiences` | Une entrée par expérience (§ 6) |

Chaque valeur porte une clé `_source...` voisine : origine, date, statut (mesuré, catalogue, hypothèse).

### Modèle C++

**`model/lorawan-cell-shadow.cc`** (environ 2 300 lignes), dans l'ordre du fichier :

1. **Compteurs par nœud** (`NodeStats`), branchés sur les traces du module : trames envoyées, reçues, acquittées, temps d'antenne, alertes, mesures, énergie, récapitulatif.
2. **Suivi par alerte** (`AlertRec`, v6) : instant de production, intérieur ou non, livraison, acquittement, alarme du pont.
3. **`IndoorLossModel`** (v6) : maillon de propagation qui retire la perte en intérieur pour chaque extrémité « nœud à l'intérieur ».
4. **`ProfileSender`** : l'application du pont. Elle produit :
   - la routine (cadence du profil) ;
   - les alertes (processus de Poisson) ;
   - le store-and-forward (sonde, tampon, lots) ;
   - le récapitulatif quotidien (v6) ;
   - l'alarme technique locale.
5. **`main`** :
   - lit les arguments (`cmd.AddValue`) ;
   - règle le module (fenêtres, remontée, sensibilité) ;
   - construit la chaîne de propagation ;
   - place les nœuds et les passerelles ;
   - installe les applications ;
   - lance la simulation et écrit les lignes de sortie.

**`model/stopmnt-propagation.h`** contient les maillons de propagation propres au projet :
- `NodeShadowingLossModel` : ombrage par nœud, réglable par zone, corrélé entre sites ;
- `VegetationLossModel` : végétation UIT-R P.833 ;
- `GatewayRxGainModel` : gain d'antenne de la passerelle, en réception seulement ;
- `RadioHorizonLossModel` : horizon radio ;
- `ExcessLossModel` : perte fixe.

### Orchestrateur Python

**`orchestrateur/run_experiences.py`** :
- `resoudre_experience` : héritage entre expériences (`experience_de_base`, en chaîne) ;
- `variantes_zone` : produit cartésien des balayages (gain, végétation, intérieur, espacement, mode, cadence, RX1, puissance RX2, panne, part du temps à l'intérieur, sensibilité, pics de remontée, alertes) ;
- `construire_args` : traduit config + zone + variante en arguments du binaire ns-3 ;
- `rayon_fiable_theorique`, `rayon_dimensionnement`, `rayon_descendant_rx2` : bilans de liaison qui fixent la géométrie ;
- `p2109_mediane_db`, `perte_interieur_db`, `reference_effective` : intérieur et extrapolation sous 1 km (v6) ;
- `lire_lignes_noeuds`, `lire_lignes_ack` : lecture des sorties.

Les deux autres lanceurs :
- **`run_mobilite.py`** : patients mobiles (trajets, politiques de SF, store-and-forward).
- **`run_sfw_longue.py`** : tampon de 72 h. Des mobiles sortent de la couverture 48 ou 96 h.

## 4. Parcours d'une trame, du pont au serveur

1. **Production.** `ProfileSender::Routine` (ou `Alert`) crée une mesure (`NewReading`, notée dans `g_readings`), puis appelle `SendReadings`.
2. **Emballage.** `SendReadings` crée le paquet, règle sur la MAC le type (confirmé ou non) et le nombre de transmissions, puis appelle `m_mac->Send`. Le module ajoute ses en-têtes LoRaWAN ; le MIC de 4 octets est ajouté par nous (`micBytes`).
3. **MAC du nœud** (module, `EndDeviceLorawanMac`). Elle choisit un canal libre au sens du cycle de service (1 % dans la sous-bande 868,0 à 868,6 MHz) et émet. La trace `SentNewPacket` alimente `OnMacNewPacket`.
4. **Canal.** `LoraChannel` calcule la puissance reçue par chaque radio à travers la chaîne de propagation :
   - log-distance avec d0 effectif ;
   - ombrage ;
   - gain de la passerelle ;
   - végétation ;
   - intérieur ;
   - horizon.
5. **Passerelle** (module, `GatewayLoraPhy`). Elle reçoit si la puissance dépasse la sensibilité du SF (SX1302 en v6) et si un des 8 chemins de réception est libre. Les collisions sont jugées sur l'interférence. Une réception déclenche `OnGwMacReceived` : première réception = trame livrée, mesures livrées, alerte livrée.
6. **Remontée.** Lien point à point de 2 ms vers le serveur. En v6, la latence réelle est tirée par le planificateur du module (§ 5).
7. **Serveur** (module, `NetworkServer`, puis `NetworkScheduler::OnReceivedPacket`). Si la montante est confirmée, il programme l'accusé :
   - fenêtre RX1 (même canal, 14 dBm) ou RX2 (869,525 MHz, SF12, 27 dBm) ;
   - choix selon le bilan prévu (option `rx1Check`) et selon la remontée (v6).
8. **Accusé.** La passerelle émet l'accusé, sauf si elle est déjà en train d'émettre ou si le cycle de service RX2 (10 %) est épuisé. La MAC du nœud ouvre RX1 puis RX2 ; sans accusé, elle retransmet jusqu'à `nbTrans`. L'issue arrive par la trace `ConfirmedTransmissionOutcome` vers :
   - `OnConfirmedOutcome` : compteurs ;
   - `ProfileSender::OnOutcome` : logique de l'application (tampon, récapitulatif, alarme).
9. **Fin de run.** Une ligne `CSV;` agrégée, une ligne `NODE;` par nœud, des lignes `ACK;` de percentiles, et pour les mobiles des lignes `PKT;`, `DL;` et `RD;`.

## 5. Modifications apportées au module lorawan, et pourquoi

Toutes sont désactivées par défaut. Avec les valeurs par défaut, un run de référence redonne exactement le résultat d'avant (vérifié à chaque étape). Fichiers d'origine (`*.orig`), versions modifiées (`*.stopmnt`) et patch complet (`stopmnt-module-complet.patch`) : dans `model/patch_module_lorawan/`.

| Fichier du module | Modification | Pourquoi |
|---|---|---|
| `network-scheduler.h/.cc` | `Rx1BudgetCheck`, `Rx1MarginDb`, `GwRxGainDb` : accusé en RX2 si RX1 (14 dBm) ne porte pas | Rendre le tout-confirmé viable (revue du 27/10) |
| `network-scheduler.h/.cc` | `Rx1Delay` : instant de la réponse | Délai RX1 de 5 s (consignes v4) |
| `network-scheduler.h/.cc` | `BackhaulModel` et paramètres `Bh*`, `DedupMs`, `TooLateMs` : latence tirée, pics, retransmission TCP, déduplication, estimation de l'aller-retour (90e centile des 20 derniers), rejet TOO_LATE puis fenêtre suivante ; compteurs `s_bh*` | Remontée réaliste (consignes v6, point 3) |
| `class-a-end-device-lorawan-mac.cc` | Attributs `ReceiveDelay1` et `ReceiveDelay2` | Délai RX1 réglable côté nœud |
| `logical-lora-channel-helper.h` | `GetSubBandFromFrequency` rendu public | Régler la puissance de la sous-bande RX2 (scénario 14 dBm) |
| `gateway-lora-phy.h/.cc` | `SENSITIVITY` non constant | Sensibilité SX1302 au lieu de SX1301 (consignes v6, point 1) |

Après toute modification du module ou du modèle :

```
cp model/lorawan-cell-shadow.cc ~/ns-3.48/scratch/stopmnt-production.cc
cp model/stopmnt-propagation.h ~/ns-3.48/scratch/
cd ~/ns-3.48 && ./ns3 build stopmnt-production
```

Compter quelques minutes si le module a changé, quelques secondes sinon.

## 6. Changer un paramètre et relancer une seule expérience

**Exemple : passer la perte en intérieur de dimensionnement à 10 dB et refaire la portée.**

1. Dans `config/config.json`, `noeud.interieur.perte_dimensionnement_db` : 14.219 → 10. Mettre à jour la clé `_source...` voisine.
2. Lancer :

```
cd ~/stopmnt-sim
.venv/bin/python orchestrateur/run_experiences.py --config config/config.json \
  --ns3-dir ~/ns-3.48 --shadow-bin stopmnt-production --exp portee_v6 --jobs 11 \
  --out resultats/production/portee_v6_essai
```

3. Analyser :

```
.venv/bin/python analyse/rayon_fiable.py --probit --config config/config.json \
  --noeuds resultats/production/portee_v6_essai/noeuds_*.csv --out resultats/production/portee_v6_essai/rayon_fiable_probit
```

**Options utiles de l'orchestrateur :**
- `--zones` : restreindre les zones ;
- `--modes` : restreindre les modes ;
- `--nb-noeuds` : imposer les paliers ;
- `--repetitions` : forcer le nombre de répétitions ;
- `--duree-jours` : durée simulée ;
- `--reprendre` : reprendre une campagne interrompue ;
- `--smoke` : un essai minimal.

**Durées approximatives** (12 cœurs, `--jobs 11`) :

| Expérience | Runs | Durée |
|---|---|---|
| Portée, 5 zones × 100 répétitions | 500 | moins d'une minute |
| Multi-passerelles, 5 zones × 9 espacements × 3 corrélations × 20 | 2 700 | 4 à 15 min |
| Robustesse, 5 zones × 31 espacements × 2 états × 20 | 3 100 | environ 5 min |
| Capacité, 5 zones × 3 modes × 7 paliers × 10, 2 jours | ~1 000 | 1 à 3 h (les gros paliers sont les plus longs) |
| Capacité à récapitulatif, 4 jours | ~350 | 1 à 2 h |
| Tampon de 72 h, 80 runs de 10 jours | 80 | environ 20 min |
| Couche coût | | quelques secondes |
| Tornade | | environ 1 min |
| Monte-Carlo, 500 tirages | | quelques minutes |

**Options de la couche coût** (`analyse/couche_cout.py`) :
- `--scenario-rx2-14dbm` : RX2 à 14 dBm, cellules dimensionnées sur la voie descendante ;
- `--espacement-alerte` : espacement fixé par l'exigence d'alerte (`cout.espacement_exigence_alerte`) ;
- `--sans-figure` : pas de figure, pour les appels répétés.

La tornade (`tornade_cout.py`) et le Monte-Carlo (`monte_carlo_cout.py`) acceptent les mêmes options de scénario.

**Placement par PLNE** (environ 3 à 6 min par commune avec `--limite-s 180` ; les communes se lancent en parallèle) :

```
.venv/bin/python analyse/placement_plne.py --config config/config.json \
  --out resultats/production/placement_v61 --communes ze --limite-s 180
.venv/bin/python analyse/couche_cout.py --config config/config.json --placement placement_v61 \
  --out resultats/production/cout_v61
```

L'option `--placement` remplace, commune par commune, le nombre de passerelles du pavage par celui du placement. Les communes de `cout.placement_plne.communes_exclues` gardent le pavage. La couche coût calcule aussi les réseaux mixtes (`cout.hybrides`) ; `--hybrides` dans la tornade et le Monte-Carlo compare « LoRa + secours cellulaire » à « cellulaire + secours LoRa ».

**Version finale (v6.2).** Placement en mélange de zones, environ 1 h pour les huit communes en parallèle :

```
for c in ouidah tori_bossito so_ava kpomasse abomey_calavi allada toffo ze; do
  .venv/bin/python analyse/placement_plne_v62.py --config config/config.json \
    --out resultats/production/placement_v62 --communes $c &
done
```

Coût central :

```
.venv/bin/python analyse/couche_cout.py --config config/config.json --placement placement_v62 \
  --out resultats/production/cout_v62
```

Autres options de la couche coût :
- `--melange placement_v62` : pavage en mélange de zones ;
- `--mat neuf|partage` : variante à 30 m, avec un config où `passerelle.hauteur_antenne_m` = 30 et `radio.correction_hauteur_db` = 4,44 ;
- `--population-variante` : totaux WorldPop 2021.

Version du mémoire : `analyse/convention_v63.py --config config/config.json --out resultats/production/final/central`, puis `analyse/figures_memoire.py`. Optimisation par le coût : `analyse/optimisation_cout.py --config config/config.json --out resultats/production/final/optimisation` (environ 40 min, 13 scénarios), puis `analyse/comparaison_commune.py`. Contrôle documentaire : `analyse/revue_openalex.py`. Tests du serveur : `prototype_tests/test_integration.py`, à lancer sur le serveur.

La tornade et le Monte-Carlo acceptent `--choix` (réseau choisi commune par commune) et `--hybrides`. Les figures finales se refont par `analyse/figures_v62.py --out <dossier>`.

**Paquets ajoutés à l'environnement virtuel :** rasterio, shapely, highspy.

**Mobilité avec le pont porté** :

```
.venv/bin/python orchestrateur/run_mobilite.py --config config/config.json --ns3-dir ~/ns-3.48 \
  --bin stopmnt-production --out resultats/production/mobilite_interieur_v6 --repetitions 5 --jobs 4 \
  --scenarios a_trajet c_debordement --fractions-interieur 0.5 0.7 0.9 1.0 --alertes-mobiles --duree-jours 3
```

Durée : environ 30 min.

**Piège connu.** Pour arrêter un calcul, ne jamais utiliser `pkill -f <motif>` depuis une commande qui contient elle-même ce motif : le shell qui lance la commande se tue lui-même. Prendre le numéro du processus avec `ps` et le tuer par son numéro.

**Ajouter une expérience.** Créer une entrée dans `config.json > experiences` avec `experience_de_base` (héritage) et les clés à changer (`balayage_...`, `zones`, `repetitions`, `duree_simulee_jours`), puis la lancer par `--exp`.

## 7. Comment est produit chaque CSV et chaque figure

| Sortie | Produite par | À partir de |
|---|---|---|
| `resultats_<exp>_<date>.csv` (une ligne par run), `noeuds_<exp>_<date>.csv` (une ligne par nœud), `ack_<exp>_<date>.csv` (percentiles) | `run_experiences.py` | sortie du modèle |
| `rayon_fiable_probit.csv` | `analyse/rayon_fiable.py --probit` | `noeuds_*` de la portée |
| `rayon_fiable_bandes.csv` | `analyse/rayon_fiable.py --bandes 20` | idem |
| `fig_portee.png` | `analyse/figure_portee_compacte.py` | bandes + probit + nœuds |
| `multi_passerelles_synthese_production.csv` | `analyse/analyse_multi_passerelles.py` | multi-passerelles |
| `robustesse_marge.csv`, `robustesse_panne.png` | `analyse/analyse_robustesse.py` | robustesse + synthèse multi |
| `capacite_production.csv` (croisements), `capacite_points_production.csv` (par palier), `capacite_*.png` | `analyse/analyse_capacite.py` | capacité (nœuds + ack) |
| `tampon_72h.csv`, `fig_tampon_72h.png` | `analyse/analyse_sfw_longue.py` | `run_sfw_longue.py` |
| `bilan_cellulaire.csv` | `analyse/bilan_cellulaire.py` | config seul |
| `portee_site_lora_4g.png`, `energie_ponts.png` | `analyse/figures_cellulaire.py` | bilan + rayons + énergie |
| `table_calibration.csv` | `analyse/table_calibration.py` | config + rayons |
| `cout_*.csv`, `cout_par_patient.png` | `analyse/couche_cout.py` | config + capacités + multi + robustesse |
| `tornade_cout.csv/png` | `analyse/tornade_cout.py` | relance la couche coût paramètre par paramètre |
| `monte_carlo_*.csv/png` | `analyse/monte_carlo_cout.py` | tirages simultanés |
| `controle_repetitions.csv` | `analyse/controle_repetitions.py` | tous les tableaux de points |
| `exigences_v6.csv`, `essais_alerte_sf12.csv` | `analyse/exigences_v6.py` | capacité, continuité, remontée, pavage |
| `rayon_interieur.png`, `exigences_pavage.png` | `analyse/figures_v6.py` | portée selon l'intérieur, `exigences_v6.csv` |
| `mobilite_interieur.csv` | `analyse/analyse_mobilite_interieur.py` | `run_mobilite.py --fractions-interieur ... --alertes-mobiles` |
| `couverture_arcep_communes.csv` | `analyse/couverture_arcep.py` | atlas ARCEP (API, réponses gardées) + bilan cellulaire |
| `placement_plne_<commune>.csv`, `population_communes_<commune>.csv`, `sites_*.csv`, `placement_*.png` | `analyse/placement_plne.py` | WorldPop 2021 (100 m, contraint) + contours ARCEP + synthèse multi-passerelles ; PLNE de couverture (scipy `milp`, HiGHS), glouton de secours, densification de capacité |
| `secours_lora.csv` | `analyse/secours_lora.py` | nœuds d'`exigences_pavage_v61` + couverture ARCEP |
| `placement_v62_<commune>.csv`, `couvert_arbore_<commune>.csv`, `sites_v62_*.csv` | `analyse/placement_plne_v62.py` | WorldPop + ESA WorldCover 10 m 2021 + contours ARCEP ; zone par maille, pavage comme départ, HiGHS (highspy), 30 min par commune |
| `alarme_deux_temps.csv`, `parade_ouverture.csv` | `analyse/analyse_v62.py` | expériences `alarme_deux_temps_v62`, `parade_ouverture_v62` |
| `choix_communes.csv` | `analyse/couche_cout.py` (avec `cout.hybrides`) | coût par patient par commune, choix, abonnement et densité de bascule |
| `fig_*_v62.png`, `repetitions_*.csv` | `analyse/figures_v62.py` | une ligne par répétition ; moyenne ± 1 écart-type ; police STIX |
| `composantes.csv` | `analyse/couche_cout.py --composantes` | postes hors connexion par commune (v6.3) |
| `cout_departement_v63.csv`, `cout_communes_v63.csv`, `choix_communes_v63.csv`, `seuils_convention_v63.csv`, `monte_carlo_resume_v63.csv`, `controles_v63.*`, `tirages_v63.csv`, `fig_carte_convention_v63.png`, `fig_cout_par_commune_v63.png` | `analyse/convention_v63.py` | `composantes.csv` (centre + 500 tirages v6.2 régénérés) + `cout.convention` |

**Sens des colonnes ajoutées en v6** dans les lignes `ACK;` de type `alerte_reseau`, `alerte_interieur` et `remontee` : voir les commentaires en tête de la section de sortie de `lorawan-cell-shadow.cc`, qui reprennent les colonnes de la ligne ACK avec un autre sens.

### Coût de connexion v6.3 (`analyse/convention_v63.py`)

**Commande** (environ 20 s, dont l'évaluation des 500 tirages) :

```
.venv/bin/python analyse/convention_v63.py --config config/config.json --out resultats/production/v63
```

**Entrée.**
- Pour chaque commune, la couche coût v6.2 (`couche_cout.py --composantes`) donne les postes hors connexion, sans rien changer à ses autres sorties :
  - patients et passerelles du placement v6.2 ;
  - part des patients au secours cellulaire (f) ;
  - part sans couverture intérieure (u) et passerelles du secours LoRa (g) ;
  - kits par an et passerelle par an hors remontée ;
  - serveur LoRaWAN et volume MQTT/TLS du pont.
- Le bloc `cout.convention` du config fournit p_Go, m, F_global, k, f_ligne, le forfait public et les réceptions par trame.

**Formule** (fonction `couts`, en € par an) :
- Prix de l'octet : pb = p_Go × (1 + m) / 2^30 / 655,957.
- Volumes :
  - pont : 12 × volume MQTT mensuel ;
  - passerelle : 1,52 Mo de maintien par jour, plus, par patient LoRa et par jour, 10 × 290 o × réceptions par trame + accusés × 550 o.
- LoRa sans convention = kits + secours au forfait public + passerelles × (hors remontée + forfait public).
- LoRa sous convention = kits + secours au volume + passerelles hors remontée + volume des passerelles ; lignes = n·f + passerelles.
- Cellulaire = ponts au volume + patients du secours en kit LoRa + g passerelles hors remontée + leur volume ; lignes = n·(1 − u) + g.
- Part par ligne : + 12 × f_ligne / 655,957 × lignes (fonction `avec_ligne`).
- F_global : k × F_global, payé une fois si une ligne au moins est dans la convention.
- Structure Kerlink : pas de remontée, passerelles hors lignes.

**Sortie.**
- `enumerer` parcourt les 256 affectations × 2 options. Elle rend le coût, l'affectation, l'option et le nombre de lignes. Ces sorties forment la vue A.
- `decomposer` donne le même optimum en forme fermée, pour la carte. Une assertion vérifie l'égalité avec `enumerer`.
- `vue_b` rend le coût par patient de chaque option, commune par commune. F_global y est réparti au prorata des lignes, les autres communes gardant leur choix optimal.

**Exemple chiffré : Allada, scénario bas, F_global = 0, k = 1.**
- Paramètres : p_Go = 1 228 FCFA, m = 0,15, f_ligne = 55 FCFA, forfait public 2 500 FCFA, 1,5 réception par trame.
- Entrées : 2 550 patients ; 84 passerelles ; f = 0,0235 ; u = 0, donc g = 0 ; pont 0,98 Mo par mois.
- Cellulaire :
  - volume : 2 550 × 12 × 0,98 Mo = 28,0 Go ; 28,0 × 1 228 × 1,15 = 39 600 FCFA, soit 60 € ;
  - lignes : 2 550 × 12 × 55 / 655,957 = 2 566 € ;
  - kits : 2 550 × 24,18 = 61 677 € ;
  - total 61 737 € (sans les lignes), soit 25,27 € par patient et par an, serveur compris.
- LoRa sous convention :
  - kits, passerelles (84 × 291,7 €) et volume des passerelles (52 Go) : 75 736 € ;
  - 144 lignes, soit 145 € ;
  - total 29,80 € par patient.
- LoRa sans convention : 32,29 € par patient.
- Gagnant : le cellulaire.
- Avec F_global = 10 M FCFA : la part d'Allada (28 % des lignes de la convention) ajoute 1,65 € par patient au cellulaire.

## 8. Limites connues du modèle

**Ajouts v6.2.**
- La part arborée vient d'ESA WorldCover (classe « arbre » dès 10 % de couvert), assimilée au rural arboré à densité 0,35, avec un seuil de maille à 50 %.
- WorldPop contraint manque les villages lacustres de Sô-Ava : cette commune garde le pavage.
- Le placement PLNE s'arrête à 30 min, avec un écart à l'optimum de 0 à 8 %.
- La correction de hauteur 3GPP RMa est appliquée au bilan, pas simulée.
- L'alarme en deux temps du pont est émulée, et dépend du récapitulatif, qui passe par la même voie descendante.

**Propagation.**
- Log-distance + ombrage log-normal par nœud, sans corrélation spatiale fine ni modèle de terrain (UIT-R P.1812 en perspective).
- La calibration vient de campagnes publiées hors du Bénin (Bonn, Oulu).
- Sous 1 km, la loi est extrapolée jusqu'à 100 m (v6) : hors du domaine mesuré.

**Intérieur.**
- Médiane P.2109 appliquée comme un décalage fixe, pas comme une variable aléatoire.
- Le calendrier dedans/dehors est une hypothèse de forme, une seule plage dehors par jour.

**Sensibilités.**
- Passerelle : valeurs SX1302 pour des paquets de 12 octets, alors que nos trames sont plus longues ; d'où le décalage de −3 à 0 dB en sensibilité.
- Nœud : bornes SX1262 (SF7 et SF12), SF intermédiaires du module.
- Le module choisit le SF du nœud d'après la sensibilité du nœud, pas celle de la passerelle (marge de 3 à 4 dB).

**Énergie.** Modèle SX1272 du module, radio seule ; microcontrôleur et Bluetooth non comptés.

**Remontée.**
- Latence log-normale + pics + retransmission TCP : un modèle de forme, calé sur une seule latence moyenne mesurée (nPerf).
- Pas de coupure longue de la remontée (perte du lien 4G de la passerelle pendant des heures).

**Récapitulatif quotidien.**
- Émulé par une montée confirmée à une seule transmission.
- Les 6 octets de la descendante ne sont pas comptés dans le temps d'antenne.
- Le serveur ne garde pas d'état propre : l'échéance est suivie côté pont.

**Store-and-forward.** Logique applicative simplifiée ; la MAC du module n'a pas de file (une trame remplace celle en cours).

**Cellulaire.**
- Pas de simulation ns-3 : le module LTE sature sa voie montante 6 à 20 dB avant la référence 3GPP, d'où la décision O de passer par le bilan de liaison.
- Rayons par site sans diversité ni réseau réel d'opérateur.

**Coût.** Prix catalogue, pas de devis ; populations de 2013 ; affectation des communes aux zones proposée par l'auteur.
