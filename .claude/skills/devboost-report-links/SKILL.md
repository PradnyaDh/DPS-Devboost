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

