#!/usr/bin/env bash
# Campagnes du retour de l'auteur sur la v4 (2026-10-28), lancees a la suite.
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
PY="$RACINE/.venv/bin/python"
RUN="$PY $RACINE/orchestrateur/run_experiences.py --config $RACINE/config/config.json --ns3-dir $HOME/ns-3.48 --shadow-bin stopmnt-production --jobs 11 --timeout 14400"
P="$RACINE/resultats/production"
mkdir -p "$P/v5"
J="$P/v5/journal_campagne_v5.txt"
$RUN --exp portee_v5 --out "$P/portee_v5" >> "$J" 2>&1
$RUN --exp multi_passerelles_v5 --out "$P/multi_passerelles_v5" >> "$J" 2>&1
$RUN --exp robustesse_panne_v5 --out "$P/robustesse_panne_v5" >> "$J" 2>&1
$RUN --exp capacite_rx2_14dbm_descendante --out "$P/capacite_rx2_14dbm_descendante" >> "$J" 2>&1
$PY $RACINE/orchestrateur/run_sfw_longue.py --config $RACINE/config/config.json --ns3-dir $HOME/ns-3.48 --jobs 11 --out "$P/sfw_longue" >> "$J" 2>&1
$RUN --exp capacite_v5 --out "$P/capacite_v5" >> "$J" 2>&1
echo FIN >> "$J"
