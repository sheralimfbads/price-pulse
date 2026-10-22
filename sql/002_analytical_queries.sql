
-- Query 1: Month-over-month price changes for rice

WITH rice_history AS (
    SELECT
        product_code,
        product_name_en,
        period,
        average_price_uzs_per_kg,

        LAG(average_price_uzs_per_kg) OVER (
            PARTITION BY product_code
            ORDER BY period
        ) AS previous_month_price

    FROM staging.official_price_observations
    WHERE product_code = '001'
)

SELECT
    product_name_en,
    period,
    average_price_uzs_per_kg AS current_price,
    previous_month_price,

    ROUND(
        average_price_uzs_per_kg - previous_month_price,
        2
    ) AS change_uzs,

    ROUND(
        100.0 * (
            average_price_uzs_per_kg - previous_month_price
        ) / NULLIF(previous_month_price, 0),
        2
    ) AS change_percent

FROM rice_history
ORDER BY period DESC
LIMIT 12;


-- Query 2: Year-over-year price changes for rice

WITH rice_history AS (
    SELECT
        product_code,
        product_name_en,
        period,
        average_price_uzs_per_kg,

        LAG(average_price_uzs_per_kg, 12) OVER (
            PARTITION BY product_code
            ORDER BY period
        ) AS price_12_months_ago

    FROM staging.official_price_observations
    WHERE product_code = '001'
)

SELECT
    product_name_en,
    period,
    average_price_uzs_per_kg AS current_price,
    price_12_months_ago,

    ROUND(
        average_price_uzs_per_kg - price_12_months_ago,
        2
    ) AS change_uzs,

    ROUND(
        100.0 * (
            average_price_uzs_per_kg - price_12_months_ago
        ) / NULLIF(price_12_months_ago, 0),
        2
    ) AS year_over_year_percent

FROM rice_history
ORDER BY period DESC
LIMIT 12;


-- Query 3: Rank products by year-over-year price change
-- Positive percentages indicate increases; negative percentages indicate decreases.

WITH price_history AS (
    SELECT
        product_code,
        product_name_en,
        period,
        average_price_uzs_per_kg,

        LAG(average_price_uzs_per_kg, 12) OVER (
            PARTITION BY product_code
            ORDER BY period
        ) AS price_12_months_ago

    FROM staging.official_price_observations
),

latest_month_changes AS (
    SELECT
        product_code,
        product_name_en,
        period,
        average_price_uzs_per_kg AS current_price,
        price_12_months_ago,

        ROUND(
            100.0 * (
                average_price_uzs_per_kg - price_12_months_ago
            ) / NULLIF(price_12_months_ago, 0),
            2
        ) AS yoy_change_percent

    FROM price_history

    WHERE period = (
        SELECT MAX(period)
        FROM staging.official_price_observations
    )
)

SELECT
    product_code,
    product_name_en,
    period,
    current_price,
    price_12_months_ago,
    yoy_change_percent,

    RANK() OVER (
        ORDER BY yoy_change_percent DESC
    ) AS change_rank

FROM latest_month_changes

WHERE current_price IS NOT NULL
  AND price_12_months_ago IS NOT NULL

ORDER BY change_rank, product_code
LIMIT 10;

