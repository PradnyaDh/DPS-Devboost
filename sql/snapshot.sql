-- DevBoost hierarchy snapshot for the Logistics domain.
--
-- Emits one row per (group, month). Every hierarchy level (PLATFORM / DOMAIN /
-- TRIBE / SQUAD) is published by DevBoost as its own pre-aggregated row, each
-- recomputed from raw events rather than averaged from its children, so parent
-- rows are read directly and never derived here.
--
-- Identity is group_id: reorgs rewrite the display path while the id is stable.
-- The label therefore comes from each group's most recent path.

WITH src AS (
  SELECT
    report_month,
    group_id,
    hierarchy_full_display_name AS raw_hierarchy,
    REGEXP_EXTRACT(hierarchy_full_display_name, r'^\[([A-Z-]+)\]')    AS level,
    -- drop the "[LEVEL] " prefix and the trailing " (group-slug)"
    REGEXP_REPLACE(
      REGEXP_REPLACE(hierarchy_full_display_name, r'^\[[A-Z-]+\] ', ''),
      r' \([^)]*\)$', ''
    )                                                                  AS path,
    dev_satisf_nps, normalized_dev_satisf_nps,
    num_bugs_per_engineer, normalized_num_bugs_per_engineer,
    code_coverage, normalized_code_coverage,
    code_security, normalized_code_security,
    num_prs_merged_per_engineer, normalized_num_prs_merged_per_engineer,
    depl_frequency, normalized_depl_frequency,
    median_pr_reviewtime, normalized_median_pr_reviewtime,
    median_pr_lifetime, normalized_median_pr_lifetime,
    focus_nps, normalized_focus_nps,
    change_failure_rate,
    overall_score
  FROM `fulfillment-dwh-production.curated_data_shared_psf.devboost_overall_monthly_score`
  WHERE report_month >= DATE '2025-01-01'
    AND hierarchy_full_display_name LIKE '%Logistics%'
),

-- Most recent path per group: reorgs change the path, not the id.
latest AS (
  SELECT group_id, path AS label_path, level
  FROM (
    SELECT group_id, path, level,
           ROW_NUMBER() OVER (PARTITION BY group_id ORDER BY report_month DESC) AS rn
    FROM src
  )
  WHERE rn = 1
),

-- Placeholder groups from before the hierarchy settled (June 2025): unnamed
-- path segments, or fragments that stopped reporting during the 2025 churn.
excluded AS (
  SELECT group_id
  FROM latest
  WHERE label_path LIKE '%/ -%' OR label_path LIKE '%/ -'
),

joined AS (
  SELECT
    s.report_month,
    s.group_id,
    l.level,
    l.label_path,
    SPLIT(l.label_path, ' / ')[SAFE_OFFSET(ARRAY_LENGTH(SPLIT(l.label_path,' / ')) - 1)] AS name,
    -- parent = label_path minus its last segment; empty for the root
    IF(ARRAY_LENGTH(SPLIT(l.label_path, ' / ')) <= 1, '',
       ARRAY_TO_STRING(
         ARRAY_SLICE(SPLIT(l.label_path, ' / '), 0,
                     ARRAY_LENGTH(SPLIT(l.label_path, ' / ')) - 1), ' / '))      AS parent_path,
    s.raw_hierarchy,
    s.* EXCEPT (report_month, group_id, level, path, raw_hierarchy)
  FROM src s
  JOIN latest l USING (group_id)
  WHERE s.group_id NOT IN (SELECT group_id FROM excluded)
)

SELECT
  FORMAT_DATE('%Y-%m', report_month) AS month,
  group_id, level, name, label_path, parent_path,
  -- untouched display name: Looker Studio's team filter matches on this exactly
  raw_hierarchy,
  ROUND(overall_score * 100, 2) AS score,
  ROUND(dev_satisf_nps, 2)               AS dev_satisf_nps,
  ROUND(num_bugs_per_engineer, 3)        AS bugs_per_eng,
  ROUND(code_coverage * 100, 2)          AS code_coverage,   -- raw is a fraction; shown as %
  ROUND(code_security, 3)                AS code_security,
  ROUND(num_prs_merged_per_engineer, 4)  AS prs_per_eng_day,
  ROUND(depl_frequency, 4)               AS depl_per_eng_day,
  ROUND(median_pr_reviewtime, 2)         AS pr_review_hrs,
  ROUND(median_pr_lifetime, 2)           AS pr_lifetime_hrs,
  ROUND(focus_nps, 2)                    AS focus_nps,
  ROUND(change_failure_rate, 4)          AS change_failure_rate,
  -- normalized 0-1 values, already weight-ready
  ROUND(normalized_dev_satisf_nps, 4)               AS n_dev_satisf_nps,
  ROUND(normalized_num_bugs_per_engineer, 4)        AS n_bugs_per_eng,
  ROUND(normalized_code_coverage, 4)                AS n_code_coverage,
  -- DevBoost normalizes coverage against max=100 though the raw value is a
  -- fraction (0-1), so this lands ~100x low and costs every team ~4.7 pts.
  -- Reported as-is to match the official score; corrected value shown alongside.
  ROUND(LEAST(code_coverage, 1.0), 4)               AS n_code_coverage_fixed,
  ROUND(normalized_code_security, 4)                AS n_code_security,
  ROUND(normalized_num_prs_merged_per_engineer, 4)  AS n_prs_per_eng_day,
  ROUND(normalized_depl_frequency, 4)               AS n_depl_per_eng_day,
  ROUND(normalized_median_pr_reviewtime, 4)         AS n_pr_review_hrs,
  ROUND(normalized_median_pr_lifetime, 4)           AS n_pr_lifetime_hrs,
  ROUND(normalized_focus_nps, 4)                    AS n_focus_nps,
  -- Flags a metric the pipeline imputed at the 0.5 midpoint. Imputation *replaces*
  -- the null, so the normalized column is never null — the tell is a missing raw
  -- value alongside a normalized value of exactly 0.5.
  (  (dev_satisf_nps IS NULL              AND normalized_dev_satisf_nps = 0.5)
  OR (num_bugs_per_engineer IS NULL       AND normalized_num_bugs_per_engineer = 0.5)
  OR (code_coverage IS NULL               AND normalized_code_coverage = 0.5)
  OR (code_security IS NULL               AND normalized_code_security = 0.5)
  OR (num_prs_merged_per_engineer IS NULL AND normalized_num_prs_merged_per_engineer = 0.5)
  OR (depl_frequency IS NULL              AND normalized_depl_frequency = 0.5)
  OR (median_pr_reviewtime IS NULL        AND normalized_median_pr_reviewtime = 0.5)
  OR (median_pr_lifetime IS NULL          AND normalized_median_pr_lifetime = 0.5)
  OR (focus_nps IS NULL                   AND normalized_focus_nps = 0.5)
  )                                                 AS has_imputed_metric,
  -- how many of the nine were imputed, so "one missing" reads differently from "five"
  (  CAST(dev_satisf_nps IS NULL              AND normalized_dev_satisf_nps = 0.5 AS INT64)
   + CAST(num_bugs_per_engineer IS NULL       AND normalized_num_bugs_per_engineer = 0.5 AS INT64)
   + CAST(code_coverage IS NULL               AND normalized_code_coverage = 0.5 AS INT64)
   + CAST(code_security IS NULL               AND normalized_code_security = 0.5 AS INT64)
   + CAST(num_prs_merged_per_engineer IS NULL AND normalized_num_prs_merged_per_engineer = 0.5 AS INT64)
   + CAST(depl_frequency IS NULL              AND normalized_depl_frequency = 0.5 AS INT64)
   + CAST(median_pr_reviewtime IS NULL        AND normalized_median_pr_reviewtime = 0.5 AS INT64)
   + CAST(median_pr_lifetime IS NULL          AND normalized_median_pr_lifetime = 0.5 AS INT64)
   + CAST(focus_nps IS NULL                   AND normalized_focus_nps = 0.5 AS INT64)
  )                                                 AS imputed_count
FROM joined
ORDER BY label_path, month
