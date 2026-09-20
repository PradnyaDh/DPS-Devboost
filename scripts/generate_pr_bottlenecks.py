import json
import subprocess
import sys

# 1. BigQuery Query to fetch all Customer Pricing PR bottlenecks (anonymized)
QUERY_PR = """
SELECT 
  pr.repository_id,
  pr.repository_name,
  pr.requester_login,
  pr.title,
  pr.created_at,
  pr.merged_at,
  CONCAT('https://github.com/', pr.repository_id, '/pull/', pr.pr_number) AS html_url,
  TIMESTAMP_DIFF(pr.merged_at, pr.created_at, HOUR) AS lifetime_hours
FROM `fulfillment-dwh-production.curated_data_shared_psf.git_pull_requests` AS pr
WHERE pr.merged_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND pr.repository_id IN (
    'deliveryhero/logistics-dynamic-pricing',
    'deliveryhero/logistics-dynamic-pricing-api',
    'deliveryhero/logistics-dynamic-pricing-dashboard',
    'deliveryhero/dynamic-pricing-dashboard',
    'deliveryhero/central-dynamic-pricing-model',
    'deliveryhero/logistics-multi-armed-bandit',
    'deliveryhero/pp-dbdf-calibration-tool'
  )
  AND pr.requester_login NOT LIKE '%bot%'
  AND TIMESTAMP_DIFF(pr.merged_at, pr.created_at, HOUR) > 24
ORDER BY lifetime_hours DESC
"""

# 2. BigQuery Query to fetch 90-day Reviewer load and speeds
QUERY_REV = """
WITH first_reviews AS (
  SELECT 
    rev.repository_id,
    rev.pr_number,
    rev.review_user,
    MIN(rev.submitted_at) AS first_review_at
  FROM `fulfillment-dwh-production.curated_data_shared_psf.git_pr_reviews` AS rev
  WHERE rev.review_user NOT LIKE '%bot%'
    AND rev.review_state IN ('APPROVED', 'CHANGES_REQUESTED')
  GROUP BY 1, 2, 3
),
pr_review_durations AS (
  SELECT 
    pr.repository_name,
    pr.pr_number,
    fr.review_user AS reviewer,
    TIMESTAMP_DIFF(fr.first_review_at, pr.created_at, HOUR) AS review_wait_hours
  FROM `fulfillment-dwh-production.curated_data_shared_psf.git_pull_requests` AS pr
  INNER JOIN first_reviews AS fr
    ON pr.pr_number = fr.pr_number AND pr.repository_id = fr.repository_id
  WHERE pr.merged_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
    AND pr.repository_id IN (
      'deliveryhero/logistics-dynamic-pricing',
      'deliveryhero/logistics-dynamic-pricing-api',
      'deliveryhero/logistics-dynamic-pricing-dashboard',
      'deliveryhero/dynamic-pricing-dashboard',
      'deliveryhero/central-dynamic-pricing-model',
      'deliveryhero/logistics-multi-armed-bandit',
      'deliveryhero/pp-dbdf-calibration-tool'
    )
    AND pr.requester_login NOT LIKE '%bot%'
)
SELECT 
  reviewer,
  COUNT(DISTINCT pr_number) AS total_reviews_done,
  ROUND(AVG(review_wait_hours), 1) AS avg_turnaround_hours
FROM pr_review_durations
GROUP BY reviewer
ORDER BY total_reviews_done DESC
"""

print("⏳ Fetching Pricing PR bottlenecks and Reviewer telemetry from BigQuery...")

# Run PR bottlenecks query
try:
    res_pr = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json", "--max_rows=100", QUERY_PR],
        capture_output=True, text=True, check=True
    )
    prs = json.loads(res_pr.stdout)
except Exception as e:
    print(f"Error querying PRs: {e}", file=sys.stderr)
    sys.exit(1)

# Run Reviewers telemetry query
try:
    res_rev = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json", "--max_rows=100", QUERY_REV],
        capture_output=True, text=True, check=True
    )
    revs = json.loads(res_rev.stdout)
except Exception as e:
    print(f"Error querying reviews: {e}", file=sys.stderr)
    sys.exit(1)

# Compile PR Bottlenecks JSON
bottlenecks = {
    "group:pricing": [],
    "group:log-pricing-benefits": [],
    "group:log-pricing-foundations": [],
    "group:log-pricing-orchestration": []
}

for pr in prs:
    repo_name = pr["repository_name"]
    hours = int(pr["lifetime_hours"])
    title = pr["title"]
    url = pr["html_url"]
    
    item = {
        "repo": repo_name,
        "hours": hours,
        "title": title,
        "url": url
    }
    
    # Domain level
    bottlenecks["group:pricing"].append(item)
    
    # Squad allocation
    if repo_name in ["logistics-dynamic-pricing-api", "logistics-dynamic-pricing-dashboard", "dynamic-pricing-dashboard"]:
        bottlenecks["group:log-pricing-benefits"].append(item)
    elif repo_name in ["logistics-dynamic-pricing"]:
        bottlenecks["group:log-pricing-foundations"].append(item)
    elif repo_name in ["central-dynamic-pricing-model", "pp-dbdf-calibration-tool", "logistics-multi-armed-bandit"]:
        bottlenecks["group:log-pricing-orchestration"].append(item)

out_pr_path = "/Users/pradnya.shelar/prad-devboost-explorer/web/data/pr_bottlenecks.json"
try:
    with open(out_pr_path, "w") as f:
        json.dump(bottlenecks, f, indent=2)
    print(f"   Wrote: {out_pr_path}")
except Exception as e:
    print(f"Error writing PR JSON: {e}")
    sys.exit(1)

# Compile and Anonymize Reviewer Health JSON
# Map reviewer logins to "Reviewer A", "Reviewer B", etc. (ordered by volume of reviews)
anonymized_reviews = []
for idx, r in enumerate(revs):
    count = int(r["total_reviews_done"])
    hours = float(r["avg_turnaround_hours"])
    label = f"Reviewer {chr(65 + idx)}" if idx < 26 else f"Reviewer Z{idx-25}"
    
    anonymized_reviews.append({
        "label": label,
        "count": count,
        "hours": hours
    })

out_rev_path = "/Users/pradnya.shelar/prad-devboost-explorer/web/data/code_review_health.json"
try:
    with open(out_rev_path, "w") as f:
        json.dump(anonymized_reviews, f, indent=2)
    print(f"   Wrote: {out_rev_path}")
    print("✅ Successfully synchronized all live metrics JSON files!")
except Exception as e:
    print(f"Error writing Reviewer JSON: {e}")
    sys.exit(1)
