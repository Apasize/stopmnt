#!/usr/bin/env bash
# Campagnes des consignes v4 (2026-10-27), lancees a la suite.
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
PY="$RACINE/.venv/bin/python"
RUN="$PY $RACINE/orchestrateur/run_experiences.py --config $RACINE/config/config.json --ns3-dir $HOME/ns-3.48 --shadow-bin stopmnt-production --jobs 11 --timeout 14400"
P="$RACINE/resultats/production"
mkdir -p "$P/v4"
J="$P/v4/journal_campagne_v4.txt"
$RUN --exp robustesse_panne --out "$P/robustesse_panne" >> "$J" 2>&1
$RUN --exp reglementaire_rx2_14dbm --out "$P/reglementaire_rx2_14dbm" >> "$J" 2>&1
$RUN --exp delai_rx1_5s --out "$P/delai_rx1_5s" >> "$J" 2>&1
for mode in tout_confirme_rx2 mixte_rx2; do
  n=$($PY -c "import json;print(json.load(open('$RACINE/config/config.json'))['experiences']['capacite_longue_v4']['points_retenus']['$mode'])")
  $RUN --exp capacite_longue_v4 --modes $mode --nb-noeuds $n --out "$P/capacite_longue_v4" >> "$J" 2>&1
done
echo FIN >> "$J"
