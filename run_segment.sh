#!/usr/bin/env bash
# One bounded segment of the 2025-01-01..2026-07-31 full-period panel.
# FETCH_START includes 7 causal warm-up days before the first scored day.
set -euo pipefail
FETCH_START=$1; END=$2; TAG=$3
export PYTHONPATH=src
D=/tmp/bess-$TAG; mkdir -p $D/ercot $D/caiso results/seg
printf 'tag=%s fetch_start=%s end=%s started=%s\n' "$TAG" "$FETCH_START" "$END" "$(date -u +%FT%TZ)" | tee results/seg/$TAG.meta
python src/fetch_ercot.py --start $FETCH_START --end $END --out $D/ercot --sleep 0.05 > results/seg/$TAG.fetch_ercot.log 2>&1
for pass in 1 2 3 4 5 6; do
  if python src/fetch_caiso.py --start $FETCH_START --end $END --out $D/caiso --workers 2 > results/seg/$TAG.fetch_caiso.pass$pass.log 2>&1; then echo "caiso pass $pass complete"; break; fi
  echo "caiso pass $pass: $(tail -1 results/seg/$TAG.fetch_caiso.pass$pass.log)"; sleep 60
done
echo "fetched $(date -u +%FT%TZ) ercot=$(ls $D/ercot/*.csv | wc -l) caiso=$(ls $D/caiso/*.csv | wc -l)" | tee -a results/seg/$TAG.meta
python src/matched_month.py --ercot $D/ercot --caiso $D/caiso --out results/seg/$TAG.panel.json > results/seg/$TAG.matched.log 2>&1
tail -25 results/seg/$TAG.matched.log
python src/verify_matched.py --result results/seg/$TAG.panel.json --ercot $D/ercot --caiso $D/caiso --out results/seg/$TAG.verify.json > results/seg/$TAG.verify.log 2>&1 || echo "verify rc=$?"
tail -5 results/seg/$TAG.verify.log
python - "$TAG" <<'PY'
import json,sys
t=sys.argv[1]; p=json.load(open(f'results/seg/{t}.panel.json'))
p.pop('traces',None); json.dump(p,open(f'results/seg/{t}.summary.json','w'),indent=1)
PY
gzip -9 -f results/seg/$TAG.panel.json
tar czf results/seg/$TAG.inputs.tgz -C $D ercot caiso
printf 'finished=%s\n' "$(date -u +%FT%TZ)" | tee -a results/seg/$TAG.meta
