# log-devboost-explorer

Drill-down dashboard for DevBoost scores across Logistics. Select any team from the
platform root down to a squad, see its scorecard, compare its sub-teams side by side.

- Repo: `deliveryhero/log-devboost-explorer` (internal). Direct pushes to `main` work.
- Live: https://legendary-robot-l67woe7.pages.github.io/ — private Pages, requires DH
  GitHub org login. The obfuscated hostname is GitHub-generated and would change if the
  site were ever made public.

An earlier `deliveryhero/devboost-explorer` was abandoned: it inherited the org's
`global-branch-protection` ruleset, which required an approving review and had zero
bypass actors, so nothing could ever be merged. Creating a repo in the DH org does not
make you its admin. Before assuming a new repo is writable, check
`gh api repos/OWNER/REPO/rules/branches/main`.
- Deploy: `.github/workflows/pages.yml` publishes `web/` on push to `main`.

## Layout

| Path | Role |
|---|---|
| `sql/snapshot.sql` | One query over the DevBoost table, all levels, from 2025-03 |
| `scripts/build_snapshot.py` | Reshapes rows into a tree keyed by `group_id` |
| `scripts/refresh.sh` | Runs both, writes `web/data/snapshot.json` |
| `web/index.html` | Self-contained explorer, no dependencies |

Data and presentation are deliberately split: the UI only reads `data/snapshot.json`
and knows nothing about BigQuery, so pointing it at another source (e.g. folding into
the adoption tracker) is a data swap, not a rewrite.

Refreshing is manual — `./scripts/refresh.sh`, then commit and push the snapshot.
A scheduled Action would need BigQuery credentials in the repo.

## The data source

`fulfillment-dwh-production.curated_data_shared_psf.devboost_overall_monthly_score`

The table named in the [Confluence methodology page](https://deliveryhero.atlassian.net/wiki/spaces/techfoundations/pages/231211183/DevBoost+DevBoost+score)
(`dh-gsre-jira-metrics.dev_productivity_metrics.overall_monthly_score`) is **stale** and
unreadable. The methodology itself — weights, min-max normalization — is accurate.

**Querying:** you can read the table but cannot create jobs in its host project, so bill
the query elsewhere. `scripts/refresh.sh` uses `BILLING_PROJECT`, default
`dhub-data-commune`. Gotchas that cost time:

- Pipe SQL via stdin. `bq query "$(cat f.sql)"` crashes parsing leading `--` comments.
- `bq ls` returns nothing useful against these projects.
- A query against a *nonexistent* table returns the same `Access Denied` as a real
  permissions failure. Use `bq show` to tell "missing" from "forbidden".

**Never roll up.** Every hierarchy level — PLATFORM / PRODUCT-LINE / TRIBE / DOMAIN /
SQUAD — is published as its own row, tagged in `hierarchy_full_display_name` (e.g.
`[TRIBE] Logistics / Rider / Deliveries (log-deliveries)`). Each is recomputed upstream
from raw events, so a tribe's median PR lifetime is the true median across all its PRs —
something you cannot reconstruct from squad medians. Read the parent row instead.
Note `[PRODUCT-LINE]` contains a hyphen, which defeats a naive `^\[([A-Z]+)\]` regex.

**`overall_score` is a 0-1 fraction**, not a percentage. Verified it reproduces exactly
from the normalized columns times the documented weights across all 3,788 YTD rows,
max difference 0.0 — so trust the column and don't recompute.

**Identity is `group_id`**, which is stable across reorgs; the display path changes, so
labels come from each group's most recent path. Where one path maps to several ids (a
rename where the old id stopped reporting), the longest-lived id wins. Data starts
2025-03 and the hierarchy only settled ~2025-06; one pre-reorg orphan is dropped.

**The current month is partial** and never the default, but it is selectable and
visible — marked "in progress" on the hero, in the trend caption and on the sub-teams
heading, and drawn as a dashed segment with a hollow point on the chart. Its
cumulative metrics (PRs merged, deployments) are part-way through and read low, while
medians and NPS are already meaningful, so the composite is biased downward rather
than merely noisy. It is selectable because the official DevBoost report defaults to
a range including it, so reconciling the two requires being able to view it.

## Linking out to the official DevBoost report

The provenance panel deep-links each team into the Looker Studio report. Its filter
values are `include<U+E000>0<U+E000>IN<U+E000><value>`, double-URL-encoded, with every
filter in one JSON `params` object:

| Param | Filter |
|---|---|
| `df249` | team — matches `hierarchy_full_display_name` **exactly** |
| `df53`, `df55`, `df145` | contributor scope |
| `df207` | Human / HeroGen |

`df105`/`df117` take a quarter (`2026'Q1`) but the report ignores them — it resets
them in the URL and renders whatever its own date control says — so the generated
link does not pass them.

`df249` is why the snapshot carries `raw_hierarchy` untouched as each node's `raw`:
the display path shown in the UI is stripped of its `[LEVEL]` prefix and `(slug)`
suffix, but the filter needs the original string. Report id, page id and the `s=`
source were taken from a working link; verified by regenerating that link and
comparing decoded params field by field.

Verified end to end by loading a generated squad link in a browser: the report's
filter bar showed `[SQUAD] Logistics / Rider / Deliveries / Rider Fundamentals /
Rider Experience (rider-experience)` and every metric matched this repo's snapshot
for that squad.

One difference to expect: the report opens on its own date range, which includes the
current partial month, while this explorer defaults to the last complete one. Select
the in-progress month here to reconcile — verified for Customer Product Line, where
all eleven metrics and the score match the report exactly for 2026-09.

## Known upstream bugs, surfaced not fixed

**Code coverage is scored exactly 100x low.** Raw `code_coverage` is a fraction
(0.82 = 82%) but normalization divides by max=100, so credit lands at ~0.008 instead of
~0.82. Verified: `raw / normalized` is exactly 100.000000 on all 4,916 real measurements
across all 19 months and all 11 top-level orgs, zero exceptions; coverage's normalized
ceiling is 0.01 while every other metric reaches 1.0.

The loss is **not** uniform — it equals each team's actual coverage, so teams at 80-100%
lose ~4.34 of 5 points while teams under 20% lose ~0.38. **Rankings therefore do move**:
re-ranking the 198 squads with a coverage measurement reorders 170 of them, largest move
18 places. (An earlier note here claimed rankings were unaffected. That was wrong — it
assumed a uniform deduction without checking.)

**The official Looker Studio report inherits the defect.** It displays raw coverage
correctly as a percentage, but its score field reads `overall_score` from this same
table, so it shows the same wrong number: for `log-deliveries` 2026-09 the report shows
60%, matching the broken 60.50 rather than the corrected 64.58. There is no consumer
holding a correct value. (An earlier note here claimed the report used the correct
scale; that was inferred from a Claude-generated summary of an export, not from the
report itself.)

The snapshot carries a corrected `n_code_coverage_fixed` alongside the official value,
and the UI shows the real coverage bar with a warning. Full evidence write-up:
`docs/coverage-scale-defect.html`.

**Missing metrics impute to 0.5**, silently scoring a team 50% on that metric and
looking identical to a real middling score. Flagged per row as `has_imputed_metric`.

Neither has been raised with Tech Foundations, who own the methodology. That's
deliberate and Brad's call to make.

**Survey metrics are genuinely per-squad.** `dev_satisf_nps` and `focus_nps` are 25% of
the composite and quarterly, but they are *not* inherited from the parent org — every
squad carries a distinct value, so squad-level comparison is valid across the full 100
points. Worth knowing because the opposite is the natural assumption.

`change_failure_rate` is in the table but excluded from the score upstream due to low
adoption. Carried through the snapshot, unused by the UI.

## Pending: custom domain

[dh-cloudflare-dns-tf#4103](https://github.com/deliveryhero/dh-cloudflare-dns-tf/pull/4103)
adds a CNAME for `logistics-devboost.deliveryhero.net` -> `deliveryhero.github.io`,
applied by #gdp-support after review. Once DNS resolves, **in this order**:

1. `echo logistics-devboost.deliveryhero.net > CNAME`, commit, PR, merge
2. Settings -> Pages -> Custom domain, then enforce HTTPS

Order matters: Pages stops serving the generated `pages.github.io` hostname the moment a
custom domain is configured, so step 1 first breaks the working URL until DNS is live.
Precedent for private Pages on a DH domain: `promptdelivery.deliveryhero.net`.
