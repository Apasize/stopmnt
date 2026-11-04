#!/bin/bash
# Usage : ./regenerate.sh <IP du serveur>
# Régénère tous les certificats avec la nouvelle IP
SERVER_IP=${1:?"Usage : ./regenerate.sh <IP du serveur>"}
echo "Régénération des certificats pour IP=$SERVER_IP"
echo "Modifier les fichiers .ext avec la nouvelle IP et relancer openssl x509..."
echo "Penser à redémarrer les conteneurs après : docker compose restart mosquitto nginx"
