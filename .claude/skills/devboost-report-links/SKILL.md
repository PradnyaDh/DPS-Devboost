---
name: devboost-report-links
description: Build deep links into the official DevBoost Looker Studio report for a given team. Use when generating, debugging, or verifying the provenance panel's report links, or when asked how the df249/df53/df207 filter params encode a team.
---


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

## The Codacy Code Security page — do not deep-link it

The report has a **Codacy Code Security** page (`p_qkwxk3lkrd`, datasource
`s=kz4Oms3kKEo` — both different from the scorecard's) listing open Codacy findings:
repository, category, severity, pattern, message, file path, line, link per issue.
It is filtered by `df249` in the UI and reads at every level, so it looks like the
ideal target for a per-metric source link. **It cannot be linked to reliably.**

**Looker replays the viewer's saved filter state over the incoming URL.** Opening a
generated link in a browser that has used this report discards the `df249` in the URL
and restores the last-used filter, together with the full param set from that session
(`df274`, `df275`, `df344`, `df345`, `df53`, `df55`, `df105`, `df117`, `df154`,
`df160`, `df145`, `df207`). The reader lands on someone else's team.

Demonstrated conclusively: a link carrying
`[SQUAD] Logistics / Rider / Workforce / Payments & Incentives / Rewards (rider-rewards)`
— no connection to Customer — loaded as
`[PRODUCT-LINE] Logistics / Customer Product Line (customer-product-line)`, because that
was the session's saved filter. A new tab does not help; the state is per profile, not
per tab.

**This defeats verification too, so be careful believing a success here.** A generated
link "working" only proves the saved state happened to match what you asked for. During
this investigation a product-line link appeared to load correctly and was recorded as
verified; it was the sticky state agreeing by coincidence. To test properly you need a
profile that has never opened the report — and a clean profile hits the Google login
wall, so there is currently no way to test this from the CLI at all.

Earlier notes in this file claimed the `s` token was the deciding factor between a
working and a broken link (`kz4Oms3kKEo` vs `lrt_RG_kWfY`). That was the same illusion:
the apparent difference tracked what the session held at the time, not the token.

**What still holds.** The scorecard deep link (`page/EojEF`, `s=m1Y11HWY8Dw`) documented
above has been verified separately and is used by the explorer's provenance panel. The
sticky-state behaviour presumably affects it too — worth re-checking before trusting it
in a context where landing on the wrong team matters.

**If a code-security source link is wanted later**, the options are: link to the report
without a team filter and let the reader pick, ask Tech Foundations whether the page can
be made linkable (a URL-driven filter that beats saved state), or go back to per-repo
Codacy links, which are honest but stop at squad level and cannot confirm which repos
are actually onboarded.

**Encoding**, if a link is ever built: values are double-encoded, once inside the JSON
and once as the query string, and the parens in the trailing `(slug)` stay literal.
