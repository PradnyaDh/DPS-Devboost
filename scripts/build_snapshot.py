#!/usr/bin/env python3
"""Reshape the BigQuery row dump into the nested structure the explorer loads.

Output:
  generated : ISO timestamp
  months    : sorted month keys present
  latest    : last complete month (partial current month excluded)
  nodes     : {group_id: {name, level, path, parent (group_id|None),
                          children[], series{month: metrics}}}
"""
import json, sys
from datetime import datetime, timezone

WEIGHTS = {  # from the DevBoost methodology; verified exact against overall_score
    "dev_satisf_nps": 0.15, "bugs_per_eng": 0.10, "code_coverage": 0.05,
    "code_security": 0.05, "prs_per_eng_day": 0.15, "depl_per_eng_day": 0.10,
    "pr_review_hrs": 0.15, "pr_lifetime_hrs": 0.15, "focus_nps": 0.10,
}
RAW = list(WEIGHTS) + ["change_failure_rate"]

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
        "children": [], "series": {},
    })
    # path/name track the most recent month, since reorgs rewrite the path
    if month >= max(n["series"], default=""):
        n.update(name=r["name"], level=r["level"],
                 path=r["label_path"], parent_path=r["parent_path"])
    m = {"score": num(r["score"]),
         "imputed": r["has_imputed_metric"] in (True, "true")}
    for k in RAW:
        m[k] = num(r.get(k))
    for k in WEIGHTS:
        m["n_" + k] = num(r.get("n_" + k))
    m["n_code_coverage_fixed"] = num(r.get("n_code_coverage_fixed"))
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
