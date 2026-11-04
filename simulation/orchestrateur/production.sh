#!/usr/bin/env bash
# Chaine de production a 20 repetitions (decision M), dans l'ordre d'utilite
# pour le departage : portee, capacite en trois modes de confirmation (experience
# centrale), multi-passerelles, mobilite, sensibilite, capacite par fraction
# intensive. Chaque etape tourne ses runs en parallele (--jobs) ; une etape en
# echec n'arrete pas les suivantes. Journal : resultats/production/journal.txt
#
# Usage : bash orchestrateur/production.sh [jobs]
set -u
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
PY="$RACINE/.venv/bin/python"
NS3="$HOME/ns-3.48"
BIN="stopmnt-production"
JOBS="${1:-9}"
OUT="$RACINE/resultats/production"
mkdir -p "$OUT"
J="$OUT/journal.txt"

etape () {
  local nom="$1"; shift
  echo "=== $(date '+%F %T') debut $nom" >> "$J"
  "$@" >> "$J" 2>&1
  echo "=== $(date '+%F %T') fin $nom (code $?)" >> "$J"
}

run_exp () {
  etape "$1" "$PY" "$RACINE/orchestrateur/run_experiences.py" --config "$RACINE/config/config.json" \
    --ns3-dir "$NS3" --shadow-bin "$BIN" --exp "$1" --jobs "$JOBS" --timeout 7200 --reprendre --out "$OUT/$1"
}

run_exp capacite_modes
run_exp multi_passerelles
etape mobilite "$PY" "$RACINE/orchestrateur/run_mobilite.py" --config "$RACINE/config/config.json" \
  --ns3-dir "$NS3" --bin "$BIN" --out "$OUT/mobilite" --jobs "$JOBS"
run_exp sensibilite_propagation
run_exp capacite
echo "=== $(date '+%F %T') PRODUCTION TERMINEE" >> "$J"
