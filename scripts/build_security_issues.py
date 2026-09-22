#!/usr/bin/env python3
"""Pack Codacy security issues into the file the explorer fetches on demand.

Run by scripts/refresh.sh. The raw query is ~15MB of JSON; this gets it under a
megabyte so it can be a single lazy fetch rather than a paginated API:

  - columnar rows (arrays, not objects) so field names are stored once
  - repo, pattern and message interned into lookup tables; the same CVE text
    repeats across hundreds of lockfile rows
  - issues grouped by month then squad, so the UI slices without scanning

Usage: build_security_issues.py RAW.json SNAPSHOT.json OUT.json
"""
import json, sys
from collections import defaultdict

raw, snap_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
rows = json.load(open(raw))
snap = json.load(open(snap_path))

# Catalog ids that differ from DevBoost's. Same aliases as the repo map.
ALIASES = {
    "group:log-tracking-ui": "group:log-tracking-sdk",
    "group:ticketing-experience": "group:log-agent-workflows",
}
SEV = {"critical": 0, "high": 1, "medium": 2, "minor": 3}

# Intern the repeated strings. Messages dominate: a CVE description is identical
# across every lockfile row that carries it.
repos, patterns, messages, files = {}, {}, {}, {}
def intern(tbl, v):
    v = v or ""
    if v not in tbl:
        tbl[v] = len(tbl)
    return tbl[v]

# month -> squad -> [issue, ...]
by_month = defaultdict(lambda: defaultdict(list))
loaded = {}
for r in rows:
    sid = ALIASES.get(r["squad_id"], r["squad_id"])
    by_month[r["month"]][sid].append([
        intern(repos, r["repo"]),
        SEV.get(r["severity"], 3),
        intern(patterns, r["pattern"]),
        intern(messages, r["message"]),
        intern(files, r["file_path"]),
        int(r["line_number"] or 0),
        r["issue_id"] or "",
    ])
    loaded[r["month"]] = r["loaded_date"]

inv = lambda t: [k for k, _ in sorted(t.items(), key=lambda kv: kv[1])]
doc = {
    # field order of each issue row, so the UI is not indexing magic numbers
    "fields": ["repo", "sev", "pattern", "msg", "file", "line", "id"],
    "severities": ["critical", "high", "medium", "minor"],
    "repos": inv(repos),
    "patterns": inv(patterns),
    "messages": inv(messages),
    "files": inv(files),
    "loaded": loaded,          # month -> the Codacy load date it came from
    "months": {m: dict(s) for m, s in by_month.items()},
}
json.dump(doc, open(out, "w"), separators=(",", ":"))

import os
print(f"{len(rows)} issues, {len(by_month)} months, "
      f"{len(repos)} repos, {len(messages)} distinct messages "
      f"-> {os.path.getsize(out)/1e6:.1f}MB")
