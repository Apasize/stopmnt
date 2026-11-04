#!/usr/bin/env bash
# Suite de la production (2026-10-27) : attend la fin de l'etape sensibilite de
# production.sh, arrete la chaine avant la capacite par fraction intensive
# (deja validee a 10 repetitions), puis lance la capacite en cinq modes avec
# l'antenne de 5 dBi (resultats/production/capacite_modes_5dBi).
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
J="$RACINE/resultats/production/journal.txt"
until grep -q "fin sensibilite_propagation" "$J"; do sleep 30; done
pgrep -f "orchestrateur/production.sh" | xargs -r kill
sleep 1
pgrep -f "exp capacite --jobs" | xargs -r kill
sleep 2
echo "=== $(date '+%F %T') chaine arretee avant la capacite par fraction intensive (deja validee)" >> "$J"
echo "=== $(date '+%F %T') debut capacite_modes_5dBi" >> "$J"
"$RACINE/.venv/bin/python" "$RACINE/orchestrateur/run_experiences.py" --config "$RACINE/config/config.json" \
  --ns3-dir "$HOME/ns-3.48" --shadow-bin stopmnt-production --exp capacite_modes --jobs 10 --timeout 7200 \
  --reprendre --out "$RACINE/resultats/production/capacite_modes_5dBi" >> "$J" 2>&1
echo "=== $(date '+%F %T') fin capacite_modes_5dBi (code $?)" >> "$J"
