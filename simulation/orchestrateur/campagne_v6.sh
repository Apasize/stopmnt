#!/usr/bin/env bash
# Campagnes des consignes v6 (2026-10-28), lancees a la suite. Les plus
# courtes d'abord ; la capacite (la plus longue) ensuite.
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
PY="$RACINE/.venv/bin/python"
RUN="$PY $RACINE/orchestrateur/run_experiences.py --config $RACINE/config/config.json --ns3-dir $HOME/ns-3.48 --shadow-bin stopmnt-production --jobs 11 --timeout 21600"
P="$RACINE/resultats/production"
mkdir -p "$P/v6"
J="$P/v6/journal_campagne_v6.txt"
for e in portee_v6 portee_interieur_v6 portee_sensibilite_v6 multi_passerelles_v6 robustesse_v6 capacite_rx2_14dbm_v6 continuite_interieur_v6 capacite_v6 capacite_recap_v6 remontee_v6 alertes_rares_v6; do
  echo "=== $e $(date)" >> "$J"
  $RUN --exp $e --out "$P/$e" >> "$J" 2>&1
done
echo FIN >> "$J"
