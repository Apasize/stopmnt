#!/usr/bin/env bash
# Simulation longue de 7 jours aux points de capacite retenus (config :
# experiences.capacite_longue.points_retenus), une repetition par zone.
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$RACINE/resultats/production/capacite_longue_7j"
mkdir -p "$OUT"
for mode in tout_confirme_rx2 mixte_rx2; do
  n=$("$RACINE/.venv/bin/python" -c "import json;print(json.load(open('$RACINE/config/config.json'))['experiences']['capacite_longue']['points_retenus']['$mode'])")
  "$RACINE/.venv/bin/python" "$RACINE/orchestrateur/run_experiences.py" --config "$RACINE/config/config.json" \
    --ns3-dir "$HOME/ns-3.48" --shadow-bin stopmnt-production --exp capacite_modes --modes $mode \
    --nb-noeuds $n --repetitions 1 --duree-jours 7 --jobs 10 --timeout 7200 --out "$OUT" >> "$OUT/journal.txt" 2>&1
done
echo "FIN" >> "$OUT/journal.txt"
