#!/usr/bin/env bash
# Complement v6.1 (2026-10-29).
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
PY="$RACINE/.venv/bin/python"
RUN="$PY $RACINE/orchestrateur/run_experiences.py --config $RACINE/config/config.json --ns3-dir $HOME/ns-3.48 --shadow-bin stopmnt-production --jobs 10 --timeout 21600"
P="$RACINE/resultats/production"
mkdir -p "$P/v61"
J="$P/v61/journal_campagne_v61.txt"
for e in portee_gain_v61 exigences_pavage_v61; do
  echo "=== $e $(date)" >> "$J"
  $RUN --exp $e --out "$P/$e" >> "$J" 2>&1
done
echo FIN >> "$J"
