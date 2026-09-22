#!/usr/bin/env bash
# Regenerate the generated data in web/data/ from BigQuery:
#   snapshot.json        - the scores the explorer reads
#   repo-map.*           - which repos each team owns, and their Codacy issue counts
#   security-issues.json - the individual open issues, fetched on demand by the UI
# Reads tables in fulfillment-dwh-production, billing the queries to a project
# where you can create jobs (BILLING_PROJECT, default dhub-data-commune).
#
# Pass --snapshot-only to skip the repo map (it is slower and the explorer does
# not need it to render).
set -euo pipefail
cd "$(dirname "$0")/.."
BILLING_PROJECT="${BILLING_PROJECT:-dhub-data-commune}"
OUT=data/snapshot.json

echo "Querying BigQuery (billing: $BILLING_PROJECT)..."
bq query --use_legacy_sql=false --project_id="$BILLING_PROJECT" \
         --format=prettyjson --max_rows=100000 < sql/snapshot.sql > "$OUT.raw"

python3 scripts/build_snapshot.py "$OUT.raw" "$OUT"
rm -f "$OUT.raw"
echo "Wrote $OUT ($(du -h "$OUT" | cut -f1))"

if [[ "${1:-}" == "--snapshot-only" ]]; then exit 0; fi

# Team -> repo mapping. Runs second because it reads the snapshot above for the
# hierarchy: repos attach to squads, and every level's set is the union of its
# children's. A failure here leaves the snapshot intact — the explorer renders
# without the map, so this must not take the whole refresh down with it.
echo "Querying repo map (billing: $BILLING_PROJECT)..."
# --quiet: bq otherwise writes progress lines to stdout and corrupts the JSON.
if bq --quiet query --use_legacy_sql=false --project_id="$BILLING_PROJECT" \
      --format=prettyjson --max_rows=10000 < sql/repo_map.sql > web/data/repo-map.raw.json; then
  python3 scripts/build_repo_map.py web/data/repo-map.raw.json "$OUT" web/data/repo-map
  rm -f web/data/repo-map.raw.json
else
  echo "WARNING: repo map query failed - snapshot is still current" >&2
  rm -f web/data/repo-map.raw.json
fi

# Individual security issues, for the list the UI fetches when someone expands it.
# ~15MB raw, packed to ~2MB (790KB over the wire) by interning repeated strings.
# Same containment as above: a failure leaves the rest of web/data/ usable.
echo "Querying security issues (billing: $BILLING_PROJECT)..."
if bq --quiet query --use_legacy_sql=false --project_id="$BILLING_PROJECT" \
      --format=prettyjson --max_rows=200000 < sql/security_issues.sql > web/data/security.raw.json; then
  python3 scripts/build_security_issues.py web/data/security.raw.json "$OUT" \
          web/data/security-issues.json
  rm -f web/data/security.raw.json
else
  echo "WARNING: security issue query failed - the issue list will be stale" >&2
  rm -f web/data/security.raw.json
fi
