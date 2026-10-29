-- Rank valid year-over-year price changes within each calendar month.
-- Ranks are based on the percentage change exposed by the YoY view,
-- which is rounded to two decimal places.

CREATE OR REPLACE VIEW analytics.vw_yoy_price_change_rankings AS
WITH eligible AS (
    SELECT
        product_code,
        product_name_en,
        month_start,
        comparison_month_start,
        current_price_uzs_per_kg,
        price_12_months_ago_uzs_per_kg,
        change_uzs_per_kg,
        yoy_change_percent
    FROM analytics.vw_year_over_year_price_changes
    WHERE yoy_change_percent IS NOT NULL
),
ranked AS (
    SELECT
        *,
        CASE
            WHEN yoy_change_percent > 0
            THEN RANK() OVER (
                PARTITION BY month_start
                ORDER BY yoy_change_percent DESC
            )
        END AS increase_rank,

        CASE
            WHEN yoy_change_percent < 0
            THEN RANK() OVER (
                PARTITION BY month_start
                ORDER BY yoy_change_percent ASC
            )
        END AS decrease_rank

    FROM eligible
)
SELECT *
FROM ranked;
