-- Reusable analytical views based on cleaned star-schema prices.
-- Calendar dates are matched explicitly instead of assuming a fixed
-- number of rows separates months.

CREATE OR REPLACE VIEW analytics.vw_monthly_price_changes AS
SELECT
    p.product_code,
    p.product_name_en,

    current_month.month_start,
    current_fact.average_price_uzs_per_kg
        AS current_price_uzs_per_kg,
    current_fact.price_status
        AS current_price_status,

    previous_month.month_start
        AS previous_month_start,
    previous_fact.average_price_uzs_per_kg
        AS previous_price_uzs_per_kg,
    previous_fact.price_status
        AS previous_price_status,

    (
        current_fact.average_price_uzs_per_kg
        - previous_fact.average_price_uzs_per_kg
    ) AS change_uzs_per_kg,

    ROUND(
        100.0 * (
            current_fact.average_price_uzs_per_kg
            - previous_fact.average_price_uzs_per_kg
        ) / NULLIF(
            previous_fact.average_price_uzs_per_kg,
            0
        ),
        2
    ) AS change_percent

FROM analytics.fact_monthly_official_price AS current_fact

JOIN analytics.dim_product AS p
    ON p.product_key = current_fact.product_key

JOIN analytics.dim_month AS current_month
    ON current_month.month_key = current_fact.month_key

LEFT JOIN analytics.dim_month AS previous_month
    ON previous_month.month_start =
       (current_month.month_start - INTERVAL '1 month')::DATE

LEFT JOIN analytics.fact_monthly_official_price AS previous_fact
    ON previous_fact.product_key = current_fact.product_key
   AND previous_fact.month_key = previous_month.month_key;


CREATE OR REPLACE VIEW analytics.vw_year_over_year_price_changes AS
SELECT
    p.product_code,
    p.product_name_en,

    current_month.month_start,
    current_fact.average_price_uzs_per_kg
        AS current_price_uzs_per_kg,
    current_fact.price_status
        AS current_price_status,

    comparison_month.month_start
        AS comparison_month_start,
    comparison_fact.average_price_uzs_per_kg
        AS price_12_months_ago_uzs_per_kg,
    comparison_fact.price_status
        AS comparison_price_status,

    (
        current_fact.average_price_uzs_per_kg
        - comparison_fact.average_price_uzs_per_kg
    ) AS change_uzs_per_kg,

    ROUND(
        100.0 * (
            current_fact.average_price_uzs_per_kg
            - comparison_fact.average_price_uzs_per_kg
        ) / NULLIF(
            comparison_fact.average_price_uzs_per_kg,
            0
        ),
        2
    ) AS yoy_change_percent

FROM analytics.fact_monthly_official_price AS current_fact

JOIN analytics.dim_product AS p
    ON p.product_key = current_fact.product_key

JOIN analytics.dim_month AS current_month
    ON current_month.month_key = current_fact.month_key

LEFT JOIN analytics.dim_month AS comparison_month
    ON comparison_month.month_start =
       (current_month.month_start - INTERVAL '1 year')::DATE

LEFT JOIN analytics.fact_monthly_official_price AS comparison_fact
    ON comparison_fact.product_key = current_fact.product_key
   AND comparison_fact.month_key = comparison_month.month_key;
