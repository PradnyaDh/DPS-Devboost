-- Open Codacy security issues per repo, one row per issue, for the months the
-- explorer can display.
--
-- Keyed to a month by taking each month's LAST weekly Codacy load, so the list
-- tracks the selected month like every other metric rather than always showing
-- today. Loads are weekly (3-5 per month through 2026).
--
-- Severity uses Codacy's own three tiers, not the DevBoost report's two. The
-- report renders High and Error alike as CRITICAL; Codacy's UI shows HIGH and
-- CRITICAL separately, and the raw pattern ids agree with Codacy -- 'critical'
-- patterns appear only under Error, 'high' only under High, 'medium' only under
-- Warning. Verified against Codacy's own issue page for logistics-pyosrm.
--
-- Repos come from the DevHub catalog by squad_id; the hierarchy is applied
-- downstream from the DevBoost snapshot. Counts will therefore not match the
-- report's for large teams, which uses its own repo->team mapping.

WITH repos AS (
  SELECT DISTINCT
    squad_id,
    REGEXP_REPLACE(repo, r'^deliveryhero/', '') AS repo
  FROM `fulfillment-dwh-production.cl.tech_log_devhub_catalog`,
       UNNEST(github_repositories) AS repo
  WHERE archived IS NOT TRUE AND squad_id IS NOT NULL AND repo != ''
),

-- Last load of each month, so one month maps to one set of open issues.
month_end AS (
  SELECT FORMAT_DATE('%Y-%m', _loaded_date) AS month, MAX(_loaded_date) AS loaded
  FROM `fulfillment-dwh-production.curated_data_shared_psf.dev_productivity_codacy_issues`
  WHERE _loaded_date >= '2026-02-01'
  GROUP BY month
)

SELECT
  m.month,
  r.squad_id,
  c.repository_name AS repo,
  i.issue_id,
  -- Codacy's tiers. Error is its CRITICAL; High and Warning are its own labels.
  CASE i.pattern_info.severity_level
    WHEN 'Error'   THEN 'critical'
    WHEN 'High'    THEN 'high'
    WHEN 'Warning' THEN 'medium'
    WHEN 'Info'    THEN 'minor'
  END AS severity,
  i.pattern_info.sub_category AS kind,
  i.pattern_info.id           AS pattern,
  i.message,
  i.file_path,
  i.line_number,
  m.loaded AS loaded_date
FROM `fulfillment-dwh-production.curated_data_shared_psf.dev_productivity_codacy_issues` c
JOIN month_end m ON m.loaded = c._loaded_date
JOIN repos r ON r.repo = c.repository_name
CROSS JOIN UNNEST(c.issues) AS i
WHERE c.organization = 'deliveryhero'
  AND i.pattern_info.category = 'Security'
ORDER BY m.month, r.squad_id, c.repository_name, severity, i.file_path
