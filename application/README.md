# Application mobile STOP-MNT

Application Flutter pour Android. Elle acquiert des mesures par BLE (services normalisés de fréquence cardiaque, de tension et d'oxymétrie), lit les données autorisées dans Health Connect, les transmet au serveur en HTTPS avec un jeton JWT, et les garde dans une file locale chiffrée en cas de coupure. Chaque mesure porte un identifiant généré sur le téléphone, qui permet au serveur de refuser les doublons.

## Construire

```bash
flutter pub get
flutter build apk --dart-define=API_BASE_URL=https://<adresse du serveur>/api/v1
```

L'autorité de certification du serveur (`assets/certs/stopmnt_ca.crt`) doit correspondre à celle générée pour le serveur, et l'adresse du serveur doit être déclarée dans `android/app/src/main/res/xml/network_security_config.xml`. Le fichier Firebase `android/app/google-services.json` n'est pas versionné ; il est à créer pour son propre projet Firebase.

La version de démonstration génère des données synthétiques en mémoire et fonctionne sans serveur.
