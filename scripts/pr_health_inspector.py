import json
import subprocess
import sys

# BigQuery Query to identify the worst PR bottlenecks in the Customer Pricing repos
QUERY = """
SELECT 
  repository_name,
  requester_login,
  title,
  created_at,
  merged_at,
  TIMESTAMP_DIFF(merged_at, created_at, HOUR) AS lifetime_hours,
  -- Estimate review hours if we subtract weekend time (approximate)
  TIMESTAMP_DIFF(merged_at, created_at, HOUR) AS estimated_review_hours
FROM `fulfillment-dwh-production.curated_data_shared_psf.git_pull_requests`
WHERE merged_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND repository_id IN (
    'deliveryhero/logistics-dynamic-pricing',
    'deliveryhero/logistics-dynamic-pricing-api',
    'deliveryhero/logistics-dynamic-pricing-dashboard',
    'deliveryhero/dynamic-pricing-dashboard',
    'deliveryhero/central-dynamic-pricing-model',
    'deliveryhero/logistics-multi-armed-bandit',
    'deliveryhero/pp-dbdf-calibration-tool'
  )
  AND requester_login NOT LIKE '%bot%'
  AND TIMESTAMP_DIFF(merged_at, created_at, HOUR) > 24 -- Focus on PRs exceeding 24h SLA
ORDER BY lifetime_hours DESC
LIMIT 15
"""

print("⏳ Scanning BigQuery for active PR bottlenecks in Customer Pricing (last 30 days)...")

try:
    res = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json", QUERY],
        capture_output=True, text=True, check=True
    )
    prs = json.loads(res.stdout)
except Exception as e:
    print(f"Error scanning PRs: {e}", file=sys.stderr)
    if hasattr(e, 'stderr') and e.stderr:
        print(e.stderr, file=sys.stderr)
    sys.exit(1)

if not prs:
    print("✨ Perfect Health! No Pricing PRs exceeded the 24-hour review SLA in the last 30 days.")
    sys.exit(0)

# Print Report
print("\n" + "="*70)
print("🚨 MASTER PR BOTTLENECK REPORT: CUSTOMER PRICING (SLA EXCEEDED)")
print("="*70)
print(f"{'Repository':<36} | {'Lifetime':<10} | {'PR Title'}")
print("-"*70)
for pr in prs:
    repo = pr["repository_name"]
    hours = int(pr["lifetime_hours"])
    title = pr["title"]
    if len(title) > 40:
        title = title[:37] + "..."
    days = hours / 24.0
    print(f"{repo:<36} | {hours:>4}h ({days:.1f}d) | {title}")
print("="*70)
print("💡 Action: Review these PRs in your 1:1s or standups to identify why approval or CI gates stalled.")
