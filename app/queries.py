
OVERVIEW_SQL = """
SELECT
    (SELECT MAX(month_start) FROM analytics.dim_month) AS latest_month,
    (SELECT COUNT(*) FROM analytics.dim_product) AS product_count,
    (
        SELECT COUNT(*)
        FROM analytics.fact_monthly_official_price
        WHERE average_price_uzs_per_kg IS NOT NULL
    ) AS available_observations,
    (
        SELECT COUNT(*)
        FROM analytics.fact_monthly_official_price
        WHERE average_price_uzs_per_kg IS NULL
    ) AS unavailable_observations,
    (
        SELECT COUNT(*)
        FROM analytics.fact_monthly_official_price
    ) AS total_observations,
    (
        SELECT snapshot_filename
        FROM audit.source_snapshot
        ORDER BY fetched_at_utc DESC, snapshot_filename DESC
        LIMIT 1
    ) AS latest_source_snapshot,
    (
        SELECT fetched_at_utc
        FROM audit.source_snapshot
        ORDER BY fetched_at_utc DESC, snapshot_filename DESC
        LIMIT 1
    ) AS latest_source_fetched_at_utc
"""

READY_SQL = """
SELECT
    to_regclass('analytics.dim_product') IS NOT NULL
    AND to_regclass('analytics.dim_month') IS NOT NULL
    AND to_regclass('analytics.fact_monthly_official_price') IS NOT NULL
    AND to_regclass('analytics.vw_monthly_price_changes') IS NOT NULL
    AND to_regclass('analytics.vw_year_over_year_price_changes') IS NOT NULL
    AND to_regclass('analytics.vw_yoy_price_change_rankings') IS NOT NULL
        AS ready
"""

PRODUCTS_SQL = """
SELECT
    product_code,
    product_name_uz,
    product_name_ru,
    product_name_en,
    product_name_uz_cyrillic
FROM analytics.dim_product
WHERE (
    %(search)s::text IS NULL
    OR product_code ILIKE %(search_like)s
    OR product_name_en ILIKE %(search_like)s
    OR product_name_uz ILIKE %(search_like)s
    OR product_name_ru ILIKE %(search_like)s
)
ORDER BY product_code
LIMIT %(limit)s
OFFSET %(offset)s
"""

PRODUCTS_COUNT_SQL = """
SELECT COUNT(*) AS total
FROM analytics.dim_product
WHERE (
    %(search)s::text IS NULL
    OR product_code ILIKE %(search_like)s
    OR product_name_en ILIKE %(search_like)s
    OR product_name_uz ILIKE %(search_like)s
    OR product_name_ru ILIKE %(search_like)s
)
"""

PRODUCT_SQL = """
SELECT
    product_code,
    product_name_uz,
    product_name_ru,
    product_name_en,
    product_name_uz_cyrillic
FROM analytics.dim_product
WHERE product_code = %(product_code)s
"""

PRODUCT_PRICES_SQL = """
SELECT
    product_code,
    product_name_en,
    month_start,
    current_price_uzs_per_kg,
    current_price_status,
    previous_month_start,
    previous_price_uzs_per_kg,
    previous_price_status,
    change_uzs_per_kg,
    change_percent
FROM analytics.vw_monthly_price_changes
WHERE product_code = %(product_code)s
  AND (%(from_month)s::date IS NULL OR month_start >= %(from_month)s)
  AND (%(to_month)s::date IS NULL OR month_start <= %(to_month)s)
ORDER BY month_start
LIMIT %(limit)s
OFFSET %(offset)s
"""

PRODUCT_PRICES_COUNT_SQL = """
SELECT COUNT(*) AS total
FROM analytics.vw_monthly_price_changes
WHERE product_code = %(product_code)s
  AND (%(from_month)s::date IS NULL OR month_start >= %(from_month)s)
  AND (%(to_month)s::date IS NULL OR month_start <= %(to_month)s)
"""

LATEST_MONTH_SQL = """
SELECT MAX(month_start) AS latest_month
FROM analytics.dim_month
"""

LATEST_MOVERS_SQL = """
SELECT
    product_code,
    product_name_en,
    month_start,
    comparison_month_start,
    current_price_uzs_per_kg,
    price_12_months_ago_uzs_per_kg,
    change_uzs_per_kg,
    yoy_change_percent,
    increase_rank,
    decrease_rank
FROM analytics.vw_yoy_price_change_rankings
WHERE month_start = %(month_start)s
  AND (
        (%(direction)s = 'increase' AND increase_rank IS NOT NULL)
        OR (%(direction)s = 'decrease' AND decrease_rank IS NOT NULL)
      )
ORDER BY
    CASE WHEN %(direction)s = 'increase' THEN increase_rank END,
    CASE WHEN %(direction)s = 'decrease' THEN decrease_rank END,
    product_code
LIMIT %(limit)s
"""
