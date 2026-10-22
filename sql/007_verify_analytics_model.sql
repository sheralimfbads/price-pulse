
-- Row counts for the analytical model.

SELECT 'dim_product' AS table_name, COUNT(*) AS row_count
FROM analytics.dim_product

UNION ALL

SELECT 'dim_month', COUNT(*)
FROM analytics.dim_month

UNION ALL

SELECT 'fact_monthly_official_price', COUNT(*)
FROM analytics.fact_monthly_official_price;


-- Price quality and analytical availability.

SELECT
    price_status,
    COUNT(*) AS observations,
    COUNT(average_price_uzs_per_kg) AS analytical_prices_available
FROM analytics.fact_monthly_official_price
GROUP BY price_status
ORDER BY price_status;


-- Confirm that every product and month has exactly the expected
-- number of fact rows in this complete monthly dataset.

SELECT
    COUNT(*) AS total_fact_rows,
    COUNT(DISTINCT product_key) AS products_represented,
    COUNT(DISTINCT month_key) AS months_represented,
    COUNT(DISTINCT (product_key, month_key)) AS distinct_product_months
FROM analytics.fact_monthly_official_price;


-- First analytical query using the star schema:
-- rice's most recent 12 price observations.

SELECT
    p.product_code,
    p.product_name_en,
    m.month_start,
    f.source_price_uzs_per_kg,
    f.average_price_uzs_per_kg,
    f.price_status
FROM analytics.fact_monthly_official_price AS f

JOIN analytics.dim_product AS p
    ON p.product_key = f.product_key

JOIN analytics.dim_month AS m
    ON m.month_key = f.month_key

WHERE p.product_code = '001'
ORDER BY m.month_start DESC
LIMIT 12;
