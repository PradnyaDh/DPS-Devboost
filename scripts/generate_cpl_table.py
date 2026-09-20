import json
import subprocess
import sys

# 1. BigQuery Query to fetch all CPL repositories
QUERY = """
SELECT DISTINCT
  repo,
  d.id AS app_id,
  d.owner AS owner,
  d.info.squad AS squad,
  d.info.product_line_id AS product_line_id,
  d.info.tribe_id AS tribe_id,
  d.info.squad_id AS squad_id
FROM `fulfillment-dwh-production.cl.tech_log_devhub` d,
UNNEST(github_repositories) AS repo
WHERE d.archived = false
  AND d.info.product_line_id = 'group:customer-product-line'
ORDER BY tribe_id, squad_id, repo
"""

print("⏳ Fetching Customer Product Line data from BigQuery...")

# Run bq query
try:
    res = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json", "--max_rows=1000", QUERY],
        capture_output=True, text=True, check=True
    )
    raw_data = json.loads(res.stdout)
except Exception as e:
    print(f"Error fetching data: {e}", file=sys.stderr)
    if hasattr(e, 'stderr') and e.stderr:
        print(e.stderr, file=sys.stderr)
    sys.exit(1)

# 2. Analyze status and registry discrepancies
processed_rows = []

for row in raw_data:
    repo = row.get("repo", "")
    app_id = row.get("app_id", "")
    pl_id = row.get("product_line_id", "").replace("group:", "")
    tribe_id = row.get("tribe_id", "").replace("group:", "")
    squad_id = row.get("squad_id", "")
    
    # Clean up squad representation
    squad_display = squad_id.replace("group:", "") if squad_id else "NULL"
    
    # Default clean mapping status
    status = "Correct mapping"
    
    # 3. Apply custom logic for each repo based on our audit findings
    if repo == "deliveryhero/logistics-dynamic-pricing":
        if app_id == "dynamic-pricing-api":
            status = "Mismatch: Repoint to api repo & Benefits squad"
        elif app_id == "dynamic-pricing-workspace":
            status = "Mismatch: Repoint to dashboard repo & Benefits squad"
        elif app_id in ["dynamic-pricing-admin", "dynamic-pricing-consumer", "dynamic-pricing-jobs"]:
            status = "Workspace dead-squad mapping: Set owner to Mechanisms"
        elif app_id == "logisticsdynamicpricingservice.dynamic-pricing":
            status = "Mismatch: Monolith mapped to Algo squad"
    elif repo == "deliveryhero/logistics-dynamic-pricing-api":
        if squad_id != "group:log-pricing-benefits":
            status = "Mismatch: Reassign from Algo to Benefits squad"
    elif repo == "deliveryhero/central-dynamic-pricing-model" and squad_id == "group:log-pricing-foundations":
        status = "Mismatch: Reassign from Foundations to Algo squad"
    elif repo == "deliveryhero/pp-dbdf-calibration-tool" and squad_id == "group:log-pricing-foundations":
        status = "Mismatch: Reassign from Foundations to Algo squad"
    elif repo == "deliveryhero/logistics-multi-armed-bandit" and squad_id == "group:log-pricing-foundations":
        status = "Mismatch: Reassign from Foundations to Algo squad"
    elif repo == "deliveryhero/logistics-dynamic-pricing-dashboard" and squad_id == "group:log-pricing-benefits" and not row.get("squad"):
        status = "Untagged: Squad name field is NULL"
    elif not squad_id or squad_id == "NULL":
        status = "Untagged: No squad assigned"
        
    processed_rows.append({
        "repo": repo,
        "app_id": app_id,
        "pl_id": pl_id,
        "tribe_id": tribe_id,
        "squad": squad_display,
        "status": status
    })

# 4. Generate the exact ASCII table structure requested by the user
# Column widths from user's template:
# Col 1 (repo): 63 chars
# Col 2 (app_id): 51 chars
# Col 3 (pl_id): 23 chars
# Col 4 (tribe_id): 14 chars
# Col 5 (squad): 12 chars
# Col 6 (status): 45 chars (expanded slightly for readability)

W_REPO = 63
W_APP = 51
W_PL = 23
W_TRIBE = 14
W_SQUAD = 12
W_STATUS = 45

def pad(text, width):
    if len(text) > width:
        return text[:width-3] + "..."
    return text.ljust(width)

# Print table borders and header
print("  ┌" + "─"*W_REPO + "┬" + "─"*W_APP + "┬" + "─"*W_PL + "┬" + "─"*W_TRIBE + "┬" + "─"*W_SQUAD + "┬" + "─"*W_STATUS + "┐")
print("  │ " + pad("Repository ID", W_REPO-2) + " │ " + pad("DevHub Application ID", W_APP-2) + " │ " + pad("Product Line ID", W_PL-2) + " │ " + pad("Tribe ID", W_TRIBE-2) + " │ " + pad("Registered", W_SQUAD-2) + " │ " + pad("Status / Registry", W_STATUS-2) + " │")
print("  │ " + pad("", W_REPO-2) + " │ " + pad("", W_APP-2) + " │ " + pad("", W_PL-2) + " │ " + pad("", W_TRIBE-2) + " │ " + pad("info.squad", W_SQUAD-2) + " │ " + pad("Discrepancy", W_STATUS-2) + " │")
print("  ├" + "─"*W_REPO + "┼" + "─"*W_APP + "┼" + "─"*W_PL + "┼" + "─"*W_TRIBE + "┼" + "─"*W_SQUAD + "┼" + "─"*W_STATUS + "┤")

# Print rows
for row in processed_rows:
    print("  │ " + pad(row["repo"], W_REPO-2) + " │ " + pad(row["app_id"], W_APP-2) + " │ " + pad(row["pl_id"], W_PL-2) + " │ " + pad(row["tribe_id"], W_TRIBE-2) + " │ " + pad(row["squad"], W_SQUAD-2) + " │ " + pad(row["status"], W_STATUS-2) + " │")

print("  └" + "─"*W_REPO + "┴" + "─"*W_APP + "┴" + "─"*W_PL + "┴" + "─"*W_TRIBE + "┴" + "─"*W_SQUAD + "┴" + "─"*W_STATUS + "┘")
