#!/usr/bin/env bash
# Relance a 8 dBi (2026-11-04) des experiences du chapitre 3 simulees a 5 dBi.
# Le gain vient de config.json (passerelle.gain_antenne_dbi = 8.0).
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
PY="$RACINE/.venv/bin/python"
CFG="$RACINE/config/config.json"
RUN="$PY $RACINE/orchestrateur/run_experiences.py --config $CFG --ns3-dir $HOME/ns-3.48 --shadow-bin stopmnt-production --jobs 11 --timeout 21600"
P="$RACINE/resultats/production/final/8dbi"
mkdir -p "$P"
J="$P/journal_campagne_8dbi.txt"
for e in multi_passerelles_v6 robustesse_v6 robustesse_ext_v6 exigences_pavage_v61; do
  echo "=== $e $(date)" >> "$J"
  $RUN --exp $e --out "$P/$e" >> "$J" 2>&1
  echo "--- fin $e code $? $(date)" >> "$J"
done
echo "=== mobilite_interieur $(date)" >> "$J"
$PY "$RACINE/orchestrateur/run_mobilite.py" --config "$CFG" --ns3-dir "$HOME/ns-3.48" --bin stopmnt-production \
  --out "$P/mobilite_interieur" --repetitions 5 --jobs 11 --scenarios a_trajet c_debordement \
  --fractions-interieur 0.5 0.7 0.9 1.0 --alertes-mobiles --duree-jours 3 >> "$J" 2>&1
echo "--- fin mobilite_interieur code $? $(date)" >> "$J"
echo "=== rayon_diversite $(date)" >> "$J"
$PY "$RACINE/analyse/optimisation_cout.py" --config "$CFG" --out "$P/optimisation_rayon_diversite" --seul rayon_diversite --jobs 1 >> "$J" 2>&1
echo "--- fin rayon_diversite code $? $(date)" >> "$J"
echo "=== remontee_v6 $(date)" >> "$J"
$RUN --exp remontee_v6 --out "$P/remontee_v6" >> "$J" 2>&1
echo "--- fin remontee_v6 code $? $(date)" >> "$J"
echo FIN >> "$J"
