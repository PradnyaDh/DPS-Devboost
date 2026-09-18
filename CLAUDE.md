# log-devboost-explorer

Drill-down dashboard for DevBoost scores across Logistics. Select any team from the
platform root down to a squad, see its scorecard, compare its sub-teams side by side.

- Repo: `deliveryhero/log-devboost-explorer` (internal). Direct pushes to `main` work.
- Live: https://logistics-devboost.deliveryhero.net — private Pages, requires DH GitHub
  org login. Anonymous requests get GitHub's login wall, not the data.

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

## Engineer counts are recovered, not published

DevBoost divides by headcount (Workday P&T via DevHub) but never publishes the number.
It is recoverable because it is the *denominator* of two metrics that arrive as exact
rationals: `num_bugs_per_engineer` = bugs/H and `num_prs_merged_per_engineer` =
prs/(H x working_days). Reading those back with `Fraction(...).limit_denominator()`
yields divisors of H.

**A single month is never enough.** Python recovers fractions in lowest terms, so when
the numerator shares a factor with H the denominator collapses — the platform row yields
155 and 158 against a true 317, exact halves. Bugs alone degenerates to 1 for ~16% of
rows. PRs carry far more information because the working-days factor makes the
denominator large; only 1 of 66 rows collapses fully.

`resolve_headcount()` therefore takes the **max over a trailing 6 months**, discards
candidates below 75% of it as collapsed, and grades confidence on how many months
survive that filter. Window length matters: judged over all 19 months only 15 of 63
nodes look stable, over a trailing 6 it is 41 — the difference is real hiring, not error.

Two independent checks say the values are real, neither of which the method optimises
for: sub-team counts sum to their parent (17 of 22 parents within 15% for 2026-08, many
exact), and the platform total lands at 304-317, a credible Logistics org size.

Caveats that must stay attached to the number: it is an estimate, labelled `est.`
everywhere; it counts whoever DevBoost's denominator counts; teams whose months disagree
show a range and render dimmer; and the partial month reuses the last complete estimate,
because part-way numerators inflate the recovery several-fold.

## Known upstream bugs, surfaced not fixed

**Code coverage is scored exactly 100x low.** Raw `code_coverage` is a fraction
(0.82 = 82%) but normalization divides by max=100, so credit lands at ~0.008 instead of
~0.82. `raw / normalized` is exactly 100.000000 on all 4,916 real measurements across
19 months and all 11 top-level orgs; coverage's normalized ceiling is 0.01 while every
other metric reaches 1.0.

The loss equals each team's actual coverage, so it is not uniform: teams at 80-100%
lose ~4.34 of 5 points, teams under 20% lose ~0.38. **Rankings move** — re-ranking the
198 squads with a coverage measurement reorders 170, largest move 18 places.

The Looker Studio report inherits the defect. It displays raw coverage correctly as a
percentage, but its score reads `overall_score` from this table, so for `log-deliveries`
2026-09 it shows 60% where the corrected value is 64.58. No consumer holds a correct
value; fixing the table fixes all of them.

The fault is not in the pipeline code — `normalized_code_coverage` is computed as
`code_coverage / code_coverage_best`, correct min-max normalization. It is one value in
`dh-gsre-jira-metrics.dev_productivity_metrics.devboost_weights_for_overall_score`:
`performance_code_coverage_best_score` is 100 where it should be 1.

That config is **effective-dated**, and the score table is rebuilt with `WRITE_TRUNCATE`
over all months on every run. So updating the existing row in place backfills all 19
months automatically, while inserting a new effective-dated row would fix only future
months and leave a false ~4-point step in every team's trend. In place is correct here —
this is a unit error, not a weight change.

The snapshot carries a corrected `n_code_coverage_fixed` alongside the official value,
and the UI shows the real coverage bar with a warning. Evidence:
`docs/coverage-scale-defect.html`.

**Missing metrics impute to 0.5**, scoring a team 50% on that metric rather than leaving
it blank. Detect it by a **null raw value alongside a normalized value of exactly 0.5** —
imputation replaces the null, so the normalized column is never null and testing that
column alone silently finds nothing. The snapshot carries `has_imputed_metric` and
`imputed_count`; the UI badges the count on the hero, labels affected metric cards
"imputed", and marks child rows.

In Aug 2026, 6 of the 65 nodes in this snapshot have at least one imputed metric.
`Data & ML` (domain) and `Machine Learning Platform` (squad) each have **4 of 9**,
including all three PR metrics — 45 points of the composite. Their published scores
(43.7 and 33.7) are substantially synthetic. Company-wide the worst case is
`Data Science Service` at 7 of 9.

**The PR gap has a confirmed cause: squad rosters disagree between systems.** DevBoost knows
only `Machine Learning Platform` under the Data & ML domain. The AI adoption dashboard in
[`deliveryhero/logistics-prompt-delivery`](https://github.com/deliveryhero/logistics-prompt-delivery)
(`adoption/`, curated list at `adoption/scripts/devhub-repos.json`) attributes the
Data & ML repos — 12 repos, 515 PRs as of 2026-09 — to a `Data Engineering` squad that
DevBoost has no row for.
So the PR activity is real and visible in the dashboard while absent from DevBoost, which
then imputes. A DevHub registration gap, not a pipeline fault.

This generalizes: comparing the two repo sets (2026-09) found **14 Logistics squads with
registered repos but no DevBoost row**, covering 56 repos — every Data Science squad
(Choice, Seamless, Deliveries, Workforce), `Data Engineering`, `Wallet & Payroll`,
`Routing Models`, `Payment Incentives`, `Tech Council`. A further 14 tracked repos are
absent from `tech_log_devhub_catalog` entirely, so they cannot reach DevBoost by any route.

The adoption dashboard now carries a **Discipline** filter (Data Science vs Software
Engineering) for reading its numbers with the data science squads separated out, which is
what makes the two systems comparable: DevBoost omits those squads, so its Logistics
figures are already close to the dashboard's Software-Engineering-only view.

Two join defects worth knowing before anyone else compares these sources. `squad_id` in
the catalog and DevBoost's `group_id` share an ID space, but **two squads carry a
different id on each side** — `Tracking UI` is `group:log-tracking-ui` in the catalog and
`group:log-tracking-sdk` in DevBoost; `Agent workflows` is `group:ticketing-experience`
vs `group:log-agent-workflows`. Matching on id alone reports their repos as uncovered.
And a repo can be registered under several applications with **different** squads, so
coverage must be "reported under any registration" — first-wins picks by row order and
mis-sorts three repos.

Neither upstream bug — the coverage scale error or the imputation — has been raised
with Tech Foundations, who own the methodology, and nor has the roster mismatch above.
That's deliberate and Brad's call to make.

**Survey metrics are genuinely per-squad.** `dev_satisf_nps` and `focus_nps` are 25% of
the composite and quarterly, but they are *not* inherited from the parent org — every
squad carries a distinct value, so squad-level comparison is valid across the full 100
points. Worth knowing because the opposite is the natural assumption.

`change_failure_rate` is in the table but excluded from the score upstream due to low
adoption. Carried through the snapshot, unused by the UI.

## The Adam mode

An in-joke about AI tools only ever shipping unreadable dark mode. An "Enter Adam mode"
button sits at 34% opacity in the dead space between the two footer notes, costing no
vertical room. Clicking it adds `foradam` to the hash, which redefines the colour tokens
to a deliberately washed-out dark palette and hides the door. The "Switch to light mode"
button that then appears declines, revealing a 3D crawl of AI slop about the singularity,
HuggingFace and unused AOL chatrooms.

One-way from the UI: nothing on the page turns it off, though editing the URL still
works — it is a joke, not a trap, and a curious colleague should be able to get their
dashboard back. View state survives the transition. Respects `prefers-reduced-motion`.

Two things worth knowing if you touch it:

- **Commit the theme through the tokens**, not through `body`. Patching `body` alone
  leaves every card, table and control on the light palette. The `:root[data-adam]`
  block redefines the full set, and the light media query is guarded with
  `:not([data-adam])` so an explicit request beats the OS preference.
- **Crawl geometry**: anchor the rotated plane to the viewport with `inset:0` and rotate
  about its centre, then scroll an inner track in pixels. Animating the rotated plane
  itself does not work — percentage translates resolve against the rotated box, so the
  plane wanders off-screen.

## Custom domain

Serving from `logistics-devboost.deliveryhero.net` since 2026-09-17. CNAME added by
#gdp-support via [dh-cloudflare-dns-tf#4103](https://github.com/deliveryhero/dh-cloudflare-dns-tf/pull/4103),
pointing at the org-level `deliveryhero.github.io`; routing to this repo comes from
`web/CNAME`, which sits in `web/` because that is the directory the workflow publishes.

Order matters if this is ever redone: confirm DNS resolves *before* setting the custom
domain, because Pages stops serving the generated `*.pages.github.io` hostname the
moment one is configured. Note the `CNAME` file alone does not register the domain when
the Pages source is a workflow — set it with
`gh api -X PUT repos/OWNER/REPO/pages -f cname=...`, then enable `https_enforced` once
`.https_certificate.state` reads `approved`.
