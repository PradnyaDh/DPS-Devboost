#!/usr/bin/env bash
# Regenerate web/data/snapshot.json from BigQuery.
# Reads the DevBoost table in fulfillment-dwh-production, billing the query to
# a project where you can create jobs (BILLING_PROJECT, default dhub-data-commune).
set -euo pipefail
cd "$(dirname "$0")/.."
BILLING_PROJECT="${BILLING_PROJECT:-dhub-data-commune}"
OUT=web/data/snapshot.json

echo "Querying BigQuery (billing: $BILLING_PROJECT)..."
bq query --use_legacy_sql=false --project_id="$BILLING_PROJECT" \
         --format=prettyjson --max_rows=100000 < sql/snapshot.sql > "$OUT.raw"

python3 scripts/build_snapshot.py "$OUT.raw" "$OUT"
rm -f "$OUT.raw"
echo "Wrote $OUT ($(du -h "$OUT" | cut -f1))"
