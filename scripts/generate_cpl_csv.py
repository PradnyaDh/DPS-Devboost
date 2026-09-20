import csv
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

print("⏳ Fetching Customer Product Line data from BigQuery to generate CSV...")

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
    
    # Apply custom logic for each repo based on our audit findings
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
        "Repository ID": repo,
        "DevHub Application ID": app_id,
        "Product Line ID": pl_id,
        "Tribe ID": tribe_id,
        "Registered info.squad": squad_display,
        "Status / Registry Discrepancy": status
    })

# 3. Write data to CSV
csv_path = "/Users/pradnya.shelar/devhub_registry_cpl_audit.csv"

try:
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "Repository ID", "DevHub Application ID", "Product Line ID", 
            "Tribe ID", "Registered info.squad", "Status / Registry Discrepancy"
        ])
        writer.writeheader()
        writer.writerows(processed_rows)
    print(f"✅ Successfully wrote {len(processed_rows)} rows to {csv_path}!")
except Exception as e:
    print(f"Error writing CSV file: {e}", file=sys.stderr)
    sys.exit(1)
