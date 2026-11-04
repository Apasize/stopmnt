#!/usr/bin/env bash
# Complement v6.2 (2026-10-29), derniere campagne avant gel.
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
PY="$RACINE/.venv/bin/python"
RUN="$PY $RACINE/orchestrateur/run_experiences.py --config $RACINE/config/config.json --ns3-dir $HOME/ns-3.48 --shadow-bin stopmnt-production --jobs 6 --timeout 21600"
P="$RACINE/resultats/production"
mkdir -p "$P/v62"
J="$P/v62/journal_campagne_v62.txt"
for e in alarme_deux_temps_v62 parade_ouverture_v62; do
  echo "=== $e $(date)" >> "$J"
  $RUN --exp $e --out "$P/$e" >> "$J" 2>&1
done
echo FIN >> "$J"
