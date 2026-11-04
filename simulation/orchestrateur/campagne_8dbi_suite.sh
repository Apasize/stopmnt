#!/usr/bin/env bash
# Suite de campagne_8dbi.sh : patients fixes a l'interieur (continuite_interieur_v6) a 8 dBi.
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
P="$RACINE/resultats/production/final/8dbi"
J="$P/journal_campagne_8dbi.txt"
until grep -q "^FIN" "$J"; do sleep 30; done
echo "=== continuite_interieur_v6 $(date)" >> "$J"
"$RACINE/.venv/bin/python" "$RACINE/orchestrateur/run_experiences.py" --config "$RACINE/config/config.json" --ns3-dir "$HOME/ns-3.48" \
  --shadow-bin stopmnt-production --jobs 11 --timeout 21600 --exp continuite_interieur_v6 --out "$P/continuite_interieur_v6" >> "$J" 2>&1
echo "--- fin continuite_interieur_v6 code $? $(date)" >> "$J"
echo FIN_SUITE >> "$J"
