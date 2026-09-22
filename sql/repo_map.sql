-- Squad -> GitHub repos for Logistics, with Codacy issue coverage per repo.
--
-- Three populations meet here and they do not agree; the point of this query is to
-- keep the disagreements visible rather than inner-joining them away:
--
--   1. DevHub catalog  - who owns which repo
--   2. DevBoost        - which squads are scored (joined downstream, from the snapshot)
--   3. Codacy issues   - which repos are actually analysed
--
-- Joined on squad_id only. The catalog's own product_line / tribe / domain columns
-- disagree with DevBoost's hierarchy in places, so the hierarchy is taken from the
-- DevBoost snapshot downstream instead of from here.
--
-- Logistics only: cl.tech_log_devhub_catalog is a Logistics mirror, and the cross-org
-- developer-portal-336415.devhub_export.catalog_production is not readable with the
-- access this runs under.
--
-- `archived IS NOT TRUE` rather than `NOT archived`: equivalent today (no NULLs) but
-- does not silently drop rows if the column ever becomes nullable.

WITH catalog AS (
  SELECT DISTINCT
    squad_id,
    squad,
    REGEXP_REPLACE(repo, r'^deliveryhero/', '') AS repo
  FROM `fulfillment-dwh-production.cl.tech_log_devhub_catalog`,
       UNNEST(github_repositories) AS repo
  WHERE archived IS NOT TRUE
    AND squad_id IS NOT NULL
    AND repo != ''
),

-- Most recent Codacy load. One row per (repo, load date) with issues nested.
latest_load AS (
  SELECT MAX(_loaded_date) AS d
  FROM `fulfillment-dwh-production.curated_data_shared_psf.dev_productivity_codacy_issues`
),

codacy AS (
  SELECT
    c.repository_name AS repo,
    COUNTIF(i.pattern_info.category = 'Security')                                     AS sec_issues,
    COUNTIF(i.pattern_info.category = 'Security'
            AND i.pattern_info.severity_level IN ('High','Error'))                    AS sec_critical,
    COUNTIF(i.pattern_info.category = 'Security'
            AND i.pattern_info.severity_level = 'Warning')                            AS sec_medium,
    COUNTIF(i.pattern_info.category = 'Security'
            AND i.pattern_info.severity_level = 'Info')                               AS sec_minor,
    COUNT(*)                                                                          AS all_issues
  FROM `fulfillment-dwh-production.curated_data_shared_psf.dev_productivity_codacy_issues` c
  CROSS JOIN UNNEST(c.issues) AS i
  WHERE c._loaded_date = (SELECT d FROM latest_load)
    AND c.organization = 'deliveryhero'
  GROUP BY repo
)

SELECT
  cat.squad_id,
  cat.squad,
  cat.repo,
  -- A repo with no Codacy row is not analysed at all; one with a row and zero
  -- security issues is analysed and clean. Distinguishing them matters.
  cd.repo IS NOT NULL                    AS in_codacy,
  IFNULL(cd.sec_issues, 0)               AS sec_issues,
  IFNULL(cd.sec_critical, 0)             AS sec_critical,
  IFNULL(cd.sec_medium, 0)               AS sec_medium,
  IFNULL(cd.sec_minor, 0)                AS sec_minor,
  IFNULL(cd.all_issues, 0)               AS all_issues,
  (SELECT d FROM latest_load)            AS codacy_loaded_date
FROM catalog cat
LEFT JOIN codacy cd ON cd.repo = cat.repo
ORDER BY cat.squad_id, cat.repo
