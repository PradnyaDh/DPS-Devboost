#!/usr/bin/env python3
"""Join the squad->repo mapping against the DevBoost snapshot hierarchy.

Emits one row per (team, repo) for every level of the hierarchy — squad up through
platform — so "what repos does Customer Product Line own" is a lookup, not a join.

Run by scripts/refresh.sh after the snapshot is rebuilt.

Usage: build_repo_map.py RAW.json SNAPSHOT.json OUT_PREFIX
  RAW.json      output of sql/repo_map.sql (bq --format=prettyjson)
  SNAPSHOT.json web/data/snapshot.json, for the team hierarchy
  OUT_PREFIX    writes OUT_PREFIX-{repos.csv,summary.csv,reconciliation.json}
"""
import json, sys, csv
from collections import defaultdict

raw, snap_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
rows = json.load(open(raw))
snap = json.load(open(snap_path))
nodes = snap["nodes"]

# DevBoost and the DevHub catalog disagree on two squad ids. DevBoost's id is the
# key everywhere else in the explorer, so the catalog's is aliased onto it.
# Documented in the devboost-explorer CLAUDE.md.
# Both pairs are documented; they behave differently. log-tracking-ui exists only
# in the catalog, so without the alias its repo lands nowhere. ticketing-experience
# exists in the catalog alongside log-agent-workflows and its single repo is also
# registered under that id directly, so the alias loses nothing and only stops the
# id showing up as an unscored squad.
ALIASES = {
    "group:log-tracking-ui": "group:log-tracking-sdk",
    "group:ticketing-experience": "group:log-agent-workflows",
}

INT = ("sec_issues", "sec_critical", "sec_medium", "sec_minor", "all_issues")

# squad_id -> repo records, keyed by the DevBoost id where one exists
by_squad = defaultdict(list)
for r in rows:
    sid = ALIASES.get(r["squad_id"], r["squad_id"])
    rec = {"repo": r["repo"], "catalog_squad": r["squad"],
           "in_codacy": r["in_codacy"] == "true"}
    rec.update({k: int(r[k]) for k in INT})
    by_squad[sid].append(rec)

def descendants(gid):
    """gid and every node beneath it."""
    seen, stack = set(), [gid]
    while stack:
        g = stack.pop()
        if g in seen or g not in nodes:
            continue
        seen.add(g)
        stack.extend(nodes[g]["children"])
    return seen

# One row per (team, repo) at every level. A repo registered to two squads under the
# same parent is counted once for that parent — dedupe on repo, not on (squad, repo).
team_rows, team_summary = [], []
for gid, n in nodes.items():
    repos = {}
    # Sorted so a repo registered to several squads always attributes to the same
    # one; set iteration order otherwise makes the output differ run to run.
    for d in sorted(descendants(gid)):
        for rec in by_squad.get(d, []):
            prev = repos.get(rec["repo"])
            # keep the record that carries Codacy data if the repo is registered twice
            if prev is None or (rec["in_codacy"] and not prev["in_codacy"]):
                repos[rec["repo"]] = {**rec, "via_squad": d}
    for repo, rec in sorted(repos.items()):
        team_rows.append({
            "group_id": gid, "team": n["name"], "level": n["level"],
            "path": n["path"], "repo": repo, "via_squad": rec["via_squad"],
            "in_codacy": rec["in_codacy"],
            **{k: rec[k] for k in INT},
        })
    vals = list(repos.values())
    team_summary.append({
        "group_id": gid, "team": n["name"], "level": n["level"], "path": n["path"],
        "n_repos": len(vals),
        "n_in_codacy": sum(1 for v in vals if v["in_codacy"]),
        **{k: sum(v[k] for v in vals) for k in INT},
    })

with open(f"{out}-repos.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(team_rows[0].keys()))
    w.writeheader(); w.writerows(team_rows)
with open(f"{out}-summary.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(team_summary[0].keys()))
    w.writeheader(); w.writerows(sorted(team_summary, key=lambda r: r["path"]))

# Reconciliation. These three populations disagree and the residuals are the point:
# a mapping that hid them would be less useful than one that reports them.
devboost_squads = {g for g, n in nodes.items() if n["level"] == "SQUAD"}
catalog_squads = set(by_squad)
scored_no_repos = sorted(devboost_squads - catalog_squads)
catalog_not_scored = sorted(catalog_squads - set(nodes))
mapped_repos = {r["repo"] for r in team_rows}

report = {
    "codacy_loaded_date": rows[0]["codacy_loaded_date"],
    "catalog_rows": len(rows),
    "distinct_repos_in_catalog": len({r["repo"] for r in rows}),
    "repos_mapped_into_hierarchy": len(mapped_repos),
    "devboost_squads": len(devboost_squads),
    "catalog_squads_with_repos": len(catalog_squads),
    "scored_squads_with_no_repos": scored_no_repos,
    "catalog_squads_absent_from_devboost": catalog_not_scored,
    "repos_registered_to_multiple_squads":
        sorted({r["repo"] for r in rows
                if len({x["squad_id"] for x in rows if x["repo"] == r["repo"]}) > 1}),
}
json.dump(report, open(f"{out}-reconciliation.json", "w"), indent=2)

print(f"{len(team_rows)} (team, repo) rows across {len(team_summary)} teams")
print(f"repos: {report['distinct_repos_in_catalog']} in catalog, "
      f"{report['repos_mapped_into_hierarchy']} placed in the DevBoost hierarchy")
print(f"squads: {report['devboost_squads']} scored, "
      f"{report['catalog_squads_with_repos']} with repos, "
      f"{len(scored_no_repos)} scored with none, "
      f"{len(catalog_not_scored)} with repos but unscored")
