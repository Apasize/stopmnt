# STOP-MNT : architecture IoMT pour la collecte des données de prévention des MNT

Code source associé au mémoire de master de Phoris Andy AGBOZOGNIGBE, Institut de Formation et de Recherche en Informatique (IFRI), Université d'Abomey-Calavi, 2026 : *Conception d'une architecture IoMT pour la collecte des données utiles à la prévention des MNT en environnement à ressources limitées : application au projet STOP-MNT*. Encadrement : Dr Lionel METONGNON et Dr Ratheil HOUNDJI.

| Dossier | Contenu | Chapitre du mémoire |
|---|---|---|
| `simulation/` | Simulation LoRaWAN sous ns-3.48, bilans cellulaires, modèle de coût, optimisation du placement des passerelles | 2 et 3 |
| `serveur/` | Centre du prototype : FastAPI, PostgreSQL, InfluxDB, Redis, Mosquitto, Nginx, Grafana, sauvegarde, sous Docker Compose ; tests d'intégration | 4 |
| `application/` | Application mobile Flutter pour Android : acquisition BLE, lecture de Health Connect, file d'attente hors connexion | 4 |

Chaque dossier a son propre README. Aucun secret n'est versionné : les mots de passe, jetons, clés privées et certificats sont à générer localement (voir `serveur/.env.example` et `serveur/certs/regenerate.sh`).
