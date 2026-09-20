import json
import subprocess
import sys

# BigQuery Query to analyze reviewer load, average turnaround, and bottlenecks
QUERY = """
WITH first_reviews AS (
  -- Find the first review (Approval or Changes Requested) for each human PR
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
    pr.requester_login AS author,
    fr.review_user AS reviewer,
    pr.created_at,
    fr.first_review_at,
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

print("⏳ Fetching 90-day review load metrics from BigQuery...")

try:
    res = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=json", QUERY],
        capture_output=True, text=True, check=True
    )
    reviews = json.loads(res.stdout)
except Exception as e:
    print(f"Error querying reviews: {e}", file=sys.stderr)
    if hasattr(e, 'stderr') and e.stderr:
        print(e.stderr, file=sys.stderr)
    sys.exit(1)

# Print Report
print("\n" + "="*70)
print("🔍 SQUAD CODE REVIEW HEALTH & LOAD SHIELD REPORT (LAST 90 DAYS)")
print("="*70)
print(f"{'Reviewer Login':<25} | {'PRs Reviewed':<18} | {'Avg Turnaround Time'}")
print("-"*70)
for r in reviews:
    reviewer = r["reviewer"]
    count = int(r["total_reviews_done"])
    hours = float(r["avg_turnaround_hours"])
    days = hours / 24.0
    
    # Label warning level based on turnaround or load
    warning = ""
    if hours > 48.0:
        warning = "⚠️ SLOW SLA (>48h)"
    elif count > 20:
        warning = "🔥 HIGH LOAD (>20 reviews)"
        
    print(f"{reviewer:<25} | {count:<18} | {hours:>5}h ({days:.1f}d) {warning}")
print("="*70)
print("💡 Diagnostics & Core Actions:")
print("1. 🔥 HIGH LOAD? If a few senior leads do all reviews, delegate to spread the load.")
print("2. ⚠️ SLOW SLA? Implement automated Slack nudges for PRs waiting over 24 hours.")
print("3. 📦 Reduce PR size: Small, atomic PRs are approved 3x faster than giant branches.")
