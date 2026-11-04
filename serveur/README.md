# Serveur du prototype STOP-MNT

Neuf services sous Docker Compose : Nginx, FastAPI, PostgreSQL, Redis, Mosquitto, InfluxDB, un service de traitement MQTT (`worker`), Grafana et un service de sauvegarde.

## Démarrer

1. Copier `.env.example` en `.env` et renseigner toutes les valeurs.
2. Générer l'autorité de certification et les certificats du serveur (`certs/regenerate.sh <IP du serveur>`), puis les placer dans `nginx/certs/` et `mosquitto/certs/`.
3. `docker compose up -d`

## Tests

`tests/test_integration.py` exécute les 30 tests d'intégration décrits en annexe du mémoire, sur la machine du serveur, depuis la racine de ce dossier :

```bash
python3 tests/test_integration.py
```

Les résultats de l'exécution du 4 novembre 2026 sont dans `tests/resultats_tests.json`, et ceux de la relance du même jour dans `tests/resultats_tests_relance.json`.
