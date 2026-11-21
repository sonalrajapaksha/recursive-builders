#!/bin/bash
# usage: tools/gym/run_arms.sh OUTDIR MATCHES_PER_CHUNK CHUNKS  (arms listed below); same seeds for every arm
OUT=${1:-/tmp/ext/gymres}; PER=${2:-13}; CH=${3:-8}
export GYM_TICK_TIMEOUT=${GYM_TICK_TIMEOUT:-8}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
ARMS=(
 'default|{}'
 'cover|{"RetreatHP":0.5,"RecoverHP":0.9}'
 'laser130|{"LaserRange":130}'
 'odds|{"Odds":0.6,"OddsFlee":0.3}'
)
for a in "${ARMS[@]}"; do
  name=${a%%|*}; params=${a#*|}
  for c in $(seq 0 $((CH-1))); do
    python3 -I "$ROOT/tools/gym/gym.py" --arm "$name" --params "$params" --matches $PER --start $((c*PER)) --out "$OUT/$name.$c.jsonl" >/dev/null 2>"$OUT/$name.$c.log" &
  done
  wait
  echo "done $name $(date +%T)"
done
