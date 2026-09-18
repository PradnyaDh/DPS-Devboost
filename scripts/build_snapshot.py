#!/usr/bin/env python3
"""Reshape the BigQuery row dump into the nested structure the explorer loads.

Output:
  generated : ISO timestamp
  months    : sorted month keys present
  latest    : last complete month (partial current month excluded)
  nodes     : {group_id: {name, level, path, parent (group_id|None),
                          children[], series{month: metrics}}}
"""
import json, sys, math, calendar
from collections import Counter
from datetime import datetime, timezone, date
from fractions import Fraction

WEIGHTS = {  # from the DevBoost methodology; verified exact against overall_score
    "dev_satisf_nps": 0.15, "bugs_per_eng": 0.10, "code_coverage": 0.05,
    "code_security": 0.05, "prs_per_eng_day": 0.15, "depl_per_eng_day": 0.10,
    "pr_review_hrs": 0.15, "pr_lifetime_hrs": 0.15, "focus_nps": 0.10,
}
RAW = list(WEIGHTS) + ["change_failure_rate"]

def working_days(month):
    """Weekdays in a YYYY-MM month. Public holidays are ignored — DevBoost's own
    denominator appears to use plain weekdays, which is what the recovery below
    reproduces."""
    y, m = (int(x) for x in month.split("-"))
    n = calendar.monthrange(y, m)[1]
    return sum(1 for d in range(1, n + 1) if date(y, m, d).weekday() < 5)


def headcount_candidate(bugs, prs, month):
    """Smallest headcount consistent with one month's per-engineer metrics.

    Headcount is not published, but it divides the per-engineer metrics:
        bugs_per_engineer = bugs / H            -> denominator divides H
        prs_per_engineer  = prs / (H * workdays)-> denominator divides H*workdays
    Both arrive as exact rationals. Python recovers them in *lowest terms*, so a
    single month yields only a divisor of H, never H itself — which is why this
    returns a candidate and resolve_headcount() needs several months.

    PRs carry far more information than bugs: the extra working-days factor makes
    the denominator large, so it rarely collapses. Bugs alone degenerates to 1
    for ~16% of rows (an integer bugs-per-engineer tells you nothing).
    """
    need = []
    if bugs is not None:
        need.append(Fraction(bugs).limit_denominator(3000).denominator)
    if prs is not None:
        d = Fraction(prs).limit_denominator(30000).denominator
        need.append(d // math.gcd(d, working_days(month)))
    if not need:
        return None
    h = 1
    for d in need:
        h = h * d // math.gcd(h, d)
    return h


HC_WINDOW = 6   # months of history used per estimate

def resolve_headcount(cands):
    """Pick a headcount from per-month candidates, with a confidence flag.

    Every candidate divides the true headcount, so the maximum over the window is
    the best estimate and the mode says whether it is stable.

    The window matters: teams genuinely change size, so judging stability over all
    19 months conflates real growth with recovery noise. Over 18 months only 15 of
    63 nodes look stable; over a trailing 6 they agree 41 of 63 — the difference is
    hiring, not error. Six rather than four because three or four samples cannot
    tell a stable team from a lucky one.
    """
    vals = [v for v in cands if v]
    if not vals:
        return None, None, None
    best = max(vals)
    # Discard collapsed months before judging agreement. Every candidate divides
    # the true count, so a month whose numerator shared a factor reads as an exact
    # fraction of it (the platform row yields 155 and 158 against 317 — halves, not
    # evidence the org halved). Only candidates within 25% of the max are treated
    # as real observations; the rest carry no information about the true value.
    near = [v for v in vals if v >= best * 0.75]
    mode, hits = Counter(near).most_common(1)[0]
    if len(vals) < 3:
        conf = "low"
    elif len(near) >= max(3, len(vals) * 0.6) and hits >= len(near) / 2:
        conf = "high"
    elif len(near) >= len(vals) / 2:
        conf = "medium"
    else:
        conf = "low"
    # Low end of the plausible range: the smallest non-collapsed observation.
    return best, conf, min(near)


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return v

rows = json.load(open(sys.argv[1]))

nodes, months = {}, set()
for r in rows:
    gid, month = r["group_id"], r["month"]
    months.add(month)
    n = nodes.setdefault(gid, {
        "id": gid, "name": r["name"], "level": r["level"],
        "path": r["label_path"], "parent_path": r["parent_path"],
        # untouched display name; Looker Studio's team filter matches it exactly
        "raw": r.get("raw_hierarchy"),
        "children": [], "series": {},
    })
    # path/name track the most recent month, since reorgs rewrite the path
    if month >= max(n["series"], default=""):
        n.update(name=r["name"], level=r["level"],
                 path=r["label_path"], parent_path=r["parent_path"],
                 raw=r.get("raw_hierarchy"))
    m = {"score": num(r["score"]),
         "imputed": r["has_imputed_metric"] in (True, "true"),
         "imputed_count": int(r.get("imputed_count") or 0)}
    for k in RAW:
        m[k] = num(r.get(k))
    for k in WEIGHTS:
        m["n_" + k] = num(r.get("n_" + k))
    m["n_code_coverage_fixed"] = num(r.get("n_code_coverage_fixed"))
    # Per-month headcount candidate — a divisor of the true count, resolved below.
    m["hc_cand"] = headcount_candidate(num(r.get("hc_bugs_raw")),
                                       num(r.get("hc_prs_raw")), month)
    n["series"][month] = m

# link parents by path. A path can map to several ids when a team is renamed
# and its old id stops reporting; the longest-lived id wins and stale ones are
# dropped so the tree stays single-rooted.
by_path = {}
for gid, n in sorted(nodes.items(),
                     key=lambda kv: (len(kv[1]["series"]),
                                     max(kv[1]["series"], default="")),
                     reverse=True):
    by_path.setdefault(n["path"], gid)
superseded = {g for g, n in nodes.items() if by_path.get(n["path"]) != g}
for g in superseded:
    del nodes[g]
for gid, n in nodes.items():
    segs = n["path"].split(" / ")
    parent_path = " / ".join(segs[:-1]) if len(segs) > 1 else ""
    pid = by_path.get(parent_path) if parent_path else None
    n["parent"] = pid if pid != gid else None
    if n["parent"]:
        nodes[n["parent"]]["children"].append(gid)

for n in nodes.values():
    n["children"].sort(key=lambda c: nodes[c]["name"])
    n.pop("parent_path", None)

# Drop anything not reachable from the root: pre-June-2025 paths whose parent
# tribe no longer exists. These stopped reporting during the 2025 reorg.
def reachable(root):
    seen, stack = set(), [root]
    while stack:
        g = stack.pop()
        if g in seen:
            continue
        seen.add(g)
        stack.extend(nodes[g]["children"])
    return seen

_root = next((g for g, v in nodes.items() if v["parent"] is None), None)
keep = reachable(_root)
dropped = [nodes[g]["path"] for g in set(nodes) - keep]
for g in set(nodes) - keep:
    del nodes[g]
if dropped:
    print(f"dropped {len(dropped)} orphaned (pre-reorg) node(s): {dropped}")

months = sorted(months)
# The current month is partial until it ends; never chart it as if complete.
now = datetime.now(timezone.utc)
partial = f"{now.year:04d}-{now.month:02d}"
complete = [m for m in months if m != partial]

# Resolve headcount per node from its complete months. The partial current month
# is excluded: its numerators are part-way through, which inflates the recovered
# denominator wildly (observed 3-6x on a month two days in).
hc_stats = Counter()
for n in nodes.values():
    # Per month, resolved from that month and the HC_WINDOW-1 before it, so the
    # figure tracks the selected month instead of being one static number.
    for i, mth in enumerate(complete):
        if mth not in n["series"]:
            continue
        window = [m for m in complete[max(0, i - HC_WINDOW + 1): i + 1] if m in n["series"]]
        best, conf, mode = resolve_headcount(
            [n["series"][m].get("hc_cand") for m in window])
        n["series"][mth]["headcount"] = best
        n["series"][mth]["hc_conf"] = conf
        n["series"][mth]["hc_mode"] = mode
    # The partial month reuses the last complete estimate: its own numerators are
    # part-way through, so recovering from them inflates the count several-fold.
    if partial in n["series"]:
        prev = next((m for m in reversed(complete) if m in n["series"]), None)
        if prev:
            n["series"][partial]["headcount"] = n["series"][prev].get("headcount")
            n["series"][partial]["hc_conf"] = n["series"][prev].get("hc_conf")
            n["series"][partial]["hc_mode"] = n["series"][prev].get("hc_mode")
    last = next((m for m in reversed(complete) if m in n["series"]), None)
    hc_stats[(n["series"][last].get("hc_conf") if last else None) or "none"] += 1
print("headcount confidence (latest month):", dict(hc_stats))

root = next((g for g, n in nodes.items() if n["parent"] is None), None)
json.dump({
    "generated": now.isoformat(timespec="seconds"),
    "months": months,
    "complete_months": complete,
    "latest": complete[-1] if complete else months[-1],
    "partial_month": partial if partial in months else None,
    "root": root,
    "weights": WEIGHTS,
    "nodes": nodes,
}, open(sys.argv[2], "w"), separators=(",", ":"))

print(f"{len(nodes)} nodes, {len(months)} months, root={root}")
