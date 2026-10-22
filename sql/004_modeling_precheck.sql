
-- Check how many distinct descriptive versions exist per product.

WITH product_name_versions AS (
    SELECT DISTINCT
        product_code,
        product_name_uz,
        product_name_ru,
        product_name_en,
        product_name_uz_cyrillic
    FROM staging.official_price_observations
)

SELECT
    product_code,
    COUNT(*) AS distinct_name_versions
FROM product_name_versions
GROUP BY product_code
HAVING COUNT(*) > 1
ORDER BY product_code;
